import os
from PyQt5.QtWidgets import QLineEdit, QGraphicsDropShadowEffect
from PyQt5.QtCore import pyqtProperty, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QPainter, QCursor

class MonkezTextInput(QLineEdit):
    trailingIconClicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Monkez input text...")
        self.setMinimumSize(200, 30)

        self.inference = False

        self._radius = 10
        self._bg_color = QColor(255, 255, 255, 255)
        self._text_color = QColor("black")
        self._padding = 5
        

        # Thêm hiệu ứng shadow
        self._shadow_enabled = True
        self._shadow_blur = 10
        self._shadow_offset_x = 2
        self._shadow_offset_y = 2
        self._shadow_color = QColor(0, 0, 0, 100)

        # leading icon
        self._leading_icon_name = None
        self._leading_icon_size = 16
        self.leading_icon = None

        # Trailing icon
        self._trailing_icon_name = None
        self._trailing_size = 20
        self.trailing_icon = None
        self.trailing_hovered = False
        self.trailing_rect = None
        self.updateStyle()

    def set_inference(self):
        self.inference = True
        self.setLeadingIcon(self.leadingIcon)
        self.setTrailingIcon(self.trailingIcon)

    def mousePressEvent(self, event):
        if (self.trailing_rect and 
            self.trailing_rect.contains(event.pos())):
            self.trailingIconClicked.emit()
            print("Trailing icon clicked!")  # Debug
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Xử lý hover effect"""
        if self.trailing_rect:
            if self.trailing_rect.contains(event.pos()):
                if not self.trailing_hovered:
                    self.trailing_hovered = True
                    self.setCursor(QCursor(Qt.PointingHandCursor))
                    self.update()
            else:
                if self.trailing_hovered:
                    self.trailing_hovered = False
                    self.setCursor(QCursor(Qt.IBeamCursor))
                    self.update()

    def leaveEvent(self, event):
        """Reset hover khi chuột rời khỏi widget"""
        if self.trailing_hovered:
            self.trailing_hovered = False
            self.setCursor(QCursor(Qt.IBeamCursor))
            self.update()
        super().leaveEvent(event)

    def setPadding(self, padding):
        self._padding = padding
        self.updateStyle()

    def getPadding(self):
        return self._padding

    def setLeadingIcon(self, icon_name):
        self._leading_icon_name =  icon_name
        self.applyLeadingIcon()
        
    def getLeadingIcon(self):
        return self._leading_icon_name
    
    def setLeadingIconSize(self, size):
        self._leading_icon_size = size
        self.applyLeadingIcon()

    def getLeadingIconSize(self):
        return self._leading_icon_size
    
    def applyLeadingIcon(self):
        prerfix_path = "MonkezCustomWidgets/" if self.inference else ""
        self.leading_icon = QPixmap(prerfix_path+"monkez_assets/icons/" + self._leading_icon_name).scaled(self.leadingIconSize, self.leadingIconSize, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.updateStyle()
    
    def setTrailingIcon(self, icon_name):
        self._trailing_icon_name = icon_name
        self.applyTrailingIcon()

    def getTrailingIcon(self):
        return self._trailing_icon_name
    
    def setTrailingIconSize(self, size):
        self._trailing_size = size
        self.applyTrailingIcon()

    def getTrailingIconSize(self):
        return self._trailing_size
    
    def applyTrailingIcon(self):
        prerfix_path = "MonkezCustomWidgets/" if self.inference else ""
        self.trailing_icon = QPixmap(prerfix_path + "monkez_assets/icons/"+self._trailing_icon_name).scaled(self.trailingIconSize, self.trailingIconSize, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.updateStyle()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        
        painter = QPainter(self)
        
        # Vẽ leading icon
        if self.leading_icon:
            y = (self.height() - self.leadingIconSize) // 2
            painter.drawPixmap(self.leadingIconSize//2, y, self.leading_icon)
            
            
        # Vẽ trailing icon
        if self.trailing_icon:
            y = (self.height() - self.trailingIconSize) // 2
            x = self.width() - self.trailingIconSize - 10
            self.trailing_rect = self.trailing_icon.rect()
            self.trailing_rect.moveTo(x, y)
            
            # Nếu hover thì vẽ icon to hơn
            if self.trailing_hovered:
                scaled_icon = self.trailing_icon.scaled(self.trailingIconSize+4, self.trailingIconSize+4, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawPixmap(x - 2, y - 2, scaled_icon)
            else:
                painter.drawPixmap(x, y, self.trailing_icon)



    def applyShadow(self):
        if self._shadow_enabled:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(self._shadow_blur)
            shadow.setOffset(self._shadow_offset_x, self._shadow_offset_y)
            shadow.setColor(self._shadow_color)
            self.setGraphicsEffect(shadow)
        else:
            self.setGraphicsEffect(None)
        

    def  updateStyle(self):
        padding_left = self._padding + (self._leading_icon_size + 8 if self._leading_icon_name else 0)
        padding_right = self._padding + (self._trailing_size + 15 if self._trailing_icon_name else 0)
        # Set the border radius
        self.setStyleSheet(f"""QLineEdit {{
    border-radius: {self._radius}px;
    background-color: {self._bg_color.name()};
    color: {self._text_color.name()};
    padding: {self._padding}px;
    padding-left: {padding_left}px;
    padding-right: {padding_right}px;
}}""")
        self.applyShadow()

    def getRadius(self): return self._radius
    def setRadius(self, value): self._radius = value; self.updateStyle()

    def getTextColor(self): return self._text_color
    def setTextColor(self, color): self._text_color = color; self.updateStyle()

    def getBackgroundColor(self): return self._bg_color
    def setBackgroundColor(self, color): self._bg_color = color; self.updateStyle()

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

    shadowEnabled = pyqtProperty(bool, getShadowEnabled, setShadowEnabled)
    shadowBlur = pyqtProperty(int, getShadowBlur, setShadowBlur)
    shadowOffsetX = pyqtProperty(int, getShadowOffsetX, setShadowOffsetX)
    shadowOffsetY = pyqtProperty(int, getShadowOffsetY, setShadowOffsetY)
    shadowColor = pyqtProperty(QColor, getShadowColor, setShadowColor)

    radius = pyqtProperty(int, fget=getRadius, fset=setRadius)
    textColor = pyqtProperty(QColor, fget=getTextColor, fset=setTextColor)
    backgroundColor = pyqtProperty(QColor, fget=getBackgroundColor, fset=setBackgroundColor)

    padding = pyqtProperty(int, fget=getPadding, fset=setPadding)

    leadingIcon = pyqtProperty(str, fget=getLeadingIcon, fset=setLeadingIcon)
    leadingIconSize = pyqtProperty(int, fget=getLeadingIconSize, fset=setLeadingIconSize)
    trailingIcon = pyqtProperty(str, fget=getTrailingIcon, fset=setTrailingIcon)
    trailingIconSize = pyqtProperty(int, fget=getTrailingIconSize, fset=setTrailingIconSize)