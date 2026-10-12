import itertools
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtMultimedia import QMediaPlayer
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.result_sound import ResultSound


class ResultSoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        factory = patch("gui.result_sound.QMediaPlayer", wraps=QMediaPlayer).start()
        self.addCleanup(patch.stopall)
        factory.EndOfMedia = QMediaPlayer.EndOfMedia
        factory.NoError = QMediaPlayer.NoError
        self.player = factory.return_value = MagicMock()
        self.sound = ResultSound()
        self.addCleanup(self.sound.stop)
        self.played = []
        self.player.play.side_effect = lambda: self.played.append(
            os.path.basename(self.player.setMedia.call_args.args[0].canonicalUrl().toLocalFile())
        )

    def finish_clip(self):
        self.sound._on_status(QMediaPlayer.EndOfMedia)
        self.app.processEvents()

    def test_all_pedestals_and_ranks_read_name_then_rank_once(self):
        changes = QSignalSpy(self.sound.changed)
        failures = QSignalSpy(self.sound.failed)
        for port, rank in itertools.product(range(1, 5), ResultSound.RANK_FILES):
            self.played.clear()
            self.sound.start(port, rank)
            self.assertEqual(self.played, [f"Beso{port}.mp3"])
            self.finish_clip()
            self.assertEqual(self.played, [f"Beso{port}.mp3", ResultSound.RANK_FILES[rank]])
            self.finish_clip()
            self.assertIsNone(self.sound.port_id)
        self.assertEqual(len(changes), 32)
        self.assertEqual(len(failures), 0)
        self.player.setPlaybackRate.assert_called_with(1.0)

    def test_stop_between_clips_cancels_timer_and_can_restart(self):
        self.sound.start(1, "Khá")
        self.sound._on_status(QMediaPlayer.EndOfMedia)
        self.sound.stop()
        self.sound.start(2, "Giỏi")
        self.app.processEvents()
        self.assertEqual(self.played, ["Beso1.mp3", "Beso2.mp3"])
        self.finish_clip()
        self.assertEqual(self.played[-1], "GIOI.mp3")

    def test_busy_and_invalid_requests_do_not_replace_playback(self):
        for port, rank in ((0, "Khá"), (5, "Khá"), (1, "Unknown")):
            self.sound.start(port, rank)
        self.assertEqual(self.played, [])
        self.sound.start(1, "Khá")
        self.sound.start(2, "Giỏi")
        self.finish_clip()
        self.assertEqual(self.played, ["Beso1.mp3", "KHA.mp3"])

    def test_decode_failure_aborts_whole_sentence_and_restores_idle(self):
        failures = QSignalSpy(self.sound.failed)
        self.sound.start(1, "Khá")
        self.sound._on_error(QMediaPlayer.ResourceError)
        self.finish_clip()
        self.assertIsNone(self.sound.port_id)
        self.assertEqual(self.played, ["Beso1.mp3"])
        self.assertEqual(len(failures), 1)
        self.sound.start(2, "Đạt")
        self.assertEqual(self.played[-1], "Beso2.mp3")

    def test_missing_audio_and_synchronous_load_failure_never_play_rank_alone(self):
        failures = QSignalSpy(self.sound.failed)
        with patch("gui.result_sound.os.path.isfile", return_value=False):
            self.sound.start(1, "Khá")
        self.assertIsNone(self.sound.port_id)
        self.assertEqual(self.played, [])
        self.player.setMedia.side_effect = lambda _: self.sound._on_error(QMediaPlayer.ResourceError)
        self.sound.start(1, "Khá")
        self.app.processEvents()
        self.assertEqual(self.played, [])
        self.assertIsNone(self.sound.port_id)
        self.assertEqual(len(failures), 2)


class ResultFlowTests(unittest.TestCase):
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
        patch("gui.main_window.ShotSound").start()
        patch("gui.main_window.HitSound").start()
        factory = patch("gui.result_sound.QMediaPlayer", wraps=QMediaPlayer).start()
        factory.EndOfMedia = QMediaPlayer.EndOfMedia
        factory.NoError = QMediaPlayer.NoError
        factory.return_value = MagicMock()
        self.window = MainWindow()
        self.window.servers = [MagicMock(), MagicMock()]
        self.addCleanup(self.window.close)

    def test_all_target_combinations_and_repeated_hits_use_target_eight_rule(self):
        widget = self.window.client_widgets[0]
        for size in range(5):
            for targets in itertools.combinations(range(4), size):
                widget.start_test()
                for target in targets:
                    widget.record_shot(target, .5, .5)
                    widget.record_shot(target, .5, .5)
                widget.record_miss()
                expected = ("Giỏi" if size == 4 else "Khá" if size == 3 and 3 in targets
                            else "Đạt" if size >= 2 else "Không đạt")
                self.assertEqual(widget._rank_text(), expected, targets)
                self.assertIn(f'>{expected}</span>', widget.result_label.text())
                widget.stop_test()
                self.assertEqual(widget._rank_text(), expected)

    def test_speaker_reads_displayed_rank_and_only_selected_gun_receives_command(self):
        first, second = self.window.client_widgets
        for target in (0, 1, 3):
            first.record_shot(target, .5, .5)
        first.score_speak_icon.click()
        self.assertEqual(self.window._result_sound.port_id, 1)
        self.window.servers[0].send_uart_command.assert_called_once_with("0P000\n")
        self.window.servers[1].send_uart_command.assert_not_called()
        self.assertTrue(first.score_speak_icon.isEnabled())
        self.assertFalse(second.score_speak_icon.isEnabled())
        self.window.request_score_speak(2)
        self.assertEqual(self.window._result_sound.port_id, 1)
        self.window._result_sound._on_status(QMediaPlayer.EndOfMedia)
        self.app.processEvents()
        path = self.window._result_sound._player.setMedia.call_args.args[0].canonicalUrl().toLocalFile()
        self.assertEqual(os.path.basename(path), "KHA.mp3")
        self.window._result_sound._on_status(QMediaPlayer.EndOfMedia)
        self.app.processEvents()
        self.assertTrue(second.score_speak_icon.isEnabled())
        self.assertIsNone(self.window._result_sound.port_id)

    def test_toggle_restart_exercise_and_close_cancel_result_audio(self):
        first, second = self.window.client_widgets
        first.score_speak_icon.click()
        first.score_speak_icon.click()
        self.assertIsNone(self.window._result_sound.port_id)
        self.assertTrue(second.score_speak_icon.isEnabled())
        first.score_speak_icon.click()
        self.window.start_test()
        self.assertIsNone(self.window._result_sound.port_id)
        self.assertFalse(first.score_speak_icon.isEnabled())
        self.window.request_score_speak(1)
        self.assertIsNone(self.window._result_sound.port_id)
        self.window.stop_test()
        self.assertTrue(first.score_speak_icon.isEnabled())
        second.score_speak_icon.click()
        self.window.close()
        self.assertIsNone(self.window._result_sound.port_id)


if __name__ == "__main__":
    unittest.main()
