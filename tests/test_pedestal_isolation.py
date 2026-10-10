import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import zmq
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from gui.client_widget import ClientWidget
from gui.main_window import MainWindow
from server_client.client_core import MBT03ClientCore
from server_client.server_core import MBT03ServerCore


class PedestalIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_server_signals_keep_their_own_pedestal_id(self):
        servers = [MagicMock(port=1711), MagicMock(port=1995)]
        window = SimpleNamespace(
            p_num=2, servers=[], _load_system_id=lambda: "isolation-test",
            _on_client_connected_event=MagicMock(), _on_client_disconnected_event=MagicMock(),
            _on_shoot_image=MagicMock(), _on_connection_quality=MagicMock(),
            _update_hub_availability=MagicMock(),
        )
        with (
            patch("gui.main_window.HubRegistrar"),
            patch("gui.main_window.MBT03ServerCore", side_effect=servers),
        ):
            MainWindow._start_servers(window)
        self.assertEqual(window.servers, servers)
        for index in (1, 0, 1, 0):
            frame = np.full((8, 8, 3), index * 100, dtype=np.uint8)
            metadata = {"q0": [0.2 + index * 0.5, 0.4]}
            slot = servers[index].shoot_image_signal.connect.call_args.args[0]
            slot(frame, metadata)
            args = window._on_shoot_image.call_args.args
            self.assertEqual(args[0], index + 1)
            self.assertIs(args[1], frame)
            self.assertIs(args[2], metadata)

    def test_out_of_order_results_keep_counts_markers_and_review_separate(self):
        widgets = [ClientWidget(i, target_layout_mode="two_pedestals") for i in (1, 2)]
        window = SimpleNamespace(
            testing=True, _active_review_session_id=1, _previous_review_session_id=None,
            client_widgets=widgets, _reference_images={0: np.zeros((100, 200, 3))},
            _review_sessions={1: {1: [], 2: []}}, _maybe_close_hit_target=MagicMock(),
        )
        window._store_review_shot = lambda result: MainWindow._store_review_shot(window, result)
        try:
            untouched = widgets[0].compose_target_image()
            for port, number, point, hit in (
                (2, 2, (140, 40), False), (2, 1, (120, 60), True),
                (1, 1, (40, 30), True),
            ):
                MainWindow._on_scoring_done(window, {
                    "ok": True, "session_id": 1, "port_id": port, "shot_number": number,
                    "metadata": {"class_id": 0, "transformed_point": point,
                                 "transformed_click_point": (point[0], point[1] + 15), "hit": hit},
                })
                if port == 2:
                    self.assertEqual(widgets[0].bullet_count, 0)
                    np.testing.assert_array_equal(widgets[0].compose_target_image(), untouched)
            self.assertEqual(widgets[0].shots, [(0, 0.2, 0.3, True)])
            self.assertEqual(widgets[1].shots, [(0, 0.7, 0.4, False), (0, 0.6, 0.6, True)])
            self.assertEqual([widget.bullet_count for widget in widgets], [1, 2])
            review = window._review_sessions[1]
            self.assertEqual([shot["shot_number"] for shot in review[2]], [1, 2])
            self.assertEqual(review[1][0]["target_point"], (0.2, 0.3))
            self.assertEqual(review[2][1]["target_point"], (0.7, 0.4))
        finally:
            for widget in widgets:
                widget.deleteLater()

    def test_two_real_clients_keep_shoot_images_and_q0_on_their_own_channels(self):
        servers, clients, heartbeat_threads = [], [], []
        received = {1: [], 2: []}
        notifications = {1: [], 2: []}

        def wait_until(predicate):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if predicate():
                    return True
                time.sleep(0.01)
            return False

        with tempfile.TemporaryDirectory() as directory:
            try:
                for port in (1, 2):
                    # Never expose discovery or take a live board's stable ports.
                    with (
                        patch("server_client.server_core.PortMapping.get_port", return_value=0),
                        patch("server_client.server_core.PortMapping.get_data_port", return_value=0),
                        patch("server_client.server_core.PortMapping.get_stream_port", return_value=0),
                    ):
                        server = MBT03ServerCore(port, system_id="isolation-test")
                    servers.append(server)
                    server.shoot_image_signal.connect(
                        lambda frame, meta, pid=port: received[pid].append((frame, meta)),
                        type=Qt.DirectConnection,
                    )
                    server.shoot_notify_signal.connect(
                        lambda timestamp, pid=port: notifications[pid].append(timestamp),
                        type=Qt.DirectConnection,
                    )
                    server.start()
                    client = MBT03ClientCore(prior_port_id=port, config_dir=os.path.join(directory, str(port)))
                    clients.append(client)
                    client.running = True
                    client.context = zmq.Context()
                    self.assertEqual(client._connect("127.0.0.1", server.port, port), "accepted")
                    thread = threading.Thread(target=client._heartbeat_loop, daemon=True)
                    heartbeat_threads.append(thread)
                    thread.start()
                    self.assertTrue(wait_until(lambda: server.is_connected and client.is_connected))
                    client.q0_value = [0.2 * port, 0.3 * port]
                expected_counts = {1: 0, 2: 0}
                for port in (2, 1, 2, 1, 1, 2):
                    self.assertTrue(wait_until(
                        lambda: time.time() - clients[port - 1]._last_shoot_time >= 0.02
                    ))
                    clients[port - 1]._shoot_frame = np.full((48, 64, 3), 60 * port, dtype=np.uint8)
                    self.assertTrue(clients[port - 1].shoot())
                    expected_counts[port] += 1
                    self.assertTrue(wait_until(lambda: len(received[port]) == expected_counts[port]))
                    self.assertEqual({pid: len(items) for pid, items in received.items()}, expected_counts)
                # Hardware triggers already represent individual shots. Deliver
                # bursts on both channels without waiting for earlier images.
                for port in (2, 1):
                    for _ in range(3):
                        clients[port - 1]._shoot_frame = np.full((48, 64, 3), 60 * port, dtype=np.uint8)
                        self.assertTrue(clients[port - 1].shoot(debounce=False))
                        expected_counts[port] += 1
                self.assertTrue(wait_until(lambda: all(
                    len(received[pid]) == expected_counts[pid]
                    and len(notifications[pid]) == expected_counts[pid]
                    for pid in (1, 2)
                )))
                for port, items in received.items():
                    for frame, metadata in items:
                        self.assertAlmostEqual(float(frame.mean()), 60 * port, delta=2)
                        self.assertEqual(metadata["q0"], [0.2 * port, 0.3 * port])
            finally:
                for client in clients:
                    client.running = False
                    client.connected = False
                for thread in heartbeat_threads:
                    thread.join(timeout=2)
                for client in clients:
                    client.stop()
                for server in servers:
                    server.stop()


if __name__ == "__main__":
    unittest.main()
