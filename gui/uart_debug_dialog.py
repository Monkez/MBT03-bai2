import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout,
)

import config as cf
from assets.server_client.protocol import Protocol


TERMINAL_WIFI_STATES = {
    "already_connected", "committed", "rolled_back", "permission_denied",
    "failed", "rollback_failed", "busy", "invalid", "unsupported", "timeout",
}
WIFI_STATUS_TEXT = {
    "sending": "Đang gửi yêu cầu...",
    "sent": "Đã gửi, đang chờ board xác nhận...",
    "accepted": "Board đã nhận yêu cầu, đang thử mạng mới...",
    "duplicate": "Board đang tiếp tục yêu cầu đã nhận...",
    "applying": "Đang chuyển sang mạng mới...",
    "awaiting_commit": "Đã vào mạng mới, đang chờ kết nối ổn định để xác nhận...",
    "commit_retry": "Đang chờ kết nối ổn định để xác nhận...",
    "commit_sending": "Đang gửi xác nhận lưu mạng mới...",
    "commit_sent": "Đã gửi xác nhận, đang chờ board lưu cấu hình...",
    "committed": "Đã lưu Wi-Fi mới thành công.",
    "already_connected": "Board đang dùng đúng Wi-Fi này; không thay đổi.",
    "rolling_back": "Đang khôi phục Wi-Fi cũ...",
    "rolled_back": "Đã khôi phục Wi-Fi cũ.",
    "ack_timeout": "Chưa nhận được xác nhận; tiếp tục chờ board thử mạng hoặc khôi phục.",
    "busy": "Board đang xử lý một yêu cầu Wi-Fi khác.",
    "permission_denied": "Board không đủ quyền sửa cấu hình mạng.",
    "failed": "Không đổi được Wi-Fi. Kiểm tra kết nối và trạng thái board.",
    "commit_failed": "Không lưu được mạng mới; board đang khôi phục mạng cũ.",
    "rollback_failed": "Board không khôi phục được mạng cũ. Cần kiểm tra trực tiếp.",
    "invalid": "Board từ chối thông tin Wi-Fi không hợp lệ.",
    "unsupported": "Client trên board chưa hỗ trợ đổi Wi-Fi.",
    "timeout": "Hết thời gian xác nhận. Chưa xác định kết quả; kiểm tra kết nối board.",
}


