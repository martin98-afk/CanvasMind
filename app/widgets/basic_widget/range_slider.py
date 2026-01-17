from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import pyqtSignal, Qt, QRect
from PyQt5.QtGui import QPainter, QColor


class RangeSlider(QWidget):
    # 发送 (min_percent, max_percent) 范围，0.0-1.0
    sliderMoved = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.min_val = 0.0
        self.max_val = 1.0
        self.setFixedHeight(20)
        self.setCursor(Qt.PointingHandCursor)

        # 样式配置
        self.bg_color = QColor("#111")
        self.handle_color = QColor("#555")
        self.groove_color = QColor("#00A6FF")  # 选中部分的颜色

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cy = h // 2

        # 绘制背景轨道
        painter.setBrush(self.bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, cy - 2, w, 4, 2, 2)

        # 绘制选中高亮轨道
        x_start = int(self.min_val * w)
        x_end = int(self.max_val * w)
        painter.setBrush(self.groove_color)
        painter.drawRect(x_start, cy - 2, x_end - x_start, 4)

        # 绘制两个把手
        painter.setBrush(self.handle_color)
        painter.drawEllipse(x_start - 5, cy - 5, 10, 10)
        painter.drawEllipse(x_end - 5, cy - 5, 10, 10)

    def mouseMoveEvent(self, event):
        pos = max(0, min(event.x(), self.width()))
        val = pos / self.width()

        # 判断离哪个把手近就移动哪个
        if abs(val - self.min_val) < abs(val - self.max_val):
            self.min_val = min(val, self.max_val - 0.05)
        else:
            self.max_val = max(val, self.min_val + 0.05)

        self.update()
        self.sliderMoved.emit(self.min_val, self.max_val)

    def mousePressEvent(self, event):
        self.mouseMoveEvent(event)