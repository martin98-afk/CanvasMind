# -*- coding: utf-8 -*-
import numpy as np
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from PyQt5.QtCore import Qt, QSize, QRect
from PyQt5.QtGui import QImage, QPainter, QColor
from PyQt5 import QtWidgets, QtCore

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ImageWidget(QtWidgets.QWidget):
    valueChanged = QtCore.pyqtSignal(object)
    sizeHintChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None, node=None, default_image=None):
        super().__init__(parent)
        self._image_data = None
        self._q_image = None

        self._text_area_height = 20
        self._orig_w = 0
        self._orig_h = 0

        # 初始推荐大小
        self._hint_size = QSize(200, 150)

        self.setAttribute(Qt.WA_TranslucentBackground)
        if default_image:
            self.set_value(default_image)

    def _convert_to_qimage(self, data):
        """保持高质量转换逻辑"""
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
            elif isinstance(data, str):
                return QImage(data)
        except:
            pass
        return None

    def get_value(self):
        return self._image_data

    def set_value(self, data):
        self._image_data = data
        new_q_img = self._convert_to_qimage(data)

        if new_q_img and not new_q_img.isNull():
            self._q_image = new_q_img
            self._orig_w = new_q_img.width()
            self._orig_h = new_q_img.height()

            # 计算推荐大小：宽度默认 250，高度按比例缩放
            rec_w = 250
            scale = rec_w / float(self._orig_w)
            rec_h = int(self._orig_h * scale) + self._text_area_height

            # 限制初始推荐尺寸不至于太大或太小
            self._hint_size = QSize(rec_w, max(100, min(600, rec_h)))
        else:
            self._q_image = None
            self._orig_w, self._orig_h = 0, 0
            self._hint_size = QSize(200, 150)

        self.updateGeometry()  # 告诉布局管理器 sizeHint 变了
        self.sizeHintChanged.emit()
        self.update()  # 重新触发重绘
        self.valueChanged.emit(self._image_data)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()
        # # 填充背景（防止缩放时出现残影）
        # painter.fillRect(rect, QColor(30, 30, 30))

        if self._q_image and not self._q_image.isNull():
            # 1. 计算图片显示区域（扣除文字高度）
            display_rect = QRect(0, 0, rect.width(), rect.height() - self._text_area_height)

            # 2. 保持比例计算绘图区域 (Letterbox 效果)
            img_size = self._q_image.size()
            img_size.scale(display_rect.size(), Qt.KeepAspectRatio)

            # 居中图片
            x = (display_rect.width() - img_size.width()) // 2
            y = (display_rect.height() - img_size.height()) // 2
            target_draw_rect = QRect(x, y, img_size.width(), img_size.height())

            painter.drawImage(target_draw_rect, self._q_image)

            # 3. 绘制文字信息（固定在底部）
            text_rect = QRect(0, rect.height() - self._text_area_height, rect.width(), self._text_area_height)
            painter.setPen(QColor(150, 150, 150))
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            info_text = f"{self._orig_w} x {self._orig_h}"
            painter.drawText(text_rect, Qt.AlignCenter, info_text)
        else:
            # 透明
            painter.fillRect(rect, QColor(0, 0, 0, 0))

    def sizeHint(self):
        """给 NodeGraph 一个初始大小建议"""
        return self._hint_size


class ImageWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label_visible(False)

        self._image_widget = ImageWidget(default_image=default, parent=window)

        # 关键：手动设置包装层的 Policy
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.set_custom_widget(self._image_widget)

        self._image_widget.valueChanged.connect(self.on_value_changed)
        self._image_widget.sizeHintChanged.connect(self._update_node)

        self._update_timer = QtCore.QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._real_update_node)

    def _update_node(self):
        # 当图片变化导致推荐大小变化时，触发节点重绘
        self._update_timer.start(50)

    def _real_update_node(self):
        if self.node and self.node.graph is not None:
            # 强制节点根据内容重新计算大小（取决于 NodeGraphQt 具体实现）
            self.node.view.update()

    def get_value(self):
        return self._image_widget.get_value()

    def set_value(self, value):
        self._image_widget.set_value(value)