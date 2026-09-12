import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtCore import QObject, pyqtSignal

import config as cf

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # Keep the application importable before dependencies are installed.
    serial = None
    list_ports = None


class LoraController(QObject):
    """Own the LoRa serial port and send acknowledged commands off the UI thread."""

    connection_changed = pyqtSignal(bool, str)
    command_finished = pyqtSignal(str, bool, int)

    DEFAULT_PORT_DESCRIPTION = cf.config_str(
        "lora.port_description", "USB Serial Port"
    )
    DEFAULT_BAUD_RATE = cf.config_int(
        "lora.baud_rate", 9600, minimum=300, maximum=4000000
    )
    ACK_TIMEOUT_SECONDS = cf.config_float(
        "lora.ack_timeout_seconds", 1.0, minimum=0.01, maximum=60.0
    )
    MAX_ATTEMPTS = cf.config_int(
        "lora.max_attempts", 3, minimum=1, maximum=20
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._serial = None
        self._port_name = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="LoRa")
        self._closing = False

    @property
    def port_name(self):
        return self._port_name

    @property
    def is_connected(self):
        with self._lock:
            return bool(self._serial is not None and self._serial.is_open)

    @staticmethod
    def available_ports():
        if list_ports is None:
            return []
        return [
            {"device": port.device, "description": port.description or ""}
            for port in list_ports.comports()
        ]

    @classmethod
    def default_port_name(cls):
        expected = cls.DEFAULT_PORT_DESCRIPTION.casefold()
        for port in cls.available_ports():
            if expected in port["description"].casefold():
                return port["device"]
        return None

    def auto_connect(self):
        port_name = self.default_port_name()
        if port_name:
            return self.connect_port(port_name)
        self.connection_changed.emit(False, "Khong tim thay USB Serial Port")
        return False

    def connect_port(self, port_name):
        port_name = (port_name or "").strip()
        if not port_name:
            self.disconnect_port()
            self.connection_changed.emit(False, "Chua chon cong COM LoRa")
            return False
        if serial is None:
            self.connection_changed.emit(False, "Chua cai dat thu vien pyserial")
            return False

        with self._lock:
            if self._serial is not None and self._serial.is_open and self._port_name == port_name:
                return True
            self._close_locked()
            try:
                self._serial = serial.Serial(
                    port=port_name,
                    baudrate=self.DEFAULT_BAUD_RATE,
                    timeout=0.1,
                    write_timeout=self.ACK_TIMEOUT_SECONDS,
                )
                self._port_name = port_name
            except (OSError, serial.SerialException) as exc:
                self._serial = None
                self._port_name = port_name
                self.connection_changed.emit(False, f"Khong mo duoc {port_name}: {exc}")
                return False

        self.connection_changed.emit(True, port_name)
        return True

    def disconnect_port(self):
        with self._lock:
            self._close_locked()

    def send_command(self, command):
        if not self._closing:
            self._executor.submit(self._send_with_retry, command)

    def _send_with_retry(self, command):
        payload = command.encode("ascii")
        attempts = 0
        success = False

        with self._lock:
            device = self._serial
            if device is None or not device.is_open:
                port_name = self._port_name
                if not port_name or serial is None:
                    self.command_finished.emit(command, False, attempts)
                    return
                try:
                    device = serial.Serial(
                        port=port_name,
                        baudrate=self.DEFAULT_BAUD_RATE,
                        timeout=0.1,
                        write_timeout=self.ACK_TIMEOUT_SECONDS,
                    )
                    self._serial = device
                    self.connection_changed.emit(True, port_name)
                except (OSError, serial.SerialException):
                    self.command_finished.emit(command, False, attempts)
                    return

            for attempts in range(1, self.MAX_ATTEMPTS + 1):
                if self._closing:
                    break
                try:
                    device.reset_input_buffer()
                    device.write(payload)
                    device.flush()
                    if self._wait_for_echo(device, payload):
                        success = True
                        break
                except (OSError, serial.SerialException):
                    self._close_locked()
                    break

        self.command_finished.emit(command, success, attempts)

    def _wait_for_echo(self, device, payload):
        deadline = time.monotonic() + self.ACK_TIMEOUT_SECONDS
        received = bytearray()
        while not self._closing and time.monotonic() < deadline:
            chunk = device.read(max(1, device.in_waiting))
            if chunk:
                received.extend(chunk)
                if bytes(received).strip() == payload:
                    return True
                if len(received) > len(payload) + 4:
                    return False
        return False

    def _close_locked(self):
        device = self._serial
        self._serial = None
        if device is not None:
            try:
                device.close()
            except (OSError, serial.SerialException):
                pass

    def close(self):
        self._closing = True
        self.disconnect_port()
        self._executor.shutdown(wait=False, cancel_futures=True)
