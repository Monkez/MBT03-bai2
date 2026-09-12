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
    "biaso10_X7.png",
    "biaso6_X7.png",
    "biaso7b_X7.png",
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
    review_requested = pyqtSignal(int)

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
        self.connected = False
        self.connection_info = ""
        self._pedestal_default_style = self.pedestal_name_label.styleSheet()

        self.name_label.setTextFormat(Qt.RichText)
        self.result_label.setTextFormat(Qt.RichText)

        self._target_images = self._load_target_images()
        self._localize_text()
        self._configure_ui()
        self.reset_all()
        self.set_connection_state(False)

    def _bind_ui_widgets(self):
        self.pedestal_name_label = self.findChild(QLabel, "pedestal_name_label")
        self.name_label = self.findChild(QLabel, "name_label")
        self.result_label = self.findChild(QLabel, "result_label") or self.findChild(QLabel, "sum_score_label")
        self.go_out_btn = self.findChild(QPushButton, "go_out_btn")
        self.review_btn = self.findChild(QPushButton, "review_btn")
        self.score_speak_icon = self.findChild(QPushButton, "score_speak_icon")
        self.sign_image = self.findChild(QWidget, "sign_image")

        missing = [
            name
            for name in (
                "pedestal_name_label",
                "name_label",
                "result_label",
                "go_out_btn",
                "review_btn",
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
        self.review_btn.clicked.connect(lambda: self.review_requested.emit(self.id))
        self.review_btn.setToolTip("Xem lại các phát bắn của phiên vừa kết thúc")
        self.review_btn.setEnabled(False)
        self.go_out_btn.clicked.connect(self.reset_shooter)

    def set_review_available(self, available):
        self.review_btn.setEnabled(bool(available))

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

    def set_connection_state(self, connected, info=""):
        """Update connection text while only changing color when connected."""
        if connected is None:
            self.connected = False
            self.connection_info = str(info or "")
            self.pedestal_name_label.setText(
                f"B\u1ec6 S\u1ed0 {self.id}  \u2022  \u0110ANG X\u00c1C NH\u1eacN"
            )
            self.pedestal_name_label.setStyleSheet(self._pedestal_default_style)
            self.pedestal_name_label.setToolTip(self.connection_info)
            return

        self.connected = bool(connected)
        self.connection_info = str(info or "")
        if self.connected:
            self.pedestal_name_label.setText(
                f"B\u1ec6 S\u1ed0 {self.id}  \u2022  \u0110\u00c3 K\u1ebeT N\u1ed0I"
            )
            self.pedestal_name_label.setStyleSheet(
                "background-color: rgb(0, 153, 0);\n"
                "color: rgb(255, 255, 255);"
            )
            self.pedestal_name_label.setToolTip(self.connection_info)
        else:
            self.pedestal_name_label.setText(
                f"B\u1ec6 S\u1ed0 {self.id}  \u2022  CH\u01afA K\u1ebeT N\u1ed0I"
            )
            self.pedestal_name_label.setStyleSheet(self._pedestal_default_style)
            self.pedestal_name_label.setToolTip("")

    def set_connection_metrics(self, ping_ms=None, battery_percent=None):
        if not self.connected:
            return
        details = []
        if ping_ms is not None:
            details.append(f"Ping {float(ping_ms):.0f}ms")
        if battery_percent is not None:
            details.append(f"Pin {float(battery_percent):.0f}%")
        suffix = f"  ({' - '.join(details)})" if details else ""
        self.pedestal_name_label.setText(
            f"B\u1ec6 S\u1ed0 {self.id}  \u2022  \u0110\u00c3 K\u1ebeT N\u1ed0I{suffix}"
        )

    def set_connection_quality_state(
        self, state, ping_ms=None, battery_percent=None
    ):
        """Show the multi-stage connection state reported by the new core."""
        state = str(state or "healthy")
        if state == "healthy":
            # Always restore the complete healthy presentation.  A degraded
            # state also keeps ``connected`` true, so checking only that flag
            # would leave the previous amber background in place while the
            # text and ping already say that the connection is healthy.
            self.set_connection_state(True, self.connection_info)
            self.set_connection_metrics(ping_ms, battery_percent)
            return

        details = []
        if ping_ms is not None:
            details.append(f"Ping {float(ping_ms):.0f}ms")
        if battery_percent is not None:
            details.append(f"Pin {float(battery_percent):.0f}%")
        suffix = f"  ({' - '.join(details)})" if details else ""
        if state == "degraded":
            self.connected = True
            label = "KẾT NỐI CHẬP CHỜN"
            color = "rgb(217, 119, 6)"
        else:
            self.connected = False
            label = "MẤT TÍN HIỆU"
            color = "rgb(185, 28, 28)"
        self.pedestal_name_label.setText(
            f"BỆ SỐ {self.id}  •  {label}{suffix}"
        )
        self.pedestal_name_label.setStyleSheet(
            f"background-color: {color};\ncolor: rgb(255, 255, 255);"
        )

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

    def record_miss(self):
        """Count a shot that cannot be associated with any detected target."""
        if self.bullet_count >= self.bullet_limit:
            return
        self.bullet_count += 1
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
        self._rendered_target_rects = {}

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
        self._rendered_target_rects[target_index] = (ox, oy, iw, ih)

    def _draw_shot(self, canvas, target_index, px, py, hit):
        layout = self._current_target_layout()
        if target_index not in layout:
            return
        rendered_rect = getattr(self, "_rendered_target_rects", {}).get(target_index)
        if rendered_rect is None:
            x, y, w, h = layout[target_index]
            rendered_rect = (x + 8, y + 8, w - 16, h - 16)
        image_x, image_y, image_w, image_h = rendered_rect
        cx = int(image_x + px * image_w)
        cy = int(image_y + py * image_h)
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
