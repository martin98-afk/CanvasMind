# -*- coding: utf-8 -*-
from PyQt5.QtCore import QPropertyAnimation, pyqtProperty, QRectF
from PyQt5.QtGui import QPainter
from qfluentwidgets import TransparentToolButton


class RotatingStatusButton(TransparentToolButton):
    def __init__(self, icon, animation_duration=1000, parent=None):
        super().__init__(icon)
        self._angle = 0
        self._is_animating = False

        # 定义动画：控制 angle 属性从 0 到 360
        self.animation = QPropertyAnimation(self, b"angle")
        self.animation.setStartValue(0)
        self.animation.setEndValue(360)
        self.animation.setDuration(animation_duration)  # 1秒转一圈
        self.animation.setLoopCount(-1)  # 无限循环

    @pyqtProperty(float)
    def angle(self):
        return self._angle

    @angle.setter
    def angle(self, value):
        self._angle = value
        self.update()  # 触发重绘

    def start_rotation(self):
        if not self._is_animating:
            self._is_animating = True
            self.animation.start()

    def stop_rotation(self):
        self._is_animating = False
        self.animation.stop()
        self._angle = 0
        self.update()

    def paintEvent(self, event):
        # 如果不是运行状态，使用默认绘制
        if not self._is_animating:
            super().paintEvent(event)
            return

        # 运行状态下自定义绘制（旋转图标）
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 计算旋转中心
        rect = self.rect()
        center = rect.center()

        # 获取当前图标的 Pixmap
        icon_size = self.iconSize()
        pixmap = self.icon().pixmap(icon_size)

        painter.translate(center.x(), center.y())
        painter.rotate(self._angle)

        # 绘制图标（偏移回到左上角位置以保证居中）
        target_rect = QRectF(-icon_size.width() / 2, -icon_size.height() / 2,
                             icon_size.width(), icon_size.height())
        painter.drawPixmap(target_rect.toRect(), pixmap)
        painter.end()
