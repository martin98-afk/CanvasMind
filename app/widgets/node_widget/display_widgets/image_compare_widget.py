# -*- coding: utf-8 -*-
import os

import numpy as np
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QSize, QRect, QPoint
from PyQt5.QtGui import QImage, QPainter, QColor, QPen, QPixmap
from Qt import QtWidgets
from qfluentwidgets import PushButton, BodyLabel, StrongBodyLabel

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ImageView(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.p = parent
        self._slider_pos = 0.5
        self._is_dragging = False
        self.setMouseTracking(True)
        # 设置策略，允许在节点内垂直/水平双向拉伸
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()
        # 无图像时绘制深色背景
        if not self.p._image_a and not self.p._image_b:
            painter.fillRect(rect, QColor(25, 25, 25))
            painter.setPen(QColor(80, 80, 80))
            painter.drawText(rect, Qt.AlignCenter, "No Image Data")
            return

        # 确定层级
        img_base = self.p._image_a if not self.p._swap_layers else self.p._image_b
        img_top = self.p._image_b if not self.p._swap_layers else self.p._image_a

        # 计算保持比例的绘图区域 (Letterbox)
        ref_img = img_base or img_top
        img_size = ref_img.size()
        img_size.scale(rect.size(), Qt.KeepAspectRatio)

        draw_rect = QRect(
            (rect.width() - img_size.width()) // 2,
            (rect.height() - img_size.height()) // 2,
            img_size.width(),
            img_size.height()
        )

        # 1. 绘制底层
        if img_base:
            painter.drawImage(draw_rect, img_base)

        # 2. 绘制顶层（带裁剪和透明度）
        if img_top:
            # 分割线 X 坐标基于 draw_rect 宽度计算
            slider_x_in_draw = int(draw_rect.width() * self._slider_pos)
            abs_slider_x = draw_rect.x() + slider_x_in_draw

            painter.save()
            painter.setOpacity(self.p._opacity)
            # 裁剪区：从当前的 slider 位置裁剪到控件最右侧
            clip_rect = QRect(abs_slider_x, 0, rect.width() - abs_slider_x, rect.height())
            painter.setClipRect(clip_rect)
            painter.drawImage(draw_rect, img_top)
            painter.restore()

            # 3. 绘制分割线
            line_color = QColor(0, 180, 255) if self._is_dragging else QColor(255, 255, 255, 180)
            painter.setPen(QPen(line_color, 2))
            painter.drawLine(abs_slider_x, draw_rect.y(), abs_slider_x, draw_rect.bottom())

            # 4. 绘制对比手柄
            center_y = draw_rect.center().y()
            painter.setBrush(line_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(abs_slider_x, center_y), 8, 8)
            painter.setPen(QPen(Qt.black, 2))
            painter.drawLine(abs_slider_x - 4, center_y, abs_slider_x + 4, center_y)

    def mouseMoveEvent(self, event):
        # 将鼠标坐标转换为 0-1 的比例
        if self._is_dragging:
            pos = event.x() / float(self.width() if self.width() > 0 else 1)
            self.p.view._slider_pos = max(0.0, min(1.0, pos))
            self.update()

        # 改变光标形状
        slider_x = int(self.width() * self._slider_pos)
        if abs(event.x() - slider_x) < 15:
            self.setCursor(Qt.SplitHCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self.update()

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        self.update()


class ImageCompareWidget(QtWidgets.QWidget):
    valueChanged = QtCore.pyqtSignal(object)
    sizeHintChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_a = None
        self._image_b = None
        self._opacity = 1.0
        self._swap_layers = False
        self._hint_size = QSize(250, 180)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 1. 控制栏
        self.ctrl_bar = QtWidgets.QWidget()
        self.ctrl_bar.setFixedHeight(30)
        self.ctrl_bar.setStyleSheet("background: rgba(45, 45, 45, 220); border-bottom: 1px solid #111;")
        ctrl_layout = QtWidgets.QHBoxLayout(self.ctrl_bar)
        ctrl_layout.setContentsMargins(8, 0, 8, 0)

        self.btn_swap = PushButton("交换图片")
        self.btn_swap.setCheckable(True)
        self.btn_swap.setFixedWidth(50)
        self.btn_swap.setStyleSheet("font-size: 9px; height: 18px; color: white;")
        self.btn_swap.toggled.connect(self.set_swap)

        self.slider_opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.setFixedHeight(15)
        self.slider_opacity.valueChanged.connect(self._on_opacity_changed)

        ctrl_layout.addWidget(self.btn_swap)
        ctrl_layout.addWidget(StrongBodyLabel("透明度:", self))
        ctrl_layout.addWidget(self.slider_opacity)

        # 2. 图像视图区
        self.view = ImageView(self)

        self.layout.addWidget(self.ctrl_bar)
        self.layout.addWidget(self.view)

        self.ctrl_bar.setVisible(False)

    def _convert_to_qimage(self, data):
        if data is None: return None
        try:
            if isinstance(data, str) and os.path.exists(data): return QImage(data)
            if isinstance(data, np.ndarray):
                h, w = data.shape[:2]
                fmt = QImage.Format_Grayscale8 if data.ndim == 2 else (
                    QImage.Format_RGB888 if data.shape[2] == 3 else QImage.Format_RGBA8888)
                step = w if data.ndim == 2 else data.shape[2] * w
                return QImage(data.data, w, h, step, fmt).copy()
            if isinstance(data, Image.Image):
                rgb_img = data.convert('RGBA')
                return QImage(rgb_img.tobytes(), data.size[0], data.size[1], QImage.Format_RGBA8888).copy()
            if isinstance(data, QImage): return data
            if isinstance(data, QPixmap): return data.toImage()
        except:
            pass
        return None

    def set_value(self, data):
        """完全重置并设置新图"""
        self._image_a = None
        self._image_b = None
        has_two = False

        if isinstance(data, (list, tuple)) and len(data) >= 2:
            self._image_a = self._convert_to_qimage(data[0])
            self._image_b = self._convert_to_qimage(data[1])
            if self._image_a and self._image_b: has_two = True
        elif data is not None:
            self._image_a = self._convert_to_qimage(data)

        self.ctrl_bar.setVisible(has_two)

        # 初始尺寸建议
        ref = self._image_a or self._image_b
        if ref:
            ratio = ref.width() / float(ref.height())
            target_h = 200
            self._hint_size = QSize(int(target_h * ratio), target_h + (30 if has_two else 0))
        else:
            self._hint_size = QSize(250, 180)

        self.updateGeometry()
        self.sizeHintChanged.emit()
        self.view.update()
        self.valueChanged.emit(data)

    def set_swap(self, state):
        self._swap_layers = state
        self.view.update()

    def _on_opacity_changed(self, val):
        self._opacity = val / 100.0
        self.view.update()

    def sizeHint(self):
        return self._hint_size


class ImageCompareWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)
        self.set_label_visible(False)

        # 实例化控件
        self.custom_widget = ImageCompareWidget(parent=window)
        # 包装类也要设置 Expanding 策略
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.set_custom_widget(self.custom_widget)

        if default:
            self.custom_widget.set_value(default)

        self.custom_widget.sizeHintChanged.connect(self._update_node)

    def _update_node(self):
        if self.node and self.node.graph is not None:
            # 这里的 draw_node() 会触发 ProxyWidget 重新根据内容调整节点高度
            self.node.view.draw_node()

    def set_value(self, value):
        self.custom_widget.set_value(value)

    def get_value(self):
        w = self.custom_widget
        return (w._image_a, w._image_b, w._opacity, w._swap_layers)