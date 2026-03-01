from Qt import QtGui, QtCore, QtWidgets
from NodeGraphQt.constants import PortEnum, Z_VAL_PORT
from NodeGraphQt.qgraphics.port import PortItem


class GlowPortItem(PortItem):
    _color_cache = {}
    _cache_version = 0
    # 优化：类级别缓存渐变对象
    _glow_cache = {}

    def __init__(self, parent=None):
        super(GlowPortItem, self).__init__(parent)
        self.original_node = None
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)
        self._port_painter = None
        self._cached_base_color = None
        self._cached_rect_w = None
        self._cached_rect_h = None

    def setToolTip(self, tooltip):
        tooltip = tooltip.replace("\n", "<br/>")
        tooltip = "<b>{}</b><br/>{}".format(self._name, tooltip)
        super(GlowPortItem, self).setToolTip(tooltip)

    def set_painter(self, func=None):
        self._port_painter = func
        self.update()

    def boundingRect(self):
        return QtCore.QRectF(
            0.0, 0.0, self._width + PortEnum.CLICK_FALLOFF.value, self._height
        )

    @classmethod
    def _get_cached_color(cls, color_tuple):
        if color_tuple not in cls._color_cache:
            cls._color_cache[color_tuple] = QtGui.QColor(*color_tuple)
        return cls._color_cache[color_tuple]

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super(PortItem, self).hoverEnterEvent(event)

    def paint(self, painter, option, widget):
        parent_node = self.node
        is_selected = parent_node.isSelected() if parent_node else False
        if self._hovered or is_selected:
            self.setZValue(Z_VAL_PORT + 100)
        else:
            self.setZValue(Z_VAL_PORT)

        # 优化：缓存尺寸计算
        if self._cached_rect_w is None:
            self._cached_rect_w = self._width / 1.8
            self._cached_rect_h = self._height / 1.8

        rect_w = self._cached_rect_w
        rect_h = self._cached_rect_h

        orig_rect = QtCore.QRectF(
            0.0, 0.0, self._width + PortEnum.CLICK_FALLOFF.value, self._height
        )
        center = orig_rect.center()
        port_rect = QtCore.QRectF(
            center.x() - rect_w / 2, center.y() - rect_h / 2, rect_w, rect_h
        )
        lod = option.levelOfDetailFromTransform(painter.worldTransform())

        if self._port_painter:
            port_info = {
                "port_type": self.port_type,
                "color": self.color,
                "border_color": self.border_color,
                "connected": bool(self.connected_pipes),
                "hovered": self.hovered,
                "lod": lod,
            }
            self._port_painter(painter, port_rect, port_info)
            return

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        if self._hovered:
            base_color = self._get_cached_color(PortEnum.HOVER_COLOR.value)
        else:
            if not self._cached_base_color or self._cached_base_color[0] != self.color:
                self._cached_base_color = (
                    self.color,
                    self._get_cached_color(self.color),
                )
            base_color = self._cached_base_color[1]

        is_connected = bool(self.connected_pipes)

        if (is_connected or self._hovered) and lod > 0.3:
            glow_radius = rect_w * (2.5 if self._hovered else 1.8)

            # 优化：使用缓存键避免重复创建渐变
            cache_key = (
                glow_radius,
                self._hovered,
                base_color.red(),
                base_color.green(),
                base_color.blue(),
            )
            if cache_key not in GlowPortItem._glow_cache:
                gradient = QtGui.QRadialGradient(center, glow_radius)
                alpha = 120 if self._hovered else 60
                c = base_color
                gradient.setColorAt(
                    0.0, QtGui.QColor(c.red(), c.green(), c.blue(), alpha)
                )
                gradient.setColorAt(
                    0.4, QtGui.QColor(c.red(), c.green(), c.blue(), int(alpha * 0.3))
                )
                gradient.setColorAt(1.0, QtCore.Qt.transparent)
                GlowPortItem._glow_cache[cache_key] = gradient
            else:
                gradient = GlowPortItem._glow_cache[cache_key]

            painter.setBrush(gradient)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(center, glow_radius, glow_radius)

        pen_width = 2.5 if lod > 0.7 else 2.5 / lod
        if self._hovered:
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 255), pen_width))
        else:
            painter.setPen(QtGui.QPen(base_color.lighter(120), pen_width))

        if is_connected or self._hovered:
            painter.setBrush(base_color)
        else:
            painter.setBrush(QtGui.QColor(35, 35, 35))

        painter.drawEllipse(port_rect)

        if is_connected and not self._hovered:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(255, 255, 255, 150))
            painter.drawEllipse(center, rect_w * 0.2, rect_w * 0.2)

        painter.restore()


# --- 优化后的特殊端口 (紫色霓虹) ---
def draw_special_outputport(painter, rect, info):
    painter.save()
    painter.setRenderHint(QtGui.QPainter.Antialiasing)

    lod = info.get("lod", 1.0)
    center = rect.center()
    radius = rect.width() / 2
    NEON_PURPLE = QtGui.QColor(191, 0, 255)
    is_connected = info["connected"]
    is_hovered = info["hovered"]

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
    ring_pen = QtGui.QPen(
        QtCore.Qt.white if is_hovered else NEON_PURPLE,
        2.0 / (lod if lod < 1.0 else 1.0),
    )
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
    is_connected = info["connected"]
    is_hovered = info["hovered"]

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
