# -*- coding: utf-8 -*-
"""
MBT03 Server Core V2.0 - Single-channel stream + data channel for shoots.

Architecture:
  Control channel (ROUTER): heartbeat, connect/disconnect, shoot_notify, 
                            stream frames, commands
  Data channel (PULL): shoot images only (high-throughput, non-blocking)

Key change from V2: Stream frames go through the main ROUTER channel
(like V1/Backup) instead of separate PUB/SUB. This eliminates the extra
thread, socket, and drain loop that caused performance issues.

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
import numpy as np
import cv2
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from PyQt5.QtCore import pyqtSignal, QObject

from .protocol import PortMapping, Protocol
from .discovery import get_local_ip


class MBT03ServerCore(QObject):
    """
    Core server logic with single-channel stream.
    
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
    
    shoot_notify_signal = pyqtSignal(float)
    shoot_image_signal = pyqtSignal(object, object)  # (frame, q0_data_dict)
    stream_frame_signal = pyqtSignal(object)
    stream_state_signal = pyqtSignal(bool)
    
    connection_quality_signal = pyqtSignal(dict)  # {rtt_ms, quality, jitter_ms}
    data_received_signal = pyqtSignal(dict)
    
    def __init__(self, port_id: int, system_id: str = None, parent=None):
        super().__init__(parent)
        
        self.port_id = port_id
        self.system_id = system_id
        
        # === ZMQ Control channel (ROUTER) — handles stream too ===
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
        
        # Bind to dynamic ports (OS assigns free ports)
        # This allows multiple app instances on the same PC
        try:
            self.socket.bind("tcp://*:0")
            self.data_socket.bind("tcp://*:0")
            # Extract actual ports assigned by OS
            self.port = int(
                self.socket.getsockopt(zmq.LAST_ENDPOINT).decode().rsplit(':', 1)[-1])
            self.data_port = int(
                self.data_socket.getsockopt(zmq.LAST_ENDPOINT).decode().rsplit(':', 1)[-1])
            self._log(f"Bound to dynamic ports: control={self.port}, data={self.data_port}")
        except zmq.ZMQError as e:
            self._log(f"[ERROR] Cannot bind: {e}")
            raise
        
        # HubRegistrar is now managed globally by main_window.py
        
        # State
        self.running = False
        self.connected_client_identity = None
        self.connected_client_name = None  # client_name from payload (stable per process)
        self.connected_client_info = None
        self.last_client_heartbeat = 0
        self._stream_active = False
        
        # RTT tracking
        self._rtt_history = deque(maxlen=Protocol.RTT_WINDOW_SIZE)
        self._last_quality_report = 0
        
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
        self.SHOOT_DEBOUNCE_MS = 33  # ~33ms minimum between accepted shots (30/s)
        
        # Rejected client tracking (for rate-limited logging)
        # {client_name: last_log_time}
        self._rejected_clients = {}
        
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._stop_lock = threading.Lock()
        self._stopped = False
    
    def _log(self, msg):
        full_msg = f"[Server P{self.port_id}] {msg}"
        try:
            self.log_signal.emit(full_msg)
        except RuntimeError:
            print(full_msg)

    def _send_control(self, frames, flags=0):
        with self._send_lock:
            self.socket.send_multipart(frames, flags=flags)
    
    def start(self):
        self._stopped = False
        self.running = True
        
        self.status_signal.emit("Đang chờ kết nối...")
        
        # 3 threads: control+stream, data, heartbeat
        threading.Thread(target=self._server_loop, daemon=True,
                         name=f"SrvCtrl-P{self.port_id}").start()
        threading.Thread(target=self._data_loop, daemon=True,
                         name=f"SrvData-P{self.port_id}").start()
        threading.Thread(target=self._heartbeat_monitor, daemon=True,
                         name=f"SrvHB-P{self.port_id}").start()
    
    def stop(self):
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
            self.running = False
            self._decode_pool.shutdown(wait=False)
            
            try:
                self.socket.close()
                self.data_socket.close()
                self.context.term()
            except Exception:
                pass
        
        self._log("Server stopped.")
        self.status_signal.emit("Đã dừng")
    
    def _disconnect_client(self, reason=""):
        with self._lock:
            if self.connected_client_identity is None:
                return
            
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
            self._rtt_history.clear()
            self._rejected_clients.clear()  # Allow rejected clients to try again
        
        self._stream_active = False
        self.stream_state_signal.emit(False)
        self.client_disconnected_signal.emit()
        self.status_signal.emit("Đang chờ kết nối...")
    
    # ======================== MAIN SERVER LOOP ========================
    
    def _server_loop(self):
        """Main server loop — handles control messages AND stream frames."""
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        
        while self.running:
            try:
                socks = dict(poller.poll(200))  # 200ms poll → responsive (was 500ms)
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
                elif msg_type == Protocol.MSG_DISCONNECT:
                    if identity == self.connected_client_identity:
                        self._stream_active = False
                        self.stream_state_signal.emit(False)
                        self._disconnect_client("Client requested disconnect")
                
            except zmq.ZMQError:
                pass
            except Exception as e:
                self._log(f"Server loop error: {e}")
    
    # ======================== DATA CHANNEL ========================
    
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
                payload = frames[1]
                
                # Any data = client alive
                with self._lock:
                    if self.connected_client_identity is not None:
                        self.last_client_heartbeat = time.time()
                
                if msg_type == Protocol.MSG_SHOOT_IMAGE:
                    q0_meta = frames[2] if len(frames) > 2 else None
                    with self._decode_lock:
                        if self._decode_inflight >= self._decode_max_inflight:
                            self._log(
                                f"Drop shoot image decode: inflight={self._decode_inflight} "
                                f"max={self._decode_max_inflight}"
                            )
                            continue
                        self._decode_inflight += 1
                    try:
                        self._decode_pool.submit(self._decode_shoot_image, payload, q0_meta)
                    except RuntimeError as e:
                        with self._decode_lock:
                            self._decode_inflight = max(0, self._decode_inflight - 1)
                        self._log(f"Decode pool submit failed: {e}")
                
            except zmq.ZMQError:
                pass
            except Exception as e:
                self._log(f"Data loop error: {e}")
    
    def _decode_shoot_image(self, data, q0_meta=None):
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
    
    def _handle_connect_request(self, identity, payload_data):
        # Parse payload early to get client_name for matching
        try:
            client_info = Protocol.decode_payload(payload_data)
        except Exception:
            client_info = {}
        
        incoming_name = client_info.get('client_name', '')
        reconnect_same_device = False
        
        with self._lock:
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
                    hb_age = time.time() - self.last_client_heartbeat
                    self._log(
                        f"Rejecting '{incoming_name}' "
                        f"(occupied by '{self.connected_client_name}', "
                        f"HB={hb_age:.1f}s)")
                    try:
                        self._send_control([
                            identity, Protocol.MSG_CONNECT_REJECT,
                            b'occupied'
                        ], zmq.NOBLOCK)
                    except (zmq.Again, Exception):
                        pass  # Drop if can't send immediately
                    return
        
        # If same device reconnecting, silently swap identity (no UI signals)
        if reconnect_same_device:
            with self._lock:
                self.connected_client_identity = None
                self.connected_client_name = None
                self.connected_client_info = None
        
        with self._lock:
            self.connected_client_identity = identity
            self.connected_client_name = incoming_name
            self.connected_client_info = client_info
            self.last_client_heartbeat = time.time()
            self._rtt_history.clear()
            self._last_accepted_shoot_time = 0
            
            # Reset FPS counter on new connection
            self._stream_fps_count = 0
            self._stream_fps_timer = time.time()
            
            ack_payload = Protocol.encode_payload({
                'port_id': self.port_id,
                'port': self.port,
                'data_port': self.data_port,
                'status': 'accepted'
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
                return
        
        client_name = incoming_name or 'Unknown'
        prior_port = client_info.get('prior_port_id', '?')
        client_ip = client_info.get('client_ip', '?')
        self._log(f"Client connected: {client_name} IP={client_ip} (prior_port={prior_port})")
        self.client_connected_signal.emit(f"{client_name} IP={client_ip} (prior={prior_port})")
        self.status_signal.emit(f"Đã kết nối: {client_name} ({client_ip})")
    
    def _handle_heartbeat(self, identity, payload_data):
        """Handle heartbeat with RTT timestamp echo."""
        # Quick check under lock — release ASAP
        with self._lock:
            if identity != self.connected_client_identity:
                return
            self.last_client_heartbeat = time.time()
        
        # Parse RTT timestamp (no lock needed)
        rtt_echo = b''
        if len(payload_data) >= 8:
            try:
                rtt_echo = payload_data[:8]  # Echo back for client's own RTT calc
                
                # Read client-measured RTT (bytes 8-16, if available)
                # Client measures RTT using its own clock (always accurate)
                # Server cross-clock RTT is unreliable when NTP hasn't synced
                client_rtt = 0
                if len(payload_data) >= 16:
                    client_rtt = struct.unpack('!d', payload_data[8:16])[0]
                
                if client_rtt > 0:
                    self._rtt_history.append(client_rtt)
                
                # Quality report on every heartbeat (instant ping display)
                if self._rtt_history:
                    avg = sum(self._rtt_history) / len(self._rtt_history)
                    latest = self._rtt_history[-1]
                    jitter = (max(self._rtt_history) - min(self._rtt_history)
                              if len(self._rtt_history) > 1 else 0)
                    q = ("excellent" if avg < Protocol.RTT_GOOD_MS else
                         "good" if avg < Protocol.RTT_WARN_MS else
                         "degraded" if avg < Protocol.RTT_BAD_MS else "poor")
                    try:
                        self.connection_quality_signal.emit({
                            'rtt_ms': round(latest, 1),
                            'quality': q,
                            'jitter_ms': round(jitter, 1),
                        })
                    except RuntimeError:
                        pass
            except Exception:
                pass
        
        # Send ACK immediately; all ROUTER sends go through _send_control.
        try:
            self._send_control([
                identity, Protocol.MSG_HEARTBEAT_ACK, rtt_echo
            ])
        except Exception:
            pass
    
    def _handle_shoot_notify(self, identity, payload_data):
        with self._lock:
            if identity != self.connected_client_identity:
                return
            self.last_client_heartbeat = time.time()
        
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
        
        elapsed_since_last = (now - self._last_accepted_shoot_time) * 1000 if self._last_accepted_shoot_time > 0 else 99999
        
        # === Debounce check (300ms) ===
        if elapsed_since_last < self.SHOOT_DEBOUNCE_MS:
            self._log(
                f"\u26a1 SHOOT REJECTED (debounce) | "
                f"server={now_str}.{now_ms:03d} client={client_str}.{client_ms:03d} "
                f"latency={latency:.0f}ms gap={elapsed_since_last:.0f}ms "
                f"(min={self.SHOOT_DEBOUNCE_MS}ms)"
            )
            return
        
        # === Accepted ===
        self._last_accepted_shoot_time = now
        self._log(
            f"\u26a1 SHOOT ACCEPTED | "
            f"server={now_str}.{now_ms:03d} client={client_str}.{client_ms:03d} "
            f"latency={latency:.0f}ms gap={elapsed_since_last:.0f}ms"
        )
        self.shoot_notify_signal.emit(client_ts)
    
    def _handle_stream_frame(self, identity, payload_data):
        """Handle stream frame — inline decode with FPS monitoring."""
        with self._lock:
            if identity != self.connected_client_identity:
                return
            self.last_client_heartbeat = time.time()
        
        try:
            nparr = np.frombuffer(payload_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
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
            if identity != self.connected_client_identity:
                return
            self.last_client_heartbeat = time.time()
        
        try:
            data = Protocol.decode_payload(payload_data)
            self._log(f"Data received: {data}")
            self.data_received_signal.emit(data)
            self._send_control([
                identity, Protocol.MSG_DATA_ACK,
                Protocol.encode_payload({'status': 'received'})
            ])
        except Exception as e:
            self._log(f"Data handling error: {e}")
    
    def _heartbeat_monitor(self):
        _warned = False
        while self.running:
            time.sleep(1.0)  # Check every 1s (fixed, independent of HB interval)
            
            with self._lock:
                if self.connected_client_identity is None:
                    _warned = False
                    continue
                elapsed = time.time() - self.last_client_heartbeat
                if elapsed <= Protocol.HEARTBEAT_TIMEOUT:
                    if elapsed > Protocol.HEARTBEAT_TIMEOUT * 0.6 and not _warned:
                        _warned = True
                        self._log(f"WiFi lag: no client HB for {elapsed:.1f}s")
                    continue
                _warned = False
            
            self._disconnect_client(f"Heartbeat timeout ({elapsed:.1f}s)")
    
    # ======================== PUBLIC API ========================
    
    def send_data_to_client(self, data: dict):
        with self._lock:
            if self.connected_client_identity is None:
                return False
            identity = self.connected_client_identity
        try:
            self._send_control([
                identity, Protocol.MSG_DATA, Protocol.encode_payload(data)
            ])
            return True
        except Exception as e:
            self._log(f"Send error: {e}")
            return False
    
    def request_stream_start(self) -> bool:
        with self._lock:
            if self.connected_client_identity is None:
                return False
            identity = self.connected_client_identity
        try:
            self._send_control([identity, Protocol.MSG_STREAM_START])
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
        with self._lock:
            if self.connected_client_identity is None:
                return False
            identity = self.connected_client_identity
        try:
            self._send_control([identity, Protocol.MSG_STREAM_STOP])
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
        with self._lock:
            if self.connected_client_identity is None:
                self._log("Cannot send Q0: no client connected")
                return False
            identity = self.connected_client_identity
        try:
            payload = Protocol.encode_payload({
                'q0': q0,
                'size': size,
            })
            self._send_control([
                identity, Protocol.MSG_SET_Q0, payload
            ])
            self._log(
                f"\u2705 Q0 sent to client: ({q0[0]:.4f}, {q0[1]:.4f}), size={size}")
            return True
        except Exception as e:
            self._log(f"Send Q0 error: {e}")
            return False
            
    def send_uart_command(self, cmd: str) -> bool:
        """Send generic UART command string to client."""
        with self._lock:
            if self.connected_client_identity is None:
                self._log("Cannot send UART command: no client connected")
                return False
            identity = self.connected_client_identity
        try:
            self._send_control([
                identity, Protocol.MSG_UART_CMD, cmd.encode('utf-8')
            ])
            self._log(f"Sent UART command: {repr(cmd)}")
            return True
        except Exception as e:
            self._log(f"Send UART command error: {e}")
            return False
    
    @property
    def is_connected(self):
        return self.connected_client_identity is not None
    
    @property
    def is_streaming(self):
        return self._stream_active
    
    @property
    def client_info(self):
        return self.connected_client_info
    
    @property
    def connection_quality(self):
        if not self._rtt_history:
            return None
        avg = sum(self._rtt_history) / len(self._rtt_history)
        jitter = (max(self._rtt_history) - min(self._rtt_history)
                  if len(self._rtt_history) > 1 else 0)
        return {'rtt_ms': round(avg, 1), 'jitter_ms': round(jitter, 1)}
