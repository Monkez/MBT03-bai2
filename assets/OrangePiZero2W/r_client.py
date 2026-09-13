# -*- coding: utf-8 -*-
import sys
import os
import time
import threading
import glob
import re
import subprocess
import cv2
import numpy as np
import serial # Use standard serial for Orange Pi Hardware UART
from PyQt5.QtCore import Qt

from wifi_sync import synchronize_wifi, get_current_ssid
from wifi_manager import WiFiTransactionManager
from connection_led import ConnectionLED

cv2.setUseOptimized(True)
try:
    cv2.setNumThreads(1)
except Exception:
    pass

# Add current dir to path to find server_client
sys.path.append(os.path.dirname(__file__))
from server_client.client_core import MBT03ClientCore
from server_client.protocol import Protocol

class MBT03HardwareClient:
    def __init__(self):
        # Initialize core logic
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.core = MBT03ClientCore(config_dir=self.app_dir)
        self.core.set_direct_camera_fallback_enabled(False)
        self.wifi_manager = WiFiTransactionManager(
            self.core,
            rollback_timeout=float(
                os.environ.get("MBT03_WIFI_ROLLBACK_TIMEOUT", "90")
            ),
            log=lambda message: print(f"[WiFi] {message}"),
        )
        
        # Hardware UART on Orange Pi Zero 2W (Pins 11/13 = UART5)
        self.serial_port_path = "/dev/ttyS5" 
        self.serial_port = None
        
        self.running = True
        self._frame_buffer = []
        self._frame_lock = threading.Lock()
        self._uart_write_lock = threading.Lock()
        self._led_stop = threading.Event()
        self._led_thread = None
        self._connection_led = ConnectionLED(self.send_uart_cmd)
        self._last_battery_percent = None
        self._camera_device = None
        self._camera_mode = None
        self._last_camera_fps_log = 0.0
        self._camera_frame_count = 0
        # Connect signals for LED feedback
        self.core.connected_signal.connect(self._on_connected, type=Qt.DirectConnection)
        self.core.disconnected_signal.connect(self._on_disconnected, type=Qt.DirectConnection)
        self.core.uart_cmd_signal.connect(self._handle_remote_command, type=Qt.DirectConnection)
        self.core.wifi_config_request_signal.connect(
            self.wifi_manager.handle_request, type=Qt.DirectConnection
        )
        self.core.wifi_config_commit_signal.connect(
            self.wifi_manager.handle_commit, type=Qt.DirectConnection
        )
        self.core.wifi_config_rollback_signal.connect(
            self.wifi_manager.handle_rollback, type=Qt.DirectConnection
        )
        self.core.session_ready_signal.connect(
            self.wifi_manager.on_session_ready, type=Qt.DirectConnection
        )

    def _init_uart(self):
        try:
            self.serial_port = serial.Serial(self.serial_port_path, 9600, timeout=0.1, write_timeout=1.0)
            print(f"[Client] Opened Hardware UART: {self.serial_port_path}")
            return True
        except Exception as e:
            print(f"[Client] UART Error: {e}")
            return False

    def _on_connected(self, server_info):
        self._connection_led.update(server_connected=True)

    def _on_disconnected(self):
        self._connection_led.update(server_connected=False)

    def _refresh_wifi_led(self):
        # SSID association, not a leftover DHCP address, determines WiFi state.
        self._connection_led.update(wifi_connected=bool(get_current_ssid()))

    def _connection_led_loop(self):
        while self.running and not self._led_stop.is_set():
            try:
                self._refresh_wifi_led()
            except Exception as exc:
                print(f"[LED] WiFi state check failed: {exc}")
            self._led_stop.wait(1.0)

    def _handle_remote_command(self, cmd_str):
        """Forward hardware commands; legacy password-bearing commands are blocked."""
        if str(cmd_str).strip().lower().startswith("wifi#"):
            print("[WiFi] Blocked legacy Wifi# UART command; use WIFI_CFG protocol")
            return
        self.send_uart_cmd(cmd_str)

    def start(self):
        started_at = time.monotonic()
        print("[Boot] Starting camera and UART WiFi initialization")
        # Camera initialization does not consume UART; overlap it with WiFi
        # negotiation, but keep a single UART reader until sync finishes.
        threading.Thread(target=self._camera_read_loop, daemon=True).start()
        threading.Thread(target=self._prewarm_capture, daemon=True).start()
        uart_ready = self._init_uart()
        if uart_ready:
            # WiFi observation runs off the startup/heartbeat paths.
            self._led_thread = threading.Thread(
                target=self._connection_led_loop, daemon=True, name='ConnectionLED')
            self._led_thread.start()
        recovered_transaction = self.wifi_manager.recover()
        uart_sync_enabled = os.environ.get(
            "MBT03_UART_WIFI_SYNC", "1"
        ).strip().lower() in {"1", "true", "yes", "on"}
        if recovered_transaction:
            print("[Client] Pending WiFi transaction recovered; UART sync skipped")
        elif uart_sync_enabled:
            status = synchronize_wifi(self.serial_port if uart_ready else None,
                                      write_lock=self._uart_write_lock)
            print(f"[Client] WiFi sync status: {status}")
        else:
            print("[Client] UART WiFi sync disabled (MBT03_UART_WIFI_SYNC=0)")

        if uart_ready:
            # Drop a late/duplicate Wi-Fi reply before the normal event parser
            # begins handling shot, battery and error messages.
            try:
                self.serial_port.reset_input_buffer()
            except Exception:
                pass

            # Only WiFi sync reads UART until this point. LED writes use the
            # same write lock as queries and never consume incoming bytes.
        self.core.start()
        print(f"[Boot] Network client started after {time.monotonic() - started_at:.2f}s")
        
        # Start loops
        threading.Thread(target=self._uart_listen_loop, daemon=True).start()
        
        print("[System] Orange Pi Hardware Client Running...")
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        self._led_stop.set()
        if self._led_thread:
            self._led_thread.join(timeout=12)
        self.wifi_manager.stop()
        self.core.stop()
        if self.serial_port:
            self.serial_port.close()

    def _prewarm_capture(self):
        try:
            deadline = time.monotonic() + 5.0
            while self.running and self.core._shared_frame is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if self.core._shared_frame is None:
                print("[System] Capture/JPEG pre-warm skipped: camera not ready")
                return
            width, height = Protocol.SHOOT_RESOLUTION
            frame = self.core._capture_frame(width, height)
            self.core._encode_frame_jpeg(
                frame, Protocol.SHOOT_JPEG_QUALITY
            )
            print("[System] Capture/JPEG pre-warmed")
        except Exception as e:
            print(f"[System] Pre-warm skipped: {e}")

    def _camera_read_loop(self):
        cap = None
        fail_count = 0
        reconnect_delay = 1.0
        last_log = 0.0
        mjpg_fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        # Keep native scoring resolution. Request high FPS first; fall back if
        # the camera/USB path cannot sustain it.
        mode_candidates = [
            (640, 480, 60),
            (640, 480, 30),
        ]

        def clear_frame():
            self.core._shared_frame = None
            with self._frame_lock:
                self._frame_buffer = []

        def is_capture_device(dev):
            name_path = f"/sys/class/video4linux/{os.path.basename(dev)}/name"
            try:
                with open(name_path, "r", encoding="utf-8", errors="ignore") as f:
                    name = f.read().strip().lower()
            except Exception:
                name = ""
            if "camera" not in name:
                return False
            try:
                result = subprocess.run(
                    ["v4l2-ctl", "-D", "-d", dev],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=1.0,
                    check=False,
                )
                if result.stdout:
                    return "Video Capture" in result.stdout
            except Exception:
                pass
            return "camera" in name and os.path.basename(dev) == "video1"

        def set_camera_controls(dev):
            # Keep exposure and white balance automatic so the camera still
            # works well in low light. Ignore unsupported controls.
            controls = (
                "auto_exposure=3,"
                "white_balance_automatic=1,"
                "power_line_frequency=1"
            )
            try:
                subprocess.run(
                    ["v4l2-ctl", "-d", dev, "-c", controls],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.5,
                    check=False,
                )
            except Exception:
                pass

        def open_with_mode(dev, width, height, fps):
            set_camera_controls(dev)
            try:
                camera_index = int(os.path.basename(dev).replace("video", ""))
            except Exception:
                camera_index = dev
            camera = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
            if not camera.isOpened():
                camera.release()
                return None, None

            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            camera.set(cv2.CAP_PROP_FOURCC, mjpg_fourcc)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            camera.set(cv2.CAP_PROP_FPS, fps)

            first_frame = None
            for _ in range(12):
                ret, frame = camera.read()
                if ret and frame is not None:
                    first_frame = frame
                    break
                time.sleep(0.01)

            if first_frame is None:
                camera.release()
                return None, None

            got_w = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            got_h = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            got_fps = camera.get(cv2.CAP_PROP_FPS) or 0
            got_fourcc = int(camera.get(cv2.CAP_PROP_FOURCC) or 0)
            got_cc = "".join(chr((got_fourcc >> 8 * i) & 255) for i in range(4))
            mode = {
                "device": dev,
                "width": got_w,
                "height": got_h,
                "fps": got_fps,
                "fourcc": got_cc,
            }
            return camera, first_frame, mode

        def open_camera():
            devices = [d for d in sorted(glob.glob("/dev/video*")) if is_capture_device(d)]
            if not devices:
                devices = ["/dev/video1", "/dev/video0"]

            for dev in devices:
                for width, height, fps in mode_candidates:
                    opened = open_with_mode(dev, width, height, fps)
                    if opened[0] is None:
                        continue
                    camera, frame, mode = opened
                    self._camera_device = dev
                    self._camera_mode = mode
                    self._last_camera_fps_log = time.time()
                    self._camera_frame_count = 0
                    print(
                        "[Camera] Using "
                        f"{dev}: {mode['width']}x{mode['height']} "
                        f"@ request {fps}fps, driver {mode['fps']:.1f}fps "
                        f"{mode['fourcc']}"
                    )
                    self.core._shared_frame = frame
                    with self._frame_lock:
                        self._frame_buffer = [frame]
                    return camera
            return None

        while self.running:
            if cap is None or not cap.isOpened():
                clear_frame()
                cap = open_camera()
                if cap is None:
                    now = time.time()
                    if now - last_log >= 5.0:
                        print("[Camera] Not available, retrying...")
                        last_log = now
                    time.sleep(reconnect_delay)
                    continue
                fail_count = 0
                print("[Camera] Connected")

            ret, frame = cap.read()
            if ret:
                fail_count = 0
                self._camera_frame_count += 1
                self.core._shared_frame = frame
                with self._frame_lock:
                    self._frame_buffer = [frame]
                now = time.time()
                if now - self._last_camera_fps_log >= 5.0:
                    fps = self._camera_frame_count / (now - self._last_camera_fps_log)
                    shape = f"{frame.shape[1]}x{frame.shape[0]}"
                    print(f"[Camera] Capture: {fps:.1f}fps @ {shape}")
                    self._last_camera_fps_log = now
                    self._camera_frame_count = 0
            else:
                fail_count += 1
                if fail_count >= 5:
                    print("[Camera] Lost, reconnecting...")
                    cap.release()
                    cap = None
                    fail_count = 0
                    clear_frame()
                time.sleep(0.2)
        if cap is not None:
            cap.release()

    def send_uart_cmd(self, cmd_str):
        if not cmd_str.endswith('\n'):
            cmd_str += '\n'
        if self.serial_port and self.serial_port.is_open:
            try:
                payload = cmd_str.encode('utf-8')
                with self._uart_write_lock:
                    written = self.serial_port.write(payload)
                if written != len(payload):
                    print("[UART] Incomplete command write")
                    return False
                print(f"[UART] Sent: {repr(cmd_str.strip())}")
                return True
            except Exception as e:
                print(f"[UART] Send error: {e}")
        return False

    def _uart_listen_loop(self):
        print("[UART] Listening for commands...")
        buf = b''
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    data = self.serial_port.read(64)
                    if data:
                        buf += data
                        text = buf.decode('utf-8', 'ignore')
                        matches = re.findall(r'BAT-(\d{1,3})', text)
                        battery_keep_from = None
                        if matches:
                            battery = max(0, min(100, int(matches[-1])))
                            if self.core.set_battery_percent(battery):
                                if battery != self._last_battery_percent:
                                    print(f"[UART] Battery: {battery}%")
                                    self._last_battery_percent = battery
                            last_match = text.rfind(f"BAT-{matches[-1]}")
                            battery_keep_from = last_match + len(f"BAT-{matches[-1]}")

                        if b'0S' in buf:
                            print("[UART] >>> SHOOT TRIGGERED <<<")
                            self.shoot()
                            buf = b''
                        elif b'0E100' in buf:
                            print("[UART] >>> ERROR E1 FROM HARDWARE <<<")
                            self.core.send_data({"UART_RX_DEBUG": "E1"})
                            buf = b''
                        elif b'0E200' in buf:
                            print("[UART] >>> ERROR E2 FROM HARDWARE <<<")
                            self.core.send_data({"UART_RX_DEBUG": "E2"})
                            buf = b''
                        elif battery_keep_from is not None:
                            buf = text[battery_keep_from:].encode('utf-8', 'ignore')
                        if len(buf) > 20: buf = buf[-20:]
                except Exception:
                    time.sleep(0.1)
            else:
                time.sleep(1.0)

    def shoot(self):
        with self._frame_lock:
            if len(self._frame_buffer) > 0:
                self.core._shoot_frame = self._frame_buffer[0]
        self.core.shoot()

if __name__ == "__main__":
    client = MBT03HardwareClient()
    client.start()
