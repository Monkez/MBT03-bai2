"""Exercise startup in fresh Windows Qt processes: DPI is fixed before QApplication."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import json
from PyQt5 import uic
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow
import config as cf
import main

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(cf.DATA_DIR + "assets/qt/main.ui", self)

    def showMaximized(self):
        super().showMaximized()
        QTimer.singleShot(50, self.measure)

    def measure(self):
        ratio = self.devicePixelRatioF()
        print("DPI_RESULT " + json.dumps({
            "ratio": ratio,
            "logical_dpi": self.screen().logicalDotsPerInch(),
            "panel_width": self.frame_4.width(),
            "physical_panel_width": self.frame_4.width() * ratio,
            "button_height": self.start_btn.height(),
            "button_font_height": self.start_btn.fontMetrics().height(),
        }), flush=True)
        self.close()
        QApplication.instance().quit()

# Test the real startup and UI without starting servers or writing logs.
main.MainWindow = Window
main._configure_server_logging = lambda: None
raise SystemExit(main.run_app())
'''


@unittest.skipUnless(sys.platform == "win32", "Requires the Windows Qt platform plugin")
class DisplayScalingTests(unittest.TestCase):
    def test_startup_preserves_fractional_dpi_and_standard_scale_layout(self):
        for dpi in (96, 120, 144, 168, 192):
            with self.subTest(scale=dpi / 96):
                env = {k: v for k, v in os.environ.items() if not k.startswith("QT_")}
                env.update(QT_QPA_PLATFORM="windows", QT_FONT_DPI=str(dpi),
                           PYTHONIOENCODING="utf-8",
                           PYTHONPATH=os.pathsep.join((str(ROOT / "assets"), str(ROOT))))
                result = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env,
                                        capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                line = next(line for line in result.stdout.splitlines() if line.startswith("DPI_RESULT "))
                measured = json.loads(line.removeprefix("DPI_RESULT "))
                self.assertAlmostEqual(measured["ratio"], dpi / 96)
                self.assertAlmostEqual(measured["logical_dpi"], 96)
                self.assertEqual(measured["panel_width"], 380)
                self.assertAlmostEqual(measured["physical_panel_width"], 380 * dpi / 96)
                self.assertEqual(measured["button_height"], 50)
                self.assertLessEqual(measured["button_font_height"], measured["button_height"])


if __name__ == "__main__":
    unittest.main()
