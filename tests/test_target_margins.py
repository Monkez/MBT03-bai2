import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from gui.client_widget import ClientWidget
from gui.styles import TARGET_GREEN, TARGET_RED


class TargetMarginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = ClientWidget(1)
        self.addCleanup(self.widget.close)
        # Isolate target shading and marker colors from the supplied artwork.
        self.widget._target_images = [np.full((200, 200, 3), (30, 90, 140), np.uint8)
                                      for _ in range(4)]

    def image_area(self, canvas, target):
        x, y, w, h = self.widget._rendered_target_rects[target]
        return canvas[y:y + h, x:x + w]

    def test_sixteen_rounds_fit_left_strip_above_target_in_compact_views(self):
        widget = self.widget
        widget.resize(320, 320)
        widget.set_target_rounds({1: [("single", ((n, "hit" if n % 2 else "miss"),))
                                      for n in range(1, 17)]})
        for state, visible in ((None, ()), ((1, False), ()), ((1, True), (1, 0, 2, 3))):
            widget.set_target_presentation(state, visible_targets=visible)
            image = widget.compose_target_image()
            x, y, w, h = widget._rendered_target_rects[1]
            self.assertGreater(h, 0)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, image.shape[1])
            self.assertLessEqual(y + h, image.shape[0])
            # Both hit and miss fills remain visible independently of target artwork.
            for color in ((88, 155, 26), (73, 57, 223)):
                self.assertTrue(np.any(np.all(image == color, axis=2)))
        widget.reset_results()
        self.assertEqual(widget._target_rounds, {})

    def test_initial_view_is_colored_and_final_unhit_targets_fade_with_red_borders(self):
        widget = self.widget
        initial = widget.compose_target_image()
        self.assertFalse(np.array_equal(self.image_area(initial, 0)[:, :, 0],
                                       self.image_area(initial, 0)[:, :, 1]))
        widget.record_shot(1, .5, .5)
        widget.stop_test()
        final = widget.compose_target_image()
        for target in (0, 2, 3):
            area = self.image_area(final, target)
            np.testing.assert_array_equal(area[:, :, 0], area[:, :, 1])
            np.testing.assert_array_equal(area[:, :, 1], area[:, :, 2])
            self.assertGreaterEqual(area.min(), 214)
        hit = self.image_area(final, 1)
        self.assertFalse(np.array_equal(hit[:, :, 0], hit[:, :, 1]))
        for color in (TARGET_GREEN, TARGET_RED):
            bgr = [int(color[i:i + 2], 16) for i in (5, 3, 1)]
            self.assertGreater(np.count_nonzero(np.all(final == bgr, axis=2)), 100)
        widget.reset_results()
        np.testing.assert_array_equal(widget.compose_target_image(), initial)

    def test_late_valid_hit_changes_its_faded_result_target_back_to_color(self):
        widget = self.widget
        widget.stop_test()
        widget.record_shot(2, .5, .5)
        area = self.image_area(widget.compose_target_image(), 2)
        self.assertFalse(np.array_equal(area[:, :, 0], area[:, :, 1]))
        self.assertEqual(widget.hit_counts, [0, 0, 1, 0])

    def test_artwork_is_ten_percent_smaller_and_centered_in_the_same_frame(self):
        for mode in ("default", "two_pedestals"):
            self.widget.target_layout_mode = mode
            for state in (None, (1, True)):
                self.widget.set_target_presentation(state)
                self.widget.compose_target_image()
                for target, (x, y, w, h) in self.widget._rendered_target_rects.items():
                    left, top, width, height = self.widget._marker_clip_rects[target]
                    self.assertAlmostEqual(w / min(width, height), .9, delta=.01)
                    self.assertAlmostEqual(h / min(width, height), .9, delta=.01)
                    self.assertLessEqual(abs((x + w / 2) - (left + width / 2)), 1)
                    self.assertLessEqual(abs((y + h / 2) - (top + height / 2)), 1)

    def test_nearby_misses_draw_outside_image_at_the_true_position_in_all_views(self):
        widget = self.widget
        for mode in ("default", "two_pedestals"):
            widget.target_layout_mode = mode
            for state in (None, (1, True)):
                for px, py in ((-.03, .5), (1.03, .5), (.5, -.03), (.5, 1.03)):
                    widget.reset_results()
                    widget.set_target_presentation(state)
                    widget.record_shot(1, px, py, hit=False)
                    canvas = widget.compose_target_image()
                    x, y, w, h = widget._rendered_target_rects[1]
                    cx, cy = int(x + px * w), int(y + py * h)
                    self.assertFalse(x <= cx < x + w and y <= cy < y + h)
                    np.testing.assert_array_equal(canvas[cy, cx], (0, 0, 255))
                    self.assertEqual(widget.shots, [(1, px, py, False)])

    def test_far_misses_and_points_over_another_target_do_not_draw_or_clamp(self):
        widget = self.widget
        baseline = widget.compose_target_image()
        x, y, w, h = widget._rendered_target_rects[1]
        other_x, other_y, other_w, other_h = widget._rendered_target_rects[0]
        over_other = ((other_x + other_w / 2 - x) / w,
                      (other_y + other_h / 2 - y) / h)
        for px, py in ((-10, .5), (10, .5), (.5, -10), (.5, 10),
                       (1e308, 1e308), over_other):
            widget.record_shot(1, px, py, hit=False)
            np.testing.assert_array_equal(widget.compose_target_image(), baseline)
        self.assertEqual(widget.bullet_count, 6)
        self.assertEqual(widget.hit_targets, set())

    def test_marker_is_clipped_to_its_frame_even_when_center_is_near_the_edge(self):
        widget = self.widget
        baseline = widget.compose_target_image()
        x, y, w, h = widget._rendered_target_rects[1]
        left, top, width, height = widget._marker_clip_rects[1]
        widget.record_shot(1, (left + 1 - x) / w, .5, hit=False)
        after = widget.compose_target_image()
        changed = np.any(after != baseline, axis=2)
        ys, xs = np.where(changed)
        self.assertGreater(len(xs), 0)
        self.assertTrue(np.all((xs >= left) & (xs < left + width)))
        self.assertTrue(np.all((ys >= top) & (ys < top + height)))

    def test_invalid_marker_coordinates_do_not_lose_ammunition_or_invent_hits(self):
        for point in ((float("nan"), .5), (.5, float("inf")), (None, .5), ("bad", .5)):
            self.widget.record_shot(1, *point, hit=False)
        self.assertEqual(self.widget.bullet_count, 4)
        self.assertEqual(self.widget.shots, [])
        self.assertEqual(self.widget.hit_targets, set())


if __name__ == "__main__":
    unittest.main()
