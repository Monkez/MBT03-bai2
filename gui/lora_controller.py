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
    configuration_busy = pyqtSignal(bool)
    configuration_finished = pyqtSignal(bool, str)
    command_finished = pyqtSignal(str, bool, int)
    command_sent = pyqtSignal(str, float, float)  # command, queued_at, sent_at
    sequence_finished = pyqtSignal()
    target_state_received = pyqtSignal(int, bool, float, float)  # target, visible, requested_at, received_at

    DEFAULT_PORT_DESCRIPTION = cf.config_str(
        "lora.port_description", "USB Serial Port"
    )
    DEFAULT_BAUD_RATE = 9600
    E32_CHANNEL_CODES = {1: 0x01, 2: 0x03, 3: 0x05}
    E32_SWITCH_SECONDS = 0.2
    E32_CONFIG_ATTEMPTS = 3
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
        self._channel = cf.config_int("shooting.control_channel", 1, minimum=1, maximum=3)
        self.connection_error = ""
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
    def channel(self):
        return self._channel

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
            return self.request_connection(port_name, self._channel)
        self._report_connection(False, "Không tìm thấy cổng USB Serial Port")
        return False

    def request_connection(self, port_name, channel, *, force_channel=False):
        """Queue the port/channel change behind any pending device commands."""
        if self._closing:
            return False
        self.configuration_busy.emit(True)
        self._executor.submit(self._configure_connection, port_name, channel, force_channel)
        return True

    def _configure_connection(self, port_name, channel, force_channel):
        try:
            self.connect_port(port_name, channel, force_channel=force_channel)
        finally:
            self.configuration_busy.emit(False)

    def connect_port(self, port_name, channel=None, *, force_channel=False):
        port_name = (port_name or "").strip()
        channel = self._channel if channel is None else channel
        if type(channel) is not int or channel not in self.E32_CHANNEL_CODES:
            message = "Chọn Kênh 1, 2 hoặc 3"
            self._report_connection(False, message)
            self.configuration_finished.emit(False, message)
            return False
        with self._lock:
            if self._closing:
                connected, message = False, "Đang đóng LoRa"
            elif self._serial is not None and self._serial.is_open and self._port_name == port_name:
                connected, message = True, f"{port_name} · Đã mở cổng"
            else:
                self._close_locked()
                self._port_name = port_name or None
                if port_name:
                    connected, message = self._open_port_locked()
                else:
                    connected, message = False, "Không sử dụng LoRa"
            self._channel = channel
            applied = connected or not port_name
            apply_message = message
            if connected and force_channel:
                applied, apply_message = self._apply_channel_locked()
        self._report_connection(connected, message)
        self.configuration_finished.emit(applied, apply_message)
        return connected and applied

    def _report_connection(self, connected, message):
        self.connection_error = message if not connected and self._port_name else ""
        self.connection_changed.emit(connected, message)

    def _open_port_locked(self):
        port_name = self._port_name
        if serial is None:
            return False, "Chưa cài thư viện pyserial"
        if self._closing:
            return False, "Đang đóng LoRa"
        try:
            self._serial = serial.Serial(
                port=port_name, baudrate=self.DEFAULT_BAUD_RATE,
                timeout=0.2, write_timeout=self.ACK_TIMEOUT_SECONDS,
            )
        except (OSError, serial.SerialException) as error:
            return False, f"Không mở được {port_name}: {error}"
        return True, f"{port_name} · Đã mở cổng"

    def _apply_channel_locked(self):
        port_name, channel = self._port_name, self._channel
        try:
            if self._program_e32_channel(self._serial, channel) and not self._closing:
                return True, f"{port_name} · Kênh {channel}"
            return False, f"{port_name} · E32 chưa xác nhận Kênh {channel}"
        except (OSError, serial.SerialException) as error:
            return False, f"{port_name} · Lỗi đặt Kênh {channel}: {error}"

    def _program_e32_channel(self, device, channel):
        frame = bytes((0xC0, 0x00, 0x00, 0x1A, self.E32_CHANNEL_CODES[channel], 0x44))
        try:
            for _ in range(self.E32_CONFIG_ATTEMPTS):
                if self._closing:
                    return False
                device.setRTS(False)
                if self._stop_event.wait(self.E32_SWITCH_SECONDS):
                    return False
                device.reset_input_buffer()
                if device.write(frame) != len(frame):
                    continue
                device.flush()
                if self._stop_event.wait(self.E32_SWITCH_SECONDS):
                    return False
                if device.read(len(frame)) == frame:
                    return True
            return False
        finally:
            device.setRTS(True)
            self._stop_event.wait(self.E32_SWITCH_SECONDS)

    def disconnect_port(self):
        with self._lock:
            self._close_locked()
            self._port_name = None
            self.connection_error = ""

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
        requires_ack = command != "@661#"
        status_query = command == "@448#"
        attempts = 0
        success = False

        connection_result = None
        with self._lock:
            device = self._serial
            if not self._closing and self._port_name and (device is None or not device.is_open):
                self._close_locked()
                connection_result = self._open_port_locked()
                device = self._serial

            max_attempts = self.MAX_ATTEMPTS if requires_ack and not status_query else 1
            if command == "@444#":
                max_attempts = min(max_attempts, 3)
            for attempts in range(1, max_attempts + 1):
                if self._closing or device is None or not device.is_open:
                    attempts = 0
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
                    connection_result = (False, f"{self._port_name} · Mất kết nối LoRa")
                    break

        if connection_result is not None:
            self._report_connection(*connection_result)
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
