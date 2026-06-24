import os
from PyQt5.QtDesigner import QPyDesignerCustomWidgetPlugin
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt
from monkez_image import MonkezImage

class MonkezButtonPlugin(QPyDesignerCustomWidgetPlugin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initialized = False

    def initialize(self, core):
        self.initialized = True

    def isInitialized(self):
        return self.initialized

    def createWidget(self, parent):
        return MonkezImage(parent)

    def name(self):
        return "MonkezImage"

    def group(self):
        return "Monkez Widgets"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "monkez_assets/icons", "MonkezImage.jpg")
        icon = QIcon(QPixmap(icon_path).scaled(64, 64))
        return icon

    def toolTip(self):
        return "Image display widget with customizable background color and resizing"

    def whatsThis(self):
        return "A widget that displays images with options for resizing and background color"

    def isContainer(self):
        return False

    def includeFile(self):
        return "monkez_image"
