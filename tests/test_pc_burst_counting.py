import os
import threading
import unittest
from collections import deque
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
from server_client.protocol import Protocol
from test_connection_timeout import _DeferredExecutor, _make_server_harness


class PcBurstCountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_full_decode_queue_preserves_three_received_images(self):
        server = _make_server_harness()
        server.running = True
        server._decode_lock = threading.Lock()
        server._decode_inflight = 0
        # Force saturation even for a short burst, without depending on CPU speed.
        server._decode_max_inflight = 1
        server._decode_pool = _DeferredExecutor()
        server.data_socket = MagicMock()
        received = []
        server.shoot_image_signal.connect(
            lambda frame, meta: received.append(int(frame[0, 0, 0])),
            type=Qt.DirectConnection,
        )
        messages = deque(
            [Protocol.MSG_SHOOT_IMAGE, cv2.imencode(
                ".png", np.full((8, 8, 3), value, dtype=np.uint8)
            )[1].tobytes()]
            for value in (20, 40, 60)
        )
        server.data_socket.recv_multipart.side_effect = messages.popleft

        def complete_one(*_args):
            if server._decode_pool.jobs:
                worker, args = server._decode_pool.jobs.pop(0)
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
        self.assertEqual(received, [20, 40, 60])
        self.assertEqual(server._decode_inflight, 0)

    def test_three_images_count_even_when_two_scoring_jobs_fail(self):
        self.assert_burst_count(failed_jobs=2)

    def test_three_images_count_when_all_scoring_jobs_succeed(self):
        self.assert_burst_count(failed_jobs=0)

    def assert_burst_count(self, failed_jobs):
        widget = ClientWidget(1)
        window = SimpleNamespace(
            testing=True, _active_review_session_id=1, _previous_review_session_id=None,
            client_widgets=[widget], _reference_images={0: np.zeros((100, 200, 3))},
            _review_sessions={1: {1: []}}, _review_shot_counters={},
            _scoring_pool=_DeferredExecutor(), _get_scoring_session=lambda: None,
            _maybe_close_hit_target=MagicMock(), scoring_done_signal=MagicMock(),
            _setting_window=None, _queue_raw_camera_image=MagicMock(),
        )
        window._store_review_shot = lambda result: MainWindow._store_review_shot(window, result)
        window._next_review_shot_number = lambda sid, pid: MainWindow._next_review_shot_number(window, sid, pid)
        window._score_shot_worker = lambda *args: MainWindow._score_shot_worker(window, *args)
        window.process_shot = lambda *args: MainWindow.process_shot(window, *args)
        window.scoring_done_signal.emit.side_effect = lambda result: MainWindow._on_scoring_done(window, result)
        try:
            for value in (20, 40, 60):
                MainWindow._on_shoot_image(window, 1, np.full((8, 8, 3), value, dtype=np.uint8), {})
            self.assertEqual(len(window._scoring_pool.jobs), 3)
            results = [
                (None, {"class_id": 0, "transformed_point": (100, 50), "hit": True})
                for _ in range(3 - failed_jobs)
            ] + [RuntimeError("injected inference failure") for _ in range(failed_jobs)]
            with patch("gui.main_window.scoring.scoring", side_effect=results):
                # Worker completion order must not change the number of shots.
                for worker, args in reversed(window._scoring_pool.jobs):
                    worker(*args)
            self.assertEqual(widget.bullet_count, 3)
            self.assertEqual(len(widget.shots), 3 - failed_jobs)
            self.assertEqual(widget.hit_targets, {0})
            review = window._review_sessions[1][1]
            self.assertEqual([shot["shot_number"] for shot in review], [1, 2, 3])
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
