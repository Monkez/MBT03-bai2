import os
from PyQt5.QtDesigner import QPyDesignerCustomWidgetPlugin
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt
from monkez_combobox import MonkezComboBox

class MonkezComboBoxPlugin(QPyDesignerCustomWidgetPlugin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initialized = False

    def initialize(self, core):
        self.initialized = True

    def isInitialized(self):
        return self.initialized

    def createWidget(self, parent):
        return MonkezComboBox(parent)

    def name(self):
        return "MonkezComboBox"

    def group(self):
        return "Monkez Widgets"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "monkez_assets/icons", "MonkezButton.png")
        icon = QIcon(QPixmap(icon_path).scaled(64, 64))
        return icon

    def toolTip(self):
        return "A custom combo box with icon and text support"

    def whatsThis(self):
        return "This is a custom combo box widget that supports displaying icons and text."

    def isContainer(self):
        return False

    def includeFile(self):
        return "monkez_combobox"
