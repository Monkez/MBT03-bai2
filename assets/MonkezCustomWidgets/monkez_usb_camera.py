import cv2
import os
from monkez_image import MonkezImage

class MonkezUSBCamera(MonkezImage):
    def __init__(self, parent=None, background_color=(31, 31, 31)):
        super().__init__(parent, background_color, "monkez_assets/images/CameraOffline.png")

