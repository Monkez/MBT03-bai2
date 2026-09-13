import unittest
from unittest import mock

import numpy as np

import scoring


LAB_TARGET_OFFSETS = {
    0: (0.0, -0.06),
    1: (0.0, 0.0),
    2: (0.0, -0.10),
    3: (-0.40, 0.0),
}


class TargetOffsetTests(unittest.TestCase):
    def test_provisional_offsets_are_relative_to_reference_size(self):
        shape = (1000, 500, 3)
        point = (250.0, 500.0)

        with mock.patch.dict(scoring.TARGET_OFFSETS, LAB_TARGET_OFFSETS, clear=True):
            self.assertEqual(scoring.apply_target_offset(1, shape, point), point)
            self.assertEqual(scoring.apply_target_offset(0, shape, point), (250.0, 440.0))
            self.assertEqual(scoring.apply_target_offset(2, shape, point), (250.0, 400.0))
            self.assertEqual(scoring.apply_target_offset(3, shape, point), (50.0, 500.0))

    def test_offset_rotation_is_disabled_by_default(self):
        shape = (1000, 400, 3)
        point = (200.0, 500.0)
        matrix = np.asarray(
            [[0.0, -2.0, 0.0], [2.0, 0.0, 0.0]],
            dtype=np.float64,
        )

        with mock.patch.dict(scoring.TARGET_OFFSETS, LAB_TARGET_OFFSETS, clear=True):
            adjusted = scoring.apply_target_offset(3, shape, point, matrix)

        self.assertAlmostEqual(adjusted[0], 40.0)
        self.assertAlmostEqual(adjusted[1], 500.0)

    def test_bia_8_horizontal_rotation_can_be_enabled_with_mirrored_angle(self):
        shape = (1000, 400, 3)
        point = (200.0, 500.0)
        matrix = np.asarray(
            [[0.0, -2.0, 0.0], [2.0, 0.0, 0.0]],
            dtype=np.float64,
        )

        with (
            mock.patch.object(scoring, "TARGET_OFFSET_ROTATION_ENABLED", True),
            mock.patch.dict(scoring.TARGET_OFFSETS, {3: (0.025, 0.02)}),
        ):
            adjusted = scoring.apply_target_offset(3, shape, point, matrix)

        # Horizontal +10 px uses -90 degrees (up); vertical +20 px keeps
        # the normal +90-degree rotation (left).
        self.assertAlmostEqual(adjusted[0], 180.0)
        self.assertAlmostEqual(adjusted[1], 490.0)

    def test_rotation_extraction_does_not_change_offset_distance_under_shear(self):
        matrix = np.asarray(
            [[1.2, 0.4, 0.0], [0.1, 0.8, 0.0]],
            dtype=np.float64,
        )
        rotation = scoring.affine_rotation_matrix(matrix)
        vector = np.asarray([12.0, -7.0])

        self.assertAlmostEqual(
            float(np.linalg.norm(rotation @ vector)),
            float(np.linalg.norm(vector)),
        )

    def test_scoring_reports_click_and_offset_impact_on_reference_target(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        reference = np.zeros((100, 200, 3), dtype=np.uint8)
        detection = {
            "bbox": [0, 0, 199, 99],
            "conf": 0.9,
            "class_id": 0,
            "keypoints": [],
        }
        identity = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)

        with (
            mock.patch.dict(scoring.TARGET_OFFSETS, LAB_TARGET_OFFSETS, clear=True),
            mock.patch.object(scoring, "inference", return_value=[detection]),
            mock.patch.object(scoring, "estimate_target_transform", return_value=(identity, 4)),
            mock.patch.object(scoring, "point_in_hit_area", return_value=True) as hit_area,
        ):
            _, metadata = scoring.scoring(
                image,
                (0.5, 0.5),
                {0: reference},
                session=object(),
            )

        self.assertEqual(metadata["transformed_click_point"], (100.0, 50.0))
        self.assertEqual(metadata["transformed_point"], (100.0, 44.0))
        self.assertNotIn("camera_impact_point", metadata)
        self.assertEqual(metadata["target_offset"], (0.0, -0.06))
        self.assertEqual(hit_area.call_count, 2)
        self.assertEqual(
            hit_area.call_args,
            mock.call(0, reference.shape, (100.0, 44.0)),
        )


if __name__ == "__main__":
    unittest.main()
