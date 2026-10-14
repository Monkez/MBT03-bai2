import os
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from openpyxl import Workbook
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.shooting_roster import read_roster


def write_roster(path, rows):
    book = Workbook()
    book.active.append(["STT", "Họ tên", "Đơn vị", "Ngày sinh"])
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()


class RosterReaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="Danh sách bắn ")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "Tiểu đoàn.xlsx"

    def test_unicode_dates_blank_rows_and_nonconsecutive_numbers(self):
        write_roster(self.path, [[3, " Nguyễn Văn An ", " Đại đội 1 ", datetime(2000, 2, 3)],
                                 [None, None, None, None], [8, "Trần Bình", None, "2001"]])
        people = read_roster(self.path, 4)
        self.assertEqual([(p.number, p.name, p.unit, p.birthday, p.pedestal) for p in people],
                         [(3, "Nguyễn Văn An", "Đại đội 1", "03/02/2000", 3),
                          (8, "Trần Bình", "", "2001", 4)])
        self.assertEqual([p.pedestal for p in read_roster(self.path, 1)], [1, 1])
        # Workbook handles must be closed, including on Windows.
        self.path.rename(self.path.with_name("Đã đọc.xlsx"))

    def test_invalid_rows_are_rejected_with_row_numbers(self):
        for row, message in [([1, "", "", ""], "thiếu họ tên"),
                             ([0, "An"], "số nguyên dương"),
                             ([1.5, "An"], "số nguyên dương"),
                             ([None, "An"], "số nguyên dương"),
                             ([True, "An"], "số nguyên dương")]:
            with self.subTest(row=row):
                write_roster(self.path, [row])
                with self.assertRaisesRegex(ValueError, "Dòng 2:.*" + message):
                    read_roster(self.path, 2)
        write_roster(self.path, [[2, "An"], [2, "Bình"]])
        with self.assertRaisesRegex(ValueError, "Dòng 3: STT 2 bị trùng"):
            read_roster(self.path, 2)

    def test_empty_or_corrupt_workbook(self):
        write_roster(self.path, [])
        with self.assertRaisesRegex(ValueError, "chưa có người bắn"):
            read_roster(self.path, 1)
        self.path.write_text("not an Excel workbook", encoding="utf-8")
        with self.assertRaises(Exception):
            read_roster(self.path, 1)


