"""PC-side transport regression tests; no gun or LoRa hardware is contacted."""
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import cv2
import numpy as np
import zmq
from PyQt5.QtCore import Qt

from server_client.protocol import Protocol
from server_client.server_core import MBT03ServerCore
from test_connection_timeout import _make_server_harness


class FourGunBurstTests(unittest.TestCase):
    def decoder(self):
        server = _make_server_harness()
        server._decode_lock = threading.Lock()
        server._decode_inflight = 1
        received = []
        server.shoot_image_signal.connect(
            lambda frame, meta: received.append(meta), type=Qt.DirectConnection)
        encoded = cv2.imencode('.png', np.zeros((8, 8, 3), np.uint8))[1].tobytes()
        return server, received, encoded

    def test_admitted_image_survives_heartbeat_timeout_during_decode(self):
        server, received, encoded = self.decoder()
        server.last_client_heartbeat = 100.0
        server._connection_state = Protocol.CONNECTION_STATE_OFFLINE
        with patch('server_client.server_core.time.monotonic', return_value=107.0):
            server._decode_shoot_image(encoded, session_generation=1, received_at=101.0)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['_server_received_at'], 101.0)
        self.assertEqual(server._decode_inflight, 0)

    def test_admitted_image_cannot_cross_replaced_connection(self):
        server, received, encoded = self.decoder()
        server._session_generation = 2
        server._decode_shoot_image(encoded, session_generation=1, received_at=101.0)
        self.assertEqual(received, [])
        self.assertEqual(server._decode_inflight, 0)

    def test_four_tcp_senders_queue_all_64_images_before_decoders_resume(self):
        context = zmq.Context()
        release = threading.Event()
        servers, senders, loops, arrivals, errors = [], [], [], [], []
        arrival_lock = threading.Lock()
        # Noisy 640x480 JPEGs exercise transport buffering with realistic sizes,
        # instead of tiny solid-color images. Sequence metadata checks identity.
        frame = np.random.default_rng(42).integers(0, 256, (480, 640, 3), dtype=np.uint8)
        encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 65])[1].tobytes()

        def collect(port, frame, meta):
            with arrival_lock:
                arrivals.append((port, meta['audit_shot'], meta['_server_received_at']))

        try:
            for port in range(1, 5):
                server = _make_server_harness()
                server.port_id = port
                server.running = True
                server._decode_lock = threading.Lock()
                server._decode_inflight = 0
                server._decode_max_inflight = MBT03ServerCore.SHOOT_QUEUE_CAPACITY
                server._decode_pool = ThreadPoolExecutor(max_workers=2)
                server.data_socket = context.socket(zmq.PULL)
                server.data_socket.setsockopt(zmq.RCVHWM, MBT03ServerCore.SHOOT_QUEUE_CAPACITY)
                tcp_port = server.data_socket.bind_to_random_port('tcp://127.0.0.1')
                server.shoot_image_signal.connect(
                    lambda frame, meta, port=port: collect(port, frame, meta),
                    type=Qt.DirectConnection)
                original = server._decode_shoot_image

                def delayed_decode(*args, original=original):
                    release.wait(10)
                    original(*args)

                server._decode_shoot_image = delayed_decode
                servers.append(server)
                loop = threading.Thread(target=server._data_loop)
                loops.append(loop)
                loop.start()

                def send_burst(tcp_port=tcp_port):
                    # Same HWM/time limit as the deployed sender, independent
                    # sockets owned by their threads. Change only the PC here.
                    sender = context.socket(zmq.PUSH)
                    sender.setsockopt(zmq.SNDHWM, 3)
                    sender.setsockopt(zmq.SNDTIMEO, 200)
                    sender.connect(f'tcp://127.0.0.1:{tcp_port}')
                    try:
                        for shot in range(16):
                            sender.send_multipart([
                                Protocol.MSG_SHOOT_IMAGE, encoded,
                                Protocol.encode_payload({'audit_shot': shot}),
                            ])
                    except Exception as exc:
                        errors.append(exc)
                    finally:
                        sender.close(1000)

                sender_thread = threading.Thread(target=send_burst)
                senders.append(sender_thread)

            for sender in senders:
                sender.start()
            for sender in senders:
                sender.join(4)
            self.assertFalse(any(sender.is_alive() for sender in senders))
            self.assertEqual(errors, [])
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if all(server._decode_inflight == 16 for server in servers):
                    break
                time.sleep(.005)
            # Each complete burst must be timestamped BEFORE decoding is freed.
            self.assertEqual([server._decode_inflight for server in servers], [16] * 4)
            # Windows monotonic timestamps may share a ~15 ms tick. Put the
            # simulated cutoff on a later tick without relaxing the strict
            # before-deadline assertion used by the application.
            admitted_at = time.monotonic()
            while time.monotonic() <= admitted_at:
                time.sleep(.001)
            cutoff = time.monotonic()
            # Heartbeat expires after admission, while all four decoders wait.
            for server in servers:
                with server._lock:
                    server.last_client_heartbeat = cutoff - Protocol.CONNECTION_OFFLINE_TIMEOUT - 1
                    server._connection_state = Protocol.CONNECTION_STATE_OFFLINE
            release.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                with arrival_lock:
                    if len(arrivals) == 64:
                        break
                time.sleep(.005)
            with arrival_lock:
                self.assertEqual(len(arrivals), 64)
                for port in range(1, 5):
                    self.assertEqual(sorted(shot for pid, shot, _ in arrivals if pid == port), list(range(16)))
                self.assertTrue(all(received_at < cutoff for _, _, received_at in arrivals))
        finally:
            release.set()
            for server in servers:
                server.running = False
            for sender in senders:
                if sender.ident is not None:
                    sender.join(5)
            for loop in loops:
                loop.join(2)
            for server in servers:
                server._decode_pool.shutdown(wait=True)
                server.data_socket.close(0)
            context.term()


if __name__ == '__main__':
    unittest.main()
