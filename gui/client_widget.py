import math
import os

import cv2
import numpy as np
from PyQt5 import sip, uic
from PyQt5.QtCore import QEvent, QRectF, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt5.QtWidgets import QLabel, QPushButton, QWidget, QFrame, QSizePolicy

import config as cf
from gui.styles import TARGET_GREEN, TARGET_RED


TARGET_IMAGE_FILES = [
    "biaso10_X7.png",
    "biaso6_X7.png",
    "biaso7b_X7.png",
    "biaso8_phai_X7.png",
]
TARGET_NAMES = ("BIA SỐ 10", "BIA SỐ 6", "BIA SỐ 7B", "BIA SỐ 8C")
TARGET_IMAGE_SCALE = 0.9


TARGET_LAYOUT = {
    1: (20, 20, 426, 326),
    0: (20, 354, 426, 256),
    2: (454, 20, 286, 590),
    3: (748, 20, 232, 590),
}

TWO_PEDESTAL_TARGET_LAYOUT = {
    1: (32, 24, 456, 312),
    0: (32, 344, 456, 250),
    2: (32, 612, 224, 468),
    3: (264, 612, 224, 468),
}


def classify_hits(hit_targets, has_single_shots=False):
    count = len(hit_targets)
    if count == 4:
        return "Khá" if has_single_shots else "Giỏi"
    if count == 3 and 3 in hit_targets:
        return "Đạt" if has_single_shots else "Khá"
    return "Đạt" if count >= 2 else "Không đạt"


