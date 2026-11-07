import os
from pathlib import Path

import cv2
import numpy as np
from PyQt5 import QtGui, uic
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QAbstractSpinBox, QDialog, QGridLayout, QLabel, QDoubleSpinBox, QMessageBox

import config as cf
import scoring
from gui.target_timing import (
    MAX_SETTING_SECONDS, TARGET_LABELS, get_target_times, hardware_delay_time,
    save_control_channel, save_timing_settings, validate_times,
)
from gui.client_widget import TARGET_IMAGE_FILES
from gui.shooting_session import TARGET_CLASS_SEQUENCE


class SettingWindow(QDialog):
    Q0_SAMPLE_COUNT = cf.config_int(
        "calibration.sample_count", 3, minimum=1, maximum=20
    )
    Q0_UART_COMMAND = cf.config_str(
        "calibration.uart_command", "0Q000\n"
    )

    def __init__(self, p_num=1, servers=None, lora_controller=None, parent=None, *, calibration_active=False):
        super().__init__(parent)
        uic.loadUi(cf.DATA_DIR + "assets/qt/setting.ui", self)
        self.setWindowTitle("Cài đặt")
        self.setWindowIcon(QtGui.QIcon(cf.DATA_DIR + "assets/images/icon.png"))
        self.setWindowModality(Qt.ApplicationModal)

        self.p_num = p_num
        self.servers = list(servers or [])
        self.lora_controller = lora_controller
        self._lora_applying = False
        self._calibration_active = calibration_active
        self.calibration_target_suspended = False
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
        self.close_window_btn.clicked.connect(self._close_settings)
        self.cancel_btn.clicked.connect(self._retry_q0)
        self.confirm_btn.clicked.connect(self._confirm_q0)
        self._update_q0_buttons()
        self.lora_accept_btn.clicked.connect(self.apply_lora_selection)
        self.lora_accept_btn.setEnabled(self.lora_controller is not None)
        self.lora_log_label.setTextFormat(Qt.PlainText)
        self.lora_log_label.setWordWrap(True)
        self._show_lora_message("")
        if self.lora_controller is not None:
            self.lora_controller.configuration_finished.connect(self._on_lora_configuration_finished)
            self.lora_controller.connection_changed.connect(self._on_lora_connection_changed)
            self.lora_controller.command_finished.connect(self._on_lora_command_finished)
            self._show_lora_message(self.lora_controller.connection_error)

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
        if isinstance(current_port, str) and current_port and selected_index == 0:
            self.comport_combo.addItem(f"{current_port} (chưa kết nối)", userData=current_port)
            selected_index = self.comport_combo.count() - 1
        self.comport_combo.setCurrentIndex(selected_index)

    def _configure_target_times(self):
        self.channel_combo.clear()
        for channel in (1, 2, 3):
            self.channel_combo.addItem(f"Kênh {channel}", userData=channel)
        self._initial_channel = cf.config_int("shooting.control_channel", 1, minimum=1, maximum=3)
        self.channel_combo.setCurrentIndex(self._initial_channel - 1)
        self.channel_combo.setToolTip("Bấm ĐẶT để áp dụng cổng LoRa và gửi lại kênh cho E32.")
        self._initial_times = get_target_times()
        grid = QGridLayout(self.time_setting_frame)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.time_setting_frame.setStyleSheet("QFrame#time_setting_frame {background: #f8fafc; border: 1px solid #dbe3eb; border-radius: 10px;}")
        title = QLabel("THỜI GIAN HIỆN / ẨN BIA", self.time_setting_frame)
        title.setStyleSheet("background: transparent; font-size: 13px; font-weight: bold; color: #24364b;")
        grid.addWidget(title, 0, 0, 1, 5)
        for row, text in ((3, "Hiện"), (4, "Ẩn")):
            row_label = QLabel(text, self.time_setting_frame)
            row_label.setStyleSheet("background: transparent;")
            grid.addWidget(row_label, row, 0)
        self.target_time_inputs = []
        for column, (target, label, item) in enumerate(zip(TARGET_CLASS_SEQUENCE, TARGET_LABELS, self._initial_times), 1):
            thumbnail = QLabel(self.time_setting_frame)
            thumbnail.setStyleSheet("background-color: #ffffff;")
            thumbnail.setAlignment(Qt.AlignCenter)
            image = QtGui.QPixmap(os.path.join(cf.DATA_DIR, "assets", "signs", TARGET_IMAGE_FILES[target]))
            thumbnail.setPixmap(image.scaled(80, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            grid.addWidget(thumbnail, 1, column)
            name = QLabel(label, self.time_setting_frame)
            name.setAlignment(Qt.AlignCenter)
            name.setStyleSheet("background: transparent; font-size: 11px; font-weight: bold; color: #334155;")
            grid.addWidget(name, 2, column)
            inputs = {}
            for row, key, action in ((3, "show_seconds", "Hiện"), (4, "hide_seconds", "Ẩn")):
                field = QDoubleSpinBox(self.time_setting_frame)
                field.setRange(0, MAX_SETTING_SECONDS)
                field.setDecimals(1)
                field.setSingleStep(1)
                if target == 3 and key == "hide_seconds":
                    field.setToolTip("Mốc ẩn tính từ đầu bài, cùng cách nhập với các bia khác. Thời gian chạy 8C = Ẩn − Hiện; giới hạn chờ từ @444# = Ẩn − Hiện + 4 giây. Ví dụ Hiện 64, Ẩn 80 thì tối đa 20 giây; nếu bia gập trước thì kết thúc sau 2 giây.")
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
        self.timing_error_label.setStyleSheet("background: transparent; font-size: 11px; color: #b91c1c;")
        grid.addWidget(self.timing_error_label, 5, 0, 1, 5)
        self._validate_target_times()
        self.setMinimumWidth(max(self.minimumWidth(), 540))

    def _target_time_values(self):
        return [{key: field.value() for key, field in pair.items()} for pair in self.target_time_inputs]

    def _validate_target_times(self):
        try:
            validate_times(self._target_time_values(), hardware_delay_time())
        except ValueError as error:
            self._set_timing_error(str(error))
            return False
        self._set_timing_error("")
        return True

    def _set_timing_error(self, message):
        self.timing_error_label.setText(message)
        self.timing_error_label.setVisible(bool(message))

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
        if self._q0_ready() and not self._lora_applying:
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

    def _close_settings(self):
        if self._lora_applying or self._q0_ready() or not self._validate_target_times():
            return
        try:
            save_timing_settings(self._target_time_values())
        except (OSError, ValueError) as error:
            self._set_timing_error(f"Chưa lưu được cài đặt: {error}")
            return
        self.accept()

    def _confirm_q0(self):
        if not self._q0_ready() or self._lora_applying:
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

    def apply_lora_selection(self):
        controller = self.lora_controller
        if controller is None or self._lora_applying:
            return
        port = self.comport_combo.currentData() or ""
        channel = self.channel_combo.currentData()
        self._show_lora_message("")
        try:
            save_control_channel(channel)
        except (OSError, ValueError) as error:
            self._show_lora_message(f"Chưa lưu được kênh LoRa: {error}")
            return
        if self._calibration_active and (port != (controller.port_name or "") or channel != controller.channel):
            if controller.port_name and not self.calibration_target_suspended:
                controller.send_command(cf.config_str("calibration.target_lower_command", "@112#"))
            self.calibration_target_suspended = True
        self._set_lora_applying(True)
        if not controller.request_connection(port, channel, force_channel=True):
            self._on_lora_configuration_finished(False, "Chưa gửi được yêu cầu đặt LoRa")

    def _set_lora_applying(self, applying):
        self._lora_applying = applying
        for widget in (self.lora_accept_btn, self.comport_combo, self.channel_combo,
                       self.confirm_btn, self.cancel_btn, self.close_window_btn):
            widget.setEnabled(not applying)

    def _show_lora_message(self, message, *, warning=False):
        colors = ("#fffbeb", "#a16207", "#fde68a") if warning else ("#fef2f2", "#991b1b", "#fecaca")
        background, foreground, border = colors
        self.lora_log_label.setStyleSheet(
            f"QLabel {{ background: {background}; color: {foreground}; border: 1px solid {border}; "
            "border-radius: 5px; padding: 5px 8px; font-size: 12px; }"
        )
        self.lora_log_label.setText(message.split(": ", 1)[0])
        self.lora_log_label.setToolTip(message)
        self.lora_log_label.setVisible(bool(message))

    def _on_lora_connection_changed(self, _connected, _message):
        if not self._lora_applying:
            self._show_lora_message(self.lora_controller.connection_error)

    def _on_lora_command_finished(self, command, success, attempts):
        controller = self.lora_controller
        if self._lora_applying or not controller.port_name:
            return
        error = controller.connection_error
        if not success and not error:
            error = f"LoRa không phản hồi {command}" if attempts else f"Chưa gửi được {command}"
        self._show_lora_message(error)

    def _on_lora_configuration_finished(self, success, message):
        if not self._lora_applying:
            return
        self._set_lora_applying(False)
        if success and not self.lora_controller.port_name:
            self._show_lora_message("Không sử dụng LoRa", warning=True)
        else:
            self._show_lora_message("" if success else message)
        if success and self.calibration_target_suspended and self.lora_controller.port_name:
            self.lora_controller.send_command(cf.config_str("calibration.target_raise_command", "@114#"))
            self.calibration_target_suspended = False

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
        if self._lora_applying:
            return
        if self.lora_controller is not None:
            for signal, slot in (
                (self.lora_controller.configuration_finished, self._on_lora_configuration_finished),
                (self.lora_controller.connection_changed, self._on_lora_connection_changed),
                (self.lora_controller.command_finished, self._on_lora_command_finished),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
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
