import os
import unittest
from unittest.mock import MagicMock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gui.main_window import MainWindow


class PedestalLocateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(patch.stopall)
        option = patch("gui.main_window.OptionWindow").start().return_value
        option.exec_.return_value = option.Accepted = 1
        option.start = True
        option.p_num = 2
        option.automatic_close_target_enabled = False
        patch.object(MainWindow, "_start_servers").start()
        patch("gui.main_window.LoraController").start()
        self.window = MainWindow()
        self.window.servers = [MagicMock(is_connected=True), MagicMock(is_connected=True)]
        for server, widget in zip(self.window.servers, self.window.client_widgets):
            server.send_uart_command.return_value = True
            widget.set_connection_state(True)
        self.addCleanup(self.window.close)

    def click(self, index, button=Qt.LeftButton):
        QTest.mouseClick(self.window.client_widgets[index].pedestal_name_label, button)

    def test_click_toggles_only_selected_gun_and_keyboard_can_stop(self):
        self.click(1)
        widget = self.window.client_widgets[1]
        self.assertTrue(widget.locating)
        self.assertTrue(widget._locate_timer.isActive())
        self.assertIn("220, 0, 0", widget.pedestal_name_label.styleSheet())
        widget._blink_locate_label()
        self.assertIn("0, 153, 0", widget.pedestal_name_label.styleSheet())
        self.click(1)
        self.assertFalse(widget.locating)
        self.assertFalse(widget._locate_timer.isActive())
        self.click(1)
        QTest.keyClick(widget.pedestal_name_label, Qt.Key_Return)
        self.assertFalse(widget.locating)
        self.window.servers[0].send_uart_command.assert_not_called()
        self.assertEqual(self.window.servers[1].send_uart_command.call_args_list,
                         [call("0LR01\n"), call("0LG00\n")] * 2)

    def test_right_click_disconnected_and_invalid_ports_send_nothing(self):
        self.click(0, Qt.RightButton)
        self.window.servers[0].is_connected = False
        self.click(0)  # UI can lag behind server state.
        self.window.client_widgets[1].set_connection_state(False)
        self.click(1)
        for port in (0, 3):
            self.window._toggle_pedestal_locate(port)
        for server in self.window.servers:
            server.send_uart_command.assert_not_called()

    def test_send_failure_keeps_state_and_reports_error(self):
        server = self.window.servers[0]
        widget = self.window.client_widgets[0]
        with patch("gui.main_window.QMessageBox.warning") as warning:
            server.send_uart_command.return_value = False
            self.click(0)
            self.assertFalse(widget.locating)
            server.send_uart_command.return_value = True
            self.click(0)
            server.send_uart_command.return_value = False
            self.click(0)
            self.assertTrue(widget.locating)
            self.assertEqual(warning.call_count, 2)

    def test_connection_warning_takes_priority_and_disconnect_resets_indicator(self):
        self.click(0)
        widget = self.window.client_widgets[0]
        widget.set_connection_quality_state("degraded")
        widget._blink_locate_label()
        self.assertIn("217, 119, 6", widget.pedestal_name_label.styleSheet())
        widget.set_connection_quality_state("healthy")
        widget._blink_locate_label()
        self.assertIn("220, 0, 0", widget.pedestal_name_label.styleSheet())
        widget.set_connection_quality_state("offline")
        self.assertFalse(widget.locating)
        self.assertFalse(widget._locate_timer.isActive())
        self.assertIn("185, 28, 28", widget.pedestal_name_label.styleSheet())
        widget.set_connection_state(True)
        self.assertFalse(widget.locating)

    def test_close_stops_locating_guns(self):
        self.click(0)
        self.window.close()
        self.assertEqual(self.window.servers[0].send_uart_command.call_args_list,
                         [call("0LR01\n"), call("0LG00\n")])
        self.assertFalse(self.window.client_widgets[0]._locate_timer.isActive())


if __name__ == "__main__":
    unittest.main()