class UartDebugDialog(QDialog):
    operation_done = pyqtSignal(object)

    def __init__(self, servers, parent=None):
        super().__init__(parent)
        self.servers = list(servers)
        self._requests = {}  # Latest transaction per pedestal; never store passwords.
        self._busy = False
        self._closing = False
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="DeviceDebug")
        self.operation_done.connect(self._on_operation_done)
        self.setWindowTitle("UART Debug · Ctrl+S")
        self.setModal(False)
        self.resize(620, 440)
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QDialog { background: #f5f5f3; color: #101010; }
            QLabel#DialogTitle { font-size: 18px; font-weight: 700; }
            QLabel#DialogHint { color: #606060; }
            QLineEdit, QComboBox {
                min-height: 30px; border: 1px solid #cfcfcf; border-radius: 6px;
                background: white; padding: 4px 10px; font-size: 14px;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #009200; }
            QPushButton {
                min-height: 32px; padding: 4px 14px; border: 1px solid #cfcfcf;
                border-radius: 6px; background: white; color: #101010;
            }
            QPushButton:hover { background: #e8eee8; }
            QPushButton#SendButton { background: #009900; color: white; }
            QPushButton#RedButton { background: #c47d5e; color: white; }
            QPushButton#GreenButton { background: #ecffe6; color: #007a16; }
            QPushButton:disabled { background: #e5e7eb; color: #6b7280; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel("UART Debug")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        hint = QLabel("Gửi lệnh kiểm tra tới bệ hoặc đổi Wi-Fi trực tiếp trên Orange Pi.")
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.port_combo = QComboBox()
        self.port_combo.addItem("Tất cả bệ online", -1)
        for index, server in enumerate(self.servers):
            self.port_combo.addItem(f"Bệ {server.port_id}", index)
        self.command_input = QLineEdit("0LG00")
        self.command_input.setPlaceholderText("Nhập lệnh UART")
        self.ssid_input = QLineEdit()
        self.ssid_input.setPlaceholderText("Tên Wi-Fi, ví dụ MBT03-5G")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Mật khẩu Wi-Fi")
        form = QFormLayout()
        for label, field in (("Bệ / Port", self.port_combo), ("Lệnh UART", self.command_input),
                             ("Wi-Fi SSID", self.ssid_input), ("Mật khẩu", self.password_input)):
            form.addRow(label, field)
            field.setAccessibleName(label)
        layout.addLayout(form)

        quick = QHBoxLayout()
        for command, label, style in (
            ("0LR01", "Đỏ nhấp nháy", "RedButton"),
            ("0LG01", "Xanh nhấp nháy", "GreenButton"),
            ("0LG00", "Xanh sáng", "GreenButton"),
        ):
            button = QPushButton(label)
            button.setObjectName(style)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, cmd=command: self.command_input.setText(cmd))
            quick.addWidget(button)
        layout.addLayout(quick)
        wifi_hint = QLabel("Chọn một bệ để đổi Wi-Fi. Board giữ mạng cũ để tự khôi phục nếu mất kết nối.")
        wifi_hint.setObjectName("DialogHint")
        wifi_hint.setWordWrap(True)
        layout.addWidget(wifi_hint)
        self.wifi_button = QPushButton("Đổi Wi-Fi an toàn")
        self.wifi_button.setObjectName("SendButton")
        self.wifi_button.setAutoDefault(False)
        layout.addWidget(self.wifi_button)
        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(40)
        layout.addWidget(self.status_label)
        actions = QHBoxLayout()
        actions.addStretch()
        self.send_button = QPushButton("Gửi UART")
        self.send_button.setObjectName("SendButton")
        self.send_button.setAutoDefault(False)
        close_button = QPushButton("Đóng")
        close_button.setAutoDefault(False)
        actions.addWidget(self.send_button)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self.send_button.clicked.connect(self.send_command)
        self.command_input.returnPressed.connect(self.send_command)
        self.wifi_button.clicked.connect(self.send_wifi)
        self.password_input.returnPressed.connect(self.send_wifi)
        self.port_combo.currentIndexChanged.connect(self._show_selected_status)
        close_button.clicked.connect(self.close)
        for server in self.servers:
            server.wifi_config_event_signal.connect(self._on_wifi_event)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(500)
        self.refresh()

    def _testing(self):
        return bool(getattr(self.parent(), "testing", False))

    def has_pending_operations(self):
        return self._busy or any(
            request["status"] not in TERMINAL_WIFI_STATES
            for request in self._requests.values()
        )

    def _can_send(self):
        if self._closing or self._busy:
            return False
        if self._testing():
            self.status_label.setText("Đang chạy bài bắn; kết thúc bài trước khi gửi lệnh kiểm tra.")
            return False
        return True

    def _selected_server(self):
        index = self.port_combo.currentData()
        return self.servers[index] if index is not None and 0 <= index < len(self.servers) else None

    def _show_selected_status(self):
        server = self._selected_server()
        request = self._requests.get(server.port_id) if server else None
        if request:
            self.status_label.setText(
                f"Bệ {server.port_id} · {request['ssid']}: "
                + WIFI_STATUS_TEXT.get(request["status"], request["status"])
            )
        else:
            self.status_label.setText("Sẵn sàng")

    def _submit(self, kind, function, *args, request=None, **kwargs):
        self._busy = True
        self.refresh()
        self._pool.submit(self._run_operation, kind, function, args, kwargs, request)

    def _run_operation(self, kind, function, args, kwargs, request):
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            # Unexpected transport errors must not expose Wi-Fi credentials.
            result = {"ok": False, "reason": type(exc).__name__}
        if not self._closing:
            self.operation_done.emit({"kind": kind, "result": result, "request": request})

    def send_command(self):
        if not self._can_send():
            return
        command = self.command_input.text().strip()
        if not command:
            self.status_label.setText("Nhập lệnh UART trước khi gửi.")
            return
        if Protocol.is_legacy_wifi_command(command):
            self.status_label.setText("Lệnh Wifi# thô đã bị khóa; hãy dùng Đổi Wi-Fi an toàn.")
            return
        selected = self._selected_server()
        targets = [selected] if selected is not None else [s for s in self.servers if s.is_connected]
        if not targets:
            self.status_label.setText("Không có bệ online để gửi lệnh.")
            return
        self._submit("uart", self._send_uart, targets, command + "\n")

    @staticmethod
    def _send_uart(targets, command):
        sent, failed = [], []
        for server in targets:
            try:
                ok = server.send_uart_command(command)
            except Exception:
                ok = False
            (sent if ok else failed).append(str(server.port_id))
        return {"sent": sent, "failed": failed}

    def send_wifi(self):
        if not self._can_send():
            return
        server = self._selected_server()
        if server is None:
            self.status_label.setText("Chọn một bệ cụ thể trước khi đổi Wi-Fi.")
            return
        active = self._requests.get(server.port_id)
        if active and active["status"] not in TERMINAL_WIFI_STATES:
            self._show_selected_status()
            return
        try:
            ssid, password = Protocol.validate_wifi_credentials(
                self.ssid_input.text().strip(), self.password_input.text()
            )
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        answer = QMessageBox.question(
            self, "Xác nhận đổi Wi-Fi",
            f"Đổi Bệ {server.port_id} sang Wi-Fi '{ssid}'?\n\n"
            "Board thử mạng mới và tự khôi phục mạng cũ nếu không được xác nhận kịp thời.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes or not self._can_send():
            return
        timeout = cf.config_float("wifi.rollback_timeout_seconds", 90, minimum=30, maximum=600)
        now = time.monotonic()
        request = {
            "request_id": uuid.uuid4().hex, "port_id": server.port_id, "ssid": ssid,
            "status": "sending", "created_at": now, "deadline": now + timeout,
        }
        self._requests[server.port_id] = request
        self.password_input.clear()
        self._show_selected_status()
        self._submit("wifi", server.request_wifi_config, ssid, password, request["request_id"],
                     rollback_timeout_seconds=timeout, request=request)

    def _on_operation_done(self, event):
        self._busy = False
        if self._closing:
            return
        result, request = event["result"], event["request"]
        if event["kind"] == "uart":
            sent = ", ".join(result.get("sent", [])) or "không có"
            failed = ", ".join(result.get("failed", [])) or "không có"
            self.status_label.setText(f"Đã gửi tới bệ: {sent}. Gửi thất bại: {failed}.")
        elif request and request["status"] in {"sending", "commit_sending"}:
            if result.get("ok"):
                request["status"] = "sent" if event["kind"] == "wifi" else "commit_sent"
            elif event["kind"] == "commit" and result.get("reason") == "not_healthy":
                request["status"] = "commit_retry"
                request["retry_at"] = time.monotonic() + 0.5
            else:
                request["status"] = "unsupported" if result.get("reason") == "unsupported_client" else "failed"
            self._show_selected_status()
        self.refresh()

    def _on_wifi_event(self, event):
        request = self._requests.get(event.get("port_id"))
        status = event.get("status")
        if (request is None or event.get("request_id") != request["request_id"]
                or status not in WIFI_STATUS_TEXT):
            return
        if request["status"] in TERMINAL_WIFI_STATES and status not in TERMINAL_WIFI_STATES:
            return
        request["status"] = status
        self._show_selected_status()
        self.refresh()

    def refresh(self):
        if self._closing:
            return
        can_send = not self._busy and not self._testing()
        self.send_button.setEnabled(can_send)
        self.wifi_button.setEnabled(can_send)
        for index, server in enumerate(self.servers, start=1):
            state = "online" if server.is_connected else "offline"
            self.port_combo.setItemText(index, f"Bệ {server.port_id} ({state})")
        now = time.monotonic()
        for server in self.servers:
            request = self._requests.get(server.port_id)
            if not request or request["status"] in TERMINAL_WIFI_STATES:
                continue
            if now >= request["deadline"]:
                request["status"] = "timeout"
                self._show_selected_status()
            elif request["status"] == "sent" and now - request["created_at"] >= cf.config_float(
                "wifi.request_ack_timeout_seconds", 3, minimum=0.1, maximum=60
            ):
                request["status"] = "ack_timeout"
                self._show_selected_status()
            elif (request["status"] in {"awaiting_commit", "commit_retry"}
                  and not self._busy and now >= request.get("retry_at", 0)):
                # Commit only after the server sees the same healthy board again.
                request["status"] = "commit_sending"
                self._submit("commit", server.commit_wifi_config, request["request_id"], request=request)
        if self._testing():
            self.status_label.setText("Đang chạy bài bắn; các nút gửi tạm khóa.")

    def hideEvent(self, event):
        self.password_input.clear()
        # Keep tracking an in-flight Wi-Fi change when the user hides this window.
        super().hideEvent(event)

    def shutdown(self):
        self._closing = True
        self._timer.stop()
        self.password_input.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.close()
