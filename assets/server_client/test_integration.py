# -*- coding: utf-8 -*-
"""Local integration check for the three-channel MBT03 transport."""

import os
import sys
import tempfile
import threading
import time

import cv2
import numpy as np
import zmq
from PyQt5.QtCore import QCoreApplication, Qt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server_client.client_core import MBT03ClientCore
from server_client.server_core import MBT03ServerCore


def wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def main():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    server = MBT03ServerCore(port_id=1, system_id="integration-system")
    client = None
    heartbeat_thread = None

    with tempfile.TemporaryDirectory(prefix="mbt03-integration-") as config_dir:
        try:
            print("[1/5] Starting server...")
            server.start()

            print("[2/5] Connecting client directly...")
            client = MBT03ClientCore(prior_port_id=1, config_dir=config_dir)
            client.running = True
            client.context = zmq.Context()
            result = client._connect("127.0.0.1", server.port, 1)
            if result != "accepted":
                raise RuntimeError(f"handshake failed: {result}")

            if client.current_server_stream_port != server.stream_port:
                raise RuntimeError("client received the wrong stream port")

            heartbeat_thread = threading.Thread(
                target=client._heartbeat_loop,
                name="IntegrationHeartbeat",
                daemon=True,
            )
            heartbeat_thread.start()
            if not wait_until(lambda: server.is_connected):
                raise RuntimeError("heartbeat did not establish a live session")

            print("[3/5] Checking isolated stream channel...")
            stream_frames = []
            server.stream_frame_signal.connect(
                stream_frames.append, type=Qt.DirectConnection
            )
            source = np.zeros((24, 32, 3), dtype=np.uint8)
            ok, encoded = cv2.imencode(".jpg", source)
            if not ok or not client._queue_stream_frame(encoded.tobytes()):
                raise RuntimeError("could not queue stream frame")
            if not wait_until(lambda: bool(stream_frames)):
                raise RuntimeError("server did not receive the stream frame")

            print("[4/5] Checking bidirectional data...")
            server_data = []
            client_logs = []
            server.data_received_signal.connect(
                server_data.append, type=Qt.DirectConnection
            )
            client.log_signal.connect(
                client_logs.append, type=Qt.DirectConnection
            )
            if not client.send_data({"source": "client", "value": 42}):
                raise RuntimeError("client-to-server send failed")
            if not server.send_data_to_client({"source": "server", "value": 24}):
                raise RuntimeError("server-to-client send failed")
            if not wait_until(
                lambda: bool(server_data)
                and any("Data:" in message for message in client_logs)
            ):
                raise RuntimeError("bidirectional data was not received")

            print("[5/5] PASS: control, stream and shoot-data transport is healthy.")
            return 0
        except Exception as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        finally:
            if client is not None:
                client.running = False
                client.connected = False
                if heartbeat_thread is not None:
                    heartbeat_thread.join(timeout=2.0)
                client.stop()
            server.stop()
            app.processEvents()


if __name__ == "__main__":
    sys.exit(main())
