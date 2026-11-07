from pathlib import Path

import cv2
import numpy as np
from PyQt5 import QtGui, uic
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QDialog, QMessageBox

import config as cf
import scoring


class QuyKhongWindow(QDialog):
    Q0_SAMPLE_COUNT = cf.config_int(
        "calibration.sample_count", 3, minimum=1, maximum=20
    )
    Q0_UART_COMMAND = cf.config_str(
        "calibration.uart_command", "0Q000\n"
    )

    def __init__(self, p_num=1, servers=None, parent=None):
        super().__init__(parent)
        uic.loadUi(cf.DATA_DIR + "assets/qt/quy_khong.ui", self)
        self.setWindowTitle("Quy không")
        self.setWindowIcon(QtGui.QIcon(cf.DATA_DIR + "assets/images/icon.png"))
        self.setWindowModality(Qt.ApplicationModal)
        self.p_num = p_num
        self.servers = list(servers or [])
        self._stream_server = None
        self._current_server_index = -1
        self._current_stream_frame = None
        self._stream_available = False
        self._adjusting_camera = False

        self.Q0 = False
        self.Q0_values = []
        self.Q0_sizes = []
        self._q0_request = None
        self._q0_pending_server = None
        self._q0_start_timer = QTimer(self)
        self._q0_start_timer.setSingleShot(True)
        self._q0_start_timer.setTimerType(Qt.PreciseTimer)
        self._q0_start_timer.timeout.connect(self._send_q0_command)

        self._configure_ui()
        self._show_offline_image()

        parent_window = self.parent()
        if parent_window is not None and hasattr(parent_window, "q0_done_signal"):
            parent_window.q0_done_signal.connect(self._on_q0_done)

        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._update_frame)
        self._frame_timer.start(
            cf.config_int(
                "runtime.settings_frame_refresh_ms", 30, minimum=10, maximum=1000
            )
        )

    def _configure_ui(self):
        placeholder = self.client_combo.itemText(0) if self.client_combo.count() else "Chọn thiết bị"
        self.client_combo.clear()
        self.client_combo.addItems([placeholder] + [f"Bệ số {i}" for i in range(1, self.p_num + 1)])

        self.client_combo.currentIndexChanged.connect(self._on_client_changed)
        self.adjust_btn.clicked.connect(self._toggle_camera_adjustment)
        self.Q0_btn.clicked.connect(self._toggle_q0)
        self.close_window_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self._retry_q0)
        self.confirm_btn.clicked.connect(self._confirm_q0)
        self._update_q0_buttons()
        self.adjust_btn.setEnabled(False)
        self.adjust_btn.setCheckable(True)
        self.Q0_btn.setEnabled(False)
        self.Q0_btn.setCheckable(True)
        target_name = scoring.CLASS_NAMES.get(
            scoring.Q0_TARGET_CLASS_ID,
            f"class {scoring.Q0_TARGET_CLASS_ID}",
        )
        self.Q0_btn.setToolTip(
            f"Bắn {self.Q0_SAMPLE_COUNT} phát vào {target_name} "
            "để xác định Quy không."
        )

    def _on_client_changed(self, index):
        self._stop_stream()
        self._reset_controls()
        if index <= 0 or index > len(self.servers):
            return

        server = self.servers[index - 1]
        if not server.is_connected:
            return

        self._stream_server = server
        self._current_server_index = index - 1
        server.stream_frame_signal.connect(self._on_stream_frame)
        server.stream_state_signal.connect(self._on_stream_state_changed)
        server.shoot_image_signal.connect(self._on_q0_shoot_image)
        if not server.request_stream_start():
            self._stop_stream()
            self._reset_controls()
            return
        self._set_stream_available(True)

    def _on_stream_frame(self, frame):
        if (self._stream_available and self._stream_server is not None
                and self.sender() is self._stream_server and frame is not None):
            self._current_stream_frame = frame

    def _on_stream_state_changed(self, active):
        server = self._stream_server
        if server is not None and self.sender() is server:
            self._set_stream_available(active and server.is_connected)

    def _set_stream_available(self, available):
        self._stream_available = available
        self.adjust_btn.setEnabled(available)
        self.Q0_btn.setEnabled(available)
        if not available:
            self._current_stream_frame = None
            self._adjusting_camera = False
            self.adjust_btn.setChecked(False)
            self._reset_q0_round()
            self._show_offline_image()

    def _toggle_camera_adjustment(self):
        self._adjusting_camera = not self._adjusting_camera
        self.adjust_btn.setChecked(self._adjusting_camera)

    def _q0_ready(self):
        return self.Q0 and len(self.Q0_values) >= self.Q0_SAMPLE_COUNT

    def _update_q0_buttons(self):
        ready = self._q0_ready()
        self.close_window_btn.setVisible(not ready)
        self.cancel_btn.setVisible(ready)
        self.confirm_btn.setVisible(ready)

    def _reset_q0_round(self):
        self._cancel_q0_start()
        self.Q0 = False
        self.Q0_values.clear()
        self.Q0_sizes.clear()
        self._q0_request = None
        self.Q0_btn.setChecked(False)
        self._update_q0_buttons()

    def _toggle_q0(self):
        if self.Q0:
            self._reset_q0_round()
        else:
            self._start_q0_round()

    def _start_q0_round(self):
        self._reset_q0_round()
        server = self._stream_server
        if server is None or not server.is_connected or not server.send_uart_command("0F003\n"):
            return
        self.Q0 = True
        self.Q0_btn.setChecked(True)
        self._q0_pending_server = server
        self._q0_start_timer.start(300)

    def _retry_q0(self):
        if self._q0_ready():
            self._start_q0_round()

    def _cancel_q0_start(self):
        self._q0_start_timer.stop()
        self._q0_pending_server = None

    def _send_q0_command(self):
        server = self._q0_pending_server
        self._q0_pending_server = None
        if self.Q0 and server is not None and server is self._stream_server:
            if not server.is_connected or not server.send_uart_command(self.Q0_UART_COMMAND):
                self._reset_q0_round()

    def _on_q0_shoot_image(self, frame, _q0_data):
        if (not self.Q0 or self._q0_pending_server is not None
                or self._q0_request is not None or self._q0_ready()):
            return
        parent = self.parent()
        if parent is None or not hasattr(parent, "process_q0_calibration"):
            return
        self._q0_request = object()
        port_id = self._current_server_index + 1
        if not parent.process_q0_calibration(port_id, frame, self._q0_request):
            self._q0_request = None

    def _on_q0_done(self, result):
        if (not self.Q0 or result.get("port_id") != self._current_server_index + 1
                or self._q0_request is None or result.get("request_id") is not self._q0_request):
            return
        self._q0_request = None
        if not result.get("ok"):
            print(f"[Q0] Invalid shot ignored: {result.get('status', 'unknown')}")
            return
        q0 = result.get("q0")
        if q0 is None or not (0.0 <= q0[0] <= 1.0 and 0.0 <= q0[1] <= 1.0):
            print("[Q0] Shot center outside image; ignored")
            return
        self.Q0_values.append((float(q0[0]), float(q0[1])))
        self.Q0_sizes.append(int(result.get("target_size", 0)))
        self._update_q0_buttons()

    def _confirm_q0(self):
        if not self._q0_ready():
            return
        q0_x = sum(point[0] for point in self.Q0_values) / len(self.Q0_values)
        q0_y = sum(point[1] for point in self.Q0_values) / len(self.Q0_values)
        size = int(round(sum(self.Q0_sizes) / len(self.Q0_sizes))) if self.Q0_sizes else 0
        server = self._stream_server
        if server is None or not server.send_q0_to_client([q0_x, q0_y], size):
            QMessageBox.warning(self, "Quy 0", "Chưa gửi được kết quả Quy 0 đến súng đang chọn.")
            return
        port_id = self._current_server_index + 1
        parent = self.parent()
        if parent is not None and hasattr(parent, "_q0_calibrated"):
            parent._q0_calibrated[port_id] = {"q0": [q0_x, q0_y], "size": size}
        server.send_uart_command("0S000\n")
        print(f"[Q0] Port {port_id}: ({q0_x:.6f}, {q0_y:.6f}), size={size}")
        self._reset_q0_round()

    def _initial_q0(self):
        port_id = self._current_server_index + 1
        parent = self.parent()
        calibrated = getattr(parent, "_q0_calibrated", {}) if parent else {}
        q0 = calibrated.get(port_id, {}).get("q0", [0.5, 0.5])
        try:
            return (
                max(0.0, min(1.0, float(q0[0]))),
                max(0.0, min(1.0, float(q0[1]))),
            )
        except (TypeError, ValueError, IndexError):
            return 0.5, 0.5

    def _update_frame(self):
        if self._stream_available and self._stream_server is not None and not self._stream_server.is_connected:
            self._set_stream_available(False)
            return
        # Shoot images are calibration inputs only. Continue displaying the
        # latest live frame and overlay completed Q0 samples on top.
        frame = self._current_stream_frame
        if frame is None or not hasattr(self, "monkezusbcamera"):
            return
        display = frame.copy()
        height, width = display.shape[:2]

        if self._adjusting_camera:
            box_size = min(height, width) // 2
            center_x = width // 2
            center_y = int(height / 2.5)
            cv2.rectangle(
                display,
                (center_x - box_size // 2, center_y - box_size // 2),
                (center_x + box_size // 2, center_y + box_size // 2),
                (0, 0, 255),
                2,
            )

        if self.Q0:
            sample_count = getattr(self, "Q0_SAMPLE_COUNT", 3)
            for index in range(max(0, sample_count - len(self.Q0_values))):
                cv2.circle(display, (30 + index * 60, 30), 20, (255, 0, 0), -1)

            for sample_x, sample_y in self.Q0_values:
                point = (int(sample_x * width), int(sample_y * height))
                cv2.drawMarker(
                    display, point, (0, 255, 255), cv2.MARKER_CROSS, 16, 3
                )
        else:
            q0_x, q0_y = self._initial_q0()
            q0_point = (int(q0_x * width), int(q0_y * height))
            cv2.drawMarker(display, q0_point, (0, 255, 0), cv2.MARKER_CROSS, 22, 2)

        self.monkezusbcamera.set_image(display)

    def _reset_controls(self):
        self._current_server_index = -1
        self._set_stream_available(False)

    def _stop_stream(self):
        self._cancel_q0_start()
        server = self._stream_server
        self._stream_server = None
        self._stream_available = False
        self._current_stream_frame = None
        if server is None:
            return
        for signal, slot in (
            (server.stream_frame_signal, self._on_stream_frame),
            (server.stream_state_signal, self._on_stream_state_changed),
            (server.shoot_image_signal, self._on_q0_shoot_image),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        server.request_stream_stop()

    def done(self, result):
        self._frame_timer.stop()
        self._stop_stream()
        parent = self.parent()
        if parent is not None and hasattr(parent, "q0_done_signal"):
            try:
                parent.q0_done_signal.disconnect(self._on_q0_done)
            except (TypeError, RuntimeError):
                pass
        self._reset_controls()
        super().done(result)

    def _show_offline_image(self):
        if not hasattr(self, "monkezusbcamera"):
            return
        camera = self.monkezusbcamera
        base = Path(cf.DATA_DIR)
        relative = Path("monkez_assets/images/CameraOffline.png")
        for path in (base / relative, base / "MonkezCustomWidgets" / relative):
            try:
                image = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
            except (OSError, cv2.error):
                continue
            if image is not None:
                camera.set_image(image)
                return
        camera.image = None
        camera.set_image(None)
