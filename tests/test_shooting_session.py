import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

import config as cf
from gui.main_window import MainWindow, _configured_lora_script
from gui.shot_sound import ShotSound
from gui.shooting_session import ShootingSession


class ShootingSessionTests(unittest.TestCase):
    def test_invalid_timeline_falls_back_without_shifting_target_identity(self):
        defaults = cf.DEFAULT_CONFIG["shooting"]["lora_timeline"]
        expected = tuple((item["delay_seconds"], item["command"], item["description"])
                         for item in defaults)
        for delays in ((15, 18, 42, 64), (15, 32, 42, 70), (15, 32, 42),
                       (15, 32, float("nan"), 64), (15, 32, float("inf"), 64),
                       (-1, 32, 42, 64)):
            configured = [dict(item, delay_seconds=delay)
                          for item, delay in zip(defaults, delays)]
            with self.subTest(delays=delays), patch("gui.main_window.cf.get_setting", return_value=configured):
                self.assertEqual(_configured_lora_script(), expected)

    def test_exposure_boundaries_sequence_and_gaps(self):
        session = ShootingSession(100)
        self.assertIsNone(session.active_target(114.999))
        for seconds, class_id in ((15, 1), (32, 0), (42, 2), (64, 3)):
            now = 100 + seconds
            self.assertTrue(session.open_target(class_id, now))
            self.assertIsNone(session.active_target(now - 0.001))
            self.assertEqual(session.active_target(now).class_id, class_id)
            self.assertEqual(session.active_target(now + 6.999).class_id, class_id)
            self.assertIsNone(session.active_target(now + 7))
        self.assertFalse(session.expired(174.999))
        self.assertTrue(session.expired(175))
        self.assertFalse(session.open_target(1, 176))

    def test_wrong_order_is_rejected_and_overlapping_windows_are_exclusive(self):
        session = ShootingSession(100)
        self.assertFalse(session.open_target(3, 115))
        self.assertTrue(session.open_target(1, 115))
        previous = session.active_target(115)
        self.assertTrue(session.open_target(0, 116))
        self.assertFalse(previous.contains(116))
        self.assertEqual(session.active_target(116).class_id, 0)
        self.assertFalse(session.open_target(0, 117))

    def test_early_close_preserves_shots_received_before_close(self):
        session = ShootingSession(100)
        session.open_target(1, 115)
        exposure = session.active_target(116)
        self.assertFalse(session.close_target(3, 116))
        self.assertTrue(session.close_target(1, 117))
        self.assertTrue(exposure.contains(116.999))
        self.assertFalse(exposure.contains(117))
        self.assertIsNone(session.active_target(118))


class ShootingFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.clock = patch("gui.main_window.time.monotonic", return_value=100.0).start()
        self.addCleanup(patch.stopall)
        option = patch("gui.main_window.OptionWindow").start().return_value
        option.exec_.return_value = option.Accepted = 1
        option.start = True
        option.p_num = 1
        option.automatic_close_target_enabled = True
        patch.object(MainWindow, "_start_servers").start()
        patch("gui.main_window.LoraController").start()
        patch("gui.main_window.ShotSound").start()
        self.window = MainWindow()
        self.window._scoring_pool.shutdown(wait=True)
        self.window._scoring_pool = MagicMock()
        self.window.start_test()
        self.window._cancel_lora_script()
        self.addCleanup(self.window.close)

    def open_target(self, index):
        seconds, command, description = self.window.LORA_SCRIPT[index]
        self.clock.return_value = 100 + seconds
        self.window._send_lora_script_command(command, description, (1, 0, 2, 3)[index])

    def receive(self, at):
        self.clock.return_value = at
        return self.window.process_shot(1, np.zeros((8, 8, 3), dtype=np.uint8), (0.5, 0.5))

    def complete(self, class_id, hit=True, job_index=-1):
        args = self.window._scoring_pool.submit.call_args_list[job_index].args
        worker, session_id, number, port, frame, point, received_at, exposure = args
        result = {
            "ok": True, "session_id": session_id, "shot_number": number,
            "port_id": port, "frame": frame, "bullet_point": point,
            "received_at": received_at, "exposure": exposure,
            "metadata": {"class_id": class_id, "hit": hit,
                         "transformed_point": (100, 100)},
        }
        self.window._on_scoring_done(result)

    def test_wrong_target_consumes_round_without_hit_or_close(self):
        for index in range(3):
            self.open_target(index)
        self.receive(143)
        self.complete(3)
        widget = self.window.client_widgets[0]
        self.assertEqual(widget.bullet_count, 1)
        self.assertEqual(widget.hit_targets, set())
        self.assertEqual(self.window.lora.send_command.call_count, 3)
        shot = self.window._review_sessions[1][1][0]
        self.assertFalse(shot["hit"])
        self.assertIn("nhận diện khác bia", shot["status"])

    def test_before_open_at_seven_seconds_and_after_early_close_do_not_hit(self):
        self.receive(114.999)
        self.complete(1)
        self.open_target(0)
        self.receive(122)
        self.complete(1)
        self.open_target(1)
        self.receive(133)
        self.complete(0)
        self.receive(133.001)
        self.complete(0)
        widget = self.window.client_widgets[0]
        self.assertEqual(widget.bullet_count, 4)
        self.assertEqual([shot[3] for shot in widget.shots], [False, False, True, False])
        self.assertEqual(widget.hit_targets, {0})
        self.window.lora.send_command.assert_called_with("@222#")

    def test_delayed_results_use_receipt_window_and_do_not_close_later_target(self):
        self.open_target(0)
        self.receive(121.999)
        self.open_target(1)
        self.complete(1)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {1})
        self.assertEqual(self.window.lora.send_command.call_count, 2)
        self.assertEqual(self.window._shooting_session.active_target(133).class_id, 0)

    def test_multiple_pedestals_without_auto_close_keep_window_open(self):
        self.window.automatic_close_target_enabled = False
        self.open_target(0)
        self.receive(116)
        self.complete(1)
        self.receive(117)
        self.complete(1)
        self.assertEqual(self.window.lora.send_command.call_count, 1)
        self.assertEqual(self.window.client_widgets[0].bullet_count, 2)
        self.assertIsNotNone(self.window._shooting_session.active_target(121.999))

    def test_queued_burst_before_early_close_still_counts_all_hits(self):
        self.open_target(0)
        self.receive(116)
        self.receive(116.2)
        self.clock.return_value = 117
        self.complete(1, job_index=0)
        self.complete(1, job_index=1)
        self.assertEqual(self.window.client_widgets[0].bullet_count, 2)
        self.assertEqual([shot[3] for shot in self.window.client_widgets[0].shots], [True, True])
        self.assertEqual(self.window.lora.send_command.call_count, 2)
        self.assertIsNone(self.window._shooting_session.active_target(117))

    def test_deadline_rejects_new_shots_but_counts_pending_result(self):
        for index in range(4):
            self.open_target(index)
        self.receive(170.999)
        self.clock.return_value = 175
        self.window.update_app()
        self.assertFalse(self.window.testing)
        self.assertFalse(self.window._test_timeout_timer.isActive())
        self.assertTrue(self.window.setting_btn.isEnabled())
        self.assertFalse(self.receive(175))
        self.complete(3)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {3})
        self.assertEqual(self.window.client_widgets[0].bullet_count, 1)
        self.assertTrue(self.window._review_sessions[1][1][0]["hit"])
        self.assertEqual(self.window.lora.send_command.call_count, 4)

    def test_receipt_enforces_deadline_even_before_timer_callback(self):
        self.assertFalse(self.receive(175))
        self.assertFalse(self.window.testing)
        self.window._scoring_pool.submit.assert_not_called()
        self.window._shot_sound.play.assert_not_called()

    def test_timeout_timer_stops_and_cancels_lora_without_status_refresh(self):
        self.assertEqual(self.window._test_timeout_timer.interval(), 75000)
        self.window._schedule_lora_script()
        self.window.timer.stop()
        self.clock.return_value = 175
        self.window._test_timeout_timer.start(1)
        QTest.qWait(30)
        self.assertFalse(self.window.testing)
        self.assertEqual(self.window._lora_schedule_timers, [])
        self.assertFalse(self.window.client_widgets[0].testing)

    def test_restart_discards_old_job_and_resets_visibility(self):
        self.open_target(0)
        self.receive(116)
        self.window.stop_test()
        self.clock.return_value = 180
        self.window.start_test()
        self.complete(1)
        self.assertEqual(self.window.client_widgets[0].bullet_count, 0)
        self.assertEqual(self.window._review_sessions, {2: {1: []}})
        self.assertIsNone(self.window._shooting_session.active_target(180))
        self.assertEqual(self.window._auto_closed_target_classes, set())

    def test_each_shot_plays_once_before_inference_including_misses(self):
        for at in (110, 111, 112):
            self.receive(at)
        self.assertEqual(self.window._shot_sound.play.call_count, 3)
        self.assertEqual(self.window._scoring_pool.submit.call_count, 3)
        for job_index in range(3):
            self.complete(3, job_index=job_index)
        self.assertEqual(self.window._shot_sound.play.call_count, 3)

    def test_settings_cannot_raise_another_target_during_exercise(self):
        self.assertFalse(self.window.setting_btn.isEnabled())
        with patch("gui.main_window.SettingWindow") as dialog:
            self.window.open_setting_window()
        dialog.assert_not_called()
        self.window.lora.send_command.assert_not_called()


class ShotSoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_burst_uses_independent_players_and_close_stops_all(self):
        with patch("gui.shot_sound.QMediaPlayer") as factory:
            players = [MagicMock() for _ in range(8)]
            factory.side_effect = players
            sound = ShotSound()
            for _ in range(3):
                sound.play()
            for player in players[:3]:
                player.play.assert_called_once()
            for player in players[3:]:
                player.play.assert_not_called()
            source = players[0].setMedia.call_args.args[0].canonicalUrl().toLocalFile()
            self.assertTrue(os.path.isfile(source))
            self.assertTrue(source.endswith("TN.mp3"))
            sound.stop()
            for player in players:
                player.stop.assert_called()


if __name__ == "__main__":
    unittest.main()
