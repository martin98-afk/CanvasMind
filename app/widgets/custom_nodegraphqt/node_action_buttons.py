# 节点悬浮快捷按钮
from NodeGraphQt.constants import (
    Z_VAL_NODE_WIDGET
)
from PyQt5 import QtWidgets, QtCore, QtGui


class NodeActionButton(QtWidgets.QGraphicsItem):
    def __init__(self, parent, icon_type, tooltip, color, hover_color, is_permanent=False):
        super(NodeActionButton, self).__init__(parent)
        self.setAcceptHoverEvents(True)
        self.setZValue(Z_VAL_NODE_WIDGET + 10)
        self.icon_type = icon_type
        self.setToolTip(tooltip)
        self.color = QtGui.QColor(color)
        self.hover_color = QtGui.QColor(hover_color)
        self.is_permanent = is_permanent
        self._hovered = False
        self._rect = QtCore.QRectF(0, 0, 28, 28)
        self.clicked_func = None

    def boundingRect(self):
        return self._rect

    def shape(self):
        path = QtGui.QPainterPath()
        path.addEllipse(self._rect)
        return path

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        if self._hovered:
            painter.setBrush(self.hover_color)
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1.5))
        elif self.is_permanent:
            painter.setBrush(self.color)
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 0.5))
        else:
            painter.setBrush(QtGui.QColor(255, 255, 255, 15))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 30), 1.0))

        painter.drawRoundedRect(self._rect, 8, 8)
        icon_opacity = 255 if (self._hovered or self.is_permanent) else 150
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, icon_opacity), 2.0)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)

        m = 8.5
        r = self._rect
        cx, cy = r.center().x(), r.center().y()

        if self.icon_type == 'collapse':
            painter.drawLine(QtCore.QPointF(r.left() + m, cy), QtCore.QPointF(r.right() - m, cy))
        elif self.icon_type == 'expand':
            painter.drawLine(QtCore.QPointF(r.left() + m, cy), QtCore.QPointF(r.right() - m, cy))
            painter.drawLine(QtCore.QPointF(cx, r.top() + m), QtCore.QPointF(cx, r.bottom() - m))
        elif self.icon_type == 'run':
            path = QtGui.QPainterPath()
            path.moveTo(r.left() + m + 1, r.top() + m - 1)
            path.lineTo(r.right() - m + 2, cy)
            path.lineTo(r.left() + m + 1, r.bottom() - m + 1)
            path.closeSubpath()
            if self._hovered or self.is_permanent: painter.setBrush(QtCore.Qt.white)
            painter.drawPath(path)
        elif self.icon_type == 'debug':
            painter.drawEllipse(QtCore.QRectF(cx - 4, cy - 3, 8, 9))
            painter.drawLine(QtCore.QPointF(cx, cy - 3), QtCore.QPointF(cx, cy + 6))
            painter.drawArc(QtCore.QRectF(cx - 2.5, cy - 5, 5, 4), 0, 180 * 16)
            for i in [-1, 1]:
                painter.drawLine(QtCore.QPointF(cx + 4 * i, cy), QtCore.QPointF(cx + 6.5 * i, cy - 1))
                painter.drawLine(QtCore.QPointF(cx + 4 * i, cy + 3), QtCore.QPointF(cx + 7 * i, cy + 3))
                painter.drawLine(QtCore.QPointF(cx + 4 * i, cy + 6), QtCore.QPointF(cx + 6.5 * i, cy + 7))
        elif self.icon_type == 'comment':
            # 图标：气泡/便签样式 (用于注释)
            painter.drawRoundedRect(QtCore.QRectF(cx - 7, cy - 5, 14, 11), 2, 2)
            painter.drawLine(QtCore.QPointF(cx - 4, cy - 1), QtCore.QPointF(cx + 4, cy - 1))
            painter.drawLine(QtCore.QPointF(cx - 4, cy + 2), QtCore.QPointF(cx + 1, cy + 2))

        elif self.icon_type == 'clone':
            # 图标：双层矩形 (用于克隆/拷贝)
            # 底层矩形
            painter.drawRoundedRect(QtCore.QRectF(cx - 6, cy - 6, 9, 9), 1, 1)
            # 顶层矩形 (带背景填充，增加重叠感)
            painter.setBrush(painter.pen().color())
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(QtCore.QRectF(cx - 1, cy - 1, 9, 9), 1, 1)
            # 补回顶层边框
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(pen)
            painter.drawRoundedRect(QtCore.QRectF(cx - 1, cy - 1, 9, 9), 1, 1)

        elif self.icon_type == 'template':
            # 图标：魔法棒或方框带星星 (用于加入模板库)
            painter.drawRoundedRect(QtCore.QRectF(cx - 7, cy - 7, 14, 14), 2, 2)
            # 绘制内部的星形交叉
            s = 3.5
            painter.drawLine(QtCore.QPointF(cx - s, cy), QtCore.QPointF(cx + s, cy))
            painter.drawLine(QtCore.QPointF(cx, cy - s), QtCore.QPointF(cx, cy + s))
            painter.drawPoint(QtCore.QPointF(cx, cy))
        elif self.icon_type == 'zoom':
            o, l = 7.0, 4.0
            for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
                painter.drawLine(QtCore.QPointF(cx + o * dx, cy + o * dy),
                                 QtCore.QPointF(cx + (o - l) * dx, cy + o * dy))
                painter.drawLine(QtCore.QPointF(cx + o * dx, cy + o * dy),
                                 QtCore.QPointF(cx + o * dx, cy + (o - l) * dy))
        elif self.icon_type == 'close':
            painter.drawLine(QtCore.QPointF(r.left() + m, r.top() + m), QtCore.QPointF(r.right() - m, r.bottom() - m))
            painter.drawLine(QtCore.QPointF(r.right() - m, r.top() + m), QtCore.QPointF(r.left() + m, r.bottom() - m))
        elif self.icon_type == 'exec_ipython':
            path = QtGui.QPainterPath()
            path.moveTo(cx + 2, cy - 7)
            path.lineTo(cx - 4, cy + 1)
            path.lineTo(cx + 1, cy + 1)
            path.lineTo(cx - 2, cy + 7)
            painter.drawPath(path)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 100), 1.0, QtCore.Qt.DashLine))
            painter.drawEllipse(QtCore.QRectF(cx - 9, cy - 9, 18, 18))
        elif self.icon_type == 'exec_subprocess':
            painter.drawRoundedRect(QtCore.QRectF(cx - 8, cy - 7, 16, 14), 2, 2)
            painter.drawLine(QtCore.QPointF(cx - 8, cy - 2), QtCore.QPointF(cx + 8, cy - 2))
            painter.drawLine(QtCore.QPointF(cx - 4, cy + 2), QtCore.QPointF(cx - 2, cy + 4))
            painter.drawLine(QtCore.QPointF(cx - 2, cy + 4), QtCore.QPointF(cx - 4, cy + 6))
        painter.restore()

    def hoverEnterEvent(self, event):
        self._hovered = True;
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False;
        self.update()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
            if self.clicked_func: self.clicked_func()
        else:
            event.ignore()