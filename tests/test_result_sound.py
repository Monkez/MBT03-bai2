import itertools
import io
import os
import time
import unittest
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import soundfile as sf

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtMultimedia import QMediaPlayer
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.result_sound import ResultSound


def wait_for_playback(sound):
    deadline = time.monotonic() + 3
    while not sound._playing and sound.port_id is not None and time.monotonic() < deadline:
        QTest.qWait(5)
    if not sound._playing:
        raise AssertionError("The sentence did not reach playback")


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
        self.sources = []
        original_read = ResultSound._read_pcm
        def read_pcm(path):
            self.sources.append(os.path.basename(path))
            return original_read(path)
        patch.object(ResultSound, "_read_pcm", side_effect=read_pcm).start()
        self.player.play.side_effect = self.capture_playback

    def capture_playback(self):
        path = self.player.setMedia.call_args.args[0].canonicalUrl().toLocalFile()
        with open(path, "rb") as audio:
            self.played.append((path, audio.read()))

    def test_all_pedestals_and_ranks_use_one_continuous_pcm_file(self):
        changes = QSignalSpy(self.sound.changed)
        failures = QSignalSpy(self.sound.failed)
        for port, rank in itertools.product(range(1, 5), ResultSound.RANK_FILES):
            self.played.clear()
            self.sources.clear()
            self.player.reset_mock()
            self.sound.start(port, rank)
            wait_for_playback(self.sound)
            self.assertEqual(self.sources, [f"Beso{port}.mp3", ResultSound.RANK_FILES[rank]])
            self.assertEqual(len(self.played), 1)
            self.player.setMedia.assert_called_once()
            self.player.stop.assert_not_called()
            path, data = self.played[0]
            with wave.open(io.BytesIO(data), "rb") as wav:
                self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()),
                                 (44100, 2, 2))
                self.assertGreater(wav.getnframes(), 44100 * 3)
            self.sound._on_status(QMediaPlayer.EndOfMedia)
            self.assertIsNone(self.sound.port_id)
            self.assertFalse(os.path.exists(path))
        self.assertEqual(len(changes), 32)
        self.assertEqual(len(failures), 0)
        self.player.setPlaybackRate.assert_called_with(1.0)

    def test_stop_while_decoding_cancels_old_sentence_and_can_restart(self):
        self.sound.start(1, "Khá")
        self.sound.stop()
        self.assertEqual(self.played, [])
        self.sources.clear()
        self.sound.start(2, "Giỏi")
        wait_for_playback(self.sound)
        self.assertEqual(self.sources, ["Beso2.mp3", "GIOI.mp3"])
        self.assertEqual(len(self.played), 1)
        path = self.played[0][0]
        self.sound.stop()
        self.assertFalse(os.path.exists(path))

    def test_stop_cancels_queued_preparation_without_decoding_either_phrase(self):
        self.sound.start(1, "Khá")
        self.assertTrue(self.sound._prepare_timer.isActive())
        self.sound.stop()
        QTest.qWait(20)
        self.assertEqual(self.played, [])
        self.assertEqual(self.sources, [])
        self.assertIsNone(self.sound.port_id)

    def test_busy_and_invalid_requests_do_not_replace_playback(self):
        for port, rank in ((0, "Khá"), (5, "Khá"), (1, "Unknown")):
            self.sound.start(port, rank)
        self.assertEqual(self.played, [])
        self.sound.start(1, "Khá")
        self.sound.start(2, "Giỏi")
        wait_for_playback(self.sound)
        self.assertEqual(self.sources, ["Beso1.mp3", "KHA.mp3"])
        self.assertEqual(len(self.played), 1)

    def test_decode_failure_aborts_whole_sentence_and_restores_idle(self):
        failures = QSignalSpy(self.sound.failed)
        with patch("gui.result_sound.sf.read", side_effect=sf.SoundFileError("corrupt audio")):
            self.sound.start(1, "Khá")
            self.assertTrue(failures.wait(3000))
        self.assertIsNone(self.sound.port_id)
        self.assertEqual(self.played, [])
        self.assertEqual(len(failures), 1)
        self.sound.start(2, "Đạt")
        wait_for_playback(self.sound)
        self.assertEqual(len(self.played), 1)

    def test_missing_audio_and_synchronous_load_failure_never_play_rank_alone(self):
        failures = QSignalSpy(self.sound.failed)
        with patch("gui.result_sound.sf.read", side_effect=FileNotFoundError("missing audio")):
            self.sound.start(1, "Khá")
            self.assertTrue(failures.wait(3000))
        self.assertIsNone(self.sound.port_id)
        self.assertEqual(self.played, [])
        self.player.setMedia.side_effect = lambda _: self.sound._on_error(QMediaPlayer.ResourceError)
        self.sound.start(1, "Khá")
        deadline = time.monotonic() + 3
        while self.sound.port_id is not None and time.monotonic() < deadline:
            QTest.qWait(5)
        self.assertEqual(self.played, [])
        self.assertIsNone(self.sound.port_id)
        self.assertEqual(len(failures), 2)

    def test_missing_second_clip_never_plays_only_pedestal_name(self):
        failures = QSignalSpy(self.sound.failed)
        original = sf.read
        def read(path, **kwargs):
            if path.endswith("KHA.mp3"):
                raise FileNotFoundError(path)
            return original(path, **kwargs)
        with patch("gui.result_sound.sf.read", side_effect=read):
            self.sound.start(1, "Khá")
            self.assertTrue(failures.wait(3000))
        self.assertEqual(self.played, [])
        self.assertIsNone(self.sound.port_id)

    def test_cannot_create_temp_file_restores_idle(self):
        failures = QSignalSpy(self.sound.failed)
        with patch("gui.result_sound.tempfile.TemporaryDirectory", side_effect=OSError("disk full")):
            self.sound.start(1, "Khá")
            self.assertTrue(failures.wait(3000))
        self.assertEqual(self.played, [])
        self.assertIsNone(self.sound.port_id)

    def test_pcm_join_has_silence_and_smooth_edges_without_changing_phrase_levels(self):
        first = np.full((2000, 2), 10000, dtype="<i2")
        second = np.full((3000, 2), -8000, dtype="<i2")
        data = ResultSound._sentence_wav([first.tobytes(), second.tobytes()])
        gap_frames = ResultSound.SAMPLE_RATE * ResultSound.GAP_MS // 1000
        with wave.open(io.BytesIO(data), "rb") as wav:
            self.assertEqual(wav.getnframes(), 5000 + gap_frames)
            joined = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").reshape(-1, 2)
        np.testing.assert_array_equal(joined[220:1780], first[220:1780])
        np.testing.assert_array_equal(joined[2000:2000+gap_frames], 0)
        np.testing.assert_array_equal(joined[2000+gap_frames+220:-220], second[220:-220])
        np.testing.assert_array_equal(joined[[0, 1999, 2000+gap_frames, -1]], 0)
        self.assertLess(np.max(np.abs(np.diff(joined.astype(int), axis=0))), 50)

    def test_mono_22050_conversion_preserves_duration_channels_and_sample_levels(self):
        original = np.arange(-1000, 1000, dtype="int16").reshape(-1, 1)
        # Use the real conversion, bypassing only file decoding.
        with patch("gui.result_sound.sf.read", return_value=(original, 22050)):
            pcm = self.sound._read_pcm("mono.wav")
        converted = np.frombuffer(pcm, dtype="<i2").reshape(-1, 2)
        self.assertEqual(len(converted), len(original) * 2)
        np.testing.assert_array_equal(converted[:, 0], converted[:, 1])
        np.testing.assert_array_equal(converted[::2, 0], original[:, 0])


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
        self.read_pcm = patch.object(ResultSound, "_read_pcm", wraps=ResultSound._read_pcm).start()
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
        wait_for_playback(self.window._result_sound)
        self.assertTrue(self.read_pcm.call_args.args[0].endswith("KHA.mp3"))
        path = self.window._result_sound._player.setMedia.call_args.args[0].canonicalUrl().toLocalFile()
        self.assertEqual(os.path.basename(path), "result.wav")
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
