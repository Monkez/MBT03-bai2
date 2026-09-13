import ipaddress
import queue
import struct
import threading
import time
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QObject

from server_client.client_core import MBT03ClientCore
from server_client.protocol import Protocol
from server_client.server_core import MBT03ServerCore


class _RecordingSocket:
    def __init__(self):
        self.sent = []

    def send_multipart(self, frames, flags=0):
        self.sent.append((frames, flags))

    def send(self, payload, flags=0):
        self.sent.append((payload, flags))


class _RetryOnceSocket(_RecordingSocket):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    def send_multipart(self, frames, flags=0):
        self.attempts += 1
        if self.attempts == 1:
            import zmq
            raise zmq.Again()
        super().send_multipart(frames, flags)


class _AlwaysAgainSocket:
    def __init__(self):
        self.connected_to = None
        self.closed = False
        self.close_linger = None

    def connect(self, endpoint):
        self.connected_to = endpoint

    def send_multipart(self, frames, flags=0):
        import zmq
        raise zmq.Again()

    def close(self, linger=None):
        self.closed = True
        self.close_linger = linger


class _DeferredExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, func, *args):
        self.jobs.append((func, args))


class _FakeFrame:
    shape = (Protocol.SHOOT_RESOLUTION[1], Protocol.SHOOT_RESOLUTION[0], 3)


def _make_server_harness():
    server = MBT03ServerCore.__new__(MBT03ServerCore)
    QObject.__init__(server)
    server.port_id = 1
    server.port = 1711
    server.data_port = 1811
    server.stream_port = 1911
    server._accepting_connections = True
    server._lock = threading.Lock()
    server._session_generation = 1
    server.connected_client_identity = b'old-identity'
    server.connected_client_name = 'Client-test'
    server.connected_client_info = {'client_ip': '127.0.0.1'}
    server.last_client_heartbeat = time.monotonic()
    server.last_client_activity = server.last_client_heartbeat
    server._rtt_history = deque(maxlen=Protocol.RTT_WINDOW_SIZE)
    server._battery_percent = None
    server._rejected_clients = {}
    server._stream_active = False
    server._connection_state = Protocol.CONNECTION_STATE_HEALTHY
    server._recovery_heartbeat_count = 0
    server._last_recovery_sample_at = None
    server._last_recovery_sequence = None
    server._last_heartbeat_sequence = None
    server._last_accepted_shoot_time = 0
    server._stream_fps_count = 0
    server._stream_fps_timer = 0
    server.CONNECT_GRACE_TIMEOUT = 8.0
    server.PENDING_REPLACE_TIMEOUT = 2.5
    server._control_thread_id = None
    server._control_send_queue = queue.Queue()
    server.stream_socket = _RecordingSocket()
    server._stream_thread = None
    server._send_control = lambda *args, **kwargs: True
    server._log = lambda *args, **kwargs: None
    server._emit_connection_quality = lambda *args, **kwargs: None
    return server


def _make_client_harness():
    client = MBT03ClientCore.__new__(MBT03ClientCore)
    QObject.__init__(client)
    client._lock = threading.Lock()
    client._data_send_lock = threading.Lock()
    client._stream_send_lock = threading.Lock()
    client._priority_control_send_queue = queue.Queue(maxsize=32)
    client._control_send_queue = queue.Queue(maxsize=128)
    client._deferred_priority_control_send = None
    client._deferred_control_send = None
    client.connected = True
    client.running = True
    client.socket = _RecordingSocket()
    client.stream_socket = _RecordingSocket()
    client.data_socket = _RecordingSocket()
    client.client_name = 'Client-test'
    client.prior_port_id = 1
    client._last_system_id = None
    client._connection_state = Protocol.CONNECTION_STATE_HEALTHY
    client._recovery_ack_count = 0
    client._last_recovery_sample_at = None
    client._last_recovery_sequence = None
    client._current_hb_interval = Protocol.HEARTBEAT_INTERVAL
    client._rtt_history = deque(maxlen=Protocol.RTT_WINDOW_SIZE)
    client._connection_generation = 1
    client._active_wifi_request_id = None
    client._stream_paused_for_link = False
    client._last_shoot_time = 0
    client._shoot_frame = _FakeFrame()
    client._shoot_pool = _DeferredExecutor()
    client.q0_value = [0.5, 0.5]
    client.q0_size = 0
    client._log = lambda *args, **kwargs: None
    client._encode_frame_jpeg = lambda *args, **kwargs: b'jpeg'
    return client


