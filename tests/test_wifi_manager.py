import json
import os
import tempfile
import threading
import time
import unittest

from OrangePiZero2W.wifi_manager import WiFiTransactionManager


class FakeCore:
    def __init__(self):
        self.statuses = []
        self.reconnects = []
        self.status_event = threading.Event()
        self.active_wifi_request_id = None

    def send_wifi_config_status(self, request_id, status, ssid, error=None):
        self.statuses.append((request_id, status, ssid, error))
        self.status_event.set()
        return True

    def request_reconnect(self, reason):
        self.reconnects.append(reason)

    def restore_active_wifi_request(self, request_id):
        if self.active_wifi_request_id not in {None, request_id}:
            return False
        self.active_wifi_request_id = request_id
        return True


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class WiFiTransactionManagerTests(unittest.TestCase):
    def test_startup_fallback_is_not_recovered_as_an_app_transaction(self):
        core = FakeCore()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'boot-default.json')
            with open(path, 'w', encoding='utf-8') as file:
                json.dump({'version': 1, 'transaction_id': 'boot-default',
                           'ssid': 'DefaultNet', 'status': 'fallback_pending',
                           'startup_fallback': True}, file)
            manager = WiFiTransactionManager(core, transaction_dir=directory)
            self.assertFalse(manager.recover())
            self.assertIsNone(core.active_wifi_request_id)

    def test_recover_ignores_netplan_snapshot_and_allows_uart_sync(self):
        core = FakeCore()
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = os.path.join(
                directory, "request-snapshot.netplan-snapshot.json"
            )
            with open(snapshot_path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "version": 1,
                        "files": [{"path": "/etc/netplan/example.yaml"}],
                    },
                    file,
                )

            manager = WiFiTransactionManager(core, transaction_dir=directory)

            self.assertFalse(manager.recover())
            self.assertIsNone(core.active_wifi_request_id)
            self.assertIsNone(manager.current_transaction)

    def test_recover_validates_filename_matches_transaction_id(self):
        core = FakeCore()
        logs = []
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "wrong-name.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "version": 1,
                        "transaction_id": "different-id",
                        "ssid": "NewNet",
                        "status": "staged",
                        "rollback_deadline": time.time() + 90,
                    },
                    file,
                )

            manager = WiFiTransactionManager(
                core, transaction_dir=directory, log=logs.append
            )

            self.assertFalse(manager.recover())
            self.assertTrue(any("không hợp lệ" in message for message in logs))

    def test_stage_reconnect_and_commit(self):
        core = FakeCore()
        calls = []

        def stage(ssid, password, **kwargs):
            self.assertEqual(password, "password123")
            return {
                "transaction_id": kwargs["transaction_id"],
                "ssid": ssid,
                "status": "staged",
                "rollback_deadline": time.time() + 30,
            }

        def commit(transaction, **_kwargs):
            calls.append("commit")
            transaction["status"] = "committed"
            return "committed"

        manager = WiFiTransactionManager(
            core,
            stage_func=stage,
            commit_func=commit,
            rollback_func=lambda *_args, **_kwargs: "rolled_back",
        )
        request = {
            "request_id": "request-0001",
            "ssid": "MBT03-5G",
            "password": "password123",
            "rollback_timeout_seconds": 90,
        }
        self.assertTrue(manager.handle_request(request))
        self.assertTrue(wait_until(lambda: "wifi_staged" in core.reconnects))
        self.assertTrue(manager.handle_commit({"request_id": "request-0001"}))
        self.assertTrue(wait_until(lambda: calls == ["commit"]))
        self.assertIn(
            ("request-0001", "committed", "MBT03-5G", None),
            core.statuses,
        )

    def test_timeout_rolls_back_and_requests_reconnect(self):
        core = FakeCore()
        rolled_back = threading.Event()

        def stage(ssid, _password, **kwargs):
            return {
                "transaction_id": kwargs["transaction_id"],
                "ssid": ssid,
                "status": "staged",
                "rollback_deadline": time.time() + 0.05,
            }

        def rollback(transaction, **_kwargs):
            transaction["status"] = "rolled_back"
            rolled_back.set()
            return "rolled_back"

        manager = WiFiTransactionManager(
            core,
            stage_func=stage,
            commit_func=lambda *_args, **_kwargs: "committed",
            rollback_func=rollback,
        )
        manager.handle_request(
            {
                "request_id": "request-0002",
                "ssid": "BackupNet",
                "password": "password123",
            }
        )
        self.assertTrue(rolled_back.wait(2.0))
        self.assertIn("wifi_rollback", core.reconnects)
        self.assertIn(
            ("request-0002", "rolled_back", "BackupNet", None),
            core.statuses,
        )

    def test_recover_expired_staged_transaction(self):
        core = FakeCore()
        rolled_back = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "request-0003.json")
            transaction = {
                "version": 1,
                "transaction_id": "request-0003",
                "ssid": "NewNet",
                "status": "staged",
                "rollback_deadline": time.time() - 1,
                "updated_at": time.time(),
            }
            with open(path, "w", encoding="utf-8") as file:
                json.dump(transaction, file)

            def rollback(value, **_kwargs):
                value["status"] = "rolled_back"
                rolled_back.set()
                return "rolled_back"

            manager = WiFiTransactionManager(
                core,
                transaction_dir=directory,
                stage_func=lambda *_args, **_kwargs: None,
                commit_func=lambda *_args, **_kwargs: "committed",
                rollback_func=rollback,
            )
            self.assertTrue(manager.recover())
            self.assertTrue(rolled_back.wait(2.0))
            self.assertIn("wifi_recovery_timeout", core.reconnects)
            self.assertEqual(core.active_wifi_request_id, "request-0003")

    def test_recover_staged_transaction_restores_id_and_accepts_commit(self):
        core = FakeCore()
        committed = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            now = time.time()
            path = os.path.join(directory, "request-0006.json")
            transaction = {
                "version": 1,
                "transaction_id": "request-0006",
                "ssid": "NewNet",
                "status": "staged",
                "created_at": now,
                "staged_at": now,
                "rollback_timeout_s": 90,
                "rollback_deadline": now + 90,
                "updated_at": now,
            }
            with open(path, "w", encoding="utf-8") as file:
                json.dump(transaction, file)

            def commit(value, **_kwargs):
                value["status"] = "committed"
                committed.set()
                return "committed"

            manager = WiFiTransactionManager(
                core,
                transaction_dir=directory,
                stage_func=lambda *_args, **_kwargs: None,
                commit_func=commit,
                rollback_func=lambda *_args, **_kwargs: "rolled_back",
            )
            self.assertTrue(manager.recover())
            self.assertEqual(core.active_wifi_request_id, "request-0006")
            self.assertTrue(
                wait_until(
                    lambda: any(status[1] == "awaiting_commit" for status in core.statuses)
                )
            )
            self.assertTrue(manager.handle_commit({"request_id": "request-0006"}))
            self.assertTrue(committed.wait(2.0))

    def test_recover_retries_rollback_failed_transaction(self):
        core = FakeCore()
        rolled_back = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "request-0007.json")
            transaction = {
                "version": 1,
                "transaction_id": "request-0007",
                "ssid": "NewNet",
                "status": "rollback_failed",
                "updated_at": time.time(),
            }
            with open(path, "w", encoding="utf-8") as file:
                json.dump(transaction, file)

            def rollback(value, **_kwargs):
                value["status"] = "rolled_back"
                rolled_back.set()
                return "rolled_back"

            manager = WiFiTransactionManager(
                core,
                transaction_dir=directory,
                stage_func=lambda *_args, **_kwargs: None,
                commit_func=lambda *_args, **_kwargs: "committed",
                rollback_func=rollback,
            )
            self.assertTrue(manager.recover())
            self.assertTrue(rolled_back.wait(2.0))
            self.assertEqual(core.active_wifi_request_id, "request-0007")
            self.assertIn("wifi_recovery_rollback", core.reconnects)

    def test_second_request_is_busy_while_first_is_staged(self):
        core = FakeCore()
        stage_started = threading.Event()

        def stage(ssid, _password, **kwargs):
            stage_started.set()
            return {
                "transaction_id": kwargs["transaction_id"],
                "ssid": ssid,
                "status": "staged",
                "rollback_deadline": time.time() + 30,
            }

        manager = WiFiTransactionManager(
            core,
            stage_func=stage,
            commit_func=lambda *_args, **_kwargs: "committed",
            rollback_func=lambda *_args, **_kwargs: "rolled_back",
        )
        self.assertTrue(
            manager.handle_request(
                {
                    "request_id": "request-0004",
                    "ssid": "FirstNet",
                    "password": "password123",
                }
            )
        )
        self.assertTrue(stage_started.wait(1.0))
        self.assertFalse(
            manager.handle_request(
                {
                    "request_id": "request-0005",
                    "ssid": "SecondNet",
                    "password": "password456",
                }
            )
        )
        manager.stop()


if __name__ == "__main__":
    unittest.main()
