# -*- coding: utf-8 -*-
"""
MBT03 Client Core V2.0 - WiFi-resilient heartbeat + single-channel stream.

Architecture:
  Control socket (DEALER): heartbeat, connect, shoot_notify, stream frames, commands
  Data socket (PUSH): shoot images only (high-throughput, non-blocking)

V2.2 changes (WiFi stability):
  1. Lazy disconnect: only after 15s total silence (was 5 miss × ~2s)
  2. Low-frequency heartbeat: 2-3s interval (was 0.2-0.8s), reduces WiFi congestion
  3. Adaptive interval: RTT-based (1s degraded → 3s excellent)
  4. Single warning log on lag, no spam
  5. Poll 500ms (was 200ms), lower CPU on Pi Zero

Kept from V2.1:
  1. Data channel for shoot images (large, shouldn't block heartbeat)
  2. Fast reconnect: on disconnect, probe same IP first (<0.5s)
  3. Exponential backoff: reduce network flood on repeated failures
  4. RTT monitoring: track connection quality with sliding window
  5. TCP keepalive + optimized ZMQ socket options
"""

import zmq
import threading
import time
import json
import os
import uuid
import struct
import numpy as np
import cv2
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtCore import pyqtSignal, QObject

from .protocol import PortMapping, Protocol
from .discovery import ServerFinder


