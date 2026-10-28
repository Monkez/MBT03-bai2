import json
import logging
import math
import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime

import cv2
import numpy as np
from PyQt5 import QtGui, uic
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QMainWindow, QMessageBox, QShortcut

import config as cf
import scoring
from assets.server_client.discovery import HubRegistrar
from assets.server_client.server_core import MBT03ServerCore
from assets.server_client.protocol import Protocol
from gui.client_widget import ClientWidget
from gui.lora_controller import LoraController
from gui.option_window import OptionWindow
from gui.review_window import ShotReviewDialog
from gui.setting_window import SettingWindow
from gui.shot_sound import ShotSound
from gui.hit_sound import HitSound
from gui.result_sound import ResultSound
from gui.uart_debug_dialog import UartDebugDialog
from gui.shooting_roster import ShootingRoster
from gui.shooting_session import (
    MAX_DURATION_SECONDS, TARGET_CLASS_SEQUENCE, TARGET_VISIBLE_SECONDS_BY_CLASS,
    ShootingSession,
)


class StartupCancelled(Exception):
    pass


def _configured_auto_close_commands():
    configured = cf.get_setting(
        "shooting.automatic_close_target.commands_by_class", {}
    )
    commands = {}
    if isinstance(configured, dict):
        for class_id, item in configured.items():
            if not isinstance(item, dict):
                continue
            command = item.get("command")
            if not isinstance(command, str) or not command:
                continue
            try:
                numeric_class_id = int(class_id)
            except (TypeError, ValueError):
                continue
            commands[numeric_class_id] = (
                command,
                str(item.get("description") or f"gap bia class {numeric_class_id}"),
            )
    return commands


def _configured_lora_script():
    configured = cf.get_setting("shooting.lora_timeline", [])
    script = []
    if isinstance(configured, list):
        for item in configured:
            if not isinstance(item, dict):
                continue
            command = item.get("command")
            if not isinstance(command, str) or not command:
                continue
            try:
                delay_seconds = float(item.get("delay_seconds", 0))
            except (TypeError, ValueError):
                continue
            script.append(
                (
                    delay_seconds,
                    command,
                    str(item.get("description") or command),
                )
            )
    # Validate commanded visibility; grace periods may overlap or meet the deadline.
    if (len(script) != len(TARGET_CLASS_SEQUENCE)
            or not isinstance(configured, list) or len(configured) != len(script)
            or any(not math.isfinite(item[0]) or item[0] < 0
                   or item[0] + TARGET_VISIBLE_SECONDS_BY_CLASS[class_id] > MAX_DURATION_SECONDS
                   for class_id, item in zip(TARGET_CLASS_SEQUENCE, script))
            or any(right[0] < left[0] + TARGET_VISIBLE_SECONDS_BY_CLASS[class_id]
                   for class_id, left, right in zip(TARGET_CLASS_SEQUENCE, script, script[1:]))):
        print("[Config] Lich bia khong hop le, dung lich mac dinh 6 -> 10 -> 7 -> 8")
        script = [
            (item["delay_seconds"], item["command"], item["description"])
            for item in cf.DEFAULT_CONFIG["shooting"]["lora_timeline"]
        ]
    return tuple(script)


