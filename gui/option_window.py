from functools import partial

from PyQt5 import QtGui, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog

import config as cf


OPTION_ACTIVE_STYLE = """
PushButton, QPushButton {
    color: white;
    background-color: rgb(0, 153, 0);
    border-radius: 5px;
}
"""

OPTION_INACTIVE_STYLE = """
PushButton, QPushButton {
    color: black;
    background-color: rgb(255, 255, 255);
    border-radius: 5px;
}
"""


class OptionWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(cf.DATA_DIR + "assets/qt/start_window.ui", self)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowIcon(QtGui.QIcon(cf.DATA_DIR + "assets/images/icon.png"))
        self.start = False
        self.p_num = 1

        self.p_num_btns = [
            self.p_num1_btn,
            self.p_num2_btn,
            self.p_num3_btn,
            self.p_num4_btn,
        ]
        for index, btn in enumerate(self.p_num_btns, start=1):
            btn.clicked.connect(partial(self.p_num_btn_clicked, index))

        self.start_btn.clicked.connect(self.start_btn_clicked)
        self.p_num_btn_clicked(1)

    def p_num_btn_clicked(self, stt):
        self.p_num = stt
        for index, btn in enumerate(self.p_num_btns, start=1):
            self._set_option_button_selected(btn, index == stt)

    def _set_option_button_selected(self, btn, selected):
        if hasattr(btn, "setCheckable"):
            btn.setCheckable(True)
        if hasattr(btn, "setChecked"):
            btn.setChecked(selected)

        is_monkez_button = all(
            hasattr(btn, attr)
            for attr in ("setActiveColor", "setDeactiveColor", "setTextColor")
        )
        if not is_monkez_button:
            btn.setStyleSheet(OPTION_ACTIVE_STYLE if selected else OPTION_INACTIVE_STYLE)

    def start_btn_clicked(self):
        self.start = True
        self.accept()
