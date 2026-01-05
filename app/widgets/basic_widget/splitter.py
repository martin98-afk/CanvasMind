# -*- coding: utf-8 -*-
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QRect, QPoint, QSize, QVariantAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QLinearGradient, QBrush, QFont, QPainterPath, QPolygon
from PyQt5.QtWidgets import QSplitter, QSplitterHandle


class CyberSplitterHandle(QSplitterHandle):
    """
    极致科技感分割器手柄：
    - 动态能量脉冲
    - 数字化 HUD 坐标读数
    - 霓虹边缘折射效果
    """

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hovered = False
        self._pressed = False
        self._pulse_pos = 0.0  # 能量脉冲位置 0.0 -> 1.0

        # 能量脉冲动画控制
        self.pulse_anim = QVariantAnimation(self)
        self.pulse_anim.setDuration(2000)
        self.pulse_anim.setStartValue(0.0)
        self.pulse_anim.setEndValue(1.0)
        self.pulse_anim.setLoopCount(-1)  # 无限循环
        self.pulse_anim.valueChanged.connect(self._update_pulse)
        self.pulse_anim.start()

        # 鼠标形状
        self.setCursor(Qt.SplitHCursor if orientation == Qt.Horizontal else Qt.SplitVCursor)

    def _update_pulse(self, value):
        self._pulse_pos = value
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.pulse_anim.setDuration(800)  # 悬停时脉冲加快，更有“通电”感
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.pulse_anim.setDuration(2000)  # 离开恢复常态
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        is_hor = self.orientation() == Qt.Horizontal

        # --- 颜色方案 ---
        neon_blue = QColor("#00f0ff")  # 高亮赛博蓝
        dark_blue = QColor(0, 162, 255, 100)
        bg_dark = QColor(10, 10, 10, 200)  # 磨砂背景

        # 1. 绘制磨砂导轨背景
        path = QPainterPath()
        path.addRect(QtCore.QRectF(rect))
        painter.fillPath(path, QBrush(bg_dark))

        # 2. 绘制边缘发光线条 (冷光)
        edge_pen = QPen(QColor(255, 255, 255, 15 if not self._hovered else 40), 1)
        painter.setPen(edge_pen)
        if is_hor:
            painter.drawLine(0, 0, 0, rect.height())
            painter.drawLine(rect.width() - 1, 0, rect.width() - 1, rect.height())
        else:
            painter.drawLine(0, 0, rect.width(), 0)
            painter.drawLine(0, rect.height() - 1, rect.width(), rect.height() - 1)

        # 3. 绘制能量中心线
        mid = rect.center().x() if is_hor else rect.center().y()

        # 底色暗线
        line_pen = QPen(QColor(40, 40, 40), 1)
        painter.setPen(line_pen)
        if is_hor:
            painter.drawLine(mid, 10, mid, rect.height() - 10)
        else:
            painter.drawLine(10, mid, rect.width() - 10, mid)

        # 4. 绘制能量脉冲 (Energy Pulse)
        pulse_color = neon_blue if self._hovered else dark_blue
        pulse_grad = QLinearGradient()
        if is_hor:
            start_y = self._pulse_pos * rect.height()
            pulse_grad.setStart(mid, start_y - 40)
            pulse_grad.setFinalStop(mid, start_y + 40)
        else:
            start_x = self._pulse_pos * rect.width()
            pulse_grad.setStart(start_x - 40, mid)
            pulse_grad.setFinalStop(start_x + 40, mid)

        pulse_grad.setColorAt(0, QColor(0, 240, 255, 0))
        pulse_grad.setColorAt(0.5, pulse_color)
        pulse_grad.setColorAt(1, QColor(0, 240, 255, 0))

        painter.setPen(QPen(QBrush(pulse_grad), 2 if self._hovered else 1))
        if is_hor:
            painter.drawLine(mid, 0, mid, rect.height())
        else:
            painter.drawLine(0, mid, rect.width(), mid)

        # 5. 绘制 HUD 数字化刻度 (仅在 Hover 时显示)
        if self._hovered or self._pressed:
            self._draw_hud_decals(painter, rect, is_hor, neon_blue)

    def _draw_hud_decals(self, painter, rect, is_hor, color):
        """绘制 HUD 风格的数字化读数"""
        painter.setFont(QFont("Consolas", 7))
        painter.setPen(QPen(color))

        # 获取 Splitter 状态 (计算百分比)
        splitter = self.parentWidget()
        if splitter:
            sizes = splitter.sizes()
            total = sum(sizes) if sum(sizes) > 0 else 1
            percent = int((sizes[0] / total) * 100)

            txt = f"{percent}%"
            cx, cy = rect.center().x(), rect.center().y()

            if is_hor:
                # 顶部小三角装饰
                painter.setBrush(QBrush(color))
                tri = QPolygon([QPoint(cx - 3, 5), QPoint(cx + 3, 5), QPoint(cx, 10)])
                painter.drawPolygon(tri)

                # 底部读数
                painter.drawText(rect.adjusted(0, 0, 0, -5), Qt.AlignBottom | Qt.AlignHCenter, txt)

                # 两侧微缩刻度线
                for i in range(10, rect.height(), 20):
                    painter.drawLine(0, i, 2, i)
                    painter.drawLine(rect.width() - 2, i, rect.width(), i)
            else:
                # 左右小三角
                painter.setBrush(QBrush(color))
                tri = QPolygon([QPoint(5, cy - 3), QPoint(5, cy + 3), QPoint(10, cy)])
                painter.drawPolygon(tri)

                painter.drawText(rect.adjusted(5, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, txt)


class ModernSplitter(QSplitter):
    """
    极致赛博感分割器：适配高科技属性面板。
    """

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setHandleWidth(10)  # 稍微加宽手柄，增强 HUD 表现空间
        self.setStyleSheet("""
            QSplitter {
                background-color: transparent;
                border: none;
            }
            QSplitter::handle {
                background: none;
            }
        """)

    def createHandle(self):
        return CyberSplitterHandle(self.orientation(), self)