class ConnectionTimeoutPolicyTests(unittest.TestCase):
    def test_connection_settings_are_validated_and_applied_atomically(self):
        original = Protocol.connection_settings()
        custom = dict(original)
        custom.update({
            'heartbeat_interval_seconds': 0.9,
            'heartbeat_min_interval_seconds': 0.4,
            'heartbeat_max_interval_seconds': 1.4,
            'degraded_after_seconds': 3.0,
            'offline_after_seconds': 5.0,
            'client_reconnect_after_seconds': 7.0,
            'session_release_after_seconds': 12.0,
            'recovery_ack_count': 3,
        })
        try:
            self.assertEqual(Protocol.configure_connection(custom), custom)
            before_invalid = Protocol.connection_settings()
            invalid = dict(custom)
            invalid['offline_after_seconds'] = 2.0
            with self.assertRaises(ValueError):
                Protocol.configure_connection(invalid)
            self.assertEqual(Protocol.connection_settings(), before_invalid)
            self.assertEqual(
                Protocol.HEARTBEAT_TIMEOUT,
                Protocol.SERVER_SESSION_TIMEOUT)
            self.assertEqual(
                Protocol.CLIENT_DISCONNECT_TIMEOUT,
                Protocol.CLIENT_RECONNECT_TIMEOUT)
        finally:
            Protocol.configure_connection(original)

    def test_media_settings_are_validated_and_applied_atomically(self):
        original = Protocol.media_settings()
        custom = {
            'shoot_resolution': [800, 600],
            'shoot_jpeg_quality': 70,
            'stream_resolution': [480, 360],
            'stream_jpeg_quality': 45,
            'stream_fps_target': 20,
        }
        try:
            self.assertEqual(Protocol.configure_media(custom), custom)
            before_invalid = Protocol.media_settings()
            invalid = dict(custom)
            invalid['stream_jpeg_quality'] = 5
            with self.assertRaises(ValueError):
                Protocol.configure_media(invalid)
            self.assertEqual(Protocol.media_settings(), before_invalid)
        finally:
            Protocol.configure_media(original)

    def test_connection_state_thresholds(self):
        cases = (
            (-1.0, Protocol.CONNECTION_STATE_HEALTHY),
            (0.0, Protocol.CONNECTION_STATE_HEALTHY),
            (3.499, Protocol.CONNECTION_STATE_HEALTHY),
            (3.5, Protocol.CONNECTION_STATE_DEGRADED),
            (5.999, Protocol.CONNECTION_STATE_DEGRADED),
            (6.0, Protocol.CONNECTION_STATE_OFFLINE),
            (14.999, Protocol.CONNECTION_STATE_OFFLINE),
            (15.0, Protocol.CONNECTION_STATE_SESSION_EXPIRED),
        )
        for elapsed, expected in cases:
            with self.subTest(elapsed=elapsed):
                self.assertEqual(
                    Protocol.classify_connection_state(elapsed), expected)

    def test_soft_timeouts_do_not_trigger_teardown(self):
        for elapsed in (
            Protocol.CONNECTION_DEGRADED_TIMEOUT,
            Protocol.CONNECTION_OFFLINE_TIMEOUT,
            Protocol.CLIENT_RECONNECT_TIMEOUT - 0.001,
        ):
            with self.subTest(elapsed=elapsed):
                self.assertFalse(Protocol.should_client_reconnect(elapsed))
                self.assertFalse(
                    Protocol.should_release_server_session(elapsed))

    def test_client_reconnects_before_server_releases_slot(self):
        self.assertTrue(
            Protocol.should_client_reconnect(
                Protocol.CLIENT_RECONNECT_TIMEOUT))
        self.assertFalse(
            Protocol.should_release_server_session(
                Protocol.CLIENT_RECONNECT_TIMEOUT))
        self.assertTrue(
            Protocol.should_release_server_session(
                Protocol.SERVER_SESSION_TIMEOUT))

    def test_heartbeat_probe_range(self):
        self.assertEqual(Protocol.HEARTBEAT_INTERVAL, 1.0)
        self.assertEqual(Protocol.HEARTBEAT_MIN_INTERVAL, 0.5)
        self.assertEqual(Protocol.HEARTBEAT_MAX_INTERVAL, 1.5)
        self.assertLessEqual(
            Protocol.HEARTBEAT_MIN_INTERVAL,
            Protocol.HEARTBEAT_INTERVAL)
        self.assertLessEqual(
            Protocol.HEARTBEAT_INTERVAL,
            Protocol.HEARTBEAT_MAX_INTERVAL)

    def test_only_live_and_degraded_states_are_operational(self):
        self.assertTrue(Protocol.is_operational_connection_state(
            Protocol.CONNECTION_STATE_HEALTHY))
        self.assertTrue(Protocol.is_operational_connection_state(
            Protocol.CONNECTION_STATE_DEGRADED))
        self.assertFalse(Protocol.is_operational_connection_state(
            Protocol.CONNECTION_STATE_OFFLINE))
        self.assertFalse(Protocol.is_operational_connection_state(
            Protocol.CONNECTION_STATE_SESSION_EXPIRED))

    def test_recovery_streak_requires_ordered_and_timely_samples(self):
        minimum_gap, maximum_gap = Protocol.recovery_sample_gap_bounds()
        valid_gap = (minimum_gap + maximum_gap) / 2.0

        count, sample_at, sequence = Protocol.next_recovery_streak(
            0, None, None, 100.0, sequence=100, rtt_seconds=0.1)
        self.assertEqual(count, 1)

        # A buffered burst restarts rather than completes the streak.
        count, sample_at, sequence = Protocol.next_recovery_streak(
            count,
            sample_at,
            sequence,
            100.0 + minimum_gap / 10.0,
            sequence=101,
            rtt_seconds=0.1,
        )
        self.assertEqual(count, 1)

        # A skipped sequence also restarts the streak.
        count, sample_at, sequence = Protocol.next_recovery_streak(
            count,
            sample_at,
            sequence,
            sample_at + valid_gap,
            sequence=103,
            rtt_seconds=0.1,
        )
        self.assertEqual(count, 1)

        # A sample arriving too late cannot extend an old streak.
        count, sample_at, sequence = Protocol.next_recovery_streak(
            count,
            sample_at,
            sequence,
            sample_at + maximum_gap + 0.1,
            sequence=104,
            rtt_seconds=0.1,
        )
        self.assertEqual(count, 1)

        # A buffered ACK with excessive RTT is ignored completely.
        count, sample_at, sequence = Protocol.next_recovery_streak(
            count,
            sample_at,
            sequence,
            sample_at + valid_gap,
            sequence=105,
            rtt_seconds=maximum_gap + 0.1,
        )
        self.assertEqual((count, sample_at, sequence), (0, None, None))

    def test_legacy_recovery_samples_use_cadence_when_sequence_is_absent(self):
        minimum_gap, maximum_gap = Protocol.recovery_sample_gap_bounds()
        valid_gap = (minimum_gap + maximum_gap) / 2.0
        count, sample_at, sequence = Protocol.next_recovery_streak(
            0, None, None, 10.0)
        count, sample_at, sequence = Protocol.next_recovery_streak(
            count, sample_at, sequence, 10.0 + valid_gap)
        self.assertEqual(count, 2)


