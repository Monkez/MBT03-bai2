import os
from PyQt5.QtDesigner import QPyDesignerCustomWidgetPlugin
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt
from monkez_text_input import MonkezTextInput

class MonkezTextInputPlugin(QPyDesignerCustomWidgetPlugin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initialized = False

    def initialize(self, core):
        self.initialized = True

    def isInitialized(self):
        return self.initialized

    def createWidget(self, parent):
        return MonkezTextInput(parent)

    def name(self):
        return "MonkezTextInput"

    def group(self):
        return "Monkez Widgets"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "monkez_assets/icons", "MonkezTextInput.png")
        icon = QIcon(QPixmap(icon_path).scaled(64, 64))
        return icon

    def toolTip(self):
        return "Text input with customizable style"

    def whatsThis(self):
        return "A text input field that supports custom background color, text color, and shadow effects"

    def isContainer(self):
        return False

    def includeFile(self):
        return "monkez_text_input"
