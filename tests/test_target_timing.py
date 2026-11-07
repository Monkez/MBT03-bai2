import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

import config as cf
from gui.main_window import MainWindow, _configured_lora_script
from gui.setting_window import SettingWindow
from gui.shooting_session import ShootingSession
from gui.target_timing import get_target_times, hardware_delay_time, save_timing_settings, validate_times

TIMES = [{"show_seconds": show, "hide_seconds": hide}
         for show, hide in ((10, 17), (27, 37), (40, 50), (59, 79))]


class TimingFixture:
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(cf.APP_CONFIG, copy.deepcopy(cf.APP_CONFIG)).start()
        patch.dict(cf.APP_CONFIG["shooting"], hardware_delay_time=1.5, target_times=[]).start()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"
        self.path.write_text(json.dumps({"shooting": {"existing": "keep"},
                                         "review": {"camera_zoom": 1.7}}), encoding="utf-8")
        patch.object(cf, "CONFIG_PATH", str(self.path)).start()


class TimingTests(TimingFixture, unittest.TestCase):
    def test_inconsistent_delay_falls_back_and_large_valid_delay_is_supported(self):
        with patch.dict(cf.APP_CONFIG["shooting"], hardware_delay_time=50, target_times=[]):
            self.assertEqual(hardware_delay_time(), 1.5)
            self.assertEqual(get_target_times()[0]["show_seconds"], 15)
        values = [{"show_seconds": show, "hide_seconds": show + 10} for show in (60,80,100,120)]
        with patch.dict(cf.APP_CONFIG["shooting"], hardware_delay_time=50, target_times=values):
            self.assertEqual(hardware_delay_time(), 50)
            self.assertEqual(get_target_times(), values)
    def test_overlapping_times_are_saved_and_hidden_times_can_be_in_any_order(self):
        times = copy.deepcopy(TIMES)
        times[1] = {"show_seconds": 10, "hide_seconds": 16}
        save_timing_settings(times, 1)
        self.assertEqual(get_target_times(), times)

    def test_auto_end_waits_for_every_actual_hide_then_uses_four_delays(self):
        session = ShootingSession(100, (8.5, 25.5, 38.5, 57.5),
                                  {1: 7, 0: 10, 2: 10, 3: 20}, hardware_delay_time=1.5)
        for target, shown in ((1,108.5),(0,125.5),(2,138.5),(3,157.5)):
            session.open_target(target, shown)
            session.confirm_command_sent(target, shown, raised=True)
        for target, hidden in ((1,115.5),(0,135.5),(2,148.5),(3,177.5)):
            session.close_target(target, hidden, scheduled=True)
            if target != 3:
                session.confirm_command_sent(target, hidden, raised=False)
        self.assertFalse(session.expired(200), "Must wait for the last actual serial write")
        self.assertEqual(session.active_target(189, 3).class_id, 3)
        self.assertEqual(session.visible_target_classes(189), (3,))
        session.confirm_command_sent(3, 190, raised=False)
        self.assertEqual(session.deadline, 196)
        self.assertIsNone(session.active_target(193, 3))
        self.assertFalse(session.expired(195.999))
        self.assertTrue(session.expired(196))
    def test_configurable_delay_changes_command_times(self):
        for delay in (0, .75, 2):
            with patch.dict(cf.APP_CONFIG["shooting"], hardware_delay_time=delay, target_times=TIMES):
                self.assertEqual([item[0] for item in _configured_lora_script()],
                                 [10 - delay, 27 - delay, 40 - delay, 59 - delay])

    def test_save_and_restart_preserve_values_channel_delay_and_unrelated_config(self):
        save_timing_settings(TIMES, 3)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["shooting"]["existing"], "keep")
        self.assertEqual(raw["review"], {"camera_zoom": 1.7})
        restarted = cf.load_app_config(self.path)
        self.assertEqual(restarted["shooting"]["target_times"], TIMES)
        self.assertEqual(restarted["shooting"]["control_channel"], 3)
        self.assertEqual(restarted["shooting"]["hardware_delay_time"], 1.5)
        self.assertEqual(get_target_times(), TIMES)

    def test_atomic_failure_preserves_file_and_live_settings(self):
        before = self.path.read_bytes()
        live = copy.deepcopy(cf.APP_CONFIG)
        with patch("gui.target_timing.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                save_timing_settings(TIMES, 2)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(cf.APP_CONFIG, live)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_invalid_order_nonfinite_and_per_target_bounds_are_rejected(self):
        for field, value in (("show_seconds", 18), ("hide_seconds", 10),
                             ("show_seconds", float("nan")), ("hide_seconds", float("inf"))):
            times = copy.deepcopy(TIMES)
            times[0][field] = value
            with self.assertRaises(ValueError):
                validate_times(times)
        for index, key, value in ((1, "show_seconds", 9), (3, "hide_seconds", 3601),
                                  (0, "show_seconds", 1)):
            times = copy.deepcopy(TIMES)
            times[index][key] = value
            with self.assertRaises(ValueError):
                save_timing_settings(times, 1)

    def test_receipt_window_uses_actual_writes_and_twice_hardware_delay(self):
        session = ShootingSession(100, (8.5, 25.5, 38.5, 57.5), hardware_delay_time=1.5)
        session.open_target(1, 108.5)
        session.confirm_command_sent(1, 108.5, raised=True)
        self.assertIsNone(session.active_target(108.499))
        self.assertEqual(session.active_target(108.5).class_id, 1)
        self.assertEqual(session.target_presentation(109.999), (1, False))
        self.assertEqual(session.target_presentation(110), (1, True))
        session.confirm_command_sent(1, 109, raised=True)
        self.assertIsNone(session.active_target(108.999))
        self.assertEqual(session.active_target(109).class_id, 1)
        session.close_target(1, 115.5, scheduled=True)
        session.confirm_command_sent(1, 117, raised=False)  # late serial queue
        self.assertEqual(session.active_target(119.999).class_id, 1)
        self.assertIsNone(session.active_target(120))
        self.assertEqual(session.target_presentation(118.499), (1, True))
        self.assertEqual(session.target_presentation(118.5), (1, False))


class TimingUiTests(TimingFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def dialog(self):
        dialog = SettingWindow()
        self.addCleanup(dialog.reject)
        return dialog

    def test_port_combo_preserves_device_data_with_current_ui_widget(self):
        lora = MagicMock()
        lora.port_name = "COM7"
        lora.available_ports.return_value = [{"device": "COM7", "description": "USB Serial"}]
        dialog = SettingWindow(lora_controller=lora)
        self.addCleanup(dialog.reject)
        self.assertEqual(dialog.comport_combo.currentData(), "COM7")
        dialog._apply_lora_selection()
        lora.connect_port.assert_called_once_with("COM7")

    def test_dialog_reuses_channel_combo_and_saves_on_accept_then_reloads(self):
        dialog = self.dialog()
        self.assertEqual([dialog.channel_combo.itemText(i) for i in range(3)],
                         ["Kênh 1", "Kênh 2", "Kênh 3"])
        for index, (pair, values) in enumerate(zip(dialog.target_time_inputs, TIMES)):
            for key, value in values.items():
                pair[key].setValue(value - values["show_seconds"] if index == 3 and key == "hide_seconds" else value)
        dialog.channel_combo.setCurrentIndex(2)
        dialog.confirm_btn.click()
        self.assertEqual(dialog.result(), dialog.Accepted, dialog.timing_error_label.text())
        reopened = self.dialog()
        self.assertEqual(reopened._target_time_values(), TIMES)
        self.assertEqual(reopened.channel_combo.currentData(), 3)
        self.assertFalse(dialog._frame_timer.isActive())

    def test_target8_hidden_field_is_run_duration_and_persists_sixteen_seconds(self):
        from gui.target_timing import target8_timeout_seconds
        dialog = self.dialog()
        pair = dialog.target_time_inputs[3]
        pair["hide_seconds"].setValue(16)
        shown = pair["show_seconds"].value()
        dialog.confirm_btn.click()
        self.assertEqual(dialog.result(), dialog.Accepted, dialog.timing_error_label.text())
        reopened = self.dialog()
        self.assertEqual(reopened.target_time_inputs[3]["hide_seconds"].value(), 16)
        self.assertEqual(get_target_times()[3]["hide_seconds"], shown + 16)
        self.assertEqual(target8_timeout_seconds(get_target_times()), 20)

    def test_cancel_validation_and_write_failure_do_not_change_settings(self):
        before = self.path.read_bytes()
        dialog = self.dialog()
        dialog.target_time_inputs[0]["hide_seconds"].setValue(14)
        dialog.confirm_btn.click()
        self.assertNotEqual(dialog.result(), dialog.Accepted)
        self.assertTrue(dialog.timing_error_label.text())
        self.assertEqual(self.path.read_bytes(), before)
        dialog.target_time_inputs[0]["hide_seconds"].setValue(22)
        with patch("gui.setting_window.save_timing_settings", side_effect=PermissionError("locked")):
            dialog.confirm_btn.click()
        self.assertNotEqual(dialog.result(), dialog.Accepted)
        self.assertIn("locked", dialog.timing_error_label.text())
        dialog.cancel_btn.click()
        self.assertEqual(self.path.read_bytes(), before)

    def test_main_window_sends_both_commands_early_and_stops_without_leaving_target_raised(self):
        save_timing_settings(TIMES, 2)
        option = patch("gui.main_window.OptionWindow").start().return_value
        option.exec_.return_value = option.Accepted = 1
        option.start, option.p_num, option.automatic_close_target_enabled = True, 1, True
        patch.object(MainWindow, "_start_servers").start()
        for name in ("LoraController", "ShotSound", "HitSound", "ResultSound"):
            patch(f"gui.main_window.{name}").start()
        clock = patch("gui.main_window.time.monotonic", return_value=100).start()
        window = MainWindow()
        self.addCleanup(window.close)
        window.lora.send_command.side_effect = lambda command: window._on_lora_command_sent(
            command, clock.return_value, clock.return_value)
        window.start_test()
        self.assertEqual([t.interval() for t in window._lora_schedule_timers],
                         [8500, 15500, 25500, 35500, 38500, 48500, 57500])
        clock.return_value = 108.5
        window._lora_schedule_timers[0].timeout.emit()
        window.lora.send_command.assert_called_with("@114#")
        clock.return_value = 115.5
        window._lora_schedule_timers[1].timeout.emit()
        window.lora.send_command.assert_called_with("@112#")
        self.assertEqual(window._shooting_session.active_target(118.499).class_id, 1)
        self.assertIsNone(window._shooting_session.active_target(118.5))
        clock.return_value = 125.5
        window._lora_schedule_timers[2].timeout.emit()
        window.stop_test()
        window.lora.send_command.assert_called_with("@222#")
        self.assertEqual(window._lora_schedule_timers, [])

    def test_simultaneous_raises_render_both_and_early_hit_folds_only_its_target(self):
        times = copy.deepcopy(TIMES)
        times[1] = {"show_seconds": 10, "hide_seconds": 18}
        save_timing_settings(times, 1)
        option = patch("gui.main_window.OptionWindow").start().return_value
        option.exec_.return_value = option.Accepted = 1
        option.start, option.p_num, option.automatic_close_target_enabled = True, 1, True
        patch.object(MainWindow, "_start_servers").start()
        for name in ("LoraController", "ShotSound", "HitSound", "ResultSound"):
            patch(f"gui.main_window.{name}").start()
        clock = patch("gui.main_window.time.monotonic", return_value=100).start()
        window = MainWindow()
        self.addCleanup(window.close)
        window.lora.send_command.side_effect = lambda command: window._on_lora_command_sent(
            command, clock.return_value, clock.return_value)
        window.start_test()
        clock.return_value = 108.5
        window._lora_schedule_timers[0].timeout.emit()
        window._lora_schedule_timers[1].timeout.emit()
        self.assertEqual([call.args[0] for call in window.lora.send_command.call_args_list],
                         ["@114#", "@224#"])
        clock.return_value = 110
        window._refresh_target_presentation()
        widget = window.client_widgets[0]
        self.assertEqual(widget._visible_target_classes, (1, 0))
        widget.compose_target_image()
        self.assertEqual(set(widget._rendered_target_rects), {1, 0})
        clock.return_value = 111
        self.assertTrue(window._maybe_close_hit_target(1, True))
        clock.return_value = 112.5
        window._refresh_target_presentation()
        self.assertEqual(widget._visible_target_classes, (0,))
        self.assertEqual(widget._target_presentation, (0, True))
