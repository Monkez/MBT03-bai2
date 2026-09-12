import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from OrangePiZero2W import wifi_sync
from OrangePiZero2W.wifi_sync import (
    apply_wifi_credentials,
    commit_wifi_transaction,
    load_wifi_transaction,
    parse_wifi_command,
    parse_wifi_response,
    query_wifi_credentials,
    rollback_wifi_transaction,
    stage_wifi_credentials,
    synchronize_wifi,
    transaction_needs_rollback,
)
from server_client.protocol import Protocol


OLD_UUID = "11111111-1111-4111-8111-111111111111"
CANDIDATE_UUID = "22222222-2222-4222-8222-222222222222"
WIRED_UUID = "33333333-3333-4333-8333-333333333333"


def completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class FakeSerial:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.writes = []

    def reset_input_buffer(self):
        pass

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        pass

    def read(self, _size):
        return self.chunks.pop(0) if self.chunks else b""


class FakeNetworkManagerRunner:
    def __init__(self, active_ssid="Old-WiFi", ipv4=True):
        self.active_ssid = active_ssid
        self.ipv4 = ipv4
        self.active_uuid = OLD_UUID
        self.target_ssid = "MBT03-5G"
        self.activation_fails = False
        self.rollback_activation_fails = False
        self.delete_fails = set()
        self.malformed_wifi_uuid = False
        self.list_wifi_type = "wifi"
        self.calls = []
        self.profiles = {
            OLD_UUID: {
                "name": "old-profile",
                "type": "802-11-wireless",
                "interface": "wlan0",
                "ssid": active_ssid,
            },
            WIRED_UUID: {
                "name": "wired-profile",
                "type": "802-3-ethernet",
                "interface": "eth0",
                "ssid": None,
            },
        }

    def _profile(self, kind, identifier):
        if kind == "uuid":
            return self.profiles.get(identifier)
        for profile in self.profiles.values():
            if profile["name"] == identifier:
                return profile
        return None

    def _uuid_for(self, kind, identifier):
        if kind == "uuid":
            return identifier
        for profile_uuid, profile in self.profiles.items():
            if profile["name"] == identifier:
                return profile_uuid
        return None

    def __call__(self, args, timeout=30):
        del timeout
        args = list(args)
        self.calls.append(args)

        if args[:2] == ["iwgetid", "wlan0"]:
            return completed(args, stdout=(self.active_ssid + "\n") if self.active_ssid else "")
        if args[:4] == ["ip", "-4", "-o", "addr"]:
            stdout = "3: wlan0 inet 192.168.1.8/24 scope global wlan0\n" if self.ipv4 else ""
            return completed(args, stdout=stdout)
        if "GENERAL.NM-MANAGED" in args:
            return completed(args, stdout="yes\n")
        if "GENERAL.CONNECTION,GENERAL.CON-UUID" in args:
            profile = self.profiles.get(self.active_uuid)
            if profile is None:
                return completed(args, stdout="--\n\n")
            return completed(args, stdout=f"{profile['name']}\n{self.active_uuid}\n")
        if "connection.uuid,connection.type,connection.interface-name" in args:
            kind, identifier = args[-2:]
            profile_uuid = self._uuid_for(kind, identifier)
            profile = self._profile(kind, identifier)
            if profile is None or profile_uuid is None:
                return completed(args, returncode=10, stderr="unknown profile")
            return completed(
                args,
                stdout=f"{profile_uuid}\n{profile['type']}\n{profile['interface']}\n",
            )
        if args[:4] == ["nmcli", "connection", "add", "type"]:
            name = args[args.index("con-name") + 1]
            self.target_ssid = args[args.index("ssid") + 1]
            self.profiles[CANDIDATE_UUID] = {
                "name": name,
                "type": "802-11-wireless",
                "interface": "wlan0",
                "ssid": self.target_ssid,
            }
            return completed(args)
        if args[:3] == ["nmcli", "connection", "modify"]:
            return completed(args)
        if "connection" in args and "up" in args:
            profile_uuid = args[args.index("uuid") + 1]
            if profile_uuid == CANDIDATE_UUID and self.activation_fails:
                return completed(args, returncode=10, stderr="activation failed")
            if profile_uuid == OLD_UUID and self.rollback_activation_fails:
                return completed(args, returncode=10, stderr="rollback failed")
            profile = self.profiles.get(profile_uuid)
            if profile is None:
                return completed(args, returncode=10, stderr="unknown profile")
            self.active_uuid = profile_uuid
            self.active_ssid = profile["ssid"]
            self.ipv4 = True
            return completed(args)
        if "UUID,TYPE" in args:
            lines = []
            for profile_uuid, profile in self.profiles.items():
                profile_type = profile["type"]
                if profile_uuid == OLD_UUID and profile_type in {"wifi", "802-11-wireless"}:
                    profile_type = self.list_wifi_type
                lines.append(f"{profile_uuid}:{profile_type}")
            if self.malformed_wifi_uuid:
                lines.append("not-a-valid-uuid:wifi")
            return completed(args, stdout="\n".join(lines) + "\n")
        if args[:3] == ["nmcli", "connection", "delete"]:
            kind, identifier = args[-2:]
            profile_uuid = self._uuid_for(kind, identifier)
            if profile_uuid in self.delete_fails:
                return completed(args, returncode=10, stderr="delete failed")
            if profile_uuid is not None:
                self.profiles.pop(profile_uuid, None)
            return completed(args)
        return completed(args)


