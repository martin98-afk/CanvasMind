from Qt import QtGui, QtCore, QtWidgets
from NodeGraphQt.constants import PortEnum, Z_VAL_PORT
from NodeGraphQt.qgraphics.port import PortItem


class GlowPortItem(PortItem):
    def __init__(self, parent=None):
        super(GlowPortItem, self).__init__(parent)
        self.original_node = None
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)
        self._port_painter = None

    def setToolTip(self, tooltip):
        tooltip = tooltip.replace('\n', '<br/>')
        tooltip = '<b>{}</b><br/>{}'.format(self._name, tooltip)
        super(GlowPortItem, self).setToolTip(tooltip)

    def set_painter(self, func=None):
        self._port_painter = func
        self.update()

    def boundingRect(self):
        return QtCore.QRectF(0.0, 0.0, self._width + PortEnum.CLICK_FALLOFF.value, self._height)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()  # 强制触发所有视口重绘
        super(PortItem, self).hoverEnterEvent(event)

    def paint(self, painter, option, widget):
        # --- 1. 动态层级 ---
        parent_node = self.node
        is_selected = parent_node.isSelected() if parent_node else False
        if self._hovered or is_selected:
            self.setZValue(Z_VAL_PORT + 100)
        else:
            self.setZValue(Z_VAL_PORT)

        # --- 2. 几何位置 (保持原逻辑) ---
        rect_w = self._width / 1.8
        rect_h = self._height / 1.8
        orig_rect = QtCore.QRectF(0.0, 0.0, self._width + PortEnum.CLICK_FALLOFF.value, self._height)
        center = orig_rect.center()
        port_rect = QtCore.QRectF(center.x() - rect_w / 2, center.y() - rect_h / 2, rect_w, rect_h)
        lod = option.levelOfDetailFromTransform(painter.worldTransform())

        # --- 3. 逻辑分流 ---
        if self._port_painter:
            port_info = {
                'port_type': self.port_type,
                'color': self.color,
                'border_color': self.border_color,
                'connected': bool(self.connected_pipes),
                'hovered': self.hovered,
                'lod': lod
            }
            self._port_painter(painter, port_rect, port_info)
            return

        # --- 4. 优化后的 ComfyUI 风格绘制 ---
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 基础色提取
        if self._hovered:
            base_color = QtGui.QColor(*PortEnum.HOVER_COLOR.value)
        else:
            base_color = QtGui.QColor(*self.color)

        is_connected = bool(self.connected_pipes)

        # A. 核心发光 (Glow) - 仅在连接或悬浮时显示
        # 优化点：多级渐变，模拟真实光晕
        if (is_connected or self._hovered) and lod > 0.3:
            glow_radius = rect_w * (2.5 if self._hovered else 1.8)
            gradient = QtGui.QRadialGradient(center, glow_radius)

            # ComfyUI 风格的光晕通常带有高透明度的扩散
            alpha = 120 if self._hovered else 60
            c = base_color
            gradient.setColorAt(0.0, QtGui.QColor(c.red(), c.green(), c.blue(), alpha))
            gradient.setColorAt(0.4, QtGui.QColor(c.red(), c.green(), c.blue(), int(alpha * 0.3)))
            gradient.setColorAt(1.0, QtCore.Qt.transparent)

            painter.setBrush(gradient)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(center, glow_radius, glow_radius)

        # B. 绘制外边框 (Ring)
        pen_width = 2.5 if lod > 0.7 else 2.5 / lod
        if self._hovered:
            # 悬浮时边框变白发亮
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 255), pen_width))
        else:
            # 默认边框比底色略亮一点
            painter.setPen(QtGui.QPen(base_color.lighter(120), pen_width))

        # C. 填充背景 (Core)
        if is_connected or self._hovered:
            # 连接态：实心
            painter.setBrush(base_color)
        else:
            # 非连接态：空心（深色背景）
            painter.setBrush(QtGui.QColor(35, 35, 35))

        painter.drawEllipse(port_rect)

        # D. 绘制中心高亮小点 (可选，增加精致感)
        if is_connected and not self._hovered:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(255, 255, 255, 150))
            painter.drawEllipse(center, rect_w * 0.2, rect_w * 0.2)

        painter.restore()


# --- 优化后的特殊端口 (紫色霓虹) ---
def draw_special_outputport(painter, rect, info):
    painter.save()
    painter.setRenderHint(QtGui.QPainter.Antialiasing)

    lod = info.get('lod', 1.0)
    center = rect.center()
    radius = rect.width() / 2
    NEON_PURPLE = QtGui.QColor(191, 0, 255)
    is_connected = info['connected']
    is_hovered = info['hovered']

    # 1. 弥散霓虹发光
    if (is_connected or is_hovered) and lod > 0.2:
        glow_size = radius * (4.0 if is_hovered else 2.5)
        grad = QtGui.QRadialGradient(center, glow_size)
        alpha = 180 if is_hovered else 80
        grad.setColorAt(0, QtGui.QColor(191, 0, 255, alpha))
        grad.setColorAt(0.5, QtGui.QColor(191, 0, 255, int(alpha * 0.2)))
        grad.setColorAt(1, QtCore.Qt.transparent)
        painter.setBrush(grad)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(center, glow_size, glow_size)

    # 2. 霓虹外环
    ring_pen = QtGui.QPen(QtCore.Qt.white if is_hovered else NEON_PURPLE, 2.0 / (lod if lod < 1.0 else 1.0))
    painter.setPen(ring_pen)

    # 3. 内部填充
    if is_connected or is_hovered:
        painter.setBrush(NEON_PURPLE.darker(150) if is_hovered else NEON_PURPLE)
    else:
        painter.setBrush(QtGui.QColor(20, 20, 20))  # 空心感

    painter.drawEllipse(rect)

    # 4. 核心亮点
    if is_connected:
        painter.setBrush(QtCore.Qt.white)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(center, radius * 0.3, radius * 0.3)

    painter.restore()


# --- 优化后的方型端口 ---
def draw_square_port(painter, rect, info):
    painter.save()
    painter.setRenderHint(QtGui.QPainter.Antialiasing)

    base_color = QtGui.QColor(195, 60, 60)
    is_connected = info['connected']
    is_hovered = info['hovered']

    if is_hovered:
        border_color = QtGui.QColor(255, 255, 255)
        fill_color = base_color
    elif is_connected:
        border_color = base_color.lighter(130)
        fill_color = base_color
    else:
        border_color = base_color.darker(120)
        fill_color = QtGui.QColor(40, 40, 40)

    painter.setPen(QtGui.QPen(border_color, 2.5))
    painter.setBrush(fill_color)
    # 使用稍微圆角的矩形看起来比纯直角更现代
    painter.drawRoundedRect(rect, 2, 2)
    painter.restore()