class ClientWidget(QFrame):
    score_speak_requested = pyqtSignal(int)
    review_requested = pyqtSignal(int)
    locate_requested = pyqtSignal(int)

    def __init__(self, pedestal_id, parent=None, target_layout_mode="default"):
        super().__init__(parent)
        uic.loadUi(cf.DATA_DIR + "assets/qt/client.ui", self)
        self._bind_ui_widgets()

        self.id = pedestal_id
        self.target_layout_mode = target_layout_mode
        self.bullet_limit = cf.max_bullets()
        self.bullet_count = 0
        self.hit_targets = set()
        self.has_single_shots = False
        self.single_shot_targets = set()
        self._target_rounds = {}
        self.hit_counts = [0] * 4
        self.shots = []
        self.testing = False
        self._target_presentation = None
        self._show_final_results = False
        self._visible_target_classes = ()
        self.connected = False
        self.connection_info = ""
        self._pedestal_default_style = self.pedestal_name_label.styleSheet()
        self._pedestal_connection_style = self._pedestal_default_style
        self._connection_healthy = False
        self.locating = False
        self._locate_blink_on = False
        self._locate_timer = QTimer(self)
        self._locate_timer.setInterval(500)
        self._locate_timer.timeout.connect(self._blink_locate_label)
        self.pedestal_name_label.installEventFilter(self)
        self.pedestal_name_label.setFocusPolicy(Qt.StrongFocus)
        self.pedestal_name_label.setAccessibleDescription(
            "Bấm hoặc nhấn Enter để bật/tắt nhấp nháy đèn tìm súng của bệ"
        )

        self.name_label.setTextFormat(Qt.RichText)
        self._shooter_text = ""
        self.name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.name_label.installEventFilter(self)
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
        self.target_status_label = QLabel(self.sign_image)
        self.target_status_label.setAlignment(Qt.AlignCenter)
        self.target_status_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.target_status_label.hide()
        self.error_label = QLabel(self.sign_image)
        self.error_label.setTextFormat(Qt.PlainText)
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.error_label.setAccessibleName("Cảnh báo lỗi súng")
        self.error_label.setStyleSheet(
            "background-color: rgba(255, 245, 245, 245); color: #b91c1c;"
            "font-size: 20px; font-weight: bold; border: 2px solid #b91c1c;"
            "border-radius: 6px; padding: 10px;"
        )
        self.error_label.hide()
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self.error_label.hide)
        self.sign_image.installEventFilter(self)
        self.sign_image.frame.installEventFilter(self)
        self.score_speak_icon.clicked.connect(lambda: self.score_speak_requested.emit(self.id))
        self.set_score_speak_ui_state("idle")
        self.review_btn.clicked.connect(lambda: self.review_requested.emit(self.id))
        self.review_btn.setToolTip("Xem lại các phát bắn của phiên vừa kết thúc")
        self.review_btn.setEnabled(False)
        self.go_out_btn.clicked.connect(self.reset_shooter)

    def show_error(self, code):
        messages = {"E1": "Lỗi giữ cò quá lâu!", "E2": "Lỗi bắn quá nhanh!"}
        if code not in messages:
            return
        self.error_label.setText(messages[code] + "\nChờ 7 giây trước khi bắn tiếp.")
        self._position_error_label()
        self.error_label.show()
        self.error_label.raise_()
        self._error_timer.start(cf.config_int(
            "runtime.error_message_duration_ms", 7000, minimum=1, maximum=60000
        ))

    def _position_error_label(self):
        width = max(1, min(400, self.sign_image.width() - 24))
        self.error_label.setFixedWidth(width)
        height = self.error_label.heightForWidth(width)
        self.error_label.resize(width, max(90, height))
        self.error_label.move(
            (self.sign_image.width() - width) // 2,
            max(0, (self.sign_image.height() - self.error_label.height()) // 2),
        )

    def eventFilter(self, watched, event):
        if watched is self.name_label and event.type() == QEvent.Resize and self._shooter_text:
            self._update_shooter_label()
        if watched is self.pedestal_name_label:
            clicked = (event.type() == QEvent.MouseButtonRelease
                       and event.button() == Qt.LeftButton)
            keyed = (event.type() == QEvent.KeyPress
                     and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space)
                     and not event.isAutoRepeat())
            if clicked or keyed:
                if self.connected:
                    self.locate_requested.emit(self.id)
                return True
        if watched is self.sign_image and event.type() == QEvent.Resize:
            self._position_error_label()
            self._position_target_status()
        if watched is self.sign_image.frame and event.type() == QEvent.Resize and self.testing:
            self.show_target_simulation()
        return super().eventFilter(watched, event)

    def clear_error(self):
        self._error_timer.stop()
        self.error_label.hide()

    def set_review_available(self, available):
        self.review_btn.setEnabled(bool(available))

    def _set_target_background_white(self):
        if hasattr(self.sign_image, "set_background_color"):
            self.sign_image.set_background_color(QColor(255, 255, 255))
        if hasattr(self.sign_image, "frame"):
            self.sign_image.frame.setStyleSheet("background-color: rgb(255, 255, 255); border-radius: 5px;")

    def reset_all(self):
        self.clear_error()
        self.bullet_count = 0
        self.hit_targets.clear()
        self.has_single_shots = False
        self.single_shot_targets.clear()
        self._target_rounds = {}
        self.hit_counts = [0] * 4
        self.shots.clear()
        self.testing = False
        self._target_presentation = None
        self._show_final_results = False
        self.pedestal_name_label.setText(f"BỆ SỐ {self.id}")
        self._visible_target_classes = ()
        self.reset_shooter()
        self.show_target_simulation()

    def reset_shooter(self):
        self._shooter_text = ""
        self.name_label.setTextFormat(Qt.RichText)
        self.name_label.setToolTip("")
        self.name_label.setAccessibleName("Người bắn: chưa chọn")
        self.name_label.setText(
            '<html><head/><body><p align="center">'
            'Người bắn: <span style="color:#ff0000;">-</span>'
            "</p></body></html>"
        )
        self.update_result_label()

    def set_shooter(self, text):
        self._shooter_text = text
        self.name_label.setTextFormat(Qt.PlainText)
        self.name_label.setToolTip(text)
        self.name_label.setAccessibleName(f"Người bắn: {text}")
        self._update_shooter_label()

    def _update_shooter_label(self):
        self.name_label.setText(self.name_label.fontMetrics().elidedText(
            self._shooter_text, Qt.ElideRight, max(1, self.name_label.contentsRect().width())))

    def set_connection_state(self, connected, info=""):
        """Update connection text while only changing color when connected."""
        self._connection_healthy = bool(connected)
        if not connected:
            self.set_locating(False)
        if connected is None:
            self.connected = False
            self.connection_info = str(info or "")
            self.pedestal_name_label.setText(
                f"B\u1ec6 S\u1ed0 {self.id}  \u2022  \u0110ANG X\u00c1C NH\u1eacN"
            )
            self._set_pedestal_connection_style(self._pedestal_default_style)
            return

        self.connected = bool(connected)
        self.connection_info = str(info or "")
        if self.connected:
            self.pedestal_name_label.setText(
                f"B\u1ec6 S\u1ed0 {self.id}  \u2022  \u0110\u00c3 K\u1ebeT N\u1ed0I"
            )
            self._set_pedestal_connection_style(
                "background-color: rgb(0, 153, 0);\n"
                "color: rgb(255, 255, 255);"
            )
        else:
            self.pedestal_name_label.setText(
                f"B\u1ec6 S\u1ed0 {self.id}  \u2022  CH\u01afA K\u1ebeT N\u1ed0I"
            )
            self._set_pedestal_connection_style(self._pedestal_default_style)

    def set_locating(self, active):
        self.locating = bool(active)
        self._locate_blink_on = self.locating
        if self.locating:
            self._locate_timer.start()
        else:
            self._locate_timer.stop()
        self._render_locate_label()

    def _blink_locate_label(self):
        self._locate_blink_on = not self._locate_blink_on
        self._render_locate_label()

    def _set_pedestal_connection_style(self, style):
        self._pedestal_connection_style = style
        self._render_locate_label()

    def _render_locate_label(self):
        style = self._pedestal_connection_style
        if self._connection_healthy and self.locating and self._locate_blink_on:
            style = "background-color: rgb(220, 0, 0); color: white;"
        self.pedestal_name_label.setStyleSheet(style)
        hint = ("Đang nhấp nháy đèn tìm súng. Bấm để tắt."
                if self.locating else "Bấm để nhấp nháy đèn tìm súng của bệ.")
        if not self.connected:
            hint = "Kết nối súng để sử dụng chức năng nhấp nháy đèn."
        self.pedestal_name_label.setToolTip("\n".join(filter(None, (self.connection_info, hint))))
        self.pedestal_name_label.setCursor(Qt.PointingHandCursor if self.connected else Qt.ArrowCursor)

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

        self._connection_healthy = False
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
            self.set_locating(False)
            label = "MẤT TÍN HIỆU"
            color = "rgb(185, 28, 28)"
        self.pedestal_name_label.setText(
            f"BỆ SỐ {self.id}  •  {label}{suffix}"
        )
        self._set_pedestal_connection_style(
            f"background-color: {color};\ncolor: rgb(255, 255, 255);"
        )

    def start_test(self):
        self.reset_results()
        self.testing = True
        self.set_target_presentation((1, False))

    def reset_results(self):
        self.clear_error()
        self._show_final_results = False
        self.bullet_count = 0
        self.hit_targets.clear()
        self.has_single_shots = False
        self.single_shot_targets.clear()
        self._target_rounds = {}
        self.hit_counts = [0] * 4
        self.shots.clear()
        self.update_result_label()
        self.show_target_simulation()

    def stop_test(self):
        self.testing = False
        self._show_final_results = True
        self._visible_target_classes = ()
        self._target_presentation = None
        self.show_target_simulation()
        self.update_result_label()

    def record_shot(self, target_index, x_ratio, y_ratio, hit=True, show_marker=True):
        if self.bullet_count >= self.bullet_limit:
            return

        target_index = max(0, min(3, int(target_index)))
        try:
            x_ratio, y_ratio = float(x_ratio), float(y_ratio)
            show_marker = show_marker and math.isfinite(x_ratio) and math.isfinite(y_ratio)
        except (TypeError, ValueError, OverflowError):
            show_marker = False

        self.bullet_count += 1
        if show_marker:
            self.shots.append((target_index, x_ratio, y_ratio, bool(hit)))
        if hit:
            self.hit_targets.add(target_index)
            self.hit_counts[target_index] += 1

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
        return classify_hits(self.hit_targets, self.has_single_shots)

    def set_burst_assessment(self, singles, targets):
        state = (bool(singles), set(targets))
        if state == (self.has_single_shots, self.single_shot_targets):
            return
        self.has_single_shots, self.single_shot_targets = state
        self.update_result_label()
        self.show_target_simulation()

    def set_target_rounds(self, groups):
        if groups != self._target_rounds:
            self._target_rounds = groups
            self.show_target_simulation()

    def _target_border_color(self, target):
        return TARGET_GREEN if target in self.hit_targets else TARGET_RED

    def set_score_speak_ui_state(self, state):
        speaking = state == "speaking"
        self.score_speak_icon.setEnabled(state in ("idle", "speaking"))
        tooltip = {
            "idle": "Đọc kết quả bệ này",
            "speaking": "Đang đọc — bấm để dừng",
            "disabled": "Đang đọc kết quả bệ khác",
            "testing": "Kết thúc bài bắn để đọc kết quả",
        }[state]
        self.score_speak_icon.setToolTip(tooltip)
        self.score_speak_icon.setAccessibleName(tooltip)
        self.score_speak_icon.setStyleSheet(
            "QPushButton { background: white; border: "
            + ("2px solid #dc2626;" if speaking else "1px solid #9ca3af;")
            + "border-radius: 4px; }"
            "QPushButton:disabled { background: #e5e7eb; }"
            "QPushButton:focus { border: 2px solid #2563eb; }"
        )

    def show_target_simulation(self):
        self.sign_image.set_image(self.compose_target_image())
        self._update_target_status()

    def set_target_presentation(self, state, visible_targets=None):
        visible_targets = tuple(visible_targets) if visible_targets is not None else (
            (state[0],) if state is not None and state[1] else ())
        if state != self._target_presentation or visible_targets != self._visible_target_classes:
            self._target_presentation = state
            self._visible_target_classes = visible_targets
            self.show_target_simulation()

    def _position_target_status(self):
        self.target_status_label.setGeometry(8, 4, max(1, self.sign_image.width() - 16), 28)

    def _update_target_status(self):
        state = self._target_presentation
        self.target_status_label.setVisible(state is not None)
        if state is None:
            self.sign_image.setAccessibleName("Toàn bộ bốn bia và các điểm chạm")
            return
        if len(self._visible_target_classes) > 1:
            self.target_status_label.hide()
            self.sign_image.setAccessibleName("; ".join(
                f"{TARGET_NAMES[target]} đang hiện" for target in self._visible_target_classes))
            return
        target, visible = state
        status = "ĐANG HIỆN" if visible else "ĐANG GẬP"
        text = f"{TARGET_NAMES[target]} · {status}"
        self.target_status_label.setText(text)
        self.target_status_label.setStyleSheet(
            "background: white; font-size: 15px; font-weight: bold; color: "
            + ("#15803d;" if visible else "#64748b;")
        )
        self._position_target_status()
        self.target_status_label.raise_()
        self.error_label.raise_()
        self.sign_image.setAccessibleName(text)

    def compose_target_image(self):
        if self._target_presentation is not None:
            if len(self._visible_target_classes) > 1:
                return self._compose_visible_targets()
            return self._compose_focused_target()
        layout = self._current_target_layout()
        canvas_w, canvas_h = self._current_canvas_size()
        canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
        self._rendered_target_rects = {}
        self._marker_clip_rects = {}

        for target_index in (0, 2, 1, 3):
            x, y, w, h = layout[target_index]
            border_color = self._target_border_color(target_index)
            self._draw_target(canvas, target_index, x, y, w, h, border_color,
                              folded=self._show_final_results and target_index not in self.hit_targets)

        for target_index, px, py, hit in self.shots:
            self._draw_shot(canvas, target_index, px, py, hit)

        return canvas

    def _compose_visible_targets(self):
        width = max(160, self.sign_image.frame.width()) * 2
        height = max(160, self.sign_image.frame.height()) * 2
        canvas = np.full((height, width, 3), 255, dtype=np.uint8)
        self._rendered_target_rects, self._marker_clip_rects = {}, {}
        targets = self._visible_target_classes
        columns = 2 if width >= height or len(targets) > 2 else 1
        rows = (len(targets) + columns - 1) // columns
        cell_w = (width - 20 * (columns + 1)) // columns
        cell_h = (height - 16 - 20 * rows) // rows
        captions = []
        for index, target in enumerate(targets):
            x = 20 + (index % columns) * (cell_w + 20)
            y = 16 + (index // columns) * (cell_h + 20)
            self._draw_target(canvas, target, x, y + 34, cell_w, cell_h - 34,
                              self._target_border_color(target))
            captions.append((QRectF(x, y, cell_w, 30), f"{TARGET_NAMES[target]} · ĐANG HIỆN"))
        for target, px, py, hit in self.shots:
            if target in targets:
                self._draw_shot(canvas, target, px, py, hit)
        surface = QImage(sip.voidptr(canvas.ctypes.data), width, height, canvas.strides[0], QImage.Format_BGR888)
        painter = QPainter(surface)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Segoe UI")
        font.setPixelSize(26)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#15803d"))
        for rectangle, text in captions:
            painter.drawText(rectangle, Qt.AlignCenter, text)
        painter.end()
        return canvas

    def _compose_focused_target(self):
        target, visible = self._target_presentation
        # Match the live viewport so both landscape and portrait targets enlarge.
        width = max(160, self.sign_image.frame.width()) * 2
        height = max(160, self.sign_image.frame.height()) * 2
        canvas = np.full((height, width, 3), 255, dtype=np.uint8)
        self._rendered_target_rects = {}
        self._marker_clip_rects = {}
        border = self._target_border_color(target)
        self._draw_target(canvas, target, 20, 72, width - 40, height - 92,
                          border, folded=not visible)
        if visible:
            for index, px, py, hit in self.shots:
                if index == target:
                    self._draw_shot(canvas, index, px, py, hit)
        return canvas

    @staticmethod
    def _folded_image(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        return cv2.addWeighted(gray, 0.16, np.full_like(gray, 255), 0.84, 0)

    def _current_target_layout(self):
        if self.target_layout_mode == "two_pedestals":
            return TWO_PEDESTAL_TARGET_LAYOUT
        return TARGET_LAYOUT

    def _current_canvas_size(self):
        if self.target_layout_mode == "two_pedestals":
            return 520, 1104
        return 1000, 630

    def _draw_target(self, canvas, target_index, x, y, w, h, border_color_hex, folded=False):
        # Paint directly into the BGR canvas for smooth corners at every size.
        scale = 2 if self._target_presentation is not None else 1
        stroke = 3 * scale
        halo = 9 * scale
        inset = halo / 2 + 1
        frame = QRectF(x + inset, y + inset, w - 2 * inset, h - 2 * inset)
        surface = QImage(sip.voidptr(canvas.ctypes.data), canvas.shape[1], canvas.shape[0],
                         canvas.strides[0], QImage.Format_BGR888)
        painter = QPainter(surface)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(border_color_hex)
        soft_color = QColor(color)
        soft_color.setAlpha(35)
        painter.setBrush(Qt.white)
        painter.setPen(QPen(soft_color, halo))
        painter.drawRoundedRect(frame, 12 * scale, 12 * scale)
        painter.setPen(QPen(color, stroke))
        painter.drawRoundedRect(frame, 12 * scale, 12 * scale)
        painter.end()

        padding = 12 * scale
        strip_height = self._draw_target_rounds(surface, target_index, x + padding, y + padding,
                                                w - 2 * padding, h - 2 * padding, scale)
        inner = (x + padding, y + padding + strip_height, w - 2 * padding, h - 2 * padding - strip_height)
        image = self._fit_image(self._target_images[target_index],
                                max(1, round(inner[2] * TARGET_IMAGE_SCALE)),
                                max(1, round(inner[3] * TARGET_IMAGE_SCALE)))
        if folded:
            image = self._folded_image(image)
        ih, iw = image.shape[:2]
        ox = inner[0] + (inner[2] - iw) // 2
        oy = inner[1] + (inner[3] - ih) // 2
        canvas[oy:oy + ih, ox:ox + iw] = image
        self._rendered_target_rects[target_index] = (ox, oy, iw, ih)
        self._marker_clip_rects[target_index] = inner

    def _draw_target_rounds(self, surface, target, x, y, width, height, scale):
        groups = self._target_rounds.get(target, ())
        # Reserve a fixed band before the first receipt; only cells adapt to it.
        columns = max(1, int((width + 8 * scale) // (36 * scale)))
        rows = min(2, math.ceil(self.bullet_limit / columns))
        strip_height = min(rows * 30 * scale, int(height * .24))
        for cell in range(20 * scale, 2, -1):
            pad, gap = max(1, cell // 5), max(2, cell * 2 // 5)
            cursor, row, segments = 0, 0, []
            row_height = cell + 2 * pad + gap
            for kind, rounds in groups:
                remaining = list(rounds)
                if cursor and cursor + len(remaining) * (cell + pad) + pad > width:
                    cursor, row = 0, row + 1
                while remaining:
                    count = max(1, min(len(remaining), int((width - cursor - pad) // (cell + pad))))
                    segment, remaining = remaining[:count], remaining[count:]
                    group_width = count * (cell + pad) + pad
                    segments.append((kind, segment, QRectF(x + cursor, y + row * row_height,
                                                          group_width, cell + 2 * pad)))
                    cursor += group_width + gap
                    if remaining:
                        cursor, row = 0, row + 1
            if (row + 1) * row_height <= strip_height:
                break
        painter = QPainter(surface)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont("Segoe UI"); font.setPixelSize(max(6, round(cell * .55))); font.setBold(True)
        painter.setFont(font)
        for kind, rounds, outer in segments:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#eab52c" if kind == "single" else "#1769ff"), max(1, cell / 10)))
            if kind in ("single", "burst"):
                painter.drawRoundedRect(outer, pad, pad)
            for index, (number, status) in enumerate(rounds):
                rect = QRectF(outer.x() + pad + index * (cell + pad), outer.y() + pad, cell, cell)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor({"hit": "#1a9b58", "miss": "#df3949", "pending": "#dce2ea"}[status]))
                painter.drawRoundedRect(rect, 3, 3)
                painter.setPen(QColor("#64748b" if status == "pending" else "white"))
                painter.drawText(rect, Qt.AlignCenter, str(number))
        painter.end()
        return strip_height

    def _draw_shot(self, canvas, target_index, px, py, hit):
        if (self._target_presentation is not None and target_index != self._target_presentation[0]
                and target_index not in self._visible_target_classes):
            return
        rendered_rect = getattr(self, "_rendered_target_rects", {}).get(target_index)
        clip = getattr(self, "_marker_clip_rects", {}).get(target_index)
        if rendered_rect is None or clip is None:
            return
        image_x, image_y, image_w, image_h = rendered_rect
        cx, cy = image_x + px * image_w, image_y + py * image_h
        clip_x, clip_y, clip_w, clip_h = clip
        # Keep the true projection, including nearby misses outside the image.
        # A distant point is hidden, never moved onto an edge or another target.
        if not (clip_x <= cx < clip_x + clip_w and clip_y <= cy < clip_y + clip_h):
            return
        marker_canvas = canvas[clip_y:clip_y + clip_h, clip_x:clip_x + clip_w]
        center = (int(cx) - clip_x, int(cy) - clip_y)
        color = (255, 0, 0) if hit else (0, 0, 255)
        cv2.drawMarker(
            marker_canvas,
            center,
            color,
            markerType=cv2.MARKER_CROSS,
            markerSize=24,
            thickness=3,
        )
        cv2.circle(marker_canvas, center, 6, (255, 255, 255), 2)

    def _fit_image(self, image, box_w, box_h):
        h, w = image.shape[:2]
        scale = min(box_w / w, box_h / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
