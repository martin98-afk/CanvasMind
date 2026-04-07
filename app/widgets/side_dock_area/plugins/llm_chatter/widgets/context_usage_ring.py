from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QWidget,
)


class ContextUsageRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._percent = 0
        self._ring_color = QColor("#5aa9ff")
        self._track_color = QColor(255, 255, 255, 40)
        self.setFixedSize(18, 18)
        self.setToolTip("上下文占用：0%")

    def set_usage(self, percent: int, used_tokens: int, budget_tokens: int):
        self._percent = max(0, min(100, int(percent)))
        if self._percent >= 90:
            self._ring_color = QColor("#ff6b6b")
        elif self._percent >= 70:
            self._ring_color = QColor("#f6c453")
        else:
            self._ring_color = QColor("#5aa9ff")

        self.setToolTip(
            f"当前上下文占用\n已用: {used_tokens} tokens\n预算: {budget_tokens} tokens\n占比: {self._percent}%"
        )
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        start_angle = 90 * 16
        span_angle = int(-360 * 16 * (self._percent / 100.0))

        track_pen = QPen(self._track_color, 2.2)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        ring_pen = QPen(self._ring_color, 2.2)
        painter.setPen(ring_pen)
        painter.drawArc(rect, start_angle, span_angle)