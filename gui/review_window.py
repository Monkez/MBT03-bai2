import json
import os

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QImage, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QPlainTextEdit,
    QScrollArea,
    QWidget,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QVBoxLayout,
)

import config as cf
import scoring
from gui.shot_groups import burst_groups


SHOW_CAMERA_AIM_POINT = cf.config_bool("review.show_camera_aim_point", True)
SHOW_CAMERA_IMPACT_POINT = cf.config_bool("review.show_camera_impact_point", True)
SHOW_SIMULATION_AIM_POINT = cf.config_bool("review.show_simulation_aim_point", False)
SHOW_SIMULATION_IMPACT_POINT = cf.config_bool("review.show_simulation_impact_point", True)
REVIEW_CAMERA_ZOOM = cf.config_float(
    "review.camera_zoom", 1.5, minimum=1.0, maximum=5.0
)
SIMULATION_MARKER_SCALE = cf.config_float(
    "review.simulation_marker_scale", 1.45, minimum=0.5, maximum=5.0
)
SELECTED_BOX_THICKNESS = cf.config_int(
    "review.selected_box_thickness", 2, minimum=1, maximum=10
)
OTHER_BOX_THICKNESS = cf.config_int(
    "review.other_box_thickness", 1, minimum=1, maximum=10
)


def draw_impact_marker(image, point, color=(0, 0, 255), scale_factor=1.0):
    """Draw a simple cross at the impact point."""
    if image is None or point is None:
        return
    height, width = image.shape[:2]
    if not np.all(np.isfinite(point)):
        return
    x, y = int(round(point[0])), int(round(point[1]))
    if not (0 <= x < width and 0 <= y < height):
        return
    base = max(height, width)
    scale_factor = max(0.5, float(scale_factor))
    size = max(18, int(round(base * 0.04 * scale_factor)))
    thickness = max(6, int(round(base * 0.008 * scale_factor)))
    cv2.drawMarker(image, (x, y), color, cv2.MARKER_CROSS, size, thickness)


def marker_legend(show_aim, show_impact):
    labels = []
    if show_aim:
        labels.append('<span style="color:#0000ff">+ Điểm ngắm (Trước offset)</span>')
    if show_impact:
        labels.append('<span style="color:#b91c1c">+ Điểm chạm (Sau offset)</span>')
    return " &nbsp; · &nbsp; ".join(labels) or "Đã ẩn các dấu điểm theo config"


class AspectImageLabel(QLabel):
    def __init__(self, placeholder, parent=None):
        super().__init__(placeholder, parent)
        self._source_pixmap = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(280, 240)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setStyleSheet(
            "QLabel {"
            "background: #111827;"
            "color: #94a3b8;"
            "border: 1px solid #334155;"
            "border-radius: 10px;"
            "font-size: 14px;"
            "}"
        )

    def set_bgr_image(self, image):
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            self._source_pixmap = None
            self.setPixmap(QPixmap())
            return
        if image.ndim == 2:
            rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        qimage = QImage(
            rgb.data,
            width,
            height,
            rgb.strides[0],
            QImage.Format_RGB888,
        ).copy()
        self._source_pixmap = QPixmap.fromImage(qimage)
        self._update_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if self._source_pixmap is None:
            return
        self.setPixmap(
            self._source_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )


