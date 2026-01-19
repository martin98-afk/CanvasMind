# -*- coding: utf-8 -*-
import os
import numpy as np
from PIL import Image
from Qt import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QImage, QPainter

# -*- coding: utf-8 -*-
import os
import numpy as np
from PIL import Image
from Qt import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QImage, QPainter


class GalleryImageItem(QtWidgets.QWidget):
    """单个图像块"""

    def __init__(self, q_img, size, parent=None):
        super().__init__(parent)
        self._q_image = q_img
        self._fixed_size = size
        self.setFixedSize(size)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def update_size(self, new_size):
        self._fixed_size = new_size
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
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 数据存储
        self._image_list_data = []  # 存储原始 QImage 列表
        self._cols = 2
        self._item_w = 150

        # 布局
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. 控制栏
        self.ctrl_bar = QtWidgets.QWidget()
        self.ctrl_bar.setFixedHeight(30)
        self.ctrl_bar.setStyleSheet("background: rgba(40, 40, 40, 150); color: #ccc; font-size: 10px;")
        ctrl_layout = QtWidgets.QHBoxLayout(self.ctrl_bar)
        ctrl_layout.setContentsMargins(5, 0, 5, 0)

        # 列数控制
        ctrl_layout.addWidget(QtWidgets.QLabel("Cols:"))
        self.spin_cols = QtWidgets.QSpinBox()
        self.spin_cols.setRange(1, 10)
        self.spin_cols.setValue(self._cols)
        self.spin_cols.setFixedWidth(40)
        self.spin_cols.valueChanged.connect(self._on_config_changed)
        ctrl_layout.addWidget(self.spin_cols)

        # 大小控制
        ctrl_layout.addWidget(QtWidgets.QLabel("Size:"))
        self.slider_size = QtWidgets.QSlider(Qt.Horizontal)
        self.slider_size.setRange(50, 400)
        self.slider_size.setValue(self._item_w)
        self.slider_size.valueChanged.connect(self._on_config_changed)
        ctrl_layout.addWidget(self.slider_size)

        # 2. 滚动区域
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.container)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll_area.setWidget(self.container)

        self.main_layout.addWidget(self.ctrl_bar)
        self.main_layout.addWidget(self.scroll_area)

        # 初始大小
        self._current_size = QSize(350, 250)
        self.setFixedSize(self._current_size)
        self.ctrl_bar.setVisible(False)

    def _on_config_changed(self):
        """当列数或大小时改变时刷新布局"""
        self._cols = self.spin_cols.value()
        self._item_w = self.slider_size.value()
        self._refresh_gallery()

    def _clear_layout(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _convert_to_qimage(self, data):
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

    def set_value(self, image_list):
        """设置新数据"""
        self._image_list_data = []
        if isinstance(image_list, (list, tuple)):
            for img in image_list:
                q_img = self._convert_to_qimage(img)
                if q_img:
                    self._image_list_data.append(q_img)

        # 只有有图时才显示控制栏
        has_images = len(self._image_list_data) > 0
        self.ctrl_bar.setVisible(has_images)
        self._refresh_gallery()

    def _refresh_gallery(self):
        """根据当前的 _cols 和 _item_w 重新构建布局"""
        self._clear_layout()

        if not self._image_list_data:
            self._current_size = QSize(200, 150)
            self.setFixedSize(self._current_size)
            self.sizeHintChanged.emit()
            return

        item_size = QSize(self._item_w, self._item_w)
        for i, q_img in enumerate(self._image_list_data):
            item_widget = GalleryImageItem(q_img, item_size)
            self.grid_layout.addWidget(item_widget, i // self._cols, i % self._cols)

        # 计算总高度和宽度，用于更新 Node 节点的大小
        rows = (len(self._image_list_data) + self._cols - 1) // self._cols

        # 计算理想宽度：列数 * (项宽 + 间距) + 边距 + 滚动条预留
        ideal_w = self._cols * (self._item_w + self.grid_layout.spacing()) + 30
        # 计算理想高度：行数 * (项高 + 间距) + 边距 + 控制栏高度
        ideal_h = rows * (self._item_w + self.grid_layout.spacing()) + 50

        # 限制最大显示尺寸，防止 Node 过大
        target_w = max(200, min(10000, ideal_w))
        target_h = max(150, min(1000, ideal_h))

        self._current_size = QSize(target_w, target_h)
        self.setFixedSize(self._current_size)
        self.sizeHintChanged.emit()

    def sizeHint(self):
        return self._current_size