class ShootingRosterTests(unittest.TestCase):
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
        patch("gui.main_window.ResultSound").start()
        self.window = MainWindow()
        self.window._scoring_pool.shutdown(wait=True)
        self.window._scoring_pool = MagicMock()
        self.addCleanup(self.window.close)
        directory = tempfile.TemporaryDirectory(prefix="Danh sách bắn ")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "Danh sách.xlsx"
        write_roster(self.path, [[1, "Nguyễn An", "Đại đội 1", datetime(2000, 1, 2)],
                                 [2, "Trần Bình", "Đại đội 2"], [3, "Lê Chi", "Đại đội 1"],
                                 [4, "Đỗ Dũng", "Đại đội 2"], [5, "Phạm Hà", "Đại đội 1"]])
        self.roster = self.window._roster

    def wait_loaded(self):
        deadline = time.monotonic() + 3
        while self.roster.loading and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.roster.loading, "Excel loading did not finish")

    def load(self):
        self.assertTrue(self.roster.load_file(str(self.path)))
        self.wait_loaded()

    def begin(self):
        self.window.start_test()
        self.window._cancel_lora_script()
        self.window._start_followup_timer.stop()

    def result(self, port, number, hit=False, class_id=None):
        sid = self.window._active_review_session_id or self.window._previous_review_session_id
        received = self.window._shooting_session.started_at + 16
        self.window._on_scoring_done({
            "ok": True, "session_id": sid, "port_id": port, "shot_number": number,
            "frame": np.zeros((8, 8, 3), dtype=np.uint8), "bullet_point": (.5, .5),
            "received_at": received,
            "metadata": {"hit": hit, "class_id": class_id, "transformed_point": (100, 100)},
        })

    def test_file_picker_load_assign_next_group_and_clear(self):
        with patch("gui.shooting_roster.QFileDialog.getOpenFileName", return_value=(str(self.path), "")):
            self.window.select_file_btn.click()
        self.wait_loaded()
        self.assertEqual(len(self.roster.people), 5)
        self.assertFalse(self.window.start_btn.isEnabled())
        self.window.start_test()
        self.assertFalse(self.window.testing)
        self.roster.list.setCurrentRow(2)
        self.roster.assign_button.click()
        self.assertEqual(self.roster.assignments, {1: 3})
        self.assertEqual(self.window.client_widgets[0]._shooter_text, "Lê Chi — Đại đội 1")
        self.window.new_route_btn.click()
        self.assertEqual(self.roster.assignments, {1: 1, 2: 2})
        self.window.client_widgets[0].go_out_btn.click()
        self.assertEqual(self.roster.assignments, {2: 2})
        self.assertEqual(self.window.client_widgets[0]._shooter_text, "")

    def test_cancel_and_invalid_file_preserve_current_assignments(self):
        self.load()
        self.roster.next_group()
        with patch("gui.shooting_roster.QFileDialog.getOpenFileName", return_value=("", "")):
            self.roster.choose_file()
        write_roster(self.path, [[1, "An"], [1, "Bình"]])
        with patch("gui.shooting_roster.QMessageBox.warning") as warning:
            self.roster.load_file(str(self.path))
            self.wait_loaded()
        warning.assert_called_once()
        self.assertEqual(len(self.roster.people), 5)
        self.assertEqual(self.roster.assignments, {1: 1, 2: 2})

    def test_keyboard_activation_and_literal_long_name(self):
        write_roster(self.path, [[1, "Nguyễn <An> & Bình " * 12, "Đại đội 1"]])
        self.load()
        self.roster.list.setCurrentRow(0)
        QTest.keyClick(self.roster.list, Qt.Key_Return)
        self.assertEqual(self.roster.assignments, {1: 1})
        label = self.window.client_widgets[0].name_label
        self.assertEqual(label.textFormat(), Qt.PlainText)
        self.assertIn("<An> & Bình", label.toolTip())

    def test_round_blocks_reassignment_then_advances_even_without_shots(self):
        self.load()
        self.roster.next_group()
        self.begin()
        self.assertFalse(self.window.select_file_btn.isEnabled())
        self.assertFalse(self.window.new_route_btn.isEnabled())
        self.assertFalse(self.roster.assign(3))
        self.roster.clear(1)
        self.assertEqual(self.roster.assignments, {1: 1, 2: 2})
        self.window.stop_test()
        self.assertEqual(self.roster.results, {1: (0, 0, "Không đạt"), 2: (0, 0, "Không đạt")})
        self.roster.next_group()
        self.assertEqual(self.roster.assignments, {1: 3, 2: 4})
        self.begin()
        self.window.stop_test()
        self.roster.next_group()
        self.assertEqual(self.roster.assignments, {1: 5})
        self.assertEqual(self.window.client_widgets[1]._shooter_text, "")

    def test_pending_scoring_blocks_new_people_and_new_exercise(self):
        self.load()
        self.roster.next_group()
        self.begin()
        sid = self.window._active_review_session_id
        self.window._review_shot_counters[(sid, 1)] = 1
        self.window.stop_test()
        self.assertFalse(self.roster.assign(3))
        self.assertFalse(self.roster.load_file(str(self.path)))
        self.window.start_test()
        self.assertFalse(self.window.testing)
        self.result(1, 1, hit=True, class_id=1)
        self.assertEqual(self.roster.results[1], (1, 1, "Không đạt"))
        self.assertTrue(self.window.new_route_btn.isEnabled())

    def test_late_old_images_never_count_for_new_person(self):
        self.load()
        self.roster.next_group()
        self.begin()
        self.window.stop_test()
        self.roster.next_group()
        self.result(1, 1, hit=True, class_id=1)
        self.assertEqual(self.roster.results[1], (1, 1, "Không đạt"))
        self.assertNotIn(3, self.roster.results)
        self.assertEqual(self.window.client_widgets[0].bullet_count, 0)
        self.assertFalse(self.window.client_widgets[0].review_btn.isEnabled())

    def test_loading_blocks_start_and_does_not_overwrite_connection_style(self):
        self.window.client_widgets[0].set_connection_quality_state("degraded", 900, 50)
        label = self.window.client_widgets[0].pedestal_name_label
        text, style = label.text(), label.styleSheet()
        self.roster.loading = True
        self.roster.refresh_controls()
        self.window.start_test()
        self.assertFalse(self.window.testing)
        self.roster.loading = False
        self.load()
        self.roster.next_group()
        self.assertEqual((label.text(), label.styleSheet()), (text, style))

    def test_result_ranking_matches_target_eight_rule(self):
        self.load()
        self.roster.next_group()
        self.begin()
        sid = self.window._active_review_session_id
        self.window._review_sessions[sid][1] = [
            {"target_index": i, "hit": True} for i in (0, 1, 2)]
        self.window.stop_test()
        self.assertEqual(self.roster.results[1][2], "Đạt")
        self.window._review_sessions[sid][1][2]["target_index"] = 3
        self.roster.update_results(sid)
        self.assertEqual(self.roster.results[1][2], "Khá")

    def test_background_load_keeps_ui_alive_and_close_discards_completion(self):
        started, release = threading.Event(), threading.Event()

        def slow_reader(*_args):
            started.set()
            release.wait(5)
            return []

        with patch("gui.shooting_roster.read_roster", side_effect=slow_reader):
            try:
                self.roster.load_file(str(self.path))
                self.assertTrue(started.wait(1))
                ticks = []
                QTimer.singleShot(0, lambda: ticks.append(True))
                QTest.qWait(20)
                self.assertEqual(ticks, [True])
                self.window.close()
                self.assertTrue(self.roster.closed)
            finally:
                release.set()
                self.roster._pool.shutdown(wait=True)
        self.app.processEvents()
        self.assertEqual(self.roster.people, {})


if __name__ == "__main__":
    unittest.main()
