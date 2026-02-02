# -*- coding: utf-8 -*-
import os
import numpy as np
from PIL import Image
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QImage, QPainter

from app.widgets.node_widget.base import CustomNodeBaseWidget


class GalleryImageItem(QtWidgets.QWidget):
    """单个图像块"""

    def __init__(self, q_img, size, parent=None):
        super().__init__(parent)
        self._q_image = q_img
        self._current_size = size
        # Item 内部依然需要固定大小，以便 Grid 计算
        self.setFixedSize(size)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def update_size(self, new_size):
        if self.size() != new_size:
            self.setFixedSize(new_size)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        if self._q_image and not self._q_image.isNull():
            painter.drawImage(rect, self._q_image)
        else:
            painter.fillRect(rect, Qt.black)


class ImageGalleryWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, node=None):
        super().__init__(parent)
        self.node = node
        # 1. 设置自适应策略 (关键点)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self._items = []
        self._item_w = (node and node.get_property("_item_w")) or 150
        self._spacing = 10

        # 主布局
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 控制栏
        self.ctrl_bar = QtWidgets.QWidget()
        self.ctrl_bar.setFixedHeight(35)
        self.ctrl_bar.setStyleSheet("background: rgba(45, 45, 45, 200); border-bottom: 1px solid #111;")
        ctrl_layout = QtWidgets.QHBoxLayout(self.ctrl_bar)
        ctrl_layout.setContentsMargins(10, 0, 10, 0)

        self.slider_size = QtWidgets.QSlider(Qt.Horizontal)
        self.slider_size.setRange(60, 600)
        self.slider_size.setValue(self._item_w)
        self.slider_size.valueChanged.connect(self._on_slider_changed)
        ctrl_layout.addWidget(QtWidgets.QLabel("Scale:"))
        ctrl_layout.addWidget(self.slider_size)

        # 滚动区域 (关键点: 也要设置 Expanding)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.scroll_area.setStyleSheet("background-color: transparent;")

        self.container = QtWidgets.QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.grid_layout = QtWidgets.QGridLayout(self.container)
        self.grid_layout.setSpacing(self._spacing)
        self.grid_layout.setContentsMargins(self._spacing, self._spacing, self._spacing, self._spacing)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll_area.setWidget(self.container)

        self.main_layout.addWidget(self.ctrl_bar)
        self.main_layout.addWidget(self.scroll_area)

        self.ctrl_bar.setVisible(False)

    def _on_slider_changed(self, value):
        self._item_w = value
        if self.node:
            self.node.set_property("_item_w", self._item_w)
        self._relayout_gallery()

    def resizeEvent(self, event):
        """当节点被拉伸时，此方法会被自动触发"""
        super().resizeEvent(event)
        # 延迟一丁点处理排列，或者直接处理，确保容器宽度已更新
        self._relayout_gallery()

    def set_value(self, image_list):
        """设置数据并刷新"""
        self._clear_all()

        if not image_list:
            self.ctrl_bar.setVisible(False)
            return
        self.scroll_area.show()
        for img_data in image_list:
            q_img = self._convert_to_qimage(img_data)
            if q_img:
                item_widget = GalleryImageItem(q_img, QSize(self._item_w, self._item_w))
                self._items.append(item_widget)
                self.grid_layout.addWidget(item_widget)

        self.ctrl_bar.setVisible(len(self._items) > 0)
        self._relayout_gallery()

    def _relayout_gallery(self):
        """自适应排列核心算法"""
        if not self._items:
            return

        # 获取当前滚动区域的可视宽度
        available_w = self.scroll_area.viewport().width()
        if available_w <= 0: return

        # 计算列数：(可用宽度 - 边距) // (物品宽 + 间距)
        # 考虑两边的 margins
        margins = self.grid_layout.contentsMargins()
        net_width = available_w - margins.left() - margins.right()
        col_count = max(1, net_width // (self._item_w + self._spacing))

        self.grid_layout.setEnabled(False)
        item_size = QSize(self._item_w, self._item_w)

        for i, item in enumerate(self._items):
            item.update_size(item_size)
            row = i // col_count
            col = i % col_count
            self.grid_layout.addWidget(item, row, col)

        self.grid_layout.setEnabled(True)

    def _clear_all(self):
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._items = []
        self.scroll_area.hide()

    def _convert_to_qimage(self, data):
        """统一图像转换逻辑"""
        if data is None: return None
        try:
            if isinstance(data, np.ndarray):
                h, w = data.shape[:2]
                if data.ndim == 2:
                    return QImage(data.data, w, h, w, QImage.Format_Grayscale8).copy()
                else:
                    c = data.shape[2]
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
            print(f"Gallery Convert Error: {e}")
        return None

    def clear(self):
        """供外部手动调用的清空方法"""
        self.set_value([])


class ImageGalleryWidgetWrapper(CustomNodeBaseWidget):
    """
    包装器：将 ImageGalleryWidget 适配到节点编辑器系统中
    """

    def __init__(self, parent=None, name="", window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label_visible(False)

        self._image_widget = ImageGalleryWidget(parent=window)

        # 关键：手动设置包装层的 Policy
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.set_custom_widget(self._image_widget)

    def get_value(self):
        pass

    def set_value(self, value):
        self._image_widget.set_value(value)