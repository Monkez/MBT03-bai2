import os

import cv2
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
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
    """Draw a high-contrast marker that remains visible after scaling."""
    if image is None or point is None:
        return
    height, width = image.shape[:2]
    x = max(0, min(width - 1, int(round(point[0]))))
    y = max(0, min(height - 1, int(round(point[1]))))
    base = max(height, width)
    scale_factor = max(0.5, float(scale_factor))
    size = max(18, int(round(base * 0.055 * scale_factor)))
    thickness = max(2, int(round(base * 0.004 * scale_factor)))
    radius = max(4, size // 7)

    cv2.drawMarker(image, (x, y), (0, 0, 0), cv2.MARKER_CROSS, size, thickness + 4)
    cv2.drawMarker(image, (x, y), (255, 255, 255), cv2.MARKER_CROSS, size, thickness + 2)
    cv2.drawMarker(image, (x, y), color, cv2.MARKER_CROSS, size, thickness)
    cv2.circle(image, (x, y), radius + 4, (0, 0, 0), -1)
    cv2.circle(image, (x, y), radius + 2, (0, 255, 255), -1)
    cv2.circle(image, (x, y), radius, color, -1)
    cv2.circle(image, (x, y), max(1, radius // 3), (255, 255, 255), -1)


class AspectImageLabel(QLabel):
    def __init__(self, placeholder, parent=None):
        super().__init__(placeholder, parent)
        self._source_pixmap = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(420, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
    def __init__(self, pedestal_id, shots, parent=None):
        super().__init__(parent)
        self.pedestal_id = pedestal_id
        self.shots = sorted(shots, key=lambda shot: shot.get("shot_number", 0))
        self.current_index = 0
        self._reference_images = self._load_reference_images()

        self.setWindowTitle(f"Xem lại phát bắn - Bệ {pedestal_id}")
        self.setMinimumSize(1080, 680)
        self.resize(1280, 780)
        self.setModal(True)
        self._build_ui()
        self._bind_shortcuts()
        self._show_current_shot()

    def _build_ui(self):
        self.setStyleSheet(
            "QDialog { background: #f1f5f9; }"
            "QLabel#dialogTitle { color: #0f172a; font-size: 22px; font-weight: 700; }"
            "QLabel#dialogSubtitle { color: #64748b; font-size: 13px; }"
            "QLabel#panelTitle { color: #334155; font-size: 13px; font-weight: 700; }"
            "QLabel#shotStatus { color: #0f172a; font-size: 15px; font-weight: 600; }"
            "QLabel#shotDetails { color: #64748b; font-size: 13px; }"
            "QPushButton {"
            "min-height: 38px; padding: 0 18px; border-radius: 7px;"
            "background: white; color: #1e293b; border: 1px solid #cbd5e1;"
            "font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #e2e8f0; }"
            "QPushButton:disabled { color: #94a3b8; background: #f8fafc; }"
            "QPushButton#primaryButton { background: #2563eb; color: white; border: none; }"
            "QPushButton#primaryButton:hover { background: #1d4ed8; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel(f"XEM LẠI PHÁT BẮN · BỆ {self.pedestal_id}")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Phiên bắn vừa kết thúc")
        subtitle.setObjectName("dialogSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        panels = QHBoxLayout()
        panels.setSpacing(16)
        self.camera_view = self._create_panel(panels, "ẢNH CHỤP TỪ SÚNG", "Không có ảnh camera")
        self.simulation_view = self._create_panel(panels, "MÔ PHỎNG ĐIỂM CHẠM", "Không có ảnh mô phỏng")
        root.addLayout(panels, 1)

        info_frame = QFrame()
        info_frame.setObjectName("infoFrame")
        info_frame.setStyleSheet(
            "QFrame#infoFrame {"
            "background: white; border: 1px solid #dbe3ec; border-radius: 9px;"
            "}"
        )
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(16, 10, 16, 10)
        info_layout.setSpacing(3)
        self.status_label = QLabel()
        self.status_label.setObjectName("shotStatus")
        self.details_label = QLabel()
        self.details_label.setObjectName("shotDetails")
        info_layout.addWidget(self.status_label)
        info_layout.addWidget(self.details_label)
        root.addWidget(info_frame)

        controls = QHBoxLayout()
        controls.setSpacing(9)
        self.previous_btn = QPushButton("◀  Phát trước")
        self.counter_label = QLabel()
        self.counter_label.setAlignment(Qt.AlignCenter)
        self.counter_label.setMinimumWidth(130)
        self.counter_label.setStyleSheet(
            "color: #0f172a; font-size: 15px; font-weight: 700; padding: 8px;"
        )
        self.next_btn = QPushButton("Phát sau  ▶")
        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("primaryButton")

        self.previous_btn.clicked.connect(self.show_previous)
        self.next_btn.clicked.connect(self.show_next)
        close_btn.clicked.connect(self.accept)

        controls.addWidget(self.previous_btn)
        controls.addStretch()
        controls.addWidget(self.counter_label)
        controls.addStretch()
        controls.addWidget(self.next_btn)
        controls.addSpacing(12)
        controls.addWidget(close_btn)
        root.addLayout(controls)

    def _create_panel(self, panels, title_text, placeholder):
        frame = QFrame()
        frame.setObjectName("reviewPanel")
        frame.setStyleSheet(
            "QFrame#reviewPanel {"
            "background: white; border: 1px solid #dbe3ec; border-radius: 10px;"
            "}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("panelTitle")
        view = AspectImageLabel(placeholder)
        layout.addWidget(title)
        layout.addWidget(view, 1)
        panels.addWidget(frame, 1)
        return view

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
        if not self.shots:
            self.counter_label.setText("0 / 0")
            self.status_label.setText("Chưa có dữ liệu phát bắn")
            self.details_label.setText("")
            for button in (self.previous_btn, self.next_btn):
                button.setEnabled(False)
            return

        shot = self.shots[self.current_index]
        self.camera_view.set_bgr_image(self._camera_preview(shot))
        self.simulation_view.set_bgr_image(self._simulation_preview(shot))

        shot_number = shot.get("shot_number", self.current_index + 1)
        target_name = shot.get("target_name") or "Không xác định được bia"
        status = shot.get("status") or "Không có trạng thái"
        hit = shot.get("hit")
        result_text = "TRÚNG" if hit is True else "TRƯỢT" if hit is False else "CHƯA XÁC ĐỊNH"
        self.status_label.setText(
            f"Phát {shot_number} · {target_name} · {result_text}"
        )
        detection_count = len(shot.get("detections", []))
        self.details_label.setText(
            f"{status} · Phát hiện {detection_count} bia · "
            "Ảnh camera zoom 1.5x · "
            "Khung vàng: bia được chọn; khung xanh: detection khác"
        )
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.shots)}")

        at_start = self.current_index == 0
        at_end = self.current_index == len(self.shots) - 1
        self.previous_btn.setEnabled(not at_start)
        self.next_btn.setEnabled(not at_end)

    def _camera_preview(self, shot):
        frame = shot.get("frame")
        if frame is None:
            return self._placeholder_image("KHONG CO ANH CAMERA")
        normalized = shot.get("camera_point")
        if normalized is None:
            preview = frame.copy()
            self._draw_detection_boxes(preview, shot.get("detections", []))
            return preview

        height, width = frame.shape[:2]
        source_point = (normalized[0] * width, normalized[1] * height)
        preview, transform = self._zoom_around_point(
            frame,
            source_point,
            REVIEW_CAMERA_ZOOM,
        )
        detections = [
            {
                **detection,
                "bbox": self._transform_bbox(detection.get("bbox"), transform),
            }
            for detection in shot.get("detections", [])
        ]
        self._draw_detection_boxes(preview, detections)
        draw_impact_marker(preview, self._transform_point(source_point, transform))
        return preview

    @staticmethod
    def _draw_detection_boxes(image, detections):
        height, width = image.shape[:2]
        scale = max(0.55, min(1.1, max(height, width) / 900.0))
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

            class_id = detection.get("class_id")
            class_name = scoring.CLASS_NAMES.get(class_id, f"Class {class_id}")
            prefix = "CHON" if selected else "DET"
            label = (
                f"{prefix} C{class_id} {class_name} "
                f"{detection.get('confidence', 0.0):.2f}"
            )
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.55 * scale
            text_thickness = max(1, int(round(2 * scale)))
            (text_width, text_height), baseline = cv2.getTextSize(
                label, font, font_scale, text_thickness
            )
            label_top = max(0, y1 - text_height - baseline - 8)
            label_right = min(width - 1, x1 + text_width + 10)
            cv2.rectangle(
                image,
                (x1, label_top),
                (label_right, min(height - 1, label_top + text_height + baseline + 8)),
                (0, 0, 0),
                -1,
            )
            cv2.putText(
                image,
                label,
                (x1 + 5, label_top + text_height + 3),
                font,
                font_scale,
                color,
                text_thickness,
                cv2.LINE_AA,
            )

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
        hit = shot.get("hit")
        border_color = (40, 170, 40) if hit is True else (40, 40, 220)
        thickness = max(5, int(round(max(preview.shape[:2]) * 0.012)))
        cv2.rectangle(
            preview,
            (thickness // 2, thickness // 2),
            (preview.shape[1] - thickness // 2 - 1, preview.shape[0] - thickness // 2 - 1),
            border_color,
            thickness,
        )
        normalized = shot.get("target_point")
        if normalized is not None:
            height, width = preview.shape[:2]
            point = (normalized[0] * width, normalized[1] * height)
            # Always use bright red for the impact itself.  Reusing the green
            # "hit" border made the marker disappear into dark-green targets.
            draw_impact_marker(
                preview,
                point,
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
