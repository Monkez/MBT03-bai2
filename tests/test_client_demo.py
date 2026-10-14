import contextlib
import io
import os
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import client_demo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PyQt5.QtWidgets import QApplication
from server_client.demo_client import ClientDemoWindow


class ClientDemoEntryPointTests(unittest.TestCase):
    def test_entry_point_loads_current_shared_demo(self):
        demo_main = client_demo._load_demo_main()

        self.assertEqual(demo_main.__module__, "server_client.demo_client")

    def test_help_uses_root_entry_point_name_without_starting_gui(self):
        output = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["client_demo.py", "--help"]),
            contextlib.redirect_stdout(output),
        ):
            result = client_demo.main()

        self.assertIsNone(result)
        self.assertIn("python client_demo.py", output.getvalue())


class ClientDemoPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with mock.patch.object(ClientDemoWindow, "_start_client"):
            self.window = ClientDemoWindow()
        self.window.preview_timer.stop()
        self.window.client = SimpleNamespace(q0_value=[0.5, 0.5], is_streaming=False,
                                             stop=mock.Mock(), _capture_frame=mock.Mock(),
                                             camera_index=0, camera_backend="auto",
                                             set_camera_index=mock.Mock(), set_camera_backend=mock.Mock())
        self.addCleanup(self.window.close)

    def test_overlay_uses_current_q0_without_changing_capture(self):
        frame = np.full((320, 480, 3), 90, dtype=np.uint8)
        original = frame.copy()
        self.window.client.q0_value = [0.6, 0.4]
        self.window._show_frame(frame)
        np.testing.assert_array_equal(frame, original)
        text = self.window.camera_preview.accessibleDescription()
        self.assertIn("X=0.6000  Y=0.4000", text)
        self.assertIn("dX=+10.00%  dY=-10.00%", text)
        # The reticle is on the scaled camera position, not the frame center.
        image = self.window.camera_preview.pixmap().toImage()
        color = image.pixelColor(round(image.width() * .6), round(image.height() * .4))
        self.assertEqual(color.name(), "#00ff80")
        source = self.window._preview_source_pixmap.toImage()
        self.assertEqual(source.pixelColor(288, 128).red(), 90)

    def test_q0_updates_while_streaming_without_capturing_again(self):
        self.window._show_frame(np.zeros((320, 480, 3), dtype=np.uint8))
        self.window.client.is_streaming = True
        self.window.client.q0_value = [.4861, .4405]
        self.window._update_local_preview()
        self.window.client._capture_frame.assert_not_called()
        text = self.window.camera_preview.accessibleDescription()
        self.assertIn("X=0.4861  Y=0.4405", text)
        self.assertIn("dX=-1.39%  dY=-5.95%", text)

    def test_high_dpi_keeps_logical_size_and_renders_at_native_resolution(self):
        with mock.patch.object(self.window.camera_preview, "devicePixelRatioF", return_value=2.0):
            self.window._show_frame(np.zeros((320, 480, 3), dtype=np.uint8))
        pixmap = self.window.camera_preview.pixmap()
        self.assertEqual(pixmap.devicePixelRatioF(), 2.0)
        self.assertEqual(pixmap.width() / 2, self.window.camera_preview.contentsRect().width())
        self.assertEqual(pixmap.height() / 2, self.window.camera_preview.contentsRect().height())
        self.assertEqual(pixmap.toImage().pixelColor(pixmap.width() // 2, pixmap.height() // 2).name(),
                         "#00ff80")

    def test_invalid_q0_is_reported_instead_of_showing_a_false_center(self):
        for value in (None, [], [1], [1, 2, 3], [float("nan"), .5], [float("inf"), .5],
                      [1.2, .5], ["bad", .5]):
            with self.subTest(value=value):
                self.window.client.q0_value = value
                self.window._show_frame(np.zeros((240, 320, 3), dtype=np.uint8))
                self.assertIn("Q0: không hợp lệ", self.window.camera_preview.accessibleDescription())
                self.assertFalse(self.window.camera_preview.pixmap().isNull())

    def test_reticle_respects_letterboxing_and_q0_edges(self):
        frame = np.zeros((640, 320, 3), dtype=np.uint8)
        self.window.client.q0_value = [0, 0]
        self.window._show_frame(frame)
        image = self.window.camera_preview.pixmap().toImage()
        left = (image.width() - round(image.height() / 2)) // 2
        self.assertEqual(image.pixelColor(left, 0).name(), "#00ff80")
        self.assertEqual(image.pixelColor(left - 1, 0).name(), "#11111b")
        self.window.client.q0_value = [1, 0]
        self.window._show_frame(frame)
        image = self.window.camera_preview.pixmap().toImage()
        right = left + round(image.height() / 2) - 1
        self.assertEqual(image.pixelColor(right, 0).name(), "#00ff80")

    def test_camera_change_clears_cached_picture(self):
        self.window._show_frame(np.zeros((320, 480, 3), dtype=np.uint8))
        self.window._on_camera_index_changed(1)
        self.assertIsNone(self.window._preview_source_pixmap)
        self.window.client.is_streaming = True
        self.window._update_local_preview()
        self.assertIn("Camera 1", self.window.camera_preview.text())


if __name__ == "__main__":
    unittest.main()
