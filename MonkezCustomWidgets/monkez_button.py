from PyQt5.QtWidgets import QPushButton, QGraphicsDropShadowEffect
from PyQt5.QtCore import pyqtProperty, Qt
from PyQt5.QtGui import QColor

class MonkezButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._radius = 15
        self._buttonType = 'filled'
        self.setText("Button")

        # Default colors
        self._active_color = QColor(0, 170, 0,  255)
        self._deactive_color = QColor(170, 0, 0, 255)
        self._text_color = QColor("white")
        self._hover_text_color = QColor(255, 255, 0)
        self._isChecked = False

        # Thêm hiệu ứng shadow
        self._shadow_enabled = True
        self._shadow_blur = 10
        self._shadow_offset_x = 1
        self._shadow_offset_y = 1
        self._shadow_color = QColor(0, 0, 0, 100)

        self.applyShadow()

        # Set default size
        self.setMinimumSize(130, 40)

        self.setMouseTracking(True)
        self._hovered = False
        self._pressed = False
        self.updateStyle()

    def enterEvent(self, event):
        self._hovered = True
        self.updateStyle()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.updateStyle()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.updateStyle()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self.updateStyle()
        super().mouseReleaseEvent(event)

    def applyShadow(self):
        if self._shadow_enabled:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(self._shadow_blur)
            shadow.setOffset(self._shadow_offset_x, self._shadow_offset_y)
            shadow.setColor(self._shadow_color)
            self.setGraphicsEffect(shadow)
        else:
            self.setGraphicsEffect(None)

    def updateStyle(self):
        bg_color = self._active_color if self.isChecked else self._deactive_color
        bg_tuple_color = bg_color.getRgb()
        hover_color = QColor(min(bg_tuple_color[0]+10, 255), min(bg_tuple_color[1]+10, 255), min(bg_tuple_color[2]+10, 255), bg_color.alpha())
        pressed_color = QColor(max(bg_tuple_color[0]-10, 0), max(bg_tuple_color[1]-10, 0), max(bg_tuple_color[2]-10,  0), bg_color.alpha())   
        bg = bg_color
        text_color = self._text_color
        if self._pressed:
            bg = pressed_color
            
        elif self._hovered:
            bg = hover_color
            text_color = self._hover_text_color

        r, g, b, a = bg.red(), bg.green(), bg.blue(), bg.alpha()
        if self._buttonType == 'filled':
            style = f"""QPushButton {{
    border-radius: {self._radius}px;
    background-color: rgba({r}, {g}, {b}, {a});
    color: {text_color.name()};
    border: none;
}}"""
        elif self._buttonType == 'outlined':
            style = f"""QPushButton {{
    border-radius: {self._radius}px;
    background-color: white;
    color: {text_color.name()};
    border: 2px solid {self._deactive_color.name()};
}}"""
        elif self._buttonType == 'text':
            style = f"""QPushButton {{
    border-radius: {self._radius}px;
    background-color: transparent;
    color: {text_color.name()};
    border: none;
}}"""
        self.setStyleSheet(style)

    # Properties cho từng kiểu
    def isFilledButton(self):
        return self._buttonType == 'filled'

    def setFilledButton(self, checked):
        if checked:
            self._buttonType = 'filled'
            self.updateStyle()

    def isOutlinedButton(self):
        return self._buttonType == 'outlined'

    def setOutlinedButton(self, checked):
        if checked:
            self._buttonType = 'outlined'
            self.updateStyle()

    def isTextButton(self):
        return self._buttonType == 'text'

    def setTextButton(self, checked):
        if checked:
            self._buttonType = 'text'
            self.updateStyle()

    # --- Properties ---
    def setChecked(self, checked):
        self._isChecked = checked
        self.updateStyle()

    def getChecked(self):
        return self._isChecked
    
    def getRadius(self): return self._radius
    def setRadius(self, value): self._radius = value; self.updateStyle()

    def getActiveColor(self): return self._active_color
    def setActiveColor(self, color): self._active_color = color; self.updateStyle()

    def getDeactiveColor(self): return self._deactive_color
    def setDeactiveColor(self, color): self._deactive_color = color; self.updateStyle()

    def getTextColor(self): return self._text_color
    def setTextColor(self, color): self._text_color = color; self.updateStyle()

    def getHoverTextColor(self): return self._hover_text_color
    def setHoverTextColor(self, color): self._hover_text_color = color; self.updateStyle()

    def getShadowEnabled(self): return self._shadow_enabled
    def setShadowEnabled(self, enabled):
        self._shadow_enabled = enabled
        self.applyShadow()

    def getShadowBlur(self): return self._shadow_blur
    def setShadowBlur(self, val): self._shadow_blur = val; self.applyShadow()

    def getShadowOffsetX(self): return self._shadow_offset_x
    def setShadowOffsetX(self, val): self._shadow_offset_x = val; self.applyShadow()

    def getShadowOffsetY(self): return self._shadow_offset_y
    def setShadowOffsetY(self, val): self._shadow_offset_y = val; self.applyShadow()

    def getShadowColor(self): return self._shadow_color
    def setShadowColor(self, val): self._shadow_color = val; self.applyShadow()

    isChecked = pyqtProperty(bool, getChecked, setChecked)

    shadowEnabled = pyqtProperty(bool, getShadowEnabled, setShadowEnabled)
    shadowBlur = pyqtProperty(int, getShadowBlur, setShadowBlur)
    shadowOffsetX = pyqtProperty(int, getShadowOffsetX, setShadowOffsetX)
    shadowOffsetY = pyqtProperty(int, getShadowOffsetY, setShadowOffsetY)
    shadowColor = pyqtProperty(QColor, getShadowColor, setShadowColor)

    radius = pyqtProperty(int, fget=getRadius, fset=setRadius)
    filledButton = pyqtProperty(bool, fget=isFilledButton, fset=setFilledButton)
    outlinedButton = pyqtProperty(bool, fget=isOutlinedButton, fset=setOutlinedButton)
    textButton = pyqtProperty(bool, fget=isTextButton, fset=setTextButton)


    ActiveColor = pyqtProperty(QColor, fget=getActiveColor, fset=setActiveColor)
    DeactiveColor = pyqtProperty(QColor, fget=getDeactiveColor, fset=setDeactiveColor)
    textColor = pyqtProperty(QColor, fget=getTextColor, fset=setTextColor)
    hoverTextColor = pyqtProperty(QColor, fget=getHoverTextColor, fset=setHoverTextColor)
