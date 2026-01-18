from PyQt5 import QtGui
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import pyqtSignal, Qt, QRect
from PyQt5.QtGui import QPainter, QColor


def format_time(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:04.1f}"


class RangeSlider(QWidget):
    sliderMoved = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.min_val = 0.0
        self.max_val = 1.0
        self.total_duration = 0.0  # 总时长（秒）
        self.setFixedHeight(35)  # 稍微加高以容纳文字

        self._active_handle = None
        self.highlight_color = QColor("#00A6FF")
        self.handle_color = QColor("#DDDDDD")

    def set_duration(self, duration):
        self.total_duration = duration
        self.update()

    def _val_to_pos(self, val):
        return int(val * (self.width() - 20)) + 10

    def _pos_to_val(self, pos):
        val = (pos - 10) / (self.width() - 20)
        return max(0.0, min(1.0, val))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cy = h - 10  # 轨道靠下绘制，上方留给文字

        # 绘制背景轨道
        painter.setBrush(QColor("#111"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(5, cy - 3, w - 10, 6, 3, 3)

        # 绘制选中区间
        x1 = self._val_to_pos(self.min_val)
        x2 = self._val_to_pos(self.max_val)
        painter.setBrush(self.highlight_color)
        painter.drawRect(x1, cy - 2, x2 - x1, 4)

        # 绘制把手
        painter.setBrush(self.handle_color)
        painter.drawEllipse(x1 - 6, cy - 6, 12, 12)
        painter.drawEllipse(x2 - 6, cy - 6, 12, 12)

        # --- 核心：绘制时间文字 ---
        if self.total_duration > 0:
            t_start = format_time(self.min_val * self.total_duration)
            t_end = format_time(self.max_val * self.total_duration)
            t_range = f"{t_start} - {t_end}"

            painter.setPen(QColor("#AAA"))
            painter.setFont(QtGui.QFont("Consolas", 9))
            # 在控件顶部居中绘制时间范围
            painter.drawText(QRect(0, 0, w, 15), Qt.AlignCenter, t_range)

    def mousePressEvent(self, event):
        pos = event.x()
        v = self._pos_to_val(pos)
        if abs(v - self.min_val) < abs(v - self.max_val):
            self._active_handle = 'min'
            self.min_val = min(v, self.max_val - 0.01)
        else:
            self._active_handle = 'max'
            self.max_val = max(v, self.min_val + 0.01)
        self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._active_handle:
            v = self._pos_to_val(event.x())
            if self._active_handle == 'min':
                self.min_val = min(v, self.max_val - 0.02)
            else:
                self.max_val = max(v, self.min_val + 0.02)
            self.update()
            self.sliderMoved.emit(self.min_val, self.max_val)

    def mouseReleaseEvent(self, event):
        self._active_handle = None