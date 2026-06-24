# -*- coding: utf-8 -*-
import sys
import os
import time
import threading
import glob
import cv2
import numpy as np
import serial # Use standard serial for Orange Pi Hardware UART
from PyQt5.QtCore import Qt

# Add current dir to path to find server_client
sys.path.append(os.path.dirname(__file__))
from server_client.client_core import MBT03ClientCore

class MBT03HardwareClient:
    def __init__(self):
        # Initialize core logic
        self.core = MBT03ClientCore(config_dir=".")
        
        # Hardware UART on Orange Pi Zero 2W (Pins 11/13 = UART5)
        self.serial_port_path = "/dev/ttyS5" 
        self.serial_port = None
        
        self.running = True
        self._frame_buffer = []
        self._frame_lock = threading.Lock()
        self._last_led_cmd = None

        # Connect signals for LED feedback
        self.core.connected_signal.connect(self._on_connected, type=Qt.DirectConnection)
        self.core.disconnected_signal.connect(self._on_disconnected, type=Qt.DirectConnection)
        self.core.uart_cmd_signal.connect(self.send_uart_cmd, type=Qt.DirectConnection)

    def _init_uart(self):
        try:
            self.serial_port = serial.Serial(self.serial_port_path, 9600, timeout=0.1)
            print(f"[Client] Opened Hardware UART: {self.serial_port_path}")
            self._send_led_state("0LR01", "WiFi ready")
            time.sleep(0.2)
            self._send_led_state("0LG01", "Client started")
        except Exception as e:
            print(f"[Client] UART Error: {e}")

    def _send_led_state(self, cmd, label):
        if self._last_led_cmd == cmd:
            return
        print(f"[LED] {label} -> Sending {cmd}")
        self._last_led_cmd = cmd
        self.send_uart_cmd(cmd)

    def _on_connected(self, server_info):
        self._send_led_state("0LG00", "Server connected")

    def _on_disconnected(self):
        self._send_led_state("0LG01", "Server disconnected")

    def start(self):
        self._init_uart()
        self.core.start()
        threading.Thread(target=self._prewarm_capture, daemon=True).start()
        
        # Start loops
        threading.Thread(target=self._camera_read_loop, daemon=True).start()
        threading.Thread(target=self._uart_listen_loop, daemon=True).start()
        
        print("[System] Orange Pi Hardware Client Running...")
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        self.core.stop()
        if self.serial_port:
            self.serial_port.close()

    def _prewarm_capture(self):
        try:
            time.sleep(0.5)
            frame = self.core._capture_frame(640, 480)
            self.core._encode_frame_jpeg(frame, 65)
            print("[System] Capture/JPEG pre-warmed")
        except Exception as e:
            print(f"[System] Pre-warm skipped: {e}")

    def _camera_read_loop(self):
        cap = None
        fail_count = 0
        reconnect_delay = 1.0
        last_log = 0.0

        def clear_frame():
            self.core._shared_frame = None
            with self._frame_lock:
                self._frame_buffer = []

        def open_camera():
            devices = sorted(glob.glob("/dev/video*"))
            if not devices:
                devices = [0]

            for dev in devices:
                camera = cv2.VideoCapture(dev)
                if not camera.isOpened():
                    camera.release()
                    continue

                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                ret, frame = camera.read()
                if ret and frame is not None:
                    print(f"[Camera] Using {dev}")
                    self.core._shared_frame = frame
                    with self._frame_lock:
                        self._frame_buffer = [frame]
                    return camera

                camera.release()
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
                self.core._shared_frame = frame
                with self._frame_lock:
                    self._frame_buffer = [frame]
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
                self.serial_port.write(cmd_str.encode('utf-8'))
                print(f"[UART] Sent: {repr(cmd_str.strip())}")
            except Exception as e:
                print(f"[UART] Send error: {e}")

    def _uart_listen_loop(self):
        print("[UART] Listening for commands...")
        buf = b''
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    data = self.serial_port.read(64)
                    if data:
                        buf += data
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