class ConnectionCoreTimeoutTests(unittest.TestCase):
    def test_stale_monitor_snapshot_cannot_mutate_reconnected_session(self):
        server = _make_server_harness()
        old_identity = server.connected_client_identity
        old_generation = server._session_generation
        old_heartbeat = server.last_client_heartbeat

        # Simulate a reconnect arriving after the monitor took its snapshot.
        server.connected_client_identity = b'new-identity'
        server._session_generation += 1
        server.last_client_heartbeat = time.monotonic()

        changed = server._set_connection_state(
            Protocol.CONNECTION_STATE_OFFLINE,
            Protocol.CONNECTION_OFFLINE_TIMEOUT,
            expected_identity=old_identity,
            expected_generation=old_generation,
            expected_heartbeat=old_heartbeat,
        )
        disconnected = server._disconnect_client(
            "stale timeout",
            expected_identity=old_identity,
            expected_generation=old_generation,
            expected_heartbeat=old_heartbeat,
        )

        self.assertFalse(changed)
        self.assertFalse(disconnected)
        self.assertEqual(server.connected_client_identity, b'new-identity')
        self.assertEqual(
            server._connection_state,
            Protocol.CONNECTION_STATE_HEALTHY)

    def test_server_waits_for_recovery_state_before_allowing_operations(self):
        server = _make_server_harness()
        server._connection_state = Protocol.CONNECTION_STATE_OFFLINE
        server.last_client_heartbeat = time.monotonic()
        minimum_gap, maximum_gap = Protocol.recovery_sample_gap_bounds()
        valid_gap = (minimum_gap + maximum_gap) / 2.0
        payload_1 = struct.pack('!dddQ', 0.0, 10.0, -1.0, 100)
        payload_2 = struct.pack('!dddQ', 0.0, 10.0, -1.0, 101)

        with patch(
            'server_client.server_core.time.monotonic',
            # The live-target probe samples the monotonic clock as part of its
            # heartbeat-age guard.  ``is_connected`` exits on the offline
            # state before sampling it, so the second heartbeat is the third
            # clock read and must land one valid recovery interval later.
            side_effect=[100.0, 100.0, 100.0 + valid_gap],
        ):
            server._handle_heartbeat(
                server.connected_client_identity, payload_1)
            self.assertEqual(
                server._connection_state,
                Protocol.CONNECTION_STATE_OFFLINE)
            self.assertIsNone(server._get_live_client_identity())
            self.assertFalse(server.is_connected)
            server._handle_heartbeat(
                server.connected_client_identity, payload_2)

        self.assertEqual(
            server._connection_state,
            Protocol.CONNECTION_STATE_HEALTHY)
        # Restore a real monotonic timestamp before exercising public age-based
        # properties outside the patched clock.
        server.last_client_heartbeat = time.monotonic()
        self.assertEqual(
            server._get_live_client_identity(),
            server.connected_client_identity)
        self.assertTrue(server.is_connected)

    def test_timeout_classifier_cannot_improve_an_offline_state(self):
        server = _make_server_harness()
        server._connection_state = Protocol.CONNECTION_STATE_OFFLINE
        changed = server._set_connection_state(
            Protocol.CONNECTION_STATE_DEGRADED,
            Protocol.CONNECTION_DEGRADED_TIMEOUT,
        )
        self.assertFalse(changed)
        self.assertEqual(
            server._connection_state, Protocol.CONNECTION_STATE_OFFLINE)

        client = _make_client_harness()
        client._connection_state = Protocol.CONNECTION_STATE_OFFLINE
        changed = client._set_connection_state(
            Protocol.CONNECTION_STATE_DEGRADED,
            Protocol.CONNECTION_DEGRADED_TIMEOUT,
        )
        self.assertFalse(changed)
        self.assertEqual(
            client._connection_state, Protocol.CONNECTION_STATE_OFFLINE)

    def test_server_blocks_legacy_password_bearing_uart_command(self):
        server = _make_server_harness()
        self.assertFalse(
            server.send_uart_command("Wifi#example#password123")
        )

    def test_same_device_reconnect_resets_stream_state_and_emits_signal(self):
        server = _make_server_harness()
        server._stream_active = True
        stream_states = []
        server.stream_state_signal.connect(stream_states.append)

        server._handle_connect_request(
            b'new-identity',
            Protocol.encode_payload({
                'client_name': server.connected_client_name,
                'client_ip': '127.0.0.2',
            }),
        )

        self.assertFalse(server._stream_active)
        self.assertEqual(stream_states, [False])
        self.assertEqual(server.connected_client_identity, b'new-identity')
        self.assertEqual(server._session_generation, 2)

    def test_client_drain_drops_queue_and_stream_when_offline(self):
        client = _make_client_harness()
        self.assertTrue(client._enqueue_control_send([b'queued']))

        with client._lock:
            client._connection_state = Protocol.CONNECTION_STATE_OFFLINE
            client._stream_paused_for_link = True
            client._connection_generation += 1

        client._drain_control_sends()

        self.assertEqual(client.socket.sent, [])
        self.assertTrue(client._control_send_queue.empty())
        self.assertFalse(client._queue_stream_frame(b'frame'))
        self.assertEqual(client.stream_socket.sent, [])
        self.assertFalse(client._enqueue_control_send([b'late']))

    def test_degraded_client_suspends_stream_but_keeps_control_probes(self):
        client = _make_client_harness()
        with client._lock:
            client._connection_state = Protocol.CONNECTION_STATE_DEGRADED
            client._stream_paused_for_link = True

        self.assertTrue(client._enqueue_control_send([b'control']))
        self.assertFalse(client._queue_stream_frame(b'frame'))
        client._drain_control_sends()

        self.assertEqual(len(client.socket.sent), 1)
        self.assertEqual(client.socket.sent[0][0], [b'control'])
        self.assertEqual(client.stream_socket.sent, [])

    def test_stream_frame_uses_dedicated_socket_not_control(self):
        client = _make_client_harness()

        self.assertTrue(client._queue_stream_frame(b'frame'))

        self.assertEqual(client.socket.sent, [])
        self.assertEqual(client.stream_socket.sent[0][0], b'frame')

    def test_client_control_queue_reports_full_without_evicting(self):
        client = _make_client_harness()
        client._control_send_queue = queue.Queue(maxsize=1)

        self.assertTrue(client._enqueue_control_send([b'first']))
        self.assertFalse(client._enqueue_control_send([b'second']))
        client._drain_control_sends()

        self.assertEqual(
            [entry[0] for entry in client.socket.sent],
            [[b'first']],
        )

    def test_client_retries_control_frame_after_temporary_backpressure(self):
        client = _make_client_harness()
        client.socket = _RetryOnceSocket()
        self.assertTrue(
            client._enqueue_control_send([b'important'], priority=True)
        )

        client._drain_control_sends()
        self.assertEqual(client.socket.sent, [])
        self.assertIsNotNone(client._deferred_priority_control_send)

        client._drain_control_sends()
        self.assertEqual(client.socket.sent[0][0], [b'important'])
        self.assertIsNone(client._deferred_priority_control_send)

    def test_failed_connect_send_closes_socket_before_context_rotation(self):
        client = _make_client_harness()
        failing_socket = _AlwaysAgainSocket()

        with patch.object(
            client, '_make_control_socket', return_value=failing_socket
        ), patch('server_client.client_core.time.sleep'):
            result = client._connect('10.0.0.2', 1711, 1)

        self.assertEqual(result, 'timeout')
        self.assertEqual(failing_socket.connected_to, 'tcp://10.0.0.2:1711')
        self.assertTrue(failing_socket.closed)
        self.assertEqual(failing_socket.close_linger, 0)
        self.assertIsNone(client.socket)
        self.assertIsNone(client.data_socket)

    def test_wifi_change_does_not_start_when_ack_cannot_be_sent(self):
        client = _make_client_harness()
        requests = []
        client.wifi_config_request_signal.connect(requests.append)
        client._send_wifi_ack = lambda *args, **kwargs: False
        payload = {
            "version": Protocol.WIFI_CONFIG_VERSION,
            "request_id": "req-ack-failure",
            "ssid": "MBT03-5G",
            "password": "testpass123",
            "rollback_timeout_seconds": 90.0,
        }
        client._handle_wifi_config_request(Protocol.encode_payload(payload))

        self.assertEqual(requests, [])
        self.assertIsNone(client._active_wifi_request_id)

    def test_local_scan_range_uses_wlan_prefix(self):
        ip_output = (
            '[{"addr_info":[{"family":"inet","local":"10.207.242.24",'
            '"prefixlen":24,"scope":"global"}]}]'
        )
        with patch(
            'server_client.client_core.subprocess.run',
            return_value=SimpleNamespace(returncode=0, stdout=ip_output),
        ):
            network, local_ip = MBT03ClientCore._local_ipv4_scan_range()

        self.assertEqual(network, ipaddress.ip_network('10.207.242.0/24'))
        self.assertEqual(local_ip, ipaddress.ip_address('10.207.242.24'))

    def test_subnet_scan_prioritizes_previous_pedestal(self):
        client = _make_client_harness()
        client.prior_port_id = 3
        client._last_subnet_scan_at = 0.0
        client._local_ipv4_scan_range = lambda: (
            ipaddress.ip_network('10.0.0.0/29'),
            ipaddress.ip_address('10.0.0.2'),
        )
        reachable = {
            ('10.0.0.3', 1999),
            ('10.0.0.4', 1711),
        }
        client._tcp_probe = (
            lambda ip, port, timeout=None: (ip, port) in reachable
        )

        found = client._scan_local_stable_servers()

        self.assertEqual(
            found,
            [('10.0.0.3', 1999, 3), ('10.0.0.4', 1711, 1)],
        )

    def test_main_loop_uses_subnet_fallback_when_mdns_is_empty(self):
        client = _make_client_harness()
        client.connected = False
        client._last_server_ip = None
        client.finder = SimpleNamespace(
            find_all_servers=lambda **_kwargs: [],
        )
        client._scan_local_stable_servers = lambda: [
            ('10.207.242.205', 1711, 1)
        ]
        client._connect = MagicMock(return_value='accepted')
        client._on_connect_success = MagicMock()
        client._heartbeat_loop = MagicMock()
        client._cleanup_connection = MagicMock()
        client._reconnect_delay = Protocol.RECONNECT_MIN_DELAY

        client._main_loop_step(is_first_boot=False)

        client._connect.assert_called_once_with('10.207.242.205', 1711, 1)
        client._on_connect_success.assert_called_once_with(
            '10.207.242.205', 1711, 1, None
        )
        client._heartbeat_loop.assert_called_once_with()
        client._cleanup_connection.assert_called_once_with()

    def test_async_shoot_image_is_not_sent_after_connection_changes(self):
        client = _make_client_harness()
        data_socket = client.data_socket

        self.assertTrue(client.shoot())
        self.assertEqual(len(client._shoot_pool.jobs), 1)

        with client._lock:
            client._connection_state = Protocol.CONNECTION_STATE_OFFLINE
            client._connection_generation += 1
        func, args = client._shoot_pool.jobs.pop()
        func(*args)

        self.assertEqual(data_socket.sent, [])


if __name__ == '__main__':
    unittest.main()
