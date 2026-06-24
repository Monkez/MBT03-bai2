# -*- coding: utf-8 -*-
"""
Protocol definitions for MBT03 Server-Client system.
V2: Dual-channel architecture + adaptive heartbeat + RTT monitoring.
"""

import json


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
    
    
    # === Data channel messages (PUSH-PULL) ===
    MSG_SHOOT_IMAGE = b'SHOOT_IMG'       # Full image (data channel)
    MSG_STREAM_FRAME = b'STREAM_FRM'     # Stream frame (data channel)
    
    # === Heartbeat (WiFi-resilient, tuned for responsiveness) ===
    HEARTBEAT_INTERVAL = 1.5             # Send HB every 1.5s (fast detection)
    HEARTBEAT_TIMEOUT = 10.0             # Server: 10s silence → disconnect (was 15s)
    CLIENT_DISCONNECT_TIMEOUT = 10.0     # Client: 10s no reply → disconnect (was 15s)
    
    # === Adaptive Heartbeat ===
    HEARTBEAT_MIN_INTERVAL = 0.8         # Fast heartbeat (degraded network)
    HEARTBEAT_MAX_INTERVAL = 2.0         # Don't slow down too much even on good network
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
    DIRECT_PROBE_TIMEOUT = 0.2            # Faster per-port probe (was 0.3s)
    
    # Config
    CLIENT_CONFIG_FILE = "client_port_config.json"
    
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
