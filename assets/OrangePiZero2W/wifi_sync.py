# -*- coding: utf-8 -*-
"""Synchronize and transactionally update Orange Pi Wi-Fi credentials.

The staged API deliberately keeps the previous configuration recoverable until
the remote application confirms that it can reach the board on the new Wi-Fi.
Transaction dictionaries contain no password and can be serialized as JSON.
"""

import base64
import glob
import json
import os
import re
import stat
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager

import yaml


UART_WIFI_QUERY = "0W000"
WIFI_INTERFACE = "wlan0"
MANAGED_CONNECTION_NAME = "mbt03-uart-wifi"
NETPLAN_CONFIG_DIR = "/etc/netplan"
NETPLAN_MANAGED_PATH = "/etc/netplan/20-mbt03-uart-wifi.yaml"
TRANSACTION_DIR = "/var/lib/mbt03/wifi-transactions"
TRANSACTION_VERSION = 1
DEFAULT_ROLLBACK_TIMEOUT = 90
WIFI_CHANGE_MARKER = "/run/mbt03-wifi-change"

_WIFI_CONNECTION_TYPES = {"802-11-wireless", "wifi"}
_TRANSACTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _default_log(message):
    print(f"[WiFi Sync] {message}")


def _redact_secret(value, secret):
    text = str(value or "").strip()
    return text.replace(secret, "[REDACTED]") if secret else text


def _run_command(args, timeout=30):
    try:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


@contextmanager
def _wifi_change_guard(runner, log):
    """Prevent the board watchdog from resetting wlan0 during a transaction."""
    marker = runner(
        ["install", "-m", "600", "/dev/null", WIFI_CHANGE_MARKER], timeout=5
    )
    guarded = marker.returncode == 0
    if not guarded:
        log("Cảnh báo: không tạo được khóa tạm dừng Wi-Fi watchdog")
    else:
        # Cancel a watchdog invocation that was already queued or running when
        # the marker was created. Future timer invocations are blocked by the
        # systemd ConditionPathExists drop-in installed during deployment.
        runner(["systemctl", "stop", "wifi-watchdog.service"], timeout=10)
    try:
        yield
    finally:
        if guarded:
            removed = runner(["rm", "-f", "--", WIFI_CHANGE_MARKER], timeout=5)
            if removed.returncode != 0:
                log("Cảnh báo: không xóa được khóa tạm dừng Wi-Fi watchdog")


