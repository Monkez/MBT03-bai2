import os

import cv2
import numpy as np
from PyQt5 import uic
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLabel, QPushButton, QWidget, QFrame

import config as cf
from gui.styles import TARGET_GREEN, TARGET_RED


TARGET_IMAGE_FILES = [
    "biaso6_X7.png",
    "biaso7b_X7.png",
    "biaso10_X7.png",
    "biaso8_phai_X7.png",
]


TARGET_LAYOUT = {
    0: (20, 20, 426, 326),
    2: (20, 354, 426, 256),
    1: (454, 20, 286, 590),
    3: (748, 20, 232, 590),
}

TWO_PEDESTAL_TARGET_LAYOUT = {
    0: (32, 24, 456, 312),
    2: (32, 344, 456, 250),
    1: (32, 612, 224, 468),
    3: (264, 612, 224, 468),
}


class ClientWidget(QFrame):
    score_speak_requested = pyqtSignal(int)

    def __init__(self, pedestal_id, parent=None, target_layout_mode="default"):
        super().__init__(parent)
        uic.loadUi(cf.DATA_DIR + "assets/qt/client.ui", self)
        self._bind_ui_widgets()

        self.id = pedestal_id
        self.target_layout_mode = target_layout_mode
        self.bullet_limit = 16
        self.bullet_count = 0
        self.hit_targets = set()
        self.shots = []
        self.testing = False

        self.name_label.setTextFormat(Qt.RichText)
        self.result_label.setTextFormat(Qt.RichText)

        self._target_images = self._load_target_images()
        self._localize_text()
        self._configure_ui()
        self.reset_all()

    def _bind_ui_widgets(self):
        self.pedestal_name_label = self.findChild(QLabel, "pedestal_name_label")
        self.name_label = self.findChild(QLabel, "name_label")
        self.result_label = self.findChild(QLabel, "result_label") or self.findChild(QLabel, "sum_score_label")
        self.go_out_btn = self.findChild(QPushButton, "go_out_btn")
        self.score_speak_icon = self.findChild(QPushButton, "score_speak_icon")
        self.sign_image = self.findChild(QWidget, "sign_image")

        missing = [
            name
            for name in (
                "pedestal_name_label",
                "name_label",
                "result_label",
                "go_out_btn",
                "score_speak_icon",
                "sign_image",
            )
            if getattr(self, name) is None
        ]
        if missing:
            raise RuntimeError(f"client.ui thiếu widget: {', '.join(missing)}")

    def _load_target_images(self):
        images = []
        for filename in TARGET_IMAGE_FILES:
            path = os.path.join(cf.DATA_DIR, "assets", "signs", filename)
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is None:
                image = np.full((300, 220, 3), 255, dtype=np.uint8)
            images.append(image)
        return images

    def _localize_text(self):
        self.pedestal_name_label.setText(f"BỆ SỐ {self.id}")
        self.reset_shooter()

    def _configure_ui(self):
        self._set_target_background_white()
        self.score_speak_icon.clicked.connect(lambda: self.score_speak_requested.emit(self.id))
        self.go_out_btn.clicked.connect(self.reset_shooter)

    def _set_target_background_white(self):
        if hasattr(self.sign_image, "set_background_color"):
            self.sign_image.set_background_color(QColor(255, 255, 255))
        if hasattr(self.sign_image, "frame"):
            self.sign_image.frame.setStyleSheet("background-color: rgb(255, 255, 255); border-radius: 5px;")

    def reset_all(self):
        self.bullet_count = 0
        self.hit_targets.clear()
        self.shots.clear()
        self.testing = False
        self.pedestal_name_label.setText(f"BỆ SỐ {self.id}")
        self.reset_shooter()
        self.show_target_simulation()

    def reset_shooter(self):
        self.name_label.setText(
            '<html><head/><body><p align="center">'
            'Người bắn: <span style="color:#ff0000;">-</span>'
            "</p></body></html>"
        )
        self.update_result_label()

    def start_test(self):
        self.bullet_count = 0
        self.hit_targets.clear()
        self.shots.clear()
        self.testing = True
        self.update_result_label()
        self.show_target_simulation()

    def stop_test(self):
        self.testing = False
        self.update_result_label()

    def record_shot(self, target_index, x_ratio, y_ratio, hit=True):
        if self.bullet_count >= self.bullet_limit:
            return

        target_index = max(0, min(3, int(target_index)))
        x_ratio = max(0.0, min(1.0, float(x_ratio)))
        y_ratio = max(0.0, min(1.0, float(y_ratio)))

        self.bullet_count += 1
        self.shots.append((target_index, x_ratio, y_ratio, bool(hit)))
        if hit:
            self.hit_targets.add(target_index)

        self.update_result_label()
        self.show_target_simulation()

    def update_result_label(self):
        hit_count = len(self.hit_targets)
        rank = self._rank_text()
        self.result_label.setText(
            '<html><head/><body><p align="center">'
            f'Đạn: <span style="color:#ff0000;">{self.bullet_count}</span>/{self.bullet_limit}  '
            f'Mục tiêu: <span style="color:#ff0000;">{hit_count}</span>/4  '
            f'Xếp loại: <span style="color:#ff0000;">{rank}</span>'
            "</p></body></html>"
        )

    def _rank_text(self):
        if self.bullet_count == 0 and not self.hit_targets:
            return "-"
        if len(self.hit_targets) == 4:
            return "Đạt"
        if self.bullet_count >= self.bullet_limit:
            return "Không đạt"
        return "-"

    def show_target_simulation(self):
        self.sign_image.set_image(self.compose_target_image())

    def compose_target_image(self):
        layout = self._current_target_layout()
        canvas_w, canvas_h = self._current_canvas_size()
        canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)

        for target_index in (0, 2, 1, 3):
            x, y, w, h = layout[target_index]
            border_color = TARGET_GREEN if target_index in self.hit_targets else TARGET_RED
            self._draw_target(canvas, target_index, x, y, w, h, border_color)

        for target_index, px, py, hit in self.shots:
            self._draw_shot(canvas, target_index, px, py, hit)

        return canvas

    def _current_target_layout(self):
        if self.target_layout_mode == "two_pedestals":
            return TWO_PEDESTAL_TARGET_LAYOUT
        return TARGET_LAYOUT

    def _current_canvas_size(self):
        if self.target_layout_mode == "two_pedestals":
            return 520, 1104
        return 1000, 630

    def _draw_target(self, canvas, target_index, x, y, w, h, border_color_hex):
        cv2.rectangle(canvas, (x, y), (x + w, y + h), self._hex_to_bgr(border_color_hex), 6)

        inner = (x + 8, y + 8, w - 16, h - 16)
        image = self._fit_image(self._target_images[target_index], inner[2], inner[3])
        ih, iw = image.shape[:2]
        ox = inner[0] + (inner[2] - iw) // 2
        oy = inner[1] + (inner[3] - ih) // 2
        canvas[oy:oy + ih, ox:ox + iw] = image

    def _draw_shot(self, canvas, target_index, px, py, hit):
        layout = self._current_target_layout()
        if target_index not in layout:
            return
        x, y, w, h = layout[target_index]
        inner_x, inner_y, inner_w, inner_h = x + 8, y + 8, w - 16, h - 16
        cx = int(inner_x + px * inner_w)
        cy = int(inner_y + py * inner_h)
        color = (255, 0, 0) if hit else (0, 0, 255)
        cv2.drawMarker(
            canvas,
            (cx, cy),
            color,
            markerType=cv2.MARKER_CROSS,
            markerSize=24,
            thickness=3,
        )
        cv2.circle(canvas, (cx, cy), 6, (255, 255, 255), 2)

    def _fit_image(self, image, box_w, box_h):
        h, w = image.shape[:2]
        scale = min(box_w / w, box_h / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def _hex_to_bgr(self, color):
        color = color.lstrip("#")
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        return b, g, r
