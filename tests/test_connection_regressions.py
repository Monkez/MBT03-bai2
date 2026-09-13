import json
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from server_client.client_core import MBT03ClientCore
from server_client.discovery import ServerFinder
from server_client.protocol import Protocol
from server_client.server_core import MBT03ServerCore


class ConnectionRegressionTests(unittest.TestCase):
    def test_live_session_requires_both_device_and_instance_identity(self):
        server = SimpleNamespace(
            connected_client_info={'device_id': 'serial:a', 'instance_id': 'one'},
            connected_client_name='Client-duplicate',
        )
        matches = lambda info: MBT03ServerCore._same_client_process(server, info)
        self.assertTrue(matches({'device_id': 'serial:a', 'instance_id': 'one'}))
        self.assertFalse(matches({'device_id': 'serial:b', 'instance_id': 'one'}))
        self.assertFalse(matches({'device_id': 'serial:a', 'instance_id': 'two'}))
        self.assertFalse(matches({'client_name': 'Client-duplicate'}))

    def test_cancel_interrupts_discovery_and_stays_cancelled(self):
        finder = ServerFinder()
        results = []
        thread = threading.Thread(target=lambda: results.append(
            finder.find_all_servers(timeout=30)))
        thread.start()
        finder.cancel()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results, [[]])
        self.assertEqual(finder.find_all_servers(timeout=30), [])

    def test_failed_atomic_config_replace_preserves_previous_config(self):
        with tempfile.TemporaryDirectory() as directory:
            client = MBT03ClientCore(config_dir=directory)
            try:
                client._save_config()
                with open(client.config_file, encoding='utf-8') as stream:
                    before = json.load(stream)
                client.q0_size = before['q0_size'] + 1
                with patch('server_client.client_core.os.replace', side_effect=OSError('disk failure')):
                    client._save_config()
                with open(client.config_file, encoding='utf-8') as stream:
                    self.assertEqual(json.load(stream), before)
                self.assertFalse(any(name.startswith('.mbt03-config-') for name in os.listdir(directory)))
            finally:
                client.stop()

    def test_wifi_commit_and_rollback_reach_handlers_only_for_current_request(self):
        with tempfile.TemporaryDirectory() as directory:
            client = MBT03ClientCore(config_dir=directory)
            commits, rollbacks = [], []
            client.wifi_config_commit_signal.connect(commits.append)
            client.wifi_config_rollback_signal.connect(rollbacks.append)
            request_id = 'a' * 32
            client._active_wifi_request_id = request_id
            payload = {'version': Protocol.WIFI_CONFIG_VERSION, 'request_id': request_id}
            try:
                for kind in (Protocol.MSG_WIFI_CONFIG_COMMIT, Protocol.MSG_WIFI_CONFIG_ROLLBACK):
                    client._handle_wifi_config_decision(kind, Protocol.encode_payload(payload))
                    client._handle_wifi_config_decision(kind, Protocol.encode_payload(
                        dict(payload, request_id='b' * 32)))
                    client._handle_wifi_config_decision(kind, b'not-json')
                self.assertEqual(commits, [payload])
                self.assertEqual(rollbacks, [payload])
            finally:
                client.stop()

    def test_stale_nonempty_mdns_does_not_suppress_subnet_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            client = MBT03ClientCore(config_dir=directory)
            client.running = True
            client._last_server_ip = None
            client.finder = SimpleNamespace(
                find_all_servers=lambda **kwargs: [('10.0.0.2', 1711, 1, 'old')],
                cancel=lambda: None, stop=lambda: None,
            )
            client._scan_local_stable_servers = MagicMock(return_value=[('10.0.0.3', 1711, 1)])
            client._connect = MagicMock(side_effect=['timeout', 'accepted'])
            client._on_connect_success = MagicMock()
            client._heartbeat_loop = MagicMock()
            client._cleanup_connection = MagicMock()
            try:
                client._main_loop_step(False)
                client._scan_local_stable_servers.assert_called_once_with()
                client._on_connect_success.assert_called_once_with('10.0.0.3', 1711, 1, None)
            finally:
                client.stop()
