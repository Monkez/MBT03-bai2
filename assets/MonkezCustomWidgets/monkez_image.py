import os
from PyQt5.QtWidgets import QDialog, QLabel, QSizePolicy, QVBoxLayout, QWidget, QFrame
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal as Signal, QTimer, pyqtProperty
from PyQt5.QtWidgets import QApplication
import cv2

def letterbox(image, new_shape=(640, 640), color=(0, 0, 0),
              auto=False, scaleFill=False, scaleup=True, stride=32):
    shape = image.shape[:2]  # (height, width)
    orig_h, orig_w = shape
    target_w, target_h = new_shape

    # Tính tỉ lệ scale
    r = min(target_w / orig_w, target_h / orig_h)
    if not scaleup:
        r = min(r, 1.0)

    # Kích thước sau khi scale
    new_unpad_w = int(round(orig_w * r))
    new_unpad_h = int(round(orig_h * r))
    img = cv2.resize(image, (new_unpad_w, new_unpad_h), interpolation=cv2.INTER_LINEAR)

    # Tính padding
    pad_w = target_w - new_unpad_w
    pad_h = target_h - new_unpad_h

    if auto:
        pad_w = pad_w % stride
        pad_h = pad_h % stride

    pad_w_left = pad_w // 2
    pad_w_right = pad_w - pad_w_left
    pad_h_top = pad_h // 2
    pad_h_bottom = pad_h - pad_h_top

    # Thêm padding
    img = cv2.copyMakeBorder(img, pad_h_top, pad_h_bottom, pad_w_left, pad_w_right,
                             cv2.BORDER_CONSTANT, value=color)

    ratio = (r, r)
    padding = (pad_w_left, pad_h_top)
    return img, ratio, padding

class MonkezImage(QWidget):
    def __init__(self, parent=None, background_color= (255, 255, 255), image_file=None):
        super().__init__(parent)
        # label for displaying the image
        self.padding = 2
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(self.padding, self.padding, self.padding, self.padding)
        self.frame = QFrame(self)
        self.frame.setStyleSheet(f"background-color: {background_color}; border-radius: 5px;")
        self.layout.addWidget(self.frame)
        self.image_label = QLabel(self.frame)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setText("Image will be displayed here")
        image_path = os.path.join(os.path.dirname(__file__), "monkez_assets/images", "MonkezPlaceHolderImage.jpg") if image_file is None else os.path.join(os.path.dirname(__file__), image_file)
        self.image = cv2.imread(image_path)
        self.set_image(None)
        self._background_color = QColor(background_color[0], background_color[1], background_color[2])  # Default to white background
        self.setMinimumSize(100, 100)

    def set_background_color(self, color):
        self._background_color = color
        self.set_image(self.image)

    def get_background_color(self):
        return self._background_color
        
    def set_image(self, image= None):
        W = self.frame.width()
        H = self.frame.height()
        if image is not None:
            self.image = image.copy()
            self.image_label.setFixedSize(W, H)
            # convert the image from BGR to RGB format
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            # resize the image to fit the frame
            image  = letterbox(image, new_shape=(W*2, H*2), color=self._background_color.getRgb())[0]
            # get the width, height, and bytes per line of the image
            height, width, channel = image.shape
            bytes_per_line = channel * width
            q_img = QImage(image.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)

            pixmap = QPixmap.fromImage(q_img)
            self.image_label.setPixmap(pixmap)
            self.image_label.setScaledContents(True)
        else:
            self.image_label.setText("No image loaded")
            # center the label in the frame
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # On resize, update the image size
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.set_image(self.image)

    background_color = pyqtProperty(QColor, get_background_color, set_background_color)