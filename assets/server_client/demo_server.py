# -*- coding: utf-8 -*-
"""
Demo Server GUI - PyQt5 application with Camera view support.

Usage:
    python demo_server.py <port_id>
    
    port_id: 1, 2, 3, or 4
"""

import sys
import os
import time

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import numpy as np
import cv2
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QFrame, QLineEdit, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QFont, QImage, QPixmap

from server_client.server_core import MBT03ServerCore
from server_client.protocol import PortMapping


class ServerDemoWindow(QMainWindow):
    def __init__(self, port_id: int):
        super().__init__()
        self.port_id = port_id
        self.port = PortMapping.get_port(port_id)
        
        self.setWindowTitle(f"MBT03 Server - Port {port_id} (:{self.port})")
        self.setMinimumSize(700, 550)
        self.resize(750, 620)
        
        self._setup_ui()
        self._setup_style()
        self._start_server()
        
        self.start_time = time.time()
        self.uptime_timer = QTimer()
        self.uptime_timer.timeout.connect(self._update_uptime)
        self.uptime_timer.start(1000)
        
        self._stream_frame_count = 0
        self._stream_fps_time = time.time()
        self._stream_fps = 0.0
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._update_fps_display)
        self.fps_timer.start(1000)
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(5)
        root.setContentsMargins(8, 8, 8, 8)
        
        # ── ROW 1: Header bar ──
        hdr = QFrame()
        hdr.setObjectName("hdr")
        hdr.setFixedHeight(48)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(10, 4, 10, 4)
        
        title = QLabel(f"🖥️ Server P{self.port_id}")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setObjectName("title")
        hl.addWidget(title)
        
        self.lbl_status = QLabel("Khởi động...")
        self.lbl_status.setFont(QFont("Segoe UI", 9))
        self.lbl_status.setObjectName("sub")
        hl.addWidget(self.lbl_status)
        hl.addStretch()
        
        self.lbl_uptime = QLabel("0s")
        self.lbl_uptime.setFont(QFont("Segoe UI", 9))
        self.lbl_uptime.setObjectName("sub")
        hl.addWidget(self.lbl_uptime)
        
        self.dot = QLabel("●")
        self.dot.setFont(QFont("Segoe UI", 18))
        self.dot.setStyleSheet("color:#ffa500;")
        hl.addWidget(self.dot)
        
        root.addWidget(hdr)
        
        # ── ROW 2: Client info + controls (single line) ──
        r2 = QHBoxLayout()
        r2.setSpacing(5)
        
        self.lbl_client = QLabel("Client: —")
        self.lbl_client.setFont(QFont("Segoe UI", 9))
        self.lbl_client.setObjectName("infoLabel")
        self.lbl_client.setFixedHeight(28)
        r2.addWidget(self.lbl_client, 1)
        
        self.btn_disconnect = QPushButton("⛔ Ngắt")
        self.btn_disconnect.setFont(QFont("Segoe UI", 9))
        self.btn_disconnect.setFixedSize(70, 28)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self._disconnect_client)
        r2.addWidget(self.btn_disconnect)
        
        self.btn_stream = QPushButton("▶ Stream")
        self.btn_stream.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.btn_stream.setFixedSize(100, 28)
        self.btn_stream.setEnabled(False)
        self.btn_stream.setObjectName("streamBtn")
        self.btn_stream.clicked.connect(self._toggle_stream)
        r2.addWidget(self.btn_stream)
        
        root.addLayout(r2)
        
        # ── ROW 3: Camera views (stream + shoot side by side) ──
        cam_row = QHBoxLayout()
        cam_row.setSpacing(6)
        
        # Stream column
        sc = QVBoxLayout()
        sc.setSpacing(2)
        lbl_s = QLabel("🎬 Stream")
        lbl_s.setFont(QFont("Segoe UI", 8, QFont.Bold))
        lbl_s.setAlignment(Qt.AlignCenter)
        sc.addWidget(lbl_s)
        
        self.stream_view = QLabel("OFF")
        self.stream_view.setFixedSize(340, 227)
        self.stream_view.setAlignment(Qt.AlignCenter)
        self.stream_view.setObjectName("camView")
        sc.addWidget(self.stream_view, 0, Qt.AlignCenter)
        
        self.lbl_fps = QLabel("FPS: --")
        self.lbl_fps.setFont(QFont("Segoe UI", 8))
        self.lbl_fps.setAlignment(Qt.AlignCenter)
        sc.addWidget(self.lbl_fps)
        cam_row.addLayout(sc)
        
        # Shoot column
        shc = QVBoxLayout()
        shc.setSpacing(2)
        lbl_h = QLabel("📸 Shoot")
        lbl_h.setFont(QFont("Segoe UI", 8, QFont.Bold))
        lbl_h.setAlignment(Qt.AlignCenter)
        shc.addWidget(lbl_h)
        
        self.shoot_view = QLabel("—")
        self.shoot_view.setFixedSize(340, 227)
        self.shoot_view.setAlignment(Qt.AlignCenter)
        self.shoot_view.setObjectName("camView")
        shc.addWidget(self.shoot_view, 0, Qt.AlignCenter)
        
        self.lbl_shoot_info = QLabel(" ")
        self.lbl_shoot_info.setFont(QFont("Segoe UI", 8))
        self.lbl_shoot_info.setAlignment(Qt.AlignCenter)
        shc.addWidget(self.lbl_shoot_info)
        cam_row.addLayout(shc)
        
        root.addLayout(cam_row)
        
        # ── ROW 4: Send data (inline) ──
        sr = QHBoxLayout()
        sr.setSpacing(4)
        
        self.txt_send = QLineEdit()
        self.txt_send.setPlaceholderText("Gửi tới client...")
        self.txt_send.setFont(QFont("Segoe UI", 9))
        self.txt_send.setFixedHeight(28)
        self.txt_send.returnPressed.connect(self._send_data)
        sr.addWidget(self.txt_send)
        
        self.btn_send = QPushButton("📤")
        self.btn_send.setFont(QFont("Segoe UI", 9))
        self.btn_send.setFixedSize(36, 28)
        self.btn_send.setEnabled(False)
        self.btn_send.clicked.connect(self._send_data)
        sr.addWidget(self.btn_send)
        
        root.addLayout(sr)
        
        # ── ROW 5: Log (fills remaining space) ──
        log_row = QHBoxLayout()
        log_row.setSpacing(0)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 8))
        log_row.addWidget(self.log_text)
        
        root.addLayout(log_row, 1)
    
    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #1e1e2e; }
            QWidget { color: #cdd6f4; }
            QFrame#hdr { background: #313244; border-radius: 6px; }
            QLabel#title { color: #89b4fa; }
            QLabel#sub { color: #a6adc8; }
            QLabel#infoLabel {
                background: #313244; border-radius: 4px;
                padding: 2px 8px;
            }
            QLabel#camView {
                background: #11111b;
                border: 2px solid #45475a;
                border-radius: 4px;
                color: #585b70;
            }
            QLineEdit {
                background: #45475a; border: 1px solid #585b70;
                border-radius: 4px; padding: 2px 6px; color: #cdd6f4;
            }
            QLineEdit:focus { border-color: #89b4fa; }
            QPushButton {
                background: #45475a; border: 1px solid #585b70;
                border-radius: 4px; padding: 2px 8px; color: #cdd6f4;
            }
            QPushButton:hover { background: #585b70; border-color: #89b4fa; }
            QPushButton:pressed { background: #313244; }
            QPushButton:disabled { background: #313244; color: #585b70; border-color: #45475a; }
            QPushButton#streamBtn {
                background: #a6e3a1; color: #1e1e2e;
                border: 2px solid #a6e3a1; font-weight: bold;
            }
            QPushButton#streamBtn:hover { background: #b8ecb4; border-color: #b8ecb4; }
            QPushButton#streamBtn:disabled { background: #313244; color: #585b70; border-color: #45475a; }
            QTextEdit {
                background: #11111b; border: 1px solid #45475a;
                border-radius: 4px; padding: 2px; color: #a6e3a1;
            }
        """)
    
    def _start_server(self):
        try:
            self.server = MBT03ServerCore(self.port_id)
            self.server.log_signal.connect(self._on_log)
            self.server.status_signal.connect(self._on_status)
            self.server.client_connected_signal.connect(self._on_client_connected)
            self.server.client_disconnected_signal.connect(self._on_client_disconnected)
            self.server.shoot_notify_signal.connect(self._on_shoot_notify)
            self.server.shoot_image_signal.connect(self._on_shoot_image)
            self.server.stream_frame_signal.connect(self._on_stream_frame)
            self.server.stream_state_signal.connect(self._on_stream_state)
            self.server.start()
        except Exception as e:
            self._on_log(f"[FATAL] Cannot start server: {e}")
    
    @pyqtSlot(str)
    def _on_log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {msg}")
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    @pyqtSlot(str)
    def _on_status(self, status):
        self.lbl_status.setText(status)
        if "kết nối" in status.lower() and "chờ" not in status.lower() and "ngắt" not in status.lower():
            self.dot.setStyleSheet("color:#a6e3a1;")
        elif "chờ" in status.lower():
            self.dot.setStyleSheet("color:#ffa500;")
        else:
            self.dot.setStyleSheet("color:#f38ba8;")
    
    @pyqtSlot(str)
    def _on_client_connected(self, info):
        self.lbl_client.setText(f"✅ {info}")
        self.btn_disconnect.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_stream.setEnabled(True)
    
    @pyqtSlot()
    def _on_client_disconnected(self):
        self.lbl_client.setText("Client: —")
        self.btn_disconnect.setEnabled(False)
        self.btn_send.setEnabled(False)
        self.btn_stream.setEnabled(False)
        self._set_stream_btn(False)
        self.stream_view.setPixmap(QPixmap())
        self.stream_view.setText("OFF")
        self.lbl_fps.setText("FPS: --")
    
    @pyqtSlot(float)
    def _on_shoot_notify(self, timestamp):
        self.shoot_view.setStyleSheet(
            "background:#11111b; border:3px solid #f38ba8; border-radius:4px;"
        )
        self.lbl_shoot_info.setText("⚡ Chờ ảnh...")
        QTimer.singleShot(500, lambda: self.shoot_view.setStyleSheet(
            "background:#11111b; border:2px solid #45475a; border-radius:4px;"
        ))
    
    @pyqtSlot(object)
    def _on_shoot_image(self, frame):
        self._show_frame(frame, self.shoot_view)
        h, w = frame.shape[:2]
        self.lbl_shoot_info.setText(f"📸 {w}×{h} | {time.strftime('%H:%M:%S')}")
    
    @pyqtSlot(object)
    def _on_stream_frame(self, frame):
        self._show_frame(frame, self.stream_view)
        self._stream_frame_count += 1
    
    @pyqtSlot(bool)
    def _on_stream_state(self, active):
        self._set_stream_btn(active)
        if not active:
            self.stream_view.setPixmap(QPixmap())
            self.stream_view.setText("OFF")
            self.lbl_fps.setText("FPS: --")
            self._stream_frame_count = 0
    
    def _show_frame(self, frame, label):
        if frame is None:
            return
        try:
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(qimg)
            label.setPixmap(pix.scaled(label.size(), Qt.KeepAspectRatio, Qt.FastTransformation))
        except Exception:
            pass
    
    def _update_fps_display(self):
        now = time.time()
        dt = now - self._stream_fps_time
        if dt >= 1.0:
            self._stream_fps = self._stream_frame_count / dt
            self._stream_frame_count = 0
            self._stream_fps_time = now
            if hasattr(self, 'server') and self.server.is_streaming:
                self.lbl_fps.setText(f"FPS: {self._stream_fps:.1f}")
    
    def _toggle_stream(self):
        if not hasattr(self, 'server'):
            return
        if self.server.is_streaming:
            self.server.request_stream_stop()
        else:
            self.server.request_stream_start()
    
    def _set_stream_btn(self, streaming: bool):
        if streaming:
            self.btn_stream.setText("⏹ Stop")
            self.btn_stream.setStyleSheet("""
                QPushButton { background:#f38ba8; color:#1e1e2e;
                    border:2px solid #f38ba8; font-weight:bold; border-radius:4px; padding:2px 8px; }
                QPushButton:hover { background:#eba0b3; border-color:#eba0b3; }
            """)
        else:
            self.btn_stream.setText("▶ Stream")
            self.btn_stream.setStyleSheet("")
    
    def _disconnect_client(self):
        if hasattr(self, 'server'):
            self.server._disconnect_client("Manual disconnect from UI")
    
    def _send_data(self):
        text = self.txt_send.text().strip()
        if not text:
            return
        if hasattr(self, 'server'):
            ok = self.server.send_data_to_client({'message': text, 'time': time.time()})
            if ok:
                self._on_log(f"[TX] {text}")
                self.txt_send.clear()
            else:
                self._on_log("[TX] Failed")
    
    def _update_uptime(self):
        s = int(time.time() - self.start_time)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        self.lbl_uptime.setText(f"{h}h{m}m{s}s")
    
    def closeEvent(self, event):
        if hasattr(self, 'server'):
            if self.server.is_streaming:
                self.server.request_stream_stop()
            self.server.stop()
        event.accept()


def main():
    if len(sys.argv) < 2:
        print("Usage: python demo_server.py <port_id>")
        print("  port_id: 1 (→1711), 2 (→1995), 3 (→1999), 4 (→2026)")
        sys.exit(1)
    
    try:
        port_id = int(sys.argv[1])
        if port_id not in PortMapping.MAP:
            print(f"Error: port_id must be 1-4, got {port_id}")
            sys.exit(1)
    except ValueError:
        print(f"Error: port_id must be integer, got '{sys.argv[1]}'")
        sys.exit(1)
    
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    except Exception:
        pass
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = ServerDemoWindow(port_id)
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
