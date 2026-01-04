# -*- coding: utf-8 -*-
import numpy as np
from PIL import Image
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from Qt import QtWidgets, QtCore

# 导入 qfluentwidgets
try:
    from qfluentwidgets import ImageLabel
except ImportError:
    # 备选方案，如果没有安装 qfluentwidgets 则回退到 QLabel
    from Qt.QtWidgets import QLabel as ImageLabel

    print("Warning: qfluentwidgets not found, fallback to QLabel")

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ImageWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None, default_image=None):
        super().__init__(parent)
        self._image_data = default_image
        # 默认最大显示尺寸
        self._max_width = 300
        self._max_height = 300

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(0)

        # 使用 QFluentWidgets 的 ImageLabel
        self.label = ImageLabel(self)

        # 属性设置
        if hasattr(self.label, 'setBorderRadius'):
            self.label.setBorderRadius(8, 8, 8, 8)  # 设置圆角

        # 居中显示
        # self.label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.label)

        if default_image is not None:
            self.set_value(default_image)
        else:
            self.updateGeometry()
            self.sizeHintChanged.emit()
            self.label.setFixedSize(200, 150)

    def _convert_to_qimage(self, data):
        """将不同格式的数据统一转换为 QImage，ImageLabel 支持 QImage/QPixmap/str"""
        if data is None:
            return None

        try:
            # 1. 处理 NumPy 数组
            if isinstance(data, np.ndarray):
                if len(data.shape) == 2:  # 灰度图
                    height, width = data.shape
                    channel = 1
                    format = QImage.Format_Grayscale8
                else:
                    height, width, channel = data.shape
                    format = QImage.Format_RGB888 if channel == 3 else QImage.Format_RGBA8888

                bytes_per_line = channel * width
                # 必须 .copy() 否则内存释放会导致崩溃
                return QImage(data.data, width, height, bytes_per_line, format).copy()

            # 2. 处理 PIL Image
            elif isinstance(data, Image.Image):
                if data.mode != 'RGBA':
                    data = data.convert('RGBA')
                data_bytes = data.tobytes("raw", "RGBA")
                return QImage(data_bytes, data.size[0], data.size[1], QImage.Format_RGBA8888).copy()

            # 3. 处理 QPixmap
            elif isinstance(data, QPixmap):
                return data.toImage()

            # 4. 处理 QImage
            elif isinstance(data, QImage):
                return data

            # 5. 处理 文件路径
            elif isinstance(data, str):
                return QImage(data)

        except Exception as e:
            print(f"Image conversion error: {e}")
            return None

        return None

    def set_value(self, data):
        """支持传入 PIL Image, np.array, QPixmap, QImage, str(path)"""
        self._image_data = data
        # 增加判断：如果数据为空，重置为默认显示
        if data is None or (isinstance(data, str) and data == ""):
            self._pixmap = None
            self.label.setImage(None)  # 清除 qfluentwidgets 的图片
            if hasattr(self.label, 'setText'):
                self.label.setText("等待图片输入...")

            # 关键点：重置为默认大小
            self.label.setFixedSize(200, 150)
        else:
            q_img = self._convert_to_qimage(data)
            if q_img and not q_img.isNull():
                img_size = q_img.size()
                img_size.scale(self._max_width, self._max_height, Qt.KeepAspectRatio)
                self.label.setFixedSize(img_size)
                self.label.setImage(q_img)
            else:
                self.label.setText("无效图片")
                self.label.setFixedSize(200, 150)

        self.updateGeometry()
        self.sizeHintChanged.emit()
        self.valueChanged.emit(self._image_data)

    def get_value(self):
        return self._image_data

    def sizeHint(self):
        # 加上 layout 的 margins
        if self._image_data:
            return self.label.size() + QtCore.QSize(10, 10)
        return QtCore.QSize(200, 150)


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