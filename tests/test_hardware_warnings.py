import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from gui.client_widget import ClientWidget
from gui.main_window import MainWindow


class HardwareWarningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widgets = [ClientWidget(1), ClientWidget(2)]
        self.window = SimpleNamespace(_closing=False, client_widgets=self.widgets)
        for widget in self.widgets:
            self.addCleanup(widget.deleteLater)
            self.addCleanup(widget.clear_error)

    def test_errors_are_routed_to_correct_pedestal_without_changing_score(self):
        for port, code in ((2, "E2"), (1, "E1")):
            MainWindow._on_data_received(self.window, port, {"UART_RX_DEBUG": code})
            widget = self.widgets[port - 1]
            self.assertFalse(widget.error_label.isHidden())
            self.assertEqual(widget._error_timer.interval(), 7000)
            self.assertEqual(widget.bullet_count, 0)
            self.assertEqual(widget.hit_targets, set())
            if port == 2:
                self.assertTrue(self.widgets[0].error_label.isHidden())
        self.assertIn("bắn quá nhanh", self.widgets[1].error_label.text())
        self.assertIn("giữ cò quá lâu", self.widgets[0].error_label.text())

    def test_invalid_ports_payloads_and_similar_codes_are_ignored(self):
        for port in (0, -1, 3):
            MainWindow._on_data_received(self.window, port, {"UART_RX_DEBUG": "E1"})
        for data in (None, [], {}, {"UART_RX_DEBUG": None}, {"UART_RX_DEBUG": 1},
                     {"UART_RX_DEBUG": "E10"}, {"UART_RX_DEBUG": "debug E2"},
                     {"UART_RX_DEBUG": "<b>E1</b>"}):
            MainWindow._on_data_received(self.window, 1, data)
        self.assertTrue(all(widget.error_label.isHidden() for widget in self.widgets))

    def test_complete_hardware_tokens_and_whitespace_are_supported(self):
        MainWindow._on_data_received(self.window, 1, {"UART_RX_DEBUG": " 0E200\r\n"})
        self.assertIn("bắn quá nhanh", self.widgets[0].error_label.text())

    def test_new_error_replaces_old_and_restarts_single_timer(self):
        widget = self.widgets[0]
        widget.show_error("E1")
        timer = widget._error_timer
        timer.start(1)
        widget.show_error("E2")
        self.assertIs(widget._error_timer, timer)
        self.assertGreater(timer.remainingTime(), 6000)
        self.assertIn("bắn quá nhanh", widget.error_label.text())

    def test_warning_hides_after_configured_duration(self):
        widget = self.widgets[0]
        with patch("gui.client_widget.cf.config_int", return_value=30):
            widget.show_error("E1")
        self.assertTrue(QSignalSpy(widget._error_timer.timeout).wait(1000))
        self.assertTrue(widget.error_label.isHidden())

    def test_start_clears_old_warning_and_close_ignores_queued_data(self):
        widget = self.widgets[0]
        widget.show_error("E2")
        widget.start_test()
        self.assertTrue(widget.error_label.isHidden())
        self.assertFalse(widget._error_timer.isActive())
        self.window._closing = True
        MainWindow._on_data_received(self.window, 1, {"UART_RX_DEBUG": "E1"})
        self.assertTrue(widget.error_label.isHidden())

    def test_warning_stays_inside_target_area_after_resize(self):
        widget = self.widgets[0]
        widget.show()
        for width, height in ((507, 345), (340, 345), (800, 550)):
            widget.resize(width, height)
            self.app.processEvents()
            widget.show_error("E2")
            self.assertTrue(widget.sign_image.rect().contains(widget.error_label.geometry()))
        widget.close()


if __name__ == "__main__":
    unittest.main()
