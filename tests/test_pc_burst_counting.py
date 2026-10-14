import os
import threading
import time
import unittest
from collections import deque
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import zmq
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from gui.client_widget import ClientWidget
from gui.main_window import MainWindow
from gui.shooting_session import ShootingSession
from server_client.protocol import Protocol
from test_connection_timeout import _DeferredExecutor, _make_server_harness


class PcBurstCountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_full_decode_queue_preserves_sixteen_received_images(self):
        server = _make_server_harness()
        server.running = True
        server._decode_lock = threading.Lock()
        server._decode_inflight = 0
        # Force saturation even for a short burst, without depending on CPU speed.
        server._decode_max_inflight = 1
        server._decode_pool = _DeferredExecutor()
        server.data_socket = MagicMock()
        received = []
        receipt_times = []
        submitted_times = []
        server.shoot_image_signal.connect(
            lambda frame, meta: received.append(int(frame[0, 0, 0])),
            type=Qt.DirectConnection,
        )
        server.shoot_image_signal.connect(
            lambda frame, meta: receipt_times.append(meta["_server_received_at"]),
            type=Qt.DirectConnection,
        )
        values = list(range(20, 36))
        messages = deque(
            [Protocol.MSG_SHOOT_IMAGE, cv2.imencode(
                ".png", np.full((8, 8, 3), value, dtype=np.uint8)
            )[1].tobytes()]
            for value in values
        )
        server.data_socket.recv_multipart.side_effect = messages.popleft

        def complete_one(*_args):
            if server._decode_pool.jobs:
                worker, args = server._decode_pool.jobs.pop(0)
                submitted_times.append(args[-1])
                worker(*args)

        def poll(_timeout):
            if messages:
                return [(server.data_socket, zmq.POLLIN)]
            complete_one()
            server.running = False
            return []

        with (
            patch("server_client.server_core.zmq.Poller") as poller,
            patch("server_client.server_core.time.sleep", side_effect=complete_one),
        ):
            poller.return_value.poll.side_effect = poll
            server._data_loop()
        self.assertEqual(received, values)
        self.assertEqual(server._decode_inflight, 0)
        self.assertEqual(receipt_times, submitted_times)
        self.assertTrue(all(isinstance(value, float) for value in receipt_times))

    def test_decoder_preserves_receipt_time_and_overwrites_client_timing_field(self):
        server = _make_server_harness()
        server._decode_lock = threading.Lock()
        server._decode_inflight = 1
        received = []
        server.shoot_image_signal.connect(lambda frame, meta: received.append(meta),
                                         type=Qt.DirectConnection)
        encoded = cv2.imencode(".png", np.zeros((8, 8, 3), dtype=np.uint8))[1].tobytes()
        metadata = Protocol.encode_payload({"q0": [.4, .6], "_server_received_at": 999})
        server._decode_shoot_image(encoded, metadata, received_at=123.5)
        self.assertEqual(received[0]["_server_received_at"], 123.5)
        self.assertEqual(received[0]["q0"], [.4, .6])

    def test_valid_shot_image_survives_malformed_q0_metadata(self):
        for q0 in ([.4], "invalid", {"x": .5}, [None, .5], [float("nan"), .5]):
            with self.subTest(q0=q0):
                server = _make_server_harness()
                server._decode_lock = threading.Lock()
                server._decode_inflight = 1
                received = []
                server.shoot_image_signal.connect(lambda frame, meta: received.append(meta),
                                                 type=Qt.DirectConnection)
                encoded = cv2.imencode(".png", np.zeros((8, 8, 3), dtype=np.uint8))[1].tobytes()
                server._decode_shoot_image(encoded, Protocol.encode_payload({"q0": q0}))
                self.assertEqual(len(received), 1)
                self.assertEqual(received[0]["q0"], [.5, .5])
                self.assertEqual(server._decode_inflight, 0)

    def test_three_images_count_even_when_two_scoring_jobs_fail(self):
        self.assert_burst_count(failed_jobs=2)

    def test_three_images_count_when_all_scoring_jobs_succeed(self):
        self.assert_burst_count(failed_jobs=0)

    def test_sixteen_images_count_despite_three_failed_scoring_jobs(self):
        self.assert_burst_count(failed_jobs=3, count=16)

    def assert_burst_count(self, failed_jobs, count=3):
        widget = ClientWidget(1)
        saves = [Future() for _ in range(count)]
        window = SimpleNamespace(
            testing=True, _active_review_session_id=1, _previous_review_session_id=None,
            client_widgets=[widget], _reference_images={0: np.zeros((100, 200, 3))},
            _review_sessions={1: {1: []}}, _review_shot_counters={},
            _scoring_pool=_DeferredExecutor(), _get_scoring_session=lambda: None,
            _maybe_close_hit_target=MagicMock(), scoring_done_signal=MagicMock(),
            _setting_window=None, _queue_raw_camera_image=MagicMock(side_effect=saves),
            _shot_sound=MagicMock(), _shooting_session=ShootingSession(time.monotonic()),
            automatic_close_target_enabled=True,
        )
        now = time.monotonic()
        window._shooting_session.open_target(1, now)
        window._shooting_session.open_target(0, now)
        window._store_review_shot = lambda result: MainWindow._store_review_shot(window, result)
        window._next_review_shot_number = lambda sid, pid: MainWindow._next_review_shot_number(window, sid, pid)
        window._score_shot_worker = lambda *args: MainWindow._score_shot_worker(window, *args)
        window.process_shot = lambda *args, **kwargs: MainWindow.process_shot(window, *args, **kwargs)
        window.scoring_done_signal.emit.side_effect = lambda result: MainWindow._on_scoring_done(window, result)
        try:
            for value in range(20, 20 + count):
                MainWindow._on_shoot_image(window, 1, np.full((8, 8, 3), value, dtype=np.uint8), {})
            self.assertEqual(len(window._scoring_pool.jobs), count)
            results = [
                (None, {"class_id": 0, "transformed_point": (100, 50), "hit": True})
                for _ in range(count - failed_jobs)
            ] + [RuntimeError("injected inference failure") for _ in range(failed_jobs)]
            with patch("gui.main_window.scoring.scoring", side_effect=results):
                # Worker completion order must not change the number of shots.
                for worker, args in reversed(window._scoring_pool.jobs):
                    worker(*args)
            self.assertEqual(widget.bullet_count, count)
            self.assertEqual(len(widget.shots), count - failed_jobs)
            self.assertEqual(widget.hit_targets, {0})
            review = window._review_sessions[1][1]
            self.assertEqual([shot["shot_number"] for shot in review], list(range(1, count + 1)))
            # Saving and scoring may finish in different orders; keep the exact
            # save associated with its shot, including inference failures.
            for index in reversed(range(count)):
                saves[index].set_result(f"image_{index + 1}_be_01.png")
            for index, shot in enumerate(review):
                self.assertIs(shot["raw_image_save"], saves[index])
                self.assertEqual(shot["raw_image_save"].result(), f"image_{index + 1}_be_01.png")
            if failed_jobs:
                self.assertEqual(review[0]["status"], "injected inference failure")
        finally:
            widget.deleteLater()

    def test_failed_result_from_another_session_does_not_count(self):
        widget = MagicMock()
        window = SimpleNamespace(
            testing=True, _active_review_session_id=2, client_widgets=[widget],
            _store_review_shot=MagicMock(),
        )
        MainWindow._on_scoring_done(window, {
            "ok": False, "session_id": 1, "port_id": 1, "error": "old result",
        })
        widget.record_miss.assert_not_called()

    def test_full_decode_queue_can_stop_without_consuming_next_image(self):
        server = _make_server_harness()
        server.running = True
        server._decode_lock = threading.Lock()
        server._decode_inflight = server._decode_max_inflight = 8
        server.data_socket = MagicMock()
        with (
            patch("server_client.server_core.zmq.Poller") as poller,
            patch("server_client.server_core.time.sleep",
                  side_effect=lambda _delay: setattr(server, "running", False)),
        ):
            poller.return_value.poll.return_value = [(server.data_socket, zmq.POLLIN)]
            server._data_loop()
        server.data_socket.recv_multipart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
