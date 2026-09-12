# -*- coding: utf-8 -*-
"""
Protocol definitions for MBT03 Server-Client system.
V3: Three isolated channels + adaptive heartbeat + RTT monitoring.
"""

import json
import re
import threading


class PortMapping:
    """Maps port_id (1-4) to TCP port numbers."""
    
    MAP = {
        1: 1711,
        2: 1995,
        3: 1999,
        4: 2026,
    }
    
    DATA_PORT_OFFSET = 100  # Data channel = control port + 100
    STREAM_PORT_OFFSET = 200 # Stream channel = control port + 200
    
    REVERSE_MAP = {v: k for k, v in MAP.items()}
    
    @classmethod
    def get_port(cls, port_id: int) -> int:
        if port_id not in cls.MAP:
            raise ValueError(f"Invalid port_id: {port_id}. Must be 1-4.")
        return cls.MAP[port_id]
    
    @classmethod
    def get_data_port(cls, port_id: int) -> int:
        """Data channel port = control port + offset."""
        return cls.get_port(port_id) + cls.DATA_PORT_OFFSET
    
    @classmethod
    def get_stream_port(cls, port_id: int) -> int:
        """Stream channel port = control port + stream offset."""
        return cls.get_port(port_id) + cls.STREAM_PORT_OFFSET
    
    @classmethod
    def get_port_id(cls, port: int) -> int:
        if port not in cls.REVERSE_MAP:
            raise ValueError(f"Unknown port: {port}")
        return cls.REVERSE_MAP[port]
    
    @classmethod
    def all_port_ids(cls):
        return list(cls.MAP.keys())
    
    @classmethod
    def all_ports(cls):
        return list(cls.MAP.values())


