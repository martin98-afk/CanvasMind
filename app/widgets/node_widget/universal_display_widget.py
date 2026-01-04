# -*- coding: utf-8 -*-
import os

import numpy as np
from PIL import Image
from Qt import QtWidgets, QtCore
from app.widgets.node_widget.base import CustomNodeBaseWidget
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from .html_widget import HtmlWidget
from .image_widget import ImageWidget


class UniversalDisplayWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QtWidgets.QStackedWidget()
        self.layout.addWidget(self.stack)

        self.html_view = HtmlWidget(self)  # 之前定义的 HTML 控件
        self.image_view = ImageWidget(self)  # 之前定义的图片控件

        self.stack.addWidget(self.html_view)  # Index 0
        self.stack.addWidget(self.image_view)  # Index 1

        self.html_view.sizeHintChanged.connect(self.sizeHintChanged.emit)
        self.image_view.sizeHintChanged.connect(self.sizeHintChanged.emit)

    def show_html(self, html_str):
        self.stack.setCurrentIndex(0)
        self.html_view.set_value(html_str)
        self.sizeHintChanged.emit()

    def show_image(self, img_data):
        self.stack.setCurrentIndex(1)
        self.image_view.set_value(img_data)
        self.sizeHintChanged.emit()

    def get_value(self):
        if self.stack.currentIndex() == 0:
            return self.html_view.get_value()
        elif self.stack.currentIndex() == 1:
            return self.image_view.get_value()
        else:
            return None

    def set_value(self, value):
        # 如果图像数据为数据、本地存在的图片路径即显示图片
        if isinstance(value, (np.ndarray, Image.Image)) or (isinstance(value, str) and os.path.exists(value)):
            self.show_image(value)
        elif isinstance(value, str) and value:
            self.show_html(value)
        else:
            self.show_html("<center>无 HTML 数据</center>")
            self.show_image(None)


class UniversalWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)

        widget = UniversalDisplayWidget(parent=window)
        self.set_custom_widget(widget)

        widget.valueChanged.connect(self.on_value_changed)
        widget.sizeHintChanged.connect(self._update_node)

    def _update_node(self):
        if self.node and self.node.graph is not None:
            self.node.view.set_proxy_mode(False)
            self.node.view.draw_node()

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)