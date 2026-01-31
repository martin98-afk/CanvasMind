# -*- coding: utf-8 -*-
from collections import OrderedDict

from NodeGraphQt.constants import (
    ITEM_CACHE_MODE, PortTypeEnum, ICON_NODE_BASE, NodeEnum, Z_VAL_BACKDROP
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from NodeGraphQt.qgraphics.port import CustomPortItem
from qtpy import QtCore, QtGui, QtWidgets

try:
    from app.widgets.custom_nodegraphqt.custom_port_item import GlowPortItem
except ImportError:
    GlowPortItem = CustomPortItem


class ControlFlowBackdropNodeItem(BackdropNodeItem):
    def __init__(self, name='控制流区域', text='', parent=None):
        self._text_item = None
        self._icon_item = None
        self._input_items = OrderedDict()
        self._output_items = OrderedDict()

        # --- 风格定义：在此处统一定义参数，方便后期微调 ---
        self._header_height = 42.0  # 显著增加标题栏高度
        self._header_font_size = 28  # 字体加大
        self._corner_radius = 16.0  # 圆角加大，更具现代感
        self._icon_size = 35.0  # 图标同步加大

        super(ControlFlowBackdropNodeItem, self).__init__(name=name, text=text, parent=parent)

        # 字体加粗加大
        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont("Segoe UI" if QtCore.QSysInfo.productType() == "windows" else "Arial")
        font.setPixelSize(self._header_font_size)
        font.setWeight(QtGui.QFont.Black)  # 使用极致加粗
        self._text_item.setFont(font)
        self._text_item.setDefaultTextColor(QtGui.QColor(255, 255, 255, 240))

        # 图标适配高度
        pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(int(self._icon_size), int(self._icon_size),
                                   QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self._icon_item = QtWidgets.QGraphicsPixmapItem(pixmap, self)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)

        self.setZValue(Z_VAL_BACKDROP)
        self.update_layout()

    # --- 交互区域适配：确保点击新的标题栏高度能拖动 ---
    def shape(self):
        path = QtGui.QPainterPath()
        # 匹配新的 header 高度
        path.addRect(0, 0, self._width, self._header_height)
        if self._sizer:
            path.addRect(self._sizer.boundingRect().translated(self._sizer.pos()))
        return path

    def mousePressEvent(self, event):
        # 匹配新的 header 高度
        if event.pos().y() <= self._header_height:
            super(ControlFlowBackdropNodeItem, self).mousePressEvent(event)
        elif self._sizer and self._sizer.boundingRect().translated(self._sizer.pos()).contains(event.pos()):
            super(ControlFlowBackdropNodeItem, self).mousePressEvent(event)
        else:
            event.ignore()

    # --- 原始端口管理 (完全未改动) ---
    def _add_port(self, port):
        text = QtWidgets.QGraphicsTextItem("", self)
        text.setVisible(False)
        text.setCacheMode(ITEM_CACHE_MODE)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        elif port.port_type == PortTypeEnum.OUT.value:
            self._output_items[port] = text
        self.update_layout()
        return port

    def add_input(self, name='input', multi_port=False, display_name=True, locked=False, painter_func=None):
        port = CustomPortItem(self, painter_func) if painter_func else GlowPortItem(self)
        port.name = name
        port.port_type = PortTypeEnum.IN.value
        port.multi_connection = multi_port
        port.display_name = display_name
        port.locked = locked
        return self._add_port(port)

    def add_output(self, name='output', multi_port=False, display_name=True, locked=False, painter_func=None):
        port = CustomPortItem(self, painter_func) if painter_func else GlowPortItem(self)
        port.name = name
        port.port_type = PortTypeEnum.OUT.value
        port.multi_connection = multi_port
        port.display_name = display_name
        port.locked = locked
        return self._add_port(port)

    # --- 布局优化 ---
    def update_layout(self):
        if not self._text_item or not self._icon_item:
            return

        rect = self.boundingRect()

        # 文字垂直居中于 header
        text_rect = self._text_item.boundingRect()
        tx = rect.center().x() - (text_rect.width() / 2)
        ty = rect.top() + (self._header_height - text_rect.height()) / 2
        self._text_item.setPos(tx, ty)

        # 图标垂直居中于 header
        ix = rect.left() + 15.0  # 稍微增加左间距
        iy = rect.top() + (self._header_height - self._icon_item.pixmap().height()) / 2
        self._icon_item.setPos(ix, iy)

        # 端口对齐位置下移，避免重叠标题栏
        self.align_ports(v_offset=self._header_height + 10.0)

    def align_ports(self, v_offset=0.0):
        width = self._width
        txt_offset = 4
        spacing = 4  # 增加端口间距
        inputs = [p for p in self.inputs if p.isVisible()]
        for i, port in enumerate(inputs):
            port_width = port.boundingRect().width()
            port_height = port.boundingRect().height()
            py = v_offset + i * (port_height + spacing)
            port.setPos(-(port_width / 2), py)
            text = self._input_items.get(port)
            if text: text.setPos(port_width / 2 - txt_offset, py - 1.5)

        outputs = [p for p in self.outputs if p.isVisible()]
        for i, port in enumerate(outputs):
            port_width = port.boundingRect().width()
            port_height = port.boundingRect().height()
            py = v_offset + i * (port_height + spacing)
            port.setPos(width - (port_width / 2), py)
            text = self._output_items.get(port)
            if text:
                txt_width = text.boundingRect().width() - txt_offset
                text.setPos(port.x() - txt_width, py - 1.5)

    @property
    def icon(self):
        return self._properties.get("icon")

    @icon.setter
    def icon(self, value=None):
        self._properties['icon'] = value
        size = int(self._icon_size)
        if isinstance(value, QtGui.QIcon):
            pixmap = value.pixmap(size, size)
        elif isinstance(value, str):
            pixmap = QtGui.QPixmap(value)
        else:
            pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if pixmap.isNull():
            pixmap = QtGui.QPixmap(ICON_NODE_BASE)

        if pixmap.height() > size or pixmap.width() > size:
            pixmap = pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        if self._icon_item:
            self._icon_item.setPixmap(pixmap)
        self.update_layout()

    @property
    def inputs(self):
        return list(self._input_items.keys())

    @property
    def outputs(self):
        return list(self._output_items.keys())

    # --- 绘制优化：提升设计感 ---
    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        margin = 1.0
        rect = self.boundingRect().adjusted(margin, margin, -margin, -margin)
        radius = self._corner_radius

        # 1. 绘制整体半透明背景
        c = self.color
        body_color = QtGui.QColor(c[0], c[1], c[2], 30)  # 降低主体透明度，增加高级感
        painter.setBrush(body_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        # 2. 绘制标题栏背景 (Header)
        header_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width(), self._header_height)
        header_color = QtGui.QColor(*self.color)
        painter.setBrush(header_color)

        # 绘制带圆角的顶部区域（仅上方两角圆润）
        path = QtGui.QPainterPath()
        path.addRoundedRect(header_rect, radius, radius)
        # 将下方多出的圆角补平
        painter.drawPath(path)
        flat_rect = QtCore.QRectF(header_rect.x(), header_rect.y() + self._header_height - radius,
                                  header_rect.width(), radius)
        painter.drawRect(flat_rect)

        # 3. 绘制内部说明文字 (如果有)
        if self.backdrop_text:
            painter.setPen(QtGui.QColor(*self.text_color))
            # 距离标题栏留出更多呼吸空间
            txt_rect = QtCore.QRectF(header_rect.x() + 10.0, header_rect.bottom() + 10.0,
                                     rect.width() - 20.0, rect.height() - self._header_height - 20.0)
            painter.drawText(txt_rect, QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap, self.backdrop_text)

        # 4. 绘制边框
        border_color = QtGui.QColor(*self.color)
        border_width = 1.5  # 稍微加粗边框

        if self.selected:
            # 选中状态：使用较亮的发光效果
            border_color = QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value)
            border_width = 2.0
            # 绘制一个微弱的整体选中遮罩
            painter.setBrush(QtGui.QColor(255, 255, 255, 10))
            painter.drawRoundedRect(rect, radius, radius)

        painter.setBrush(QtCore.Qt.NoBrush)
        pen = QtGui.QPen(border_color, border_width)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, radius, radius)

        painter.restore()

    def on_backdrop_updated(self, update_prop, value):
        super(ControlFlowBackdropNodeItem, self).on_backdrop_updated(update_prop, value)
        self.update_layout()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if not self.disabled:
                if self._text_item and self._text_item.sceneBoundingRect().contains(event.scenePos()):
                    self._text_item.set_editable(True)
                    self._text_item.setFocus()
                    return
            viewer = self.viewer()
            if viewer: viewer.node_double_clicked.emit(self.id)
        super(BackdropNodeItem, self).mouseDoubleClickEvent(event)

    def draw_node(self):
        self.update_layout()

    @AbstractNodeItem.width.setter
    def width(self, width=0.0):
        AbstractNodeItem.width.fset(self, width)
        if self._sizer: self._sizer.set_pos(self._width, self._height)
        self.update_layout()

    @AbstractNodeItem.height.setter
    def height(self, height=0.0):
        AbstractNodeItem.height.fset(self, height)
        if self._sizer: self._sizer.set_pos(self._width, self._height)
        self.update_layout()

    @AbstractNodeItem.name.setter
    def name(self, name=''):
        AbstractNodeItem.name.fset(self, name)
        if self._text_item and name != self._text_item.toPlainText():
            self._text_item.setPlainText(name)
            self.update_layout()