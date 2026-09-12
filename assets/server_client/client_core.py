# -*- coding: utf-8 -*-
"""
MBT03 Client Core V2.0 - WiFi-resilient heartbeat + isolated video stream.

Architecture:
  Control socket (DEALER): heartbeat, connect, shoot_notify, commands
  Stream socket (PUSH): latest-only live video frames
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

import ipaddress
import json
import os
import queue
import socket
import struct
import subprocess
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np
import zmq
from PyQt5.QtCore import pyqtSignal, QObject

from .protocol import PortMapping, Protocol
from .discovery import ServerFinder


class MBT03ClientCore(QObject):
    """
    Core client logic with isolated stream transport and adaptive heartbeat.
    """

    SUBNET_SCAN_PREFIX = 24
    SUBNET_SCAN_WORKERS = 48
    SUBNET_SCAN_PROBE_TIMEOUT = 0.15
    SUBNET_SCAN_INTERVAL = 15.0
    
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
    wifi_config_request_signal = pyqtSignal(dict)
    wifi_config_commit_signal = pyqtSignal(dict)
    wifi_config_rollback_signal = pyqtSignal(dict)
    session_ready_signal = pyqtSignal()
    
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
        
        # ZMQ — independent control, live-stream and shoot-image channels.
        self.context = None  # Created fresh each connection cycle
        self.socket = None        # Control (DEALER)
        self.stream_socket = None # Live video (PUSH, latest-only)
        self.data_socket = None   # Data (PUSH) — shoot images only
        self._data_send_lock = threading.Lock()
        self._stream_send_lock = threading.Lock()
        self._priority_control_send_queue = queue.Queue(maxsize=32)
        self._control_send_queue = queue.Queue(maxsize=128)
        # A ZeroMQ NOBLOCK send may temporarily report EAGAIN even though the
        # connection is still usable.  Keep the dequeued item here and retry
        # it on the next owner-loop pass instead of silently dropping it.
        self._deferred_priority_control_send = None
        self._deferred_control_send = None
        
        # State
        self.running = False
        self.connected = False
        self.current_server_ip = None
        self.current_server_port = None
        self.current_server_data_port = None
        self.current_server_stream_port = None
        self.current_server_port_id = None
        self._last_server_ip = self._load_last_server_ip()
        self._last_port = self._load_last_port()
        self._last_system_id = self._load_last_system_id()
        self._last_subnet_scan_at = 0.0
        
        # Q0 calibration (persistent)
        q0_data = self._load_q0()
        self.q0_value = q0_data.get('q0', [0.5, 0.5])  # (x, y) normalized
        self.q0_size = q0_data.get('size', 0)           # avg bullet hole area
        
        # RTT / adaptive heartbeat
        self._rtt_history = deque(maxlen=Protocol.RTT_WINDOW_SIZE)
        self._current_hb_interval = Protocol.HEARTBEAT_INTERVAL
        self._battery_percent = self._load_battery_percent()
        self._connection_state = Protocol.CONNECTION_STATE_HEALTHY
        self._recovery_ack_count = 0
        self._last_recovery_sample_at = None
        self._last_recovery_sequence = None
        self._heartbeat_sequence = 0
        self._last_acked_heartbeat_sequence = -1
        self._last_heartbeat_ack = 0.0
        self._stream_paused_for_link = False
        # Invalidates async work queued for an older connection or for a link
        # that has crossed the offline threshold.
        self._connection_generation = 0
        self._session_ready_emitted = False
        self._active_wifi_request_id = None
        self._force_reconnect_event = threading.Event()
        
        # Reconnection
        self._reconnect_delay = Protocol.RECONNECT_MIN_DELAY
        self._main_thread = None
        
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
        self._allow_direct_camera_open = True
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
        try:
            print(full_msg)
        except UnicodeEncodeError:
            # Logging must never turn a successful network handshake into a
            # reconnect when the service/console uses a legacy code page.
            try:
                print(full_msg.encode("ascii", "backslashreplace").decode("ascii"))
            except Exception:
                pass
        try:
            self.log_signal.emit(full_msg)
        except RuntimeError:
            pass

    def _connection_quality_payload(self, elapsed_seconds=0.0):
        with self._lock:
            history = list(self._rtt_history)
            state = self._connection_state

        avg = sum(history) / len(history) if history else None
        latest = history[-1] if history else None
        jitter = max(history) - min(history) if len(history) > 1 else 0.0
        quality = None
        if avg is not None:
            quality = (
                "excellent" if avg < Protocol.RTT_GOOD_MS else
                "good" if avg < Protocol.RTT_WARN_MS else
                "degraded" if avg < Protocol.RTT_BAD_MS else "poor"
            )
        return {
            'rtt_ms': round(latest, 1) if latest is not None else None,
            'avg_rtt_ms': round(avg, 1) if avg is not None else None,
            'quality': quality,
            'jitter_ms': round(jitter, 1),
            'hb_interval': round(self._current_hb_interval, 2),
            'samples': len(history),
            'connection_state': state,
            'elapsed_since_ack_s': round(max(0.0, elapsed_seconds), 2),
            'operational': Protocol.is_operational_connection_state(state),
            'stream_suspended': self._stream_paused_for_link,
        }

    def _emit_connection_quality(self, elapsed_seconds=0.0):
        try:
            self.connection_quality_signal.emit(
                self._connection_quality_payload(elapsed_seconds))
        except RuntimeError:
            pass

    def _set_connection_state(
            self, state, elapsed_seconds=0.0, *, allow_recovery=False):
        with self._lock:
            if state == self._connection_state:
                return False
            previous = self._connection_state
            if (
                not allow_recovery
                and not Protocol.is_worsening_connection_transition(
                    previous, state
                )
            ):
                return False
            self._connection_state = state
            self._recovery_ack_count = 0
            self._last_recovery_sample_at = None
            self._last_recovery_sequence = None
            self._stream_paused_for_link = (
                state != Protocol.CONNECTION_STATE_HEALTHY
            )
            if state in (
                Protocol.CONNECTION_STATE_OFFLINE,
                Protocol.CONNECTION_STATE_SESSION_EXPIRED,
            ):
                self._connection_generation += 1

        if state == Protocol.CONNECTION_STATE_OFFLINE:
            self._clear_control_outbox()

        if state == Protocol.CONNECTION_STATE_DEGRADED:
            self._current_hb_interval = Protocol.HEARTBEAT_MIN_INTERVAL
            self._log(f"Connection degraded: no ACK for {elapsed_seconds:.1f}s")
            self.status_signal.emit("Kết nối chập chờn...")
        elif state == Protocol.CONNECTION_STATE_OFFLINE:
            self._current_hb_interval = Protocol.HEARTBEAT_MIN_INTERVAL
            self._log(f"Connection offline: no ACK for {elapsed_seconds:.1f}s")
            self.status_signal.emit("Mất tín hiệu - đang thử kết nối lại...")
        elif state == Protocol.CONNECTION_STATE_SESSION_EXPIRED:
            self._current_hb_interval = Protocol.HEARTBEAT_MIN_INTERVAL
        elif previous != Protocol.CONNECTION_STATE_HEALTHY:
            self._current_hb_interval = self._calc_hb_interval()
            self._log(
                "Connection recovered after "
                f"{Protocol.RECOVERY_ACK_COUNT} consecutive ACKs"
            )
            if self.current_server_port_id is not None:
                self.status_signal.emit(
                    f"Đã kết nối: P{self.current_server_port_id}")

        self._emit_connection_quality(elapsed_seconds)
        return True
    
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

    def _load_battery_percent(self):
        """Restore the latest valid UART battery reading after a restart."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    value = json.load(f).get('battery_percent')
                if value is not None:
                    return max(0, min(100, int(value)))
        except (OSError, TypeError, ValueError):
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
                'battery_percent': self._battery_percent,
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
        self._main_thread = threading.Thread(
            target=self._main_loop, daemon=True, name="ClientMainLoop"
        )
        self._main_thread.start()
        self._log(f"Client started (prior_port_id={self.prior_port_id})")

    @staticmethod
    def _close_zmq_socket(socket):
        """Close a socket immediately without allowing LINGER to block."""
        if socket is None:
            return
        try:
            socket.close(0)
        except TypeError:
            # Small test/integration doubles may only implement close().
            try:
                socket.close()
            except Exception:
                pass
        except Exception:
            pass

    def _close_transport_sockets(self):
        """Detach and close every socket owned by the current ZMQ context.

        ``Context.term()`` waits for all sockets to close.  A failed handshake
        used to return with the DEALER socket still attached, which could
        freeze the reconnect loop forever on its next context rotation.
        """
        control_socket = self.socket
        self.socket = None
        self._close_zmq_socket(control_socket)

        with self._data_send_lock:
            data_socket = self.data_socket
            self.data_socket = None
            self._close_zmq_socket(data_socket)

        with self._stream_send_lock:
            stream_socket = self.stream_socket
            self.stream_socket = None
            self._close_zmq_socket(stream_socket)

        self._clear_control_outbox()
    
    def stop(self):
        self.running = False
        with self._lock:
            self.connected = False
            self._connection_generation += 1
        
        if self.finder:
            self.finder.cancel()
            self.finder.stop()
            self.finder = None

        self._streaming = False
        if self._stream_thread and self._stream_thread is not threading.current_thread():
            self._stream_thread.join(timeout=2.0)
            self._stream_thread = None

        # Shutdown shoot image pool
        try:
            self._shoot_pool.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass

        if self._main_thread and self._main_thread is not threading.current_thread():
            self._main_thread.join(timeout=4.0)
            self._main_thread = None
        
        self._close_transport_sockets()
        
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
        4. Probe stable MBT03 ports in the local subnet when multicast is blocked
        5. Backoff and retry
        
        No fixed port preference. After disconnect, tries same port first.
        If rejected, automatically moves to the next available port.
        """
        is_first_boot = True
        while self.running:
            try:
                # Fresh ZMQ context each connection cycle (prevents zombie sockets)
                if self.context is not None:
                    # term() is intentionally called only after all sockets
                    # have been detached and closed with LINGER=0.
                    self._close_transport_sockets()
                    old_context = self.context
                    self.context = None
                    try:
                        old_context.term()
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
            
        # === Phase 1: Direct reconnect on the last known server IP ===
        # Try both the last endpoint and the stable V27 ports. This also runs
        # on first boot so recovery does not depend entirely on mDNS.
        if self._last_server_ip:
            direct_candidates = []
            if self._last_port:
                direct_candidates.append((self._last_port, self.prior_port_id))
            stable_candidate = (
                PortMapping.get_port(self.prior_port_id), self.prior_port_id
            )
            if stable_candidate not in direct_candidates:
                direct_candidates.append(stable_candidate)
            for direct_port, direct_port_id in direct_candidates:
                if not self.running:
                    return
                if not self._tcp_probe(self._last_server_ip, direct_port):
                    continue

                self._log(
                    f"Direct reconnect → {self._last_server_ip}:{direct_port} "
                    f"(P{direct_port_id})"
                )
                self.status_signal.emit(f"Kết nối nhanh P{direct_port_id}...")
                rc = self._connect(
                    self._last_server_ip, direct_port, direct_port_id
                )
                if rc == 'accepted':
                    self._on_connect_success(
                        self._last_server_ip, direct_port,
                        direct_port_id, self._last_system_id)
                    self._heartbeat_loop()
                    self._cleanup_connection()
                    return
            
        if not self.running:
            return
            
        # === Phase 2: Zeroconf discovery (find ALL servers) ===
        # Zeroconf remains the only way to discover dynamic fallback ports.
        self._log("Zeroconf discovery...")
        self.status_signal.emit("Tìm server...")
        
        servers = []
        try:
            if self.finder is None:
                self.finder = ServerFinder(log_func=self._log)
                self.finder.start()
            finder = self.finder
            
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
            if self.finder:
                try:
                    self.finder.stop()
                except Exception:
                    pass
                self.finder = None

        # Some access points allow client-to-client unicast but suppress mDNS
        # multicast. In that case a stale cached IP used to leave the board in
        # discovery forever even though the PC's stable ports were reachable.
        if not servers and self.running:
            stable_servers = self._scan_local_stable_servers()
            if stable_servers:
                system_id = self._last_system_id or 'subnet-scan'
                servers = [
                    (ip, port, port_id, system_id)
                    for ip, port, port_id in stable_servers
                ]
            
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
        
        # === Phase 4: No server found → backoff ===
        if self.running:
            self._log(f"No server. Retry in {self._reconnect_delay:.1f}s...")
            self.status_signal.emit("Không tìm thấy server...")
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 1.5, Protocol.RECONNECT_MAX_DELAY)
    
    # ======================== TCP PROBE ========================
    
    @staticmethod
    def _local_ipv4_scan_range():
        """Return a bounded IPv4 network and this board's address.

        The board normally receives a /24 from its dedicated AP. Larger LANs
        are intentionally narrowed to the local /24 so fallback discovery
        cannot create an unbounded port scan.
        """
        local_ip = None
        prefix_length = None
        try:
            result = subprocess.run(
                ['ip', '-j', '-4', 'addr', 'show', 'dev', 'wlan0'],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
            if result.returncode == 0:
                entries = json.loads(result.stdout or '[]')
                for entry in entries:
                    for address in entry.get('addr_info', []):
                        if (
                            address.get('family') == 'inet'
                            and address.get('scope') == 'global'
                        ):
                            local_ip = ipaddress.ip_address(address['local'])
                            prefix_length = int(address['prefixlen'])
                            break
                    if local_ip is not None:
                        break
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ):
            pass

        if local_ip is None:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(('10.255.255.255', 1))
                local_ip = ipaddress.ip_address(probe.getsockname()[0])
            except (OSError, ValueError):
                return None
            finally:
                probe.close()
            prefix_length = MBT03ClientCore.SUBNET_SCAN_PREFIX

        # A dedicated AP normally uses /24. Never scan more than that even if
        # an upstream network supplies a broader prefix.
        prefix_length = max(prefix_length, MBT03ClientCore.SUBNET_SCAN_PREFIX)
        network = ipaddress.ip_network(
            f'{local_ip}/{prefix_length}', strict=False
        )
        return network, local_ip

    def _scan_local_stable_servers(self):
        """Find MBT03 candidates without relying on multicast discovery."""
        now = time.monotonic()
        if now - self._last_subnet_scan_at < self.SUBNET_SCAN_INTERVAL:
            return []
        self._last_subnet_scan_at = now

        scan_range = self._local_ipv4_scan_range()
        if scan_range is None:
            return []
        network, local_ip = scan_range
        hosts = [str(host) for host in network.hosts() if host != local_ip]
        port_ids = [self.prior_port_id] + [
            port_id for port_id in PortMapping.all_port_ids()
            if port_id != self.prior_port_id
        ]
        candidates = [
            (ip, PortMapping.get_port(port_id), port_id)
            for port_id in port_ids
            for ip in hosts
        ]
        found = []

        def probe(candidate):
            ip, port, _port_id = candidate
            if self._tcp_probe(
                ip, port, timeout=self.SUBNET_SCAN_PROBE_TIMEOUT
            ):
                return candidate
            return None

        worker_count = min(self.SUBNET_SCAN_WORKERS, len(candidates))
        if worker_count <= 0:
            return []
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix='SubnetProbe',
        ) as executor:
            futures = [executor.submit(probe, item) for item in candidates]
            for future in as_completed(futures):
                if not self.running:
                    break
                try:
                    candidate = future.result()
                except Exception:
                    candidate = None
                if candidate is not None:
                    found.append(candidate)

        port_order = {port_id: index for index, port_id in enumerate(port_ids)}
        found.sort(
            key=lambda item: (
                port_order[item[2]], ipaddress.ip_address(item[0])
            )
        )
        if found:
            endpoints = ', '.join(f'{ip}:{port}' for ip, port, _ in found)
            self._log(f'Subnet fallback found stable endpoint(s): {endpoints}')
        return found

    def _tcp_probe(self, ip: str, port: int, timeout: float = None) -> bool:
        """Quick TCP check if a port is reachable (~10ms on LAN)."""
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(
                Protocol.DIRECT_PROBE_TIMEOUT if timeout is None else timeout
            )
            return s.connect_ex((ip, port)) == 0
        except Exception:
            return False
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
    
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

    def _make_stream_socket(self):
        """Create a latest-only PUSH socket dedicated to live video."""
        s = self.context.socket(zmq.PUSH)
        s.setsockopt(zmq.LINGER, 0)
        s.setsockopt(zmq.SNDHWM, 1)
        s.setsockopt(zmq.SNDTIMEO, 0)
        s.setsockopt(zmq.TCP_KEEPALIVE, 1)
        s.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 5)
        s.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)
        conflate = getattr(zmq, 'CONFLATE', None)
        if conflate is not None:
            try:
                s.setsockopt(conflate, 1)
            except zmq.ZMQError:
                pass
        for opt_name, val in [('TCP_NODELAY', 1), ('IMMEDIATE', 1)]:
            opt = getattr(zmq, opt_name, None)
            if opt is not None:
                try:
                    s.setsockopt(opt, val)
                except zmq.ZMQError:
                    pass
        return s
    
    def _connect(self, ip: str, port: int, port_id: int) -> str:
        """Connect control, stream and shoot-data channels.
        Returns: 'accepted', 'rejected', or 'timeout'.
        """
        self.status_signal.emit(f"Kết nối P{port_id} ({ip})...")
        
        # Every attempt starts without sockets from the previous endpoint.
        self._close_transport_sockets()
        
        self.socket = self._make_control_socket()
        
        try:
            self.socket.connect(f"tcp://{ip}:{port}")
        except Exception as e:
            self._log(f"TCP connect failed: {e}")
            self._close_transport_sockets()
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
        
        connect_info = {
            'client_name': self.client_name,
            'prior_port_id': self.prior_port_id,
            'client_ip': local_ip,
            'q0_value': self.q0_value,
            'q0_size': self.q0_size,
            'protocol_version': Protocol.PROTOCOL_VERSION,
            'capabilities': [Protocol.CAPABILITY_WIFI_CONFIG_V1],
            'system_id': self._last_system_id,
        }
        payload = Protocol.encode_payload(connect_info)
        
        request_sent = False
        last_send_error = None
        for send_attempt in range(3):
            if not self.running:
                break
            try:
                self.socket.send_multipart([
                    Protocol.MSG_CONNECT_REQUEST, payload
                ])
                request_sent = True
                break
            except zmq.Again as e:
                last_send_error = e
                time.sleep(0.1)
            except Exception as e:
                last_send_error = e
                break
        if not request_sent:
            self._log(f"Connect request send failed: {last_send_error}")
            self._close_transport_sockets()
            return 'timeout'
        
        # Wait a bit longer for weak WiFi; 1s was too aggressive at range.
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        
        has_reply = bool(poller.poll(2500))
        for retry_no in range(2):
            if has_reply or not self.running:
                break
            try:
                self.socket.send_multipart([
                    Protocol.MSG_CONNECT_REQUEST, payload
                ])
                self._log(f"Retry connect request P{port_id} ({retry_no + 1}/2)")
            except Exception:
                break
            has_reply = bool(poller.poll(1500))

        if has_reply:
            try:
                frames = self.socket.recv_multipart()
                if frames[0] == Protocol.MSG_CONNECT_ACK:
                    server_info = Protocol.decode_payload(frames[1]) if len(frames) > 1 else {}
                    connection_settings = server_info.get('connection')
                    if connection_settings is not None:
                        try:
                            Protocol.configure_connection(connection_settings)
                            self._rtt_history = deque(
                                self._rtt_history,
                                maxlen=Protocol.RTT_WINDOW_SIZE,
                            )
                        except ValueError as e:
                            # Keep the last locally validated policy when an
                            # older/misconfigured server sends bad values.
                            self._log(f"Ignored invalid connection settings: {e}")
                    media_settings = server_info.get('media')
                    if media_settings is not None:
                        try:
                            Protocol.configure_media(media_settings)
                        except ValueError as e:
                            self._log(f"Ignored invalid media settings: {e}")
                    data_port = server_info.get(
                        'data_port', PortMapping.get_data_port(port_id))
                    stream_port = server_info.get(
                        'stream_port', PortMapping.get_stream_port(port_id))
                    
                    # Connect data channel (for shoot images)
                    self.data_socket = self._make_data_socket()
                    try:
                        self.data_socket.connect(f"tcp://{ip}:{data_port}")
                    except Exception as e:
                        self._log(f"Data channel failed: {e}, will use control")

                    # Live video has its own latest-only transport so a JPEG
                    # frame can never sit ahead of heartbeat/command traffic.
                    self.stream_socket = self._make_stream_socket()
                    try:
                        self.stream_socket.connect(f"tcp://{ip}:{stream_port}")
                    except Exception as e:
                        self._log(f"Stream channel failed: {e}")
                        self._close_zmq_socket(self.stream_socket)
                        self.stream_socket = None
                    
                    with self._lock:
                        self._connection_generation += 1
                        self.connected = True
                        self.current_server_ip = ip
                        self.current_server_port = port
                        self.current_server_data_port = data_port
                        self.current_server_stream_port = stream_port
                        self.current_server_port_id = port_id
                        self._rtt_history.clear()
                        self._current_hb_interval = Protocol.HEARTBEAT_INTERVAL
                        self._connection_state = Protocol.CONNECTION_STATE_HEALTHY
                        self._recovery_ack_count = 0
                        self._last_recovery_sample_at = None
                        self._last_recovery_sequence = None
                        self._heartbeat_sequence = 0
                        self._last_acked_heartbeat_sequence = -1
                        self._last_heartbeat_ack = time.monotonic()
                        self._stream_paused_for_link = False
                        self._session_ready_emitted = False
                        self._force_reconnect_event.clear()
                    
                    self._log(
                        f"✅ Connected P{port_id} at {ip}:"
                        f"{port}+{stream_port}+{data_port}")
                    self.connected_signal.emit(f"Server P{port_id} ({ip})")
                    self.status_signal.emit(f"Đã kết nối: P{port_id}")
                    return 'accepted'
                    
                elif frames[0] == Protocol.MSG_CONNECT_REJECT:
                    reason = frames[1].decode() if len(frames) > 1 else "?"
                    self._log(f"Rejected by P{port_id}: {reason}")
                    # Close socket immediately to prevent buffered messages
                    self._close_transport_sockets()
                    return 'rejected'
                else:
                    self._log("Unexpected connect response; closing attempt")
                    self._close_transport_sockets()
                    return 'timeout'
            except Exception as e:
                self._log(f"ACK parse error: {e}")
                self._close_transport_sockets()
                return 'timeout'
        else:
            self._log(f"Timeout P{port_id} (no response)")
            # CRITICAL: Close socket immediately to prevent ghost connections
            # Without this, the buffered connect request may reach the server
            # after the client has moved on to try another port
            self._close_transport_sockets()
            return 'timeout'
    
    # ======================== ADAPTIVE HEARTBEAT ========================
    
    def _calc_hb_interval(self) -> float:
        """Dynamic heartbeat interval based on RTT quality."""
        if self._connection_state != Protocol.CONNECTION_STATE_HEALTHY:
            return Protocol.HEARTBEAT_MIN_INTERVAL
        if len(self._rtt_history) < 3:
            return Protocol.HEARTBEAT_INTERVAL
        
        avg_rtt = sum(self._rtt_history) / len(self._rtt_history)
        
        if avg_rtt < Protocol.RTT_GOOD_MS:
            return Protocol.HEARTBEAT_MAX_INTERVAL
        elif avg_rtt < Protocol.RTT_WARN_MS:
            return Protocol.HEARTBEAT_INTERVAL
        else:
            return Protocol.HEARTBEAT_MIN_INTERVAL

    def _clear_control_outbox(self):
        for q in (self._priority_control_send_queue, self._control_send_queue):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        self._deferred_priority_control_send = None
        self._deferred_control_send = None

    def _control_send_allowed_locked(self) -> bool:
        return (
            self.connected
            and self.socket is not None
            and Protocol.is_operational_connection_state(
                self._connection_state)
        )

    def _stream_send_allowed_locked(self) -> bool:
        return (
            self._control_send_allowed_locked()
            and self.stream_socket is not None
            and self._connection_state == Protocol.CONNECTION_STATE_HEALTHY
            and not self._stream_paused_for_link
        )

    def _data_send_allowed_locked(self, expected_generation=None) -> bool:
        if (
            expected_generation is not None
            and expected_generation != self._connection_generation
        ):
            return False
        return (
            self.connected
            and self.data_socket is not None
            and Protocol.is_operational_connection_state(
                self._connection_state)
        )

    def _mark_transport_disconnected(self):
        """Invalidate async work as soon as the control transport is lost."""
        with self._lock:
            if self.connected:
                self.connected = False
                self._connection_generation += 1

    def _enqueue_control_send(self, frames, priority: bool = False) -> bool:
        # Keep the state check and queue insertion ordered with the offline
        # transition. Otherwise a producer can enqueue immediately after the
        # transition has cleared the outbox.
        with self._lock:
            if not self._control_send_allowed_locked():
                return False
            target_queue = (
                self._priority_control_send_queue if priority
                else self._control_send_queue
            )
            try:
                target_queue.put_nowait(
                    (self._connection_generation, frames)
                )
                return True
            except queue.Full:
                # Never evict an older accepted control message.  Callers can
                # now report backpressure accurately and decide whether to
                # retry, instead of receiving a false-success result.
                return False

    def _queue_stream_frame(self, jpeg_bytes: bytes):
        with self._lock:
            if not self._stream_send_allowed_locked():
                return False
        try:
            with self._stream_send_lock:
                with self._lock:
                    if not self._stream_send_allowed_locked():
                        return False
                    stream_socket = self.stream_socket
                stream_socket.send(jpeg_bytes, zmq.NOBLOCK)
            return True
        except (zmq.Again, zmq.ZMQError):
            # A live stream favors freshness: never wait behind an old frame.
            return False

    def _drain_control_sends(self):
        with self._lock:
            control_allowed = self._control_send_allowed_locked()
        if not control_allowed:
            self._clear_control_outbox()
            return

        for target_queue, deferred_name, max_count in (
            (
                self._priority_control_send_queue,
                '_deferred_priority_control_send',
                32,
            ),
            (self._control_send_queue, '_deferred_control_send', 32),
        ):
            for _ in range(max_count):
                item = getattr(self, deferred_name, None)
                if item is None:
                    try:
                        item = target_queue.get_nowait()
                    except queue.Empty:
                        break
                # Accept the old raw-frame private layout for in-process
                # integrations, while every new item carries the connection
                # generation that accepted it.
                if (
                    isinstance(item, tuple)
                    and len(item) == 2
                    and isinstance(item[0], int)
                ):
                    item_generation, frames = item
                else:
                    item_generation, frames = None, item
                with self._lock:
                    if (
                        not self._control_send_allowed_locked()
                        or (
                            item_generation is not None
                            and item_generation != self._connection_generation
                        )
                    ):
                        setattr(self, deferred_name, None)
                        self._clear_control_outbox()
                        return
                    socket = self.socket
                try:
                    # Priority controls must also be non-blocking: the owner
                    # loop is responsible for heartbeats and cannot safely
                    # stall behind a full transport buffer.
                    socket.send_multipart(frames, zmq.NOBLOCK)
                except zmq.Again:
                    setattr(self, deferred_name, item)
                    break
                else:
                    setattr(self, deferred_name, None)

    def _send_wifi_control(self, msg_type, payload, *, immediate=False):
        payload = dict(payload)
        payload["version"] = Protocol.WIFI_CONFIG_VERSION
        frames = [
            msg_type, Protocol.encode_payload(payload)
        ]
        if not immediate:
            return self._enqueue_control_send(frames, priority=True)

        # Wi-Fi request handling runs on the DEALER owner loop.  Requiring the
        # ACK to enter ZeroMQ before starting route reconfiguration
        # avoids changing networks after a merely queued (or full-queue) ACK.
        with self._lock:
            if not self._control_send_allowed_locked():
                return False
            socket = self.socket
            try:
                socket.send_multipart(frames, zmq.NOBLOCK)
                return True
            except (zmq.Again, zmq.ZMQError):
                return False

    def _send_wifi_ack(self, request_id, status, *, immediate=False):
        return self._send_wifi_control(
            Protocol.MSG_WIFI_CONFIG_ACK,
            {"request_id": request_id, "status": status},
            immediate=immediate,
        )

    def _decode_wifi_payload(self, payload_data):
        payload = Protocol.decode_payload(payload_data)
        if (
            not isinstance(payload, dict)
            or payload.get("version") != Protocol.WIFI_CONFIG_VERSION
        ):
            raise ValueError("invalid Wi-Fi message")
        payload["request_id"] = Protocol.validate_wifi_request_id(
            payload.get("request_id")
        )
        return payload

    def _handle_wifi_config_request(self, payload_data):
        try:
            payload = self._decode_wifi_payload(payload_data)
            Protocol.validate_wifi_credentials(
                payload.get("ssid"), payload.get("password")
            )
            rollback_timeout = float(
                payload.get("rollback_timeout_seconds", 0)
            )
            if not 30.0 <= rollback_timeout <= 600.0:
                raise ValueError("invalid rollback timeout")
        except Exception:
            return

        request_id = payload["request_id"]
        with self._lock:
            if (
                self._active_wifi_request_id is not None
                and self._active_wifi_request_id != request_id
            ):
                ack_status = "busy"
            elif self._active_wifi_request_id == request_id:
                ack_status = "duplicate"
            else:
                self._active_wifi_request_id = request_id
                ack_status = "accepted"
        ack_sent = self._send_wifi_ack(
            request_id, ack_status, immediate=True
        )
        if not ack_sent:
            if ack_status == "accepted":
                with self._lock:
                    if self._active_wifi_request_id == request_id:
                        self._active_wifi_request_id = None
            self._log(
                "Wi-Fi request ignored because its ACK could not be sent"
            )
            return
        if ack_status != "busy":
            # The DirectConnection handler only starts a worker; it must never
            # perform network reconfiguration in this ZMQ owner thread.
            self.wifi_config_request_signal.emit(payload)

    def _handle_wifi_config_decision(self, msg_type, payload_data):
        try:
            payload = self._decode_authenticated_wifi_payload(payload_data)
        except Exception:
            return
        with self._lock:
            if payload["request_id"] != self._active_wifi_request_id:
                return
        if msg_type == Protocol.MSG_WIFI_CONFIG_COMMIT:
            self.wifi_config_commit_signal.emit(payload)
        else:
            self.wifi_config_rollback_signal.emit(payload)
    
    def _heartbeat_loop(self):
        """Adaptive heartbeat loop with RTT monitoring."""
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        
        # Send the first heartbeat immediately so even a conservatively tuned
        # interval cannot exceed the server handshake grace period.
        last_hb_sent = 0.0
        last_hb_received = time.monotonic()
        
        while self.running and self.connected:
            try:
                if self._force_reconnect_event.is_set():
                    self._log("Reconnect requested after Wi-Fi route change")
                    self._mark_transport_disconnected()
                    return
                now = time.monotonic()
                self._drain_control_sends()
                
                # Poll incoming (300ms — responsive on all platforms)
                socks = dict(poller.poll(100))
                if self.socket in socks:
                    frames = self.socket.recv_multipart()
                    if not frames:
                        continue
                    msg_type = frames[0]
                    
                    if msg_type == Protocol.MSG_HEARTBEAT_ACK:
                        ack_payload = frames[1] if len(frames) > 1 else b''
                        ack_sequence = None
                        if len(ack_payload) >= 16:
                            try:
                                ack_sequence = struct.unpack(
                                    '!Q', ack_payload[8:16])[0]
                            except struct.error:
                                ack_sequence = None

                        # Legacy peers only echo the timestamp.  New peers also
                        # echo sequence so a buffered duplicate cannot falsely
                        # recover an unhealthy link.
                        fresh_ack = (
                            ack_sequence is None
                            or ack_sequence > self._last_acked_heartbeat_sequence
                        )
                        if fresh_ack:
                            if ack_sequence is not None:
                                self._last_acked_heartbeat_sequence = ack_sequence
                            now = time.monotonic()
                            last_hb_received = now
                            self._last_heartbeat_ack = now

                            rtt_seconds = None
                            rtt = None
                            if len(ack_payload) >= 8:
                                try:
                                    sent_ts = struct.unpack(
                                        '!d', ack_payload[:8])[0]
                                    rtt_seconds = max(0.0, now - sent_ts)
                                    rtt = rtt_seconds * 1000
                                except (struct.error, ValueError):
                                    rtt_seconds = None

                            recover_now = False
                            with self._lock:
                                if (
                                    self._connection_state
                                    != Protocol.CONNECTION_STATE_HEALTHY
                                ):
                                    (
                                        self._recovery_ack_count,
                                        self._last_recovery_sample_at,
                                        self._last_recovery_sequence,
                                    ) = Protocol.next_recovery_streak(
                                        self._recovery_ack_count,
                                        self._last_recovery_sample_at,
                                        self._last_recovery_sequence,
                                        now,
                                        sequence=ack_sequence,
                                        rtt_seconds=rtt_seconds,
                                    )
                                    recover_now = (
                                        self._recovery_ack_count
                                        >= Protocol.RECOVERY_ACK_COUNT
                                    )
                                else:
                                    self._recovery_ack_count = 0
                                    self._last_recovery_sample_at = None
                                    self._last_recovery_sequence = None

                            if rtt is not None:
                                self._rtt_history.append(rtt)

                            if recover_now:
                                self._set_connection_state(
                                    Protocol.CONNECTION_STATE_HEALTHY,
                                    elapsed_seconds=0.0,
                                    allow_recovery=True,
                                )
                            self._current_hb_interval = self._calc_hb_interval()
                            self._emit_connection_quality(0.0)
                            emit_ready = False
                            with self._lock:
                                if not self._session_ready_emitted:
                                    self._session_ready_emitted = True
                                    emit_ready = True
                            if emit_ready:
                                self.session_ready_signal.emit()
                    
                    elif msg_type == Protocol.MSG_DISCONNECT:
                        self._log("Server disconnect")
                        self._stop_streaming()
                        self._mark_transport_disconnected()
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
                    
                    elif msg_type == Protocol.MSG_UART_CMD:
                        if len(frames) > 1:
                            try:
                                cmd_str = frames[1].decode('utf-8')
                                self.uart_cmd_signal.emit(cmd_str)
                                safe_cmd = Protocol.redact_uart_command(cmd_str)
                                self._log(f"Received UART command: {repr(safe_cmd)}")
                            except Exception as e:
                                self._log(f"UART command decode error: {e}")

                    elif msg_type == Protocol.MSG_WIFI_CONFIG_REQUEST:
                        if len(frames) > 1:
                            self._handle_wifi_config_request(frames[1])

                    elif msg_type in (
                        Protocol.MSG_WIFI_CONFIG_COMMIT,
                        Protocol.MSG_WIFI_CONFIG_ROLLBACK,
                    ):
                        if len(frames) > 1:
                            self._handle_wifi_config_decision(
                                msg_type, frames[1]
                            )
                    
                    elif msg_type == Protocol.MSG_DATA:
                        if len(frames) > 1:
                            try:
                                data = Protocol.decode_payload(frames[1])
                                self._log(f"Data: {data}")
                            except Exception:
                                pass

                # Send heartbeat with timestamp + client-measured RTT + battery percent
                interval = self._current_hb_interval
                if now - last_hb_sent >= interval:
                    # Keep a steady retry cadence even when one send fails.
                    last_hb_sent = now
                    try:
                        ts_bytes = struct.pack('!d', time.monotonic())
                        # Include client-measured RTT so server can display accurate ping
                        # (server can't measure RTT accurately due to clock difference)
                        client_rtt = self._rtt_history[-1] if self._rtt_history else 0
                        rtt_bytes = struct.pack('!d', client_rtt)
                        with self._lock:
                            battery = (
                                float(self._battery_percent)
                                if self._battery_percent is not None else -1.0
                            )
                        battery_bytes = struct.pack('!d', battery)
                        self._heartbeat_sequence = (
                            self._heartbeat_sequence + 1
                        ) & 0xFFFFFFFFFFFFFFFF
                        sequence_bytes = struct.pack(
                            '!Q', self._heartbeat_sequence)
                        self.socket.send_multipart([
                            Protocol.MSG_HEARTBEAT,
                            ts_bytes + rtt_bytes + battery_bytes + sequence_bytes
                        ])
                    except zmq.Again:
                        pass
                    except Exception as e:
                        self._log(f"HB send error: {e}")

                # Classify silence independently of the send cadence.  The
                # degraded/offline states are soft; only the dedicated client
                # reconnect threshold tears this socket down.
                now = time.monotonic()
                elapsed = now - last_hb_received
                observed_state = Protocol.classify_connection_state(elapsed)
                if Protocol.should_client_reconnect(elapsed):
                    self._set_connection_state(
                        Protocol.CONNECTION_STATE_OFFLINE, elapsed)
                    self._log(
                        f"Connection lost (no correlated ACK for {elapsed:.1f}s); "
                        "reconnecting"
                    )
                    self._mark_transport_disconnected()
                    return
                if observed_state in (
                    Protocol.CONNECTION_STATE_DEGRADED,
                    Protocol.CONNECTION_STATE_OFFLINE,
                ):
                    self._set_connection_state(observed_state, elapsed)
                
            except zmq.ZMQError as e:
                self._log(f"ZMQ error: {e}")
                self._stop_streaming()
                self._mark_transport_disconnected()
                return
            except Exception as e:
                self._log(f"HB loop error: {e}")
                self._stop_streaming()
                self._mark_transport_disconnected()
                return
    
    def _cleanup_connection(self):
        # Stop streaming without blocking (don't join thread from heartbeat loop)
        self._streaming = False
        with self._lock:
            self.connected = False
            self._connection_generation += 1
            self.current_server_ip = None
            self.current_server_port = None
            self.current_server_data_port = None
            self.current_server_stream_port = None
            self.current_server_port_id = None
            self._session_ready_emitted = False
        self._close_transport_sockets()
        
        # Context will be terminated and recreated at top of _main_loop
        # This ensures clean ZMQ state for next connection attempt
        
        self.disconnected_signal.emit()
        self.status_signal.emit("Đã ngắt kết nối")
    
    # ======================== SHOOT ========================
    
    def shoot(self) -> bool:
        """Two-phase shoot: instant notify (control) + image (data channel)."""
        with self._lock:
            can_shoot = self._control_send_allowed_locked()
            shoot_generation = self._connection_generation
        if not can_shoot:
            self._log("Cannot shoot: not connected")
            return False
        
        now = time.time()
        # Keep client and server debounce aligned for three-round bursts.
        if now - self._last_shoot_time < 0.015:
            return False
        self._last_shoot_time = now
        
        # Phase 1: Instant notification via control channel
        if self._enqueue_control_send([
            Protocol.MSG_SHOOT_NOTIFY,
            struct.pack('!d', time.time())
        ], priority=True):
            self.shoot_sent_signal.emit()
            self._log("Shoot notification sent")
        else:
            self._log("Shoot notify failed: control queue unavailable")
            return False

        w, h = Protocol.SHOOT_RESOLUTION
        frame_for_shot = self._shoot_frame
        self._shoot_frame = None
        if frame_for_shot is None:
            frame_for_shot = self._capture_frame(w, h)
        
        # Phase 2: Image via data channel (async, non-blocking)
        def _send_image(frame):
            start_t = time.time()
            try:
                with self._lock:
                    if not self._data_send_allowed_locked(shoot_generation):
                        return
                if frame.shape[1] != w or frame.shape[0] != h:
                    frame = cv2.resize(frame, (w, h))
                
                encode_t = time.time()
                jpeg_data = self._encode_frame_jpeg(frame, Protocol.SHOOT_JPEG_QUALITY)
                
                # Build Q0 metadata to send with image
                q0_meta = Protocol.encode_payload({
                    'q0': self.q0_value,
                    'q0_size': self.q0_size,
                    'ts': time.time(),
                })
                
                with self._data_send_lock:
                    # Keep the final eligibility check ordered with the
                    # offline transition, and reject work from an older
                    # connection even if a new socket is already connected.
                    with self._lock:
                        if not self._data_send_allowed_locked(shoot_generation):
                            return
                        frames = [
                            Protocol.MSG_SHOOT_IMAGE, jpeg_data, q0_meta
                        ]
                        self.data_socket.send_multipart(frames)
                
                total_ms = (time.time() - start_t) * 1000
                encode_ms = (time.time() - encode_t) * 1000
                self.shoot_image_sent_signal.emit()
                self._log(f"Shoot image sent: {len(jpeg_data)//1024}KB, Total: {total_ms:.0f}ms (Enc: {encode_ms:.0f}ms)")
            except Exception as e:
                self._log(f"Shoot image failed: {e}")
        
        try:
            self._shoot_pool.submit(_send_image, frame_for_shot)
        except RuntimeError:
            # Pool was shut down, recreate it
            self._shoot_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ShootImg")
            self._shoot_pool.submit(_send_image, frame_for_shot)
        return True
        
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
                    # Keep the stream thread/session alive, but stop spending
                    # bandwidth and CPU on frames while heartbeat recovery is
                    # probing a degraded link.
                    if self._stream_paused_for_link:
                        time.sleep(Protocol.HEARTBEAT_MIN_INTERVAL)
                        continue

                    # Capture
                    frame = self._capture_frame(w, h)
                    
                    # Encode
                    _, jpeg = cv2.imencode('.jpg', frame, encode_params)
                    jpeg_bytes = jpeg.tobytes()
                    
                    # Send via main socket — use separate lock to avoid blocking heartbeat
                    self._queue_stream_frame(jpeg_bytes)
                    
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

    def set_direct_camera_fallback_enabled(self, enabled: bool):
        with self._camera_lock:
            self._allow_direct_camera_open = bool(enabled)
            if not enabled and self._camera_cap is not None:
                try:
                    self._camera_cap.release()
                except Exception:
                    pass
                self._camera_cap = None

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

            if not self._allow_direct_camera_open:
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
        # Keep encoding fast on ARM; optimized JPEG saves bytes but adds latency.
        params = [
            int(cv2.IMWRITE_JPEG_QUALITY), quality,
            int(cv2.IMWRITE_JPEG_OPTIMIZE), 0
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

    def set_battery_percent(self, percent) -> bool:
        try:
            value = int(percent)
        except (TypeError, ValueError):
            return False
        value = max(0, min(100, value))
        with self._lock:
            changed = value != self._battery_percent
            self._battery_percent = value
        if changed:
            self._save_config()
        return True
    
    def send_data(self, data: dict) -> bool:
        try:
            return self._enqueue_control_send([
                Protocol.MSG_DATA, Protocol.encode_payload(data)
            ])
        except Exception as e:
            self._log(f"Send error: {e}")
            return False

    def send_wifi_config_status(
            self, request_id, status, ssid, error=None):
        try:
            request_id = Protocol.validate_wifi_request_id(request_id)
        except ValueError:
            return False
        payload = {
            "request_id": request_id,
            "status": str(status),
            "ssid": str(ssid),
        }
        if error:
            payload["error"] = str(error)[:240]
        sent = self._send_wifi_control(
            Protocol.MSG_WIFI_CONFIG_STATUS, payload
        )
        if sent and status in {
            "already_connected",
            "committed",
            "rolled_back",
            "permission_denied",
            "failed",
        }:
            with self._lock:
                if self._active_wifi_request_id == request_id:
                    self._active_wifi_request_id = None
        return sent

    def restore_active_wifi_request(self, request_id):
        """Restore the decision filter for a transaction loaded after restart."""
        try:
            request_id = Protocol.validate_wifi_request_id(request_id)
        except ValueError:
            return False
        with self._lock:
            if self._active_wifi_request_id not in {None, request_id}:
                return False
            self._active_wifi_request_id = request_id
        return True

    def request_reconnect(self, reason="requested"):
        self._log(f"Reconnect scheduled: {reason}")
        self._force_reconnect_event.set()
    
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
            'stream_port': self.current_server_stream_port,
            'port_id': self.current_server_port_id,
        }
    
    @property
    def connection_quality(self):
        elapsed = (
            time.monotonic() - self._last_heartbeat_ack
            if self._last_heartbeat_ack > 0 else 0.0
        )
        payload = self._connection_quality_payload(elapsed)
        if self._rtt_history:
            payload['rtt_ms'] = round(
                sum(self._rtt_history) / len(self._rtt_history), 1)
        return payload

    @property
    def connection_state(self):
        with self._lock:
            return self._connection_state

    @property
    def is_operational(self):
        return (
            self.connected
            and Protocol.is_operational_connection_state(
                self.connection_state)
        )
