import os

from PyQt5 import QtGui, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractSpinBox, QDialog, QGridLayout, QLabel, QDoubleSpinBox

import config as cf
from gui.target_timing import (
    MAX_SETTING_SECONDS, TARGET_LABELS, get_target_times, hardware_delay_time,
    save_control_channel, save_timing_settings, validate_times,
)
from gui.client_widget import TARGET_IMAGE_FILES
from gui.shooting_session import TARGET_CLASS_SEQUENCE


class SettingWindow(QDialog):
    def __init__(self, lora_controller=None, parent=None):
        super().__init__(parent)
        uic.loadUi(cf.DATA_DIR + "assets/qt/setting.ui", self)
        self.setWindowTitle("Cài đặt")
        self.setWindowIcon(QtGui.QIcon(cf.DATA_DIR + "assets/images/icon.png"))
        self.setWindowModality(Qt.ApplicationModal)
        self.lora_controller = lora_controller
        self._lora_applying = False

        self._configure_ui()
        self._configure_target_times()
        self._configure_lora_ports()
        self.resize(self.width(), max(self.height(), self.sizeHint().height()))

    def _configure_ui(self):
        self.close_window_btn.clicked.connect(self._close_settings)
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
            thumbnail.setFixedHeight(58)
            image = QtGui.QPixmap(os.path.join(cf.DATA_DIR, "assets", "signs", TARGET_IMAGE_FILES[target]))
            thumbnail.setPixmap(image.scaled(100, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
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

    def _close_settings(self):
        if self._lora_applying or not self._validate_target_times():
            return
        try:
            save_timing_settings(self._target_time_values())
        except (OSError, ValueError) as error:
            self._set_timing_error(f"Chưa lưu được cài đặt: {error}")
            return
        self.accept()

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
        self._set_lora_applying(True)
        if not controller.request_connection(port, channel, force_channel=True):
            self._on_lora_configuration_finished(False, "Chưa gửi được yêu cầu đặt LoRa")

    def _set_lora_applying(self, applying):
        self._lora_applying = applying
        for widget in (self.lora_accept_btn, self.comport_combo, self.channel_combo,
                       self.close_window_btn):
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
        super().done(result)
