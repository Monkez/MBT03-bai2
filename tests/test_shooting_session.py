import os
import unittest
from unittest.mock import MagicMock, call, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

import config as cf
from gui.main_window import MainWindow, _configured_lora_script
from gui.shot_sound import ShotSound
from gui.shooting_session import ShootingSession


class ShootingSessionTests(unittest.TestCase):
    def test_serial_queue_delay_moves_window_to_actual_raise(self):
        session = ShootingSession(100, (15, 32, 42, 64))
        session.open_target(1, 115)
        exposure = session.active_target(116)
        self.assertTrue(session.confirm_command_sent(1, 118, raised=True))
        self.assertIsNone(session.active_target(116.999))
        self.assertIs(session.active_target(117), exposure)
        self.assertIs(session.active_target(126.999), exposure)
        self.assertIsNone(session.active_target(127))

    def test_serial_queue_delay_moves_early_close_without_extending_natural_duration(self):
        session = ShootingSession(100)
        session.open_target(1, 115)
        session.close_target(1, 116)
        session.confirm_command_sent(1, 119, raised=False)
        self.assertEqual(session.active_target(120.999).class_id, 1)
        self.assertIsNone(session.active_target(121))
        session.confirm_command_sent(1, 130, raised=False)
        self.assertIsNone(session.active_target(124))

    def test_receipt_before_previous_target_closed_remains_available_after_next_raise(self):
        session = ShootingSession(100)
        session.open_target(1, 115)
        previous = session.active_target(120)
        session.open_target(0, 132)
        self.assertIs(session.active_target(120), previous)
        self.assertIsNone(session.active_target(125))

    def test_invalid_timeline_falls_back_without_shifting_target_identity(self):
        defaults = cf.DEFAULT_CONFIG["shooting"]["lora_timeline"]
        expected = tuple((item["delay_seconds"], item["command"], item["description"])
                         for item in defaults)
        for delays in ((15, 18, 42, 64), (15, 32, 41, 64), (15, 32, 42, 70), (15, 32, 42),
                       (15, 32, float("nan"), 64), (15, 32, float("inf"), 64),
                       (-1, 32, 42, 64)):
            configured = [dict(item, delay_seconds=delay)
                          for item, delay in zip(defaults, delays)]
            with self.subTest(delays=delays), patch("gui.main_window.cf.get_setting", return_value=configured):
                self.assertEqual(_configured_lora_script(), expected)

    def test_exposure_boundaries_sequence_and_gaps(self):
        session = ShootingSession(100)
        self.assertIsNone(session.active_target(114.999))
        for seconds, class_id, duration in ((15, 1, 7), (32, 0, 7), (42, 2, 7), (64, 3, 18)):
            now = 100 + seconds
            self.assertTrue(session.open_target(class_id, now))
            if class_id == 2:
                # A delayed image from 40.999s still belongs to the prior target.
                self.assertEqual(session.active_target(now - 1.001).class_id, 0)
            else:
                self.assertIsNone(session.active_target(now - 1.001))
            self.assertFalse(session.window_for_target(class_id).contains(now - 1.001))
            self.assertEqual(session.active_target(now - 1).class_id, class_id)
            self.assertEqual(session.active_target(now).class_id, class_id)
            self.assertEqual(session.active_target(now + duration + 1.999).class_id, class_id)
            self.assertIsNone(session.active_target(now + duration + 2))
        self.assertFalse(session.expired(184.999))
        self.assertTrue(session.expired(185))
        self.assertFalse(session.open_target(1, 186))

    def test_last_target_timeline_must_fit_visibility_and_late_grace(self):
        for seconds, accepted in ((65, True), (65.001, False)):
            script = [dict(item) for item in cf.DEFAULT_CONFIG["shooting"]["lora_timeline"]]
            script[-1]["delay_seconds"] = seconds
            with self.subTest(seconds=seconds), patch("gui.main_window.cf.get_setting", return_value=script):
                self.assertEqual(_configured_lora_script()[-1][0], seconds if accepted else 64)

    def test_delayed_target_eight_is_capped_at_exercise_deadline(self):
        session = ShootingSession(100)
        for class_id, now in ((1, 115), (0, 132), (2, 142), (3, 180)):
            self.assertTrue(session.open_target(class_id, now))
        self.assertEqual(session.active_target(184.999).class_id, 3)
        self.assertIsNone(session.active_target(185))

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
        self.assertTrue(exposure.contains(118.999))
        self.assertFalse(exposure.contains(119))
        self.assertIsNone(session.active_target(119))
        self.assertFalse(session.close_target(1, 118))

    def test_scheduled_windows_accept_early_shots_and_share_exposure_with_command(self):
        session = ShootingSession(100, (15, 32, 42, 64))
        for class_id, raised_at, end in ((1, 115, 124), (0, 132, 141),
                                         (2, 142, 151), (3, 164, 184)):
            exposure = session.active_target(raised_at - 1)
            self.assertEqual(exposure.class_id, class_id)
            self.assertFalse(exposure.contains(raised_at - 1.001))
            self.assertFalse(session.close_target(class_id, raised_at - 0.5))
            self.assertTrue(session.open_target(class_id, raised_at))
            self.assertIs(exposure, session.exposure)
            self.assertTrue(exposure.contains(end - 0.001))
            self.assertFalse(exposure.contains(end))
            self.assertFalse(session.close_target(class_id, end - 0.5))

    def test_delayed_raise_keeps_pre_command_shot_and_extends_from_actual_raise(self):
        session = ShootingSession(100, (15, 32, 42, 64))
        early = session.active_target(114)
        self.assertIs(session.active_target(115.1), early)
        session.open_target(1, 115.2)
        self.assertIs(session.exposure, early)
        self.assertTrue(early.contains(114))
        self.assertTrue(early.contains(124.199))
        self.assertFalse(early.contains(124.2))


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
        patch("gui.main_window.HitSound").start()
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

    def test_delayed_image_dispatch_uses_server_receipt_before_target_change(self):
        self.open_target(0)
        self.open_target(1)
        self.clock.return_value = 134
        with patch.object(self.window, "_queue_raw_camera_image"):
            self.window._on_shoot_image(1, np.zeros((8, 8, 3), dtype=np.uint8),
                                       {"q0": [.5, .5], "_server_received_at": 123.5})
        self.complete(1)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {1})
        self.assertEqual(self.window._scoring_pool.submit.call_args.args[-2], 123.5)
        self.assertEqual(self.window.lora.send_command.call_count, 2)

    def test_late_serial_confirmation_corrects_a_pending_scoring_result(self):
        self.open_target(0)
        self.receive(125)
        self.assertIsNone(self.window._scoring_pool.submit.call_args.args[-1])
        self.window._on_lora_command_sent("@111#", 115, 118)
        self.complete(1)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {1})

    def test_previous_session_serial_command_does_not_shift_current_window(self):
        self.open_target(0)
        self.window._on_lora_command_sent("@111#", 99, 118)
        self.assertIsNone(self.window._shooting_session.active_target(125))
        self.clock.return_value = 117
        self.window.stop_test()
        self.window._on_lora_command_sent("@111#", 118, 119)
        self.assertIsNone(self.window._shooting_session.active_target(125))

    def test_previous_session_image_does_not_consume_current_round(self):
        with patch.object(self.window, "_queue_raw_camera_image"):
            self.window._on_shoot_image(1, np.zeros((8, 8, 3), dtype=np.uint8),
                                       {"_server_received_at": 99.5})
        self.window._scoring_pool.submit.assert_not_called()

    def test_rejected_hit_reports_receipt_and_target_window_in_review(self):
        self.open_target(0)
        self.receive(125)
        self.complete(1)
        status = self.window._review_sessions[1][1][0]["status"]
        self.assertIn("Nhận ảnh: 25.00s", status)
        self.assertIn("Khoảng nhận: 14.00–24.00s", status)

    def test_image_received_before_stop_is_scored_after_late_ui_dispatch(self):
        self.open_target(0)
        self.clock.return_value = 116
        self.window.stop_test()
        self.clock.return_value = 120
        with patch.object(self.window, "_queue_raw_camera_image"):
            self.window._on_shoot_image(1, np.zeros((8, 8, 3), dtype=np.uint8),
                                       {"_server_received_at": 115.5})
        self.complete(1)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {1})
        self.assertEqual(self.window._scoring_pool.submit.call_count, 1)
        with patch.object(self.window, "_queue_raw_camera_image"):
            self.window._on_shoot_image(1, np.zeros((8, 8, 3), dtype=np.uint8),
                                       {"_server_received_at": 116.01})
        self.assertEqual(self.window._scoring_pool.submit.call_count, 1)

    def test_image_received_before_deadline_is_scored_after_timeout(self):
        for index in range(4):
            self.open_target(index)
        self.clock.return_value = 185
        self.window.stop_test()
        self.clock.return_value = 188
        with patch.object(self.window, "_queue_raw_camera_image"):
            self.window._on_shoot_image(1, np.zeros((8, 8, 3), dtype=np.uint8),
                                       {"_server_received_at": 183.5})
        self.complete(3)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {3})

    def test_start_sends_followup_once_after_delay_to_each_server(self):
        self.window.stop_test()
        self.window.servers = [MagicMock(), MagicMock()]
        self.window.start_test()
        timer = self.window._start_followup_timer
        self.assertEqual(timer.interval(), 300)
        for server in self.window.servers:
            server.send_uart_command.assert_called_once_with("0F016\n")
        self.assertTrue(QSignalSpy(timer.timeout).wait(1000))
        for server in self.window.servers:
            self.assertEqual(server.send_uart_command.call_args_list,
                             [call("0F016\n"), call("0A000\n")])
        self.assertFalse(timer.isActive())

    def test_stop_cancels_followup_and_restart_schedules_new_one(self):
        self.window.servers = [MagicMock()]
        timer = self.window._start_followup_timer
        self.assertTrue(timer.isActive())
        self.window.stop_test()
        self.assertFalse(timer.isActive())
        self.window._send_start_followup_command()
        self.window.servers[0].send_uart_command.assert_called_once_with("0S000\n")
        self.window.start_test()
        self.assertTrue(QSignalSpy(timer.timeout).wait(1000))
        self.assertEqual(self.window.servers[0].send_uart_command.call_args_list,
                         [call("0S000\n"), call("0F016\n"), call("0A000\n")])

    def test_close_cancels_followup(self):
        self.window.servers = [MagicMock()]
        self.window.close()
        self.window._hit_sound.stop.assert_called_once_with()
        self.assertFalse(self.window._start_followup_timer.isActive())
        self.window._send_start_followup_command()
        self.window.servers[0].send_uart_command.assert_called_once_with("0S000\n")

    def test_manual_and_automatic_stop_send_stop_command_to_all_servers_once(self):
        for automatic in (False, True):
            with self.subTest(automatic=automatic):
                self.window.servers = [MagicMock(), MagicMock()]
                if automatic:
                    self.clock.return_value = 185
                    self.window.update_app()
                else:
                    self.window.start_btn_clicked()
                self.window.stop_test()
                for server in self.window.servers:
                    server.send_uart_command.assert_called_once_with("0S000\n")
                if not automatic:
                    self.window.start_test()

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

    def test_outside_grace_windows_and_after_early_close_do_not_hit(self):
        self.receive(113.999)
        self.complete(1)
        self.open_target(0)
        self.receive(124)
        self.complete(1)
        self.open_target(1)
        self.receive(133)
        self.complete(0)
        self.receive(135)
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

    def test_early_hit_is_scored_before_raise_without_sending_premature_close(self):
        self.receive(114)
        self.complete(1)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {1})
        self.window.lora.send_command.assert_not_called()
        self.open_target(0)
        self.window.lora.send_command.assert_called_once_with("@111#")

    def test_early_result_arriving_after_raise_retains_its_window(self):
        self.receive(114)
        self.open_target(0)
        self.complete(1)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {1})
        self.window.lora.send_command.assert_called_with("@112#")

    def test_two_seconds_after_early_close_counts_without_resending_close(self):
        self.open_target(0)
        for received_at in (116, 117.999, 118):
            self.receive(received_at)
            self.complete(1)
        self.assertEqual([shot[3] for shot in self.window.client_widgets[0].shots],
                         [True, True, False])
        self.assertEqual(self.window.lora.send_command.call_args_list,
                         [call("@111#"), call("@112#")])

    def test_adjacent_grace_windows_route_boundary_to_next_target(self):
        self.window.automatic_close_target_enabled = False
        self.open_target(0)
        self.open_target(1)
        for received_at, class_id in ((140.999, 0), (141, 0), (141, 2)):
            self.receive(received_at)
            self.complete(class_id)
        self.assertEqual([shot[3] for shot in self.window.client_widgets[0].shots],
                         [True, False, True])
        self.assertEqual(self.window.lora.send_command.call_count, 2)

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
        self.assertIsNotNone(self.window._shooting_session.active_target(118.999))
        self.assertIsNone(self.window._shooting_session.active_target(119))

    def test_deadline_rejects_new_shots_but_counts_pending_result(self):
        for index in range(4):
            self.open_target(index)
        self.receive(183.999)
        self.clock.return_value = 185
        self.window.update_app()
        self.assertFalse(self.window.testing)
        self.assertFalse(self.window._test_timeout_timer.isActive())
        self.assertTrue(self.window.setting_btn.isEnabled())
        self.assertFalse(self.receive(185))
        self.complete(3)
        self.assertEqual(self.window.client_widgets[0].hit_targets, {3})
        self.assertEqual(self.window.client_widgets[0].bullet_count, 1)
        self.assertTrue(self.window._review_sessions[1][1][0]["hit"])
        self.assertEqual(self.window.lora.send_command.call_count, 4)

    def test_receipt_enforces_deadline_even_before_timer_callback(self):
        self.assertFalse(self.receive(185))
        self.assertFalse(self.window.testing)
        self.window._scoring_pool.submit.assert_not_called()
        self.window._shot_sound.play.assert_not_called()

    def test_target_eight_scores_until_twenty_seconds_including_late_grace(self):
        self.window.automatic_close_target_enabled = False
        for index in range(4):
            self.open_target(index)
        for received_at in (171, 175, 181.999, 182, 183.999, 184):
            self.assertTrue(self.receive(received_at))
            self.complete(3)
        self.assertEqual([shot[3] for shot in self.window.client_widgets[0].shots],
                         [True, True, True, True, True, False])
        self.clock.return_value = 184.999
        self.window.update_app()
        self.assertTrue(self.window.testing)
        self.clock.return_value = 185
        self.window.update_app()
        self.assertFalse(self.window.testing)

    def test_timeout_timer_stops_and_cancels_lora_without_status_refresh(self):
        self.assertEqual(self.window._test_timeout_timer.interval(), 85000)
        self.window._schedule_lora_script()
        self.window.timer.stop()
        self.clock.return_value = 185
        timeout = QSignalSpy(self.window._test_timeout_timer.timeout)
        self.window._test_timeout_timer.start(1)
        self.assertTrue(timeout.wait(1000), "Exercise timeout signal was not delivered")
        self.assertFalse(self.window.testing)
        self.assertEqual(self.window._lora_schedule_timers, [])
        self.assertFalse(self.window.client_widgets[0].testing)

    def test_restart_discards_old_job_and_resets_visibility(self):
        self.open_target(0)
        self.receive(116)
        self.window.stop_test()
        self.clock.return_value = 180
        self.window.start_test()
        self.assertEqual(self.window._hit_sound.reset.call_count, 2)
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
