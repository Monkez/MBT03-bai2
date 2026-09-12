import random
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import cv2
import numpy as np
from PyQt5 import QtGui, uic
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QMainWindow

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
                delay_seconds = max(0.0, float(item.get("delay_seconds", 0)))
            except (TypeError, ValueError):
                continue
            script.append(
                (
                    delay_seconds,
                    command,
                    str(item.get("description") or command),
                )
            )
    return tuple(script)


class MainWindow(QMainWindow):
    scoring_done_signal = pyqtSignal(object)
    q0_done_signal = pyqtSignal(object)
    START_UART_COMMAND = cf.config_str(
        "shooting.start_uart_command", "0Q000\n"
    )
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
        self.client_widgets = []
        self._start_button_text = self.start_btn.text()
        self._test_start_time = 0.0
        self._lora_schedule_timers = []
        self._closing = False
        self.servers = []
        self.hub_registrar = None
        self._ping_data = {}
        self._battery_data = {}
        self._confirmed_ports = set()
        self._q0_calibrated = {}
        self._setting_window = None
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

        self._configure_main_ui()
        self._create_client_widgets()
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

    def _create_client_widgets(self):
        positions = self._client_positions(self.p_num)
        target_layout_mode = "two_pedestals" if self.p_num == 2 else "default"
        for index in range(self.p_num):
            widget = ClientWidget(index + 1, self, target_layout_mode=target_layout_mode)
            widget.score_speak_requested.connect(self.request_score_speak)
            widget.review_requested.connect(self.open_shot_review)
            self.client_widgets.append(widget)
            row, col = positions[index]
            self.client_grid_layout.addWidget(widget, row, col)

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
                server.start()
                self.servers.append(server)
            self._update_hub_availability()
        except Exception as exc:
            print(f"[Main] Khong khoi dong duoc ket noi client: {exc}")

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
        self._queue_raw_camera_image(port_id, frame)
        if self._setting_window is not None and self._setting_window.Q0:
            return
        q0 = (q0_data or {}).get("q0", [0.5, 0.5])
        try:
            bullet_point = (float(q0[0]), float(q0[1]))
        except (TypeError, ValueError, IndexError):
            bullet_point = (0.5, 0.5)
        self.process_shot(port_id, frame, bullet_point)

    def _queue_raw_camera_image(self, port_id, frame):
        """Snapshot an untouched shoot frame and queue a lossless PNG write."""
        if not self._save_raw_data_enabled or self._raw_image_pool is None:
            return False
        if frame is None or not hasattr(frame, "copy"):
            return False
        captured_at = datetime.now()
        try:
            self._raw_image_pool.submit(
                self._save_raw_camera_image,
                self._raw_data_dir,
                port_id,
                frame.copy(),
                captured_at,
            )
        except RuntimeError as exc:
            print(f"[RawData] Cannot queue image from pedestal {port_id}: {exc}")
            return False
        return True

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

    def process_shot(self, port_id, frame, bullet_point):
        """Public entry point for scoring one pedestal image and impact."""
        if not self.testing or not (1 <= port_id <= len(self.client_widgets)):
            return False
        session_id = self._active_review_session_id
        if session_id is None:
            return False
        shot_number = self._next_review_shot_number(session_id, port_id)
        self._scoring_pool.submit(
            self._score_shot_worker,
            session_id,
            shot_number,
            port_id,
            frame.copy(),
            (float(bullet_point[0]), float(bullet_point[1])),
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

    def _score_shot_worker(self, session_id, shot_number, port_id, frame, bullet_point):
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
        self._store_review_shot(result)
        if not result.get("ok"):
            print(f"[Main] Cham bia loi tai be {result.get('port_id')}: {result.get('error')}")
            return
        if (
            not self.testing
            or result.get("session_id") != self._active_review_session_id
        ):
            return
        port_id = result["port_id"]
        if not (1 <= port_id <= len(self.client_widgets)):
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
        if mapped is not None and reference is not None:
            ref_h, ref_w = reference.shape[:2]
            x_ratio = mapped[0] / ref_w
            y_ratio = mapped[1] / ref_h
        else:
            x_ratio, y_ratio = 0.5, 0.5
        hit = metadata.get("hit") is True
        self.client_widgets[port_id - 1].record_shot(
            class_id,
            x_ratio,
            y_ratio,
            hit,
        )
        self._maybe_close_hit_target(class_id, hit)
        print(
            f"[Main] Be {port_id}: class={class_id}, "
            f"hit={hit}, status={metadata.get('status')}"
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
        mapped = metadata.get("transformed_point")
        reference = self._reference_images.get(target_index)
        if mapped is not None and reference is not None:
            ref_h, ref_w = reference.shape[:2]
            target_point = (
                max(0.0, min(1.0, float(mapped[0]) / ref_w)),
                max(0.0, min(1.0, float(mapped[1]) / ref_h)),
            )

        shot = {
            "shot_number": int(result.get("shot_number", 0)),
            "frame": result.get("frame"),
            "camera_point": result.get("bullet_point"),
            "target_index": target_index,
            "target_name": metadata.get("target_name"),
            "target_point": target_point,
            "hit": metadata.get("hit"),
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
        if session_id == self._previous_review_session_id:
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
        self._play_start_announcement()
        self._begin_review_session()
        self._auto_closed_target_classes.clear()
        self.testing = True
        self._test_start_time = time.monotonic()
        self._send_start_uart_command()
        self._schedule_lora_script()
        self._set_start_button_active(True)
        self.update_app()
        for widget in self.client_widgets:
            widget.start_test()

    def _send_start_uart_command(self):
        for server in self.servers:
            server.send_uart_command(self.START_UART_COMMAND)

    def _maybe_close_hit_target(self, class_id, hit):
        if not self.testing or not self.automatic_close_target_enabled or not hit:
            return False
        command_info = self.AUTO_CLOSE_TARGET_COMMANDS.get(class_id)
        if command_info is None or class_id in self._auto_closed_target_classes:
            return False
        command, description = command_info
        self._auto_closed_target_classes.add(class_id)
        print(f"[LoRa] Gui {command}: {description}")
        self.lora.send_command(command)
        return True

    def stop_test(self):
        self.testing = False
        self._finish_review_session()
        self._cancel_lora_script()
        self._set_start_button_active(False)
        self.start_btn.setText(self._start_button_text)
        for widget in self.client_widgets:
            widget.stop_test()

    def update_app(self):
        if not self.testing:
            return

        elapsed = int(time.monotonic() - self._test_start_time)
        self.start_btn.setText(f"KẾT THÚC ({elapsed}s)")

    def _set_start_button_active(self, active):
        if hasattr(self.start_btn, "setChecked"):
            self.start_btn.setChecked(active)

    def open_setting_window(self):
        self._setting_window = SettingWindow(
            p_num=self.p_num,
            servers=self.servers,
            lora_controller=self.lora,
            parent=self,
        )
        self._setting_window.exec_()
        self._setting_window = None

    def request_score_speak(self, port_id):
        return

    def _play_start_announcement(self):
        """Reserved for the future 'Bat dau tap ban AK bai 2' audio file."""
        return

    def _schedule_lora_script(self):
        self._cancel_lora_script()
        for seconds, command, description in self.LORA_SCRIPT:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setTimerType(Qt.PreciseTimer)
            timer.timeout.connect(
                lambda cmd=command, desc=description: self._send_lora_script_command(cmd, desc)
            )
            timer.start(int(round(seconds * 1000)))
            self._lora_schedule_timers.append(timer)

    def _cancel_lora_script(self):
        for timer in self._lora_schedule_timers:
            timer.stop()
            timer.deleteLater()
        self._lora_schedule_timers.clear()

    def _send_lora_script_command(self, command, description):
        if not self.testing:
            return
        print(f"[LoRa] Gui {command}: {description}")
        self.lora.send_command(command)

    def _on_lora_connection_changed(self, connected, message):
        state = "da ket noi" if connected else "chua ket noi"
        print(f"[LoRa] {state}: {message}")

    def _on_lora_command_finished(self, command, success, attempts):
        if success:
            print(f"[LoRa] {command} da duoc xac nhan sau {attempts} lan gui")
        else:
            print(f"[LoRa] {command} khong co phan hoi hop le sau {attempts} lan gui")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_D and self.client_widgets:
            widget = self.client_widgets[0]
            target = random.randrange(4)
            widget.record_shot(target, random.uniform(0.25, 0.75), random.uniform(0.25, 0.75), True)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        self._closing = True
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
