from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QSizePolicy
from qfluentwidgets import ImageLabel


class ResizableImageLabel(ImageLabel):
    """可随容器宽度自动缩放的图片标签，保持宽高比，限制最大高度"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._original_pixmap = QPixmap()
        self._max_height = 200  # 可根据需要调整
        self.setMinimumWidth(0)
        self.setAlignment(Qt.AlignCenter)

    def setOriginalPixmap(self, pixmap: QPixmap):
        self._original_pixmap = pixmap
        self._update_scaled_pixmap()

    def setMaxHeight(self, h: int):
        self._max_height = h
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if self._original_pixmap.isNull():
            self.setText("⚠️ 无预览图")
            self.setStyleSheet("color: #888; font-size: 12px;")
            return

        # 获取当前可用宽度（减去边距）
        width = self.width()
        if width <= 1:
            return

        # 按宽度缩放，保持比例
        scaled = self._original_pixmap.scaledToWidth(width, Qt.SmoothTransformation)
        
        # 限制最大高度
        if scaled.height() > self._max_height:
            scaled = scaled.scaled(self._max_height * scaled.width() // scaled.height(),
                                   self._max_height,
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)

        super().setPixmap(scaled)
        self.setScaledContents(False)  # ImageLabel 默认可能开启，关闭以避免双重缩放

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()