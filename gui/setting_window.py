import os

import cv2
from PyQt5 import QtGui, uic
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QDialog

import config as cf
import scoring


class SettingWindow(QDialog):
    Q0_SAMPLE_COUNT = cf.config_int(
        "calibration.sample_count", 3, minimum=1, maximum=20
    )
    Q0_UART_COMMAND = cf.config_str(
        "calibration.uart_command", "0Q000\n"
    )

    def __init__(self, p_num=1, servers=None, lora_controller=None, parent=None):
        super().__init__(parent)
        uic.loadUi(cf.DATA_DIR + "assets/qt/setting.ui", self)
        self.setWindowIcon(QtGui.QIcon(cf.DATA_DIR + "assets/images/icon.png"))
        self.setWindowModality(Qt.ApplicationModal)

        self.p_num = p_num
        self.servers = list(servers or [])
        self.lora_controller = lora_controller
        self._stream_server = None
        self._current_server_index = -1
        self._current_stream_frame = None
        self._adjusting_camera = False

        self.Q0 = False
        self.Q0_values = []
        self.Q0_sizes = []
        self._q0_processing = False

        self._configure_ui()
        self._configure_lora_ports()
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
        self.cancel_btn.clicked.connect(self.reject)
        self.confirm_btn.clicked.connect(self._confirm_settings)

        self.adjust_btn.setEnabled(False)
        self.adjust_btn.setStyleSheet("color: #666666;")
        self.adjust_btn.setCheckable(True)
        self.Q0_btn.setEnabled(False)
        self.Q0_btn.setStyleSheet("color: #666666;")
        self.Q0_btn.setCheckable(True)
        target_name = scoring.CLASS_NAMES.get(
            scoring.Q0_TARGET_CLASS_ID,
            f"class {scoring.Q0_TARGET_CLASS_ID}",
        )
        self.Q0_btn.setToolTip(
            f"Bắn {self.Q0_SAMPLE_COUNT} phát vào {target_name} "
            "để xác định Quy không."
        )

    def _configure_lora_ports(self):
        if not hasattr(self, "comport_combo") or self.lora_controller is None:
            return
        current_port = self.lora_controller.port_name
        self.comport_combo.clear()
        self.comport_combo.addItem("Không sử dụng LoRa", "")
        selected_index = 0
        for port in self.lora_controller.available_ports():
            device = port["device"]
            description = port["description"]
            label = f"{device} - {description}" if description else device
            self.comport_combo.addItem(label, device)
            if device == current_port:
                selected_index = self.comport_combo.count() - 1
        self.comport_combo.setCurrentIndex(selected_index)

    def _on_client_changed(self, index):
        self._stop_stream()
        if index <= 0 or index > len(self.servers):
            self._reset_controls()
            self._show_offline_image()
            return

        server = self.servers[index - 1]
        if not server.is_connected:
            self._reset_controls()
            self._show_offline_image()
            return

        self._stream_server = server
        self._current_server_index = index - 1
        server.stream_frame_signal.connect(self._on_stream_frame)
        server.stream_state_signal.connect(self._on_stream_state_changed)
        server.shoot_image_signal.connect(self._on_q0_shoot_image)
        if not server.request_stream_start():
            self._stop_stream()
            self._reset_controls()
            self._show_offline_image()
            return
        self.adjust_btn.setEnabled(True)
        self.adjust_btn.setStyleSheet("")
        self.Q0_btn.setEnabled(True)
        self.Q0_btn.setStyleSheet("")

    def _on_stream_frame(self, frame):
        if frame is not None:
            self._current_stream_frame = frame

    def _on_stream_state_changed(self, active):
        if not active:
            self._current_stream_frame = None
            self._show_offline_image()

    def _toggle_camera_adjustment(self):
        self._adjusting_camera = not self._adjusting_camera
        self.adjust_btn.setChecked(self._adjusting_camera)

    def _toggle_q0(self):
        self.Q0 = not self.Q0
        self.Q0_btn.setChecked(self.Q0)
        self.Q0_values = []
        self.Q0_sizes = []
        self._q0_processing = False
        if self.Q0 and self._stream_server is not None:
            self._stream_server.send_uart_command(self.Q0_UART_COMMAND)

    def _on_q0_shoot_image(self, frame, _q0_data):
        if not self.Q0 or self._q0_processing or len(self.Q0_values) >= self.Q0_SAMPLE_COUNT:
            return
        parent = self.parent()
        if parent is None or not hasattr(parent, "process_q0_calibration"):
            return
        self._q0_processing = True
        port_id = self._current_server_index + 1
        if not parent.process_q0_calibration(port_id, frame):
            self._q0_processing = False

    def _on_q0_done(self, result):
        if result.get("port_id") != self._current_server_index + 1 or not self.Q0:
            return
        self._q0_processing = False
        if not result.get("ok"):
            print(f"[Q0] Invalid shot ignored: {result.get('status', 'unknown')}")
            return
        q0 = result.get("q0")
        if q0 is None or not (0.0 <= q0[0] <= 1.0 and 0.0 <= q0[1] <= 1.0):
            print("[Q0] Shot center outside image; ignored")
            return
        self.Q0_values.append((float(q0[0]), float(q0[1])))
        self.Q0_sizes.append(int(result.get("target_size", 0)))

    def _confirm_settings(self):
        if self.Q0 and len(self.Q0_values) < self.Q0_SAMPLE_COUNT:
            print(
                f"[Q0] Need {self.Q0_SAMPLE_COUNT} valid shots; "
                f"received {len(self.Q0_values)}"
            )
            return

        self._apply_lora_selection()
        if not self.Q0:
            self.accept()
            return

        q0_x = sum(point[0] for point in self.Q0_values) / len(self.Q0_values)
        q0_y = sum(point[1] for point in self.Q0_values) / len(self.Q0_values)
        size = int(round(sum(self.Q0_sizes) / len(self.Q0_sizes))) if self.Q0_sizes else 0
        port_id = self._current_server_index + 1
        parent = self.parent()
        if parent is not None and hasattr(parent, "_q0_calibrated"):
            parent._q0_calibrated[port_id] = {
                "q0": [q0_x, q0_y],
                "size": size,
            }
        if self._stream_server is not None:
            self._stream_server.send_q0_to_client([q0_x, q0_y], size)
        print(f"[Q0] Bệ {port_id}: ({q0_x:.6f}, {q0_y:.6f}), size={size}")
        self.Q0 = False
        self.accept()

    def _apply_lora_selection(self):
        if self.lora_controller is None or not hasattr(self, "comport_combo"):
            return
        selected_port = self.comport_combo.currentData() or ""
        if selected_port:
            self.lora_controller.connect_port(selected_port)
        else:
            self.lora_controller.disconnect_port()

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
        self._current_stream_frame = None
        self._adjusting_camera = False
        self.Q0 = False
        self.Q0_values = []
        self.Q0_sizes = []
        self._q0_processing = False
        self.adjust_btn.setChecked(False)
        self.Q0_btn.setChecked(False)
        self.adjust_btn.setEnabled(False)
        self.Q0_btn.setEnabled(False)
        self.adjust_btn.setStyleSheet("color: #666666;")
        self.Q0_btn.setStyleSheet("color: #666666;")

    def _stop_stream(self):
        server = self._stream_server
        self._stream_server = None
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
        path = os.path.join(
            cf.DATA_DIR,
            "MonkezCustomWidgets",
            "monkez_assets",
            "images",
            "CameraOffline.png",
        )
        image = cv2.imread(path, cv2.IMREAD_COLOR) if os.path.exists(path) else None
        if image is not None:
            self.monkezusbcamera.set_image(image)
