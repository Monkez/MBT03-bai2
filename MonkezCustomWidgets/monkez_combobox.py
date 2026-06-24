import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtCore import pyqtProperty, Qt

class CustomItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Lấy icon và text
        icon = index.data(Qt.DecorationRole)
        text = index.data(Qt.DisplayRole)
        
        # Thiết lập màu nền
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#4c4f5189"))
            text_color = QColor("white")
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor("#ebf3fd"))
            text_color = QColor("#2c3e50")
        else:
            text_color = QColor("#2c3e50")
        
        # Vẽ icon
        if icon and not icon.isNull():
            icon_size = 24
            icon_rect = QRect(
                option.rect.x() + 12,
                option.rect.y() + (option.rect.height() - icon_size) // 2,
                icon_size,
                icon_size
            )
            icon.paint(painter, icon_rect, Qt.AlignCenter)
            text_x = icon_rect.right() + 12
        else:
            text_x = option.rect.x() + 12
        
        # Vẽ text
        text_rect = QRect(
            text_x,
            option.rect.y(),
            option.rect.width() - text_x - 12,
            option.rect.height()
        )
        
        painter.setPen(text_color)
        painter.setFont(QFont("Arial", 12))
        painter.drawText(text_rect, Qt.AlignVCenter, text)

class MonkezComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_opened = False
        self._border_color = QColor("#5b8dae")
        self._background_color = QColor("white")
        self._hover_background_color = QColor("#f8f9fa")
        self._text_color = QColor("#2c3e50")
        self._hover_text_color = QColor("#3498db")

        self._boder_radius = 8
        
        # Tạo custom item delegate để hiển thị icon và text
        self.setItemDelegate(CustomItemDelegate())
        
        # Thiết lập style ban đầu
        self.updateStyles()
    
    def showPopup(self):
        """Override showPopup để cập nhật mũi tên khi mở dropdown"""
        self.is_opened = True
        self.updateStyles()
        super().showPopup()
    
    def hidePopup(self):
        """Override hidePopup để cập nhật mũi tên khi đóng dropdown"""
        self.is_opened = False
        self.updateStyles()
        super().hidePopup()
    
    def updateStyles(self):
        """Cập nhật style với mũi tên phù hợp"""
        # Tạo mũi tên bằng Unicode symbols
        if self.is_opened:
            arrow_char = "▲"  # Mũi tên lên
        else:
            arrow_char = "▼"  # Mũi tên xuống
        
        # Thiết lập style hoàn chỉnh
        self.setStyleSheet(f"""
            QComboBox {{
                border: 2px solid {self._border_color.name()};
                border-radius: {self._boder_radius}px;
                padding: 8px 12px;
                padding-right: 40px;
                background-color: {self._background_color.name()};
                color: {self._text_color.name()};
                min-height: 20px;
            }}
            
            QComboBox:hover {{
                background-color: {self._hover_background_color.name()};
                color: {self._hover_text_color.name()};
            }}  
            
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 35px;
                border-left: 0px solid {self._border_color.name()};
                border-top-right-radius: {self._boder_radius - 2}px;
                border-bottom-right-radius: {self._boder_radius - 2}px;
                background-color: {self._hover_background_color.name()};
            }}
            
            QComboBox::drop-down:hover {{
                background-color: {self._hover_background_color.name()};
            }}
            
            QComboBox::down-arrow {{
                width: 0px;
                height: 0px;
                border: none;
                background: none;
            }}
            
            QComboBox QAbstractItemView {{
                border: 2px solid {self._border_color.name()};
                border-radius: 0px;
                background-color: white;
                selection-background-color: {self._hover_background_color.name()};
                selection-color: white;
                padding: 4px;
            }}
            
            QComboBox QAbstractItemView::item {{
                height: 30px;
                padding: 8px;
                border-radius: 4px;
                margin: 2px;
            }}
            
            QComboBox QAbstractItemView::item:hover {{
                background-color: {self._hover_background_color.name()};
                color: #2c3e50;
            }}
            
            QComboBox QAbstractItemView::item:selected {{
                background-color: {self._hover_background_color.name()};
                color: white;
            }}
        """)
        
        # Vẽ mũi tên custom
        self.update()
    
    def paintEvent(self, event):
        """Override paintEvent để vẽ mũi tên custom"""
        super().paintEvent(event)
        
        # Vẽ mũi tên
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Vị trí mũi tên
        rect = self.rect()
        arrow_rect = QRect(rect.width() - 30, rect.y(), 20, rect.height())
        
        # Màu mũi tên
        painter.setPen(QPen(QColor("#000000"), 2))
        painter.setFont(QFont("Arial", 12))
        
        # Vẽ mũi tên
        if self.is_opened:
            arrow_char = "▲"
        else:
            arrow_char = "▼"
        
        painter.drawText(arrow_rect, Qt.AlignCenter, arrow_char)
        painter.end()
        
    def addItemWithIcon(self, icon_path, text, data=None):
        """Thêm item với icon và text"""
        icon = QIcon(icon_path)
        self.addItem(icon, text, data)
        
    def addItemWithPixmap(self, pixmap, text, data=None):
        """Thêm item với pixmap và text"""
        icon = QIcon(pixmap)
        self.addItem(icon, text, data)

    def getBorderColor(self): return self._border_color
    def setBorderColor(self, color): self._border_color = QColor(color); self.updateStyles()

    def getBackgroundColor(self): return self._background_color
    def setBackgroundColor(self, color): self._background_color = QColor(color); self.updateStyles()

    def getHoverBackgroundColor(self): return self._hover_background_color
    def setHoverBackgroundColor(self, color): self._hover_background_color = QColor(color); self.updateStyles()

    def getTextColor(self): return self._text_color
    def setTextColor(self, color): self._text_color = QColor(color); self.updateStyles()

    def getHoverTextColor(self): return self._hover_text_color
    def setHoverTextColor(self, color): self._hover_text_color = QColor(color); self.updateStyles()

    def getBoderRadius(self): return self._boder_radius
    def setBoderRadius(self, radius): self._boder_radius = radius; self.updateStyles()

    boderColor = pyqtProperty(QColor, getBorderColor, setBorderColor)
    backgroundColor = pyqtProperty(QColor, getBackgroundColor, setBackgroundColor)  
    hoverBackgroundColor = pyqtProperty(QColor, getHoverBackgroundColor, setHoverBackgroundColor)
    textColor = pyqtProperty(QColor, getTextColor, setTextColor)
    hoverTextColor = pyqtProperty(QColor, getHoverTextColor, setHoverTextColor)
    boderRadius = pyqtProperty(int, getBoderRadius, setBoderRadius)

    

