import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QWidget

from gui.main_window import MainWindow
from gui.uart_debug_dialog import UartDebugDialog


class FakeServer(QObject):
    wifi_config_event_signal = pyqtSignal(dict)

    def __init__(self, port_id, connected=True):
        super().__init__()
        self.port_id = port_id
        self.is_connected = connected
        self.send_uart_command = MagicMock(return_value=True)
        self.request_wifi_config = MagicMock(return_value={"ok": True})
        self.commit_wifi_config = MagicMock(return_value={"ok": True})


class UartDebugDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.parent = QWidget()
        self.parent.testing = False
        self.servers = [FakeServer(1), FakeServer(2, connected=False)]
        self.dialog = UartDebugDialog(self.servers, self.parent)
        self.dialog._pool.shutdown(wait=True)
        self.dialog._pool = MagicMock()
        self.addCleanup(self.parent.deleteLater)
        self.addCleanup(self.dialog.shutdown)

    def finish_job(self):
        args = self.dialog._pool.submit.call_args.args
        args[0](*args[1:])

    def request_wifi(self):
        self.dialog.port_combo.setCurrentIndex(1)
        self.dialog.ssid_input.setText("Test-Network")
        self.dialog.password_input.setText("test-password-123")
        with patch("gui.uart_debug_dialog.QMessageBox.question", return_value=QMessageBox.Yes):
            self.dialog.send_wifi()
        return self.dialog._requests[1]

    def emit_status(self, request, status, port_id=1):
        self.servers[0].wifi_config_event_signal.emit({
            "port_id": port_id, "request_id": request["request_id"], "status": status,
        })

    def test_uart_broadcast_only_targets_online_boards_and_appends_newline(self):
        self.dialog.command_input.setText(" 0LG00\n ")
        self.dialog.send_command()
        self.assertFalse(self.dialog.send_button.isEnabled())
        self.finish_job()
        self.servers[0].send_uart_command.assert_called_once_with("0LG00\n")
        self.servers[1].send_uart_command.assert_not_called()
        self.assertIn("Đã gửi tới bệ: 1", self.dialog.status_label.text())

    def test_selected_board_failure_does_not_fall_back_to_broadcast(self):
        self.dialog.port_combo.setCurrentIndex(2)
        self.servers[1].send_uart_command.return_value = False
        self.dialog.send_command()
        self.finish_job()
        self.servers[0].send_uart_command.assert_not_called()
        self.servers[1].send_uart_command.assert_called_once()
        self.assertIn("Gửi thất bại: 2", self.dialog.status_label.text())

    def test_empty_legacy_wifi_and_offline_broadcast_do_not_send(self):
        for command in ("", "Wifi#ssid#secret"):
            self.dialog.command_input.setText(command)
            self.dialog.send_command()
        self.servers[0].is_connected = False
        self.dialog.command_input.setText("0LG00")
        self.dialog.send_command()
        self.dialog._pool.submit.assert_not_called()

    def test_exercise_blocks_buttons_and_direct_calls(self):
        self.parent.testing = True
        self.dialog.refresh()
        self.assertFalse(self.dialog.send_button.isEnabled())
        self.assertFalse(self.dialog.wifi_button.isEnabled())
        self.dialog.send_command()
        self.dialog.send_wifi()
        self.dialog._pool.submit.assert_not_called()
        self.parent.testing = False
        self.dialog.refresh()
        self.assertTrue(self.dialog.send_button.isEnabled())

    def test_wifi_requires_one_board_valid_credentials_and_confirmation(self):
        with patch("gui.uart_debug_dialog.QMessageBox.question", return_value=QMessageBox.No) as question:
            self.dialog.send_wifi()
            question.assert_not_called()
            self.dialog.port_combo.setCurrentIndex(1)
            self.dialog.ssid_input.setText("Test-Network")
            self.dialog.password_input.setText("short")
            self.dialog.send_wifi()
            question.assert_not_called()
            self.dialog.password_input.setText("test-password-123")
            self.dialog.send_wifi()
            question.assert_called_once()
        self.dialog._pool.submit.assert_not_called()
        self.assertEqual(self.dialog._requests, {})

    def test_wifi_success_waits_for_board_then_commits_and_hides_password(self):
        request = self.request_wifi()
        self.assertEqual(self.dialog.password_input.text(), "")
        self.assertNotIn("test-password-123", repr(self.dialog._requests))
        self.finish_job()
        self.assertEqual(request["status"], "sent")
        self.servers[0].commit_wifi_config.assert_not_called()
        self.emit_status(request, "accepted")
        self.emit_status(request, "awaiting_commit")
        self.assertEqual(request["status"], "commit_sending")
        self.finish_job()
        self.servers[0].commit_wifi_config.assert_called_once_with(request["request_id"])
        self.assertEqual(request["status"], "commit_sent")
        self.emit_status(request, "committed")
        self.assertEqual(request["status"], "committed")
        self.assertIn("thành công", self.dialog.status_label.text())
        self.emit_status(request, "accepted")
        self.assertEqual(request["status"], "committed")

    def test_wifi_ack_before_send_completion_is_not_overwritten(self):
        request = self.request_wifi()
        self.emit_status(request, "accepted")
        self.finish_job()
        self.assertEqual(request["status"], "accepted")

    def test_wifi_events_from_other_board_or_request_are_ignored(self):
        request = self.request_wifi()
        self.finish_job()
        self.emit_status(request, "committed", port_id=2)
        self.emit_status({"request_id": "other"}, "committed")
        self.assertEqual(request["status"], "sent")

    def test_commit_retries_with_delay_and_stops_at_deadline(self):
        with patch("gui.uart_debug_dialog.time.monotonic", return_value=100) as clock:
            request = self.request_wifi()
            self.finish_job()
            self.servers[0].commit_wifi_config.return_value = {"ok": False, "reason": "not_healthy"}
            self.emit_status(request, "awaiting_commit")
            self.finish_job()
            self.assertEqual(request["status"], "commit_retry")
            submitted = self.dialog._pool.submit.call_count
            self.dialog.refresh()
            self.assertEqual(self.dialog._pool.submit.call_count, submitted)
            clock.return_value = 100.5
            self.dialog.refresh()
            self.assertEqual(self.dialog._pool.submit.call_count, submitted + 1)
            self.finish_job()
            clock.return_value = request["deadline"]
            self.dialog.refresh()
            self.assertEqual(request["status"], "timeout")

    def test_no_ack_times_out_and_allows_new_request_after_deadline(self):
        with patch("gui.uart_debug_dialog.time.monotonic", return_value=100) as clock:
            request = self.request_wifi()
            self.finish_job()
            clock.return_value = 104
            self.dialog.refresh()
            self.assertEqual(request["status"], "ack_timeout")
            self.request_wifi()
            self.assertIs(self.dialog._requests[1], request)
            clock.return_value = request["deadline"]
            self.dialog.refresh()
            self.assertEqual(request["status"], "timeout")
            new_request = self.request_wifi()
            self.assertNotEqual(new_request["request_id"], request["request_id"])

    def test_close_clears_password_but_keeps_tracking_wifi(self):
        request = self.request_wifi()
        self.finish_job()
        self.dialog.show()
        self.dialog.password_input.setText("unsent-secret")
        QTest.keyClick(self.dialog, Qt.Key_Escape)
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.dialog.password_input.text(), "")
        self.emit_status(request, "rolled_back")
        self.assertEqual(request["status"], "rolled_back")

    def test_transport_exception_does_not_expose_password_or_leave_busy(self):
        request = self.request_wifi()
        self.servers[0].request_wifi_config.side_effect = RuntimeError("test-password-123")
        self.finish_job()
        self.assertEqual(request["status"], "failed")
        self.assertNotIn("test-password-123", self.dialog.status_label.text())
        self.assertFalse(self.dialog._busy)

    def test_cannot_start_exercise_while_wifi_transaction_is_pending(self):
        request = self.request_wifi()
        self.finish_job()
        self.assertTrue(self.dialog.has_pending_operations())
        window = SimpleNamespace(
            testing=False, _uart_debug_dialog=self.dialog, _play_start_announcement=MagicMock(),
        )
        with patch("gui.main_window.QMessageBox.information") as message:
            MainWindow.start_test(window)
        message.assert_called_once()
        window._play_start_announcement.assert_not_called()
        self.emit_status(request, "rolled_back")
        self.assertFalse(self.dialog.has_pending_operations())

    def test_main_window_shortcut_opens_and_reuses_dialog(self):
        window = MainWindow.__new__(MainWindow)
        QMainWindow.__init__(window)
        window.testing = False
        window._uart_debug_dialog = None
        window.servers = self.servers
        window.setting_btn = MagicMock()
        window.start_btn = MagicMock()
        window._closing = True  # Avoid real server shutdown in this UI-only harness.
        window._configure_main_ui()
        self.assertEqual(window._uart_debug_shortcut.key().toString(), "Ctrl+S")
        window.show()
        window.activateWindow()
        self.app.processEvents()
        QTest.keyClick(window, Qt.Key_S, Qt.ControlModifier)
        self.app.processEvents()
        self.assertIsNotNone(window._uart_debug_dialog)
        first = window._uart_debug_dialog
        first.close()
        window._uart_debug_shortcut.activated.emit()
        self.assertIs(window._uart_debug_dialog, first)
        self.assertTrue(first.isVisible())
        first.shutdown()
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
