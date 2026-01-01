# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel, QSizePolicy


class ResizableImageLabel(QLabel):
    """能严格按父容器宽度自适应缩放的图片标签，高度按比例计算，支持最大高度限制"""

    clicked = pyqtSignal()  # ✅ 自定义点击信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_pixmap = QPixmap()
        self._max_height = 200
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(False)
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumSize(1, 1)
        self.setCursor(Qt.PointingHandCursor)  # ✅ 视觉反馈

    def setOriginalPixmap(self, pixmap: QPixmap):
        self._original_pixmap = pixmap if not pixmap.isNull() else QPixmap()
        self._update_pixmap()

    def setMaxHeight(self, h: int):
        self._max_height = max(50, h)
        self._update_pixmap()

    def _update_pixmap(self):
        if self._original_pixmap.isNull():
            self.setText("⚠️ 无预览图")
            self.setStyleSheet("color: #888; font-size: 12px;")
            return

        available_width = self.width()
        if available_width <= 1:
            return

        scaled = self._original_pixmap.scaledToWidth(available_width, Qt.SmoothTransformation)
        if scaled.height() > self._max_height:
            scaled = scaled.scaledToHeight(self._max_height, Qt.SmoothTransformation)

        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_pixmap)

    def hasHeightForWidth(self) -> bool:
        return not self._original_pixmap.isNull()

    def heightForWidth(self, w: int) -> int:
        if self._original_pixmap.isNull():
            return 80
        ratio = self._original_pixmap.height() / self._original_pixmap.width()
        ideal_h = int(w * ratio)
        return min(ideal_h, self._max_height)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()