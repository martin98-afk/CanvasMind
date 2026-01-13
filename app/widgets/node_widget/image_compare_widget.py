# -*- coding: utf-8 -*-
import numpy as np
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from PyQt5.QtCore import Qt, QSize, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QPen
from Qt import QtWidgets, QtCore

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ImageCompareWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_a = None  # 左侧/底层图
        self._image_b = None  # 右侧/顶层图
        
        self._slider_pos = 0.5  # 0.0 - 1.0
        self._is_dragging = False
        
        self._min_width = 200
        self._max_width = 500
        self._current_size = QSize(200, 150)

        # 开启鼠标追踪，以便改变光标形状
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def _convert_to_qimage(self, data):
        if data is None: return None
        try:
            # --- 处理字符串路径 ---
            if isinstance(data, str):
                q_img = QImage(data)
                if q_img.isNull():
                    print(f"图片加载失败，路径无效或格式不支持: {data}")
                    return None
                return q_img
            # --------------------------

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
            return None
        except Exception as e:
            print(f"转换失败: {e}")
            return None

    def set_value(self, data):
        """
        data 可以是一个 tuple/list (img_a, img_b) 
        或者单张图（此时对比功能失效，只显示一张）
        """
        if isinstance(data, (list, tuple)) and len(data) >= 2:
            self._image_a = self._convert_to_qimage(data[0])
            self._image_b = self._convert_to_qimage(data[1])
        else:
            self._image_a = self._convert_to_qimage(data)
            self._image_b = None

        # 以第一张图为基准计算尺寸
        ref_img = self._image_a or self._image_b
        if ref_img and not ref_img.isNull():
            orig_size = ref_img.size()
            target_w = max(self._min_width, min(orig_size.width(), self._max_width))
            scale_ratio = target_w / float(orig_size.width())
            target_h = int(orig_size.height() * scale_ratio)
            self._current_size = QSize(target_w, target_h)
        else:
            self._current_size = QSize(200, 150)

        self.setFixedSize(self._current_size)
        self.sizeHintChanged.emit()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            slider_x = int(self.width() * self._slider_pos)
            # 点击在滑块附近 20 像素范围内触发拖拽
            if abs(event.x() - slider_x) < 20:
                self._is_dragging = True
                self.update()

    def mouseMoveEvent(self, event):
        slider_x = int(self.width() * self._slider_pos)
        
        # 改变鼠标光标
        if abs(event.x() - slider_x) < 10 or self._is_dragging:
            self.setCursor(Qt.SplitHCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

        if self._is_dragging:
            pos = event.x() / float(self.width())
            self._slider_pos = max(0.0, min(1.0, pos))
            self.update()

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()
        painter.fillRect(rect, Qt.transparent)

        if not self._image_a and not self._image_b:
            return

        # 1. 绘制底层图片 (Image A)
        if self._image_a:
            painter.drawImage(rect, self._image_a)
        
        # 2. 绘制顶层图片 (Image B) 并进行裁剪
        if self._image_b:
            slider_x = int(rect.width() * self._slider_pos)
            
            # 保存状态
            painter.save()
            # 设置裁剪区域：只显示右侧
            clip_rect = QRect(slider_x, 0, rect.width() - slider_x, rect.height())
            painter.setClipRect(clip_rect)
            painter.drawImage(rect, self._image_b)
            painter.restore()

            # 3. 绘制分割线
            line_color = QColor(255, 255, 255, 200)
            if self._is_dragging:
                line_color = QColor(0, 180, 255) # 拖拽时变蓝
            
            painter.setPen(QPen(line_color, 2))
            painter.drawLine(slider_x, 0, slider_x, rect.height())

            # 4. 绘制中心圆圈手柄 (可选)
            handle_r = 12
            painter.setBrush(line_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(slider_x, rect.height() // 2), handle_r, handle_r)
            # 画个小箭头提示
            painter.setPen(QPen(Qt.black, 2))
            painter.drawLine(slider_x - 4, rect.height() // 2, slider_x + 4, rect.height() // 2)

    def sizeHint(self):
        return self._current_size

class ImageCompareWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)

        # 使用新的对比控件
        widget = ImageCompareWidget(parent=window)
        self.set_custom_widget(widget)
        
        if default:
            widget.set_value(default)
            
        widget.sizeHintChanged.connect(self._update_node)

    def _update_node(self):
        if self.node and self.node.graph is not None:
            self.node.view.set_proxy_mode(False)
            self.node.view.draw_node()

    def set_value(self, value):
        """
        value 可以是:
        1. [img_a, img_b]
        2. single_img
        """
        self.get_custom_widget().set_value(value)

    def get_value(self):
        # 返回当前控件内的图像数据
        w = self.get_custom_widget()
        return (w._image_a, w._image_b)