class MBT03ClientCore(QObject):
    """
    Core client logic with single-channel stream and adaptive heartbeat.
    """
    
    # UI signals
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    connected_signal = pyqtSignal(str)
    disconnected_signal = pyqtSignal()
    port_id_changed_signal = pyqtSignal(int)
    
    # Camera signals
    shoot_sent_signal = pyqtSignal()
    shoot_image_sent_signal = pyqtSignal()
    streaming_started_signal = pyqtSignal()
    streaming_stopped_signal = pyqtSignal()
    camera_frame_signal = pyqtSignal(object)
    
    # Quality signal
    connection_quality_signal = pyqtSignal(dict)
    
    # UART signal
    uart_cmd_signal = pyqtSignal(str)
    
    def __init__(
            self,
            prior_port_id: int = None,
            config_dir: str = ".",
            camera_index: int = 0,
            camera_backend: str = None,
            parent=None):
        super().__init__(parent)
        
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, Protocol.CLIENT_CONFIG_FILE)
        
        self.prior_port_id = (
            prior_port_id if prior_port_id in PortMapping.MAP else self._load_prior_port_id()
        )
        
        self.client_name = self._get_stable_name()
        
        # ZMQ — only 2 sockets (was 3)
        self.context = None  # Created fresh each connection cycle
        self.socket = None        # Control + Stream (DEALER)
        self.data_socket = None   # Data (PUSH) — shoot images only
        self._send_lock = threading.Lock()
        self._data_send_lock = threading.Lock()
        self._stream_send_lock = threading.Lock()  # Separate lock for stream (avoid blocking heartbeat)
        
        # State
        self.running = False
        self.connected = False
        self.current_server_ip = None
        self.current_server_port = None
        self.current_server_data_port = None
        self.current_server_port_id = None
        self._last_server_ip = self._load_last_server_ip()
        self._last_port = self._load_last_port()
        self._last_system_id = self._load_last_system_id()
        
        # Q0 calibration (persistent)
        q0_data = self._load_q0()
        self.q0_value = q0_data.get('q0', [0.5, 0.5])  # (x, y) normalized
        self.q0_size = q0_data.get('size', 0)           # avg bullet hole area
        
        # RTT / adaptive heartbeat
        self._rtt_history = deque(maxlen=Protocol.RTT_WINDOW_SIZE)
        self._current_hb_interval = Protocol.HEARTBEAT_INTERVAL
        
        # Reconnection
        self._reconnect_delay = Protocol.RECONNECT_MIN_DELAY
        
        # Finder
        self.finder = None
        
        # Camera
        self._streaming = False
        self._stream_thread = None
        self.camera_index = self._load_camera_index() if camera_index is None else int(camera_index)
        self.camera_backend = self._normalize_camera_backend(
            self._load_camera_backend() if camera_backend is None else camera_backend
        )
        self._camera_backend_active = None
        self._camera_cap = None
        self._camera_lock = threading.Lock()
        self._use_fake_camera = False
        self._fake_frame_counter = 0
        self._last_shoot_time = 0
        self._shared_frame = None
        self._shoot_frame = None  # Pre-set by hardware client for timing compensation
        
        # Single-worker pool for shoot image sends (prevents thread leak)
        self._shoot_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ShootImg")
        
        self._lock = threading.Lock()
    
    @staticmethod
    def _get_stable_name() -> str:
        """Generate stable client name from hardware MAC (survives restarts).
        Falls back to UUID for PC/non-Linux platforms."""
        try:
            # Try wlan0 first (Orange Pi WiFi), then eth0
            for iface in ['wlan0', 'eth0']:
                path = f'/sys/class/net/{iface}/address'
                if os.path.exists(path):
                    with open(path) as f:
                        mac = f.read().strip().replace(':', '')
                    return f"Client-{mac[-6:]}"
        except Exception:
            pass
        return f"Client-{uuid.uuid4().hex[:6]}"
    
    # ======================== CONFIG ========================
    
    def _log(self, msg):
        full_msg = f"[Client {self.client_name}] {msg}"
        print(full_msg)
        try:
            self.log_signal.emit(full_msg)
        except RuntimeError:
            pass
    
    def _load_prior_port_id(self) -> int:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    port_id = json.load(f).get('prior_port_id')
                    port_id = int(port_id)
                    if port_id in PortMapping.MAP:
                        return port_id
        except Exception:
            pass
        return 1

    def _load_camera_index(self) -> int:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return int(json.load(f).get('camera_index', 0))
        except Exception:
            pass
        return 0

    def _load_camera_backend(self) -> str:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f).get('camera_backend', 'auto')
        except Exception:
            pass
        return 'auto'
    
    def _load_last_server_ip(self) -> str:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f).get('last_server_ip', None)
        except Exception:
            pass
        return None
    
    def _load_last_port(self) -> int:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    p = json.load(f).get('last_port')
                    return int(p) if p else None
        except Exception:
            pass
        return None
    
    def _load_last_system_id(self) -> str:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    sid = json.load(f).get('last_system_id')
                    if sid:
                        self._log(f"Last system_id: {sid[:8]}")
                    return sid
        except Exception:
            pass
        return None
    
    def _load_q0(self) -> dict:
        """Load Q0 calibration from config file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    q0 = data.get('q0_value')
                    size = data.get('q0_size', 0)
                    if q0 and len(q0) == 2:
                        self._log(f"Loaded Q0=({q0[0]:.4f}, {q0[1]:.4f}), size={size}")
                        return {'q0': q0, 'size': size}
        except Exception:
            pass
        return {'q0': [0.5, 0.5], 'size': 0}
    
    def _save_config(self):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            config = {
                'prior_port_id': self.prior_port_id,
                'camera_index': self.camera_index,
                'camera_backend': self.camera_backend,
                'last_server_ip': self._last_server_ip,
                'last_port': self._last_port,
                'last_system_id': self._last_system_id,
                'q0_value': self.q0_value,
                'q0_size': self.q0_size,
            }
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r') as f:
                        if json.load(f) == config:
                            return
                except Exception:
                    pass
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            self._log(f"Failed to save config: {e}")
    
    # ======================== LIFECYCLE ========================
    
    def start(self):
        self.running = True
        threading.Thread(target=self._main_loop, daemon=True,
                         name="ClientMainLoop").start()
        self._log(f"Client started (prior_port_id={self.prior_port_id})")
    
    def stop(self):
        self.running = False
        self.connected = False
        
        if self.finder:
            self.finder.cancel()
            self.finder.stop()
            self.finder = None
        
        # Shutdown shoot image pool
        try:
            self._shoot_pool.shutdown(wait=False)
        except Exception:
            pass
        
        for sock in [self.socket, self.data_socket]:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        
        if self.context:
            try:
                self.context.term()
            except Exception:
                pass
            self.context = None

        with self._camera_lock:
            if self._camera_cap is not None:
                try:
                    self._camera_cap.release()
                except Exception:
                    pass
                self._camera_cap = None
        
        self._log("Client stopped.")
        self.status_signal.emit("Đã dừng")
    
    # ======================== MAIN LOOP ========================
    
    def _main_loop(self):
        """
        Connection strategy (auto port assignment):
        1. Quick reconnect to last server+port (if just disconnected)
        2. Try ALL ports on last known server IP
        3. Zeroconf discovery for any available server
        4. Backoff and retry
        
        No fixed port preference. After disconnect, tries same port first.
        If rejected, automatically moves to the next available port.
        """
        is_first_boot = True
        while self.running:
            try:
                # Fresh ZMQ context each connection cycle (prevents zombie sockets)
                if self.context is not None:
                    try:
                        self.context.term()
                    except Exception:
                        pass
                self.context = zmq.Context()
                
                self._main_loop_step(is_first_boot)
            except Exception as e:
                self._log(f"Main loop step error: {e}")
                time.sleep(1.0)
            is_first_boot = False

    def _main_loop_step(self, is_first_boot):
        self.connected = False
        self.status_signal.emit("Đang tìm server...")
        self.disconnected_signal.emit()
            
        # === Phase 1: Quick reconnect to last known server+port ===
        # Skip on first boot to ensure we scan and prioritize smallest port_id
        if not is_first_boot and self._last_server_ip and self._last_port:
            self._log(f"Quick reconnect → {self._last_server_ip}:{self._last_port} (P{self.prior_port_id})")
            self.status_signal.emit(f"Kết nối nhanh P{self.prior_port_id}...")
            
            if self._tcp_probe(self._last_server_ip, self._last_port):
                rc = self._connect(self._last_server_ip, self._last_port, self.prior_port_id)
                if rc == 'accepted':
                    self._on_connect_success(
                        self._last_server_ip, self._last_port,
                        self.prior_port_id, self._last_system_id)
                    self._heartbeat_loop()
                    self._cleanup_connection()
                    return
                # rejected/timeout → fall through to Zeroconf
            
        if not self.running:
            return
            
        # === Phase 2: Zeroconf discovery (find ALL servers) ===
        # With dynamic ports, Zeroconf is the ONLY way to find servers
        self._log("Zeroconf discovery...")
        self.status_signal.emit("Tìm server...")
        
        servers = []
        finder = None
        try:
            finder = ServerFinder(log_func=self._log)
            finder.start()
            self.finder = finder
            
            # Wait shorter on first boot — Hub broadcasts all ports at once
            gather_t = 1.5 if is_first_boot else 0.3
            servers = finder.find_all_servers(
                prefer_system_id=self._last_system_id,
                timeout=5.0,
                gather_time=gather_t
            )
        except OSError as e:
            self._log(f"Zeroconf network error (WiFi down?): {e}")
            time.sleep(2.0)  # Back off when network is unreachable
        except Exception as e:
            self._log(f"Zeroconf error: {e}")
        finally:
            self.finder = None
            if finder:
                try:
                    finder.stop()
                except Exception:
                    pass
                del finder  # Help GC release Zeroconf resources
            
        if not self.running:
            return
            
        connected_successfully = False
        if servers:
            # Prioritize configured port_id so client pairs with correct target (e.g. board 3 to bệ 3)
            servers.sort(key=lambda s: 0 if s[2] == self.prior_port_id else 1)
            for s in servers:
                ip, port, port_id, system_id = s
                self._log(f"Trying discovered server: {ip}:{port} (P{port_id}, sys={system_id[:8]})")
                
                rc = self._connect(ip, port, port_id)
                if rc == 'accepted':
                    self._on_connect_success(ip, port, port_id, system_id)
                    self._heartbeat_loop()
                    self._cleanup_connection()
                    connected_successfully = True
                    break
                elif rc == 'rejected':
                    self._log(f"P{port_id}: occupied, will try next if available")
        
        if connected_successfully:
            return
        
        # === Phase 3: No server found → backoff ===
        if self.running:
            self._log(f"No server. Retry in {self._reconnect_delay:.1f}s...")
            self.status_signal.emit("Không tìm thấy server...")
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 1.5, Protocol.RECONNECT_MAX_DELAY)
    
    # ======================== TCP PROBE ========================
    
    def _tcp_probe(self, ip: str, port: int) -> bool:
        """Quick TCP check if a port is reachable (~10ms on LAN)."""
        import socket as sock
        try:
            s = sock.socket(sock.AF_INET, sock.SOCK_STREAM)
            s.settimeout(Protocol.DIRECT_PROBE_TIMEOUT)
            result = s.connect_ex((ip, port)) == 0
            s.close()
            return result
        except Exception:
            return False
    
    def _on_connect_success(self, ip: str, port: int, port_id: int, 
                            system_id: str = None):
        """Update state after successful connection."""
        self._last_server_ip = ip
        self._last_port = port  # Save actual port for quick reconnect
        self._last_system_id = system_id
        if port_id != self.prior_port_id:
            self._log(f"Port ID: {self.prior_port_id} → {port_id}")
            self.port_id_changed_signal.emit(port_id)
        self.prior_port_id = port_id
        self._save_config()
        self._reconnect_delay = Protocol.RECONNECT_MIN_DELAY
        if system_id:
            self._log(f"Connected to system {system_id[:8]}")
    
    # ======================== CONNECT ========================
    
    def _make_control_socket(self):
        """Create optimized DEALER socket."""
        s = self.context.socket(zmq.DEALER)
        s.setsockopt(zmq.LINGER, 0)
        identity = f"{self.client_name}-{uuid.uuid4().hex[:4]}"
        s.setsockopt(zmq.IDENTITY, identity.encode('utf-8'))
        # TCP keepalive (detect dead connections at OS level)
        s.setsockopt(zmq.TCP_KEEPALIVE, 1)
        s.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 3)
        s.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)
        s.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)
        # Buffer limits
        s.setsockopt(zmq.SNDHWM, 10)
        s.setsockopt(zmq.SNDTIMEO, 500)
        # Optional optimizations (may not be available in older pyzmq)
        # NOTE: Do NOT set RECONNECT_IVL=-1, it disables ZMQ internal reconnect
        # and causes zombie sockets when TCP drops silently
        for opt_name, val in [('TCP_NODELAY', 1), ('IMMEDIATE', 1)]:
            opt = getattr(zmq, opt_name, None)
            if opt is not None:
                try:
                    s.setsockopt(opt, val)
                except zmq.ZMQError:
                    pass
        return s
    
    def _make_data_socket(self):
        """Create optimized PUSH socket for shoot images."""
        s = self.context.socket(zmq.PUSH)
        s.setsockopt(zmq.LINGER, 0)
        s.setsockopt(zmq.SNDHWM, 3)
        s.setsockopt(zmq.SNDTIMEO, 200)
        s.setsockopt(zmq.TCP_KEEPALIVE, 1)
        s.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 5)
        s.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)
        # Optional optimizations
        for opt_name, val in [('TCP_NODELAY', 1), ('IMMEDIATE', 1)]:
            opt = getattr(zmq, opt_name, None)
            if opt is not None:
                try:
                    s.setsockopt(opt, val)
                except zmq.ZMQError:
                    pass
        return s
    
    def _connect(self, ip: str, port: int, port_id: int) -> str:
        """Connect control + data channels.
        Returns: 'accepted', 'rejected', or 'timeout'.
        """
        self.status_signal.emit(f"Kết nối P{port_id} ({ip})...")
        
        # Close existing sockets
        for sock in [self.socket, self.data_socket]:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        self.data_socket = None
        
        self.socket = self._make_control_socket()
        
        try:
            self.socket.connect(f"tcp://{ip}:{port}")
        except Exception as e:
            self._log(f"TCP connect failed: {e}")
            return 'timeout'
        
        # Handshake — include local IP for server-side logging
        import socket as _sock
        try:
            _s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
            _s.connect((ip, 80))
            local_ip = _s.getsockname()[0]
            _s.close()
        except Exception:
            local_ip = 'unknown'
        
        payload = Protocol.encode_payload({
            'client_name': self.client_name,
            'prior_port_id': self.prior_port_id,
            'client_ip': local_ip,
            'q0_value': self.q0_value,
            'q0_size': self.q0_size,
        })
        
        try:
            self.socket.send_multipart([Protocol.MSG_CONNECT_REQUEST, payload])
        except Exception as e:
            self._log(f"Connect request send failed: {e}")
            return 'timeout'
        
        # Wait for ACK/REJECT (1s timeout for fast port scanning)
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        
        if poller.poll(1000):
            try:
                frames = self.socket.recv_multipart()
                if frames[0] == Protocol.MSG_CONNECT_ACK:
                    server_info = Protocol.decode_payload(frames[1]) if len(frames) > 1 else {}
                    data_port = server_info.get('data_port',
                                                PortMapping.get_data_port(port_id))
                    
                    # Connect data channel (for shoot images)
                    self.data_socket = self._make_data_socket()
                    try:
                        self.data_socket.connect(f"tcp://{ip}:{data_port}")
                    except Exception as e:
                        self._log(f"Data channel failed: {e}, will use control")
                    
                    self.connected = True
                    self.current_server_ip = ip
                    self.current_server_port = port
                    self.current_server_data_port = data_port
                    self.current_server_port_id = port_id
                    self._rtt_history.clear()
                    self._current_hb_interval = Protocol.HEARTBEAT_INTERVAL
                    
                    self._log(f"✅ Connected P{port_id} at {ip}:{port}+{data_port}")
                    self.connected_signal.emit(f"Server P{port_id} ({ip})")
                    self.status_signal.emit(f"Đã kết nối: P{port_id}")
                    return 'accepted'
                    
                elif frames[0] == Protocol.MSG_CONNECT_REJECT:
                    reason = frames[1].decode() if len(frames) > 1 else "?"
                    self._log(f"Rejected by P{port_id}: {reason}")
                    # Close socket immediately to prevent buffered messages
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                    self.socket = None
                    return 'rejected'
            except Exception as e:
                self._log(f"ACK parse error: {e}")
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
                return 'timeout'
        else:
            self._log(f"Timeout P{port_id} (no response)")
            # CRITICAL: Close socket immediately to prevent ghost connections
            # Without this, the buffered connect request may reach the server
            # after the client has moved on to try another port
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
            return 'timeout'
    
    # ======================== ADAPTIVE HEARTBEAT ========================
    
    def _calc_hb_interval(self) -> float:
        """Dynamic heartbeat interval based on RTT quality."""
        if len(self._rtt_history) < 3:
            return Protocol.HEARTBEAT_INTERVAL
        
        avg_rtt = sum(self._rtt_history) / len(self._rtt_history)
        
        if avg_rtt < Protocol.RTT_GOOD_MS:
            return Protocol.HEARTBEAT_MAX_INTERVAL
        elif avg_rtt < Protocol.RTT_WARN_MS:
            return Protocol.HEARTBEAT_INTERVAL
        else:
            return Protocol.HEARTBEAT_MIN_INTERVAL
    
    def _heartbeat_loop(self):
        """Adaptive heartbeat loop with RTT monitoring."""
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        
        last_hb_sent = time.monotonic()
        last_hb_received = time.monotonic()
        _warned_lag = False
        
        while self.running and self.connected:
            try:
                now = time.monotonic()
                
                # Poll incoming (300ms — responsive on all platforms)
                socks = dict(poller.poll(300))
                if self.socket in socks:
                    frames = self.socket.recv_multipart()
                    if not frames:
                        continue
                    msg_type = frames[0]
                    
                    if msg_type == Protocol.MSG_HEARTBEAT_ACK:
                        last_hb_received = now
                        _warned_lag = False
                        # RTT from echoed timestamp
                        if len(frames) > 1 and len(frames[1]) >= 8:
                            try:
                                sent_ts = struct.unpack('!d', frames[1][:8])[0]
                                rtt = (time.time() - sent_ts) * 1000
                                self._rtt_history.append(rtt)
                                self._current_hb_interval = self._calc_hb_interval()
                            except Exception:
                                pass
                    
                    elif msg_type == Protocol.MSG_DISCONNECT:
                        self._log("Server disconnect")
                        self._stop_streaming()
                        self.connected = False
                        return
                    
                    elif msg_type == Protocol.MSG_STREAM_START:
                        self._start_streaming()
                    
                    elif msg_type == Protocol.MSG_STREAM_STOP:
                        self._stop_streaming()
                    
                    elif msg_type == Protocol.MSG_SET_Q0:
                        # Server sent Q0 calibration data
                        if len(frames) > 1:
                            try:
                                q0_data = Protocol.decode_payload(frames[1])
                                self.q0_value = q0_data.get('q0', self.q0_value)
                                self.q0_size = q0_data.get('size', self.q0_size)
                                self._save_config()
                                self._log(
                                    f"\u2705 Q0 received & saved: "
                                    f"({self.q0_value[0]:.4f}, {self.q0_value[1]:.4f}), "
                                    f"size={self.q0_size}")
                            except Exception as e:
                                self._log(f"Q0 parse error: {e}")
                        last_hb_received = now
                    
                    elif msg_type == Protocol.MSG_UART_CMD:
                        if len(frames) > 1:
                            try:
                                cmd_str = frames[1].decode('utf-8')
                                self.uart_cmd_signal.emit(cmd_str)
                                self._log(f"Received UART command: {repr(cmd_str)}")
                            except Exception as e:
                                self._log(f"UART command decode error: {e}")
                        last_hb_received = now
                    
                    elif msg_type == Protocol.MSG_DATA:
                        if len(frames) > 1:
                            try:
                                data = Protocol.decode_payload(frames[1])
                                self._log(f"Data: {data}")
                            except Exception:
                                pass
                        last_hb_received = now
                
                # Send heartbeat with timestamp + client-measured RTT
                interval = self._current_hb_interval
                if now - last_hb_sent >= interval:
                    try:
                        ts_bytes = struct.pack('!d', time.time())
                        # Include client-measured RTT so server can display accurate ping
                        # (server can't measure RTT accurately due to clock difference)
                        client_rtt = self._rtt_history[-1] if self._rtt_history else 0
                        rtt_bytes = struct.pack('!d', client_rtt)
                        with self._send_lock:
                            self.socket.send_multipart([
                                Protocol.MSG_HEARTBEAT, ts_bytes + rtt_bytes
                            ])
                        last_hb_sent = now
                    except Exception as e:
                        self._log(f"HB send error: {e}")
                    
                    # Check silence duration - tolerate WiFi jitter
                    elapsed = now - last_hb_received
                    if elapsed > Protocol.CLIENT_DISCONNECT_TIMEOUT:
                        self._log(f"Connection lost (no reply for {elapsed:.1f}s)")
                        self._stop_streaming()
                        self.connected = False
                        return
                    # Log warning once when lag starts
                    elif elapsed > Protocol.HEARTBEAT_MAX_INTERVAL * 2 and not _warned_lag:
                        _warned_lag = True
                        self._log(f"WiFi lag: no reply for {elapsed:.1f}s")
                
            except zmq.ZMQError as e:
                self._log(f"ZMQ error: {e}")
                self._stop_streaming()
                self.connected = False
                return
            except Exception as e:
                self._log(f"HB loop error: {e}")
                self._stop_streaming()
                self.connected = False
                return
    
    def _cleanup_connection(self):
        # Stop streaming without blocking (don't join thread from heartbeat loop)
        self._streaming = False
        self.connected = False
        self.current_server_ip = None
        self.current_server_port = None
        self.current_server_data_port = None
        self.current_server_port_id = None
        
        for sock_name in ['socket', 'data_socket']:
            sock = getattr(self, sock_name, None)
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
                setattr(self, sock_name, None)
        
        # Context will be terminated and recreated at top of _main_loop
        # This ensures clean ZMQ state for next connection attempt
        
        self.disconnected_signal.emit()
        self.status_signal.emit("Đã ngắt kết nối")
    
    # ======================== SHOOT ========================
    
    def shoot(self) -> bool:
        """Two-phase shoot: instant notify (control) + image (data channel)."""
        if not self.connected or not self.socket:
            self._log("Cannot shoot: not connected")
            return False
        
        now = time.time()
        # 30 shots/s max (~33ms debounce), matched with server-side
        if now - self._last_shoot_time < 0.033:  # ~33ms debounce (30/s)
            return False
        self._last_shoot_time = now
        
        # Phase 1: Instant notification via control channel
        try:
            with self._send_lock:
                self.socket.send_multipart([
                    Protocol.MSG_SHOOT_NOTIFY,
                    struct.pack('!d', time.time())
                ])
            self.shoot_sent_signal.emit()
            self._log("Shoot notification sent")
        except Exception as e:
            self._log(f"Shoot notify failed: {e}")
            return False
        
        # Phase 2: Image via data channel (async, non-blocking)
        def _send_image():
            start_t = time.time()
            try:
                w, h = Protocol.SHOOT_RESOLUTION
                # Use pre-set shoot frame (timing-compensated) if available
                if self._shoot_frame is not None:
                    frame = self._shoot_frame
                    self._shoot_frame = None
                    if frame.shape[1] != w or frame.shape[0] != h:
                        frame = cv2.resize(frame, (w, h))
                else:
                    frame = self._capture_frame(w, h)
                
                encode_t = time.time()
                jpeg_data = self._encode_frame_jpeg(frame, Protocol.SHOOT_JPEG_QUALITY)
                
                # Build Q0 metadata to send with image
                q0_meta = Protocol.encode_payload({
                    'q0': self.q0_value,
                    'q0_size': self.q0_size,
                    'ts': time.time(),
                })
                
                # Send via data channel (PUSH): [MSG, JPEG, Q0_META]
                target = self.data_socket if self.data_socket else self.socket
                lock = self._data_send_lock if self.data_socket else self._send_lock
                
                if not self.connected:
                    return  # Abort if disconnected while encoding
                
                with lock:
                    target.send_multipart([
                        Protocol.MSG_SHOOT_IMAGE, jpeg_data, q0_meta
                    ])
                
                total_ms = (time.time() - start_t) * 1000
                encode_ms = (time.time() - encode_t) * 1000
                self.shoot_image_sent_signal.emit()
                self._log(f"Shoot image sent: {len(jpeg_data)//1024}KB, Total: {total_ms:.0f}ms (Enc: {encode_ms:.0f}ms)")
            except Exception as e:
                self._log(f"Shoot image failed: {e}")
        
        try:
            self._shoot_pool.submit(_send_image)
        except RuntimeError:
            # Pool was shut down, recreate it
            self._shoot_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ShootImg")
            self._shoot_pool.submit(_send_image)
        return True
        
    def send_data(self, data_dict: dict) -> bool:
        """Send custom JSON data to server over control channel."""
        if not self.connected or not self.socket:
            return False
        try:
            payload = Protocol.encode_payload(data_dict)
            with self._send_lock:
                self.socket.send_multipart([ Protocol.MSG_DATA, payload ])
            return True
        except Exception as e:
            self._log(f"Send data failed: {e}")
            return False
    
    # ======================== STREAMING ========================
    
    def _start_streaming(self):
        if self._streaming:
            return
        self._streaming = True
        self._stream_thread = threading.Thread(
            target=self._stream_loop, daemon=True, name="CamStream")
        self._stream_thread.start()
        self.streaming_started_signal.emit()
        self._log("Streaming started")
    
    def _stop_streaming(self):
        if not self._streaming:
            return
        self._streaming = False
        if self._stream_thread:
            self._stream_thread.join(timeout=2.0)
            self._stream_thread = None
        self.streaming_stopped_signal.emit()
        self._log("Streaming stopped")
    
    def _stream_loop(self):
        """Stream via main DEALER socket (like V1 Backup).
        
        Simple approach: capture → encode → send via main socket.
        No separate PUB socket, no drain loop, no extra locks.
        """
        w, h = Protocol.STREAM_RESOLUTION
        sleep_interval = 1.0 / Protocol.STREAM_FPS_TARGET
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), Protocol.STREAM_JPEG_QUALITY]
        
        self._log(f"Stream: {w}x{h} @ {Protocol.STREAM_FPS_TARGET}fps, quality={Protocol.STREAM_JPEG_QUALITY}")
        
        frame_count = 0
        fps_timer = time.time()
        
        try:
            while self._streaming and self.connected and self.running:
                try:
                    # Capture
                    frame = self._capture_frame(w, h)
                    
                    # Encode
                    _, jpeg = cv2.imencode('.jpg', frame, encode_params)
                    jpeg_bytes = jpeg.tobytes()
                    
                    # Send via main socket — use separate lock to avoid blocking heartbeat
                    with self._stream_send_lock:
                        self.socket.send_multipart([
                            Protocol.MSG_STREAM_FRAME, jpeg_bytes
                        ], zmq.NOBLOCK)
                    
                    frame_count += 1
                    now = time.time()
                    if now - fps_timer >= 5.0:
                        fps = frame_count / (now - fps_timer)
                        self._log(f"Stream: {fps:.1f}fps, ~{len(jpeg_bytes)}B/frame")
                        frame_count = 0
                        fps_timer = now
                    
                except zmq.Again:
                    pass  # Buffer full, skip frame
                except Exception as e:
                    self._log(f"Stream error: {e}")
                    break
                
                # Simple sleep (like backup - critical for ARM, no busy-wait)
                time.sleep(sleep_interval)
        finally:
            pass
        
        self._streaming = False
    
    # ======================== CAMERA ========================

    @staticmethod
    def _normalize_camera_backend(camera_backend: str) -> str:
        backend = str(camera_backend or 'auto').strip().lower()
        if backend in ('directshow', 'dshow', 'ds'):
            return 'dshow'
        if backend in ('mediafoundation', 'msmf', 'mf'):
            return 'msmf'
        if backend in ('default', 'opencv'):
            return 'default'
        return 'auto'

    def _camera_backend_candidates(self):
        default = [('default', None)]
        if os.name != 'nt':
            return default

        backends = [
            ('dshow', cv2.CAP_DSHOW),
            ('msmf', cv2.CAP_MSMF),
            ('default', None),
        ]
        if self.camera_backend == 'auto':
            return backends
        for name, api in backends:
            if name == self.camera_backend:
                return [(name, api)]
        return backends

    def set_camera_backend(self, camera_backend: str):
        camera_backend = self._normalize_camera_backend(camera_backend)
        with self._camera_lock:
            if camera_backend == self.camera_backend and not self._use_fake_camera:
                return
            self.camera_backend = camera_backend
            if self._camera_cap is not None:
                try:
                    self._camera_cap.release()
                except Exception:
                    pass
                self._camera_cap = None
            self._camera_backend_active = None
            self._use_fake_camera = False
        self._save_config()
        self._log(f"Camera backend set to {self.camera_backend}")

    def set_camera_index(self, camera_index: int):
        camera_index = max(0, int(camera_index))
        with self._camera_lock:
            if camera_index == self.camera_index and not self._use_fake_camera:
                return
            self.camera_index = camera_index
            if self._camera_cap is not None:
                try:
                    self._camera_cap.release()
                except Exception:
                    pass
                self._camera_cap = None
            self._camera_backend_active = None
            self._use_fake_camera = False
        self._save_config()
        self._log(f"Camera index set to {self.camera_index}")

    def _open_camera(self, width: int, height: int):
        for backend_name, backend_api in self._camera_backend_candidates():
            cap = None
            try:
                if backend_api is None:
                    cap = cv2.VideoCapture(self.camera_index)
                else:
                    cap = cv2.VideoCapture(self.camera_index, backend_api)

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not cap.isOpened():
                    cap.release()
                    continue

                first_frame = None
                for _ in range(8):
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        first_frame = frame
                        break
                    time.sleep(0.03)

                if first_frame is None:
                    cap.release()
                    continue

                self._camera_backend_active = backend_name
                self._log(f"Camera opened: index={self.camera_index}, backend={backend_name}")
                return cap, first_frame
            except Exception as e:
                self._log(f"Camera open failed: index={self.camera_index}, backend={backend_name}, error={e}")
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

        self._log(
            f"Camera unavailable: index={self.camera_index}, "
            f"backend={self.camera_backend}"
        )
        return None, None
    
    def _capture_frame(self, width: int, height: int) -> np.ndarray:
        if self._shared_frame is not None:
            frame = self._shared_frame
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))
            return frame
        
        with self._camera_lock:
            if self._use_fake_camera:
                return self._generate_fake_frame(width, height)
            
            if self._camera_cap is None or not self._camera_cap.isOpened():
                self._camera_cap, first_frame = self._open_camera(width, height)
                if self._camera_cap is None:
                    self._use_fake_camera = True
                    return self._generate_fake_frame(width, height)
                return cv2.resize(first_frame, (width, height))
            
            if not self._camera_cap.isOpened():
                self._use_fake_camera = True
                return self._generate_fake_frame(width, height)

            ret, frame = self._camera_cap.read()

        if not ret:
            return self._generate_fake_frame(width, height)
        return cv2.resize(frame, (width, height))
    
    def _encode_frame_jpeg(self, frame: np.ndarray, quality: int) -> bytes:
        # Optimization: use JPEG_OPTIMIZE=1 for slightly smaller files with same quality
        # and ensure progressive is disabled for faster encoding/decoding on ARM
        params = [
            int(cv2.IMWRITE_JPEG_QUALITY), quality,
            int(cv2.IMWRITE_JPEG_OPTIMIZE), 1
        ]
        _, jpeg = cv2.imencode('.jpg', frame, params)
        return jpeg.tobytes()
    
    def _generate_fake_frame(self, width: int, height: int) -> np.ndarray:
        """Professional fake frame when camera unavailable.
        Caches result briefly; refreshes timestamp often enough for latency checks."""
        self._fake_frame_counter += 1
        
        # Keep fake frames cheap for streaming, but refresh the millisecond timestamp.
        now = time.time()
        cache_key = (width, height)
        if (hasattr(self, '_fake_cache_key') and self._fake_cache_key == cache_key
                and hasattr(self, '_fake_cache_time')
                and now - self._fake_cache_time < 0.04
                and hasattr(self, '_fake_cache_connected')
                and self._fake_cache_connected == self.connected
                and hasattr(self, '_fake_cache_img')):
            return self._fake_cache_img
        
        W, H = width, height
        img = np.zeros((H, W, 3), dtype=np.uint8)
        
        for y in range(H):
            ratio = y / H
            img[y, :] = (int(45 - 25*ratio), int(42 - 22*ratio), int(48 - 28*ratio))
        
        for x in range(0, W, 40):
            cv2.line(img, (x, 0), (x, H), (55, 52, 58), 1)
        for y in range(0, H, 40):
            cv2.line(img, (0, y), (W, y), (55, 52, 58), 1)
        
        t = time.time()
        pulse = (np.sin(t * 3.0) + 1.0) / 2.0
        cx, cy = W // 2, H // 2 - 30
        
        overlay = img.copy()
        cv2.circle(overlay, (cx, cy), int(68 + 10*pulse), (200, 120, 60), -1)
        cv2.addWeighted(overlay, 0.15 + 0.1*pulse, img, 0.85 - 0.1*pulse, 0, img)
        
        bw, bh = 80, 56
        cv2.rectangle(img, (cx-bw//2, cy-bh//2), (cx+bw//2, cy+bh//2),
                      (160, 160, 170), 3, cv2.LINE_AA)
        cv2.circle(img, (cx, cy), 18, (160, 160, 170), 2, cv2.LINE_AA)
        cv2.circle(img, (cx, cy), 8, (120, 120, 130), -1, cv2.LINE_AA)
        cv2.line(img, (cx-36, cy+30), (cx+36, cy-30), (80, 80, 220), 3, cv2.LINE_AA)
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, _), _ = cv2.getTextSize("NO CAMERA", font, 1.2, 3)
        tx, ty = cx - tw//2, cy + bh//2 + 45
        cv2.putText(img, "NO CAMERA", (tx, ty), font, 1.2, (180, 180, 190), 3, cv2.LINE_AA)
        
        ov2 = img.copy()
        cv2.rectangle(ov2, (0, 0), (W, 56), (0, 0, 0), -1)
        cv2.addWeighted(ov2, 0.5, img, 0.5, 0, img)
        cv2.putText(img, "MBT03", (12, 38), font, 1.0, (100, 180, 255), 2, cv2.LINE_AA)
        cv2.putText(img, "WIRELESS", (125, 38), font, 0.7, (140, 140, 150), 2, cv2.LINE_AA)
        
        ms = int((t - int(t)) * 1000)
        tt = time.strftime("%H:%M:%S", time.localtime(t)) + f".{ms:03d}"
        time_scale = 0.58 if W < 500 else 0.8
        (ttw, _), _ = cv2.getTextSize(tt, font, time_scale, 2)
        cv2.putText(img, tt, (W-ttw-12, 38), font, time_scale, (180, 220, 255), 2, cv2.LINE_AA)
        
        ov3 = img.copy()
        cv2.rectangle(ov3, (0, H-70), (W, H), (0, 0, 0), -1)
        cv2.addWeighted(ov3, 0.55, img, 0.45, 0, img)
        
        info = f"{self.client_name}  |  Port {self.prior_port_id}"
        cv2.putText(img, info, (12, H-28), font, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
        
        cv2.line(img, (0, 56), (W, 56), (180, 100, 40), 2, cv2.LINE_AA)
        cv2.line(img, (0, H-70), (W, H-70), (180, 100, 40), 2, cv2.LINE_AA)
        
        # Cache the rendered frame
        self._fake_cache_key = cache_key
        self._fake_cache_time = now
        self._fake_cache_connected = self.connected
        self._fake_cache_img = img
        
        return img
    
    # ======================== DATA ========================
    
    def send_data(self, data: dict) -> bool:
        if not self.connected or not self.socket:
            return False
        try:
            with self._send_lock:
                self.socket.send_multipart([
                    Protocol.MSG_DATA, Protocol.encode_payload(data)
                ])
            return True
        except Exception as e:
            self._log(f"Send error: {e}")
            return False
    
    @property
    def is_streaming(self):
        return self._streaming
    
    @property
    def is_connected(self):
        return self.connected
    
    @property
    def server_info(self):
        if not self.connected:
            return None
        return {
            'ip': self.current_server_ip,
            'port': self.current_server_port,
            'data_port': self.current_server_data_port,
            'port_id': self.current_server_port_id,
        }
    
    @property
    def connection_quality(self):
        if not self._rtt_history:
            return None
        avg = sum(self._rtt_history) / len(self._rtt_history)
        return {
            'rtt_ms': round(avg, 1),
            'hb_interval': round(self._current_hb_interval, 2),
            'samples': len(self._rtt_history),
        }
