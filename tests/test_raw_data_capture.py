import os
import re
import tempfile
import unittest
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np

from gui.main_window import MainWindow


class RawDataCaptureTests(unittest.TestCase):
    def test_queue_returns_exact_saved_file_and_copies_frame(self):
        frame = np.full((12, 16, 3), 42, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory, ThreadPoolExecutor(max_workers=1) as pool:
            window = SimpleNamespace(
                _save_raw_data_enabled=True, _raw_image_pool=pool,
                _raw_data_dir=directory, _save_raw_camera_image=MainWindow._save_raw_camera_image,
            )
            save = MainWindow._queue_raw_camera_image(window, 2, frame)
            frame[:] = 255
            path = save.result(timeout=5)
            self.assertTrue(path.endswith("_be_02.png"))
            self.assertEqual(os.listdir(directory), [os.path.basename(path)])
            self.assertTrue(np.all(cv2.imread(path) == 42))

    def test_queue_failure_returns_completed_unsuccessful_save(self):
        pool = MagicMock()
        pool.submit.side_effect = RuntimeError("executor closed")
        window = SimpleNamespace(
            _save_raw_data_enabled=True, _raw_image_pool=pool,
            _raw_data_dir="unused", _save_raw_camera_image=MainWindow._save_raw_camera_image,
        )
        save = MainWindow._queue_raw_camera_image(window, 1, np.zeros((4, 4, 3), dtype=np.uint8))
        self.assertTrue(save.done())
        self.assertIsNone(save.result())

    def test_raw_frame_is_saved_losslessly_with_time_and_pedestal(self):
        frame = np.arange(12 * 16 * 3, dtype=np.uint8).reshape((12, 16, 3))
        captured_at = datetime(2026, 8, 8, 14, 5, 6, 123456)

        with tempfile.TemporaryDirectory() as directory:
            path = MainWindow._save_raw_camera_image(
                directory, 3, frame, captured_at
            )
            loaded = cv2.imread(path, cv2.IMREAD_UNCHANGED)

            self.assertRegex(
                os.path.basename(path),
                re.compile(r"^20260808_140506_123456_be_03\.png$"),
            )
            self.assertTrue(np.array_equal(loaded, frame))

    def test_raw_frame_is_queued_before_q0_returns_early(self):
        frame = np.zeros((12, 16, 3), dtype=np.uint8)
        queue_raw = MagicMock(return_value=True)
        window = SimpleNamespace(
            _queue_raw_camera_image=queue_raw,
            _setting_window=SimpleNamespace(Q0=True),
            _shot_sound=MagicMock(),
        )

        MainWindow._on_shoot_image(window, 2, frame, {})

        queue_raw.assert_called_once_with(2, frame)
        window._shot_sound.play.assert_called_once_with()

    def test_disabled_capture_does_not_queue_a_write(self):
        pool = MagicMock()
        window = SimpleNamespace(
            _save_raw_data_enabled=False,
            _raw_image_pool=pool,
            _raw_data_dir="unused",
        )

        queued = MainWindow._queue_raw_camera_image(
            window, 1, np.zeros((4, 4, 3), dtype=np.uint8)
        )

        self.assertFalse(queued)
        pool.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
