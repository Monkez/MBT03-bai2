import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtMultimedia import QMediaPlayer
from PyQt5.QtWidgets import QApplication

import config as cf
from gui.hit_sound import HitSound
from gui.main_window import MainWindow
from gui.shooting_session import TargetExposure


class HitSoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        factory = patch("gui.hit_sound.QMediaPlayer", wraps=QMediaPlayer).start()
        factory.EndOfMedia = QMediaPlayer.EndOfMedia
        factory.NoError = QMediaPlayer.NoError
        self.addCleanup(patch.stopall)
        patch.object(cf, "APP_CONFIG", cf.DEFAULT_CONFIG).start()
        self.player = factory.return_value = MagicMock()
        self.sound = HitSound()
        self.addCleanup(self.sound.stop)
        self.played = []
        self.player.play.side_effect = lambda: self.played.append(
            self.player.setMedia.call_args.args[0].canonicalUrl().toLocalFile()
        )

    def drain(self):
        for _ in range(20):
            self.sound._on_status(QMediaPlayer.EndOfMedia)
            self.app.processEvents()

    def test_playback_rate_loaded_from_config_with_defaults_and_limits(self):
        for value, expected in ((1.5, 1.5), (2, 2.0), (2.0, 2.0),
                                (0, 0.5), (-1.0, 0.5), (10.0, 4.0),
                                ("fast", 1.75), (True, 1.75), (None, 1.75)):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, "config.json")
                with open(path, "w", encoding="utf-8") as file:
                    json.dump({"shooting": {"hit_announcement_playback_rate": value}}, file)
                with patch.object(cf, "APP_CONFIG", cf.load_app_config(path)):
                    sound = HitSound()
                    sound.announce(1, 0)
                    self.player.setPlaybackRate.assert_called_with(expected)
                    sound.stop()
        with patch.object(cf, "APP_CONFIG", {}):
            sound = HitSound()
            sound.announce(1, 0)
            self.player.setPlaybackRate.assert_called_with(1.75)
            sound.stop()

    def test_burst_reads_each_pair_once_and_queues_all_four_pedestals(self):
        for target in (1, 0, 2, 3):
            for port in (2, 1, 4, 3):
                for _ in range(3):
                    self.sound.announce(port, target)
        self.assertEqual(len(self.played), 1, "Voices must not overlap")
        self.drain()
        self.assertEqual([os.path.basename(path) for path in self.played],
                         [f"{port}.mp3" for port in (2, 1, 4, 3)] * 4)
        self.assertTrue(all(os.path.isfile(path) for path in self.played))
        self.assertEqual(self.player.setPlaybackRate.call_count, 16)
        self.assertTrue(all(args.args == (1.75,)
                            for args in self.player.setPlaybackRate.call_args_list))
        self.sound.announce(2, 1)
        self.assertEqual(len(self.played), 16)

    def test_reset_cancels_old_queue_and_allows_same_pair_again(self):
        self.sound.announce(1, 0)
        self.sound.announce(2, 0)
        self.sound._on_status(QMediaPlayer.EndOfMedia)
        self.sound.reset()
        self.app.processEvents()
        self.assertEqual(len(self.played), 1)
        self.sound.announce(1, 0)
        self.drain()
        self.assertEqual([os.path.basename(path) for path in self.played], ["1.mp3"] * 2)

    def test_stop_cancels_queue_and_ignores_late_results(self):
        self.sound.announce(1, 0)
        self.sound.announce(2, 0)
        self.sound.stop()
        self.sound.announce(3, 0)
        self.drain()
        self.assertEqual(len(self.played), 1)
        self.player.stop.assert_called()

    def test_audio_failure_does_not_block_following_notification(self):
        self.sound.announce(1, 0)
        self.sound.announce(2, 0)
        self.sound._on_error(QMediaPlayer.ResourceError)
        self.app.processEvents()
        self.assertEqual([os.path.basename(path) for path in self.played], ["1.mp3", "2.mp3"])

    def window(self, count=4):
        return SimpleNamespace(
            testing=True, _active_review_session_id=1, _previous_review_session_id=None,
            client_widgets=[MagicMock() for _ in range(count)],
            _store_review_shot=MagicMock(), _reference_images={},
            _maybe_close_hit_target=MagicMock(), _hit_sound=self.sound,
        )

    def result(self, port=1, target=1, hit=True, **changes):
        return dict({
            "ok": True, "session_id": 1, "port_id": port,
            "received_at": 116, "exposure": TargetExposure(1, 115, 122),
            "metadata": {"class_id": target, "hit": hit},
        }, **changes)

    def test_scoring_accepts_distinct_pedestals_and_filters_invalid_hits(self):
        window = self.window()
        for result in (
            self.result(hit=False), self.result(target=0),
            self.result(received_at=122), self.result(exposure=None),
            self.result(ok=False), self.result(session_id=99), self.result(port=5),
        ):
            MainWindow._on_scoring_done(window, result)
        self.assertEqual(self.played, [])
        for port in (3, 1, 3, 2, 4, 1):
            MainWindow._on_scoring_done(window, self.result(port=port))
        self.drain()
        self.assertEqual([os.path.basename(path) for path in self.played],
                         ["3.mp3", "1.mp3", "2.mp3", "4.mp3"])

    def test_single_pedestal_does_not_read_number(self):
        MainWindow._on_scoring_done(self.window(count=1), self.result())
        self.assertEqual(self.played, [])

    def test_pending_valid_result_after_end_still_announces_once(self):
        window = self.window(count=2)
        window.testing = False
        window._active_review_session_id = None
        window._previous_review_session_id = 1
        MainWindow._on_scoring_done(window, self.result())
        MainWindow._on_scoring_done(window, self.result())
        self.drain()
        self.assertEqual(len(self.played), 1)


if __name__ == "__main__":
    unittest.main()
