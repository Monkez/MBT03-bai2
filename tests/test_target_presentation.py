import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import config as cf

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

from gui.main_window import MainWindow
from gui.shooting_session import ShootingSession
from gui.styles import TARGET_GREEN, TARGET_RED


class TargetPresentationTests(unittest.TestCase):
    def test_sequence_uses_visibility_not_early_and_late_scoring_grace(self):
        session = ShootingSession(100, (15, 32, 42, 64))
        self.assertEqual(session.target_presentation(100), (1, False))
        for target, opened in ((1, 115), (0, 132), (2, 142), (3, 164)):
            session.open_target(target, opened)
            self.assertEqual(session.target_presentation(opened), (target, True))
            closed = opened + (18 if target == 3 else 7)
            self.assertEqual(session.target_presentation(closed - .001), (target, True))
            self.assertEqual(session.target_presentation(closed), (target, False))
            # The scoring window remains open after the picture folds.
            self.assertEqual(session.active_target(closed, target).class_id, target)
            upcoming = {1: 0, 0: 2, 2: 3, 3: 3}[target]
            next_show = {1: 132, 0: 142, 2: 164, 3: 182}[target]
            midpoint = (closed + next_show) / 2
            if target != 3:
                self.assertEqual(session.target_presentation(midpoint - .001), (target, False))
            self.assertEqual(session.target_presentation(midpoint), (upcoming, False))
        self.assertIsNone(session.target_presentation(185))

    def test_early_fold_and_delayed_serial_confirmation(self):
        session = ShootingSession(100, (15, 32, 42, 64))
        session.open_target(1, 115)
        session.confirm_command_sent(1, 118, raised=True)
        self.assertEqual(session.target_presentation(116), (1, False))
        self.assertEqual(session.target_presentation(118), (1, True))
        self.assertTrue(session.close_target(1, 119))
        self.assertEqual(session.target_presentation(119), (1, False))
        self.assertEqual(session.target_presentation(125.5), (0, False))
        session.confirm_command_sent(1, 120, raised=False)
        self.assertEqual(session.target_presentation(120.5), (1, False))
        session.stop(121)
        self.assertIsNone(session.target_presentation(121))


class TargetPresentationFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(patch.stopall)
        self.clock = patch("gui.main_window.time.monotonic", return_value=100.0).start()
        option = patch("gui.main_window.OptionWindow").start().return_value
        option.exec_.return_value = option.Accepted = 1
        option.start = True
        option.p_num = 2
        option.automatic_close_target_enabled = True
        patch.object(MainWindow, "_start_servers").start()
        for name in ("LoraController", "ShotSound", "HitSound", "ResultSound"):
            patch(f"gui.main_window.{name}").start()
        self.window = MainWindow()
        self.window.lora.send_command.side_effect = lambda command: self.window._on_lora_command_sent(
            command, self.clock.return_value, self.clock.return_value)
        self.window.servers = [MagicMock(), MagicMock()]
        self.addCleanup(self.window.close)

    def assert_state(self, state):
        for widget in self.window.client_widgets:
            self.assertEqual(widget._target_presentation, state)
            image = widget.compose_target_image()
            self.assertEqual(set(widget._rendered_target_rects),
                             set(range(4)) if state is None else {state[0]})
            if state is not None and not state[1]:
                x, y, w, h = widget._rendered_target_rects[state[0]]
                image = image[y:y+h, x:x+w]
                np.testing.assert_array_equal(image[:, :, 0], image[:, :, 1])
                np.testing.assert_array_equal(image[:, :, 1], image[:, :, 2])
                self.assertGreaterEqual(image.min(), 214)
                self.assertIn("ĐANG GẬP", widget.target_status_label.text())
                self.assertNotIn("\n", widget.target_status_label.text())

    def start(self):
        self.window.start_test()
        self.window._cancel_lora_script()

    def raise_target(self, index, at):
        self.clock.return_value = at - 1.5
        _, command, description = self.window.LORA_SCRIPT[index]
        self.window._send_lora_script_command(command, description, (1, 0, 2, 3)[index])
        self.clock.return_value = at
        self.window._refresh_target_presentation()

    def test_start_each_target_fold_preview_and_stop_restore_overview(self):
        self.assert_state(None)
        self.start()
        self.assert_state((1, False))
        for index, target, at in ((0, 1, 116.5), (1, 0, 133.5), (2, 2, 143.5), (3, 3, 165.5)):
            self.raise_target(index, at)
            if target == 3:
                self.window._on_target_state_received(3, True, at - .1, at)
            self.assert_state((target, True))
            self.clock.return_value = at + (28 if target == 3 else 8) - 1.5
            self.window._send_scheduled_target_hide(target)
            self.clock.return_value += 1.5
            if target == 3:
                self.window._on_target_state_received(3, False, self.clock.return_value - .1, self.clock.return_value)
            self.window._refresh_target_presentation()
            self.assert_state((target, False))
            next_show = {1: 133.5, 0: 143.5, 2: 165.5, 3: 193.5}[target]
            self.clock.return_value = (self.clock.return_value + next_show) / 2
            self.window._refresh_target_presentation()
            self.assert_state(({1: 0, 0: 2, 2: 3, 3: 3}[target], False))
        self.clock.return_value = 195.5
        self.window.update_app()
        self.assertFalse(self.window._target_presentation_timer.isActive())
        self.assert_state(None)

    def test_auto_fold_only_on_hit_when_enabled_and_late_result_keeps_next_target(self):
        self.start()
        self.raise_target(0, 116.5)
        self.clock.return_value = 117.5
        self.assertFalse(self.window._maybe_close_hit_target(1, False))
        self.window.automatic_close_target_enabled = False
        self.assertFalse(self.window._maybe_close_hit_target(1, True))
        self.window._refresh_target_presentation()
        self.assert_state((1, True))
        self.window.automatic_close_target_enabled = True
        self.assertTrue(self.window._maybe_close_hit_target(1, True))
        self.clock.return_value = 119
        self.window._refresh_target_presentation()
        self.assert_state((1, False))
        self.clock.return_value = 126.25
        self.window._refresh_target_presentation()
        self.assert_state((0, False))
        self.raise_target(1, 133.5)
        self.assertFalse(self.window._maybe_close_hit_target(1, True))
        self.window._refresh_target_presentation()
        self.assert_state((0, True))
        self.window.stop_test()
        self.assert_state(None)
        self.start()
        self.assert_state((1, False))

    def test_single_shot_attribution_follows_display_at_receipt_even_when_folded(self):
        self.start()
        sid = self.window._active_review_session_id
        with patch.object(self.window._scoring_pool, "submit"):
            self.assertTrue(self.window.process_shot(1, np.zeros((8, 8, 3), np.uint8),
                                                    (.5, .5), received_at=101))
            self.assertEqual(self.window._review_receipts[(sid, 1, 1)]["displayed_target_index"], 1)
            self.raise_target(0, 116.5)
            self.clock.return_value = 117.5
            self.window._maybe_close_hit_target(1, True)
            for number, at, target in ((2, 126.249, 1), (3, 126.25, 0)):
                self.assertTrue(self.window.process_shot(1, np.zeros((8, 8, 3), np.uint8),
                                                        (.5, .5), received_at=at))
                self.assertEqual(self.window._review_receipts[(sid, 1, number)]["displayed_target_index"], target)

    def test_extra_shots_are_rejected_before_scoring_or_burst_receipt(self):
        self.start()
        sid = self.window._active_review_session_id
        with patch.object(self.window._scoring_pool, "submit") as submit:
            for n in range(1, 17):
                self.assertTrue(self.window.process_shot(1, np.zeros((8, 8, 3), np.uint8),
                                                        (.5, .5), received_at=101 + n * .1))
            self.assertFalse(self.window.process_shot(1, np.zeros((8, 8, 3), np.uint8),
                                                     (.5, .5), received_at=105))
            self.assertEqual(submit.call_count, 16)
            self.assertEqual(self.window._review_shot_counters[(sid, 1)], 16)
            self.assertNotIn((sid, 1, 17), self.window._review_receipts)

    def test_focused_shot_mapping_filters_other_targets_and_overview_keeps_all_shots(self):
        widget = self.window.client_widgets[0]
        self.start()
        widget.record_shot(1, .5, .5)
        widget.record_shot(0, .25, .25)
        with patch.object(widget, "_draw_shot", wraps=widget._draw_shot) as draw:
            self.raise_target(0, 116.5)
            self.assertEqual([call.args[1] for call in draw.call_args_list], [1])
        self.window.stop_test()
        self.assertEqual(len(widget.shots), 2)
        self.assertEqual(set(widget._rendered_target_rects), set(range(4)))

    def test_live_timer_folds_after_hit_and_stop_cancels_further_transitions(self):
        self.start()
        self.raise_target(0, 116.5)
        self.clock.return_value = 117.5
        self.window._maybe_close_hit_target(1, True)
        self.clock.return_value = 119
        QTest.qWait(150)
        self.assert_state((1, False))
        self.clock.return_value = 126.25
        QTest.qWait(150)
        self.assert_state((0, False))
        self.window.stop_test()
        self.clock.return_value = 133.5
        QTest.qWait(150)
        self.assert_state(None)

    def test_overview_and_focused_target_render_distinct_hit_and_miss_borders(self):
        widget = self.window.client_widgets[0]
        widget.record_shot(1, .5, .5)
        for state in (None, (1, True), (0, True)):
            widget.set_target_presentation(state)
            canvas = widget.compose_target_image()
            colors = (TARGET_GREEN, TARGET_RED) if state is None else (
                TARGET_GREEN if state[0] == 1 else TARGET_RED,)
            for color in colors:
                bgr = tuple(int(color[i:i + 2], 16) for i in (5, 3, 1))
                self.assertGreater(np.count_nonzero(np.all(canvas == bgr, axis=2)), 100)
        widget.set_target_presentation((3, False))
        self.assertEqual(widget.target_status_label.text(), "BIA SỐ 8C · ĐANG GẬP")


if __name__ == "__main__":
    unittest.main()
