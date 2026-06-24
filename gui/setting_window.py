import os

import cv2
from PyQt5 import QtGui, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog

import config as cf


class SettingWindow(QDialog):
    def __init__(self, p_num=1, parent=None):
        super().__init__(parent)
        uic.loadUi(cf.DATA_DIR + "assets/qt/setting.ui", self)
        self.setWindowIcon(QtGui.QIcon(cf.DATA_DIR + "assets/images/icon.png"))
        self.setWindowModality(Qt.ApplicationModal)

        self.p_num = p_num
        self._configure_ui()
        self._show_offline_image()

    def _configure_ui(self):
        placeholder = self.client_combo.itemText(0) if self.client_combo.count() else "Chọn thiết bị"
        self.client_combo.clear()
        self.client_combo.addItems([placeholder] + [f"Bệ số {i}" for i in range(1, self.p_num + 1)])

        self.client_combo.currentIndexChanged.connect(self._on_client_changed)
        self.cancel_btn.clicked.connect(self.reject)
        self.confirm_btn.clicked.connect(self.accept)

    def _on_client_changed(self):
        return

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
        if os.path.exists(path):
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is not None:
                self.monkezusbcamera.set_image(image)
