# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import QSplitter, QSplitterHandle


class ModernSplitterHandle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hovered = False
        self._pressed = False

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 根据状态设置颜色
        if self._pressed:
            bg_color = QColor("#0078D4")  # 蓝色
            border_color = QColor("#0096D6")
        elif self._hovered:
            bg_color = QColor("#0078D4")  # 蓝色
            border_color = QColor("#0096D6")
        else:
            # 未hover和select状态下背景透明，只显示虚线
            bg_color = QColor(0, 0, 0, 0)  # 完全透明
            border_color = QColor("#0096D6")

        # 绘制背景（透明）
        painter.fillRect(self.rect(), bg_color)

        # 设置虚线画笔
        pen = QPen(border_color, 1)
        pen.setStyle(Qt.DashLine)  # 设置为虚线样式
        pen.setDashPattern([16, 8])  # 虚线模式：4像素线段，4像素间隔
        painter.setPen(pen)

        # 绘制虚线分隔线
        if self.orientation() == Qt.Horizontal:
            # 水平分割器，绘制垂直虚线
            center_x = self.width() // 2
            painter.drawLine(center_x, 0, center_x, self.height())
        else:
            # 垂直分割器，绘制水平虚线
            center_y = self.height() // 2
            painter.drawLine(0, center_y, self.width(), center_y)


class ModernSplitter(QSplitter):
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setHandleWidth(6)  # 设置手柄宽度

    def createHandle(self):
        return ModernSplitterHandle(self.orientation(), self)