def _remove_line_framing(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", "strict")
    if not isinstance(value, str):
        value = str(value)
    # Remove UART/message framing only. Spaces are valid WPA passphrase bytes.
    return value.strip("\x00").rstrip("\r\n")


def parse_wifi_response(value):
    """Parse ``SSID#password`` without stripping valid password spaces."""
    value = _remove_line_framing(value)
    if "#" not in value:
        raise ValueError("phản hồi không có dấu phân cách #")

    ssid, password = value.split("#", 1)
    ssid = ssid.strip()
    if not ssid:
        raise ValueError("SSID rỗng")
    if len(ssid.encode("utf-8")) > 32:
        raise ValueError("SSID dài quá 32 byte")
    if "#" in ssid or any(ord(char) < 32 for char in ssid):
        raise ValueError("SSID chứa ký tự không hợp lệ")
    if not 8 <= len(password) <= 63:
        raise ValueError("mật khẩu Wi-Fi phải dài từ 8 đến 63 ký tự")
    if any(ord(char) < 32 for char in password):
        raise ValueError("mật khẩu Wi-Fi chứa ký tự điều khiển")
    return ssid, password


def parse_wifi_command(command):
    """Parse a main-app command in the form ``Wifi#SSID#password``."""
    text = _remove_line_framing(command)
    if not text.lower().startswith("wifi#"):
        raise ValueError("không phải lệnh cấu hình Wi-Fi")
    parts = text.split("#", 2)
    if len(parts) != 3:
        raise ValueError("lệnh Wi-Fi phải có dạng Wifi#SSID#MAT_KHAU")
    return parse_wifi_response(f"{parts[1]}#{parts[2]}")


def query_wifi_credentials(
    serial_port,
    attempts=5,
    response_timeout=2.0,
    retry_delay=0.4,
    log=_default_log,
):
    """Ask the external board for credentials, ignoring boot/noise lines.

    Invalid complete lines no longer end an attempt. The reader keeps looking
    until the attempt deadline, so MCU boot logs may precede the response.
    Raw UART data, including the Wi-Fi password, is intentionally logged to
    support field diagnostics.
    """

    def parse_candidate(candidate):
        if candidate:
            log(f"UART RX frame: {candidate!r}")
        if not candidate or candidate == UART_WIFI_QUERY or b"#" not in candidate:
            return None
        try:
            credentials = parse_wifi_response(candidate)
            log(
                "Đã nhận cấu hình Wi-Fi qua UART: "
                f"SSID={credentials[0]!r}, password={credentials[1]!r}"
            )
            return credentials
        except (UnicodeDecodeError, ValueError) as exc:
            log(f"Bỏ qua phản hồi UART không hợp lệ: {exc}")
            return None

    for attempt in range(1, attempts + 1):
        try:
            serial_port.reset_input_buffer()
        except Exception:
            pass

        try:
            serial_port.write((UART_WIFI_QUERY + "\n").encode("ascii"))
            serial_port.flush()
            log(f"Đã gửi {UART_WIFI_QUERY}, lần {attempt}/{attempts}")
        except Exception as exc:
            log(f"Không gửi được lệnh hỏi Wi-Fi: {exc}")
            return None

        deadline = time.monotonic() + response_timeout
        buffer = bytearray()
        last_data_at = None
        while time.monotonic() < deadline:
            try:
                chunk = serial_port.read(64)
            except Exception as exc:
                log(f"Lỗi đọc phản hồi Wi-Fi từ UART: {exc}")
                break

            if chunk:
                log(f"UART RX bytes: {bytes(chunk)!r}")
                buffer.extend(chunk)
                last_data_at = time.monotonic()
                if len(buffer) > 4096:
                    # Preserve the newest partial data without unbounded growth.
                    buffer = buffer[-2048:]

                while True:
                    delimiters = [index for index in (buffer.find(b"\n"), buffer.find(b"\r")) if index >= 0]
                    if not delimiters:
                        break
                    end = min(delimiters)
                    candidate = bytes(buffer[:end]).strip(b"\x00")
                    consume = end + 1
                    while consume < len(buffer) and buffer[consume] in (10, 13):
                        consume += 1
                    del buffer[:consume]
                    credentials = parse_candidate(candidate)
                    if credentials is not None:
                        return credentials
                continue

            if (
                buffer
                and last_data_at is not None
                and time.monotonic() - last_data_at >= 0.2
            ):
                candidate = bytes(buffer).strip(b"\x00")
                buffer.clear()
                credentials = parse_candidate(candidate)
                if credentials is not None:
                    return credentials
            time.sleep(0.01)

        # Accept an unterminated response that arrived immediately before the
        # deadline. Invalid data is discarded and the next attempt may proceed.
        credentials = parse_candidate(bytes(buffer).strip(b"\x00"))
        if credentials is not None:
            return credentials
        if attempt < attempts:
            time.sleep(retry_delay)

    log("Không nhận được cấu hình Wi-Fi hợp lệ; giữ nguyên mạng hiện tại")
    return None


def get_current_ssid(interface=WIFI_INTERFACE, runner=_run_command):
    result = runner(["iwgetid", interface, "--raw"], timeout=5)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    result = runner(["iw", "dev", interface, "link"], timeout=5)
    if result.returncode == 0:
        match = re.search(r"^\s*SSID:\s*(.+?)\s*$", result.stdout, re.MULTILINE)
        if match:
            return match.group(1)
    return None


def _has_ipv4(interface=WIFI_INTERFACE, runner=_run_command):
    result = runner(
        ["ip", "-4", "-o", "addr", "show", "dev", interface, "scope", "global"],
        timeout=5,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _wait_for_wifi(ssid, timeout=30, interface=WIFI_INTERFACE, runner=_run_command):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (
            get_current_ssid(interface=interface, runner=runner) == ssid
            and _has_ipv4(interface=interface, runner=runner)
        ):
            return True
        time.sleep(0.5)
    return False


def _network_manager_controls_wifi(runner=_run_command):
    managed_result = runner(
        ["nmcli", "--terse", "--get-values", "GENERAL.NM-MANAGED", "device", "show", WIFI_INTERFACE],
        timeout=5,
    )
    if managed_result.returncode == 0:
        value = managed_result.stdout.strip().lower()
        if value in {"yes", "true", "1"}:
            return True
        if value in {"no", "false", "0"}:
            return False

    state_result = runner(
        ["nmcli", "--terse", "--get-values", "GENERAL.STATE", "device", "show", WIFI_INTERFACE],
        timeout=5,
    )
    if state_result.returncode == 0:
        match = re.match(r"\s*(\d+)", state_result.stdout)
        if match is not None:
            return int(match.group(1)) != 10

    # Absence of nmcli means this image uses Netplan/networkd. A transient
    # nmcli failure while NetworkManager is active is different: fail closed
    # instead of letting two network backends compete for wlan0.
    if managed_result.returncode == 127 and state_result.returncode == 127:
        return False
    service = runner(
        ["systemctl", "is-active", "NetworkManager.service"], timeout=5
    )
    if service.returncode == 0 and service.stdout.strip() == "active":
        raise RuntimeError("Không xác định được trạng thái quản lý wlan0 của NetworkManager")
    return False


def _valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _validate_transaction_id(transaction_id):
    value = str(transaction_id or uuid.uuid4().hex)
    if not _TRANSACTION_ID_RE.fullmatch(value):
        raise ValueError("transaction_id không hợp lệ")
    return value


def _ensure_private_directory(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def _atomic_write(path, content, mode=0o600):
    directory = os.path.dirname(path) or "."
    if not os.path.isdir(directory):
        os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".mbt03-wifi-", dir=directory)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        else:
            os.chmod(temporary_path, mode)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        descriptor = None
        os.replace(temporary_path, path)
        os.chmod(path, mode)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
        except OSError:
            pass


def save_wifi_transaction(transaction, path=None):
    """Persist a password-free transaction atomically with root-only access."""
    transaction_id = _validate_transaction_id(transaction.get("transaction_id"))
    state_path = path or transaction.get("state_path") or os.path.join(
        TRANSACTION_DIR, f"{transaction_id}.json"
    )
    transaction["state_path"] = state_path
    transaction["updated_at"] = time.time()
    payload = json.dumps(transaction, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    _ensure_private_directory(os.path.dirname(state_path) or ".")
    _atomic_write(state_path, payload, 0o600)
    return state_path


def load_wifi_transaction(transaction_id_or_path):
    """Load a previously persisted transaction by ID or explicit state path."""
    value = os.fspath(transaction_id_or_path)
    if os.path.dirname(value):
        state_path = value
    else:
        transaction_id = _validate_transaction_id(value)
        state_path = os.path.join(TRANSACTION_DIR, f"{transaction_id}.json")
    with open(state_path, "rb") as source:
        transaction = json.loads(source.read().decode("utf-8"))
    if transaction.get("version") != TRANSACTION_VERSION:
        raise ValueError("phiên bản giao dịch Wi-Fi không được hỗ trợ")
    _validate_transaction_id(transaction.get("transaction_id"))
    transaction["state_path"] = state_path
    return transaction


def transaction_needs_rollback(transaction, now=None):
    """Return True when a staged transaction passed its confirmation deadline."""
    if transaction.get("status") != "staged":
        return False
    current_time = float(now if now is not None else time.time())
    deadline = transaction.get("rollback_deadline")
    if deadline is None:
        return True
    deadline = float(deadline)
    created_at = float(transaction.get("created_at", current_time))
    timeout = max(1.0, float(transaction.get("rollback_timeout_s", 90.0)))
    # A board without a backed RTC can jump backwards across a reboot. Never
    # interpret that as a multi-year confirmation window.
    clock_moved_backwards = current_time < created_at - 5.0
    impossible_remaining_window = deadline - current_time > timeout + 5.0
    return (
        current_time >= deadline
        or clock_moved_backwards
        or impossible_remaining_window
    )


def _existing_transaction(transaction_id, ssid):
    if transaction_id is None:
        return None
    transaction_id = _validate_transaction_id(transaction_id)
    state_path = os.path.join(TRANSACTION_DIR, f"{transaction_id}.json")
    if not os.path.exists(state_path):
        return None
    transaction = load_wifi_transaction(state_path)
    if transaction.get("ssid") != ssid:
        raise ValueError("transaction_id đã được dùng cho một SSID khác")
    return transaction


def _new_transaction(ssid, transaction_id=None, rollback_timeout=DEFAULT_ROLLBACK_TIMEOUT):
    transaction_id = _validate_transaction_id(transaction_id)
    now = time.time()
    timeout = max(1.0, float(rollback_timeout))
    return {
        "version": TRANSACTION_VERSION,
        "transaction_id": transaction_id,
        "status": "preparing",
        "backend": None,
        "ssid": ssid,
        "previous_ssid": None,
        "created_at": now,
        "updated_at": now,
        "rollback_timeout_s": timeout,
        # Start the confirmation window only after the candidate has an IPv4.
        # A slow association/DHCP attempt must not consume this window.
        "rollback_deadline": None,
        "state_path": os.path.join(TRANSACTION_DIR, f"{transaction_id}.json"),
    }


def _set_status(transaction, status, log=_default_log, error=None):
    transaction["status"] = status
    if error:
        transaction["error"] = str(error)
    else:
        transaction.pop("error", None)
    try:
        save_wifi_transaction(transaction)
    except Exception as exc:
        log(f"Không lưu được trạng thái giao dịch Wi-Fi: {exc}")
        return False
    return True


def _nm_profile_details(kind, identifier, runner):
    result = runner(
        [
            "nmcli", "--get-values",
            "connection.uuid,connection.type,connection.interface-name",
            "connection", "show", kind, identifier,
        ],
        timeout=5,
    )
    if result.returncode != 0:
        return None
    values = result.stdout.splitlines()
    while len(values) < 3:
        values.append("")
    profile_uuid, profile_type, interface = (value.strip() for value in values[:3])
    if not _valid_uuid(profile_uuid):
        return None
    return {
        "uuid": profile_uuid,
        "type": profile_type,
        "interface": interface,
    }


def _nm_active_profile(runner):
    result = runner(
        [
            "nmcli", "--get-values", "GENERAL.CONNECTION,GENERAL.CON-UUID",
            "device", "show", WIFI_INTERFACE,
        ],
        timeout=5,
    )
    if result.returncode != 0:
        return None
    values = result.stdout.splitlines()
    while len(values) < 2:
        values.append("")
    name, profile_uuid = (value.strip() for value in values[:2])
    if not name or name == "--" or not profile_uuid:
        return None
    if not _valid_uuid(profile_uuid):
        raise ValueError("UUID profile NetworkManager đang chạy không hợp lệ")
    details = _nm_profile_details("uuid", profile_uuid, runner)
    if details is None:
        raise ValueError("không đọc được profile NetworkManager đang chạy")
    if details["type"] not in _WIFI_CONNECTION_TYPES:
        raise ValueError("profile đang chạy không phải Wi-Fi")
    if details["interface"] not in {"", WIFI_INTERFACE}:
        raise ValueError("profile đang chạy thuộc interface khác")
    details["name"] = name
    return details


def _nm_delete_candidate(candidate, runner, log):
    identifier = candidate.get("uuid")
    kind = "uuid" if _valid_uuid(identifier) else "id"
    identifier = identifier if kind == "uuid" else candidate.get("name")
    if not identifier:
        return True
    result = runner(["nmcli", "connection", "delete", kind, identifier], timeout=10)
    if result.returncode != 0:
        log(f"Không xóa được profile Wi-Fi ứng viên: {result.stderr.strip()}")
        return False
    return True


def _nm_reactivate_previous(transaction, runner, log):
    previous = transaction.get("previous")
    if not previous:
        return True
    profile_uuid = previous.get("uuid")
    if not _valid_uuid(profile_uuid):
        log("Không thể khôi phục: UUID profile Wi-Fi cũ không hợp lệ")
        return False
    details = _nm_profile_details("uuid", profile_uuid, runner)
    if (
        details is None
        or details["type"] not in _WIFI_CONNECTION_TYPES
        or details["interface"] not in {"", WIFI_INTERFACE}
    ):
        log("Không thể khôi phục: profile Wi-Fi cũ không còn hợp lệ")
        return False
    result = runner(
        ["nmcli", "--wait", "25", "connection", "up", "uuid", profile_uuid, "ifname", WIFI_INTERFACE],
        timeout=30,
    )
    if result.returncode != 0:
        log(f"Không kích hoạt lại được profile Wi-Fi cũ: {result.stderr.strip()}")
        return False
    previous_ssid = transaction.get("previous_ssid")
    if previous_ssid and not _wait_for_wifi(previous_ssid, runner=runner):
        log("Profile Wi-Fi cũ đã kích hoạt nhưng chưa có IPv4")
        return False
    return True


def _rollback_failed_nm_stage(transaction, runner, log):
    restored = _nm_reactivate_previous(transaction, runner, log)
    # Candidate cleanup is safe only after the previous Wi-Fi and its IPv4
    # have been positively restored. Otherwise keep the remaining recovery
    # path alive and report rollback_failed.
    removed = (
        _nm_delete_candidate(transaction.get("candidate", {}), runner, log)
        if restored else False
    )
    return restored and removed


def _stage_network_manager(transaction, password, runner, log):
    try:
        previous = _nm_active_profile(runner)
    except ValueError as exc:
        log(str(exc))
        transaction["error"] = str(exc)
        return "failed"

    transaction["previous"] = previous
    candidate_name = f"{MANAGED_CONNECTION_NAME}-{transaction['transaction_id'][:12]}"
    transaction["candidate"] = {"name": candidate_name}
    save_wifi_transaction(transaction)

    result = runner(
        [
            "nmcli", "connection", "add", "type", "wifi",
            "ifname", WIFI_INTERFACE, "con-name", candidate_name,
            "ssid", transaction["ssid"],
        ],
        timeout=10,
    )
    if result.returncode != 0:
        log(f"Không tạo được profile Wi-Fi ứng viên: {result.stderr.strip()}")
        return "failed"

    details = _nm_profile_details("id", candidate_name, runner)
    if (
        details is None
        or details["type"] not in _WIFI_CONNECTION_TYPES
        or details["interface"] != WIFI_INTERFACE
    ):
        log("Profile Wi-Fi ứng viên có UUID/type/interface không hợp lệ")
        return "failed" if _nm_delete_candidate(transaction["candidate"], runner, log) else "rollback_failed"
    transaction["candidate"].update(details)
    save_wifi_transaction(transaction)

    # nmcli has no portable secret-stdin option for connection modify. The
    # secret is therefore present briefly in argv, but is never persisted in
    # transaction state or copied into logs; stderr is always redacted.
    result = runner(
        [
            "nmcli", "connection", "modify", "uuid", details["uuid"],
            "connection.interface-name", WIFI_INTERFACE,
            "connection.autoconnect", "yes",
            "connection.autoconnect-priority", "999",
            "802-11-wireless.ssid", transaction["ssid"],
            "802-11-wireless.mode", "infrastructure",
            "802-11-wireless-security.key-mgmt", "wpa-psk",
            "802-11-wireless-security.psk", password,
            "ipv4.method", "auto", "ipv6.method", "auto",
        ],
        timeout=10,
    )
    if result.returncode != 0:
        detail = _redact_secret(result.stderr, password)
        log(f"Không cấu hình được profile Wi-Fi ứng viên: {detail}")
        return "failed" if _rollback_failed_nm_stage(transaction, runner, log) else "rollback_failed"

    result = runner(
        [
            "nmcli", "--wait", "25", "connection", "up",
            "uuid", details["uuid"], "ifname", WIFI_INTERFACE,
        ],
        timeout=30,
    )
    if result.returncode != 0 or not _wait_for_wifi(transaction["ssid"], runner=runner):
        log("Không kết nối được Wi-Fi ứng viên; đang khôi phục profile cũ")
        return "failed" if _rollback_failed_nm_stage(transaction, runner, log) else "rollback_failed"
    return "staged"


def _netplan_paths():
    return sorted(set(
        glob.glob(os.path.join(NETPLAN_CONFIG_DIR, "*.yaml"))
        + glob.glob(os.path.join(NETPLAN_CONFIG_DIR, "*.yml"))
    ))


def _snapshot_netplan(transaction):
    files = []
    for path in _netplan_paths():
        with open(path, "rb") as source:
            content = source.read()
        files.append({
            "path": path,
            "mode": stat.S_IMODE(os.stat(path).st_mode),
            "content_b64": base64.b64encode(content).decode("ascii"),
        })
    snapshot_path = os.path.join(
        TRANSACTION_DIR, f"{transaction['transaction_id']}.netplan-snapshot.json"
    )
    snapshot = {"version": 1, "files": files}
    _ensure_private_directory(os.path.dirname(snapshot_path) or ".")
    _atomic_write(
        snapshot_path,
        json.dumps(snapshot, sort_keys=True, indent=2).encode("utf-8"),
        0o600,
    )
    transaction["snapshot_path"] = snapshot_path
    transaction["netplan_original_paths"] = [item["path"] for item in files]
    save_wifi_transaction(transaction)


def _load_netplan_snapshot(transaction):
    with open(transaction["snapshot_path"], "rb") as source:
        snapshot = json.loads(source.read().decode("utf-8"))
    if snapshot.get("version") != 1 or not isinstance(snapshot.get("files"), list):
        raise ValueError("snapshot Netplan không hợp lệ")
    return snapshot


def _restore_netplan_transaction(transaction, runner, log):
    try:
        snapshot = _load_netplan_snapshot(transaction)
        originals = {item["path"] for item in snapshot["files"]}
        if NETPLAN_MANAGED_PATH not in originals and os.path.exists(NETPLAN_MANAGED_PATH):
            os.unlink(NETPLAN_MANAGED_PATH)
        for item in snapshot["files"]:
            content = base64.b64decode(item["content_b64"], validate=True)
            _atomic_write(item["path"], content, int(item.get("mode", 0o600)))

        generated = runner(["netplan", "generate"], timeout=20)
        if generated.returncode != 0:
            raise RuntimeError(generated.stderr.strip() or "netplan generate rollback thất bại")
        applied = runner(["netplan", "apply"], timeout=35)
        if applied.returncode != 0:
            raise RuntimeError(applied.stderr.strip() or "netplan apply rollback thất bại")
        previous_ssid = transaction.get("previous_ssid")
        if previous_ssid and not _wait_for_wifi(previous_ssid, runner=runner):
            raise RuntimeError("Wi-Fi cũ chưa hoạt động hoặc chưa có IPv4 sau rollback")
        log("Đã khôi phục và kiểm tra cấu hình Netplan trước đó")
        return True
    except Exception as exc:
        log(f"Khôi phục Netplan thất bại: {exc}")
        return False


def _remove_wifi_from_document(document):
    if not isinstance(document, dict):
        return document, False
    network = document.get("network")
    if not isinstance(network, dict) or "wifis" not in network:
        return document, False
    network.pop("wifis", None)
    return document, True


def _stage_netplan(transaction, password, runner, log):
    try:
        _snapshot_netplan(transaction)
        original_paths = list(transaction.get("netplan_original_paths", []))
        for path in original_paths:
            with open(path, "rb") as source:
                raw = source.read()
            document = yaml.safe_load(raw.decode("utf-8"))
            document, changed = _remove_wifi_from_document(document)
            if changed:
                rendered = yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode("utf-8")
                original_mode = stat.S_IMODE(os.stat(path).st_mode)
                _atomic_write(path, rendered, original_mode)

        wifi_document = {
            "network": {
                "version": 2,
                "wifis": {
                    WIFI_INTERFACE: {
                        "dhcp4": True,
                        "dhcp6": True,
                        "access-points": {
                            transaction["ssid"]: {
                                "auth": {
                                    "key-management": "psk",
                                    "password": password,
                                }
                            }
                        },
                    }
                },
            }
        }
        rendered = yaml.safe_dump(wifi_document, allow_unicode=True, sort_keys=False).encode("utf-8")
        _atomic_write(NETPLAN_MANAGED_PATH, rendered, 0o600)

        generated = runner(["netplan", "generate"], timeout=20)
        if generated.returncode != 0:
            raise RuntimeError(_redact_secret(generated.stderr, password) or "netplan generate thất bại")
        applied = runner(["netplan", "apply"], timeout=35)
        if applied.returncode != 0:
            raise RuntimeError(_redact_secret(applied.stderr, password) or "netplan apply thất bại")
        if not _wait_for_wifi(transaction["ssid"], runner=runner):
            raise RuntimeError("wlan0 chưa vào đúng SSID hoặc chưa nhận được IPv4")
        return "staged"
    except Exception as exc:
        log(f"Không áp dụng được Wi-Fi mới bằng Netplan: {_redact_secret(exc, password)}")
        if transaction.get("snapshot_path"):
            return "failed" if _restore_netplan_transaction(transaction, runner, log) else "rollback_failed"
        return "failed"


def stage_wifi_credentials(
    ssid,
    password,
    transaction_id=None,
    rollback_timeout=DEFAULT_ROLLBACK_TIMEOUT,
    runner=_run_command,
    log=_default_log,
):
    """Apply a candidate Wi-Fi while preserving a rollback transaction.

    Returns a JSON-serializable, password-free transaction dictionary. A
    ``staged`` result must later be passed to :func:`commit_wifi_transaction`
    or :func:`rollback_wifi_transaction`.
    """
    ssid, password = parse_wifi_response(f"{ssid}#{password}")
    existing = _existing_transaction(transaction_id, ssid)
    if existing is not None:
        log(f"Giao dịch Wi-Fi {existing['transaction_id']} đã tồn tại: {existing['status']}")
        return existing
    transaction = _new_transaction(ssid, transaction_id, rollback_timeout)
    current_ssid = get_current_ssid(runner=runner)
    transaction["previous_ssid"] = current_ssid

    if current_ssid == ssid and _has_ipv4(runner=runner):
        transaction["status"] = "already_connected"
        save_wifi_transaction(transaction)
        log(f"Đang kết nối đúng SSID {ssid} và đã có IPv4; không thay đổi cấu hình mạng")
        return transaction

    if hasattr(os, "geteuid") and os.geteuid() != 0:
        transaction["status"] = "permission_denied"
        save_wifi_transaction(transaction)
        log("Cần quyền root để thay đổi cấu hình Wi-Fi; giữ nguyên mạng hiện tại")
        return transaction

    log(f"Đang tạo giao dịch chuyển Wi-Fi từ {current_ssid or 'chưa kết nối'} sang {ssid}")
    try:
        with _wifi_change_guard(runner, log):
            if _network_manager_controls_wifi(runner=runner):
                transaction["backend"] = "NetworkManager"
                save_wifi_transaction(transaction)
                status = _stage_network_manager(transaction, password, runner, log)
            else:
                transaction["backend"] = "Netplan"
                save_wifi_transaction(transaction)
                status = _stage_netplan(transaction, password, runner, log)
    except Exception as exc:
        log(f"Không thể stage cấu hình Wi-Fi: {_redact_secret(exc, password)}")
        status = "failed"

    transaction["status"] = status
    if status == "staged":
        staged_at = time.time()
        transaction["staged_at"] = staged_at
        transaction["rollback_deadline"] = (
            staged_at + float(transaction["rollback_timeout_s"])
        )
    if status != "staged":
        transaction["error"] = transaction.get("error") or "Không thể kích hoạt Wi-Fi ứng viên"
    if not _set_status(transaction, status, log=log, error=transaction.get("error")) and status == "staged":
        # An unpersisted staged change cannot be recovered after restart.
        rollback_status = rollback_wifi_transaction(transaction, runner=runner, log=log)
        transaction["status"] = "rollback_failed" if rollback_status == "rollback_failed" else "failed"
    return transaction


def _validate_nm_candidate(transaction, runner):
    candidate = transaction.get("candidate") or {}
    candidate_uuid = candidate.get("uuid")
    if not _valid_uuid(candidate_uuid):
        return None
    details = _nm_profile_details("uuid", candidate_uuid, runner)
    if (
        details is None
        or details["uuid"] != candidate_uuid
        or details["type"] not in _WIFI_CONNECTION_TYPES
        or details["interface"] != WIFI_INTERFACE
    ):
        return None
    return details


def _commit_network_manager(transaction, runner, log):
    candidate = _validate_nm_candidate(transaction, runner)
    if candidate is None:
        log("Không commit: profile ứng viên có UUID/type/interface không hợp lệ")
        return False
    try:
        active = _nm_active_profile(runner)
    except ValueError as exc:
        log(f"Không commit: {exc}")
        return False
    if active is None or active.get("uuid") != candidate["uuid"]:
        log("Không commit: profile Wi-Fi ứng viên không phải profile đang hoạt động")
        return False
    if (
        get_current_ssid(runner=runner) != transaction.get("ssid")
        or not _has_ipv4(runner=runner)
    ):
        log("Không commit: Wi-Fi ứng viên chưa hoạt động với IPv4")
        return False

    profiles = runner(
        ["nmcli", "--terse", "--escape", "no", "--fields", "UUID,TYPE", "connection", "show"],
        timeout=10,
    )
    if profiles.returncode != 0:
        log(f"Không liệt kê được profile NetworkManager: {profiles.stderr.strip()}")
        return False

    delete_uuids = []
    for line in profiles.stdout.splitlines():
        try:
            profile_uuid, profile_type = (part.strip() for part in line.split(":", 1))
        except ValueError:
            log("Danh sách profile NetworkManager có dòng không hợp lệ")
            return False
        if profile_type not in _WIFI_CONNECTION_TYPES or profile_uuid == candidate["uuid"]:
            continue
        if not _valid_uuid(profile_uuid):
            log("Không commit: UUID profile Wi-Fi cũ không hợp lệ")
            return False
        details = _nm_profile_details("uuid", profile_uuid, runner)
        if details is None or details["uuid"] != profile_uuid:
            log("Không commit: không xác minh được profile Wi-Fi cũ")
            return False
        if details["type"] not in _WIFI_CONNECTION_TYPES:
            log("Không commit: type profile thay đổi trong khi xác minh")
            return False
        if details["interface"] == WIFI_INTERFACE:
            delete_uuids.append(profile_uuid)

    previous_uuid = (transaction.get("previous") or {}).get("uuid")
    # Delete the profile needed for rollback last. If deletion of another old
    # profile fails, the primary recovery path is still intact.
    delete_uuids.sort(key=lambda profile_uuid: profile_uuid == previous_uuid)
    for profile_uuid in delete_uuids:
        result = runner(["nmcli", "connection", "delete", "uuid", profile_uuid], timeout=10)
        if result.returncode != 0:
            log(f"Không xóa được profile Wi-Fi cũ {profile_uuid}: {result.stderr.strip()}")
            return False
    return True


def commit_wifi_transaction(transaction, runner=_run_command, log=_default_log):
    """Confirm a staged Wi-Fi transaction and discard its rollback data."""
    if transaction.get("status") == "already_connected":
        return "already_connected"
    if transaction.get("status") not in {"staged", "committing"}:
        return "not_staged"

    if transaction.get("status") != "committing":
        if not _set_status(transaction, "committing", log=log):
            return "commit_failed"

    backend = transaction.get("backend")
    if backend == "NetworkManager":
        success = _commit_network_manager(transaction, runner, log)
    elif backend == "Netplan":
        success = (
            get_current_ssid(runner=runner) == transaction.get("ssid")
            and _has_ipv4(runner=runner)
        )
        if not success:
            log("Không commit: Wi-Fi Netplan ứng viên chưa hoạt động với IPv4")
    else:
        success = False

    if not success:
        _set_status(transaction, "commit_failed", log=log, error="Không thể commit cấu hình Wi-Fi")
        return "commit_failed"

    if not _set_status(transaction, "committed", log=log):
        # The backend commit may already have deleted the previous NM profile.
        # Rolling back solely because this metadata write failed could delete
        # the active candidate as well and leave the board with no Wi-Fi. The
        # durable "committing" marker lets startup safely retry/finalize.
        log("Wi-Fi đã commit; trạng thái sẽ được hoàn tất lại khi bộ nhớ ghi được")
        return "committed"
    snapshot_path = transaction.get("snapshot_path")
    if snapshot_path:
        try:
            os.unlink(snapshot_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            # The network is committed; a stale root-only backup is safer than
            # reporting failure after deleting the old live configuration.
            log(f"Đã commit nhưng chưa dọn được snapshot Netplan: {exc}")
        else:
            transaction.pop("snapshot_path", None)
            transaction.pop("netplan_original_paths", None)
            save_wifi_transaction(transaction)
    log(f"Đã commit giao dịch Wi-Fi {transaction['transaction_id']} cho SSID {transaction['ssid']}")
    return "committed"


def rollback_wifi_transaction(transaction, runner=_run_command, log=_default_log):
    """Restore the previous network for a staged or failed transaction."""
    if transaction.get("status") in {"rolled_back", "committed", "already_connected"}:
        return "not_staged"
    if transaction.get("status") != "rolling_back":
        # Rollback is the safety path: attempt it even if the state disk is
        # temporarily unwritable. Persistence failure must not strand the board
        # on an unconfirmed network.
        _set_status(transaction, "rolling_back", log=log)
    with _wifi_change_guard(runner, log):
        backend = transaction.get("backend")
        if backend == "NetworkManager":
            restored = _nm_reactivate_previous(transaction, runner, log)
            removed = (
                _nm_delete_candidate(transaction.get("candidate", {}), runner, log)
                if restored else False
            )
            success = restored and removed
        elif backend == "Netplan":
            success = bool(transaction.get("snapshot_path")) and _restore_netplan_transaction(
                transaction, runner, log
            )
        else:
            success = False

    if not success:
        _set_status(transaction, "rollback_failed", log=log, error="Không thể khôi phục Wi-Fi cũ")
        return "rollback_failed"

    if not _set_status(transaction, "rolled_back", log=log):
        return "rollback_failed"
    snapshot_path = transaction.get("snapshot_path")
    if snapshot_path:
        try:
            os.unlink(snapshot_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            log(f"Đã rollback nhưng chưa dọn được snapshot Netplan: {exc}")
        else:
            transaction.pop("snapshot_path", None)
            transaction.pop("netplan_original_paths", None)
            save_wifi_transaction(transaction)
    return "rolled_back"


def _configure_network_manager(ssid, password, runner=_run_command, log=_default_log):
    """Backward-compatible immediate NetworkManager configuration helper."""
    transaction = stage_wifi_credentials(ssid, password, runner=runner, log=log)
    return (
        transaction["status"] == "already_connected"
        or commit_wifi_transaction(transaction, runner=runner, log=log) == "committed"
    )


def _restore_netplan(snapshot, original_paths, runner, log):
    """Legacy restore helper retained for callers outside this module."""
    success = True
    try:
        if NETPLAN_MANAGED_PATH not in original_paths and os.path.exists(NETPLAN_MANAGED_PATH):
            os.unlink(NETPLAN_MANAGED_PATH)
        for path, content in snapshot.items():
            _atomic_write(path, content, 0o600)
    except Exception as exc:
        log(f"Không ghi lại được snapshot Netplan: {exc}")
        success = False
    generated = runner(["netplan", "generate"], timeout=20)
    applied = runner(["netplan", "apply"], timeout=30) if generated.returncode == 0 else None
    if generated.returncode != 0 or applied is None or applied.returncode != 0:
        success = False
    if success:
        log("Đã khôi phục cấu hình Netplan trước đó")
    return success


def _configure_netplan(ssid, password, runner=_run_command, log=_default_log):
    """Backward-compatible immediate Netplan configuration helper."""
    ssid, password = parse_wifi_response(f"{ssid}#{password}")
    transaction = _new_transaction(ssid)
    transaction["previous_ssid"] = get_current_ssid(runner=runner)
    transaction["backend"] = "Netplan"
    save_wifi_transaction(transaction)
    status = _stage_netplan(transaction, password, runner, log)
    transaction["status"] = status
    save_wifi_transaction(transaction)
    if status != "staged":
        return False
    return commit_wifi_transaction(transaction, runner=runner, log=log) == "committed"


def apply_wifi_credentials(ssid, password, runner=_run_command, log=_default_log):
    """Apply and immediately commit credentials (startup compatibility API)."""
    transaction = stage_wifi_credentials(ssid, password, runner=runner, log=log)
    status = transaction["status"]
    if status in {"already_connected", "permission_denied"}:
        return status
    if status != "staged":
        log("Đồng bộ Wi-Fi thất bại; không reboot và giữ/khôi phục mạng cũ")
        return "rollback_failed" if status == "rollback_failed" else "failed"

    committed = commit_wifi_transaction(transaction, runner=runner, log=log)
    if committed == "committed":
        log(f"Đã kết nối và lưu SSID {ssid}; Wi-Fi cũ đã được loại bỏ")
        return "changed"

    rollback = rollback_wifi_transaction(transaction, runner=runner, log=log)
    if rollback == "rollback_failed":
        return "rollback_failed"
    return "failed"


def synchronize_wifi(serial_port, runner=_run_command, log=_default_log):
    """Synchronize Wi-Fi once at client startup and return a status string."""
    credentials = query_wifi_credentials(serial_port, log=log)
    if credentials is None:
        return "no_credentials"
    return apply_wifi_credentials(*credentials, runner=runner, log=log)
