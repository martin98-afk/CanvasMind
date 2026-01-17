# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QMouseEvent
from PyQt5.QtCore import Qt, QPoint, QSize, QByteArray, QBuffer
import base64
from io import BytesIO

class MaskCanvas(QWidget):
    """用于在画面上进行涂抹绘制蒙板"""

    def __init__(self, base64_image: str, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.drawing = False
        self.last_pos = QPoint()
        self.brush_size = 30
        self.brush_color = QColor(255, 255, 255, 255)  # 不透明白色（用于 alpha）

        # 解码 base64 图像
        image_data = base64.b64decode(base64_image.split(",")[-1])  # 支持 data:image/png;base64,...
        self.original_pixmap = QPixmap()
        self.original_pixmap.loadFromData(image_data)

        # 创建遮罩层（RGBA）
        self.mask_image = QImage(
            self.original_pixmap.size(),
            QImage.Format.Format_ARGB32
        )
        self.mask_image.fill(QColor(0, 0, 0, 0))  # 完全透明

        self.setMinimumSize(self.original_pixmap.size())
        self.setMaximumSize(self.original_pixmap.size())

    def paintEvent(self, event):
        painter = QPainter(self)
        # 绘制原图
        painter.drawPixmap(0, 0, self.original_pixmap)
        # 叠加遮罩（半透明白色便于观察）
        overlay = self.mask_image.copy()
        overlay_painter = QPainter(overlay)
        overlay_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        overlay_painter.fillRect(overlay.rect(), QColor(255, 255, 255, 100))
        overlay_painter.end()
        painter.drawImage(0, 0, overlay)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.last_pos = event.pos()
            self.draw_brush(event.pos())
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drawing:
            self.draw_brush(event.pos())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = False

    def draw_brush(self, pos: QPoint):
        painter = QPainter(self.mask_image)
        painter.setPen(QPen(self.brush_color, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPoint(pos)
        painter.end()

    def get_alpha_as_base64(self) -> str:
        """提取 alpha 通道并返回 base64 编码的灰度 PNG 图像"""
        w, h = self.mask_image.width(), self.mask_image.height()
        alpha_img = QImage(w, h, QImage.Format_Grayscale8)

        # 提取 alpha 并写入灰度图
        for y in range(h):
            for x in range(w):
                alpha = self.mask_image.pixelColor(x, y).alpha()
                alpha_img.setPixelColor(x, y, QColor(alpha, alpha, alpha))

        # 使用 QBuffer 将 QImage 写入内存
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QBuffer.WriteOnly)
        alpha_img.save(buffer, "PNG")
        buffer.close()

        # 转为 base64 字符串
        b64_str = bytes(byte_array.toBase64()).decode("utf-8")
        return f"data:image/png;base64,{b64_str}"