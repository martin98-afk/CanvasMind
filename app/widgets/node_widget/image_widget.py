# -*- coding: utf-8 -*-
import numpy as np
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QImage, QPixmap, QPainter
from Qt import QtWidgets, QtCore

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ImageWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    # 专门增加一个信号，通知节点大小发生了变化
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None, default_image=None):
        super().__init__(parent)
        self._image_data = None
        self._q_image = None

        # 设定显示限制（可以根据需要调整）
        self._min_width = 200
        self._max_width = 500  # 最大显示宽度，防止图片太大撑破屏幕
        self._current_size = QSize(200, 150)  # 初始默认大小

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
            # --- 关键逻辑：计算等比例缩放后的 Widget 大小 ---
            orig_size = new_q_img.size()
            target_w = max(self._min_width, min(orig_size.width(), self._max_width))
            scale_ratio = target_w / float(orig_size.width())
            target_h = int(orig_size.height() * scale_ratio)

            self._current_size = QSize(target_w, target_h)
        else:
            self._q_image = None
            self._current_size = QSize(200, 150)

        # 更新 Widget 本身的几何属性
        self.setFixedSize(self._current_size)

        # 通知 Wrapper 和 NodeGraph 更新布局
        self.sizeHintChanged.emit()
        self.update()
        self.valueChanged.emit(self._image_data)

    def get_value(self):
        return self._image_data

    def paintEvent(self, event):
        painter = QPainter(self)
        # 开启高质量渲染提示
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()

        # 绘制背景
        painter.fillRect(rect, Qt.transparent)

        if self._q_image:
            # 使用 drawImage 直接绘制到当前 rect，Qt 会自动处理高质量缩放
            painter.drawImage(rect, self._q_image)

    def sizeHint(self):
        return self._current_size


class ImageWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)

        widget = ImageWidget(default_image=default, parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)
        widget.sizeHintChanged.connect(self._update_node)

    def _update_node(self):
        """更新节点 UI 布局"""
        if self.node and self.node.graph is not None:
            # 停止代理模式以强制重绘
            self.node.view.set_proxy_mode(False)
            self.node.view.draw_node()

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)