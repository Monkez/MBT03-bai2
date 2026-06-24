import os
from PyQt5.QtDesigner import QPyDesignerCustomWidgetPlugin
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt
from monkez_usb_camera import MonkezUSBCamera

class MonkezButtonPlugin(QPyDesignerCustomWidgetPlugin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initialized = False

    def initialize(self, core):
        self.initialized = True

    def isInitialized(self):
        return self.initialized

    def createWidget(self, parent):
        return MonkezUSBCamera(parent)

    def name(self):
        return "MonkezUSBCamera"

    def group(self):
        return "Monkez Widgets"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "monkez_assets/icons", "Camera.png")
        icon = QIcon(QPixmap(icon_path).scaled(64, 64))
        return icon

    def toolTip(self):
        return "USB Camera widget with customizable background color and resizing"

    def whatsThis(self):
        return "A widget that displays images from a USB camera with options for resizing and background color"

    def isContainer(self):
        return False

    def includeFile(self):
        return "monkez_usb_camera"
