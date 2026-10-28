import json
import os
import tempfile
import unittest

import config
import scoring
from gui.main_window import MainWindow
from gui.review_window import (
    OTHER_BOX_THICKNESS,
    REVIEW_CAMERA_ZOOM,
    SELECTED_BOX_THICKNESS,
    SIMULATION_MARKER_SCALE,
    SHOW_SIMULATION_AIM_POINT,
)


class AppConfigTests(unittest.TestCase):
    def test_current_config_contains_only_documented_top_level_groups(self):
        with open(config.CONFIG_PATH, "r", encoding="utf-8") as file:
            raw = json.load(file)

        self.assertEqual(
            set(raw),
            {
                "save_raw_data",
                "shooting",
                "scoring",
                "review",
                "calibration",
                "lora",
                "runtime",
                "connection",
                "media",
                "wifi",
            },
        )
        for legacy_key in (
            "show_mode",
            "Camera",
            "Trigger",
            "Test1",
            "Test2",
            "Q0",
            "Q0_bound",
            "save_to_desktop",
        ):
            self.assertNotIn(legacy_key, raw)

        self.assertNotIn("security", config.DEFAULT_CONFIG)
        self.assertIs(raw["save_raw_data"], True)
        self.assertIs(config.DEFAULT_CONFIG["save_raw_data"], True)

    def test_partial_config_uses_defaults_and_ignores_unknown_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "review": {"camera_zoom": 2.0, "unknown": 123},
                        "legacy_option": True,
                    },
                    file,
                )

            loaded = config.load_app_config(path)

        self.assertEqual(loaded["review"]["camera_zoom"], 2.0)
        self.assertEqual(
            loaded["shooting"]["start_uart_command"],
            config.DEFAULT_CONFIG["shooting"]["start_uart_command"],
        )
        self.assertNotIn("unknown", loaded["review"])
        self.assertNotIn("legacy_option", loaded)

    def test_legacy_visibility_migrates_but_explicit_new_setting_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            for values, expected in (({"show_before_offset": True}, True),
                                     ({"show_before_offset": True, "show_simulation_aim_point": False}, False)):
                with open(path, "w", encoding="utf-8") as file:
                    json.dump({"review": values}, file)
                loaded = config.load_app_config(path)
                self.assertEqual(loaded["review"]["show_simulation_aim_point"], expected)
                self.assertNotIn("show_before_offset", loaded["review"])
                self.assertTrue(loaded["review"]["show_camera_impact_point"])
                self.assertFalse(loaded["shooting"]["show_rejected_shots_on_target"])

    def test_runtime_constants_match_config_file(self):
        self.assertEqual(SHOW_SIMULATION_AIM_POINT, config.config_bool("review.show_simulation_aim_point", False))
        self.assertEqual(
            MainWindow.START_UART_COMMAND,
            config.get_setting("shooting.start_uart_command"),
        )
        self.assertEqual(
            REVIEW_CAMERA_ZOOM,
            config.get_setting("review.camera_zoom"),
        )
        self.assertEqual(
            SIMULATION_MARKER_SCALE,
            config.get_setting("review.simulation_marker_scale"),
        )
        self.assertEqual(
            SELECTED_BOX_THICKNESS,
            config.get_setting("review.selected_box_thickness"),
        )
        self.assertEqual(
            OTHER_BOX_THICKNESS,
            config.get_setting("review.other_box_thickness"),
        )
        self.assertEqual(
            scoring.CONFIDENCE_THRESHOLD,
            config.get_setting("scoring.confidence_threshold"),
        )
        self.assertEqual(
            scoring.Q0_TARGET_CLASS_ID,
            config.get_setting("calibration.target_class_id"),
        )

if __name__ == "__main__":
    unittest.main()
