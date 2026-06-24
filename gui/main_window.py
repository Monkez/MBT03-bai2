import random
import time

from PyQt5 import QtGui, uic
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QMainWindow

import config as cf
from gui.client_widget import ClientWidget
from gui.option_window import OptionWindow
from gui.setting_window import SettingWindow


class StartupCancelled(Exception):
    pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        option_dialog = OptionWindow(self)
        option_dialog.setWindowModality(Qt.ApplicationModal)
        if option_dialog.exec_() != option_dialog.Accepted or not option_dialog.start:
            raise StartupCancelled()

        uic.loadUi(cf.DATA_DIR + "assets/qt/main.ui", self)
        self.setWindowIcon(QtGui.QIcon(cf.DATA_DIR + "assets/images/icon.png"))

        self.options = option_dialog
        self.p_num = option_dialog.p_num
        self.testing = False
        self.client_widgets = []
        self._start_button_text = self.start_btn.text()
        self._test_start_time = 0.0
        self._test_duration_seconds = self._read_test_duration_seconds()

        self._configure_main_ui()
        self._create_client_widgets()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_app)
        self.timer.start(1000)

    def _configure_main_ui(self):
        self.setting_btn.clicked.connect(self.open_setting_window)
        self.start_btn.clicked.connect(self.start_btn_clicked)

    def _create_client_widgets(self):
        positions = self._client_positions(self.p_num)
        target_layout_mode = "two_pedestals" if self.p_num == 2 else "default"
        for index in range(self.p_num):
            widget = ClientWidget(index + 1, self, target_layout_mode=target_layout_mode)
            widget.score_speak_requested.connect(self.request_score_speak)
            self.client_widgets.append(widget)
            row, col = positions[index]
            self.client_grid_layout.addWidget(widget, row, col)

    def _client_positions(self, count):
        if count == 1:
            return [(0, 0)]
        if count == 2:
            return [(0, 0), (0, 1)]
        return [(0, 0), (0, 1), (1, 0), (1, 1)][:count]

    def start_btn_clicked(self):
        if self.testing:
            self.stop_test()
        else:
            self.start_test()

    def start_test(self):
        self.testing = True
        self._test_start_time = time.monotonic()
        self._set_start_button_active(True)
        self.update_app()
        for widget in self.client_widgets:
            widget.start_test()

    def stop_test(self):
        self.testing = False
        self._set_start_button_active(False)
        self.start_btn.setText(self._start_button_text)
        for widget in self.client_widgets:
            widget.stop_test()

    def update_app(self):
        if not self.testing:
            return

        elapsed = int(time.monotonic() - self._test_start_time)
        remaining = max(0, self._test_duration_seconds - elapsed)
        self.start_btn.setText(f"KẾT THÚC ({remaining}s)")
        if remaining <= 0:
            self.stop_test()

    def _read_test_duration_seconds(self):
        time_edit = getattr(self.options, "time_edit", None)
        if time_edit is not None:
            try:
                return max(1, int(time_edit.text()))
            except (TypeError, ValueError):
                pass
        return 60

    def _set_start_button_active(self, active):
        if hasattr(self.start_btn, "setChecked"):
            self.start_btn.setChecked(active)

    def open_setting_window(self):
        dialog = SettingWindow(p_num=self.p_num, parent=self)
        dialog.exec_()

    def request_score_speak(self, port_id):
        return

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_D and self.client_widgets:
            widget = self.client_widgets[0]
            target = random.randrange(4)
            widget.record_shot(target, random.uniform(0.25, 0.75), random.uniform(0.25, 0.75), True)
            event.accept()
            return
        super().keyPressEvent(event)
