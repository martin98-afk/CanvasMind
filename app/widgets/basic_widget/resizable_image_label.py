from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QSizePolicy
from qfluentwidgets import ImageLabel

from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap


class ResizableImageLabel(QLabel):
    """能严格按父容器宽度自适应缩放的图片标签，高度按比例计算，支持最大高度限制"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_pixmap = QPixmap()
        self._max_height = 200
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(False)
        self.setTextFormat(Qt.PlainText)
        # ✅ 关键：允许水平/垂直扩展，并忽略最小尺寸限制
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumSize(1, 1)  # 防止被 layout 压成 0

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

        # 获取当前可用宽度（关键！）
        available_width = self.width()
        if available_width <= 1:
            return

        # 按宽度缩放，保持比例
        scaled = self._original_pixmap.scaledToWidth(available_width, Qt.SmoothTransformation)

        # 限制最大高度
        if scaled.height() > self._max_height:
            scaled = scaled.scaledToHeight(self._max_height, Qt.SmoothTransformation)

        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # ✅ 关键：延迟 0ms 执行，确保 width() 是最新值
        QTimer.singleShot(0, self._update_pixmap)

    # ✅ 可选：让布局系统知道“我的高度依赖宽度”
    def hasHeightForWidth(self) -> bool:
        return not self._original_pixmap.isNull()

    def heightForWidth(self, w: int) -> int:
        if self._original_pixmap.isNull():
            return 80  # fallback 高度
        # 计算理想高度
        ratio = self._original_pixmap.height() / self._original_pixmap.width()
        ideal_h = int(w * ratio)
        return min(ideal_h, self._max_height)