class Protocol:
    """Message types and constants."""
    
    # Zeroconf
    SERVICE_TYPE = "_mbt03sc._tcp.local."
    SERVICE_NAME_PREFIX = "MBT03-Port"
    
    # === Control channel messages (ROUTER-DEALER) ===
    MSG_CONNECT_REQUEST = b'CONNECT_REQ'
    MSG_CONNECT_ACK = b'CONNECT_ACK'
    MSG_CONNECT_REJECT = b'CONNECT_REJECT'
    MSG_HEARTBEAT = b'HEARTBEAT'
    MSG_HEARTBEAT_ACK = b'HEARTBEAT_ACK'
    MSG_DISCONNECT = b'DISCONNECT'
    MSG_DATA = b'DATA'
    MSG_DATA_ACK = b'DATA_ACK'
    MSG_SHOOT_NOTIFY = b'SHOOT'          # Instant notification (control channel)
    MSG_STREAM_START = b'STREAM_ON'      # Server→client command
    MSG_STREAM_STOP = b'STREAM_OFF'      # Server→client command
    MSG_SET_Q0 = b'SET_Q0'              # Server→client: calibration data
    MSG_UART_CMD = b'UART_CMD'          # Server→client: command to write to UART
    MSG_WIFI_CONFIG_REQUEST = b'WIFI_CFG_REQ'
    MSG_WIFI_CONFIG_ACK = b'WIFI_CFG_ACK'
    MSG_WIFI_CONFIG_STATUS = b'WIFI_CFG_STATUS'
    MSG_WIFI_CONFIG_COMMIT = b'WIFI_CFG_COMMIT'
    MSG_WIFI_CONFIG_ROLLBACK = b'WIFI_CFG_ROLLBACK'
    
    
    # === Dedicated PUSH-PULL channel messages ===
    MSG_SHOOT_IMAGE = b'SHOOT_IMG'       # Full image (data channel)
    MSG_STREAM_FRAME = b'STREAM_FRM'     # Legacy control-stream compatibility
    
    # === Heartbeat / connection state machine ===
    # A soft state is reported before either side tears the TCP/ZMQ session
    # down.  This makes loss visible quickly without turning a short Wi-Fi
    # stall into a reconnect loop.
    HEARTBEAT_INTERVAL = 1.0
    CONNECTION_DEGRADED_TIMEOUT = 3.5
    CONNECTION_OFFLINE_TIMEOUT = 6.0
    CLIENT_RECONNECT_TIMEOUT = 8.0
    SERVER_SESSION_TIMEOUT = 15.0
    RECOVERY_ACK_COUNT = 2

    CONNECTION_STATE_HEALTHY = "healthy"
    CONNECTION_STATE_DEGRADED = "degraded"
    CONNECTION_STATE_OFFLINE = "offline"
    CONNECTION_STATE_SESSION_EXPIRED = "session-expired"

    # Backward-compatible aliases used by older call sites and deployments.
    HEARTBEAT_TIMEOUT = SERVER_SESSION_TIMEOUT
    CLIENT_DISCONNECT_TIMEOUT = CLIENT_RECONNECT_TIMEOUT
    
    # === Adaptive Heartbeat ===
    HEARTBEAT_MIN_INTERVAL = 0.5         # Fast probe while the link is degraded
    HEARTBEAT_MAX_INTERVAL = 1.5         # Stable link, still detects loss promptly
    RTT_GOOD_MS = 100
    RTT_WARN_MS = 500
    RTT_BAD_MS = 1000
    RTT_WINDOW_SIZE = 5                  # Smaller window → react faster to changes
    
    # === Discovery ===
    PRIOR_SEARCH_TIMEOUT = 30.0
    SEARCH_RETRY_INTERVAL = 0.3           # Check frequently for Hub updates
    
    # === Reconnection ===
    RECONNECT_MIN_DELAY = 0.1             # Near-instant first retry
    RECONNECT_MAX_DELAY = 3.0             # Cap backoff lower (was 5s)
    DIRECT_PROBE_TIMEOUT = 0.5            # More tolerant probe for weak WiFi
    
    # Config
    CLIENT_CONFIG_FILE = "client_port_config.json"

    WIFI_COMMAND_PREFIX = "Wifi#"
    PROTOCOL_VERSION = 3
    WIFI_CONFIG_VERSION = 1
    CAPABILITY_WIFI_CONFIG_V1 = "wifi_config_v1"
    WIFI_REQUEST_ID_PATTERN = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9_.-]{7,63}$"
    )
    _CONNECTION_CONFIG_LOCK = threading.RLock()
    _MEDIA_CONFIG_LOCK = threading.RLock()
    
    # Camera
    SHOOT_RESOLUTION = (640, 480)
    STREAM_RESOLUTION = (400, 300)       # 4:3 ratio matching 640x480
    STREAM_JPEG_QUALITY = 40
    SHOOT_JPEG_QUALITY = 65
    STREAM_FPS_TARGET = 25
    
    @staticmethod
    def make_service_name(port_id: int) -> str:
        return f"{Protocol.SERVICE_NAME_PREFIX}{port_id}.{Protocol.SERVICE_TYPE}"
    
    @staticmethod
    def encode_payload(data: dict) -> bytes:
        return json.dumps(data).encode('utf-8')
    
    @staticmethod
    def decode_payload(data: bytes) -> dict:
        return json.loads(data.decode('utf-8'))

    @staticmethod
    def redact_uart_command(command: str) -> str:
        """Return a log-safe UART command without exposing Wi-Fi passwords."""
        text = str(command).strip()
        if text.lower().startswith(Protocol.WIFI_COMMAND_PREFIX.lower()):
            parts = text.split('#', 2)
            ssid = parts[1] if len(parts) > 1 else ""
            return f"Wifi#{ssid}#[REDACTED]"
        return text

    @staticmethod
    def is_legacy_wifi_command(command: str) -> bool:
        return str(command).strip().lower().startswith(
            Protocol.WIFI_COMMAND_PREFIX.lower()
        )

    @staticmethod
    def validate_wifi_credentials(ssid, password):
        """Return normalized Wi-Fi credentials or raise ``ValueError``."""
        if not isinstance(ssid, str) or not ssid:
            raise ValueError("SSID is required")
        if len(ssid.encode("utf-8")) > 32 or "#" in ssid:
            raise ValueError("SSID must be 1..32 bytes and cannot contain #")
        if any(ord(char) < 32 or ord(char) == 127 for char in ssid):
            raise ValueError("SSID contains control characters")
        if not isinstance(password, str) or not 8 <= len(password) <= 63:
            raise ValueError("Wi-Fi password must contain 8..63 characters")
        if any(ord(char) < 32 or ord(char) == 127 for char in password):
            raise ValueError("Wi-Fi password contains control characters")
        return ssid, password

    @staticmethod
    def validate_wifi_request_id(request_id):
        request_id = str(request_id or "")
        if not Protocol.WIFI_REQUEST_ID_PATTERN.fullmatch(request_id):
            raise ValueError("Invalid Wi-Fi request_id")
        return request_id

    @staticmethod
    def client_supports_wifi_config(client_info):
        if not isinstance(client_info, dict):
            return False
        capabilities = client_info.get("capabilities", ())
        try:
            protocol_version = int(
                client_info.get("protocol_version", 0) or 0
            )
        except (TypeError, ValueError):
            return False
        return (
            isinstance(capabilities, (list, tuple))
            and Protocol.CAPABILITY_WIFI_CONFIG_V1 in capabilities
            and protocol_version >= Protocol.PROTOCOL_VERSION
        )

    @classmethod
    def connection_settings(cls) -> dict:
        """Return the active, JSON-safe heartbeat policy."""
        with cls._CONNECTION_CONFIG_LOCK:
            return {
                'heartbeat_interval_seconds': cls.HEARTBEAT_INTERVAL,
                'heartbeat_min_interval_seconds': cls.HEARTBEAT_MIN_INTERVAL,
                'heartbeat_max_interval_seconds': cls.HEARTBEAT_MAX_INTERVAL,
                'degraded_after_seconds': cls.CONNECTION_DEGRADED_TIMEOUT,
                'offline_after_seconds': cls.CONNECTION_OFFLINE_TIMEOUT,
                'client_reconnect_after_seconds': cls.CLIENT_RECONNECT_TIMEOUT,
                'session_release_after_seconds': cls.SERVER_SESSION_TIMEOUT,
                'recovery_ack_count': cls.RECOVERY_ACK_COUNT,
                'rtt_good_ms': cls.RTT_GOOD_MS,
                'rtt_warn_ms': cls.RTT_WARN_MS,
                'rtt_bad_ms': cls.RTT_BAD_MS,
                'rtt_window_size': cls.RTT_WINDOW_SIZE,
            }

    @classmethod
    def configure_connection(cls, settings: dict) -> dict:
        """Validate and atomically apply connection settings.

        The server sends this policy in ``CONNECT_ACK`` so an Orange Pi uses
        exactly the same thresholds as the app.  Invalid/untrusted values are
        rejected before any class constant changes.
        """
        if not isinstance(settings, dict):
            raise ValueError("connection settings must be an object")

        required = (
            'heartbeat_interval_seconds',
            'heartbeat_min_interval_seconds',
            'heartbeat_max_interval_seconds',
            'degraded_after_seconds',
            'offline_after_seconds',
            'client_reconnect_after_seconds',
            'session_release_after_seconds',
            'recovery_ack_count',
            'rtt_good_ms',
            'rtt_warn_ms',
            'rtt_bad_ms',
            'rtt_window_size',
        )
        missing = [key for key in required if key not in settings]
        if missing:
            raise ValueError(
                "missing connection settings: " + ", ".join(missing))

        timeout_keys = required[:7]
        values = {}
        for key in timeout_keys:
            value = settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"connection.{key} must be a number")
            value = float(value)
            if not 0.1 <= value <= 300.0:
                raise ValueError(f"connection.{key} is outside 0.1..300")
            values[key] = value

        recovery_count = settings['recovery_ack_count']
        if (
            isinstance(recovery_count, bool)
            or not isinstance(recovery_count, int)
            or not 1 <= recovery_count <= 10
        ):
            raise ValueError("connection.recovery_ack_count must be 1..10")

        for key in ('rtt_good_ms', 'rtt_warn_ms', 'rtt_bad_ms'):
            value = settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"connection.{key} must be a number")
            value = float(value)
            if not 1.0 <= value <= 10000.0:
                raise ValueError(f"connection.{key} is outside 1..10000")
            values[key] = value
        if not (
            values['rtt_good_ms']
            < values['rtt_warn_ms']
            < values['rtt_bad_ms']
        ):
            raise ValueError("connection RTT threshold order is invalid")

        rtt_window_size = settings['rtt_window_size']
        if (
            isinstance(rtt_window_size, bool)
            or not isinstance(rtt_window_size, int)
            or not 1 <= rtt_window_size <= 30
        ):
            raise ValueError("connection.rtt_window_size must be 1..30")

        if not (
            values['heartbeat_min_interval_seconds']
            <= values['heartbeat_interval_seconds']
            <= values['heartbeat_max_interval_seconds']
            < values['degraded_after_seconds']
            < values['offline_after_seconds']
            < values['client_reconnect_after_seconds']
            < values['session_release_after_seconds']
        ):
            raise ValueError("connection timeout order is invalid")

        with cls._CONNECTION_CONFIG_LOCK:
            cls.HEARTBEAT_INTERVAL = values['heartbeat_interval_seconds']
            cls.HEARTBEAT_MIN_INTERVAL = values['heartbeat_min_interval_seconds']
            cls.HEARTBEAT_MAX_INTERVAL = values['heartbeat_max_interval_seconds']
            cls.CONNECTION_DEGRADED_TIMEOUT = values['degraded_after_seconds']
            cls.CONNECTION_OFFLINE_TIMEOUT = values['offline_after_seconds']
            cls.CLIENT_RECONNECT_TIMEOUT = values['client_reconnect_after_seconds']
            cls.SERVER_SESSION_TIMEOUT = values['session_release_after_seconds']
            cls.RECOVERY_ACK_COUNT = recovery_count
            cls.RTT_GOOD_MS = values['rtt_good_ms']
            cls.RTT_WARN_MS = values['rtt_warn_ms']
            cls.RTT_BAD_MS = values['rtt_bad_ms']
            cls.RTT_WINDOW_SIZE = rtt_window_size
            cls.HEARTBEAT_TIMEOUT = cls.SERVER_SESSION_TIMEOUT
            cls.CLIENT_DISCONNECT_TIMEOUT = cls.CLIENT_RECONNECT_TIMEOUT
            return cls.connection_settings()

    @classmethod
    def media_settings(cls) -> dict:
        """Return the active camera/stream policy in JSON-safe form."""
        with cls._MEDIA_CONFIG_LOCK:
            return {
                'shoot_resolution': list(cls.SHOOT_RESOLUTION),
                'shoot_jpeg_quality': cls.SHOOT_JPEG_QUALITY,
                'stream_resolution': list(cls.STREAM_RESOLUTION),
                'stream_jpeg_quality': cls.STREAM_JPEG_QUALITY,
                'stream_fps_target': cls.STREAM_FPS_TARGET,
            }

    @classmethod
    def configure_media(cls, settings: dict) -> dict:
        """Validate and atomically apply media settings received from the app."""
        if not isinstance(settings, dict):
            raise ValueError("media settings must be an object")
        required = (
            'shoot_resolution',
            'shoot_jpeg_quality',
            'stream_resolution',
            'stream_jpeg_quality',
            'stream_fps_target',
        )
        missing = [key for key in required if key not in settings]
        if missing:
            raise ValueError("missing media settings: " + ", ".join(missing))

        resolutions = {}
        for key in ('shoot_resolution', 'stream_resolution'):
            value = settings[key]
            if (
                not isinstance(value, (list, tuple))
                or len(value) != 2
                or any(
                    isinstance(item, bool) or not isinstance(item, int)
                    for item in value
                )
            ):
                raise ValueError(f"media.{key} must be [width, height]")
            width, height = value
            if not 160 <= width <= 3840 or not 120 <= height <= 2160:
                raise ValueError(f"media.{key} is outside supported bounds")
            resolutions[key] = (width, height)

        integers = {}
        for key in ('shoot_jpeg_quality', 'stream_jpeg_quality'):
            value = settings[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 20 <= value <= 95
            ):
                raise ValueError(f"media.{key} must be 20..95")
            integers[key] = value
        fps = settings['stream_fps_target']
        if (
            isinstance(fps, bool)
            or not isinstance(fps, int)
            or not 1 <= fps <= 60
        ):
            raise ValueError("media.stream_fps_target must be 1..60")

        with cls._MEDIA_CONFIG_LOCK:
            cls.SHOOT_RESOLUTION = resolutions['shoot_resolution']
            cls.STREAM_RESOLUTION = resolutions['stream_resolution']
            cls.SHOOT_JPEG_QUALITY = integers['shoot_jpeg_quality']
            cls.STREAM_JPEG_QUALITY = integers['stream_jpeg_quality']
            cls.STREAM_FPS_TARGET = fps
            return cls.media_settings()

    @staticmethod
    def classify_connection_state(elapsed_seconds: float) -> str:
        """Classify heartbeat silence without deciding whether to tear down.

        The client reconnect threshold intentionally sits inside the
        ``offline`` state.  The server can therefore retain the session slot
        until ``session-expired`` while the client starts a fresh handshake.
        """
        elapsed = max(0.0, float(elapsed_seconds))
        if elapsed >= Protocol.SERVER_SESSION_TIMEOUT:
            return Protocol.CONNECTION_STATE_SESSION_EXPIRED
        if elapsed >= Protocol.CONNECTION_OFFLINE_TIMEOUT:
            return Protocol.CONNECTION_STATE_OFFLINE
        if elapsed >= Protocol.CONNECTION_DEGRADED_TIMEOUT:
            return Protocol.CONNECTION_STATE_DEGRADED
        return Protocol.CONNECTION_STATE_HEALTHY

    @staticmethod
    def is_worsening_connection_transition(current: str, candidate: str) -> bool:
        """Return true only when a timeout moves the link to a worse state.

        A fresh heartbeat resets the silence timer before the recovery streak is
        complete. Without this guard the classifier could incorrectly move an
        offline link back to degraded and make it operational after one sample.
        """
        order = {
            Protocol.CONNECTION_STATE_HEALTHY: 0,
            Protocol.CONNECTION_STATE_DEGRADED: 1,
            Protocol.CONNECTION_STATE_OFFLINE: 2,
            Protocol.CONNECTION_STATE_SESSION_EXPIRED: 3,
        }
        return order.get(candidate, -1) > order.get(current, -1)

    @classmethod
    def recovery_sample_gap_bounds(cls):
        """Derive a conservative cadence window from the heartbeat policy."""
        minimum = max(0.05, cls.HEARTBEAT_MIN_INTERVAL * 0.5)
        maximum = min(
            cls.CONNECTION_DEGRADED_TIMEOUT * 0.9,
            max(
                cls.HEARTBEAT_INTERVAL * 2.0,
                cls.HEARTBEAT_MAX_INTERVAL * 2.0,
            ),
        )
        return minimum, max(minimum, maximum)

    @classmethod
    def next_recovery_streak(
            cls,
            count,
            last_sample_at,
            last_sequence,
            sample_at,
            sequence=None,
            rtt_seconds=None):
        """Accumulate only timely, ordered recovery samples.

        Invalid RTT samples are ignored. A valid but non-consecutive sample
        starts a new streak at one instead of being added to an old streak.
        """
        minimum_gap, maximum_gap = cls.recovery_sample_gap_bounds()
        sample_at = float(sample_at)
        if rtt_seconds is not None:
            rtt_seconds = float(rtt_seconds)
            if rtt_seconds < 0 or rtt_seconds > maximum_gap:
                return 0, None, None

        if last_sample_at is None:
            return 1, sample_at, sequence

        gap = sample_at - float(last_sample_at)
        sequence_ok = (
            sequence is None
            or last_sequence is None
            or int(sequence)
            == ((int(last_sequence) + 1) & 0xFFFFFFFFFFFFFFFF)
        )
        if minimum_gap <= gap <= maximum_gap and sequence_ok:
            return int(count) + 1, sample_at, sequence
        return 1, sample_at, sequence

    @staticmethod
    def should_client_reconnect(elapsed_seconds: float) -> bool:
        return float(elapsed_seconds) >= Protocol.CLIENT_RECONNECT_TIMEOUT

    @staticmethod
    def should_release_server_session(elapsed_seconds: float) -> bool:
        return float(elapsed_seconds) >= Protocol.SERVER_SESSION_TIMEOUT

    @staticmethod
    def is_operational_connection_state(state: str) -> bool:
        return state in (
            Protocol.CONNECTION_STATE_HEALTHY,
            Protocol.CONNECTION_STATE_DEGRADED,
        )
