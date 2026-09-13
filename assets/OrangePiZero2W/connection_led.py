"""Connection status LED policy; no UART reads or network work in callbacks."""
import threading


class ConnectionLED:
    def __init__(self, send):
        self._send = send
        self._lock = threading.Lock()
        self._wifi_connected = False
        self._server_connected = False
        self._last_command = None

    def update(self, *, wifi_connected=None, server_connected=None):
        with self._lock:
            if wifi_connected is not None:
                self._wifi_connected = bool(wifi_connected)
            if server_connected is not None:
                self._server_connected = bool(server_connected)
            if not self._wifi_connected:
                command = '0LR01'  # Red blink: no WiFi association
            elif not self._server_connected:
                command = '0LG01'  # Green blink: WiFi, waiting for server
            else:
                command = '0LG00'  # Green solid: server connected
            # Preserve manual locate commands while connection state is stable.
            # Failed writes are retried at the next observation.
            if command != self._last_command and self._send(command):
                self._last_command = command
