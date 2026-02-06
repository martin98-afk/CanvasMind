# -*- coding: utf-8 -*-
import numpy as np
import gc
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from PyQt5.QtCore import Qt, QSize, QRect, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPainter, QColor
from PyQt5 import QtWidgets, QtCore

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ImageWidget(QtWidgets.QWidget):
    valueChanged = pyqtSignal(object)
    sizeHintChanged = pyqtSignal()

    def __init__(self, parent=None, node=None, default_image=None):
        super().__init__(parent)
        self._image_data = None  # 原始数据
        self._q_image = None  # 转换后的 QImage
        self._raw_ref = None  # 关键：强行锁定内存引用的变量

        self._text_area_height = 20
        self._orig_w = 0
        self._orig_h = 0
        self._frame_counter = 0

        self._hint_size = QSize(200, 150)
        self.setAttribute(Qt.WA_TranslucentBackground)

        if default_image:
            self.set_value(default_image)

    def _convert_to_qimage(self, data):
        """高效转换逻辑：避免不必要的 copy"""
        if data is None: return None
        try:
            # 1. 如果是 NumPy 数组
            if isinstance(data, np.ndarray):
                # 确保内存连续，否则 QImage 显示会花屏或偏移
                if not data.flags['C_CONTIGUOUS']:
                    data = np.ascontiguousarray(data)

                h, w = data.shape[:2]
                if data.ndim == 2:  # 灰度图
                    fmt = QImage.Format_Grayscale8
                    stride = w
                else:  # 彩色图
                    c = data.shape[2]
                    # 注意：如果 OpenCV 传进来是 BGR，这里需要用 Format_BGR888 (PyQt 5.14+)
                    # 或者简单处理：假设外部已转 RGB
                    fmt = QImage.Format_RGB888 if c == 3 else QImage.Format_RGBA8888
                    stride = c * w

                # 直接构造 QImage，不使用 .copy()，但需要保证 data 的生命周期
                q_img = QImage(data.data, w, h, stride, fmt)
                return q_img

            # 2. 如果是 PIL Image
            elif isinstance(data, Image.Image):
                # PIL 转换比较消耗内存，建议尽量传 numpy
                img = data.convert('RGB')
                self._temp_pil_data = img.tobytes()  # 必须保留字节流引用
                return QImage(self._temp_pil_data, data.size[0], data.size[1], QImage.Format_RGB888)

            elif isinstance(data, QImage):
                return data
            elif isinstance(data, str):
                return QImage(data)
        except Exception as e:
            print(f"Image Conversion Error: {e}")
        return None

    def get_value(self):
        return self._image_data

    def set_value(self, data):
        # --- 策略 1: 强行锁定引用 ---
        # 必须先存引用，再做转换。这样 _convert_to_qimage 使用 data.data 时才安全
        self._raw_ref = data
        self._image_data = data

        new_q_img = self._convert_to_qimage(data)

        if new_q_img and not new_q_img.isNull():
            # --- 策略 2: 降采样 (Downsampling) ---
            # 如果图片巨大（比如 4K），在 UI 预览时存一个缩小的副本，极大节省内存
            if new_q_img.width() > 1280:
                self._q_image = new_q_img.scaledToWidth(1280, Qt.SmoothTransformation)
            else:
                # 使用 .copy() 确保 QImage 拥有自己的像素数据，断开与原始 numpy 的内存耦合
                # 虽然增加了瞬时开销，但对于 UI 稳定性是必要的
                self._q_image = new_q_img.copy()

            self._orig_w = new_q_img.width()
            self._orig_h = new_q_img.height()

            # 计算推荐大小
            rec_w = 250
            scale = rec_w / float(self._orig_w)
            rec_h = int(self._orig_h * scale) + self._text_area_height
            self._hint_size = QSize(rec_w, max(100, min(600, rec_h)))
        else:
            self._q_image = None
            self._orig_w, self._orig_h = 0, 0
            self._hint_size = QSize(200, 150)

        # --- 策略 3: 定期强制 GC ---
        # 每 30 帧清理一次 Python 的内存碎片，防止 GC 滞后
        self._frame_counter += 1
        if self._frame_counter % 30 == 0:
            gc.collect()

        self.updateGeometry()
        self.sizeHintChanged.emit()
        self.update()
        self.valueChanged.emit(self._image_data)

    def paintEvent(self, event):
        painter = QPainter(self)
        # 只有在需要缩放显示时才开启这些，提高绘制效率
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()
        if self._q_image and not self._q_image.isNull():
            display_rect = QRect(0, 0, rect.width(), rect.height() - self._text_area_height)

            # Letterbox 保持比例
            img_size = self._q_image.size()
            img_size.scale(display_rect.size(), Qt.KeepAspectRatio)

            x = (display_rect.width() - img_size.width()) // 2
            y = (display_rect.height() - img_size.height()) // 2
            target_draw_rect = QRect(x, y, img_size.width(), img_size.height())

            painter.drawImage(target_draw_rect, self._q_image)

            # 绘制文字
            text_rect = QRect(0, rect.height() - self._text_area_height, rect.width(), self._text_area_height)
            painter.setPen(QColor(150, 150, 150))
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            info_text = f"{self._orig_w} x {self._orig_h}"
            painter.drawText(text_rect, Qt.AlignCenter, info_text)
        else:
            painter.fillRect(rect, QColor(40, 40, 40, 100))  # 空状态背景

    def sizeHint(self):
        return self._hint_size


class ImageWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label_visible(False)

        self._image_widget = ImageWidget(default_image=default, parent=window)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.set_custom_widget(self._image_widget)

        self._image_widget.valueChanged.connect(self.on_value_changed)
        self._image_widget.sizeHintChanged.connect(self._update_node)

        # 使用低频率定时器处理节点尺寸更新，防止 UI 线程被淹没
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._real_update_node)

    def _update_node(self):
        if not self._update_timer.isActive():
            self._update_timer.start(100)  # 100ms 刷新一次布局即可

    def _real_update_node(self):
        if self.node and self.node.graph is not None:
            # 这里的 update 取决于 NodeGraphQt 版本，通常是强制触发重绘
            self.node.update()

    def get_value(self):
        return self._image_widget.get_value()

    def set_value(self, value):
        # 如果当前窗口被隐藏，可以选择不处理 set_value 来进一步节省性能
        self._image_widget.set_value(value)