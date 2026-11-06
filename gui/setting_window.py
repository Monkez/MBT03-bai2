import os

import cv2
from PyQt5 import QtGui, uic
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QAbstractSpinBox, QDialog, QGridLayout, QLabel, QDoubleSpinBox

import config as cf
import scoring
from gui.target_timing import get_target_times, save_timing_settings, validate_times, hardware_delay_time, TARGET_LABELS, MAX_SETTING_SECONDS
from gui.client_widget import TARGET_IMAGE_FILES
from gui.shooting_session import TARGET_CLASS_SEQUENCE


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
        self._q0_pending_server = None
        self._q0_start_timer = QTimer(self)
        self._q0_start_timer.setSingleShot(True)
        self._q0_start_timer.setTimerType(Qt.PreciseTimer)
        self._q0_start_timer.timeout.connect(self._send_q0_command)

        self._configure_ui()
        self._configure_target_times()
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
        self.comport_combo.addItem("Không sử dụng LoRa", userData="")
        selected_index = 0
        for port in self.lora_controller.available_ports():
            device = port["device"]
            description = port["description"]
            label = f"{device} - {description}" if description else device
            self.comport_combo.addItem(label, userData=device)
            if device == current_port:
                selected_index = self.comport_combo.count() - 1
        self.comport_combo.setCurrentIndex(selected_index)

    def _configure_target_times(self):
        self.channel_combo.clear()
        for channel in (1, 2, 3):
            self.channel_combo.addItem(f"Kênh {channel}", userData=channel)
        self._initial_channel = cf.config_int("shooting.control_channel", 1, minimum=1, maximum=3)
        self.channel_combo.setCurrentIndex(self._initial_channel - 1)
        self.channel_combo.setToolTip("Lưu lựa chọn kênh; chức năng điều khiển theo kênh sẽ bổ sung sau.")
        self._initial_times = get_target_times()
        grid = QGridLayout(self.time_setting_frame)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.time_setting_frame.setStyleSheet("QFrame#time_setting_frame {background: #f8fafc; border: 1px solid #dbe3eb; border-radius: 10px;}")
        title = QLabel("THỜI GIAN HIỆN / ẨN BIA", self.time_setting_frame)
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #24364b;")
        grid.addWidget(title, 0, 0, 1, 5)
        hint = QLabel("Mốc từ BẮT ĐẦU · giây · cho phép nhiều bia cùng hiện", self.time_setting_frame)
        hint.setStyleSheet("font-size: 11px; color: #64748b;")
        grid.addWidget(hint, 1, 0, 1, 5)
        for row, text in ((4, "Hiện"), (5, "Ẩn")):
            grid.addWidget(QLabel(text, self.time_setting_frame), row, 0)
        self.target_time_inputs = []
        for column, (target, label, item) in enumerate(zip(TARGET_CLASS_SEQUENCE, TARGET_LABELS, self._initial_times), 1):
            thumbnail = QLabel(self.time_setting_frame)
            thumbnail.setAlignment(Qt.AlignCenter)
            image = QtGui.QPixmap(os.path.join(cf.DATA_DIR, "assets", "signs", TARGET_IMAGE_FILES[target]))
            thumbnail.setPixmap(image.scaled(80, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            grid.addWidget(thumbnail, 2, column)
            name = QLabel(label, self.time_setting_frame)
            name.setAlignment(Qt.AlignCenter)
            name.setStyleSheet("font-size: 11px; font-weight: bold; color: #334155;")
            grid.addWidget(name, 3, column)
            inputs = {}
            for row, key, action in ((4, "show_seconds", "Hiện"), (5, "hide_seconds", "Ẩn")):
                field = QDoubleSpinBox(self.time_setting_frame)
                field.setRange(0, MAX_SETTING_SECONDS)
                field.setDecimals(1)
                field.setSingleStep(1)
                field.setValue(item[key])
                field.setAlignment(Qt.AlignCenter)
                field.setButtonSymbols(QAbstractSpinBox.NoButtons)
                field.setMinimumSize(80, 30)
                field.setAccessibleName(f"{action} {label} ở giây")
                field.setStyleSheet("QDoubleSpinBox {background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 3px; font-size: 13px;} QDoubleSpinBox:focus {border: 1px solid #008ed6;}")
                field.valueChanged.connect(self._validate_target_times)
                grid.addWidget(field, row, column)
                inputs[key] = field
            self.target_time_inputs.append(inputs)
            grid.setColumnStretch(column, 1)
        self.timing_error_label = QLabel(self.time_setting_frame)
        self.timing_error_label.setWordWrap(True)
        self.timing_error_label.setStyleSheet("font-size: 11px; color: #b91c1c;")
        grid.addWidget(self.timing_error_label, 6, 0, 1, 5)
        self._validate_target_times()
        self.setMinimumWidth(max(self.minimumWidth(), 540))

    def _target_time_values(self):
        return [{key: field.value() for key, field in pair.items()} for pair in self.target_time_inputs]

    def _validate_target_times(self):
        try:
            validate_times(self._target_time_values(), hardware_delay_time())
        except ValueError as error:
            self.timing_error_label.setText(str(error))
            return False
        self.timing_error_label.clear()
        return True

    def _on_client_changed(self, index):
        self._stop_stream()
        self._reset_controls()
        if index <= 0 or index > len(self.servers):
            self._show_offline_image()
            return

        server = self.servers[index - 1]
        if not server.is_connected:
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
        self._cancel_q0_start()
        self.Q0 = not self.Q0
        self.Q0_btn.setChecked(self.Q0)
        self.Q0_values = []
        self.Q0_sizes = []
        self._q0_processing = False
        if self.Q0 and self._stream_server is not None:
            if not self._stream_server.send_uart_command("0F003\n"):
                self.Q0 = False
                self.Q0_btn.setChecked(False)
                return
            self._q0_pending_server = self._stream_server
            self._q0_start_timer.start(300)

    def _cancel_q0_start(self):
        self._q0_start_timer.stop()
        self._q0_pending_server = None

    def _send_q0_command(self):
        server = self._q0_pending_server
        self._q0_pending_server = None
        if self.Q0 and server is not None and server is self._stream_server and server.is_connected:
            server.send_uart_command(self.Q0_UART_COMMAND)

    def _on_q0_shoot_image(self, frame, _q0_data):
        if (not self.Q0 or self._q0_pending_server is not None
                or self._q0_processing or len(self.Q0_values) >= self.Q0_SAMPLE_COUNT):
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

        if not self._validate_target_times():
            return
        times = self._target_time_values()
        channel = self.channel_combo.currentData()
        try:
            save_timing_settings(times, channel)
        except (OSError, ValueError) as error:
            self.timing_error_label.setText(f"Chưa lưu được cài đặt: {error}")
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
        self._cancel_q0_start()
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
