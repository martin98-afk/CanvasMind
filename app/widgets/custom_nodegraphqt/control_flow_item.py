# -*- coding: utf-8 -*-
from collections import OrderedDict

from NodeGraphQt.constants import (
    ITEM_CACHE_MODE, PortTypeEnum, ICON_NODE_BASE, NodeEnum, Z_VAL_BACKDROP
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from NodeGraphQt.qgraphics.port import CustomPortItem
from PyQt5 import QtCore, QtGui, QtWidgets

try:
    from app.widgets.custom_nodegraphqt.custom_port_item import GlowPortItem
except ImportError:
    GlowPortItem = CustomPortItem


# --- 精致的折叠/展开按钮 ---
class BackdropActionButton(QtWidgets.QGraphicsItem):
    def __init__(self, parent, icon_type, tooltip):
        super(BackdropActionButton, self).__init__(parent)
        self.setAcceptHoverEvents(True)
        self.setZValue(Z_VAL_BACKDROP + 10)
        self.icon_type = icon_type
        self.setToolTip(tooltip)
        self._hovered = False
        self._rect = QtCore.QRectF(0, 0, 26, 26)
        self.clicked_func = None

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        bg_opacity = 70 if self._hovered else 30
        painter.setBrush(QtGui.QColor(255, 255, 255, bg_opacity))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 100), 1.0))
        painter.drawRoundedRect(self._rect, 6, 6)

        pen = QtGui.QPen(QtCore.Qt.white, 2.5)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        m = 8.0
        cx, cy = self._rect.center().x(), self._rect.center().y()

        painter.drawLine(QtCore.QPointF(self._rect.left() + m, cy), QtCore.QPointF(self._rect.right() - m, cy))
        if self.icon_type == 'expand':
            painter.drawLine(QtCore.QPointF(cx, self._rect.top() + m), QtCore.QPointF(cx, self._rect.bottom() - m))

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