class MainWindow(QMainWindow):
    scoring_done_signal = pyqtSignal(object)
    q0_done_signal = pyqtSignal(object)
    START_UART_COMMAND = cf.config_str(
        "shooting.start_uart_command", "0F016\n"
    )
    MANUAL_OPEN_TARGET_COMMANDS = ("@114#", "@224#", "@334#", "@441#")
    AUTO_CLOSE_TARGET_COMMANDS = _configured_auto_close_commands()
    LORA_SCRIPT = _configured_lora_script()

    def __init__(self):
        super().__init__()

        option_dialog = OptionWindow(self)
        option_dialog.setWindowModality(Qt.ApplicationModal)
        if option_dialog.exec_() != option_dialog.Accepted or not option_dialog.start:
            raise StartupCancelled()

        uic.loadUi(cf.DATA_DIR + "assets/qt/main.ui", self)
        self.setWindowIcon(QtGui.QIcon(cf.DATA_DIR + "assets/images/icon.png"))

        self.options = option_dialog
        self.p_num = option_dialog.p_num
        self.automatic_close_target_enabled = (
            option_dialog.automatic_close_target_enabled
        )
        self.testing = False
        self._manual_targets_busy = False
        self.client_widgets = []
        self._start_button_text = self.start_btn.text()
        self._test_start_time = 0.0
        self._shooting_session = None
        self._shot_sound = ShotSound(self)
        self._hit_sound = HitSound(self)
        self._result_sound = ResultSound(self)
        self._result_sound.changed.connect(self._update_score_speak_buttons)
        self._result_sound.failed.connect(
            lambda message: QMessageBox.warning(self, "Đọc kết quả", message)
        )
        self._test_timeout_timer = QTimer(self)
        self._test_timeout_timer.setSingleShot(True)
        self._test_timeout_timer.setTimerType(Qt.PreciseTimer)
        self._test_timeout_timer.timeout.connect(self.stop_test)
        self._start_followup_timer = QTimer(self)
        self._start_followup_timer.setSingleShot(True)
        self._start_followup_timer.setTimerType(Qt.PreciseTimer)
        self._start_followup_timer.timeout.connect(self._send_start_followup_command)
        self._lora_schedule_timers = []
        self._closing = False
        self.servers = []
        self.hub_registrar = None
        self._ping_data = {}
        self._battery_data = {}
        self._confirmed_ports = set()
        self._q0_calibrated = {}
        self._setting_window = None
        self._uart_debug_dialog = None
        self._review_sessions = {}
        self._review_shot_counters = {}
        self._review_session_counter = 0
        self._active_review_session_id = None
        self._previous_review_session_id = None
        self._auto_closed_target_classes = set()
        self._save_raw_data_enabled = cf.config_bool("save_raw_data", True)
        self._raw_data_dir = os.path.join(cf.DATA_DIR, "raw_camera_images")
        self._raw_image_pool = (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="RawCamera")
            if self._save_raw_data_enabled
            else None
        )
        self._scoring_local = threading.local()
        self._scoring_pool = ThreadPoolExecutor(
            max_workers=max(
                1,
                min(
                    self.p_num,
                    cf.config_int(
                        "runtime.max_scoring_workers", 4, minimum=1, maximum=16
                    ),
                ),
            ),
            thread_name_prefix="Score",
        )
        self._reference_images = self._load_reference_images()
        self.scoring_done_signal.connect(self._on_scoring_done)

        self.lora = LoraController(self)
        self.lora.connection_changed.connect(self._on_lora_connection_changed)
        self.lora.command_finished.connect(self._on_lora_command_finished)
        self.lora.command_sent.connect(self._on_lora_command_sent)
        self.lora.sequence_finished.connect(self._on_manual_targets_finished)

        self._configure_main_ui()
        self._create_client_widgets()
        self._roster = ShootingRoster(self)
        self._start_servers()
        QTimer.singleShot(0, self.lora.auto_connect)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_app)
        self.timer.start(
            cf.config_int(
                "runtime.main_status_refresh_ms", 1000, minimum=100, maximum=60000
            )
        )

    def _configure_main_ui(self):
        self.setting_btn.clicked.connect(self.open_setting_window)
        self.start_btn.clicked.connect(self.start_btn_clicked)
        self.close_target_btn.clicked.connect(self._close_targets_manually)
        self.open_target_btn.clicked.connect(self._open_targets_manually)
        self._uart_debug_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+S"), self)
        self._uart_debug_shortcut.activated.connect(self._open_uart_debug_dialog)

    def _open_uart_debug_dialog(self):
        if self._uart_debug_dialog is None:
            self._uart_debug_dialog = UartDebugDialog(self.servers, self)
        self._uart_debug_dialog.refresh()
        self._uart_debug_dialog.show()
        self._uart_debug_dialog.raise_()
        self._uart_debug_dialog.activateWindow()

    def _create_client_widgets(self):
        positions = self._client_positions(self.p_num)
        target_layout_mode = "two_pedestals" if self.p_num == 2 else "default"
        for index in range(self.p_num):
            widget = ClientWidget(index + 1, self, target_layout_mode=target_layout_mode)
            widget.score_speak_requested.connect(self.request_score_speak)
            widget.review_requested.connect(self.open_shot_review)
            widget.locate_requested.connect(self._toggle_pedestal_locate)
            self.client_widgets.append(widget)
            row, col = positions[index]
            self.client_grid_layout.addWidget(widget, row, col)

    def _toggle_pedestal_locate(self, port_id):
        if self._closing or not (1 <= port_id <= min(len(self.servers), len(self.client_widgets))):
            return
        server = self.servers[port_id - 1]
        if not server.is_connected:
            return
        widget = self.client_widgets[port_id - 1]
        active = not widget.locating
        command = "0LR01\n" if active else "0LG00\n"
        if server.send_uart_command(command):
            widget.set_locating(active)
            logging.getLogger("mbt03_server").info("[Locate] Bệ %s: gửi %s", port_id, command.strip())
        else:
            logging.getLogger("mbt03_server").warning("[Locate] Bệ %s: không gửi được %s", port_id, command.strip())
            QMessageBox.warning(self, "Tìm súng", f"Không gửi được lệnh đến súng bệ {port_id}. Vui lòng thử lại.")

    def _load_reference_images(self):
        images = {}
        for class_id, template in scoring.TARGET_TEMPLATES.items():
            path = os.path.join(cf.DATA_DIR, "assets", "signs", template["file"])
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is not None:
                images[class_id] = image
        return images

    def _load_system_id(self):
        path = os.path.join(cf.DATA_DIR, "system_config.json")
        try:
            with open(path, "r", encoding="utf-8") as file:
                system_id = json.load(file).get("system_id")
                if system_id:
                    return system_id
        except (OSError, ValueError, TypeError):
            pass
        system_id = uuid.uuid4().hex[:12]
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump({"system_id": system_id}, file)
        except OSError as exc:
            print(f"[Main] Khong luu duoc system_id: {exc}")
        return system_id

    def _start_servers(self):
        """Start one camera/client endpoint per configured pedestal."""
        try:
            Protocol.configure_connection(cf.get_setting("connection", {}))
            Protocol.configure_media(cf.get_setting("media", {}))
        except ValueError as exc:
            print(f"[Config] Policy server/client khong hop le: {exc}")
            Protocol.configure_connection(cf.DEFAULT_CONFIG["connection"])
            Protocol.configure_media(cf.DEFAULT_CONFIG["media"])
        system_id = self._load_system_id()
        try:
            self.hub_registrar = HubRegistrar(system_id=system_id, log_func=print)
            for port_id in range(1, self.p_num + 1):
                server = MBT03ServerCore(
                    port_id,
                    system_id=system_id,
                )
                server.log_signal.connect(print)
                server.client_connected_event_signal.connect(
                    lambda event, pid=port_id: self._on_client_connected_event(
                        pid, event
                    )
                )
                server.client_disconnected_event_signal.connect(
                    lambda event, pid=port_id: self._on_client_disconnected_event(
                        pid, event
                    )
                )
                server.shoot_image_signal.connect(
                    lambda frame, q0, pid=port_id: self._on_shoot_image(pid, frame, q0)
                )
                server.connection_quality_signal.connect(
                    lambda quality, pid=port_id: self._on_connection_quality(pid, quality)
                )
                server.data_received_signal.connect(
                    lambda data, pid=port_id: self._on_data_received(pid, data)
                )
                server.start()
                self.servers.append(server)
            self._update_hub_availability()
        except Exception as exc:
            print(f"[Main] Khong khoi dong duoc ket noi client: {exc}")

    def _on_data_received(self, port_id, data):
        if self._closing or not (1 <= port_id <= len(self.client_widgets)):
            return
        if not isinstance(data, dict):
            return
        code = data.get("UART_RX_DEBUG")
        if not isinstance(code, str):
            return
        # Accept complete hardware tokens, not substrings such as E10.
        code = code.strip()
        code = {"0E100": "E1", "0E200": "E2"}.get(code, code)
        self.client_widgets[port_id - 1].show_error(code)

    def _update_hub_availability(self):
        if self.hub_registrar is None:
            return
        available = {
            server.port_id: server.port
            for server in self.servers
            if not server.is_session_reserved
        }
        self.hub_registrar.update_available(available)

    def _session_event_is_current(self, port_id, event):
        if not (1 <= port_id <= len(self.servers)):
            return False
        generation = event.get("session_generation")
        return (
            generation is None
            or generation == self.servers[port_id - 1].session_generation
        )

    def _on_client_connected_event(self, port_id, event):
        if self._session_event_is_current(port_id, event):
            self._on_client_connected(port_id, event.get("info", ""))

    def _on_client_disconnected_event(self, port_id, event):
        if self._session_event_is_current(port_id, event):
            self._on_client_disconnected(port_id)

    def _on_client_connected(self, port_id, info):
        print(f"[Main] Be {port_id} da ket noi: {info}")
        if 1 <= port_id <= len(self.client_widgets):
            server = self.servers[port_id - 1] if port_id <= len(self.servers) else None
            state = None if server is not None and server.is_handshaking else True
            self.client_widgets[port_id - 1].set_connection_state(state, info)
            client_info = server.connected_client_info if server is not None else None
            if client_info:
                q0 = client_info.get("q0_value")
                if isinstance(q0, (list, tuple)) and len(q0) == 2:
                    self._q0_calibrated[port_id] = {
                        "q0": [float(q0[0]), float(q0[1])],
                        "size": int(client_info.get("q0_size", 0) or 0),
                    }
        self._update_hub_availability()

    def _on_client_disconnected(self, port_id):
        if (
            1 <= port_id <= len(self.servers)
            and self.servers[port_id - 1].is_session_reserved
        ):
            return
        print(f"[Main] Be {port_id} da ngat ket noi")
        if 1 <= port_id <= len(self.client_widgets):
            self.client_widgets[port_id - 1].set_connection_state(False)
        self._ping_data.pop(port_id, None)
        self._battery_data.pop(port_id, None)
        self._confirmed_ports.discard(port_id)
        self._update_hub_availability()

    def _on_connection_quality(self, port_id, quality):
        """Update confirmed connection, ping and battery reported by heartbeat."""
        # Display the same rolling RTT that drives connection classification.
        ping = quality.get("avg_rtt_ms")
        if ping is None:
            ping = quality.get("rtt_ms")
        battery = quality.get("battery_percent")
        if ping is not None:
            self._ping_data[port_id] = ping
        if battery is not None:
            self._battery_data[port_id] = battery
        if 1 <= port_id <= len(self.client_widgets):
            widget = self.client_widgets[port_id - 1]
            widget.set_connection_quality_state(
                quality.get("connection_state", "healthy"),
                self._ping_data.get(port_id),
                self._battery_data.get(port_id),
            )
        if port_id not in self._confirmed_ports:
            self._confirmed_ports.add(port_id)
            self._update_hub_availability()

    def _on_shoot_image(self, port_id, frame, q0_data):
        """Queue scoring for an image received from a physical pedestal."""
        raw_image_save = self._queue_raw_camera_image(port_id, frame)
        if self._setting_window is not None and self._setting_window.Q0:
            self._shot_sound.play()
            return
        q0 = (q0_data or {}).get("q0", [0.5, 0.5])
        try:
            bullet_point = (float(q0[0]), float(q0[1]))
        except (TypeError, ValueError, IndexError):
            bullet_point = (0.5, 0.5)
        received_at = (q0_data or {}).get("_server_received_at")
        if (isinstance(received_at, (int, float)) and not isinstance(received_at, bool)
                and math.isfinite(received_at)):
            self.process_shot(port_id, frame, bullet_point, received_at=received_at,
                              raw_image_save=raw_image_save)
        else:
            self.process_shot(port_id, frame, bullet_point, raw_image_save=raw_image_save)

    def _queue_raw_camera_image(self, port_id, frame):
        """Snapshot an untouched shoot frame and queue a lossless PNG write."""
        if not self._save_raw_data_enabled or self._raw_image_pool is None:
            return None
        if frame is None or not hasattr(frame, "copy"):
            return None
        captured_at = datetime.now()
        try:
            return self._raw_image_pool.submit(
                self._save_raw_camera_image,
                self._raw_data_dir,
                port_id,
                frame.copy(),
                captured_at,
            )
        except RuntimeError as exc:
            print(f"[RawData] Cannot queue image from pedestal {port_id}: {exc}")
            failed_save = Future()
            failed_save.set_result(None)
            return failed_save

    @staticmethod
    def _save_raw_camera_image(output_dir, port_id, frame, captured_at=None):
        """Write one received camera frame without overlays or transformations."""
        captured_at = captured_at or datetime.now()
        timestamp = captured_at.strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}_be_{int(port_id):02d}.png"
        path = os.path.join(output_dir, filename)
        try:
            os.makedirs(output_dir, exist_ok=True)
            if not cv2.imwrite(path, frame):
                raise OSError("cv2.imwrite returned False")
        except (OSError, TypeError, ValueError, cv2.error) as exc:
            print(f"[RawData] Cannot save {filename}: {exc}")
            return None
        return path

    def process_shot(self, port_id, frame, bullet_point, received_at=None, raw_image_save=None):
        """Public entry point for scoring one pedestal image and impact."""
        if not (1 <= port_id <= len(self.client_widgets)):
            logging.getLogger("mbt03_server").warning("[ShotReceipt] Bệ %s: loại ảnh vì bệ không hợp lệ", port_id)
            return False
        session_id = (self._active_review_session_id if self.testing
                      else self._previous_review_session_id)
        if session_id is None or self._shooting_session is None:
            logging.getLogger("mbt03_server").info("[ShotReceipt] Bệ %s: không đếm ảnh vì chưa có bài bắn", port_id)
            return False
        received_at = time.monotonic() if received_at is None else received_at
        if not self._shooting_session.accepts_receipt(received_at):
            logging.getLogger("mbt03_server").info(
                "[ShotReceipt] session=%s | Bệ %s | không đếm ảnh: thời điểm nhận %.3fs ngoài bài; mốc dừng %.3fs",
                session_id, port_id, received_at - self._shooting_session.started_at,
                (self._shooting_session.stopped_at if self._shooting_session.stopped_at is not None
                 else self._shooting_session.deadline) - self._shooting_session.started_at,
            )
            if self.testing and self._shooting_session.expired(received_at):
                self.stop_test()
            return False
        exposure = self._shooting_session.active_target(received_at)
        self._shot_sound.play()
        shot_number = self._next_review_shot_number(session_id, port_id)
        logging.getLogger("mbt03_server").info(
            "[ShotReceipt] session=%s | Bệ %s | Phát %s | đã nhận để chấm lúc %.3fs | received_at=%.6f | ui_delay_ms=%.0f",
            session_id, port_id, shot_number, received_at - self._shooting_session.started_at,
            received_at, (time.monotonic() - received_at) * 1000,
        )
        self._scoring_pool.submit(
            self._score_shot_worker,
            session_id,
            shot_number,
            port_id,
            frame.copy(),
            (float(bullet_point[0]), float(bullet_point[1])),
            raw_image_save,
            received_at,
            exposure,
        )
        return True

    def _next_review_shot_number(self, session_id, port_id):
        counter_key = (session_id, port_id)
        shot_number = self._review_shot_counters.get(counter_key, 0) + 1
        self._review_shot_counters[counter_key] = shot_number
        return shot_number

    def process_q0_calibration(self, port_id, frame):
        """Calculate the class-1 reference center on a captured camera frame."""
        if not (1 <= port_id <= len(self.client_widgets)):
            return False
        self._scoring_pool.submit(self._q0_worker, port_id, frame.copy())
        return True

    def _get_scoring_session(self):
        session = getattr(self._scoring_local, "session", None)
        if session is not None:
            return session
        model_path = os.path.normpath(
            os.path.join(
                cf.DATA_DIR,
                cf.config_str(
                    "scoring.model_file", "assets/models/weights.onnx"
                ),
            )
        )
        session = scoring.create_session(
            model_path,
            intra_op_threads=cf.config_int(
                "runtime.onnx_intra_op_threads", 1, minimum=1, maximum=16
            ),
        )
        self._scoring_local.session = session
        return session

    def _score_shot_worker(self, session_id, shot_number, port_id, frame, bullet_point,
                           raw_image_save, received_at, exposure):
        try:
            _, metadata = scoring.scoring(
                frame,
                bullet_point,
                self._reference_images,
                self._get_scoring_session(),
            )
            self.scoring_done_signal.emit({
                "ok": True,
                "session_id": session_id,
                "shot_number": shot_number,
                "port_id": port_id,
                "metadata": metadata,
                "bullet_point": bullet_point,
                "frame": frame,
                "raw_image_save": raw_image_save,
                "received_at": received_at,
                "exposure": exposure,
            })
        except Exception as exc:
            self.scoring_done_signal.emit({
                "ok": False,
                "session_id": session_id,
                "shot_number": shot_number,
                "port_id": port_id,
                "error": str(exc),
                "bullet_point": bullet_point,
                "frame": frame,
                "raw_image_save": raw_image_save,
                "received_at": received_at,
                "exposure": exposure,
            })

    def _q0_worker(self, port_id, frame):
        try:
            reference = self._reference_images.get(scoring.Q0_TARGET_CLASS_ID)
            if reference is None:
                raise RuntimeError(
                    "Khong doc duoc anh mau bia "
                    f"class {scoring.Q0_TARGET_CLASS_ID}"
                )
            result = scoring.calculate_q0(
                frame,
                reference,
                self._get_scoring_session(),
            )
            result.update(port_id=port_id, frame=frame)
            self.q0_done_signal.emit(result)
        except Exception as exc:
            self.q0_done_signal.emit({
                "ok": False,
                "port_id": port_id,
                "status": str(exc),
                "frame": frame,
            })

    def _on_scoring_done(self, result):
        # Validate the receipt time, not the (possibly much later) inference time.
        # Exposure objects retain early closure times for jobs already queued.
        metadata = result.get("metadata")
        if result.get("ok") and metadata is not None:
            hit_on_image = metadata.get("hit")
            exposure = result.get("exposure")
            received_at = result.get("received_at")
            current_id = (self._active_review_session_id if self.testing
                          else self._previous_review_session_id)
            session = (getattr(self, "_shooting_session", None)
                       if result.get("session_id") == current_id else None)
            if session is not None and received_at is not None:
                # Serial confirmation may have corrected the window while scoring.
                exposure = session.active_target(received_at, metadata.get("class_id"))
            eligible = (
                exposure is not None and received_at is not None
                and exposure.contains(received_at)
                and metadata.get("class_id") == exposure.class_id
            )
            metadata = dict(metadata, scoring_eligible=eligible, hit_on_image=hit_on_image)
            result = dict(result, metadata=metadata)
            if not eligible:
                metadata["hit"] = False
                if received_at is None:
                    metadata["status"] = "Không tính trúng: thiếu thời điểm PC nhận ảnh"
                elif exposure is None or not exposure.contains(received_at):
                    metadata["status"] = (
                        "Không tính trúng: ảnh nhận ngoài thời gian cho phép tính điểm của bia"
                    )
                else:
                    detected_name = scoring.CLASS_NAMES.get(metadata.get("class_id"), "không rõ bia")
                    expected_name = scoring.CLASS_NAMES.get(exposure.class_id, "không rõ bia")
                    metadata["status"] = (
                        "Không tính trúng: nhận diện khác bia được phép tính điểm"
                        f" (nhận diện: {detected_name}; được phép: {expected_name})"
                    )
                if session is not None and received_at is not None:
                    metadata["status"] += (
                        f" · PC nhận ảnh lúc {received_at - session.started_at:.3f}s tính từ đầu bài"
                    )
                    target_window = session.window_for_target(metadata.get("class_id"))
                    if target_window is not None:
                        metadata["status"] += (
                            " · Thời gian cho phép của bia nhận diện: từ "
                            f"{target_window.opened_at - session.started_at:.3f}s"
                            f" đến trước {target_window.closed_at - session.started_at:.3f}s"
                        )
                        if received_at < target_window.opened_at:
                            metadata["status"] += (
                                f" · Sớm {target_window.opened_at - received_at:.3f}s so với mốc mở"
                            )
                        elif received_at >= target_window.closed_at:
                            metadata["status"] += (
                                f" · Muộn {received_at - target_window.closed_at:.3f}s so với mốc đóng"
                            )
            logging.getLogger("mbt03_server").info(
                "[Scoring] session=%s | Bệ %s | Phát %s | class=%s | "
                "Trúng trên ảnh=%s | Tính trúng=%s | %s",
                result.get("session_id"), result.get("port_id"), result.get("shot_number"),
                metadata.get("class_id"), hit_on_image, metadata.get("hit"),
                metadata.get("status"),
            )
        self._store_review_shot(result)
        if not result.get("ok"):
            print(f"[Main] Cham bia loi tai be {result.get('port_id')}: {result.get('error')}")
            logging.getLogger("mbt03_server").warning(
                "[Scoring] session=%s | Bệ %s | Phát %s | lỗi chấm: %s",
                result.get("session_id"), result.get("port_id"), result.get("shot_number"), result.get("error"),
            )
        session_id = (self._active_review_session_id if self.testing
                      else self._previous_review_session_id)
        if session_id is None or result.get("session_id") != session_id:
            return
        port_id = result["port_id"]
        if not (1 <= port_id <= len(self.client_widgets)):
            return
        roster = getattr(self, "_roster", None)
        if roster is not None and not roster.matches_session(session_id, port_id):
            return
        if not result.get("ok"):
            # A received shot still consumes ammunition if inference fails.
            # Keep the error in review without inventing an impact or a hit.
            self.client_widgets[port_id - 1].record_miss()
            return
        metadata = result["metadata"]
        class_id = metadata.get("class_id")
        if class_id is None:
            self.client_widgets[port_id - 1].record_miss()
            print(f"[Main] Be {port_id}: khong phat hien bia")
            return

        # scoring() maps the impact into reference-image pixels.  ClientWidget
        # stores normalized reference coordinates for target simulation.
        mapped = metadata.get("transformed_point")
        reference = self._reference_images.get(class_id)
        has_point = mapped is not None and reference is not None and np.all(np.isfinite(mapped))
        show_marker = (has_point and (metadata.get("scoring_eligible") is not False
                       or cf.config_bool("shooting.show_rejected_shots_on_target", False)))
        x_ratio, y_ratio = 0.0, 0.0
        if has_point:
            ref_h, ref_w = reference.shape[:2]
            x_ratio, y_ratio = mapped[0] / ref_w, mapped[1] / ref_h
        hit = metadata.get("hit") is True
        # Marker visibility must never change ammunition, score or hit feedback.
        self.client_widgets[port_id - 1].record_shot(
            class_id, x_ratio, y_ratio, hit, show_marker=bool(show_marker))
        if hit and (len(self.client_widgets) > 1 or not self.automatic_close_target_enabled):
            self._hit_sound.announce(port_id, class_id)
        self._maybe_close_hit_target(class_id, hit)
        print(
            f"[Main] Be {port_id}: class={class_id}, "
            f"hit={hit}, status={metadata.get('status')!a}"
        )

    def _store_review_shot(self, result):
        session_id = result.get("session_id")
        port_id = result.get("port_id")
        session = self._review_sessions.get(session_id)
        if session is None or port_id not in session:
            return

        metadata = result.get("metadata") or {}
        target_index = metadata.get("class_id")
        target_point = None
        target_point_before_offset = None
        mapped = metadata.get("transformed_point")
        mapped_click = metadata.get("transformed_click_point")
        reference = self._reference_images.get(target_index)
        if reference is not None:
            ref_h, ref_w = reference.shape[:2]
            # Preserve out-of-target coordinates so review shows the actual
            # displacement instead of moving a miss onto the image border.
            if mapped is not None:
                target_point = (float(mapped[0]) / ref_w, float(mapped[1]) / ref_h)
            if mapped_click is not None:
                target_point_before_offset = (
                    float(mapped_click[0]) / ref_w, float(mapped_click[1]) / ref_h
                )

        shot = {
            "shot_number": int(result.get("shot_number", 0)),
            "frame": result.get("frame"),
            "raw_image_save": result.get("raw_image_save"),
            "camera_point": result.get("bullet_point"),
            "camera_impact_point": metadata.get("camera_impact_point"),
            "target_index": target_index,
            "target_name": metadata.get("target_name"),
            "target_point": target_point,
            "target_point_before_offset": target_point_before_offset,
            "hit": metadata.get("hit"),
            "scoring_eligible": metadata.get("scoring_eligible"),
            "hit_on_image": metadata.get("hit_on_image"),
            "status": metadata.get("status") or result.get("error"),
            "detections": [
                {
                    "bbox": tuple(detection.get("bbox", (0, 0, 0, 0))),
                    "class_id": detection.get("class_id"),
                    "confidence": float(detection.get("conf", 0.0)),
                    "selected": detection is metadata.get("selected_detection"),
                }
                for detection in metadata.get("detections", [])
            ],
        }
        session[port_id].append(shot)
        session[port_id].sort(key=lambda item: item["shot_number"])
        roster = getattr(self, "_roster", None)
        if roster is not None:
            roster.update_results(session_id)
        if (session_id == self._previous_review_session_id
                and (roster is None or roster.matches_session(session_id, port_id))):
            self.client_widgets[port_id - 1].set_review_available(True)

    def _begin_review_session(self):
        self._review_session_counter += 1
        session_id = self._review_session_counter
        self._review_sessions = {
            session_id: {
                port_id: [] for port_id in range(1, self.p_num + 1)
            }
        }
        self._review_shot_counters = {
            (session_id, port_id): 0
            for port_id in range(1, self.p_num + 1)
        }
        self._active_review_session_id = session_id
        self._previous_review_session_id = None
        for widget in self.client_widgets:
            widget.set_review_available(False)

    def _finish_review_session(self):
        if self._active_review_session_id is None:
            return
        self._previous_review_session_id = self._active_review_session_id
        self._active_review_session_id = None
        session = self._review_sessions.get(self._previous_review_session_id, {})
        for port_id, widget in enumerate(self.client_widgets, start=1):
            widget.set_review_available(bool(session.get(port_id)))

    def open_shot_review(self, port_id):
        if not self._roster.matches_session(self._previous_review_session_id, port_id):
            return
        session = self._review_sessions.get(self._previous_review_session_id, {})
        shots = session.get(port_id, [])
        if not shots:
            return
        dialog = ShotReviewDialog(port_id, shots, self)
        dialog.exec_()

    def _client_positions(self, count):
        if count == 1:
            return [(0, 0)]
        if count == 2:
            return [(0, 0), (0, 1)]
        return [(0, 0), (0, 1), (1, 0), (1, 1)][:count]

    def start_btn_clicked(self):
        if self.testing:
            self.stop_test()
        else:
            self.start_test()

    def start_test(self):
        if self.testing or getattr(self, "_manual_targets_busy", False):
            return
        if self._uart_debug_dialog is not None and self._uart_debug_dialog.has_pending_operations():
            QMessageBox.information(
                self, "Đang xử lý thiết bị",
                "Chờ gửi lệnh hoặc đổi Wi-Fi hoàn tất trước khi bắt đầu bài bắn.",
            )
            return
        if self._roster.loading or self._roster.saving or self._roster.pending():
            return
        self._result_sound.stop()
        self._play_start_announcement()
        self._begin_review_session()
        self._hit_sound.reset()
        self._auto_closed_target_classes.clear()
        self.testing = True
        self._roster.begin_session(self._active_review_session_id)
        self._test_start_time = time.monotonic()
        self._shooting_session = ShootingSession(
            self._test_start_time, tuple(item[0] for item in self.LORA_SCRIPT)
        )
        logging.getLogger("mbt03_server").info(
            "[Exercise] session=%s | bắt đầu | %s bệ | giới hạn %ss",
            self._active_review_session_id, self.p_num, MAX_DURATION_SECONDS,
        )
        self._test_timeout_timer.start(MAX_DURATION_SECONDS * 1000)
        self.setting_btn.setEnabled(False)
        self._update_manual_target_buttons()
        self._send_start_uart_command()
        self._schedule_lora_script()
        self._set_start_button_active(True)
        self.update_app()
        for widget in self.client_widgets:
            widget.start_test()
        self._update_score_speak_buttons()

    def _update_manual_target_buttons(self):
        enabled = not self.testing and not self._manual_targets_busy and not self._closing
        self.close_target_btn.setEnabled(enabled)
        self.open_target_btn.setEnabled(enabled)

    def _send_manual_target_sequence(self, commands):
        if self.testing or self._manual_targets_busy or self._closing:
            return
        self._manual_targets_busy = True
        self._update_manual_target_buttons()
        self.setting_btn.setEnabled(False)
        self._roster.refresh_controls()
        if not self.lora.send_sequence(commands):
            self._on_manual_targets_finished()

    def _close_targets_manually(self):
        self._send_manual_target_sequence(("@661#",))

    def _open_targets_manually(self):
        self._send_manual_target_sequence(self.MANUAL_OPEN_TARGET_COMMANDS)

    def _on_manual_targets_finished(self):
        if self._closing:
            return
        self._manual_targets_busy = False
        self._update_manual_target_buttons()
        self.setting_btn.setEnabled(not self.testing)
        self._roster.refresh_controls()

    def _send_start_uart_command(self):
        for server in self.servers:
            server.send_uart_command(self.START_UART_COMMAND)
        self._start_followup_timer.start(300)

    def _send_start_followup_command(self):
        if not self.testing or self._closing:
            return
        for server in self.servers:
            server.send_uart_command("0A000\n")

    def _maybe_close_hit_target(self, class_id, hit):
        if not self.testing or not self.automatic_close_target_enabled or not hit:
            return False
        command_info = self.AUTO_CLOSE_TARGET_COMMANDS.get(class_id)
        if command_info is None or class_id in self._auto_closed_target_classes:
            return False
        if not self._shooting_session.close_target(class_id, time.monotonic()):
            return False
        command, description = command_info
        self._auto_closed_target_classes.add(class_id)
        print(f"[LoRa] Gui {command}: {description}")
        self.lora.send_command(command)
        return True

    def stop_test(self):
        if not self.testing:
            return
        session_id = self._active_review_session_id
        for widget in self.client_widgets:
            received = self._review_shot_counters.get((session_id, widget.id), 0)
            completed = len(self._review_sessions.get(session_id, {}).get(widget.id, []))
            logging.getLogger("mbt03_server").info(
                "[Exercise] session=%s | Bệ %s | dừng bài: nhận=%s, chấm xong=%s, đang chờ=%s, đạn hiển thị=%s",
                session_id, widget.id, received, completed, received - completed, widget.bullet_count,
            )
        self._shooting_session.stop(time.monotonic())
        self.testing = False
        self._test_timeout_timer.stop()
        self._update_manual_target_buttons()
        self._start_followup_timer.stop()
        for server in self.servers:
            server.send_uart_command("0S000\n")
        self.setting_btn.setEnabled(True)
        self._finish_review_session()
        self._cancel_lora_script()
        self._set_start_button_active(False)
        self.start_btn.setText(self._start_button_text)
        for widget in self.client_widgets:
            widget.stop_test()
        self._roster.update_results(self._previous_review_session_id)
        self._update_score_speak_buttons()

    def update_app(self):
        if not self.testing:
            return

        elapsed = int(time.monotonic() - self._test_start_time)
        if elapsed >= MAX_DURATION_SECONDS:
            self.stop_test()
            return
        self.start_btn.setText(f"KẾT THÚC ({elapsed}s)")

    def _set_start_button_active(self, active):
        if hasattr(self.start_btn, "setChecked"):
            self.start_btn.setChecked(active)

    def open_setting_window(self):
        if self.testing:
            return
        self._setting_window = SettingWindow(
            p_num=self.p_num,
            servers=self.servers,
            lora_controller=self.lora,
            parent=self,
        )
        try:
            self.lora.send_command(cf.config_str("calibration.target_raise_command", "@114#"))
            self._setting_window.exec_()
        finally:
            self._setting_window = None
            for server in self.servers:
                server.send_uart_command("0S000\n")
            self.lora.send_command(cf.config_str("calibration.target_lower_command", "@112#"))

    def request_score_speak(self, port_id):
        if self.testing or self._closing or not (1 <= port_id <= len(self.client_widgets)):
            return
        if self._result_sound.port_id == port_id:
            self._result_sound.stop()
            return
        if self._result_sound.port_id is not None:
            return
        self._hit_sound.stop()
        self._shot_sound.stop()
        # Match the wireless project's preparation command for the selected gun.
        if port_id <= len(self.servers):
            self.servers[port_id - 1].send_uart_command("0P000\n")
        self._result_sound.start(port_id, self.client_widgets[port_id - 1]._rank_text())

    def _update_score_speak_buttons(self):
        active = self._result_sound.port_id
        for widget in self.client_widgets:
            state = "testing" if self.testing else (
                "idle" if active is None else "speaking" if widget.id == active else "disabled"
            )
            widget.set_score_speak_ui_state(state)

    def _play_start_announcement(self):
        """Reserved for the future 'Bat dau tap ban AK bai 2' audio file."""
        return

    def _schedule_lora_script(self):
        self._cancel_lora_script()
        for class_id, (seconds, command, description) in zip(TARGET_CLASS_SEQUENCE, self.LORA_SCRIPT):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setTimerType(Qt.PreciseTimer)
            timer.timeout.connect(
                lambda cmd=command, desc=description, target=class_id:
                    self._send_lora_script_command(cmd, desc, target)
            )
            timer.start(int(round(seconds * 1000)))
            self._lora_schedule_timers.append(timer)

    def _cancel_lora_script(self):
        for timer in self._lora_schedule_timers:
            timer.stop()
            timer.deleteLater()
        self._lora_schedule_timers.clear()

    def _send_lora_script_command(self, command, description, class_id):
        if not self.testing:
            return
        now = time.monotonic()
        if self._shooting_session.expired(now):
            self.stop_test()
            return
        if not self._shooting_session.open_target(class_id, now):
            return
        print(f"[LoRa] Gui {command}: {description}")
        self.lora.send_command(command)

    def _on_lora_connection_changed(self, connected, message):
        state = "da ket noi" if connected else "chua ket noi"
        print(f"[LoRa] {state}: {message}")

    def _on_lora_command_finished(self, command, success, attempts):
        if command == "@661#":
            if success:
                print(f"[LoRa] {command} da gui 1 lan; lenh khong co phan hoi")
            else:
                print(f"[LoRa] {command} gui that bai sau {attempts} lan thu")
        elif success:
            print(f"[LoRa] {command} da duoc xac nhan sau {attempts} lan gui")
        else:
            print(f"[LoRa] {command} khong co phan hoi hop le sau {attempts} lan gui")

    def _on_lora_command_sent(self, command, queued_at, sent_at):
        session = self._shooting_session
        if session is None or not session.accepts_receipt(queued_at) or self._closing:
            return
        for class_id, (_, raise_command, _) in zip(TARGET_CLASS_SEQUENCE, self.LORA_SCRIPT):
            if command == raise_command:
                session.confirm_command_sent(class_id, sent_at, raised=True)
                return
        for class_id, (close_command, _) in self.AUTO_CLOSE_TARGET_COMMANDS.items():
            if command == close_command:
                session.confirm_command_sent(class_id, sent_at, raised=False)
                return

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        self._closing = True
        self._roster.shutdown()
        self.stop_test()
        if self._uart_debug_dialog is not None:
            self._uart_debug_dialog.shutdown()
        self._test_timeout_timer.stop()
        self._shot_sound.stop()
        self._hit_sound.stop()
        self._result_sound.stop()
        self._start_followup_timer.stop()
        for widget, server in zip(self.client_widgets, self.servers):
            if widget.locating:
                if server.is_connected:
                    server.send_uart_command("0LG00\n")
                widget.set_locating(False)
        for server in self.servers:
            try:
                server.stop()
            except Exception:
                pass
        if self.hub_registrar is not None:
            self.hub_registrar.close()
        self._cancel_lora_script()
        self.lora.close()
        if self._raw_image_pool is not None:
            self._raw_image_pool.shutdown(wait=True)
        self._scoring_pool.shutdown(wait=False, cancel_futures=True)
        event.accept()
