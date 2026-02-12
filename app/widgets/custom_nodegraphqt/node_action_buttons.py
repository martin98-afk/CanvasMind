# 节点悬浮快捷按钮
from NodeGraphQt.constants import (
    Z_VAL_NODE_WIDGET, Z_VAL_PIPE
)
from PyQt5 import QtWidgets, QtCore, QtGui


class NodeActionButton(QtWidgets.QGraphicsItem):
    def __init__(self, parent, icon_type, tooltip, color, hover_color, is_permanent=False):
        super(NodeActionButton, self).__init__(parent)
        self.setAcceptHoverEvents(True)
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)
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
        elif self.icon_type == 'layout':
            # 图标：三层节点阶梯分布感 (象征拓扑自动排布)
            # 绘制三个代表节点的小方块，并用折线连接，体现层级流动感
            s_size = 4.0  # 方块大小

            # 1. 绘制三个代表节点的小矩形（左一右二布局）
            # 左侧“父”节点
            rect_parent = QtCore.QRectF(cx - 8, cy - s_size / 2, s_size, s_size)
            # 右侧“子”节点1
            rect_child1 = QtCore.QRectF(cx + 4, cy - 7, s_size, s_size)
            # 右侧“子”节点2
            rect_child2 = QtCore.QRectF(cx + 4, cy + 3, s_size, s_size)

            # 填充方块（悬浮时高亮）
            if self._hovered or self.is_permanent:
                painter.setBrush(painter.pen().color())

            painter.drawRect(rect_parent)
            painter.drawRect(rect_child1)
            painter.drawRect(rect_child2)

            # 2. 绘制连接折线
            painter.setBrush(QtCore.Qt.NoBrush)
            line_pen = QtGui.QPen(painter.pen().color(), 1.2)
            painter.setPen(line_pen)

            # 从父节点引出的折线
            path = QtGui.QPainterPath()
            path.moveTo(cx - 4, cy)  # 父节点右侧中点
            path.lineTo(cx, cy)  # 向右延伸
            path.lineTo(cx, cy - 5)  # 向上折
            path.lineTo(cx + 4, cy - 5)  # 连向子1

            path.moveTo(cx, cy)  # 回到转折点
            path.lineTo(cx, cy + 5)  # 向下折
            path.lineTo(cx + 4, cy + 5)  # 连向子2
            painter.drawPath(path)
        elif self.icon_type == 'more':
            # 绘制三个水平圆点
            dot_size = 3.0
            painter.setBrush(painter.pen().color())
            painter.setPen(QtCore.Qt.NoPen)
            # 左点
            painter.drawEllipse(QtCore.QRectF(cx - 7, cy - dot_size / 2, dot_size, dot_size))
            # 中点
            painter.drawEllipse(QtCore.QRectF(cx - dot_size / 2, cy - dot_size / 2, dot_size, dot_size))
            # 右点
            painter.drawEllipse(QtCore.QRectF(cx + 7 - dot_size, cy - dot_size / 2, dot_size, dot_size))
        elif self.icon_type == 'info':
            # 绘制外圆圈
            painter.drawEllipse(QtCore.QRectF(cx - 7, cy - 7, 14, 14))
            # 绘制感叹号的上半部分
            painter.drawLine(QtCore.QPointF(cx, cy - 3.5), QtCore.QPointF(cx, cy + 1))
            # 绘制感叹号的下半部分点 (小矩形模拟，更清晰)
            painter.setBrush(painter.pen().color())
            painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            painter.drawRect(QtCore.QRectF(cx - 0.75, cy + 2.5, 1.5, 1.5))

        painter.restore()

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
            if self.clicked_func:
                self.clicked_func()
                self.update() # 点击后立刻强制刷新一次状态
        else:
            event.ignore()


class BaseCanvasToolbar(QtWidgets.QGraphicsWidget):
    def __init__(self, viewer=None, parent=None, ignore_transform=True):
        super(BaseCanvasToolbar, self).__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + 9)
        self.viewer = viewer
        if ignore_transform:
            self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)

        self.layout_items = []
        self._padding = 10
        self._spacing = 6
        self._total_width = 0
        self._height = 44  # 稍微加高，增加高级感

    def add_button(self, icon_type, tooltip, color, hover_color, is_permanent=False):
        btn = NodeActionButton(self, icon_type, tooltip, color, hover_color, is_permanent)
        self._add_to_layout(btn)
        return btn

    def add_separator(self):
        sep = QtWidgets.QGraphicsRectItem(0, 0, 1, 24, self)
        sep.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        sep.setBrush(QtGui.QColor(255, 255, 255, 30))
        self._add_to_layout(sep)

    def _add_to_layout(self, item):
        item.setParentItem(self)
        self.layout_items.append(item)
        self._recalculate_layout()

    def _recalculate_layout(self):
        self.prepareGeometryChange()
        x = self._padding
        for item in self.layout_items:
            h = item.boundingRect().height()
            item.setPos(x, (self._height - h) / 2)
            x += item.boundingRect().width() + self._spacing
        self._total_width = x - self._spacing + self._padding

    def boundingRect(self):
        # 增加较大的外扩范围，彻底解决拖拽残影和阴影裁剪
        return QtCore.QRectF(0, 0, self._total_width, self._height).adjusted(-10, -10, 10, 10)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(0, 0, self._total_width, self._height)

        # 1. 绘制软阴影
        for i in range(5):
            opacity = 50 - (i * 10)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(0, 0, 0, opacity))
            painter.drawRoundedRect(rect.adjusted(i, i, i, i), 12 + i, 12 + i)

        # 2. 绘制主体背景 (微梯度玻璃态)
        grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0, QtGui.QColor(45, 45, 50, 240))
        grad.setColorAt(1, QtGui.QColor(25, 25, 30, 255))
        painter.setBrush(grad)

        # 3. 绘制内发光边框 (专业感核心)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 45), 1.2))
        painter.drawRoundedRect(rect, 12, 12)

        # 4. 顶部高光细线 (模拟光源)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 0.8))
        painter.drawLine(int(rect.left() + 12), int(rect.top() + 1), int(rect.right() - 12), int(rect.top() + 1))