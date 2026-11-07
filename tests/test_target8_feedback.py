import os
import unittest
import numpy as np
from unittest.mock import MagicMock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
import config as cf
from gui.main_window import MainWindow


class Target8FeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(patch.stopall)
        option = patch('gui.main_window.OptionWindow').start().return_value
        option.exec_.return_value = option.Accepted = 1
        option.start, option.p_num, option.automatic_close_target_enabled = True, 1, True
        patch.object(MainWindow, '_start_servers').start()
        for name in ('LoraController', 'ShotSound', 'HitSound', 'ResultSound'):
            patch(f'gui.main_window.{name}').start()
        patch.dict(cf.APP_CONFIG["shooting"], target_times=[
            {"show_seconds": s, "hide_seconds": h} for s,h in ((15,22),(32,39),(42,49),(64,80))]).start()
        self.clock = patch('gui.main_window.time.monotonic', return_value=100).start()
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.window.lora.port_name = 'COM7'
        self.window.servers = [MagicMock()]
        self.window.lora.send_command.side_effect = lambda command: self.window._on_lora_command_sent(
            command, self.clock.return_value, self.clock.return_value)

    def begin_target8(self):
        w = self.window
        w.start_test()
        w._cancel_lora_script()
        w._target_presentation_timer.stop()
        for index, (target, at) in enumerate(((1, 115), (0, 132), (2, 142), (3, 164))):
            self.clock.return_value = at
            _, command, desc = w.LORA_SCRIPT[index]
            w._send_lora_script_command(command, desc, target)
            if target != 3:
                self.clock.return_value = at + 8
                w._send_scheduled_target_hide(target)
        w.lora.send_command.assert_called_with('@444#')
        self.assertTrue(w._target8_poll_timer.isActive())
        self.assertEqual(w._target8_poll_timer.interval(), 1000)
        return w._shooting_session

    def status(self, shown, at):
        self.clock.return_value = at
        self.window._on_target_state_received(3, shown, at - .1, at)

    def test_initial_hidden_waits_then_real_visibility_and_automatic_fold_end(self):
        session = self.begin_target8()
        self.status(False, 165.1)
        self.assertFalse(session.all_hides_sent)
        self.assertEqual(session.visible_target_classes(165.1), ())
        self.assertTrue(self.window._target8_poll_timer.isActive())
        self.window._target8_poll_timer.timeout.emit()
        self.window.lora.query_target8_state.assert_called_once()
        self.status(True, 166.1)
        self.assertEqual(session.visible_target_classes(166.099), ())
        self.assertEqual(session.visible_target_classes(166.1), (3,))
        self.assertEqual(self.window.client_widgets[0]._target_presentation, (3, True))
        self.status(False, 170.6)
        self.assertEqual(session.visible_target_classes(170.6), ())
        self.assertTrue(session.all_hides_sent)
        self.assertAlmostEqual(session.deadline, 172.6)
        self.assertIsNotNone(session.active_target(172.599, 3))
        self.assertIsNone(session.active_target(172.6, 3))
        self.assertFalse(self.window._target8_poll_timer.isActive())
        self.clock.return_value = 172.6
        self.window.update_app()
        self.assertFalse(self.window.testing)

    def test_hit_and_hide_setting_never_send_442_or_fold_the_carriage(self):
        session = self.begin_target8()
        self.status(True, 165)
        self.clock.return_value = 166
        self.assertFalse(self.window._maybe_close_hit_target(3, True))
        self.window._send_scheduled_target_hide(3)
        self.assertEqual(session.visible_target_classes(168), (3,))
        self.assertAlmostEqual(session.deadline, 184)
        self.assertNotIn('@442#', [c.args[0] for c in self.window.lora.send_command.call_args_list])
        self.status(False, 168.5)
        self.assertAlmostEqual(session.deadline, 170.5)
        self.clock.return_value = 170.5
        self.window.update_app()
        self.assertFalse(self.window.testing)
        self.assertNotIn('@442#', [c.args[0] for c in self.window.lora.send_command.call_args_list])

    def test_missing_status_stops_at_setting_duration_plus_four_seconds(self):
        session = self.begin_target8()
        self.assertAlmostEqual(session.deadline, 184)
        self.clock.return_value = 183.999
        self.window.update_app()
        self.assertTrue(self.window.testing)
        self.clock.return_value = 184
        self.window.update_app()
        self.assertFalse(self.window.testing)
        self.assertFalse(self.window._target8_poll_timer.isActive())
        self.assertNotIn('@442#', [c.args[0] for c in self.window.lora.send_command.call_args_list])

    def test_receipt_at_hard_limit_is_rejected_before_timeout_timer(self):
        self.begin_target8()
        self.clock.return_value = 184
        with patch.object(self.window._scoring_pool, 'submit') as submit:
            self.assertFalse(self.window.process_shot(1, np.zeros((8, 8, 3), np.uint8),
                                                      (.5, .5), received_at=184))
            submit.assert_not_called()
        self.assertFalse(self.window.testing)

    def test_late_serial_launch_anchors_limit_to_actual_write(self):
        self.begin_target8()
        self.window._on_lora_command_sent('@444#', 164, 167)
        self.assertEqual(self.window._shooting_session.deadline, 187)

    def test_real_timer_polls_then_stop_and_stale_status_do_not_change_next_run(self):
        self.begin_target8()
        self.window._target8_poll_timer.setInterval(20)
        QTest.qWait(55)
        self.assertGreaterEqual(self.window.lora.query_target8_state.call_count, 1)
        self.window.stop_test()
        self.assertFalse(self.window._target8_poll_timer.isActive())
        self.clock.return_value = 200
        self.window.start_test()
        session = self.window._shooting_session
        self.window._on_lora_command_sent("@444#", 263, 263)
        self.window._on_target_state_received(3, True, 163, 264)
        self.assertEqual(session.visible_target_classes(201), ())
        self.assertEqual(session._target_states, {})

    def test_queued_launch_from_previous_exercise_does_not_start_new_poll(self):
        self.begin_target8()
        self.window.stop_test()
        self.clock.return_value = 200
        self.window.start_test()
        self.window._on_lora_command_sent('@444#', 164, 201)
        self.assertFalse(self.window._target8_poll_timer.isActive())
        self.assertIsNone(self.window._target8_poll_started_at)

    def test_manual_launch_polls_until_shown_then_hidden(self):
        self.window._simulate_targets = True  # Previous exercise may have been offline.
        self.window._on_lora_command_sent('@444#', 100, 100)
        self.assertTrue(self.window._target8_poll_timer.isActive())
        self.status(False, 101)
        self.assertTrue(self.window._target8_poll_timer.isActive())
        self.status(True, 102)
        self.status(False, 103)
        self.assertFalse(self.window._target8_poll_timer.isActive())
