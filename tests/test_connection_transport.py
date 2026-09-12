import os
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import zmq
from PyQt5.QtCore import Qt

from server_client.client_core import MBT03ClientCore
from server_client.discovery import ServerFinder
from server_client.server_core import MBT03ServerCore


class ConnectionTransportTests(unittest.TestCase):
    def test_leftover_security_file_is_ignored_by_plain_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(
                os.path.join(directory, "security_config.json"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("not valid JSON")

            client = MBT03ClientCore(config_dir=directory)
            client.context = zmq.Context()
            sockets = [
                client._make_control_socket(),
                client._make_stream_socket(),
                client._make_data_socket(),
            ]
            try:
                for socket in sockets:
                    self.assertEqual(socket.getsockopt(zmq.MECHANISM), zmq.NULL)
            finally:
                for socket in sockets:
                    socket.close(0)
                client.context.term()

    def test_server_finder_reuses_and_closes_browser(self):
        zeroconf = MagicMock()
        browser = MagicMock()
        with patch(
            "server_client.discovery.Zeroconf", return_value=zeroconf
        ) as zeroconf_factory, patch(
            "server_client.discovery.ServiceBrowser", return_value=browser
        ) as browser_factory:
            finder = ServerFinder(log_func=lambda _message: None)
            finder.start()
            finder.start()
            finder.stop()

        zeroconf_factory.assert_called_once_with()
        browser_factory.assert_called_once()
        browser.cancel.assert_called_once_with()
        zeroconf.close.assert_called_once_with()

    def test_three_channels_exchange_stream_and_wifi_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            server = MBT03ServerCore(4, system_id="shared-system")
            client = MBT03ClientCore(prior_port_id=4, config_dir=directory)
            requests = []
            server_events = []
            stream_frames = []
            client.wifi_config_request_signal.connect(
                requests.append, type=Qt.DirectConnection
            )
            server.wifi_config_event_signal.connect(
                server_events.append, type=Qt.DirectConnection
            )
            server.stream_frame_signal.connect(
                stream_frames.append, type=Qt.DirectConnection
            )
            heartbeat_thread = None
            try:
                server.start()
                client.running = True
                client.context = zmq.Context()
                self.assertEqual(
                    client._connect("127.0.0.1", server.port, 4), "accepted"
                )
                self.assertEqual(client.socket.getsockopt(zmq.MECHANISM), zmq.NULL)
                self.assertEqual(
                    client.stream_socket.getsockopt(zmq.MECHANISM), zmq.NULL
                )
                self.assertEqual(
                    client.data_socket.getsockopt(zmq.MECHANISM), zmq.NULL
                )
                self.assertEqual(client.current_server_stream_port, server.stream_port)

                heartbeat_thread = threading.Thread(
                    target=client._heartbeat_loop, daemon=True
                )
                heartbeat_thread.start()
                self.assertTrue(wait_until(lambda: server.is_connected, 3.0))

                source = np.zeros((24, 32, 3), dtype=np.uint8)
                ok, encoded = cv2.imencode(".jpg", source)
                self.assertTrue(ok)
                self.assertTrue(client._queue_stream_frame(encoded.tobytes()))
                self.assertTrue(wait_until(lambda: bool(stream_frames), 3.0))
                self.assertEqual(stream_frames[0].shape[:2], (24, 32))

                request_id = "transport-request-0001"
                result = server.request_wifi_config(
                    "MBT03-5G",
                    "testpass123",
                    request_id,
                    rollback_timeout_seconds=90,
                )
                self.assertTrue(result["ok"], result)
                self.assertTrue(wait_until(lambda: bool(requests), 3.0))
                self.assertNotIn("auth", requests[0])
                self.assertTrue(
                    wait_until(
                        lambda: any(
                            event.get("kind") == "ack"
                            and event.get("status") == "accepted"
                            for event in server_events
                        ),
                        3.0,
                    )
                )
            finally:
                client.running = False
                client.connected = False
                if heartbeat_thread is not None:
                    heartbeat_thread.join(timeout=2.0)
                client.stop()
                server.stop()


def wait_until(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


if __name__ == "__main__":
    unittest.main()
