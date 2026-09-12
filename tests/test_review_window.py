import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

import scoring
from gui.main_window import MainWindow
from gui.review_window import REVIEW_CAMERA_ZOOM, ShotReviewDialog, draw_impact_marker


class ReviewWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_impact_marker_changes_pixels_around_point(self):
        image = np.full((240, 320, 3), 255, dtype=np.uint8)
        before = image.copy()

        draw_impact_marker(image, (160, 120))

        self.assertFalse(np.array_equal(image, before))
        self.assertFalse(
            np.array_equal(
                image[100:141, 140:181],
                before[100:141, 140:181],
            )
        )

    def test_review_navigation_stays_inside_shot_range(self):
        shots = [
            {
                "shot_number": number,
                "frame": np.full((240, 320, 3), 220, dtype=np.uint8),
                "camera_point": (0.5, 0.5),
                "target_index": None,
                "target_name": None,
                "target_point": None,
                "hit": None,
                "status": "Test",
            }
            for number in (1, 2, 3)
        ]
        dialog = ShotReviewDialog(1, shots)

        dialog.show_previous()
        self.assertEqual(dialog.current_index, 0)
        dialog.show_last()
        self.assertEqual(dialog.current_index, 2)
        dialog.show_next()
        self.assertEqual(dialog.current_index, 2)
        dialog.show_first()
        self.assertEqual(dialog.current_index, 0)
        dialog.close()

    def test_detection_boxes_are_drawn_and_selected_box_is_distinct(self):
        image = np.full((300, 400, 3), 255, dtype=np.uint8)
        before = image.copy()
        detections = [
            {
                "bbox": (20, 30, 180, 220),
                "class_id": 0,
                "confidence": 0.81,
                "selected": False,
            },
            {
                "bbox": (210, 40, 380, 250),
                "class_id": 1,
                "confidence": 0.93,
                "selected": True,
            },
        ]

        ShotReviewDialog._draw_detection_boxes(image, detections)

        self.assertFalse(np.array_equal(image, before))
        selected_crop = image[35:256, 205:386]
        self.assertTrue(
            np.any(np.all(selected_crop == np.array([0, 255, 255]), axis=2))
        )

    def test_camera_preview_zooms_around_impact_by_one_point_five(self):
        frame = np.zeros((300, 600, 3), dtype=np.uint8)
        frame[:, :300] = (0, 0, 255)
        frame[:, 300:] = (255, 0, 0)
        shot = {
            "frame": frame,
            "camera_point": (0.75, 0.5),
            "detections": [],
        }
        dialog = ShotReviewDialog.__new__(ShotReviewDialog)

        preview = dialog._camera_preview(shot)

        self.assertEqual(REVIEW_CAMERA_ZOOM, 1.5)
        self.assertEqual(preview.shape, frame.shape)
        # Centering at x=75% changes the blue share from 50% to about 75%.
        self.assertGreater(np.mean(preview[20, :, 0] > 200), 0.70)

    def test_simulation_uses_large_red_impact_marker_even_for_hit(self):
        reference = np.full((600, 800, 3), (20, 75, 25), dtype=np.uint8)
        dialog = ShotReviewDialog.__new__(ShotReviewDialog)
        dialog._reference_images = {1: reference}
        shot = {
            "target_index": 1,
            "target_point": (0.5, 0.5),
            "hit": True,
        }

        preview = dialog._simulation_preview(shot)
        center = preview[250:351, 350:451]
        red_pixels = np.all(center == np.array([0, 0, 255]), axis=2)

        self.assertGreater(np.count_nonzero(red_pixels), 100)

    def test_overlapping_boxes_do_not_favor_larger_box_by_pixel_depth(self):
        large_wrong_box = {
            "bbox": (0, 0, 220, 220),
            "class_id": 3,
            "conf": 0.99,
            "keypoints": [],
        }
        focused_correct_box = {
            "bbox": (70, 70, 130, 130),
            "class_id": 1,
            "conf": 0.80,
            "keypoints": [],
        }

        selected = scoring.select_target_result(
            [large_wrong_box, focused_correct_box],
            bullet_point=(100, 100),
        )

        self.assertIs(selected, focused_correct_box)

    def test_class_to_reference_image_mapping_is_consistent(self):
        from gui.client_widget import TARGET_IMAGE_FILES

        self.assertEqual(
            TARGET_IMAGE_FILES,
            [scoring.SIGN_FILES[index] for index in range(scoring.NUM_CLASSES)],
        )

    def test_shot_numbers_are_unique_before_workers_finish(self):
        window = type("WindowState", (), {})()
        window._review_shot_counters = {}

        numbers = [
            MainWindow._next_review_shot_number(window, session_id=4, port_id=2)
            for _ in range(4)
        ]

        self.assertEqual(numbers, [1, 2, 3, 4])

    def test_starting_new_session_clears_previous_review(self):
        review_button_states = []
        widget = type(
            "Widget",
            (),
            {"set_review_available": lambda _self, value: review_button_states.append(value)},
        )()
        window = type("WindowState", (), {})()
        window.p_num = 1
        window.client_widgets = [widget]
        window._review_session_counter = 3
        window._review_sessions = {3: {1: [{"shot_number": 1}]}}
        window._review_shot_counters = {(3, 1): 1}
        window._active_review_session_id = None
        window._previous_review_session_id = 3

        MainWindow._begin_review_session(window)

        self.assertEqual(window._active_review_session_id, 4)
        self.assertIsNone(window._previous_review_session_id)
        self.assertEqual(window._review_sessions, {4: {1: []}})
        self.assertEqual(window._review_shot_counters, {(4, 1): 0})
        self.assertEqual(review_button_states, [False])


if __name__ == "__main__":
    unittest.main()