class FakeNetplanRunner:
    def __init__(self, old_ssid="Old-WiFi", target_ssid="MBT03-5G"):
        self.old_ssid = old_ssid
        self.target_ssid = target_ssid
        self.active_ssid = old_ssid
        self.ipv4 = True
        self.generate_count = 0
        self.apply_count = 0
        self.fail_generate = set()
        self.fail_apply = set()
        self.error_text = "netplan failed"
        self.calls = []

    def __call__(self, args, timeout=30):
        del timeout
        args = list(args)
        self.calls.append(args)
        if args[:2] == ["iwgetid", "wlan0"]:
            return completed(args, stdout=(self.active_ssid + "\n") if self.active_ssid else "")
        if args[:4] == ["ip", "-4", "-o", "addr"]:
            stdout = "3: wlan0 inet 192.168.1.8/24 scope global wlan0\n" if self.ipv4 else ""
            return completed(args, stdout=stdout)
        if "GENERAL.NM-MANAGED" in args:
            return completed(args, stdout="no\n")
        if args == ["netplan", "generate"]:
            self.generate_count += 1
            if self.generate_count in self.fail_generate:
                return completed(args, returncode=1, stderr=self.error_text)
            return completed(args)
        if args == ["netplan", "apply"]:
            self.apply_count += 1
            if self.apply_count in self.fail_apply:
                return completed(args, returncode=1, stderr=self.error_text)
            self.active_ssid = self.target_ssid if self.generate_count == 1 else self.old_ssid
            self.ipv4 = True
            return completed(args)
        return completed(args)


class WifiSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.netplan_dir = os.path.join(self.temporary.name, "netplan")
        self.transaction_dir = os.path.join(self.temporary.name, "transactions")
        os.makedirs(self.netplan_dir)
        self.managed_path = os.path.join(self.netplan_dir, "20-mbt03-uart-wifi.yaml")
        self.patchers = [
            patch.object(wifi_sync, "NETPLAN_CONFIG_DIR", self.netplan_dir),
            patch.object(wifi_sync, "NETPLAN_MANAGED_PATH", self.managed_path),
            patch.object(wifi_sync, "TRANSACTION_DIR", self.transaction_dir),
            patch.object(wifi_sync.os, "geteuid", return_value=0, create=True),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temporary.cleanup()

    def _write_old_netplan(self):
        path = os.path.join(self.netplan_dir, "01-base.yaml")
        document = {
            "network": {
                "version": 2,
                "ethernets": {"eth0": {"dhcp4": True}},
                "wifis": {
                    "wlan0": {
                        "dhcp4": True,
                        "access-points": {"Old-WiFi": {"password": "old-secret"}},
                    }
                },
            }
        }
        with open(path, "w", encoding="utf-8") as output:
            yaml.safe_dump(document, output, sort_keys=False)
        return path

    def test_parse_expected_response(self):
        self.assertEqual(
            parse_wifi_response("MBT03-5G#testpass123\r\n"),
            ("MBT03-5G", "testpass123"),
        )

    def test_parse_does_not_strip_password_spaces(self):
        self.assertEqual(
            parse_wifi_response("MBT03-5G# password123 \r\n"),
            ("MBT03-5G", " password123 "),
        )
        self.assertEqual(
            parse_wifi_command("Wifi#abc# password123 \n"),
            ("abc", " password123 "),
        )

    def test_parse_main_app_wifi_command(self):
        self.assertEqual(
            parse_wifi_command("Wifi#abc#password123\n"),
            ("abc", "password123"),
        )

    def test_wifi_command_password_is_redacted(self):
        safe_value = Protocol.redact_uart_command("Wifi#abc#password123\n")
        self.assertEqual(safe_value, "Wifi#abc#[REDACTED]")
        self.assertNotIn("password123", safe_value)

    def test_parse_rejects_short_password(self):
        with self.assertRaisesRegex(ValueError, "8 đến 63"):
            parse_wifi_response("MBT03-5G#short")

    def test_query_accepts_fragmented_uart_response(self):
        serial_port = FakeSerial([b"MBT03-", b"5G#testpass123\r\n"])
        logs = []
        credentials = query_wifi_credentials(serial_port, attempts=1, log=logs.append)
        self.assertEqual(credentials, ("MBT03-5G", "testpass123"))
        self.assertEqual(serial_port.writes, [b"0W000\n"])
        self.assertIn("UART RX bytes: b'MBT03-'", logs)
        self.assertIn("UART RX bytes: b'5G#testpass123\\r\\n'", logs)
        self.assertIn(
            "Đã nhận cấu hình Wi-Fi qua UART: SSID='MBT03-5G', password='testpass123'",
            logs,
        )

    def test_query_ignores_boot_log_and_invalid_hash_line_until_deadline(self):
        serial_port = FakeSerial([
            b"U-Boot 2024.01 starting\r\n",
            b"debug#bad\n",
            b"sensor ready\nMBT03-",
            b"5G#testpass123\r\n",
        ])
        credentials = query_wifi_credentials(serial_port, attempts=1, log=lambda _msg: None)
        self.assertEqual(credentials, ("MBT03-5G", "testpass123"))

    def test_same_ssid_with_ipv4_is_already_connected(self):
        serial_port = FakeSerial([b"MBT03-5G#testpass123\n"])
        runner = FakeNetworkManagerRunner(active_ssid="MBT03-5G", ipv4=True)
        status = synchronize_wifi(serial_port, runner=runner, log=lambda _msg: None)
        self.assertEqual(status, "already_connected")
        self.assertFalse(any("connection" in call and "add" in call for call in runner.calls))

    def test_same_ssid_without_ipv4_is_not_already_connected(self):
        runner = FakeNetworkManagerRunner(active_ssid="MBT03-5G", ipv4=False)
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="same-no-ip",
            runner=runner, log=lambda _msg: None,
        )
        self.assertEqual(transaction["status"], "staged")
        self.assertTrue(any("connection" in call and "add" in call for call in runner.calls))

    def test_network_manager_detection_error_does_not_fall_through_to_netplan(self):
        calls = []

        def runner(args, timeout=30):
            del timeout
            args = list(args)
            calls.append(args)
            if args[:2] == ["iwgetid", "wlan0"]:
                return completed(args, stdout="Old-WiFi\n")
            if args[:3] == ["systemctl", "is-active", "NetworkManager.service"]:
                return completed(args, stdout="active\n")
            if args and args[0] == "nmcli":
                return completed(args, returncode=10, stderr="temporary failure")
            return completed(args)

        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="nm-detect-fail",
            runner=runner, log=lambda _msg: None,
        )
        self.assertEqual(transaction["status"], "failed")
        self.assertFalse(any(call and call[0] == "netplan" for call in calls))

    def test_network_manager_immediate_apply_deletes_only_old_wifi(self):
        runner = FakeNetworkManagerRunner()
        status = apply_wifi_credentials("MBT03-5G", "testpass123", runner=runner, log=lambda _msg: None)
        self.assertEqual(status, "changed")
        self.assertNotIn(OLD_UUID, runner.profiles)
        self.assertIn(WIRED_UUID, runner.profiles)
        self.assertIn(CANDIDATE_UUID, runner.profiles)

    def test_network_manager_activation_failure_restores_old_and_deletes_candidate(self):
        runner = FakeNetworkManagerRunner()
        runner.activation_fails = True
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="activation-fail",
            runner=runner, log=lambda _msg: None,
        )
        self.assertEqual(transaction["status"], "failed")
        self.assertEqual(runner.active_uuid, OLD_UUID)
        self.assertNotIn(CANDIDATE_UUID, runner.profiles)
        self.assertTrue(any("up" in call and OLD_UUID in call for call in runner.calls))

    def test_network_manager_activation_failure_reports_rollback_failure(self):
        runner = FakeNetworkManagerRunner()
        runner.activation_fails = True
        runner.rollback_activation_fails = True
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="rollback-fail",
            runner=runner, log=lambda _msg: None,
        )
        self.assertEqual(transaction["status"], "rollback_failed")
        self.assertIn(
            CANDIDATE_UUID,
            runner.profiles,
            "candidate must remain when the previous network cannot be verified",
        )

    def test_network_manager_commit_accepts_type_wifi(self):
        runner = FakeNetworkManagerRunner()
        runner.list_wifi_type = "wifi"
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="type-wifi",
            runner=runner, log=lambda _msg: None,
        )
        self.assertIn(OLD_UUID, runner.profiles, "stage must preserve the old profile")
        result = commit_wifi_transaction(transaction, runner=runner, log=lambda _msg: None)
        self.assertEqual(result, "committed")
        self.assertNotIn(OLD_UUID, runner.profiles)

    def test_network_manager_invalid_wifi_uuid_aborts_commit_without_deleting(self):
        runner = FakeNetworkManagerRunner()
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="bad-uuid",
            runner=runner, log=lambda _msg: None,
        )
        runner.malformed_wifi_uuid = True
        result = commit_wifi_transaction(transaction, runner=runner, log=lambda _msg: None)
        self.assertEqual(result, "commit_failed")
        self.assertIn(OLD_UUID, runner.profiles)

    def test_network_manager_explicit_rollback_reactivates_old_profile(self):
        runner = FakeNetworkManagerRunner()
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="explicit-rollback",
            runner=runner, log=lambda _msg: None,
        )
        self.assertEqual(runner.active_uuid, CANDIDATE_UUID)
        result = rollback_wifi_transaction(transaction, runner=runner, log=lambda _msg: None)
        self.assertEqual(result, "rolled_back")
        self.assertEqual(runner.active_uuid, OLD_UUID)
        self.assertNotIn(CANDIDATE_UUID, runner.profiles)

    def test_network_manager_failed_explicit_rollback_keeps_active_candidate(self):
        runner = FakeNetworkManagerRunner()
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="keep-candidate",
            runner=runner, log=lambda _msg: None,
        )
        runner.rollback_activation_fails = True
        result = rollback_wifi_transaction(
            transaction, runner=runner, log=lambda _msg: None
        )
        self.assertEqual(result, "rollback_failed")
        self.assertEqual(runner.active_uuid, CANDIDATE_UUID)
        self.assertIn(CANDIDATE_UUID, runner.profiles)

    def test_network_manager_commit_requires_candidate_to_be_active(self):
        runner = FakeNetworkManagerRunner()
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="active-candidate",
            runner=runner, log=lambda _msg: None,
        )
        runner.profiles[OLD_UUID]["ssid"] = "MBT03-5G"
        runner.active_uuid = OLD_UUID
        runner.active_ssid = "MBT03-5G"
        result = commit_wifi_transaction(
            transaction, runner=runner, log=lambda _msg: None
        )
        self.assertEqual(result, "commit_failed")
        self.assertIn(OLD_UUID, runner.profiles)
        self.assertIn(CANDIDATE_UUID, runner.profiles)

    def test_commit_metadata_failure_does_not_trigger_destructive_rollback(self):
        runner = FakeNetworkManagerRunner()
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="commit-disk-fail",
            runner=runner, log=lambda _msg: None,
        )
        real_save = wifi_sync.save_wifi_transaction

        def fail_terminal_save(value, *args, **kwargs):
            if value.get("status") == "committed":
                raise OSError("disk full")
            return real_save(value, *args, **kwargs)

        with patch.object(
            wifi_sync, "save_wifi_transaction", side_effect=fail_terminal_save
        ):
            result = commit_wifi_transaction(
                transaction, runner=runner, log=lambda _msg: None
            )

        self.assertEqual(result, "committed")
        self.assertNotIn(OLD_UUID, runner.profiles)
        self.assertIn(CANDIDATE_UUID, runner.profiles)
        durable = load_wifi_transaction("commit-disk-fail")
        self.assertEqual(durable["status"], "committing")

    def test_transaction_is_password_free_persistent_and_expirable(self):
        runner = FakeNetworkManagerRunner()
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="persist-me",
            rollback_timeout=15, runner=runner, log=lambda _msg: None,
        )
        serialized = json.dumps(transaction)
        self.assertNotIn("testpass123", serialized)
        self.assertIn("staged_at", transaction)
        self.assertAlmostEqual(
            transaction["rollback_deadline"] - transaction["staged_at"],
            15.0,
            places=3,
        )
        loaded = load_wifi_transaction("persist-me")
        self.assertEqual(loaded["transaction_id"], "persist-me")
        self.assertFalse(transaction_needs_rollback(loaded, now=loaded["rollback_deadline"] - 1))
        self.assertTrue(transaction_needs_rollback(loaded, now=loaded["rollback_deadline"]))
        with open(loaded["state_path"], encoding="utf-8") as source:
            self.assertNotIn("testpass123", source.read())

    def test_netplan_stage_preserves_root_only_snapshot_until_commit(self):
        old_path = self._write_old_netplan()
        runner = FakeNetplanRunner()
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="netplan-stage",
            runner=runner, log=lambda _msg: None,
        )
        marker_add = [
            "install", "-m", "600", "/dev/null", wifi_sync.WIFI_CHANGE_MARKER
        ]
        marker_remove = ["rm", "-f", "--", wifi_sync.WIFI_CHANGE_MARKER]
        self.assertIn(marker_add, runner.calls)
        self.assertIn(marker_remove, runner.calls)
        self.assertLess(runner.calls.index(marker_add), runner.calls.index(["netplan", "apply"]))
        self.assertGreater(runner.calls.index(marker_remove), runner.calls.index(["netplan", "apply"]))
        self.assertEqual(transaction["status"], "staged")
        self.assertTrue(os.path.exists(transaction["snapshot_path"]))
        with open(old_path, encoding="utf-8") as source:
            base = yaml.safe_load(source)
        self.assertNotIn("wifis", base["network"])
        with open(self.managed_path, encoding="utf-8") as source:
            managed = yaml.safe_load(source)
        self.assertEqual(
            managed["network"]["wifis"]["wlan0"]["access-points"]["MBT03-5G"]["auth"]["password"],
            "testpass123",
        )
        result = commit_wifi_transaction(transaction, runner=runner, log=lambda _msg: None)
        self.assertEqual(result, "committed")
        self.assertFalse(os.path.exists(transaction.get("snapshot_path", "")))

    def test_netplan_apply_failure_restores_original_configuration(self):
        old_path = self._write_old_netplan()
        with open(old_path, "rb") as source:
            original = source.read()
        runner = FakeNetplanRunner()
        runner.fail_apply.add(1)
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="apply-fail",
            runner=runner, log=lambda _msg: None,
        )
        self.assertEqual(transaction["status"], "failed")
        with open(old_path, "rb") as source:
            self.assertEqual(source.read(), original)
        self.assertFalse(os.path.exists(self.managed_path))

    def test_netplan_rollback_failure_is_reported_and_snapshot_retained(self):
        self._write_old_netplan()
        runner = FakeNetplanRunner()
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="rollback-apply-fail",
            runner=runner, log=lambda _msg: None,
        )
        snapshot_path = transaction["snapshot_path"]
        runner.fail_apply.add(2)
        result = rollback_wifi_transaction(transaction, runner=runner, log=lambda _msg: None)
        self.assertEqual(result, "rollback_failed")
        self.assertEqual(transaction["status"], "rollback_failed")
        self.assertTrue(os.path.exists(snapshot_path))

    def test_netplan_error_never_logs_or_persists_new_password(self):
        self._write_old_netplan()
        runner = FakeNetplanRunner()
        runner.fail_generate.add(1)
        runner.error_text = "invalid secret testpass123"
        logs = []
        transaction = stage_wifi_credentials(
            "MBT03-5G", "testpass123", transaction_id="secret-error",
            runner=runner, log=logs.append,
        )
        self.assertEqual(transaction["status"], "failed")
        self.assertNotIn("testpass123", "\n".join(logs))
        with open(transaction["state_path"], encoding="utf-8") as source:
            self.assertNotIn("testpass123", source.read())


if __name__ == "__main__":
    unittest.main()
