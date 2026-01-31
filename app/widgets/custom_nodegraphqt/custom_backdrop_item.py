# --- 仅在你的类中添加/覆盖以下两个方法，其余代码保持原封不动 ---

def shape(self):
    """定义点击碰撞区域：仅限标题栏和缩放手柄"""
    path = QtGui.QPainterPath()
    # 1. 标题栏区域 (高度26.0)
    path.addRect(0, 0, self._width, 26.0)

    # 2. 缩放手柄区域 (必须包含，否则无法通过右下角 resize)
    if self._sizer:
        # 将 sizer 的形状映射到当前 node 的坐标系中
        sizer_rect = self._sizer.boundingRect().translated(self._sizer.pos())
        path.addRect(sizer_rect)

    return path


def mousePressEvent(self, event):
    """处理点击事件"""
    # 如果点击的是标题栏或缩放手柄，执行默认逻辑（选中/拖动/缩放）
    # 否则忽略事件，使其穿透到下方的节点
    header_height = 26.0
    if event.pos().y() <= header_height:
        super(ControlFlowBackdropNodeItem, self).mousePressEvent(event)
    elif self._sizer and self._sizer.boundingRect().translated(self._sizer.pos()).contains(event.pos()):
        super(ControlFlowBackdropNodeItem, self).mousePressEvent(event)
    else:
        event.ignore()  # 穿透


# --- 以下是你原始代码的完整还原，仅植入了上述逻辑 ---

# -*- coding: utf-8 -*-
from collections import OrderedDict

from NodeGraphQt.constants import (
    ITEM_CACHE_MODE, PortTypeEnum, Z_VAL_NODE,
    ICON_NODE_BASE, NodeEnum, Z_VAL_BACKDROP
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

        super(ControlFlowBackdropNodeItem, self).__init__(name=name, text=text, parent=parent)

        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont()
        font.setPointSize(16)
        font.setBold(True)
        self._text_item.setFont(font)
        self._text_item.setDefaultTextColor(QtGui.QColor("white"))

        pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(28, 28, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self._icon_item = QtWidgets.QGraphicsPixmapItem(pixmap, self)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)

        self.setZValue(Z_VAL_BACKDROP)
        self.update_layout()

    # --- 新增：实现标题选中与穿透，同时保留 Resize 功能 ---
    def shape(self):
        path = QtGui.QPainterPath()
        path.addRect(0, 0, self._width, 26.0)  # 标题栏
        if self._sizer:
            path.addRect(self._sizer.boundingRect().translated(self._sizer.pos()))  # 缩放手柄
        return path

    def mousePressEvent(self, event):
        if event.pos().y() <= 26.0:
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

    # --- 原始属性与布局 (完全未改动) ---
    @property
    def icon(self):
        return self._properties.get("icon")

    @icon.setter
    def icon(self, value=None):
        self._properties['icon'] = value
        if isinstance(value, QtGui.QIcon):
            pixmap = value.pixmap(28, 28)
        elif isinstance(value, str):
            pixmap = QtGui.QPixmap(value)
        else:
            pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if pixmap.isNull():
            pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if pixmap.height() > 28 or pixmap.width() > 28:
            pixmap = pixmap.scaled(28, 28, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        if self._icon_item:
            self._icon_item.setPixmap(pixmap)
        self.update_layout()

    def update_layout(self):
        if not self._text_item or not self._icon_item:
            return
        rect = self.boundingRect()
        header_height = 26.0
        text_rect = self._text_item.boundingRect()
        tx = rect.center().x() - (text_rect.width() / 2)
        self._text_item.setPos(tx, rect.y())
        self._icon_item.setPos(rect.left() + 10.0, rect.top() + (header_height - self._icon_item.pixmap().height()) / 2)
        self.align_ports(v_offset=header_height + 5.0)

    def align_ports(self, v_offset=0.0):
        width = self._width
        txt_offset = 4
        spacing = 2
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
    def inputs(self):
        return list(self._input_items.keys())

    @property
    def outputs(self):
        return list(self._output_items.keys())

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        margin = 1.0
        rect = self.boundingRect().adjusted(margin, margin, -margin, -margin)
        radius = 2.6
        c = self.color
        painter.setBrush(QtGui.QColor(c[0], c[1], c[2], 50))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)
        top_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width(), 26.0)
        painter.setBrush(QtGui.QColor(*self.color))
        painter.drawRoundedRect(top_rect, radius, radius)
        for pos in [top_rect.left(), top_rect.right() - 5.0]:
            painter.drawRect(QtCore.QRectF(pos, top_rect.bottom() - 5.0, 5.0, 5.0))
        if self.backdrop_text:
            painter.setPen(QtGui.QColor(*self.text_color))
            txt_rect = QtCore.QRectF(top_rect.x() + 5.0, top_rect.bottom() + 3.0,
                                     rect.width() - 10.0, rect.height() - 30.0)
            painter.drawText(txt_rect, QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap, self.backdrop_text)
        border_color = self.color
        border_width = 0.8
        if self.selected:
            sel_color = list(NodeEnum.SELECTED_COLOR.value)
            sel_color[-1] = 15
            painter.setBrush(QtGui.QColor(*sel_color))
            painter.drawRoundedRect(rect, radius, radius)
            border_color = NodeEnum.SELECTED_BORDER_COLOR.value
            border_width = 1.2
        painter.setBrush(QtCore.Qt.NoBrush)
        pen = QtGui.QPen(QtGui.QColor(*border_color), border_width)
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