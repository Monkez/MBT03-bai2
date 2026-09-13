# -*- coding: utf-8 -*-
"""
Demo Client GUI - PyQt5 application with Camera support.

Usage:
    python client_demo.py [prior_port_id]
    
    prior_port_id: 1, 2, 3, or 4 (default: loads from config or 1)
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
    QLabel, QTextEdit, QPushButton, QFrame, QLineEdit, QProgressBar,
    QSpinBox, QComboBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QFont, QImage, QPixmap

from server_client.client_core import MBT03ClientCore
from server_client.protocol import PortMapping, Protocol


class ClientDemoWindow(QMainWindow):
    def __init__(
            self,
            prior_port_id: int = None,
            camera_index: int = None,
            camera_backend: str = None):
        super().__init__()
        
        self.setWindowTitle("MBT03 Client Demo")
        self.setMinimumSize(520, 500)
        self.resize(560, 560)
        
        self._setup_ui()
        self._setup_style()
        self._start_client(prior_port_id, camera_index, camera_backend)
        
        self.start_time = time.time()
        self.uptime_timer = QTimer()
        self.uptime_timer.timeout.connect(self._update_uptime)
        self.uptime_timer.start(1000)
        
        self.search_start_time = time.time()
        self.search_timer = QTimer()
        self.search_timer.timeout.connect(self._update_search_progress)
        self.search_timer.start(500)
        
        # Camera preview timer
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self._update_local_preview)
        self.preview_timer.start(50)  # ~20fps local preview
    
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
        
        self.lbl_title = QLabel("📱 Client")
        self.lbl_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.lbl_title.setObjectName("title")
        hl.addWidget(self.lbl_title)
        
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
        
        # ── ROW 2: Search progress (visible only when searching) ──
        self.search_bar = QProgressBar()
        self.search_bar.setRange(0, 100)
        self.search_bar.setValue(0)
        self.search_bar.setTextVisible(True)
        self.search_bar.setFixedHeight(18)
        self.search_bar.setFormat("Tìm server...")
        root.addWidget(self.search_bar)
        
        # ── ROW 3: Server connection info ──
        self.lbl_server = QLabel("Server: —")
        self.lbl_server.setFont(QFont("Segoe UI", 9))
        self.lbl_server.setObjectName("infoLabel")
        self.lbl_server.setFixedHeight(26)
        root.addWidget(self.lbl_server)
        
        # ── ROW 4: Camera preview ──
        cam_col = QVBoxLayout()
        cam_col.setSpacing(2)
        
        self.camera_preview = QLabel("📷 Camera")
        self.camera_preview.setFixedSize(480, 320)
        self.camera_preview.setAlignment(Qt.AlignCenter)
        self.camera_preview.setObjectName("camView")
        cam_col.addWidget(self.camera_preview, 0, Qt.AlignCenter)
        
        # Controls row under camera
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        ctrl.addStretch()

        self.lbl_camera_index = QLabel("Camera")
        self.lbl_camera_index.setFont(QFont("Segoe UI", 9))
        ctrl.addWidget(self.lbl_camera_index)

        self.spin_camera_index = QSpinBox()
        self.spin_camera_index.setRange(0, 10)
        self.spin_camera_index.setFixedSize(58, 28)
        self.spin_camera_index.setToolTip("Chọn camera index OpenCV")
        self.spin_camera_index.valueChanged.connect(self._on_camera_index_changed)
        ctrl.addWidget(self.spin_camera_index)

        self.combo_camera_backend = QComboBox()
        self.combo_camera_backend.addItem("Auto", "auto")
        self.combo_camera_backend.addItem("DSHOW", "dshow")
        self.combo_camera_backend.addItem("MSMF", "msmf")
        self.combo_camera_backend.addItem("Default", "default")
        self.combo_camera_backend.setFixedSize(92, 28)
        self.combo_camera_backend.setToolTip("Chọn backend OpenCV cho webcam")
        self.combo_camera_backend.currentIndexChanged.connect(self._on_camera_backend_changed)
        ctrl.addWidget(self.combo_camera_backend)
        
        self.btn_shoot = QPushButton("📸 Bắn")
        self.btn_shoot.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.btn_shoot.setFixedSize(120, 32)
        self.btn_shoot.setEnabled(False)
        self.btn_shoot.setObjectName("shootBtn")
        self.btn_shoot.clicked.connect(self._shoot)
        ctrl.addWidget(self.btn_shoot)
        
        self.lbl_stream = QLabel("Stream: OFF")
        self.lbl_stream.setFont(QFont("Segoe UI", 9))
        self.lbl_stream.setAlignment(Qt.AlignCenter)
        self.lbl_stream.setFixedWidth(100)
        ctrl.addWidget(self.lbl_stream)
        
        ctrl.addStretch()
        cam_col.addLayout(ctrl)
        root.addLayout(cam_col)
        
        # ── ROW 5: Send data (inline) ──
        sr = QHBoxLayout()
        sr.setSpacing(4)
        
        self.txt_send = QLineEdit()
        self.txt_send.setPlaceholderText("Gửi tới server...")
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
        
        # ── ROW 6: Log (fills remaining) ──
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 8))
        root.addWidget(self.log_text, 1)
    
    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #1e1e2e; }
            QWidget { color: #cdd6f4; }
            QFrame#hdr { background: #313244; border-radius: 6px; }
            QLabel#title { color: #f9e2af; }
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
            QSpinBox {
                background: #45475a; border: 1px solid #585b70;
                border-radius: 4px; padding: 2px 4px; color: #cdd6f4;
            }
            QComboBox {
                background: #45475a; border: 1px solid #585b70;
                border-radius: 4px; padding: 2px 4px; color: #cdd6f4;
            }
            QSpinBox:focus { border-color: #f9e2af; }
            QComboBox:focus { border-color: #f9e2af; }
            QLineEdit:focus { border-color: #f9e2af; }
            QPushButton {
                background: #45475a; border: 1px solid #585b70;
                border-radius: 4px; padding: 2px 8px; color: #cdd6f4;
            }
            QPushButton:hover { background: #585b70; border-color: #f9e2af; }
            QPushButton:pressed { background: #313244; }
            QPushButton:disabled { background: #313244; color: #585b70; border-color: #45475a; }
            QPushButton#shootBtn {
                background: #f38ba8; color: #1e1e2e;
                border: 2px solid #f38ba8; font-weight: bold;
            }
            QPushButton#shootBtn:hover { background: #eba0b3; border-color: #eba0b3; }
            QPushButton#shootBtn:disabled { background: #313244; color: #585b70; border-color: #45475a; }
            QTextEdit {
                background: #11111b; border: 1px solid #45475a;
                border-radius: 4px; padding: 2px; color: #a6e3a1;
            }
            QProgressBar {
                background: #45475a; border: 1px solid #585b70;
                border-radius: 4px; text-align: center; color: #cdd6f4;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #f9e2af, stop:1 #fab387);
                border-radius: 3px;
            }
        """)
    
    def _start_client(self, prior_port_id, camera_index, camera_backend):
        config_dir = os.path.dirname(os.path.abspath(__file__))
        self.client = MBT03ClientCore(
            prior_port_id=prior_port_id,
            camera_index=camera_index,
            camera_backend=camera_backend,
            config_dir=config_dir
        )
        self.client.log_signal.connect(self._on_log)
        self.client.status_signal.connect(self._on_status)
        self.client.connected_signal.connect(self._on_connected)
        self.client.disconnected_signal.connect(self._on_disconnected)
        self.client.port_id_changed_signal.connect(self._on_port_id_changed)
        self.client.shoot_sent_signal.connect(self._on_shoot_sent)
        self.client.shoot_image_sent_signal.connect(self._on_shoot_image_sent)
        self.client.streaming_started_signal.connect(self._on_streaming_started)
        self.client.streaming_stopped_signal.connect(self._on_streaming_stopped)
        self.client.camera_frame_signal.connect(self._on_camera_frame)

        self.spin_camera_index.blockSignals(True)
        self.spin_camera_index.setValue(self.client.camera_index)
        self.spin_camera_index.blockSignals(False)

        backend_pos = self.combo_camera_backend.findData(self.client.camera_backend)
        if backend_pos < 0:
            backend_pos = 0
        self.combo_camera_backend.blockSignals(True)
        self.combo_camera_backend.setCurrentIndex(backend_pos)
        self.combo_camera_backend.blockSignals(False)
        
        pid = self.client.prior_port_id
        port = PortMapping.get_port(pid)
        self.lbl_title.setText(f"📱 Client P{pid}")
        self.setWindowTitle(f"MBT03 Client - Prior Port {pid} (:{port})")
        self.search_start_time = time.time()
        self.client.start()
    
    @pyqtSlot(str)
    def _on_log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {msg}")
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    @pyqtSlot(str)
    def _on_status(self, status):
        self.lbl_status.setText(status)
        if "kết nối" in status.lower() and "ngắt" not in status.lower() and "đang kết nối" not in status.lower():
            self.dot.setStyleSheet("color:#a6e3a1;")
            self.search_bar.setVisible(False)
        elif "tìm" in status.lower():
            self.dot.setStyleSheet("color:#ffa500;")
            self.search_bar.setVisible(True)
            self.search_start_time = time.time()
        elif "ngắt" in status.lower():
            self.dot.setStyleSheet("color:#f38ba8;")
            self.search_bar.setVisible(True)
        else:
            self.dot.setStyleSheet("color:#ffa500;")
    
    @pyqtSlot(str)
    def _on_connected(self, server_info):
        self.lbl_server.setText(f"✅ {server_info}")
        self.btn_send.setEnabled(True)
        self.btn_shoot.setEnabled(True)
        self.search_bar.setVisible(False)
    
    @pyqtSlot()
    def _on_disconnected(self):
        self.lbl_server.setText("Server: —")
        self.btn_send.setEnabled(False)
        self.btn_shoot.setEnabled(False)
        self.lbl_stream.setText("Stream: OFF")
        self.lbl_stream.setStyleSheet("")
        self.search_bar.setVisible(True)
        self.search_start_time = time.time()
    
    @pyqtSlot(int)
    def _on_port_id_changed(self, new_id):
        port = PortMapping.get_port(new_id)
        self.lbl_title.setText(f"📱 Client P{new_id}")
        self.setWindowTitle(f"MBT03 Client - Prior Port {new_id} (:{port})")
    
    @pyqtSlot()
    def _on_shoot_sent(self):
        self.btn_shoot.setText("📸 ...")
        self.btn_shoot.setEnabled(False)
    
    @pyqtSlot()
    def _on_shoot_image_sent(self):
        self.btn_shoot.setText("📸 Bắn")
        self.btn_shoot.setEnabled(True)
    
    @pyqtSlot()
    def _on_streaming_started(self):
        self.lbl_stream.setText("🔴 LIVE")
        self.lbl_stream.setStyleSheet("color:#f38ba8; font-weight:bold;")
    
    @pyqtSlot()
    def _on_streaming_stopped(self):
        self.lbl_stream.setText("Stream: OFF")
        self.lbl_stream.setStyleSheet("")
    
    @pyqtSlot(object)
    def _on_camera_frame(self, frame):
        self._show_frame(frame)
    
    def _show_frame(self, frame):
        if frame is None:
            return
        try:
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(qimg)
            self.camera_preview.setPixmap(
                pix.scaled(self.camera_preview.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
            )
        except Exception:
            pass
    
    def _update_local_preview(self):
        if not hasattr(self, 'client'):
            return
        if self.client.is_streaming:
            return
        try:
            frame = self.client._capture_frame(480, 320)
            self._show_frame(frame)
        except Exception:
            pass
    
    def _shoot(self):
        if hasattr(self, 'client'):
            self.client.shoot()

    def _on_camera_index_changed(self, camera_index):
        if hasattr(self, 'client'):
            self.client.set_camera_index(camera_index)
            self.camera_preview.setPixmap(QPixmap())
            self.camera_preview.setText(f"📷 Camera {camera_index} ({self.client.camera_backend})")

    def _on_camera_backend_changed(self, _):
        if hasattr(self, 'client'):
            backend = self.combo_camera_backend.currentData()
            self.client.set_camera_backend(backend)
            self.camera_preview.setPixmap(QPixmap())
            self.camera_preview.setText(f"📷 Camera {self.client.camera_index} ({backend})")
    
    def _send_data(self):
        text = self.txt_send.text().strip()
        if not text:
            return
        if hasattr(self, 'client'):
            ok = self.client.send_data({'message': text, 'time': time.time()})
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
    
    def _update_search_progress(self):
        if hasattr(self, 'client') and self.client.is_connected:
            self.search_bar.setValue(100)
            return
        elapsed = time.time() - self.search_start_time
        pct = min(100, int((elapsed / Protocol.PRIOR_SEARCH_TIMEOUT) * 100))
        self.search_bar.setValue(pct)
        if pct < 100:
            rem = int(Protocol.PRIOR_SEARCH_TIMEOUT - elapsed)
            self.search_bar.setFormat(f"Tìm ưu tiên: {rem}s ({pct}%)")
        else:
            self.search_bar.setFormat("Tìm bất kỳ server...")
    
    def closeEvent(self, event):
        if hasattr(self, 'client'):
            self.client.stop()
        event.accept()


def main():
    prior_port_id = None
    camera_index = None
    camera_backend = None
    positional_args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    for arg in sys.argv[1:]:
        if arg.startswith("--camera-index="):
            try:
                camera_index = int(arg.split("=", 1)[1])
            except ValueError:
                print(f"Warning: invalid camera index '{arg}'. Using saved/default camera.")
        elif arg.startswith("--camera-backend="):
            camera_backend = arg.split("=", 1)[1]
        elif arg in ("--help", "-h"):
            print("Usage: python client_demo.py [prior_port_id] [camera_index]")
            print("       python client_demo.py [prior_port_id] --camera-index=N --camera-backend=auto|dshow|msmf|default")
            return

    if len(positional_args) >= 1:
        try:
            prior_port_id = int(positional_args[0])
            if prior_port_id not in PortMapping.MAP:
                print(f"Warning: port_id should be 1-4, got {prior_port_id}. Using default.")
                prior_port_id = None
        except ValueError:
            print(f"Warning: invalid port_id '{positional_args[0]}'. Using default.")

    if len(positional_args) >= 2 and camera_index is None:
        try:
            camera_index = int(positional_args[1])
        except ValueError:
            print(f"Warning: invalid camera index '{positional_args[1]}'. Using saved/default camera.")
    
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
    
    window = ClientDemoWindow(prior_port_id, camera_index, camera_backend)
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
