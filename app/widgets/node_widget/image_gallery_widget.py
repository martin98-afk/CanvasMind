# -*- coding: utf-8 -*-
import os
import numpy as np
from PIL import Image
from Qt import QtWidgets, QtCore, QtGui


class ImageGalleryWidget(QtWidgets.QScrollArea):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.container = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.container)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.setWidget(self.container)

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        # 初始默认大小
        self.setFixedSize(200, 150)
        self.setStyleSheet("background-color: transparent; border: none;")

    def _clear(self):
        """彻底清理布局并重置容器状态"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 取消容器可能存在的固定尺寸限制，使其能够回缩
        self.container.setMinimumSize(0, 0)
        self.container.setMaximumSize(16777215, 16777215)

    def _convert_to_qimage(self, data):
        if data is None: return None
        try:
            if isinstance(data, np.ndarray):
                if data.ndim == 2:
                    h, w = data.shape
                    return QtGui.QImage(data.data, w, h, w, QtGui.QImage.Format_Grayscale8).copy()
                else:
                    h, w, c = data.shape
                    fmt = QtGui.QImage.Format_RGB888 if c == 3 else QtGui.QImage.Format_RGBA8888
                    return QtGui.QImage(data.data, w, h, c * w, fmt).copy()
            elif isinstance(data, Image.Image):
                rgb_img = data.convert('RGB')
                return QtGui.QImage(rgb_img.tobytes(), data.size[0], data.size[1], QtGui.QImage.Format_RGB888).copy()
            elif isinstance(data, QtGui.QImage):
                return data
            elif isinstance(data, str) and os.path.exists(data):
                return QtGui.QImage(data)
            return None
        except Exception as e:
            print(f"Gallery 转换失败: {e}")
            return None

    def set_value(self, image_list):
        self._clear()

        # 处理空值
        if image_list is None or not image_list or not isinstance(image_list, (list, tuple)):
            self.set_value_none()
            return

        cols = 2
        img_w = 180
        count = 0

        # 高质量缩放模式
        smooth_mode = QtCore.Qt.SmoothTransformation
        aspect_mode = QtCore.Qt.KeepAspectRatio

        for img_data in image_list:
            q_img = self._convert_to_qimage(img_data)
            if q_img and not q_img.isNull():
                label = QtWidgets.QLabel()
                # 核心改动：在 QImage 层缩放，保证极致清晰
                scaled_img = q_img.scaled(
                    img_w, img_w,
                    aspect_mode,
                    smooth_mode
                )
                label.setPixmap(QtGui.QPixmap.fromImage(scaled_img))
                label.setAlignment(QtCore.Qt.AlignCenter)
                label.setStyleSheet("border: 1px solid #555; background-color: #111;")
                self.grid_layout.addWidget(label, count // cols, count % cols)
                count += 1

        if count == 0:
            self.set_value_none()
        else:
            # 计算所需尺寸
            rows = (count + cols - 1) // cols
            # 这里的计算要考虑网格间距和边距
            total_h = max(150, min(500, rows * (img_w + 10) + 20))
            total_w = cols * (img_w + 10) + 25  # 预留一点空间给可能的滚动条宽度

            self.setFixedSize(total_w, total_h)
            self.updateGeometry()
            self.sizeHintChanged.emit()

    def set_value_none(self):
        """恢复最初大小"""
        self.setFixedSize(200, 150)
        # 确保容器也不再占用空间
        self.container.resize(180, 130)
        self.updateGeometry()
        self.sizeHintChanged.emit()

    def sizeHint(self):
        return self.size()