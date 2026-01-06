# -*- coding: utf-8 -*-
import os

import numpy as np
from PIL import Image
from Qt import QtWidgets, QtCore
from app.widgets.node_widget.base import CustomNodeBaseWidget
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from .html_widget import HtmlWidget
from .image_widget import ImageWidget
from ..basic_widget.media_widget import VideoPlayWidget, AudioPlayWidget


class UniversalDisplayWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QtWidgets.QStackedWidget()
        self.layout.addWidget(self.stack)

        self.html_view = HtmlWidget(self)
        self.image_view = ImageWidget(self)
        self.video_view = VideoPlayWidget(self)  # 新增媒体控件
        self.audio_view = AudioPlayWidget(self)

        self.stack.addWidget(self.html_view)  # Index 0
        self.stack.addWidget(self.image_view)  # Index 1
        self.stack.addWidget(self.video_view)  # Index 2
        self.stack.addWidget(self.audio_view)

        self.html_view.sizeHintChanged.connect(self.sizeHintChanged.emit)
        self.image_view.sizeHintChanged.connect(self.sizeHintChanged.emit)
        self.video_view.sizeHintChanged.connect(self.sizeHintChanged.emit)
        self.audio_view.sizeHintChanged.connect(self.sizeHintChanged.emit)

    def show_html(self, html_str):
        self.stack.setCurrentIndex(0)
        self.html_view.set_value(html_str)
        self.sizeHintChanged.emit()

    def show_image(self, img_data):
        self.stack.setCurrentIndex(1)
        self.image_view.set_value(img_data)
        self.sizeHintChanged.emit()

    def show_video(self, file_path):
        self.stack.setCurrentIndex(2)
        self.video_view.set_value(file_path)
        self.sizeHintChanged.emit()

    def show_audio(self, file_path):
        self.stack.setCurrentIndex(3)
        self.audio_view.set_value(file_path)
        self.sizeHintChanged.emit()

    def get_value(self):
        idx = self.stack.currentIndex()
        if idx == 0: return self.html_view.get_value()
        if idx == 1: return self.image_view.get_value()
        if idx == 2: return self.video_view.get_value()
        if idx == 3: return self.audio_view.get_value()
        return None

    def set_value(self, value):
        # 1. 检查是否是多媒体文件路径
        if isinstance(value, str) and os.path.exists(value):
            ext = os.path.splitext(value)[1].lower()
            image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']

            if ext in self.video_view.EXTS:
                self.show_video(value)
                return
            elif ext in self.audio_view.EXTS:
                self.show_audio(value)
                return
            elif ext in image_exts:
                self.show_image(value)
                return

        # 2. 检查是否是图像内存数据 (numpy/PIL)
        if isinstance(value, (np.ndarray, Image.Image)):
            self.show_image(value)

        # 3. 检查是否是 HTML 字符串
        elif isinstance(value, str) and value:
            self.show_html(value)

        else:
            self.show_html("<center>无有效数据</center>")
            self.show_image(None)
            self.show_audio(None)
            self.show_video(None)

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