import unittest

from gui.client_widget import classify_hits
from gui.shot_groups import single_shot_violations


class SingleShotTests(unittest.TestCase):
    def assess(self, shots=(), receipts=None, **kwargs):
        return single_shot_violations(shots, receipts or {}, .3, limit=16, **kwargs)

    def test_rank_drops_once_with_floor_at_pass(self):
        for hits, before, after in (({0, 1, 2, 3}, "Giỏi", "Khá"),
                                    ({0, 1, 3}, "Khá", "Đạt"),
                                    ({0, 1, 2}, "Đạt", "Đạt"),
                                    ({0, 1}, "Đạt", "Đạt"),
                                    ({1}, "Không đạt", "Không đạt")):
            with self.subTest(hits=hits):
                self.assertEqual(classify_hits(hits), before)
                self.assertEqual(classify_hits(hits, True), after)

    def test_pending_inference_does_not_split_burst(self):
        receipts = {1: {"received_at": 10, "burst_id": 1},
                    2: {"received_at": 10.1, "burst_id": 1},
                    3: {"received_at": 11, "burst_id": 2}}
        shots = [{"shot_number": 1, "target_index": 1},
                 {"shot_number": 3, "target_index": 2, "hit": False}]
        self.assertEqual(self.assess(shots, receipts), ((3,), frozenset({2})))
        shots.append({"shot_number": 2, "target_index": 1})
        self.assertEqual(self.assess(shots, receipts), ((3,), frozenset({2})))

    def test_live_last_shot_waits_for_burst_gap_or_stop(self):
        receipts = {1: {"received_at": 100, "expected_target_index": 1}}
        self.assertEqual(self.assess(receipts=receipts, final=False, now=100.299), ((), frozenset()))
        self.assertEqual(self.assess(receipts=receipts, final=False, now=100.3), ((1,), frozenset({1})))
        self.assertEqual(self.assess(receipts=receipts, final=True, now=100.1), ((1,), frozenset({1})))

    def test_detected_target_wins_and_unknown_target_is_not_guessed(self):
        receipts = {1: {"received_at": 10, "expected_target_index": 1},
                    2: {"received_at": 11}}
        shots = [{"shot_number": 1, "target_index": 3, "hit": False}]
        self.assertEqual(self.assess(shots, receipts), ((1, 2), frozenset({3})))

    def test_legacy_data_without_cadence_is_not_penalized(self):
        self.assertEqual(self.assess([{"target_index": 1, "hit": True}]), ((), frozenset()))

    def test_limit_and_strict_boundary(self):
        receipts = {1: {"received_at": 100}, 2: {"received_at": 100.3},
                    17: {"received_at": 110, "expected_target_index": 3}}
        self.assertEqual(self.assess(receipts=receipts), ((1, 2), frozenset()))
