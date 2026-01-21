# -*- coding: utf-8 -*-
import numpy as np
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from PyQt5.QtCore import Qt, QSize, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QPen
from Qt import QtWidgets, QtCore
from qfluentwidgets import PushButton, BodyLabel

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ImageCompareWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    class ImageView(QtWidgets.QWidget):
        """内部绘图区，处理图像渲染和对比线拖拽"""

        def __init__(self, parent):
            super().__init__(parent)
            self.parent_widget = parent
            self._slider_pos = 0.5
            self._is_dragging = False
            self.setMouseTracking(True)

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                slider_x = int(self.width() * self._slider_pos)
                if abs(event.x() - slider_x) < 20:
                    self._is_dragging = True
                    self.update()

        def mouseMoveEvent(self, event):
            slider_x = int(self.width() * self._slider_pos)
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
            if not self.parent_widget._image_a and not self.parent_widget._image_b:
                painter.fillRect(rect, QColor(30, 30, 30))
                return

            # 决定层级
            if not self.parent_widget._swap_layers:
                base_img, top_img = self.parent_widget._image_a, self.parent_widget._image_b
            else:
                base_img, top_img = self.parent_widget._image_b, self.parent_widget._image_a

            # 1. 绘制底层图像
            if base_img:
                painter.drawImage(rect, base_img)

            # 2. 绘制顶层图像（带裁剪和透明度）
            if top_img:
                slider_x = int(rect.width() * self._slider_pos)
                painter.save()
                painter.setOpacity(self.parent_widget._opacity)
                clip_rect = QRect(slider_x, 0, rect.width() - slider_x, rect.height())
                painter.setClipRect(clip_rect)
                painter.drawImage(rect, top_img)
                painter.restore()

                # 3. 绘制分割线
                line_color = QColor(0, 180, 255) if self._is_dragging else QColor(255, 255, 255, 200)
                pen = QPen(line_color, 2)
                painter.setPen(pen)
                painter.drawLine(slider_x, 0, slider_x, rect.height())

                # 4. 绘制手柄（圆形 + 横线）
                center_y = rect.height() // 2
                handle_radius = 10

                # 圆形背景
                painter.setBrush(line_color)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(slider_x, center_y), handle_radius, handle_radius)

                # 中间横线（专业对比风格）
                painter.setPen(QPen(Qt.black, 2))  # 黑色横线，增强对比；可按需调整颜色/粗细
                line_length = 8
                painter.drawLine(
                    slider_x - line_length // 2,
                    center_y,
                    slider_x + line_length // 2,
                    center_y
                )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_a = None
        self._image_b = None
        self._opacity = 1.0
        self._swap_layers = False

        self._min_width = 200
        self._max_width = 500
        self._current_size = QSize(200, 150)

        # UI 布局
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 1. 控制栏 (当图片无效或只有一张时隐藏)
        self.ctrl_bar = QtWidgets.QWidget()
        self.ctrl_bar.setFixedHeight(30)
        self.ctrl_bar.setStyleSheet("background: rgba(40, 40, 40, 150);")
        ctrl_layout = QtWidgets.QHBoxLayout(self.ctrl_bar)
        ctrl_layout.setContentsMargins(5, 0, 5, 0)

        self.btn_swap = PushButton("交换图片")
        self.btn_swap.setCheckable(True)
        self.btn_swap.setFixedWidth(50)
        self.btn_swap.setStyleSheet("font-size: 10px; height: 18px; color: white;")
        self.btn_swap.toggled.connect(self.set_swap)

        slider_label = BodyLabel("透明度:")
        slider_label.setStyleSheet("font-size: 10px; color: white;")
        self.slider_opacity = QtWidgets.QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.setFixedHeight(15)
        self.slider_opacity.valueChanged.connect(self._on_opacity_changed)
        ctrl_layout.addWidget(self.btn_swap)
        ctrl_layout.addWidget(slider_label)
        ctrl_layout.addWidget(self.slider_opacity)

        # 2. 图像视图区
        self.view = self.ImageView(self)

        self.layout.addWidget(self.ctrl_bar)
        self.layout.addWidget(self.view)

        self.ctrl_bar.setVisible(False)  # 初始隐藏

    def _convert_to_qimage(self, data):
        if data is None: return None
        try:
            if isinstance(data, str):
                return QImage(data)
            if isinstance(data, np.ndarray):
                h, w = data.shape[:2]
                if data.ndim == 2:
                    return QImage(data.data, w, h, w, QImage.Format_Grayscale8).copy()
                else:
                    c = data.shape[2]
                    fmt = QImage.Format_RGB888 if c == 3 else QImage.Format_RGBA8888
                    return QImage(data.data, w, h, c * w, fmt).copy()
            elif isinstance(data, Image.Image):
                rgb_img = data.convert('RGBA')
                return QImage(rgb_img.tobytes(), data.size[0], data.size[1], QImage.Format_RGBA8888).copy()
            elif isinstance(data, QImage):
                return data
            elif isinstance(data, QPixmap):
                return data.toImage()
            return None
        except Exception as e:
            print(f"Convert Error: {e}")
            return None

    def set_value(self, data):
        """设置数据，控制交互按钮显隐"""
        has_two_images = False
        if isinstance(data, (list, tuple)) and len(data) >= 2:
            self._image_a = self._convert_to_qimage(data[0])
            self._image_b = self._convert_to_qimage(data[1])
            if self._image_a and self._image_b:
                has_two_images = True
        else:
            self._image_a = self._convert_to_qimage(data)
            self._image_b = None

        # 控制交互按钮显隐
        self.ctrl_bar.setVisible(has_two_images)

        # 计算尺寸
        ref_img = self._image_a or self._image_b

        # --- 修改开始 ---
        if ref_img and not ref_img.isNull():
            # 有图片时：显示控件并计算尺寸
            self.setVisible(True)

            orig_size = ref_img.size()
            target_w = max(self._min_width, min(orig_size.width(), self._max_width))
            scale_ratio = target_w / float(orig_size.width())
            target_h = int(orig_size.height() * scale_ratio)
            # 总高度 = 图片高度 + 控制栏高度(如果显示)
            total_h = target_h + (30 if has_two_images else 0)
            self._current_size = QSize(target_w, total_h)
        else:
            # 无图片时：隐藏控件并将尺寸设为 0
            self.setVisible(False)
            self._current_size = QSize(0, 0)
        # --- 修改结束 ---

        self.setFixedSize(self._current_size)
        self.updateGeometry()
        self.sizeHintChanged.emit()  # 通知 NodeGraphQt 更新节点形状

    def set_swap(self, state):
        self._swap_layers = state
        self.view.update()

    def _on_opacity_changed(self, val):
        self._opacity = val / 100.0
        self.view.update()

    def sizeHint(self):
        return self._current_size


class ImageCompareWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)
        self.set_label_visible(False)
        self.widget = ImageCompareWidget(parent=window)
        self.set_custom_widget(self.widget)

        if default:
            self.widget.set_value(default)

        self.widget.sizeHintChanged.connect(self._update_node)

    def _update_node(self):
        if self.node and self.node.graph is not None:
            self.node.view.set_proxy_mode(False)
            self.node.view.draw_node()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)

    def get_value(self):
        w = self.get_custom_widget()
        return (w._image_a, w._image_b, w._opacity, w._swap_layers)