# -*- coding: utf-8 -*-
"""
MBT03 Server Core V3.0 - isolated control, stream and shoot-data channels.

Architecture:
  Control channel (ROUTER): heartbeat, connect/disconnect, shoot_notify, commands
  Stream channel (PULL): latest-only live video
  Data channel (PULL): shoot images only (high-throughput, non-blocking)

Kept from V2:
  - Data channel for shoot images (large, shouldn't block heartbeat)
  - RTT monitoring via heartbeat timestamp echo
  - TCP keepalive for WiFi stability
  - Tolerant heartbeat (5 misses = 5.5s timeout)
  - FPS monitoring on received stream
"""

import zmq
import threading
import time
import json
import struct
import queue
import numpy as np
import cv2
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from PyQt5.QtCore import pyqtSignal, QObject

from .protocol import PortMapping, Protocol
from .discovery import get_local_ip


class MBT03ServerCore(QObject):
    """
    Core server logic with a dedicated latest-only live-stream channel.
    
    Signals:
        log_signal(str), status_signal(str),
        client_connected_signal(str), client_disconnected_signal(),
        shoot_notify_signal(float), shoot_image_signal(ndarray),
        stream_frame_signal(ndarray), stream_state_signal(bool),
        connection_quality_signal(dict)
    """
    
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    client_connected_signal = pyqtSignal(str)
    client_disconnected_signal = pyqtSignal()
    # Generation-aware variants let GUI consumers discard queued events from
    # a session that was replaced before the Qt event loop handled them.  The
    # legacy signals above remain available for integrations that do not need
    # session ordering.
    client_connected_event_signal = pyqtSignal(dict)
    client_disconnected_event_signal = pyqtSignal(dict)
    
    shoot_notify_signal = pyqtSignal(float)
    shoot_image_signal = pyqtSignal(object, object)  # (frame, q0_data_dict)
    stream_frame_signal = pyqtSignal(object)
    stream_state_signal = pyqtSignal(bool)
    
    connection_quality_signal = pyqtSignal(dict)  # {rtt_ms, quality, jitter_ms}
    data_received_signal = pyqtSignal(dict)
    wifi_config_event_signal = pyqtSignal(dict)
    
    def __init__(
            self,
            port_id: int,
            system_id: str = None,
            parent=None):
        super().__init__(parent)
        
        self.port_id = port_id
        self.system_id = system_id
        
        # === ZMQ Control channel (ROUTER) — heartbeat and commands only ===
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.RCVTIMEO, 200)    # Faster poll cycle
        self.socket.setsockopt(zmq.SNDTIMEO, 500)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.TCP_KEEPALIVE, 1)
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 5)
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)
        # Optional optimizations (may not be available in older pyzmq)
        for opt_name, val in [('TCP_NODELAY', 1), ('ROUTER_MANDATORY', 0)]:
            opt = getattr(zmq, opt_name, None)
            if opt is not None:
                try:
                    self.socket.setsockopt(opt, val)
                except zmq.ZMQError:
                    pass
        
        # === ZMQ Data channel (PULL) — shoot images only ===
        self.data_socket = self.context.socket(zmq.PULL)
        self.data_socket.setsockopt(zmq.RCVTIMEO, 100)
        self.data_socket.setsockopt(zmq.LINGER, 0)
        self.data_socket.setsockopt(zmq.RCVHWM, 5)
        opt = getattr(zmq, 'TCP_NODELAY', None)
        if opt is not None:
            try:
                self.data_socket.setsockopt(opt, 1)
            except zmq.ZMQError:
                pass

        # === ZMQ Stream channel (PULL) — latest-only live video ===
        self.stream_socket = self.context.socket(zmq.PULL)
        self.stream_socket.setsockopt(zmq.RCVTIMEO, 100)
        self.stream_socket.setsockopt(zmq.LINGER, 0)
        self.stream_socket.setsockopt(zmq.RCVHWM, 1)
        conflate = getattr(zmq, 'CONFLATE', None)
        if conflate is not None:
            try:
                self.stream_socket.setsockopt(conflate, 1)
            except zmq.ZMQError:
                pass
        stream_tcp_nodelay = getattr(zmq, 'TCP_NODELAY', None)
        if stream_tcp_nodelay is not None:
            try:
                self.stream_socket.setsockopt(stream_tcp_nodelay, 1)
            except zmq.ZMQError:
                pass
        
        # Prefer the stable V27 ports so guns can reconnect directly after an
        # app restart even when weak WiFi prevents mDNS discovery. Dynamic
        # ports remain as a fallback for a second app instance.
        preferred_port = PortMapping.get_port(port_id)
        preferred_data_port = PortMapping.get_data_port(port_id)
        preferred_stream_port = PortMapping.get_stream_port(port_id)
        try:
            try:
                self.socket.bind(f"tcp://*:{preferred_port}")
            except zmq.ZMQError:
                self.socket.bind("tcp://*:0")
            try:
                self.data_socket.bind(f"tcp://*:{preferred_data_port}")
            except zmq.ZMQError:
                self.data_socket.bind("tcp://*:0")
            try:
                self.stream_socket.bind(f"tcp://*:{preferred_stream_port}")
            except zmq.ZMQError:
                self.stream_socket.bind("tcp://*:0")

            self.port = int(
                self.socket.getsockopt(zmq.LAST_ENDPOINT).decode().rsplit(':', 1)[-1])
            self.data_port = int(
                self.data_socket.getsockopt(zmq.LAST_ENDPOINT).decode().rsplit(':', 1)[-1])
            self.stream_port = int(
                self.stream_socket.getsockopt(zmq.LAST_ENDPOINT).decode().rsplit(':', 1)[-1])
            port_mode = "stable" if self.port == preferred_port else "dynamic fallback"
            self._log(
                f"Bound ports: control={self.port}, stream={self.stream_port}, "
                f"data={self.data_port} "
                f"({port_mode})"
            )
        except zmq.ZMQError as e:
            self._log(f"[ERROR] Cannot bind: {e}")
            for socket in (self.socket, self.stream_socket, self.data_socket):
                try:
                    socket.close(0)
                except Exception:
                    pass
            try:
                self.context.term()
            except Exception:
                pass
            raise
        
        # HubRegistrar is now managed globally by main_window.py
        
        # State
        self.running = False
        self.connected_client_identity = None
        self.connected_client_name = None  # client_name from payload (stable per process)
        self.connected_client_info = None
        self.last_client_heartbeat = 0
        self.last_client_activity = 0
        self._stream_active = False
        self._connection_state = Protocol.CONNECTION_STATE_HEALTHY
        self._recovery_heartbeat_count = 0
        self._last_recovery_sample_at = None
        self._last_recovery_sequence = None
        self._last_heartbeat_sequence = None
        # Incremented whenever the ROUTER slot is assigned to a new logical
        # session. The heartbeat monitor carries this generation so a stale
        # timeout decision cannot affect a newer reconnect.
        self._session_generation = 0
        self._wifi_requests = {}
        
        # RTT tracking
        self._rtt_history = deque(maxlen=Protocol.RTT_WINDOW_SIZE)
        self._last_quality_report = 0
        self._battery_percent = None
        
        # Async decode for shoot images
        self._decode_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ImgDec")
        self._decode_inflight = 0
        self._decode_max_inflight = 8
        self._decode_lock = threading.Lock()
        
        # Stream FPS monitoring
        self._stream_fps_count = 0
        self._stream_fps_timer = time.time()
        
        # Shoot debounce: last accepted shoot time (server-side rate-limit)
        self._last_accepted_shoot_time = 0
        self.SHOOT_DEBOUNCE_MS = 15  # ~15ms minimum between accepted shots
        # A pending handshake remains valid through the client's reconnect
        # threshold; deriving this avoids two independently tuned 8s values.
        self.CONNECT_GRACE_TIMEOUT = Protocol.CLIENT_RECONNECT_TIMEOUT
        self.PENDING_REPLACE_TIMEOUT = 2.5  # Different client may replace stale pending

        # Rejected client tracking (for rate-limited logging)
        # {client_name: last_log_time}
        self._rejected_clients = {}
        
        self._lock = threading.Lock()
        self._stop_lock = threading.Lock()
        self._stopped = False
        self._accepting_connections = False
        self._control_send_queue = queue.Queue(maxsize=256)
        self._control_thread_id = None
        self._control_thread = None
        self._stream_thread = None
        self._data_thread = None
        self._heartbeat_thread = None
    
    def _log(self, msg):
        full_msg = f"[Server P{self.port_id}] {msg}"
        try:
            self.log_signal.emit(full_msg)
        except RuntimeError:
            print(full_msg)

    def _connection_quality_payload(
            self,
            elapsed_seconds=0.0,
            *,
            session_generation=None,
            connection_state=None):
        """Build one stable payload for RTT and link-state consumers."""
        with self._lock:
            history = list(self._rtt_history)
            state = (
                self._connection_state
                if connection_state is None else connection_state
            )
            battery = self._battery_percent
            generation = (
                self._session_generation
                if session_generation is None else session_generation
            )

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
            'battery_percent': battery,
            'session_generation': generation,
            'connection_state': state,
            'elapsed_since_heartbeat_s': round(max(0.0, elapsed_seconds), 2),
            'operational': Protocol.is_operational_connection_state(state),
            'stream_suspended': state != Protocol.CONNECTION_STATE_HEALTHY,
        }

    def _emit_connection_quality(
            self,
            elapsed_seconds=0.0,
            *,
            session_generation=None,
            connection_state=None):
        try:
            self.connection_quality_signal.emit(
                self._connection_quality_payload(
                    elapsed_seconds,
                    session_generation=session_generation,
                    connection_state=connection_state,
                )
            )
        except RuntimeError:
            pass

    def _session_event_is_current(
            self,
            session_generation,
            *,
            identity=None,
            connection_state=None):
        """Check an event immediately before publishing its side effects."""
        with self._lock:
            if self._session_generation != session_generation:
                return False
            if (
                identity is not None
                and self.connected_client_identity != identity
            ):
                return False
            if (
                connection_state is not None
                and self._connection_state != connection_state
            ):
                return False
            return True

    def _session_allows_operation_locked(
            self,
            *,
            identity=None,
            session_generation=None,
            require_healthy=False):
        """Validate state and heartbeat age while ``self._lock`` is held."""
        if self.connected_client_identity is None:
            return False
        if identity is not None and identity != self.connected_client_identity:
            return False
        if (
            session_generation is not None
            and session_generation != self._session_generation
        ):
            return False
        if self.last_client_heartbeat <= 0:
            return False

        heartbeat_age = time.monotonic() - self.last_client_heartbeat
        if require_healthy:
            return (
                self._connection_state == Protocol.CONNECTION_STATE_HEALTHY
                and heartbeat_age < Protocol.CONNECTION_DEGRADED_TIMEOUT
            )
        return (
            Protocol.is_operational_connection_state(self._connection_state)
            and heartbeat_age < Protocol.CONNECTION_OFFLINE_TIMEOUT
        )

    def _session_snapshot_matches_locked(
            self,
            expected_identity=None,
            expected_generation=None,
            expected_heartbeat=None,
            expected_activity=None):
        """Validate a monitor snapshot while ``self._lock`` is held."""
        if expected_generation is None:
            return True
        if self._session_generation != expected_generation:
            return False
        if self.connected_client_identity != expected_identity:
            return False
        if (
            expected_heartbeat is not None
            and self.last_client_heartbeat != expected_heartbeat
        ):
            return False
        if (
            expected_activity is not None
            and self.last_client_activity != expected_activity
        ):
            return False
        return True

    def _set_connection_state(
            self,
            state,
            elapsed_seconds=0.0,
            *,
            expected_identity=None,
            expected_generation=None,
            expected_heartbeat=None,
            expected_activity=None,
            allow_recovery=False):
        with self._lock:
            if not self._session_snapshot_matches_locked(
                expected_identity=expected_identity,
                expected_generation=expected_generation,
                expected_heartbeat=expected_heartbeat,
                expected_activity=expected_activity,
            ):
                return False
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
            self._recovery_heartbeat_count = 0
            self._last_recovery_sample_at = None
            self._last_recovery_sequence = None
            transition_generation = self._session_generation
            transition_identity = self.connected_client_identity
            client_name = self.connected_client_name or "Unknown"
            client_ip = (self.connected_client_info or {}).get('client_ip', '?')

        # A reconnect can replace the session between the state mutation and
        # these queued UI/log side effects.  Generation-tagged quality events
        # are still safe if replacement happens just after this check: the GUI
        # validates the tag again when it processes the event.
        if not self._session_event_is_current(
            transition_generation,
            identity=transition_identity,
            connection_state=state,
        ):
            return True

        if state == Protocol.CONNECTION_STATE_DEGRADED:
            self._log(f"Connection degraded: no client HB for {elapsed_seconds:.1f}s")
            self.status_signal.emit("Kết nối chập chờn...")
        elif state == Protocol.CONNECTION_STATE_OFFLINE:
            self._log(f"Connection offline: no client HB for {elapsed_seconds:.1f}s")
            self.status_signal.emit("Mất tín hiệu - đang chờ kết nối lại...")
        elif state == Protocol.CONNECTION_STATE_SESSION_EXPIRED:
            self._log(f"Connection session expired after {elapsed_seconds:.1f}s")
        elif previous != Protocol.CONNECTION_STATE_HEALTHY:
            self._log(
                "Connection recovered after "
                f"{Protocol.RECOVERY_ACK_COUNT} consecutive heartbeats"
            )
            self.status_signal.emit(f"Đã kết nối: {client_name} ({client_ip})")

        self._emit_connection_quality(
            elapsed_seconds,
            session_generation=transition_generation,
            connection_state=state,
        )
        return True

    def _control_send_guard_valid_locked(self, guard):
        if not guard:
            return True
        expected_identity = guard.get('identity')
        expected_generation = guard.get('generation')
        if (
            expected_identity is not None
            and self.connected_client_identity != expected_identity
        ):
            return False
        if (
            expected_generation is not None
            and self._session_generation != expected_generation
        ):
            return False
        if guard.get('require_healthy'):
            return self._session_allows_operation_locked(
                identity=expected_identity,
                session_generation=expected_generation,
                require_healthy=True,
            )
        if guard.get('require_operational'):
            return self._session_allows_operation_locked(
                identity=expected_identity,
                session_generation=expected_generation,
            )
        return True

    def _send_control_now(self, frames, flags=0, guard=None):
        """Validate and send atomically relative to session transitions."""
        if not guard:
            self.socket.send_multipart(frames, flags=flags)
            return True
        with self._lock:
            if not self._control_send_guard_valid_locked(guard):
                return False
            self.socket.send_multipart(frames, flags=flags)
            return True

    def _send_control(
            self,
            frames,
            flags=0,
            wait=False,
            timeout=0.5,
            *,
            expected_identity=None,
            expected_generation=None,
            require_operational=False,
            require_healthy=False):
        """Send only from the control thread that owns the ROUTER socket."""
        guard = None
        if (
            expected_identity is not None
            or expected_generation is not None
            or require_operational
            or require_healthy
        ):
            guard = {
                'identity': expected_identity,
                'generation': expected_generation,
                'require_operational': bool(require_operational),
                'require_healthy': bool(require_healthy),
            }
        if threading.get_ident() == self._control_thread_id:
            return self._send_control_now(frames, flags=flags, guard=guard)

        done = threading.Event() if wait else None
        result = {} if wait else None
        try:
            self._control_send_queue.put_nowait(
                (frames, flags, done, result, guard)
            )
        except queue.Full as exc:
            raise zmq.Again("Control send queue full") from exc

        if not wait:
            return True
        if not done.wait(timeout):
            result['cancelled'] = True
            return False
        if result.get('error') is not None:
            raise result['error']
        return bool(result.get('sent'))

    def _drain_control_sends(self, max_count=64):
        for _ in range(max_count):
            try:
                item = self._control_send_queue.get_nowait()
            except queue.Empty:
                break

            # Four-field items are accepted for compatibility with any
            # in-process integration that prepared an item using the old
            # private queue layout.
            if len(item) == 4:
                frames, flags, done, result = item
                guard = None
            else:
                frames, flags, done, result, guard = item

            try:
                if result is not None and result.get('cancelled'):
                    sent = False
                else:
                    sent = self._send_control_now(
                        frames, flags=flags, guard=guard
                    )
                if result is not None:
                    result['sent'] = sent
            except Exception as exc:
                if result is not None:
                    result['error'] = exc
                elif self.running:
                    self._log(f"Control send error: {exc}")
            finally:
                if done is not None:
                    done.set()
    
    def start(self):
        self._stopped = False
        self._accepting_connections = True
        self.running = True
        
        self.status_signal.emit("Đang chờ kết nối...")
        
        # Each ZMQ socket has one owner loop. Video traffic and JPEG decoding
        # therefore cannot delay heartbeat ACKs on the control socket.
        self._control_thread = threading.Thread(
            target=self._server_loop, daemon=True,
            name=f"SrvCtrl-P{self.port_id}")
        self._stream_thread = threading.Thread(
            target=self._stream_data_loop, daemon=True,
            name=f"SrvStream-P{self.port_id}")
        self._data_thread = threading.Thread(
            target=self._data_loop, daemon=True,
            name=f"SrvData-P{self.port_id}")
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_monitor, daemon=True,
            name=f"SrvHB-P{self.port_id}")
        self._control_thread.start()
        self._stream_thread.start()
        self._data_thread.start()
        self._heartbeat_thread.start()
    
    def stop(self):
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
            self._accepting_connections = False
            disconnect_identity = self.connected_client_identity

            if disconnect_identity is not None:
                try:
                    self._send_control([
                        disconnect_identity,
                        Protocol.MSG_DISCONNECT,
                        b'Server shutting down'
                    ], wait=True, timeout=0.4)
                except Exception:
                    pass

            self.running = False
            for thread in (
                self._control_thread,
                self._stream_thread,
                self._data_thread,
                self._heartbeat_thread,
            ):
                if thread and thread is not threading.current_thread():
                    thread.join(timeout=1.2)

            self._decode_pool.shutdown(wait=False)

            for socket in (self.socket, self.stream_socket, self.data_socket):
                try:
                    socket.close()
                except Exception:
                    pass
            try:
                self.context.term()
            except Exception:
                pass

            self.connected_client_identity = None
            self.connected_client_name = None
            self.connected_client_info = None
            self.last_client_heartbeat = 0
            self.last_client_activity = 0
            self._rtt_history.clear()
            self._battery_percent = None
            self._rejected_clients.clear()
            self._stream_active = False
            self._connection_state = Protocol.CONNECTION_STATE_SESSION_EXPIRED
            self._recovery_heartbeat_count = 0
            self._last_recovery_sample_at = None
            self._last_recovery_sequence = None
            self._last_heartbeat_sequence = None
            self._session_generation += 1
        
        self._log("Server stopped.")
        self.status_signal.emit("Đã dừng")
    
    def _disconnect_client(
            self,
            reason="",
            *,
            expected_identity=None,
            expected_generation=None,
            expected_heartbeat=None,
            expected_activity=None):
        with self._lock:
            if self.connected_client_identity is None:
                return False
            if not self._session_snapshot_matches_locked(
                expected_identity=expected_identity,
                expected_generation=expected_generation,
                expected_heartbeat=expected_heartbeat,
                expected_activity=expected_activity,
            ):
                return False
            
            client_str = self.connected_client_name or str(self.connected_client_info) or "?"
            self._log(f"Client disconnected: {client_str} ({reason})")
            
            try:
                self._send_control([
                    self.connected_client_identity,
                    Protocol.MSG_DISCONNECT,
                    b'Server disconnected you'
                ])
            except Exception:
                pass
            
            self.connected_client_identity = None
            self.connected_client_name = None
            self.connected_client_info = None
            self.last_client_heartbeat = 0
            self.last_client_activity = 0
            self._rtt_history.clear()
            self._battery_percent = None
            self._rejected_clients.clear()  # Allow rejected clients to try again
            self._connection_state = Protocol.CONNECTION_STATE_SESSION_EXPIRED
            self._recovery_heartbeat_count = 0
            self._last_recovery_sample_at = None
            self._last_recovery_sequence = None
            self._last_heartbeat_sequence = None
            self._session_generation += 1
            disconnected_generation = self._session_generation
        
        self._stream_active = False
        self.stream_state_signal.emit(False)
        self.client_disconnected_event_signal.emit({
            'session_generation': disconnected_generation,
            'reason': str(reason),
        })
        self.client_disconnected_signal.emit()
        self.status_signal.emit("Đang chờ kết nối...")
        return True
    
    # ======================== MAIN SERVER LOOP ========================
    
    def _server_loop(self):
        """Main server loop for heartbeat, commands and legacy stream peers."""
        self._control_thread_id = threading.get_ident()
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        
        while self.running:
            try:
                self._drain_control_sends()
                socks = dict(poller.poll(100))
                if self.socket not in socks:
                    continue

                frames = self.socket.recv_multipart()
                if len(frames) < 2:
                    continue
                
                identity = frames[0]
                msg_type = frames[1]
                payload = frames[2] if len(frames) > 2 else b'{}'
                
                if msg_type == Protocol.MSG_CONNECT_REQUEST:
                    self._handle_connect_request(identity, payload)
                elif msg_type == Protocol.MSG_HEARTBEAT:
                    self._handle_heartbeat(identity, payload)
                elif msg_type == Protocol.MSG_SHOOT_NOTIFY:
                    self._handle_shoot_notify(identity, payload)
                elif msg_type == Protocol.MSG_STREAM_FRAME:
                    self._handle_stream_frame(identity, payload)
                elif msg_type == Protocol.MSG_DATA:
                    self._handle_data(identity, payload)
                elif msg_type in (
                    Protocol.MSG_WIFI_CONFIG_ACK,
                    Protocol.MSG_WIFI_CONFIG_STATUS,
                ):
                    self._handle_wifi_config_event(identity, msg_type, payload)
                elif msg_type == Protocol.MSG_DISCONNECT:
                    if identity == self.connected_client_identity:
                        self._stream_active = False
                        self.stream_state_signal.emit(False)
                        self._disconnect_client("Client requested disconnect")
                
            except zmq.ZMQError:
                if not self.running:
                    break
            except Exception as e:
                self._log(f"Server loop error: {e}")

        self._control_thread_id = None
    
    # ======================== DATA CHANNEL ========================

    def _stream_data_loop(self):
        """Receive the latest live-video frame on its dedicated socket."""
        poller = zmq.Poller()
        poller.register(self.stream_socket, zmq.POLLIN)

        while self.running:
            try:
                socks = dict(poller.poll(100))
                if self.stream_socket not in socks:
                    continue
                self._handle_stream_frame(None, self.stream_socket.recv())
            except zmq.ZMQError:
                if not self.running:
                    break
            except Exception as exc:
                if self.running:
                    self._log(f"Stream loop error: {exc}")
    
    def _data_loop(self):
        """Data channel loop — shoot images only."""
        poller = zmq.Poller()
        poller.register(self.data_socket, zmq.POLLIN)
        
        while self.running:
            try:
                socks = dict(poller.poll(200))
                if self.data_socket not in socks:
                    continue
                
                frames = self.data_socket.recv_multipart()
                if len(frames) < 2:
                    continue
                
                msg_type = frames[0]
                if msg_type == Protocol.MSG_SHOOT_IMAGE:
                    payload = frames[1]
                    q0_meta = frames[2] if len(frames) > 2 else None
                    with self._lock:
                        if not self._session_allows_operation_locked():
                            data_generation = None
                        else:
                            data_generation = self._session_generation
                            # Valid data traffic proves socket activity but
                            # never replaces heartbeat/ping freshness.
                            self.last_client_activity = time.monotonic()
                    if data_generation is None:
                        continue

                    with self._decode_lock:
                        if self._decode_inflight >= self._decode_max_inflight:
                            self._log(
                                f"Drop shoot image decode: inflight={self._decode_inflight} "
                                f"max={self._decode_max_inflight}"
                            )
                            continue
                        self._decode_inflight += 1
                    try:
                        self._decode_pool.submit(
                            self._decode_shoot_image,
                            payload,
                            q0_meta,
                            data_generation,
                        )
                    except RuntimeError as e:
                        with self._decode_lock:
                            self._decode_inflight = max(0, self._decode_inflight - 1)
                        self._log(f"Decode pool submit failed: {e}")
                
            except zmq.ZMQError:
                pass
            except Exception as e:
                self._log(f"Data loop error: {e}")
    
    def _decode_shoot_image(self, data, q0_meta=None, session_generation=None):
        """Async decode shoot image + Q0 metadata."""
        try:
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                # Parse Q0 metadata from client
                q0_data = {}
                if q0_meta:
                    try:
                        q0_data = Protocol.decode_payload(q0_meta)
                    except Exception:
                        pass
                
                q0_str = ""
                if q0_data.get('q0'):
                    q0 = q0_data['q0']
                    q0_str = f" Q0=({q0[0]:.4f},{q0[1]:.4f})"
                
                with self._lock:
                    if not self._session_allows_operation_locked(
                        session_generation=session_generation
                    ):
                        return
                    # Keep the final validation and emit atomic relative to an
                    # offline/reconnect transition so a decoded, buffered
                    # image cannot leak into the next UI session.
                    self._log(f"\U0001f4f8 Shoot image: {frame.shape[1]}x{frame.shape[0]} ({len(data)}B){q0_str}")
                    self.shoot_image_signal.emit(frame, q0_data)
            else:
                self._log("Shoot image decode failed")
        except Exception as e:
            self._log(f"Shoot decode error: {e}")
        finally:
            with self._decode_lock:
                self._decode_inflight = max(0, self._decode_inflight - 1)
    
    # ======================== HANDLERS ========================

    def _reject_connect(self, identity, reason):
        try:
            self._send_control([
                identity,
                Protocol.MSG_CONNECT_REJECT,
                str(reason).encode("utf-8"),
            ], zmq.NOBLOCK)
        except Exception:
            pass

    def _handle_connect_request(self, identity, payload_data):
        if not self._accepting_connections:
            try:
                self._send_control([
                    identity, Protocol.MSG_CONNECT_REJECT, b'server_stopping'
                ], zmq.NOBLOCK)
            except Exception:
                pass
            return

        try:
            client_info = Protocol.decode_payload(payload_data)
            if not isinstance(client_info, dict):
                raise ValueError("invalid_payload")
        except Exception as exc:
            self._log(f"Rejected invalid connection request: {exc}")
            self._reject_connect(identity, "invalid_payload")
            return
        
        incoming_name = client_info.get('client_name', '')
        reconnect_same_device = False
        cleared_stale_client = False
        replaced_pending_client = False
        
        with self._lock:
            if self.connected_client_identity is not None:
                now = time.monotonic()
                if self.last_client_heartbeat > 0:
                    hb_age = now - self.last_client_heartbeat
                    stale = hb_age > Protocol.HEARTBEAT_TIMEOUT
                    age_label = f"HB={hb_age:.1f}s"
                else:
                    pending_age = now - self.last_client_activity
                    stale = pending_age > self.CONNECT_GRACE_TIMEOUT
                    age_label = f"pending={pending_age:.1f}s"

                if stale:
                    stale_name = self.connected_client_name or "?"
                    self._log(
                        f"Clearing stale client '{stale_name}' before accepting reconnect "
                        f"({age_label})")
                    self.connected_client_identity = None
                    self.connected_client_name = None
                    self.connected_client_info = None
                    self.last_client_heartbeat = 0
                    self.last_client_activity = 0
                    self._rtt_history.clear()
                    self._battery_percent = None
                    self._rejected_clients.clear()
                    cleared_stale_client = True

            if (
                self.connected_client_identity is not None
                and self.last_client_heartbeat <= 0
            ):
                now = time.monotonic()
                pending_age = now - self.last_client_activity
                same_pending_client = (
                    (incoming_name and incoming_name == self.connected_client_name)
                    or identity == self.connected_client_identity
                )
                can_replace_pending = (
                    same_pending_client
                    or pending_age > self.PENDING_REPLACE_TIMEOUT
                )
                if can_replace_pending:
                    pending_name = self.connected_client_name or "?"
                    self._log(
                        f"Replacing pending handshake '{pending_name}' "
                        f"with '{incoming_name or '?'}' "
                        f"(pending={pending_age:.1f}s)"
                    )
                    self.connected_client_identity = None
                    self.connected_client_name = None
                    self.connected_client_info = None
                    self.last_client_heartbeat = 0
                    self.last_client_activity = 0
                    self._rtt_history.clear()
                    self._battery_percent = None
                    self._rejected_clients.clear()
                    replaced_pending_client = True

            if self.connected_client_identity is not None:
                # --- Decide: same device reconnect vs different device competing ---
                if incoming_name and incoming_name == self.connected_client_name:
                    # Same client_name = same physical device/process reconnecting
                    # (ZMQ identity changes each reconnect, but client_name is stable)
                    # Silently swap socket — do NOT emit disconnect/connect to UI
                    self._log(
                        f"Same device reconnecting: {incoming_name} "
                        f"(old_identity={self.connected_client_identity!r}, "
                        f"new_identity={identity!r})")
                    reconnect_same_device = True
                elif identity == self.connected_client_identity:
                    # Same ZMQ identity re-handshake
                    self._log(f"Same identity re-handshake, accepting")
                    reconnect_same_device = True
                else:
                    # Different device competing for same port_id → reject
                    # Client will handle by trying other ports (no spam)
                    hb_age = (
                        time.monotonic() - self.last_client_heartbeat
                        if self.last_client_heartbeat > 0
                        else None
                    )
                    hb_text = f"HB={hb_age:.1f}s" if hb_age is not None else "pending handshake"
                    self._log(
                        f"Rejecting '{incoming_name}' "
                        f"(occupied by '{self.connected_client_name}', "
                        f"{hb_text})")
                    try:
                        self._send_control([
                            identity, Protocol.MSG_CONNECT_REJECT,
                            b'occupied'
                        ], zmq.NOBLOCK)
                    except (zmq.Again, Exception):
                        pass  # Drop if can't send immediately
                    return

        reset_stream_state = (
            cleared_stale_client
            or replaced_pending_client
            or reconnect_same_device
        )
        if reset_stream_state:
            self._stream_active = False
            self.stream_state_signal.emit(False)
            if cleared_stale_client:
                self.client_disconnected_signal.emit()
        
        # If same device reconnecting, silently swap identity (no UI signals)
        if reconnect_same_device:
            with self._lock:
                self.connected_client_identity = None
                self.connected_client_name = None
                self.connected_client_info = None
        
        with self._lock:
            self._session_generation += 1
            self.connected_client_identity = identity
            self.connected_client_name = incoming_name
            self.connected_client_info = client_info
            now = time.monotonic()
            self.last_client_heartbeat = 0
            self.last_client_activity = now
            self._rtt_history.clear()
            self._battery_percent = None
            self._connection_state = Protocol.CONNECTION_STATE_HEALTHY
            self._recovery_heartbeat_count = 0
            self._last_recovery_sample_at = None
            self._last_recovery_sequence = None
            self._last_heartbeat_sequence = None
            self._last_accepted_shoot_time = 0
            connected_generation = self._session_generation
            
            # Reset FPS counter on new connection
            self._stream_fps_count = 0
            self._stream_fps_timer = time.time()
            
            ack_payload = Protocol.encode_payload({
                'port_id': self.port_id,
                'port': self.port,
                'data_port': self.data_port,
                'stream_port': self.stream_port,
                'status': 'accepted',
                'system_id': getattr(self, 'system_id', None),
                'connection': Protocol.connection_settings(),
                'media': Protocol.media_settings(),
            })
            
            try:
                self._send_control([
                    identity, Protocol.MSG_CONNECT_ACK, ack_payload
                ])
            except Exception as e:
                self._log(f"Failed to send ACK: {e}")
                self.connected_client_identity = None
                self.connected_client_name = None
                self.connected_client_info = None
                self._session_generation += 1
                return
        
        client_name = incoming_name or 'Unknown'
        prior_port = client_info.get('prior_port_id', '?')
        client_ip = client_info.get('client_ip', '?')
        connected_info = f"{client_name} IP={client_ip} (prior={prior_port})"
        self._log(f"Client handshake pending: {client_name} IP={client_ip} (prior_port={prior_port})")
        self.client_connected_event_signal.emit({
            'session_generation': connected_generation,
            'info': connected_info,
        })
        self.client_connected_signal.emit(connected_info)
        self.status_signal.emit(f"Đang xác nhận: {client_name} ({client_ip})")
    
    def _handle_heartbeat(self, identity, payload_data):
        """Handle heartbeat with RTT timestamp echo."""
        heartbeat_sequence = None
        reported_rtt_seconds = None
        if len(payload_data) >= 32:
            try:
                heartbeat_sequence = struct.unpack('!Q', payload_data[24:32])[0]
            except struct.error:
                heartbeat_sequence = None
        if len(payload_data) >= 16:
            try:
                reported_rtt_ms = struct.unpack('!d', payload_data[8:16])[0]
                if reported_rtt_ms > 0:
                    reported_rtt_seconds = reported_rtt_ms / 1000.0
            except (struct.error, ValueError):
                reported_rtt_seconds = None

        # Quick check under lock — release ASAP
        with self._lock:
            if identity != self.connected_client_identity:
                return
            first_heartbeat = self.last_client_heartbeat <= 0
            now = time.monotonic()
            fresh_heartbeat = (
                heartbeat_sequence is None
                or self._last_heartbeat_sequence is None
                or heartbeat_sequence > self._last_heartbeat_sequence
            )
            if not fresh_heartbeat:
                session_generation = self._session_generation
                recover_now = False
            else:
                if heartbeat_sequence is not None:
                    self._last_heartbeat_sequence = heartbeat_sequence
                self.last_client_heartbeat = now
                self.last_client_activity = now
                session_generation = self._session_generation
                recover_now = False
                if (
                    not first_heartbeat
                    and self._connection_state
                    != Protocol.CONNECTION_STATE_HEALTHY
                ):
                    (
                        self._recovery_heartbeat_count,
                        self._last_recovery_sample_at,
                        self._last_recovery_sequence,
                    ) = Protocol.next_recovery_streak(
                        self._recovery_heartbeat_count,
                        self._last_recovery_sample_at,
                        self._last_recovery_sequence,
                        now,
                        sequence=heartbeat_sequence,
                        rtt_seconds=reported_rtt_seconds,
                    )
                    recover_now = (
                        self._recovery_heartbeat_count
                        >= Protocol.RECOVERY_ACK_COUNT
                    )
                else:
                    self._recovery_heartbeat_count = 0
                    self._last_recovery_sample_at = None
                    self._last_recovery_sequence = None

        if fresh_heartbeat and first_heartbeat:
            client_name = self.connected_client_name or "Unknown"
            client_ip = (self.connected_client_info or {}).get('client_ip', '?')
            self._log(f"Client heartbeat confirmed: {client_name} ({client_ip})")
            self.status_signal.emit(f"Đã kết nối: {client_name} ({client_ip})")
        
        elif fresh_heartbeat and recover_now:
            self._set_connection_state(
                Protocol.CONNECTION_STATE_HEALTHY,
                elapsed_seconds=0.0,
                expected_identity=identity,
                expected_generation=session_generation,
                expected_heartbeat=now,
                allow_recovery=True,
            )

        # Parse RTT timestamp (no lock needed)
        rtt_echo = b''
        if len(payload_data) >= 8:
            try:
                rtt_echo = payload_data[:8]  # Echo back for client's own RTT calc
                # Sequence is appended after the legacy timestamp/RTT/battery
                # payload and echoed after the timestamp.  The extension is
                # compatible with peers that only read or return the first 8B.
                if len(payload_data) >= 32:
                    rtt_echo += payload_data[24:32]
                
                # Read client-measured RTT (bytes 8-16, if available)
                # Client measures RTT using its own clock (always accurate)
                # Server cross-clock RTT is unreliable when NTP hasn't synced
                client_rtt = 0
                if len(payload_data) >= 16:
                    client_rtt = struct.unpack('!d', payload_data[8:16])[0]
                
                if client_rtt > 0:
                    self._rtt_history.append(client_rtt)

                battery_percent = None
                if len(payload_data) >= 24:
                    battery_raw = struct.unpack('!d', payload_data[16:24])[0]
                    if battery_raw >= 0:
                        battery_percent = max(0, min(100, int(round(battery_raw))))
                        self._battery_percent = battery_percent
                
            except Exception:
                pass

        # Link state is useful even before the first RTT sample exists.
        self._emit_connection_quality(0.0)
        
        # Send ACK immediately; all ROUTER sends go through _send_control.
        try:
            self._send_control([
                identity, Protocol.MSG_HEARTBEAT_ACK, rtt_echo
            ])
        except Exception:
            pass
    
    def _handle_shoot_notify(self, identity, payload_data):
        with self._lock:
            if not self._session_allows_operation_locked(identity=identity):
                return
            session_generation = self._session_generation
            self.last_client_activity = time.monotonic()
        
        now = time.time()
        try:
            client_ts = struct.unpack('!d', payload_data)[0]
            latency = (now - client_ts) * 1000
        except Exception as e:
            self._log(f"Shoot notify parse error: {e}")
            return
        
        # === Always log for debugging (with precise timestamps) ===
        now_str = time.strftime('%H:%M:%S', time.localtime(now))
        now_ms = int((now % 1) * 1000)
        client_str = time.strftime('%H:%M:%S', time.localtime(client_ts))
        client_ms = int((client_ts % 1) * 1000)
        
        with self._lock:
            if not self._session_allows_operation_locked(
                identity=identity,
                session_generation=session_generation,
            ):
                return
            elapsed_since_last = (
                (now - self._last_accepted_shoot_time) * 1000
                if self._last_accepted_shoot_time > 0 else 99999
            )
        
        # === Debounce check ===
        if elapsed_since_last < self.SHOOT_DEBOUNCE_MS:
            self._log(
                f"\u26a1 SHOOT REJECTED (debounce) | "
                f"server={now_str}.{now_ms:03d} client={client_str}.{client_ms:03d} "
                f"latency={latency:.0f}ms gap={elapsed_since_last:.0f}ms "
                f"(min={self.SHOOT_DEBOUNCE_MS}ms)"
            )
            return
        
        # === Accepted ===
        self._log(
            f"\u26a1 SHOOT ACCEPTED | "
            f"server={now_str}.{now_ms:03d} client={client_str}.{client_ms:03d} "
            f"latency={latency:.0f}ms gap={elapsed_since_last:.0f}ms"
        )
        with self._lock:
            if not self._session_allows_operation_locked(
                identity=identity,
                session_generation=session_generation,
            ):
                return
            self._last_accepted_shoot_time = now
            self.shoot_notify_signal.emit(client_ts)
    
    def _handle_stream_frame(self, identity, payload_data):
        """Handle stream frame — inline decode with FPS monitoring."""
        with self._lock:
            if not self._session_allows_operation_locked(
                identity=identity,
                require_healthy=True,
            ):
                return
            session_generation = self._session_generation
            self.last_client_activity = time.monotonic()
        
        try:
            nparr = np.frombuffer(payload_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                with self._lock:
                    if not self._session_allows_operation_locked(
                        identity=identity,
                        session_generation=session_generation,
                        require_healthy=True,
                    ):
                        return
                    self.stream_frame_signal.emit(frame)
                    self._stream_fps_count += 1
        except Exception:
            pass
        
        # FPS report every 5 seconds
        now = time.time()
        if now - self._stream_fps_timer >= 5.0:
            elapsed = now - self._stream_fps_timer
            fps = self._stream_fps_count / elapsed if elapsed > 0 else 0
            frame_size = len(payload_data) if payload_data else 0
            self._log(
                f"\U0001f4fa Stream: {fps:.1f} fps | ~{frame_size}B/frame"
            )
            self._stream_fps_count = 0
            self._stream_fps_timer = now
    
    def _handle_data(self, identity, payload_data):
        with self._lock:
            if not self._session_allows_operation_locked(identity=identity):
                return
            session_generation = self._session_generation
            self.last_client_activity = time.monotonic()
        
        try:
            data = Protocol.decode_payload(payload_data)
            with self._lock:
                if not self._session_allows_operation_locked(
                    identity=identity,
                    session_generation=session_generation,
                ):
                    return
                self.data_received_signal.emit(data)
            self._log(f"Data received: {data}")
            self._send_control([
                identity, Protocol.MSG_DATA_ACK,
                Protocol.encode_payload({'status': 'received'})
            ],
                expected_identity=identity,
                expected_generation=session_generation,
                require_operational=True,
            )
        except Exception as e:
            self._log(f"Data handling error: {e}")

    def _handle_wifi_config_event(self, identity, msg_type, payload_data):
        try:
            payload = Protocol.decode_payload(payload_data)
            request_id = Protocol.validate_wifi_request_id(
                payload.get("request_id")
            )
        except Exception:
            return

        with self._lock:
            if identity != self.connected_client_identity:
                return
            request = self._wifi_requests.get(request_id)
        if (
            request is None
            or payload.get("version") != Protocol.WIFI_CONFIG_VERSION
        ):
            return

        status = str(payload.get("status", ""))
        allowed = (
            {"accepted", "duplicate", "busy", "invalid", "unsupported"}
            if msg_type == Protocol.MSG_WIFI_CONFIG_ACK
            else {
                "applying",
                "awaiting_commit",
                "already_connected",
                "committed",
                "rolling_back",
                "rolled_back",
                "permission_denied",
                "failed",
                "commit_failed",
                "rollback_failed",
            }
        )
        if status not in allowed:
            return

        error = payload.get("error")
        if error is not None:
            error = str(error)[:240]
        event = {
            "port_id": self.port_id,
            "kind": "ack" if msg_type == Protocol.MSG_WIFI_CONFIG_ACK else "status",
            "request_id": request_id,
            "ssid": request["ssid"],
            "status": status,
            "error": error,
        }
        with self._lock:
            request["status"] = status
            request["updated_at"] = time.time()
        self.wifi_config_event_signal.emit(event)
    
    def _heartbeat_monitor(self):
        """Report soft link states before releasing the client session."""
        while self.running:
            time.sleep(0.25)
            if not self.running:
                break

            reason = None
            observed_state = None
            with self._lock:
                if self.connected_client_identity is None:
                    continue
                observed_identity = self.connected_client_identity
                observed_generation = self._session_generation
                observed_heartbeat = self.last_client_heartbeat
                observed_activity = self.last_client_activity
                now = time.monotonic()
                if observed_heartbeat <= 0:
                    elapsed = now - observed_activity
                    if elapsed >= self.CONNECT_GRACE_TIMEOUT:
                        reason = (
                            f"Handshake timeout ({elapsed:.1f}s without heartbeat)"
                        )
                else:
                    elapsed = now - observed_heartbeat
                    observed_state = Protocol.classify_connection_state(elapsed)

            if reason is not None:
                self._disconnect_client(
                    reason,
                    expected_identity=observed_identity,
                    expected_generation=observed_generation,
                    expected_activity=observed_activity,
                )
                continue

            if observed_state == Protocol.CONNECTION_STATE_SESSION_EXPIRED:
                self._disconnect_client(
                    f"Heartbeat timeout ({elapsed:.1f}s)",
                    expected_identity=observed_identity,
                    expected_generation=observed_generation,
                    expected_heartbeat=observed_heartbeat,
                )
            elif observed_state in (
                Protocol.CONNECTION_STATE_DEGRADED,
                Protocol.CONNECTION_STATE_OFFLINE,
            ):
                # These are notification-only states.  The ROUTER identity and
                # server slot remain intact until SERVER_SESSION_TIMEOUT.
                self._set_connection_state(
                    observed_state,
                    elapsed,
                    expected_identity=observed_identity,
                    expected_generation=observed_generation,
                    expected_heartbeat=observed_heartbeat,
                )
    
    # ======================== PUBLIC API ========================

    def _healthy_wifi_target_snapshot(self):
        with self._lock:
            if not self._session_allows_operation_locked(
                require_healthy=True
            ):
                return None, None, "not_healthy"
            if not Protocol.client_supports_wifi_config(
                self.connected_client_info
            ):
                return None, None, "unsupported_client"
            return (
                self.connected_client_identity,
                self._session_generation,
                None,
            )

    def _healthy_wifi_target(self):
        """Backward-compatible three-field Wi-Fi target lookup."""
        identity, _generation, reason = (
            self._healthy_wifi_target_snapshot()
        )
        return identity, None, reason

    def request_wifi_config(
            self,
            ssid,
            password,
            request_id,
            rollback_timeout_seconds=90.0):
        try:
            ssid, password = Protocol.validate_wifi_credentials(ssid, password)
            request_id = Protocol.validate_wifi_request_id(request_id)
            rollback_timeout_seconds = float(rollback_timeout_seconds)
            if not 30.0 <= rollback_timeout_seconds <= 600.0:
                raise ValueError("rollback timeout must be 30..600 seconds")
        except (TypeError, ValueError) as exc:
            return {"ok": False, "reason": str(exc), "request_id": request_id}

        identity, session_generation, reason = (
            self._healthy_wifi_target_snapshot()
        )
        if identity is None:
            return {"ok": False, "reason": reason, "request_id": request_id}
        with self._lock:
            if request_id in self._wifi_requests:
                return {
                    "ok": False,
                    "reason": "duplicate_request_id",
                    "request_id": request_id,
                }
            if len(self._wifi_requests) >= 64:
                oldest = min(
                    self._wifi_requests,
                    key=lambda key: self._wifi_requests[key].get("created_at", 0),
                )
                self._wifi_requests.pop(oldest, None)
            self._wifi_requests[request_id] = {
                "ssid": ssid,
                "status": "sent",
                "created_at": time.time(),
                "updated_at": time.time(),
            }

        payload = {
            "version": Protocol.WIFI_CONFIG_VERSION,
            "request_id": request_id,
            "ssid": ssid,
            "password": password,
            "rollback_timeout_seconds": rollback_timeout_seconds,
        }
        try:
            sent = self._send_control([
                identity,
                Protocol.MSG_WIFI_CONFIG_REQUEST,
                Protocol.encode_payload(payload),
            ],
                wait=True,
                timeout=0.6,
                expected_identity=identity,
                expected_generation=session_generation,
                require_healthy=True,
            )
            if not sent:
                raise RuntimeError("session_changed_before_send")
        except Exception as exc:
            with self._lock:
                self._wifi_requests.pop(request_id, None)
            return {"ok": False, "reason": str(exc), "request_id": request_id}
        return {"ok": True, "reason": None, "request_id": request_id}

    def _send_wifi_decision(self, request_id, msg_type):
        try:
            request_id = Protocol.validate_wifi_request_id(request_id)
        except ValueError as exc:
            return {"ok": False, "reason": str(exc), "request_id": request_id}
        identity, session_generation, reason = (
            self._healthy_wifi_target_snapshot()
        )
        if identity is None:
            return {"ok": False, "reason": reason, "request_id": request_id}
        with self._lock:
            request = self._wifi_requests.get(request_id)
        if request is None:
            return {"ok": False, "reason": "unknown_request", "request_id": request_id}
        payload = {
            "version": Protocol.WIFI_CONFIG_VERSION,
            "request_id": request_id,
        }
        try:
            sent = self._send_control([
                identity, msg_type, Protocol.encode_payload(payload)
            ],
                wait=True,
                timeout=0.6,
                expected_identity=identity,
                expected_generation=session_generation,
                require_healthy=True,
            )
            if not sent:
                return {
                    "ok": False,
                    "reason": "session_changed_before_send",
                    "request_id": request_id,
                }
            return {"ok": True, "reason": None, "request_id": request_id}
        except Exception as exc:
            return {"ok": False, "reason": str(exc), "request_id": request_id}

    def commit_wifi_config(self, request_id):
        return self._send_wifi_decision(
            request_id, Protocol.MSG_WIFI_CONFIG_COMMIT
        )

    def rollback_wifi_config(self, request_id):
        return self._send_wifi_decision(
            request_id, Protocol.MSG_WIFI_CONFIG_ROLLBACK
        )

    def _get_live_client_target(self, *, require_healthy=False):
        with self._lock:
            if not self._session_allows_operation_locked(
                require_healthy=require_healthy
            ):
                return None, None
            return self.connected_client_identity, self._session_generation

    def _get_live_client_identity(self):
        identity, _generation = self._get_live_client_target()
        return identity

    def send_data_to_client(self, data: dict):
        identity, session_generation = self._get_live_client_target()
        if identity is None:
            return False
        try:
            return self._send_control([
                identity, Protocol.MSG_DATA, Protocol.encode_payload(data)
            ],
                wait=True,
                timeout=0.6,
                expected_identity=identity,
                expected_generation=session_generation,
                require_operational=True,
            )
        except Exception as e:
            self._log(f"Send error: {e}")
            return False
    
    def request_stream_start(self) -> bool:
        identity, session_generation = self._get_live_client_target(
            require_healthy=True
        )
        if identity is None:
            return False
        try:
            sent = self._send_control(
                [identity, Protocol.MSG_STREAM_START],
                wait=True,
                timeout=0.6,
                expected_identity=identity,
                expected_generation=session_generation,
                require_healthy=True,
            )
            if not sent:
                return False
            with self._lock:
                if not self._session_allows_operation_locked(
                    identity=identity,
                    session_generation=session_generation,
                    require_healthy=True,
                ):
                    return False
                self._stream_active = True
            self.stream_state_signal.emit(True)
            # Reset FPS counter
            self._stream_fps_count = 0
            self._stream_fps_timer = time.time()
            self._log("Stream start command sent")
            return True
        except Exception as e:
            self._log(f"Stream start error: {e}")
            return False
    
    def request_stream_stop(self) -> bool:
        identity, session_generation = self._get_live_client_target()
        if identity is None:
            return False
        try:
            sent = self._send_control(
                [identity, Protocol.MSG_STREAM_STOP],
                wait=True,
                timeout=0.6,
                expected_identity=identity,
                expected_generation=session_generation,
                require_operational=True,
            )
            if not sent:
                return False
            with self._lock:
                if not self._session_allows_operation_locked(
                    identity=identity,
                    session_generation=session_generation,
                ):
                    return False
                self._stream_active = False
            self.stream_state_signal.emit(False)
            self._log("Stream stop command sent")
            return True
        except Exception as e:
            self._log(f"Stream stop error: {e}")
            return False
    
    def send_q0_to_client(self, q0: list, size: int) -> bool:
        """Send Q0 calibration data to the connected client.
        Client will save it to config and send it back with every shoot image.
        """
        identity, session_generation = self._get_live_client_target()
        if identity is None:
            self._log("Cannot send Q0: no live client connected")
            return False
        try:
            payload = Protocol.encode_payload({
                'q0': q0,
                'size': size,
            })
            sent = self._send_control([
                identity, Protocol.MSG_SET_Q0, payload
            ],
                wait=True,
                timeout=0.6,
                expected_identity=identity,
                expected_generation=session_generation,
                require_operational=True,
            )
            if not sent:
                return False
            self._log(
                f"\u2705 Q0 sent to client: ({q0[0]:.4f}, {q0[1]:.4f}), size={size}")
            return True
        except Exception as e:
            self._log(f"Send Q0 error: {e}")
            return False
            
    def send_uart_command(self, cmd: str) -> bool:
        """Send generic UART command string to client."""
        if Protocol.is_legacy_wifi_command(cmd):
            self._log("Blocked legacy Wifi# command; use WIFI_CFG protocol")
            return False
        identity, session_generation = self._get_live_client_target()
        if identity is None:
            self._log("Cannot send UART command: no live client connected")
            return False
        try:
            sent = self._send_control([
                identity, Protocol.MSG_UART_CMD, cmd.encode('utf-8')
            ],
                wait=True,
                timeout=0.6,
                expected_identity=identity,
                expected_generation=session_generation,
                require_operational=True,
            )
            if not sent:
                return False
            safe_cmd = Protocol.redact_uart_command(cmd)
            self._log(f"Sent UART command: {repr(safe_cmd)}")
            return True
        except Exception as e:
            self._log(f"Send UART command error: {e}")
            return False
    
    @property
    def is_connected(self):
        with self._lock:
            if self.connected_client_identity is None:
                return False
            if self.last_client_heartbeat <= 0:
                return False
            if not Protocol.is_operational_connection_state(
                self._connection_state
            ):
                return False
            elapsed = time.monotonic() - self.last_client_heartbeat
            return elapsed < Protocol.CONNECTION_OFFLINE_TIMEOUT

    @property
    def is_session_reserved(self):
        """Whether this port must stay reserved for its current identity.

        ``is_connected`` intentionally turns false at the soft offline
        threshold so UI/operations react quickly.  Discovery must use this
        property instead, otherwise it could advertise the port as free during
        the 6-15 second recovery window.
        """
        with self._lock:
            if self.connected_client_identity is None:
                return False
            now = time.monotonic()
            if self.last_client_heartbeat > 0:
                return (
                    now - self.last_client_heartbeat
                ) < Protocol.SERVER_SESSION_TIMEOUT
            if self.last_client_activity > 0:
                return (
                    now - self.last_client_activity
                ) < self.CONNECT_GRACE_TIMEOUT
            return False

    @property
    def has_reserved_session(self):
        """Backward-friendly alias for discovery/UI integration."""
        return self.is_session_reserved

    @property
    def is_handshaking(self):
        with self._lock:
            if self.connected_client_identity is None:
                return False
            if self.last_client_heartbeat > 0:
                return False
            if self.last_client_activity <= 0:
                return False
            return (
                time.monotonic() - self.last_client_activity
            ) <= self.CONNECT_GRACE_TIMEOUT

    @property
    def seconds_since_last_heartbeat(self):
        with self._lock:
            if self.connected_client_identity is None or self.last_client_heartbeat <= 0:
                return None
            return time.monotonic() - self.last_client_heartbeat

    @property
    def battery_percent(self):
        return self._battery_percent
    
    @property
    def is_streaming(self):
        return self._stream_active
    
    @property
    def client_info(self):
        return self.connected_client_info
    
    @property
    def connection_quality(self):
        elapsed = self.seconds_since_last_heartbeat or 0.0
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
    def session_generation(self):
        """Current logical session generation for event-order validation."""
        with self._lock:
            return self._session_generation

    @property
    def is_operational(self):
        return self.is_connected
