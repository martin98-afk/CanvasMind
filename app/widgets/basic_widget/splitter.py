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
            bg_color = QColor("#444444")  # 默认灰色
            border_color = QColor("#555555")

        # 绘制背景
        painter.fillRect(self.rect(), bg_color)

        # 绘制边框
        pen = QPen(border_color, 1)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # 绘制分隔线上的小点（可选）
        if self.orientation() == Qt.Horizontal:
            # 垂直方向的分隔线上画水平排列的小点
            center_y = self.height() // 2
            for i in range(0, self.height(), 6):
                if i + 2 <= self.height():
                    painter.fillRect(self.width() // 2 - 1, i, 2, 2, QColor("#888888"))
        else:
            # 水平方向的分隔线上画垂直排列的小点
            center_x = self.width() // 2
            for i in range(0, self.width(), 6):
                if i + 2 <= self.width():
                    painter.fillRect(i, self.height() // 2 - 1, 2, 2, QColor("#888888"))


class ModernSplitter(QSplitter):
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setHandleWidth(6)  # 设置手柄宽度

    def createHandle(self):
        return ModernSplitterHandle(self.orientation(), self)