class ShotReviewDialog(QDialog):
    def __init__(self, pedestal_id, shots, parent=None, *, max_bullets=None, fired_count=None, receipt_info=None):
        super().__init__(parent)
        self.pedestal_id = pedestal_id
        self._shot_source = shots
        self.shots = sorted(shots, key=lambda shot: shot.get("shot_number", 0))
        self._max_bullets = max_bullets if max_bullets is not None else cf.max_bullets()
        self._fired_count = fired_count or 0
        self._receipt_info = dict(receipt_info or {})
        self._history_signature = tuple(id(shot) for shot in self.shots)
        self.round_buttons = {}
        self.current_index = 0
        self._reference_images = self._load_reference_images()

        self.setFont(QFont("Segoe UI", 10))
        self.setWindowTitle(f"Xem lại phát bắn - Bệ {pedestal_id}")
        self.setMinimumSize(920, 600)
        self.resize(1180, 740)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build_ui()
        self._raw_file_timer = QTimer(self)
        self._raw_file_timer.setInterval(250)
        self._raw_file_timer.timeout.connect(self._update_raw_file_label)
        self.finished.connect(self._raw_file_timer.stop)
        self._history_timer = QTimer(self)
        self._history_timer.setInterval(200)
        self._history_timer.timeout.connect(self._refresh_history)
        self.finished.connect(self._history_timer.stop)
        self.finished.connect(self.log_dialog.close)
        self._bind_shortcuts()
        self._show_current_shot()

    def _build_ui(self):
        self.setStyleSheet(
            "QDialog { background: #f8fafc; }"
            "QLabel { background: transparent; color: #334155; }"
            "QLabel#dialogTitle { color: #0f172a; font-size: 20px; font-weight: 700; }"
            "QLabel#panelTitle { color: #f1f5f9; font-size: 13px; font-weight: 600; }"
            "QComboBox { background: white; border: 1px solid #cbd5e1; border-radius: 6px; min-height: 32px; padding: 0 8px; }"
            "QPushButton { min-height: 36px; padding: 0 16px; border-radius: 7px;"
            "background: white; color: #1e293b; border: 1px solid #cbd5e1; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #eef2f7; }"
            "QPushButton:focus { border: 2px solid #2563eb; }"
            "QPushButton:disabled { color: #94a3b8; background: #f1f5f9; }"
            "QPushButton#closeButton { border: 1px solid #2563eb; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel(f"Xem lại phát bắn · Bệ {self.pedestal_id}")
        title.setObjectName("dialogTitle")
        self.log_btn = QPushButton("Xem log")
        self.log_btn.clicked.connect(self.open_log)
        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("closeButton")
        close_btn.setToolTip("Đóng cửa sổ (Esc)")
        close_btn.clicked.connect(self.accept)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.log_btn)
        header.addWidget(close_btn)
        root.addLayout(header)
        self._build_log_dialog()

        panels = QHBoxLayout()
        panels.setSpacing(12)
        self.camera_view = self._create_panel(
            panels, "Điểm ngắm người tập", "Không có ảnh camera",
            f"Zoom {REVIEW_CAMERA_ZOOM:g}× · Khung vàng: bia được chọn · Khung xanh: bia khác<br>"
            + marker_legend(SHOW_CAMERA_AIM_POINT, SHOW_CAMERA_IMPACT_POINT))
        self.simulation_view = self._create_panel(
            panels, "Điểm chạm trên bia", "Không có ảnh mô phỏng",
            marker_legend(SHOW_SIMULATION_AIM_POINT, SHOW_SIMULATION_IMPACT_POINT))
        root.addLayout(panels, 1)

        self.ammo_scroll = QScrollArea()
        self.ammo_scroll.setWidgetResizable(True)
        self.ammo_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ammo_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ammo_scroll.setFixedHeight(72)
        self.ammo_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.ammo_content = QWidget()
        self.ammo_content.setStyleSheet("background: transparent;")
        self.ammo_layout = QHBoxLayout(self.ammo_content)
        self.ammo_layout.setContentsMargins(6, 4, 6, 4)
        self.ammo_layout.setSpacing(14)
        self.ammo_scroll.setWidget(self.ammo_content)
        root.addWidget(self.ammo_scroll)
        self._rebuild_round_strip()

        controls = QHBoxLayout()
        controls.setSpacing(16)
        self.previous_btn = QPushButton("◀  Phát trước")
        self.previous_btn.setToolTip("Phát trước (←)")
        self.next_btn = QPushButton("Phát sau  ▶")
        self.next_btn.setToolTip("Phát sau (→)")
        self.counter_label = QLabel()
        self.counter_label.setAlignment(Qt.AlignCenter)
        self.counter_label.setMinimumWidth(76)
        self.counter_label.setStyleSheet("font-size: 16px; font-weight: 600; background: transparent;")
        self.previous_btn.clicked.connect(self.show_previous)
        self.next_btn.clicked.connect(self.show_next)
        controls.addStretch()
        controls.addWidget(self.previous_btn)
        controls.addWidget(self.counter_label)
        controls.addWidget(self.next_btn)
        controls.addStretch()
        root.addLayout(controls)
        for button in (self.previous_btn, self.next_btn, self.log_btn, close_btn):
            button.setAutoDefault(False)

    def _build_log_dialog(self):
        self.log_dialog = QDialog(self)
        self.log_dialog.setWindowTitle(f"Log phát bắn · Bệ {self.pedestal_id}")
        self.log_dialog.setWindowFlags(self.log_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.log_dialog.resize(760, 540)
        layout = QVBoxLayout(self.log_dialog)
        self.shot_selector = QComboBox(self.log_dialog)
        self.shot_selector.setAccessibleName("Chọn phát bắn để xem log")
        self.shot_selector.currentIndexChanged.connect(self._set_index)
        layout.addWidget(self.shot_selector)
        self.status_label = QLabel(self.log_dialog)
        self.raw_file_label = QLabel(self.log_dialog)
        self.details_label = QLabel(self.log_dialog)
        for label in (self.status_label, self.raw_file_label, self.details_label):
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            layout.addWidget(label)
        self._log_guides = QVBoxLayout()
        layout.addLayout(self._log_guides)
        self.log_text = QPlainTextEdit(self.log_dialog)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet("background: white; color: #24364b; border: 1px solid #cbd5e1; border-radius: 6px;")
        layout.addWidget(self.log_text, 1)
        close = QPushButton("Đóng log", self.log_dialog)
        close.clicked.connect(self.log_dialog.close)
        layout.addWidget(close, 0, Qt.AlignRight)
        self._populate_selector()

    def _populate_selector(self):
        self.shot_selector.blockSignals(True)
        self.shot_selector.clear()
        for shot in self.shots:
            result = ("Không tính điểm" if shot.get("scoring_eligible") is False else
                      "Trúng" if shot.get("hit") is True else "Trượt" if shot.get("hit") is False else "Chưa xác định")
            self.shot_selector.addItem(f"Phát {shot.get('shot_number', 0)} · {shot.get('target_name') or 'Không rõ bia'} · {result}")
        self.shot_selector.setEnabled(bool(self.shots))
        self.shot_selector.blockSignals(False)

    def _create_panel(self, panels, title_text, placeholder, legend):
        frame = QFrame()
        frame.setObjectName("reviewPanel")
        frame.setStyleSheet("QFrame#reviewPanel { background: #272c36; border: 1px solid #303744; border-radius: 10px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        title = QLabel(title_text)
        title.setObjectName("panelTitle")
        view = AspectImageLabel(placeholder)
        layout.addWidget(title)
        layout.addWidget(view, 1)
        panels.addWidget(frame, 1)
        # Technical legends belong to the detailed log, not the image deck.
        caption = QLabel(legend, self.log_dialog)
        caption.setWordWrap(True)
        self._log_guides.addWidget(caption)
        return view

    def _rebuild_round_strip(self):
        while self.ammo_layout.count():
            item = self.ammo_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.round_buttons = {}
        self._shot_indices = {int(shot.get("shot_number", index + 1)): index
                              for index, shot in enumerate(self.shots)}
        records = dict(self._receipt_info)
        for index, shot in enumerate(self.shots):
            number = int(shot.get("shot_number", index + 1))
            records[number] = {**shot, **records.get(number, {})}
        self._total_fired = max([self._fired_count, *self._shot_indices.keys(), *records.keys()], default=0)
        capacity = max(self._max_bullets, self._total_fired)
        groups = burst_groups(records, cf.burst_gap_seconds())
        starts = {group[0]: group for group in groups}
        self.ammo_layout.addStretch()
        number = 1
        while number <= capacity:
            grouped = number in starts
            slots = starts[number] if grouped else []
            if not grouped:
                while number <= capacity and number not in starts:
                    slots.append(number)
                    number += 1
            else:
                number = slots[-1] + 1
            frame = QFrame(self.ammo_content)
            frame.setStyleSheet("QFrame { background: transparent; border: "
                                + ("2px solid #eab52c;" if grouped else "2px solid transparent;")
                                + "border-radius: 8px; }")
            frame.setFixedHeight(48)
            row = QHBoxLayout(frame)
            row.setContentsMargins(4, 4, 4, 4)
            row.setSpacing(6)
            for slot in slots:
                button = QPushButton(str(slot), frame)
                button.setFixedSize(36, 36)
                button.setAutoDefault(False)
                button.setEnabled(slot in self._shot_indices)
                button.clicked.connect(lambda _checked=False, n=slot: self._set_index(self._shot_indices[n]))
                self.round_buttons[slot] = button
                row.addWidget(button)
            self.ammo_layout.addWidget(frame, 0, Qt.AlignVCenter)
        self.ammo_layout.addStretch()

    def _update_round_selection(self):
        selected = int(self.shots[self.current_index].get("shot_number", self.current_index + 1)) if self.shots else None
        for number, button in self.round_buttons.items():
            index = self._shot_indices.get(number)
            shot = self.shots[index] if index is not None else None
            hit = shot is not None and shot.get("hit") is True and shot.get("scoring_eligible") is not False
            color = "#1a9b58" if hit else "#df3949" if shot is not None else "#dce1e8"
            text = "#ffffff" if shot is not None else "#687385"
            border = "3px solid #1769ff" if number == selected else "2px solid transparent"
            button.setStyleSheet("QPushButton, QPushButton:disabled, QPushButton:focus {"
                                f"min-height: 0; padding: 0; border-radius: 5px; background: {color}; color: {text};"
                                f"border: {border}; font-size: 13px; font-weight: 600; }}")
            result = "Trúng" if hit else "Trượt / không tính điểm" if shot is not None else (
                "Đang chấm" if number <= self._total_fired else "Chưa bắn")
            button.setToolTip(f"Phát {number} · {result}")
            button.setAccessibleName(f"Phát {number}: {result}" + (" · Đang xem" if number == selected else ""))
        if selected in self.round_buttons:
            self.ammo_scroll.ensureWidgetVisible(self.round_buttons[selected], 40, 0)
        self.log_btn.setEnabled(bool(self.shots))

    def open_log(self):
        self._update_log_text()
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()

    def _update_log_text(self):
        if not self.shots:
            self.log_text.clear()
            return
        shot = self.shots[self.current_index]
        details = {key: value for key, value in shot.items() if key not in ("frame", "raw_image_save")}
        text = json.dumps(details, ensure_ascii=False, indent=2, default=str)
        text += "\n\n" + self.raw_file_label.text()
        if self.raw_file_label.toolTip():
            text += "\n" + self.raw_file_label.toolTip()
        if text != self.log_text.toPlainText():
            position = self.log_text.verticalScrollBar().value()
            self.log_text.setPlainText(text)
            self.log_text.verticalScrollBar().setValue(position)

    def showEvent(self, event):
        super().showEvent(event)
        self._history_timer.start()

    def _refresh_history(self):
        latest = sorted(self._shot_source, key=lambda shot: shot.get("shot_number", 0))
        signature = tuple(id(shot) for shot in latest)
        if signature == self._history_signature:
            return
        selected = self.shots[self.current_index].get("shot_number") if self.shots else None
        self.shots = latest
        self._history_signature = signature
        self.current_index = next((index for index, shot in enumerate(latest) if shot.get("shot_number") == selected), 0)
        self._populate_selector()
        self._rebuild_round_strip()
        self._show_current_shot()

    def _bind_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self.show_previous)
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self.show_next)
        QShortcut(QKeySequence(Qt.Key_Home), self, activated=self.show_first)
        QShortcut(QKeySequence(Qt.Key_End), self, activated=self.show_last)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.reject)

    def show_first(self):
        self._set_index(0)

    def show_previous(self):
        self._set_index(self.current_index - 1)

    def show_next(self):
        self._set_index(self.current_index + 1)

    def show_last(self):
        self._set_index(len(self.shots) - 1)

    def _set_index(self, index):
        if not self.shots:
            return
        bounded = max(0, min(len(self.shots) - 1, int(index)))
        if bounded != self.current_index:
            self.current_index = bounded
            self._show_current_shot()

    def _show_current_shot(self):
        self._update_raw_file_label()
        if not self.shots:
            self.counter_label.setText("0 / 0")
            self.status_label.setText("Chưa có dữ liệu phát bắn")
            self.details_label.setText("")
            for button in (self.previous_btn, self.next_btn):
                button.setEnabled(False)
            self._update_round_selection()
            return

        shot = self.shots[self.current_index]
        self.camera_view.set_bgr_image(self._camera_preview(shot))
        self.simulation_view.set_bgr_image(self._simulation_preview(shot))

        shot_number = shot.get("shot_number", self.current_index + 1)
        target_name = shot.get("target_name") or "Không xác định được bia"
        status = shot.get("status") or "Không có trạng thái"
        hit = shot.get("hit")
        result_text = "TRÚNG" if hit is True else "TRƯỢT" if hit is False else "CHƯA XÁC ĐỊNH"
        if shot.get("scoring_eligible") is False:
            result_text = "KHÔNG TÍNH ĐIỂM"
        self.status_label.setText(
            f"Phát {shot_number} · {target_name} · {result_text}"
        )
        status_color = ("#b91c1c" if shot.get("scoring_eligible") is False else
                        "#166534" if hit is True else "#b91c1c" if hit is False else "#475569")
        self.status_label.setStyleSheet(f"color: {status_color};")
        detection_count = len(shot.get("detections", []))
        before = shot.get("target_point_before_offset") if SHOW_SIMULATION_AIM_POINT else None
        after = shot.get("target_point") if SHOW_SIMULATION_IMPACT_POINT else None
        if not SHOW_SIMULATION_IMPACT_POINT:
            offset_note = "Đã ẩn điểm chạm trên bia theo config."
        elif not SHOW_SIMULATION_AIM_POINT:
            offset_note = ("Chấm điểm tại dấu thập đỏ (sau offset)." if after is not None
                           else "Chưa có điểm sau offset để hiển thị.")
        elif before is None or after is None:
            offset_note = "Chưa đủ dữ liệu để so sánh hai điểm."
        elif np.allclose(before, after, rtol=0, atol=1e-9):
            offset_note = "Offset bằng 0: hai điểm trùng nhau."
        else:
            offset_note = "Chấm điểm tại dấu thập đỏ (sau offset)."
        if any(point is not None and any(value < 0 or value > 1 for value in point)
               for point in (before, after)):
            offset_note += " Điểm ngoài ảnh bia được hiển thị trên vùng nền mở rộng."
        if SHOW_CAMERA_IMPACT_POINT and shot.get("camera_impact_point") is None:
            offset_note += " Chưa đủ dữ liệu suy ngược điểm chạm lên ảnh thật."
        if shot.get("scoring_eligible") is False:
            offset_note += " Điểm hiển thị để đối chiếu; phát này không được tính điểm."
        self.details_label.setText(
            f"{status} · Phát hiện {detection_count} bia. {offset_note}"
        )
        self.counter_label.setText(f"{shot_number} / {self._total_fired}")
        self.shot_selector.blockSignals(True)
        self.shot_selector.setCurrentIndex(self.current_index)
        self.shot_selector.blockSignals(False)

        at_start = self.current_index == 0
        at_end = self.current_index == len(self.shots) - 1
        self.previous_btn.setEnabled(not at_start)
        self.next_btn.setEnabled(not at_end)
        self._update_round_selection()
        self._update_log_text()

    def _update_raw_file_label(self):
        self._raw_file_timer.stop()
        self.raw_file_label.setToolTip("")
        if not self.shots:
            self.raw_file_label.clear()
            return
        save = self.shots[self.current_index].get("raw_image_save")
        if save is None:
            self.raw_file_label.setText("Ảnh gốc: Không lưu file ảnh")
        elif not save.done():
            self.raw_file_label.setText("Ảnh gốc: Đang lưu…")
            self._raw_file_timer.start()
        else:
            try:
                path = save.result()
            except Exception:
                path = None
            if path:
                self.raw_file_label.setText(f"File ảnh gốc: {os.path.basename(path)}")
                self.raw_file_label.setToolTip(path)
            else:
                self.raw_file_label.setText("Ảnh gốc: Lưu file thất bại")

        if self.log_dialog.isVisible():
            self._update_log_text()

    def _camera_preview(self, shot):
        frame = shot.get("frame")
        if frame is None:
            return self._placeholder_image("KHONG CO ANH CAMERA")
        normalized = shot.get("camera_point")
        height, width = frame.shape[:2]
        source_point = ((normalized[0] * width, normalized[1] * height)
                        if normalized is not None and np.all(np.isfinite(normalized))
                        else (width / 2, height / 2))
        preview, transform = self._zoom_around_point(
            frame,
            source_point,
            REVIEW_CAMERA_ZOOM if normalized is not None else 1.0,
        )
        detections = [
            {
                **detection,
                "bbox": self._transform_bbox(detection.get("bbox"), transform),
            }
            for detection in shot.get("detections", [])
        ]
        self._draw_detection_boxes(preview, detections)
        points = []
        for key, enabled in (("camera_point", SHOW_CAMERA_AIM_POINT),
                             ("camera_impact_point", SHOW_CAMERA_IMPACT_POINT)):
            point = shot.get(key) if enabled else None
            points.append(self._transform_point((point[0] * width, point[1] * height), transform)
                          if point is not None and np.all(np.isfinite(point)) else None)
        before, after = points
        coincident = (before is not None and after is not None
                      and np.allclose(before, after, rtol=0, atol=1e-6))
        draw_impact_marker(preview, before, color=(255, 0, 0),
                           scale_factor=1.35 if coincident else 1.0)
        draw_impact_marker(preview, after, color=(0, 0, 255))
        return preview

    @staticmethod
    def _draw_detection_boxes(image, detections):
        height, width = image.shape[:2]
        for detection in detections:
            bbox = detection.get("bbox", (0, 0, 0, 0))
            x1, y1, x2, y2 = (
                max(0, min(width - 1, int(round(value))))
                for value in bbox
            )
            selected = bool(detection.get("selected"))
            color = (0, 255, 255) if selected else (255, 170, 0)
            thickness = (
                SELECTED_BOX_THICKNESS if selected else OTHER_BOX_THICKNESS
            )
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 0), thickness + 2)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)

    @staticmethod
    def _zoom_around_point(image, point, zoom):
        height, width = image.shape[:2]
        zoom = max(1.0, float(zoom))
        crop_width = max(1, min(width, int(round(width / zoom))))
        crop_height = max(1, min(height, int(round(height / zoom))))
        center_x = max(0.0, min(width - 1.0, float(point[0])))
        center_y = max(0.0, min(height - 1.0, float(point[1])))
        left = max(0, min(width - crop_width, int(round(center_x - crop_width / 2))))
        top = max(0, min(height - crop_height, int(round(center_y - crop_height / 2))))
        cropped = image[top:top + crop_height, left:left + crop_width]
        preview = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)
        return preview, (left, top, width / crop_width, height / crop_height)

    @staticmethod
    def _transform_point(point, transform):
        left, top, scale_x, scale_y = transform
        return (
            (float(point[0]) - left) * scale_x,
            (float(point[1]) - top) * scale_y,
        )

    @classmethod
    def _transform_bbox(cls, bbox, transform):
        if bbox is None or len(bbox) != 4:
            return (0, 0, 0, 0)
        x1, y1 = cls._transform_point((bbox[0], bbox[1]), transform)
        x2, y2 = cls._transform_point((bbox[2], bbox[3]), transform)
        return (x1, y1, x2, y2)

    def _simulation_preview(self, shot):
        target_index = shot.get("target_index")
        reference = self._reference_images.get(target_index)
        if reference is None:
            return self._placeholder_image("KHONG PHAT HIEN BIA")

        preview = reference.copy()
        height, width = preview.shape[:2]
        points = []
        for key, enabled in (("target_point_before_offset", SHOW_SIMULATION_AIM_POINT),
                             ("target_point", SHOW_SIMULATION_IMPACT_POINT)):
            normalized = shot.get(key) if enabled else None
            points.append(
                (float(normalized[0]) * width, float(normalized[1]) * height)
                if normalized is not None and np.all(np.isfinite(normalized)) else None
            )
        present = [point for point in points if point is not None]
        # Keep the reference at about 80% of the normal canvas, with white
        # space for nearby misses. Apply the same transform to both markers.
        padding = max(height, width) * .125
        marker_margin = max(height, width) * .07 * SIMULATION_MARKER_SCALE
        left, top, right, bottom = -padding, -padding, width + padding, height + padding
        if present:
            left = min(left, min(point[0] for point in present) - marker_margin)
            top = min(top, min(point[1] for point in present) - marker_margin)
            right = max(right, max(point[0] for point in present) + marker_margin)
            bottom = max(bottom, max(point[1] for point in present) + marker_margin)
        scale = min(1.0, 1600 / max(right - left, bottom - top))
        transform = np.asarray([[scale, 0, -left * scale], [0, scale, -top * scale]])
        preview = cv2.warpAffine(
            preview, transform,
            (int(np.ceil((right - left) * scale)), int(np.ceil((bottom - top) * scale))),
            borderValue=(255, 255, 255),
        )
        points = [((point[0] - left) * scale, (point[1] - top) * scale)
                  if point is not None else None for point in points]
        before, after = points
        if before is not None and after is not None:
            start = tuple(int(round(value)) for value in before)
            end = tuple(int(round(value)) for value in after)
            if start != end:
                cv2.line(
                    preview, start, end, (0, 190, 255),
                    max(2, int(round(max(preview.shape[:2]) * 0.002))),
                    cv2.LINE_AA,
                )
        if before is not None:
            coincident = after is not None and np.allclose(before, after, rtol=0, atol=1e-9)
            draw_impact_marker(
                preview, before, color=(255, 0, 0),
                scale_factor=SIMULATION_MARKER_SCALE * (1.35 if coincident else 1.0),
            )
        if after is not None:
            draw_impact_marker(
                preview,
                after,
                color=(0, 0, 255),
                scale_factor=SIMULATION_MARKER_SCALE,
            )
        return preview

    def _load_reference_images(self):
        images = {}
        for class_id, template in scoring.TARGET_TEMPLATES.items():
            path = os.path.join(cf.DATA_DIR, "assets", "signs", template["file"])
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is not None:
                images[class_id] = image
        return images

    @staticmethod
    def _placeholder_image(text):
        image = np.full((600, 800, 3), (245, 247, 250), dtype=np.uint8)
        size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
        origin = ((image.shape[1] - size[0]) // 2, (image.shape[0] + size[1]) // 2)
        cv2.putText(
            image,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (100, 116, 139),
            2,
            cv2.LINE_AA,
        )
        return image
