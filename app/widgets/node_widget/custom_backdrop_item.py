# -*- coding: utf-8 -*-
from collections import OrderedDict

from NodeGraphQt.constants import ITEM_CACHE_MODE, PortTypeEnum, Z_VAL_NODE, ICON_NODE_BASE, NodeEnum
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from NodeGraphQt.qgraphics.port import CustomPortItem, PortItem
from qtpy import QtCore, QtGui, QtWidgets


class ControlFlowBackdropNodeItem(BackdropNodeItem):
    def __init__(self, name='控制流区域', text='', parent=None):
        super().__init__(name=name, text=text, parent=parent)
        pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if pixmap.size().height() > NodeEnum.ICON_SIZE.value:
            pixmap = pixmap.scaledToHeight(
                28,
                QtCore.Qt.SmoothTransformation
            )
        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont()
        font.setPointSize(16)  # 推荐 10~12
        font.setBold(True)  # 可选
        self._text_item.setFont(font)
        self._text_item.setDefaultTextColor(QtGui.QColor("white"))
        self._icon_item = QtWidgets.QGraphicsPixmapItem(pixmap, self)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self.setZValue(Z_VAL_NODE)
        self._input_items = OrderedDict()
        self._output_items = OrderedDict()

    def _add_port(self, port):
        text = QtWidgets.QGraphicsTextItem("", self)
        text.setVisible(False)
        text.setCacheMode(ITEM_CACHE_MODE)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        elif port.port_type == PortTypeEnum.OUT.value:
            self._output_items[port] = text
        return port

    def add_input(self, name='input', multi_port=False, display_name=True, locked=False, painter_func=None):
        if painter_func:
            port = CustomPortItem(self, painter_func)
        else:
            port = PortItem(self)
        port.name = name
        port.port_type = PortTypeEnum.IN.value
        port.multi_connection = multi_port
        port.display_name = display_name
        port.locked = locked
        return self._add_port(port)

    def add_output(self, name='output', multi_port=False, display_name=True, locked=False, painter_func=None):
        if painter_func:
            port = CustomPortItem(self, painter_func)
        else:
            port = PortItem(self)
        port.name = name
        port.port_type = PortTypeEnum.OUT.value
        port.multi_connection = multi_port
        port.display_name = display_name
        port.locked = locked
        return self._add_port(port)

    @property
    def icon(self):
        return self._properties.get("icon")

    @icon.setter
    def icon(self, value=None):
        self._properties['icon'] = value

        # 确定最终使用的 pixmap
        if isinstance(value, QtGui.QIcon):
            # 从 QIcon 提取 QPixmap（推荐使用标准大小）
            pixmap = value.pixmap(28, 28)  # 或根据需要调整
        elif isinstance(value, str):
            # 从路径加载
            pixmap = QtGui.QPixmap(value)
        else:
            # fallback to default
            pixmap = QtGui.QPixmap(ICON_NODE_BASE)

        # 缩放逻辑保持不变
        if not pixmap.isNull():
            if pixmap.height() > 28:
                pixmap = pixmap.scaledToHeight(28, QtCore.Qt.SmoothTransformation)
            if pixmap.width() > 28:
                pixmap = pixmap.scaledToWidth(28, QtCore.Qt.SmoothTransformation)
        else:
            # 如果加载失败，使用默认图标
            pixmap = QtGui.QPixmap(ICON_NODE_BASE)
            if pixmap.height() > 28:
                pixmap = pixmap.scaledToHeight(28, QtCore.Qt.SmoothTransformation)
            if pixmap.width() > 28:
                pixmap = pixmap.scaledToWidth(28, QtCore.Qt.SmoothTransformation)

        self._icon_item.setPixmap(pixmap)
        if self.scene():
            self.post_init()

        self.update()

    @property
    def inputs(self):
        return list(self._input_items.keys())

    @property
    def outputs(self):
        return list(self._output_items.keys())

    def align_ports(self, v_offset=0.0):
        width = self._width
        txt_offset = 4
        spacing = 1

        inputs = [p for p in self.inputs if p.isVisible()]
        if inputs:
            port_width = inputs[0].boundingRect().width()
            port_height = inputs[0].boundingRect().height()
            port_x = (port_width / 2) * -1
            port_y = v_offset
            for port in inputs:
                port.setPos(port_x, port_y)
                port_y += port_height + spacing
            for port, text in self._input_items.items():
                if port.isVisible():
                    txt_x = port.boundingRect().width() / 2 - txt_offset
                    text.setPos(txt_x, port.y() - 1.5)

        outputs = [p for p in self.outputs if p.isVisible()]
        if outputs:
            port_width = outputs[0].boundingRect().width()
            port_height = outputs[0].boundingRect().height()
            port_x = width - (port_width / 2)
            port_y = v_offset
            for port in outputs:
                port.setPos(port_x, port_y)
                port_y += port_height + spacing
            for port, text in self._output_items.items():
                if port.isVisible():
                    txt_width = text.boundingRect().width() - txt_offset
                    txt_x = port.x() - txt_width
                    text.setPos(txt_x, port.y() - 1.5)

    def paint(self, painter, option, widget):
        """
        Draws the backdrop rect.

        Args:
            painter (QtGui.QPainter): painter used for drawing the item.
            option (QtGui.QStyleOptionGraphicsItem):
                used to describe the parameters needed to draw.
            widget (QtWidgets.QWidget): not used.
        """
        painter.save()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtCore.Qt.NoBrush)
        margin = 1.0
        rect = self.boundingRect()
        rect = QtCore.QRectF(
            rect.left() + margin,
            rect.top() + margin,
            rect.width() - (margin * 2),
            rect.height() - (margin * 2),
        )

        radius = 2.6
        color = (self.color[0], self.color[1], self.color[2], 50)
        painter.setBrush(QtGui.QColor(*color))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        top_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width(), 26.0)
        painter.setBrush(QtGui.QBrush(QtGui.QColor(*self.color)))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(top_rect, radius, radius)
        for pos in [top_rect.left(), top_rect.right() - 5.0]:
            painter.drawRect(
                QtCore.QRectF(pos, top_rect.bottom() - 5.0, 5.0, 5.0))

        if self.backdrop_text:
            painter.setPen(QtGui.QColor(*self.text_color))
            txt_rect = QtCore.QRectF(
                top_rect.x() + 5.0, top_rect.height() + 3.0,
                rect.width() - 5.0, rect.height())
            painter.setPen(QtGui.QColor(*self.text_color))
            painter.drawText(txt_rect,
                             QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap,
                             self.backdrop_text)

        if self.selected:
            sel_color = [x for x in NodeEnum.SELECTED_COLOR.value]
            sel_color[-1] = 15
            painter.setBrush(QtGui.QColor(*sel_color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(QtGui.QColor(*self.text_color))
        self._align_label()

        # 绘制边框
        border = 0.8
        border_color = self.color
        if self.selected and NodeEnum.SELECTED_BORDER_COLOR.value:
            border = 1.0
            border_color = NodeEnum.SELECTED_BORDER_COLOR.value

        painter.setBrush(QtCore.Qt.NoBrush)
        pen = QtGui.QPen(QtGui.QColor(*border_color), border)
        pen.setCosmetic(True)  # 确保线条在缩放时保持一致
        painter.setPen(pen)
        painter.drawRoundedRect(rect, radius, radius)

        painter.restore()

    def mouseDoubleClickEvent(self, event):
        """
        Re-implemented to emit "node_double_clicked" signal.

        Args:
            event (QtWidgets.QGraphicsSceneMouseEvent): mouse event.
        """
        if event.button() == QtCore.Qt.LeftButton:
            if not self.disabled:
                # enable text item edit mode.
                items = self.scene().items(event.scenePos())
                if self._text_item in items:
                    self._text_item.set_editable(True)
                    self._text_item.setFocus()
                    event.ignore()
                    return

            viewer = self.viewer()
            if viewer:
                viewer.node_double_clicked.emit(self.id)

        super(BackdropNodeItem, self).mouseDoubleClickEvent(event)

    def draw_node(self):
        QtCore.QTimer.singleShot(0, self._align_ports_later)
        QtCore.QTimer.singleShot(0, self._align_icon_horizontal)

    def _align_label(self):
        rect = self.boundingRect()
        text_rect = self._text_item.boundingRect()
        x = rect.center().x() - (text_rect.width() / 2)
        self._text_item.setPos(x, rect.y())

    def _align_ports_later(self):
        title_height = 26.0
        self.align_ports(v_offset=title_height + 5)

    def _align_icon_horizontal(self):
        x = self.boundingRect().left() + 10.0
        y = 0
        self._icon_item.setPos(x, y)

    @AbstractNodeItem.width.setter
    def width(self, width=0.0):
        AbstractNodeItem.width.fset(self, width)
        self._sizer.set_pos(self._width, self._height)
        self.draw_node()

    @AbstractNodeItem.height.setter
    def height(self, height=0.0):
        AbstractNodeItem.height.fset(self, height)
        self._sizer.set_pos(self._width, self._height)
        self.draw_node()

    @AbstractNodeItem.name.setter
    def name(self, name=''):
        AbstractNodeItem.name.fset(self, name)
        if name == self._text_item.toPlainText():
            return
        self._text_item.setPlainText(name)
        if self.scene():
            self._align_label()
        self.update()