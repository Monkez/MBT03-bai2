import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox

import config as cf
from gui.main_window import MainWindow, StartupCancelled


def run_app():
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    except Exception:
        pass

    app = QApplication(sys.argv)
    icon_path = os.path.join(cf.DATA_DIR, "assets", "images", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    try:
        main_window = MainWindow()
        main_window.showMaximized()
        return app.exec_()
    except StartupCancelled:
        return 0
    except Exception as exc:
        QMessageBox.critical(None, "MBT-03", f"Ứng dụng gặp lỗi:\n{exc}")
        raise


if __name__ == "__main__":
    sys.exit(run_app())

