# -*- coding: utf-8 -*-
"""Application-level orchestration for transactional Wi-Fi changes."""

import glob
import os
import threading
import time

try:
    from .wifi_sync import (
        TRANSACTION_DIR,
        commit_wifi_transaction,
        load_wifi_transaction,
        rollback_wifi_transaction,
        stage_wifi_credentials,
        transaction_needs_rollback,
    )
except ImportError:  # Executed directly from /root/mbt03 on Orange Pi.
    from wifi_sync import (
        TRANSACTION_DIR,
        commit_wifi_transaction,
        load_wifi_transaction,
        rollback_wifi_transaction,
        stage_wifi_credentials,
        transaction_needs_rollback,
    )


TERMINAL_STATUSES = {
    "already_connected",
    "committed",
    "rolled_back",
    "permission_denied",
    "failed",
}


class WiFiTransactionManager:
    """Stage, confirm and recover one Wi-Fi request at a time.

    ``core`` supplies authenticated messaging and reconnect signaling. Backend
    functions are injectable so state-machine tests do not touch host networking.
    """

    def __init__(
        self,
        core,
        rollback_timeout=90.0,
        transaction_dir=TRANSACTION_DIR,
        stage_func=stage_wifi_credentials,
        commit_func=commit_wifi_transaction,
        rollback_func=rollback_wifi_transaction,
        load_func=load_wifi_transaction,
        now_func=time.time,
        log=print,
    ):
        self.core = core
        self.rollback_timeout = float(rollback_timeout)
        self.transaction_dir = transaction_dir
        self._stage = stage_func
        self._commit = commit_func
        self._rollback = rollback_func
        self._load = load_func
        self._now = now_func
        self._log = log

        self._lock = threading.RLock()
        self._decision = threading.Condition(self._lock)
        self._current = None
        self._pending_action = None
        self._worker = None
        self._stopping = False

    @property
    def current_transaction(self):
        with self._lock:
            return dict(self._current) if self._current else None

    def _public_status(self, transaction):
        status = transaction.get("status", "failed")
        if status in {"preparing", "staged", "committing"}:
            return "awaiting_commit"
        if status == "rolling_back":
            return "rolling_back"
        return status

    def _send_status(self, transaction, status=None, error=None):
        if not transaction:
            return False
        public_status = status or self._public_status(transaction)
        return bool(
            self.core.send_wifi_config_status(
                transaction.get("transaction_id"),
                public_status,
                transaction.get("ssid", ""),
                error=error or transaction.get("error"),
            )
        )

    def _set_current(self, transaction):
        with self._lock:
            self._current = transaction

    def _restore_core_request_id(self, transaction):
        """Bind a recovered transaction to the transport decision filter."""
        restore = getattr(self.core, "restore_active_wifi_request", None)
        if not callable(restore):
            return True
        request_id = transaction.get("transaction_id")
        if restore(request_id):
            return True
        self._log(
            f"Không thể khôi phục request Wi-Fi đang hoạt động: {request_id}"
        )
        return False

    def _start_worker(self, target, *args):
        with self._lock:
            if self._worker and self._worker.is_alive():
                return False
            self._worker = threading.Thread(
                target=target,
                args=args,
                daemon=True,
                name="WiFiTransaction",
            )
            self._worker.start()
            return True

    def handle_request(self, payload):
        request_id = payload["request_id"]
        with self._lock:
            if self._current:
                current_id = self._current.get("transaction_id")
                current_status = self._current.get("status")
                if current_id == request_id:
                    self._send_status(self._current)
                    return True
                if current_status not in TERMINAL_STATUSES:
                    return False
            self._current = {
                "transaction_id": request_id,
                "ssid": payload["ssid"],
                "status": "preparing",
            }
        self._send_status(self._current, "applying")
        request_timeout = payload.get(
            "rollback_timeout_seconds", self.rollback_timeout
        )
        try:
            request_timeout = min(600.0, max(30.0, float(request_timeout)))
        except (TypeError, ValueError):
            request_timeout = self.rollback_timeout
        return self._start_worker(
            self._stage_and_wait,
            request_id,
            payload["ssid"],
            payload["password"],
            request_timeout,
        )

    def _stage_and_wait(self, request_id, ssid, password, rollback_timeout):
        try:
            transaction = self._stage(
                ssid,
                password,
                transaction_id=request_id,
                rollback_timeout=rollback_timeout,
                log=self._log,
            )
        except Exception as exc:
            transaction = {
                "transaction_id": request_id,
                "ssid": ssid,
                "status": "failed",
                "error": str(exc),
            }
        finally:
            # Do not retain the passphrase as object state or serialize it.
            password = None

        self._set_current(transaction)
        status = transaction.get("status")
        if status != "staged":
            self._send_status(transaction)
            return

        # NetworkManager/Netplan has switched routes. Closing/recreating the
        # ZMQ cycle avoids keeping a half-open socket pinned to the old route.
        self.core.request_reconnect("wifi_staged")
        self._send_status(transaction, "awaiting_commit")
        self._wait_for_decision(transaction)

    def _wait_for_decision(self, transaction):
        deadline = float(transaction.get("rollback_deadline") or self._now())
        action = None
        with self._decision:
            while not self._stopping:
                if self._pending_action:
                    pending_id, pending_action = self._pending_action
                    if pending_id == transaction.get("transaction_id"):
                        self._pending_action = None
                        action = pending_action
                        break
                if transaction_needs_rollback(
                    transaction, now=self._now()
                ):
                    action = "rollback"
                    break
                remaining = deadline - self._now()
                if remaining <= 0:
                    action = "rollback"
                    break
                self._decision.wait(timeout=min(1.0, remaining))

        if self._stopping:
            # The password-free state on disk is recovered on the next start.
            return
        if action == "commit":
            result = self._commit(transaction, log=self._log)
            if result == "commit_failed":
                self._send_status(transaction, result)
                result = self._rollback(transaction, log=self._log)
                self.core.request_reconnect("wifi_commit_failed")
            self._send_status(transaction, result)
            return

        result = self._rollback(transaction, log=self._log)
        self.core.request_reconnect("wifi_rollback")
        self._send_status(transaction, result)

    def handle_commit(self, payload):
        return self._queue_decision(payload.get("request_id"), "commit")

    def handle_rollback(self, payload):
        return self._queue_decision(payload.get("request_id"), "rollback")

    def _queue_decision(self, request_id, action):
        with self._decision:
            if not self._current:
                return False
            if self._current.get("transaction_id") != request_id:
                return False
            self._pending_action = (request_id, action)
            self._decision.notify_all()
            return True

    def recover(self):
        """Resume the newest non-terminal transaction after service restart."""
        candidates = []
        for path in glob.glob(os.path.join(self.transaction_dir, "*.json")):
            filename = os.path.basename(path)
            if filename.endswith(".netplan-snapshot.json"):
                continue
            try:
                transaction = self._load(path)
            except Exception as exc:
                self._log(f"Không đọc được giao dịch Wi-Fi {path}: {exc}")
                continue
            transaction_id = transaction.get("transaction_id")
            if (
                not isinstance(transaction_id, str)
                or filename != f"{transaction_id}.json"
            ):
                self._log(f"Bỏ qua file trạng thái Wi-Fi không hợp lệ: {path}")
                continue
            # Boot defaults are not app transactions and must never roll back
            # to an old credential or suppress the next boot's UART query.
            if transaction.get('startup_fallback'):
                continue
            if transaction.get("status") not in TERMINAL_STATUSES:
                candidates.append(transaction)
        if not candidates:
            return False

        transaction = max(candidates, key=lambda item: item.get("updated_at", 0))
        if not self._restore_core_request_id(transaction):
            return False
        self._set_current(transaction)
        return self._start_worker(self._recover_worker, transaction)

    def _recover_worker(self, transaction):
        status = transaction.get("status")
        if status == "committing":
            result = self._commit(transaction, log=self._log)
            self._send_status(transaction, result)
            return
        if status in {"rolling_back", "commit_failed", "rollback_failed"}:
            result = self._rollback(transaction, log=self._log)
            self.core.request_reconnect("wifi_recovery_rollback")
            self._send_status(transaction, result)
            return
        if status in {"preparing", "failed"}:
            # A crash before stage completion leaves no confirmed candidate.
            result = self._rollback(transaction, log=self._log)
            self.core.request_reconnect("wifi_recovery_rollback")
            self._send_status(transaction, result)
            return
        if status == "staged" and transaction_needs_rollback(
            transaction, now=self._now()
        ):
            result = self._rollback(transaction, log=self._log)
            self.core.request_reconnect("wifi_recovery_timeout")
            self._send_status(transaction, result)
            return
        self._send_status(transaction, "awaiting_commit")
        self._wait_for_decision(transaction)

    def on_session_ready(self):
        with self._lock:
            transaction = self._current
        if transaction:
            self._send_status(transaction)

    def stop(self):
        with self._decision:
            self._stopping = True
            self._decision.notify_all()
