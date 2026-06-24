import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

class CustomComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_opened = False
        
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
                border: 2px solid #3498db;
                border-radius: 8px;
                padding: 8px 12px;
                padding-right: 40px;
                font-size: 14px;
                background-color: white;
                color: #2c3e50;
                min-height: 20px;
            }}
            
            QComboBox:hover {{
                border: 2px solid #2980b9;
                background-color: #f8f9fa;
            }}
            
            QComboBox:focus {{
                border: 2px solid #e74c3c;
                outline: none;
            }}
            
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left: 1px solid #bdc3c7;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                background-color: #ecf0f1;
            }}
            
            QComboBox::drop-down:hover {{
                background-color: #d5dbdb;
            }}
            
            QComboBox::down-arrow {{
                width: 0px;
                height: 0px;
                border: none;
                background: none;
            }}
            
            QComboBox QAbstractItemView {{
                border: 2px solid #3498db;
                border-radius: 8px;
                background-color: white;
                selection-background-color: #3498db;
                selection-color: white;
                padding: 4px;
            }}
            
            QComboBox QAbstractItemView::item {{
                height: 40px;
                padding: 8px;
                border-radius: 4px;
                margin: 2px;
            }}
            
            QComboBox QAbstractItemView::item:hover {{
                background-color: #ebf3fd;
                color: #2c3e50;
            }}
            
            QComboBox QAbstractItemView::item:selected {{
                background-color: #3498db;
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
        arrow_rect = QRect(rect.width() - 25, rect.y(), 20, rect.height())
        
        # Màu mũi tên
        painter.setPen(QPen(QColor("#3498db"), 2))
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

class CustomItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Lấy icon và text
        icon = index.data(Qt.DecorationRole)
        text = index.data(Qt.DisplayRole)
        
        # Thiết lập màu nền
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#3498db"))
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

class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Custom ComboBox Demo")
        self.setGeometry(100, 100, 500, 400)
        
        # Widget chính
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Tiêu đề
        title = QLabel("Custom ComboBox với Icon")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 20px;
            }
        """)
        layout.addWidget(title)
        
        # ComboBox 1 - Với icon màu sắc
        label1 = QLabel("Chọn màu sắc:")
        label1.setStyleSheet("font-size: 14px; font-weight: bold; color: #34495e;")
        layout.addWidget(label1)
        
        self.combo1 = CustomComboBox()
        self.combo1.setFixedHeight(50)
        
        # Tạo icon màu sắc
        colors = [
            ("#e74c3c", "Đỏ"),
            ("#3498db", "Xanh dương"),
            ("#2ecc71", "Xanh lá"),
            ("#f39c12", "Cam"),
            ("#9b59b6", "Tím"),
            ("#1abc9c", "Xanh ngọc")
        ]
        
        for color, name in colors:
            pixmap = QPixmap(24, 24)
            pixmap.fill(QColor(color))
            self.combo1.addItemWithPixmap(pixmap, name, color)
        
        layout.addWidget(self.combo1)
        
        # ComboBox 2 - Với icon file
        label2 = QLabel("Chọn hành động:")
        label2.setStyleSheet("font-size: 14px; font-weight: bold; color: #34495e;")
        layout.addWidget(label2)
        
        self.combo2 = CustomComboBox()
        self.combo2.setFixedHeight(50)
        
        # Tạo icon từ symbol
        actions = [
            ("📁", "Mở file"),
            ("💾", "Lưu file"),
            ("✂️", "Cắt"),
            ("📋", "Sao chép"),
            ("📄", "Dán"),
            ("🗑️", "Xóa")
        ]
        
        for symbol, text in actions:
            # Tạo icon từ text symbol
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setFont(QFont("Arial", 16))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, symbol)
            painter.end()
            
            self.combo2.addItemWithPixmap(pixmap, text, text)
        
        layout.addWidget(self.combo2)
        
        # ComboBox 3 - Với hình dạng
        label3 = QLabel("Chọn hình dạng:")
        label3.setStyleSheet("font-size: 14px; font-weight: bold; color: #34495e;")
        layout.addWidget(label3)
        
        self.combo3 = CustomComboBox()
        self.combo3.setFixedHeight(50)
        
        shapes = [
            ("Hình vuông", self.createShapeIcon("square")),
            ("Hình tròn", self.createShapeIcon("circle")),
            ("Hình tam giác", self.createShapeIcon("triangle")),
            ("Hình sao", self.createShapeIcon("star")),
            ("Hình thoi", self.createShapeIcon("diamond"))
        ]
        
        for text, pixmap in shapes:
            self.combo3.addItemWithPixmap(pixmap, text, text)
        
        layout.addWidget(self.combo3)
        
        # Kết nối signals
        self.combo1.currentTextChanged.connect(self.onCombo1Changed)
        self.combo2.currentTextChanged.connect(self.onCombo2Changed)
        self.combo3.currentTextChanged.connect(self.onCombo3Changed)
        
        # Thêm spacer
        layout.addStretch()
        
        # Thiết lập style cho window
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f6fa;
            }
        """)
        
    def createShapeIcon(self, shape_type):
        """Tạo icon hình dạng"""
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Thiết lập pen và brush
        pen = QPen(QColor("#3498db"), 2)
        brush = QBrush(QColor("#3498db"))
        painter.setPen(pen)
        painter.setBrush(brush)
        
        rect = QRect(2, 2, 20, 20)
        
        if shape_type == "square":
            painter.drawRect(rect)
        elif shape_type == "circle":
            painter.drawEllipse(rect)
        elif shape_type == "triangle":
            points = [
                QPoint(12, 4),
                QPoint(4, 20),
                QPoint(20, 20)
            ]
            painter.drawPolygon(points)
        elif shape_type == "star":
            # Vẽ sao 5 cánh
            center = QPoint(12, 12)
            outer_radius = 10
            inner_radius = 4
            
            points = []
            for i in range(10):
                angle = i * 36 * 3.14159 / 180
                if i % 2 == 0:
                    radius = outer_radius
                else:
                    radius = inner_radius
                
                x = center.x() + radius * cos(angle - 3.14159/2)
                y = center.y() + radius * sin(angle - 3.14159/2)
                points.append(QPoint(int(x), int(y)))
            
            painter.drawPolygon(points)
        elif shape_type == "diamond":
            points = [
                QPoint(12, 4),
                QPoint(20, 12),
                QPoint(12, 20),
                QPoint(4, 12)
            ]
            painter.drawPolygon(points)
        
        painter.end()
        return pixmap
    
    def onCombo1Changed(self, text):
        print(f"Màu sắc được chọn: {text}")
        
    def onCombo2Changed(self, text):
        print(f"Hành động được chọn: {text}")
        
    def onCombo3Changed(self, text):
        print(f"Hình dạng được chọn: {text}")

# Import thêm cho tính toán góc và regex
from math import cos, sin
import re

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec_())