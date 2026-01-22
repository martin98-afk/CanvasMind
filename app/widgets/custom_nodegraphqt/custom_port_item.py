#!/usr/bin/python
# 必须从原路径导入 PortItem 以保留所有连线逻辑
from NodeGraphQt.constants import PortEnum, Z_VAL_PORT
from NodeGraphQt.qgraphics.port import PortItem
from PyQt5 import QtWidgets
from Qt import QtGui, QtCore


class GlowPortItem(PortItem):
    """
    修复了对齐问题的发光端口类。
    """

    def __init__(self, parent=None):
        super(GlowPortItem, self).__init__(parent)
        # 提高绘制质量
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)

    def boundingRect(self):
        """
        保持与原始 PortItem 相同的 BoundingRect 逻辑，确保对齐正确。
        """
        # 必须保持原点在 (0.0, 0.0)，否则节点布局会错乱
        return QtCore.QRectF(0.0, 0.0,
                             self._width + PortEnum.CLICK_FALLOFF.value,
                             self._height)

    def paint(self, painter, option, widget):
        """
        美化后的绘制函数
        """
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # --- 1. 计算核心几何位置 (完全对齐原始位置) ---
        # 这里的计算逻辑必须与原始类保持一致，以确保圆心对齐
        rect_w = self._width / 1.8
        rect_h = self._height / 1.8
        # 获取原始 BoundingRect 的中心
        orig_rect = QtCore.QRectF(0.0, 0.0, self._width + PortEnum.CLICK_FALLOFF.value, self._height)
        center = orig_rect.center()

        # 实际绘制端口的矩形
        port_rect = QtCore.QRectF(center.x() - rect_w / 2, center.y() - rect_h / 2, rect_w, rect_h)

        # --- 2. 缩放适配逻辑 ---
        # 获取当前的缩放比例 (LOD)
        lod = option.levelOfDetailFromTransform(painter.worldTransform())

        # --- 3. 颜色定义 ---
        if self._hovered:
            base_color = QtGui.QColor(*PortEnum.HOVER_COLOR.value)
            border_color = QtGui.QColor(255, 255, 255, 255)  # 悬浮时边框变白
        elif self.connected_pipes:
            base_color = QtGui.QColor(*PortEnum.ACTIVE_COLOR.value)
            border_color = QtGui.QColor(*PortEnum.ACTIVE_BORDER_COLOR.value)
        else:
            base_color = QtGui.QColor(*self.color)
            border_color = QtGui.QColor(*self.border_color)

        # --- 4. 绘制发光特效 (Glow) ---
        # 只有在鼠标悬浮或连接时才显示微光，缩放越小时发光越强
        if self._hovered or (self.connected_pipes and lod < 0.4):
            glow_size = rect_w * (2.0 if lod > 0.5 else 4.0 / (lod + 0.1))
            gradient = QtGui.QRadialGradient(center, glow_size)

            # 设置渐变色
            alpha = 150 if self._hovered else 80
            c = base_color
            gradient.setColorAt(0.0, QtGui.QColor(c.red(), c.green(), c.blue(), alpha))
            gradient.setColorAt(0.5, QtGui.QColor(c.red(), c.green(), c.blue(), int(alpha * 0.3)))
            gradient.setColorAt(1.0, QtCore.Qt.transparent)

            painter.setBrush(gradient)
            painter.setPen(QtCore.Qt.NoPen)
            # 这里的绘制不受 port_rect 限制，可以超出 boundingRect 少许
            # 注意：如果发光范围极大，需要适当调大 boundingRect 的宽度
            painter.drawEllipse(center, glow_size, glow_size)

        # --- 5. 绘制端口外圈 (Border) ---
        # 线条粗细随缩放调整，保证小缩放时依然可见
        line_width = 1.2 if lod > 0.8 else 1.2 / lod
        pen = QtGui.QPen(border_color, line_width)
        painter.setPen(pen)

        # 填充内色
        if self._hovered:
            painter.setBrush(base_color)
        else:
            # 未悬浮时，内部稍微暗一点，增加立体感
            painter.setBrush(base_color.darker(120))

        painter.drawEllipse(port_rect)

        # --- 6. 绘制中心圆芯 (Core) ---
        # 模仿现代 UI 的“实心点”感
        if self.connected_pipes or self._hovered:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(border_color)
            core_size = port_rect.width() * 0.4
            painter.drawEllipse(center, core_size, core_size)

        painter.restore()

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()  # 强制触发重绘以显示发光
        super(GlowPortItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()  # 强制触发重绘以关闭发光
        super(GlowPortItem, self).hoverLeaveEvent(event)


# --- 特殊端口绘制函数 ---
def draw_special_outputport(painter, rect, info):
    """
    紫色特殊端口：极致霓虹感 + 能量核设计
    """
    painter.save()
    painter.setRenderHint(QtGui.QPainter.Antialiasing)

    lod = info.get('lod', 1.0)
    center = rect.center()
    radius = rect.width() / 2

    NEON_PURPLE = QtGui.QColor(191, 0, 255)

    # 1. 强力径向发光层
    glow_mul = 4.0 if lod > 0.5 else 8.0 / lod
    grad = QtGui.QRadialGradient(center, radius * glow_mul)
    alpha = 150 if info['hovered'] else 70
    grad.setColorAt(0, QtGui.QColor(191, 0, 255, alpha))
    grad.setColorAt(0.6, QtGui.QColor(191, 0, 255, int(alpha / 4)))
    grad.setColorAt(1, QtCore.Qt.transparent)
    painter.setBrush(grad)
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawEllipse(center, radius * glow_mul, radius * glow_mul)

    # 2. 霓虹外环 (高亮外圈)
    ring_w = 1.8 if lod > 0.5 else 1.8 / lod
    if info['hovered']:
        painter.setPen(QtGui.QPen(QtCore.Qt.white, ring_w))
    else:
        painter.setPen(QtGui.QPen(NEON_PURPLE, ring_w))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawEllipse(center, radius * 1.35, radius * 1.35)

    # 3. 端口暗色主体
    body_color = QtGui.QColor(30, 0, 50)
    painter.setBrush(body_color)
    painter.drawEllipse(rect)

    # 4. 能量中心点 (Core)
    if info['connected'] or info['hovered']:
        core_color = QtCore.Qt.white if info['hovered'] else NEON_PURPLE
        painter.setBrush(core_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(center, radius * 0.5, radius * 0.5)

    painter.restore()


def draw_square_port(painter, rect, info):
    """
    Custom paint function for drawing a Square shaped port.

    Args:
        painter (QtGui.QPainter): painter object.
        rect (QtCore.QRectF): port rect used to describe parameters needed to draw.
        info (dict): information describing the ports current state.
            {
                'port_type': 'in',
                'color': (0, 0, 0),
                'border_color': (255, 255, 255),
                'multi_connection': False,
                'connected': False,
                'hovered': False,
            }
    """
    painter.save()

    # mouse over port color.
    if info['hovered']:
        color = QtGui.QColor(14, 45, 59)
        border_color = QtGui.QColor(136, 255, 35, 255)
    # port connected color.
    elif info['connected']:
        color = QtGui.QColor(195, 60, 60)
        border_color = QtGui.QColor(200, 130, 70)
    # default port color
    else:
        color = QtGui.QColor(*info['color'])
        border_color = QtGui.QColor(*info['border_color'])

    pen = QtGui.QPen(border_color, 1.8)
    pen.setJoinStyle(QtCore.Qt.MiterJoin)

    painter.setPen(pen)
    painter.setBrush(color)
    painter.drawRect(rect)

    painter.restore()