# -*- coding: utf-8 -*-
import os
import numpy as np
from PIL import Image
from Qt import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QImage, QPainter


class GalleryImageItem(QtWidgets.QWidget):
    """Gallery 中的单个图像块，采用与 ImageWidget 一致的绘图逻辑以保证清晰度"""

    def __init__(self, q_img, size, parent=None):
        super().__init__(parent)
        self._q_image = q_img
        self.setFixedSize(size)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def paintEvent(self, event):
        painter = QPainter(self)
        # 核心：使用高质量渲染提示
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()
        painter.fillRect(rect, Qt.black)

        if self._q_image and not self._q_image.isNull():
            # 关键：像 ImageWidget 一样直接 drawImage 绘制原图
            painter.drawImage(rect, self._q_image)


class ImageGalleryWidget(QtWidgets.QScrollArea):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        # 内部容器
        self.container = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.container)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.setWidget(self.container)

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        # 初始默认大小
        self.setFixedSize(200, 150)
        self.setStyleSheet("background-color: transparent; border: none;")

    def _clear(self):
        """清理布局并销毁子控件"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        # 重置容器大小限制，允许回缩
        self.container.setMinimumSize(0, 0)
        self.container.setMaximumSize(16777215, 16777215)

    def _convert_to_qimage(self, data):
        """采用与 ImageWidget 完全一致的转换逻辑"""
        if data is None: return None
        try:
            if isinstance(data, np.ndarray):
                if data.ndim == 2:
                    h, w = data.shape
                    return QImage(data.data, w, h, w, QImage.Format_Grayscale8).copy()
                else:
                    h, w, c = data.shape
                    fmt = QImage.Format_RGB888 if c == 3 else QImage.Format_RGBA8888
                    return QImage(data.data, w, h, c * w, fmt).copy()
            elif isinstance(data, Image.Image):
                rgb_img = data.convert('RGB')
                return QImage(rgb_img.tobytes(), data.size[0], data.size[1], QImage.Format_RGB888).copy()
            elif isinstance(data, QImage):
                return data
            elif isinstance(data, str) and os.path.exists(data):
                return QImage(data)
        except Exception as e:
            print(f"Gallery 转换失败: {e}")
        return None

    def set_value(self, image_list):
        self._clear()

        if not isinstance(image_list, (list, tuple)) or not image_list:
            self.set_value_none()
            return
        self.container.show()
        cols = 2
        item_w = 180  # 单张图的逻辑显示宽度
        item_size = QSize(item_w, item_w)

        count = 0
        for img_data in image_list:
            q_img = self._convert_to_qimage(img_data)
            if q_img:
                # 使用自定义绘制 Item 代替 QLabel
                item_widget = GalleryImageItem(q_img, item_size)
                self.grid_layout.addWidget(item_widget, count // cols, count % cols)
                count += 1

        if count == 0:
            self.set_value_none()
        else:
            rows = (count + cols - 1) // cols
            # 动态计算总高度和宽度
            total_h = max(150, min(500, rows * (item_w + 10) + 20))
            total_w = cols * (item_w + 10) + 25

            self.setFixedSize(total_w, total_h)
            self.updateGeometry()
            self.sizeHintChanged.emit()

    def set_value_none(self):
        """恢复最初大小并强制内部容器收缩"""
        # 关键：先清空，再重置 FixedSize
        self.container.hide()
        self.setFixedSize(200, 150)
        # 强制内部容器也变小，否则 ScrollArea 可能回缩失败
        self.container.resize(180, 130)
        self.updateGeometry()
        self.sizeHintChanged.emit()

    def sizeHint(self):
        return self.size()