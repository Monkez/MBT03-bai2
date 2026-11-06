import os
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

import config as cf
from gui.main_window import MainWindow
from gui.setting_window import SettingWindow


class OfflineScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, port=None):
        self.addCleanup(patch.stopall)
        option = patch("gui.main_window.OptionWindow").start().return_value
        option.exec_.return_value = option.Accepted = 1
        option.start, option.p_num, option.automatic_close_target_enabled = True, 1, True
        patch.object(MainWindow, "_start_servers").start()
        for name in ("LoraController", "ShotSound", "HitSound", "ResultSound"):
            patch(f"gui.main_window.{name}").start()
        window = MainWindow()
        window.lora.port_name = port
        self.addCleanup(window.close)
        return window

    def test_no_lora_runs_overlap_hide_and_auto_end_from_schedule(self):
        window = self.window()
        times = [{"show_seconds": s, "hide_seconds": h}
                 for s,h in ((10,20),(12,19),(13,21),(15,22))]
        with patch.dict(cf.APP_CONFIG["shooting"], target_times=times), patch(
                "gui.main_window.time.monotonic", return_value=100) as clock:
            window.start_test()
            timers = list(window._lora_schedule_timers)
            for index, at in enumerate((108.5,110.5,111.5,113.5)):
                clock.return_value = at
                timers[index].timeout.emit()
            clock.return_value = 115
            window._refresh_target_presentation()
            self.assertEqual(window.client_widgets[0]._visible_target_classes, (1,0,2,3))
            self.assertEqual(window._shooting_session.active_target(115, 1).class_id, 1)
            for index, at in enumerate((117.5,118.5,119.5,120.5), 4):
                clock.return_value = at
                timers[index].timeout.emit()
            self.assertEqual(window._shooting_session.deadline, 126.5)
            clock.return_value = 126.499
            window.update_app()
            self.assertTrue(window.testing)
            clock.return_value = 126.5
            window.update_app()
            self.assertFalse(window.testing)
            self.assertIsNone(window.client_widgets[0]._target_presentation)
            window.lora.send_command.assert_not_called()

    def test_real_qtimer_shows_first_target_without_serial_signal(self):
        window = self.window()
        times = [{"show_seconds": s, "hide_seconds": h}
                 for s,h in ((.2,5),(6,7),(8,9),(10,11))]
        with patch.dict(cf.APP_CONFIG["shooting"], target_times=times, hardware_delay_time=.05):
            window.start_test()
            deadline = time.monotonic() + 3
            while window.client_widgets[0]._target_presentation != (1, True) and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertEqual(window.client_widgets[0]._target_presentation, (1,True))
            window.lora.send_command.assert_not_called()

    def test_selected_com_still_requires_real_write_and_does_not_fake_scores(self):
        window = self.window("COM7")
        with patch("gui.main_window.time.monotonic", return_value=100) as clock:
            window.start_test()
            clock.return_value = 113.5
            window._lora_schedule_timers[0].timeout.emit()
            clock.return_value = 116
            window._refresh_target_presentation()
            self.assertEqual(window.client_widgets[0]._target_presentation, (1,False))
            self.assertIsNone(window._shooting_session.active_target(116,1))
            window.lora.send_command.assert_called_with("@114#")

    def test_error_row_hidden_when_empty_and_restored_on_validation_or_save_error(self):
        dialog = SettingWindow()
        self.addCleanup(dialog.reject)
        dialog.show()
        self.assertTrue(dialog.timing_error_label.isHidden())
        dialog.target_time_inputs[0]["hide_seconds"].setValue(1)
        self.assertFalse(dialog.timing_error_label.isHidden())
        dialog.target_time_inputs[0]["hide_seconds"].setValue(22)
        self.assertTrue(dialog.timing_error_label.isHidden())
        with patch("gui.setting_window.save_timing_settings", side_effect=PermissionError("locked")):
            dialog.confirm_btn.click()
        self.assertFalse(dialog.timing_error_label.isHidden())
        self.assertIn("locked", dialog.timing_error_label.text())

    def test_unavailable_selected_port_is_not_mislabeled_as_no_lora(self):
        lora = MagicMock()
        lora.port_name = "COM7"
        lora.available_ports.return_value = []
        dialog = SettingWindow(lora_controller=lora)
        self.addCleanup(dialog.reject)
        self.assertEqual(dialog.comport_combo.currentData(), "COM7")
        self.assertIn("chưa kết nối", dialog.comport_combo.currentText())
