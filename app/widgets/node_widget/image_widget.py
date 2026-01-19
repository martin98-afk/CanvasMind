# -*- coding: utf-8 -*-
import numpy as np
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from PyQt5.QtCore import Qt, QSize, QRect
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QFont
from Qt import QtWidgets, QtCore

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ImageWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None, default_image=None):
        super().__init__(parent)
        self._image_data = None
        self._q_image = None

        self._text_area_height = 20
        self._orig_w = 0
        self._orig_h = 0

        self._min_width = 200
        self._max_width = 500
        # 初始默认大小（不含文字区）
        self._current_size = QSize(200, 150)

        self.setAttribute(Qt.WA_OpaquePaintEvent)
        if default_image:
            self.set_value(default_image)

    def _convert_to_qimage(self, data):
        """将输入转为高质量 QImage"""
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
            elif isinstance(data, QPixmap):
                return data.toImage()
            elif isinstance(data, str):
                return QImage(data)
        except Exception as e:
            print(f"转换失败: {e}")
        return None

    def set_value(self, data):
        self._image_data = data
        new_q_img = self._convert_to_qimage(data)

        if new_q_img and not new_q_img.isNull():
            self._q_image = new_q_img
            self._orig_w = new_q_img.width()
            self._orig_h = new_q_img.height()

            target_w = max(self._min_width, min(self._orig_w, self._max_width))
            scale_ratio = target_w / float(self._orig_w)
            target_h = int(self._orig_h * scale_ratio)

            # 有图像：总高度 = 图片高度 + 文字区域高度
            self._current_size = QSize(target_w, target_h + self._text_area_height)
        else:
            # 无图像：清除数据，并恢复默认大小（不加文字高度）
            self._q_image = None
            self._orig_w = 0
            self._orig_h = 0
            self._current_size = QSize(200, 150)

        self.setFixedSize(self._current_size)
        self.sizeHintChanged.emit()
        self.update()
        self.valueChanged.emit(self._image_data)

    def get_value(self):
        return self._image_data

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()
        painter.fillRect(rect, Qt.transparent)

        # 核心逻辑：只有当 _q_image 存在时才绘制图片和文字
        if self._q_image:
            # 1. 绘制图片（预留底部文字空间）
            image_rect = QRect(0, 0, rect.width(), rect.height() - self._text_area_height)
            painter.drawImage(image_rect, self._q_image)

            # 2. 绘制尺寸文字
            text_rect = QRect(0, rect.height() - self._text_area_height, rect.width(), self._text_area_height)
            painter.setPen(QColor(200, 200, 200))
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)

            info_text = f"{self._orig_w} x {self._orig_h}"
            painter.drawText(text_rect, Qt.AlignCenter, info_text)
        else:
            # 无图像时：可以在这里画一个简单的占位符，或者什么都不画
            painter.setPen(QColor(80, 80, 80))
            painter.drawText(rect, Qt.AlignCenter, "No Image")

    def sizeHint(self):
        return self._current_size


class ImageWidgetWrapper(CustomNodeBaseWidget):
    """Wrapper 部分逻辑无需修改"""

    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)

        widget = ImageWidget(default_image=default, parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)
        widget.sizeHintChanged.connect(self._update_node)
        self._update_timer = QtCore.QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._real_update_node)

    def _update_node(self):
        self._update_timer.start(50)

    def _real_update_node(self):
        if self.node and self.node.graph is not None:
            self.node.view.set_proxy_mode(False)
            self.node.view.draw_node()

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)