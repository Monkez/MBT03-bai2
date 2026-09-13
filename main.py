import os
import sys
import logging
from logging.handlers import RotatingFileHandler

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox

import config as cf
from gui.main_window import MainWindow, StartupCancelled


def _configure_server_logging():
    """Persist transport diagnostics even when the GUI filters console output."""
    logger = logging.getLogger("mbt03_server")
    if any(getattr(handler, "_mbt03_server_handler", False)
           for handler in logger.handlers):
        return
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.log")
    handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler._mbt03_server_handler = True
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def run_app():
    _configure_server_logging()
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