class ControlFlowBackdropNodeItem(BackdropNodeItem):
    def __init__(self, name='控制流区域', text='', parent=None):
        self._input_items = OrderedDict()
        self._output_items = OrderedDict()
        self._is_collapsed = False
        self._pre_collapse_height = 200.0
        self._nodes_to_restore = []  # 新增：用于缓存折叠时包含的节点

        self._header_height = 42.0
        self._header_font_size = 32
        self._corner_radius = 16.0
        self._icon_size = 35

        super(ControlFlowBackdropNodeItem, self).__init__(name=name, text=text, parent=parent)

        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont("Segoe UI" if QtCore.QSysInfo.productType() == "windows" else "Arial")
        font.setPixelSize(self._header_font_size)
        font.setWeight(QtGui.QFont.Black)
        self._text_item.setFont(font)
        self._text_item.setDefaultTextColor(QtGui.QColor(255, 255, 255, 240))

        pixmap = QtGui.QPixmap(":/icons/同心圆.svg")
        if not pixmap.isNull():
            pixmap = pixmap.scaled(int(self._icon_size), int(self._icon_size),
                                   QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self._icon_item = QtWidgets.QGraphicsPixmapItem(pixmap, self)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)

        self._collapse_btn = BackdropActionButton(self, 'collapse', '折叠/展开区域')
        self._collapse_btn.clicked_func = self.toggle_collapse

        self.setZValue(Z_VAL_BACKDROP)
        self.update_layout()

    # ================= 端口管理接口 =================

    def _add_port(self, port):
        text = QtWidgets.QGraphicsTextItem(port.name, self)
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

    @property
    def inputs(self):
        return list(self._input_items.keys())

    @property
    def outputs(self):
        return list(self._output_items.keys())

    # ================= 属性控制与折叠逻辑 =================

    @property
    def visible(self):
        return self._properties.get('visible', True)

    @visible.setter
    def visible(self, visible=True):
        self._properties['visible'] = visible
        self.setVisible(visible)

    def toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self._collapse_btn.icon_type = 'expand' if self._is_collapsed else 'collapse'

        backdrop_node = self.node
        if backdrop_node:
            if self._is_collapsed:
                # 1. 折叠前：获取并缓存所有内部节点
                self._nodes_to_restore = backdrop_node.nodes()
                self._pre_collapse_height = self.height
                # 2. 设置隐藏（传入刚才获取的节点列表）
                self._set_internal_elements_visible(False)
                # 3. 改变 UI 高度
                self.height = self._header_height
            else:
                # 1. 先恢复 UI 高度
                self.height = self._pre_collapse_height
                # 2. 设置显示（使用缓存的节点列表进行恢复）
                self._set_internal_elements_visible(True)
                # 3. 清理缓存
                self._nodes_to_restore = []

        self.update_layout()
        self.update()

    def _set_internal_elements_visible(self, visible):
        """控制区域内所有节点、端口、连线的可见性"""
        try:
            # 核心修正：不再实时调用 backdrop_node.nodes()
            # 而是使用缓存的节点列表
            target_nodes = self._nodes_to_restore

            # 如果是展开且缓存为空，尝试重新获取（防御性编程）
            if visible and not target_nodes:
                if self.node: target_nodes = self.node.nodes()

            for node in target_nodes:
                # 隐藏/显示节点 View
                node.view.setVisible(visible)

                # 处理连线
                for port in node.inputs().values():
                    for pipe in port.view.connected_pipes:
                        pipe.setVisible(visible)
                for port in node.outputs().values():
                    for pipe in port.view.connected_pipes:
                        pipe.setVisible(visible)

            # 处理 Backdrop 自身的端口
            for port in self.inputs + self.outputs:
                port.setVisible(visible)
        except Exception as e:
            print(f"Backdrop Visibility Error: {e}")

    # ================= 布局与交互逻辑 =================

    def shape(self):
        path = QtGui.QPainterPath()
        path.addRect(0, 0, self._width, self._header_height)
        if not self._is_collapsed and self._sizer:
            path.addRect(self._sizer.boundingRect().translated(self._sizer.pos()))
        return path

    def update_layout(self):
        if not self._text_item or not self._icon_item: return
        rect = self.boundingRect()

        self._collapse_btn.setPos(rect.left() + 8, rect.top() + (self._header_height - 26) / 2)

        spacing = 10
        tw = self._text_item.boundingRect().width()
        iw = self._icon_item.pixmap().width() if self._icon_item.pixmap() else 0
        total_content_w = iw + spacing + tw

        start_x = rect.center().x() - (total_content_w / 2)
        start_x = max(start_x, 45)

        self._icon_item.setPos(start_x, rect.top() + (self._header_height - self._icon_item.pixmap().height()) / 2)
        self._text_item.setPos(start_x + iw + spacing,
                               rect.top() + (self._header_height - self._text_item.boundingRect().height()) / 2)

        if not self._is_collapsed:
            self.align_ports(v_offset=self._header_height + 10.0)
            if self._sizer: self._sizer.setVisible(True)
        else:
            if self._sizer: self._sizer.setVisible(False)

    def align_ports(self, v_offset=0.0):
        width = self._width
        spacing = 4
        inputs = [p for p in self.inputs if p.isVisible()]
        for i, port in enumerate(inputs):
            port_width = port.boundingRect().width()
            py = v_offset + i * (port.boundingRect().height() + spacing)
            port.setPos(-(port_width / 2), py)

        outputs = [p for p in self.outputs if p.isVisible()]
        for i, port in enumerate(outputs):
            port_width = port.boundingRect().width()
            py = v_offset + i * (port.boundingRect().height() + spacing)
            port.setPos(width - (port_width / 2), py)

    # ================= 绘图实现 =================

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        margin = 1.0
        rect = self.boundingRect().adjusted(margin, margin, -margin, -margin)
        radius = self._corner_radius

        c = self.color
        alpha = 15 if self._is_collapsed else 40
        painter.setBrush(QtGui.QColor(c[0], c[1], c[2], alpha))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        header_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width(), self._header_height)
        header_color = QtGui.QColor(*self.color)

        if self._is_collapsed:
            painter.setBrush(header_color)
            painter.drawRoundedRect(header_rect, radius, radius)
        else:
            grad = QtGui.QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
            grad.setColorAt(0, header_color.lighter(120))
            grad.setColorAt(1, header_color)
            painter.setBrush(grad)

            path = QtGui.QPainterPath()
            path.addRoundedRect(header_rect, radius, radius)
            painter.drawPath(path)
            painter.drawRect(QtCore.QRectF(header_rect.x(), header_rect.y() + self._header_height - radius,
                                           header_rect.width(), radius))

        if not self._is_collapsed and self.backdrop_text:
            painter.setPen(QtGui.QColor(*self.text_color))
            txt_rect = QtCore.QRectF(header_rect.x() + 15.0, header_rect.bottom() + 10.0,
                                     rect.width() - 30.0, rect.height() - self._header_height - 20.0)
            painter.drawText(txt_rect, QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap, self.backdrop_text)

        border_color = QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value) if self.selected else QtGui.QColor(
            *self.color)
        border_width = 2.0 if self.selected else 1.2

        painter.setBrush(QtCore.Qt.NoBrush)
        pen = QtGui.QPen(border_color, border_width)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, radius, radius)

        painter.restore()

    # ================= 原始事件兼容 =================

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

    @property
    def node(self):
        return self._node

    @node.setter
    def node(self, node):
        self._node = node

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
        if self._text_item:
            self._text_item.setPlainText(name)
            self.update_layout()

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