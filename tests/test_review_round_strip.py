import json
from pathlib import Path
import tempfile
import numpy as np
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtTest import QTest

import config as cf
from gui.client_widget import ClientWidget
from gui.main_window import MainWindow
from gui.review_window import ShotReviewDialog
from gui.shot_groups import same_burst, burst_groups


class BurstGroupingTests(unittest.TestCase):
    def test_strict_gap_boundary_chains_and_missing_or_reversed_times(self):
        self.assertTrue(same_burst(100, 100.299, .3))
        self.assertFalse(same_burst(100, 100.3, .3))
        self.assertFalse(same_burst(100, 99.9, .3))
        self.assertFalse(same_burst(None, 100, .3))
        self.assertFalse(same_burst(100, float("nan"), .3))
        records = {n: {"received_at": at} for n, at in enumerate((0, .29, .58, .88), 1)}
        self.assertEqual(burst_groups(records, .3), [[1, 2, 3], [4]])
        self.assertEqual(burst_groups(records, .1), [[1], [2], [3], [4]])

    def test_legacy_ammunition_command_migrates_when_maximum_is_not_declared(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"shooting":{"start_uart_command":"0F024\n"}}), encoding="utf-8")
            loaded = cf.load_app_config(path)
        self.assertEqual(loaded["shooting"]["max_bullets"], 24)
        with patch.object(cf, "APP_CONFIG", loaded):
            self.assertEqual(cf.ammunition_command(), "0F024\n")

    def test_receipts_group_per_gun_and_session_before_inference_finishes(self):
        window = SimpleNamespace(_review_shot_counters={}, _last_burst_receipt={},
                                 _review_receipts={}, _review_sessions={1: {1: []}},
                                 _reference_images={}, _previous_review_session_id=None)
        with patch.dict(cf.APP_CONFIG["shooting"], burst_gap_seconds=.3):
            for port, at in ((1,100), (2,100.1), (1,100.2), (1,100.5)):
                MainWindow._next_review_shot_number(window, 1, port, at)
            MainWindow._next_review_shot_number(window, 2, 1, 101)
        self.assertEqual([window._review_receipts[(1,1,n)]["burst_id"] for n in (1,2,3)], [1,1,2])
        self.assertEqual(window._review_receipts[(1,2,1)]["burst_id"], 1)
        self.assertEqual(window._review_receipts[(2,1,1)]["burst_id"], 1)
        for number in (3,1,2):
            MainWindow._store_review_shot(window, {"session_id":1, "port_id":1,
                "shot_number":number, "received_at":window._review_receipts[(1,1,number)]["received_at"],
                "metadata":{"hit":True}})
        self.assertEqual([shot["burst_id"] for shot in window._review_sessions[1][1]], [1,1,2])


class ReviewStripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def dialog(self, shots, **kwargs):
        dialog = ShotReviewDialog(1, shots, **kwargs)
        self.addCleanup(dialog.close)
        return dialog

    def test_click_navigation_blue_selection_and_log_details_stay_in_sync(self):
        shots = [{"shot_number":n, "hit":n!=2, "received_at":10 + n*.1,
                  "status":"Thông tin kỹ thuật riêng"} for n in (1,2,3)]
        dialog = self.dialog(shots)
        dialog.show()
        QTest.qWait(20)
        self.assertEqual(len(dialog.round_buttons), 16)
        self.assertEqual(dialog.round_buttons[1].width(), dialog.round_buttons[1].height())
        self.assertFalse(dialog.round_buttons[4].isEnabled())
        dialog.round_buttons[2].click()
        self.assertEqual(dialog.current_index, 1)
        self.assertEqual(dialog.counter_label.text(), "2 / 3")
        self.assertIn("#1769ff", dialog.round_buttons[2].styleSheet())
        self.assertNotIn("#1769ff", dialog.round_buttons[1].styleSheet())
        self.assertIn("#df3949", dialog.round_buttons[2].styleSheet())
        self.assertIn("#1a9b58", dialog.round_buttons[1].styleSheet())
        self.assertTrue(dialog.details_label.isHidden() or not dialog.details_label.isVisible())
        dialog.log_btn.click()
        QTest.qWait(20)
        self.assertTrue(dialog.log_dialog.isVisible())
        self.assertIn("Thông tin kỹ thuật riêng", dialog.log_text.toPlainText())
        dialog.log_dialog.close()
        dialog.next_btn.click()
        self.assertEqual(dialog.counter_label.text(), "3 / 3")
        self.assertIn("#1769ff", dialog.round_buttons[3].styleSheet())
        root = dialog.layout()
        self.assertLess(root.indexOf(dialog.ammo_scroll), root.count()-1)
        self.assertFalse(any("Chưa bắn" in label.text() for label in dialog.findChildren(QLabel)
                             if label.isVisible()))

    def test_simulated_target_has_white_space_and_no_hit_or_miss_border(self):
        dialog = self.dialog([])
        dialog._reference_images = {1: np.full((200,200,3),(20,75,25),np.uint8)}
        hit = dialog._simulation_preview({"target_index":1,"hit":True})
        miss = dialog._simulation_preview({"target_index":1,"hit":False})
        np.testing.assert_array_equal(hit, miss)
        np.testing.assert_array_equal(hit[0], 255)
        np.testing.assert_array_equal(hit[-1], 255)
        pixels = np.where(np.any(hit != 255,axis=2))
        ratio = (pixels[1].max()-pixels[1].min()+1)/hit.shape[1]
        self.assertLess(ratio,.85)
        self.assertGreater(ratio,.7)

    def test_configured_capacity_updates_widgets_uart_and_review(self):
        with patch.dict(cf.APP_CONFIG["shooting"], max_bullets=24):
            widget = ClientWidget(1)
            self.addCleanup(widget.close)
            dialog = self.dialog([])
            self.assertEqual(widget.bullet_limit, 24)
            self.assertEqual(cf.ammunition_command(), "0F024\n")
            self.assertEqual(len(dialog.round_buttons), 24)
            self.assertFalse(dialog.log_btn.isEnabled())
            for _ in range(25):
                widget.record_miss()
            self.assertEqual(widget.bullet_count, 24)

    def test_late_results_update_strip_without_losing_selected_shot(self):
        shots = [{"shot_number":2, "hit":False, "burst_id":1}]
        receipts = {1:{"burst_id":1},2:{"burst_id":1},3:{"burst_id":2}}
        dialog = self.dialog(shots, fired_count=3, receipt_info=receipts)
        dialog.show()
        self.assertEqual(dialog.counter_label.text(), "2 / 3")
        shots.insert(0, {"shot_number":1,"hit":True,"burst_id":1})
        QTest.qWait(250)
        self.assertEqual(dialog.shots[dialog.current_index]["shot_number"], 2)
        self.assertTrue(dialog.round_buttons[1].isEnabled())
        self.assertIn("#1769ff", dialog.round_buttons[2].styleSheet())
        self.assertFalse(dialog.round_buttons[3].isEnabled())
        dialog.close()
        self.assertFalse(dialog._history_timer.isActive())

    def test_ammunition_setting_reaches_real_window_start_and_large_strip_scrolls(self):
        with patch.dict(cf.APP_CONFIG["shooting"], max_bullets=24), patch(
                "gui.main_window.OptionWindow") as factory, patch.object(
                MainWindow, "_start_servers"), patch("gui.main_window.LoraController"), patch(
                "gui.main_window.ShotSound"), patch("gui.main_window.HitSound"), patch("gui.main_window.ResultSound"):
            option = factory.return_value
            option.exec_.return_value = option.Accepted = 1
            option.start, option.p_num, option.automatic_close_target_enabled = True, 1, False
            window = MainWindow()
            self.addCleanup(window.close)
            server = MagicMock()
            window.servers = [server]
            window.start_test()
            server.send_uart_command.assert_called_once_with("0F024\n")
            self.assertEqual(window.client_widgets[0].bullet_limit, 24)
            window.stop_test()
            dialog = self.dialog([{"shot_number":n,"hit":True} for n in range(1,25)])
            dialog.resize(920,600)
            dialog.show()
            self.app.processEvents()
            dialog.show_last()
            self.app.processEvents()
            self.assertGreater(dialog.ammo_scroll.horizontalScrollBar().maximum(), 0)
            self.assertIn("#1769ff", dialog.round_buttons[24].styleSheet())
            self.assertEqual(dialog.counter_label.text(), "24 / 24")


if __name__ == "__main__":
    unittest.main()
