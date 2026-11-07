import re
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
    command_sent = pyqtSignal(str, float, float)  # command, queued_at, sent_at
    sequence_finished = pyqtSignal()
    target_state_received = pyqtSignal(int, bool, float, float)  # target, visible, requested_at, received_at

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
        self._stop_event = threading.Event()
        self._query_lock = threading.Lock()
        self._target8_query_pending = False

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
            self._port_name = None

    def send_command(self, command):
        if not self._closing:
            self._executor.submit(self._send_with_retry, command, time.monotonic())

    def query_target8_state(self):
        with self._query_lock:
            if self._closing or self._target8_query_pending:
                return False
            self._target8_query_pending = True
            self._executor.submit(self._query_target8_state, time.monotonic())
        return True

    def _query_target8_state(self, requested_at):
        try:
            self._send_with_retry("@448#", requested_at)
        finally:
            with self._query_lock:
                self._target8_query_pending = False

    def send_sequence(self, commands):
        """Queue one ordered batch; no other queued commands can interleave."""
        if self._closing:
            return False
        self._executor.submit(self._send_sequence, tuple(commands), time.monotonic())
        return True

    def _send_sequence(self, commands, queued_at):
        try:
            for index, command in enumerate(commands):
                if self._closing:
                    break
                success = self._send_with_retry(command, queued_at)
                # Exhausted retries advance immediately; ACK adds a 100 ms gap.
                if success and index < len(commands) - 1:
                    if self._stop_event.wait(0.1):
                        break
        finally:
            self.sequence_finished.emit()

    def _send_with_retry(self, command, queued_at=None):
        queued_at = time.monotonic() if queued_at is None else queued_at
        payload = command.encode("ascii")
        # Broadcast and carriage launch are sent once; poll 8C for its state.
        requires_ack = command not in ("@661#", "@444#")
        status_query = command == "@448#"
        attempts = 0
        success = False

        with self._lock:
            device = self._serial
            if device is None or not device.is_open:
                port_name = self._port_name
                if not port_name or serial is None:
                    self.command_finished.emit(command, False, attempts)
                    return False
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
                    return False

            max_attempts = self.MAX_ATTEMPTS if requires_ack and not status_query else 1
            for attempts in range(1, max_attempts + 1):
                if self._closing:
                    break
                try:
                    device.reset_input_buffer()
                    device.write(payload)
                    device.flush()
                    if attempts == 1:
                        self.command_sent.emit(command, queued_at, time.monotonic())
                    if status_query:
                        success = self._wait_for_target8_state(device, queued_at)
                        break
                    if not requires_ack or self._wait_for_echo(device, payload):
                        success = True
                        break
                except (OSError, serial.SerialException):
                    self._close_locked()
                    break

        self.command_finished.emit(command, success, attempts)
        return success

    def _wait_for_target8_state(self, device, requested_at):
        deadline = time.monotonic() + min(self.ACK_TIMEOUT_SECONDS, 1.0)
        received = bytearray()
        while not self._closing and time.monotonic() < deadline:
            chunk = device.read(max(1, device.in_waiting))
            if chunk:
                received.extend(chunk)
                match = re.search(rb"(?:^|[\r\n#])@448([01])\r?\n", received)
                if match:
                    self.target_state_received.emit(3, match[1] == b"1", requested_at, time.monotonic())
                    return True
                if len(received) > 256:
                    del received[:-32]
        return False

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

    def close(self, final_commands=()):
        self._closing = True
        self._stop_event.set()
        # Abort pending raises before the final hides; shutdown must not cancel
        # the only hide of a target raised with a persistent manual command.
        with self._lock:
            device = self._serial
            if device is not None and device.is_open:
                for command in final_commands:
                    try:
                        device.write(command.encode("ascii"))
                        device.flush()
                    except (OSError, serial.SerialException):
                        break
        self.disconnect_port()
        self._executor.shutdown(wait=False, cancel_futures=True)
