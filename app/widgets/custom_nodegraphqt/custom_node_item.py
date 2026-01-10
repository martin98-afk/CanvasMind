from collections import OrderedDict

from NodeGraphQt.constants import NodeEnum, ICON_NODE_BASE, ITEM_CACHE_MODE, PortTypeEnum, LayoutDirectionEnum, \
    Z_VAL_NODE
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_base import NodeItem
from NodeGraphQt.qgraphics.node_overlay_disabled import XDisabledItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from PyQt5 import QtWidgets
from Qt import QtCore
from qtpy import QtGui

from app.utils.config import Settings


class RenameSignal(QtCore.QObject):
    rename = QtCore.Signal(str, str) # old name, new name


class CustomNodeItem(NodeItem):
    _align = None

    def __init__(self, name='node', parent=None):
        super(NodeItem, self).__init__(name, parent)
        pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if pixmap.size().height() > NodeEnum.ICON_SIZE.value:
            pixmap = pixmap.scaledToHeight(
                28,
                QtCore.Qt.SmoothTransformation
            )
        self.rename_signal = RenameSignal()
        self._properties['icon'] = ICON_NODE_BASE
        self._icon_item = QtWidgets.QGraphicsPixmapItem(pixmap, self)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont()
        font.setPointSize(16)  # 推荐 10~12
        font.setBold(True)  # 可选
        self._text_item.setFont(font)
        self._x_item = XDisabledItem(self, 'DISABLED')
        self._input_items = OrderedDict()
        self._output_items = OrderedDict()
        self._widgets = OrderedDict()
        self._proxy_mode = False
        self.setZValue(Z_VAL_NODE)
        self._proxy_text_item = QtWidgets.QGraphicsTextItem(self.name, self)
        proxy_font = QtGui.QFont()
        proxy_font.setPointSize(35)  # 大号字体，可调
        proxy_font.setBold(True)
        self._proxy_text_item.setFont(proxy_font)
        self._proxy_text_item.setVisible(False)  # 初始隐藏

    def _set_text_color(self, color=None):
        """
        set text color.

        Args:
            color (tuple): color value in (r, g, b, a).
        """
        for port, text in self._input_items.items():
            text.setDefaultTextColor(QtGui.QColor("white"))
        for port, text in self._output_items.items():
            text.setDefaultTextColor(QtGui.QColor("white"))
        self._text_item.setDefaultTextColor(QtGui.QColor("white"))
        self._proxy_text_item.setDefaultTextColor(QtGui.QColor("white"))

    @property
    def icon(self):
        return self._properties['icon']

    @AbstractNodeItem.name.setter
    def name(self, name=''):
        self.rename_signal.rename.emit(self.name, name)
        AbstractNodeItem.name.fset(self, name)
        if name == self._text_item.toPlainText():
            return
        self._text_item.setPlainText(name)
        self._proxy_text_item.setPlainText(name)
        if self.scene():
            self.align_label()
        self.update()

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

    def paint(self, painter, option, widget):
        """
        Draws the node base not the ports.

        Args:
            painter (QtGui.QPainter): painter used for drawing the item.
            option (QtGui.QStyleOptionGraphicsItem):
                used to describe the parameters needed to draw.
            widget (QtWidgets.QWidget): not used.
        """
        self.auto_switch_mode()
        if self.viewer() is None:
            return
        if self.layout_direction is LayoutDirectionEnum.HORIZONTAL.value:
            self._paint_horizontal(painter, option, widget)
        elif self.layout_direction is LayoutDirectionEnum.VERTICAL.value:
            self._paint_vertical(painter, option, widget)
        else:
            raise RuntimeError('Node graph layout direction not valid!')

    def _add_port(self, port):
        """
        Adds a port qgraphics item into the node.

        Args:
            port (PortItem): port item.

        Returns:
            PortItem: port qgraphics item.
        """
        text = QtWidgets.QGraphicsTextItem(port.name, self)
        text.setFont(QtGui.QFont("Arial", 10))
        text.setDefaultTextColor(QtGui.QColor("white"))  # 设置字体颜色
        text.setVisible(port.display_name)
        # 禁用缓存，确保始终使用高质量渲染，解决长按时字体模糊扭曲问题
        text.setCacheMode(QtWidgets.QGraphicsItem.NoCache)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        elif port.port_type == PortTypeEnum.OUT.value:
            self._output_items[port] = text
        if self.scene():
            self.post_init()
        return port

    def _paint_horizontal(self, painter, option, widget):

        painter.save()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtCore.Qt.NoBrush)

        # base background.
        margin = 1.0
        rect = self.boundingRect()
        rect = QtCore.QRectF(rect.left() + margin,
                             rect.top() + margin,
                             rect.width() - (margin * 2),
                             rect.height() - (margin * 2))

        radius = 4.0
        painter.setBrush(QtGui.QColor(*self.color))
        painter.drawRoundedRect(rect, radius, radius)

        # light overlay on background when selected.
        if self.selected:
            painter.setBrush(QtGui.QColor(*NodeEnum.SELECTED_COLOR.value))
            painter.drawRoundedRect(rect, radius, radius)

        # === 优化：节点名背景区域 ===
        MIN_HEADER_HEIGHT = 16.0  # 可根据需要调整，推荐 22~26
        header_height = max(self._text_item.boundingRect().height(), MIN_HEADER_HEIGHT)

        # 背景区域：从顶部开始，固定高度
        header_rect = QtCore.QRectF(
            rect.left() + 2.0,  # 略微内缩
            rect.top() + 1.0,
            rect.width() - 4.0,  # 两侧留空
            header_height
        )

        if self.selected:
            painter.setBrush(QtGui.QColor(*NodeEnum.SELECTED_COLOR.value))
        else:
            painter.setBrush(QtGui.QColor(0, 0, 0, 80))
        painter.drawRoundedRect(header_rect, 3.0, 3.0)

        # node border
        if self.selected:
            border_width = 1.2
            border_color = QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value)
        else:
            border_width = 0.8
            border_color = QtGui.QColor(*self.border_color)

        border_rect = QtCore.QRectF(rect.left(), rect.top(),
                                    rect.width(), rect.height())

        pen = QtGui.QPen(border_color, border_width)
        pen.setCosmetic(self.viewer().get_zoom() < 0.0)
        path = QtGui.QPainterPath()
        path.addRoundedRect(border_rect, radius, radius)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.restore()

    def _draw_node_horizontal(self):
        # === 新增：使用与 paint 一致的标题高度 ===
        MIN_HEADER_HEIGHT = 16.0
        text_height = self._text_item.boundingRect().height()
        header_height = max(text_height + 4.0, MIN_HEADER_HEIGHT)

        if not self._proxy_mode:
            label_v_offset = (header_height - text_height) / 2.0
            # update port text visibility
            for port, text in self._input_items.items():
                if port.isVisible():
                    text.setVisible(port.display_name)
            for port, text in self._output_items.items():
                if port.isVisible():
                    text.setVisible(port.display_name)

            # setup base size —— 确保总高度至少包含标题
            self._set_base_size(add_h=header_height)

            # set colors and tooltip
            self._set_text_color(self.text_color)
            self._tooltip_disable(self.disabled)

            # --- align all items with new header offset ---
            self.align_label(v_offset=label_v_offset)
            self.align_icon(h_offset=6, v_offset=label_v_offset - 1.5)

            self.align_widgets(v_offset=header_height + 8.0)  # ⬅️ widgets 下移

        self.align_ports(v_offset=header_height)  # ⬅️ ports 下移
        self.update()
        if self._proxy_mode:
            self._update_proxy_text_position()

    def remove_widget(self, widget):
        widget = self._widgets.pop(widget.get_name(), None)
        widget.setParent(None)
        widget.deleteLater()

    def set_align(self, align):
        self._align = align

    def mousePressEvent(self, event):
        # 如果是右键，先选中自己（关键！）
        if event.button() == QtCore.Qt.RightButton:
            # 清除其他选择，只选中当前节点
            scene = self.scene()
            if scene:
                scene.clearSelection()
                event.accept()
                self.setSelected(True)
        # 其他逻辑交给父类（包括左键、菜单弹出等）
        super().mousePressEvent(event)

    def _calc_size_horizontal(self):
        # width, height from node name text.
        font = self._text_item.font()
        font_metrics = QtGui.QFontMetrics(font)
        text_w = max(self._text_item.boundingRect().width(), font_metrics.horizontalAdvance(self.name))
        text_h = self._text_item.boundingRect().height()

        # width, height from node ports.
        port_width = 0.0
        p_input_text_width = 0.0
        p_output_text_width = 0.0
        p_input_height = 0.0
        p_output_height = 0.0
        for port, text in self._input_items.items():
            if not port.isVisible():
                continue
            if not port_width:
                port_width = port.boundingRect().width()
            t_width = text.boundingRect().width()
            if text.isVisible() and t_width > p_input_text_width:
                p_input_text_width = text.boundingRect().width()
            p_input_height += port.boundingRect().height()
        for port, text in self._output_items.items():
            if not port.isVisible():
                continue
            if not port_width:
                port_width = port.boundingRect().width()
            t_width = text.boundingRect().width()
            if text.isVisible() and t_width > p_output_text_width:
                p_output_text_width = text.boundingRect().width()
            p_output_height += port.boundingRect().height()

        port_text_width = p_input_text_width + p_output_text_width

        # width, height from node embedded widgets.
        widget_width = 0.0
        widget_height = 0.0
        for widget in self._widgets.values():
            if not widget.isVisible():
                continue
            # ✅ 关键：直接调用 widget.widget().sizeHint()
            real_widget = widget.widget()
            if real_widget is not None:
                w_size = real_widget.sizeHint()
                w_width = w_size.width()
                w_height = w_size.height()
                if w_width > widget_width:
                    widget_width = w_width
                widget_height += w_height + 8
            else:
                w_width = widget.boundingRect().width()
                w_height = widget.boundingRect().height()
                if w_width > widget_width:
                    widget_width = w_width
                widget_height += w_height + 8

        side_padding = 0.0
        if all([widget_width, p_input_text_width, p_output_text_width]):
            port_text_width = max([p_input_text_width, p_output_text_width])
            port_text_width *= 2
        if widget_width:
            side_padding = 20
        # 节点宽度计算, 端口宽+端口文本宽+max（节点文本宽,自定义控件宽）+边距，最后与代理文本宽度取最大
        width = max(
            port_width + max(port_text_width, 40) + max([text_w, widget_width]) + side_padding,
            self._proxy_text_item.boundingRect().width() + 20
        )
        height = max([text_h, p_input_height, p_output_height, widget_height])
        height *= 1.04
        width *= 0.92
        return width, height

    def _align_widgets_horizontal(self, v_offset):
        if not self._widgets:
            return
        rect = self.boundingRect()
        y = rect.y() + v_offset
        inputs = [p for p in self.inputs if p.isVisible()]
        outputs = [p for p in self.outputs if p.isVisible()]
        for widget in self._widgets.values():
            if not widget.isVisible():
                continue
            # ✅ 关键：使用 widget.widget().sizeHint() 获取真实尺寸
            real_widget = widget.widget()
            if real_widget is not None:
                w_size = real_widget.sizeHint()
                widget_width = w_size.width()
                widget_height = w_size.height()
            else:
                # fallback（理论上不会走到这里）
                br = widget.boundingRect()
                widget_width = br.width()
                widget_height = br.height()

            if self._align == 'left':
                x = rect.left() + 10
                widget.widget().setTitleAlign('left')
            elif self._align == 'right':
                x = rect.right() - widget_width - 10
                widget.widget().setTitleAlign('right')
            elif self._align == 'center':
                x = rect.center().x() - (widget_width / 2)
                widget.widget().setTitleAlign('center')
            else:
                if not inputs:
                    x = rect.left() + 10
                    widget.widget().setTitleAlign('left')
                elif not outputs:
                    x = rect.right() - widget_width - 10
                    widget.widget().setTitleAlign('right')
                else:
                    x = rect.center().x() - (widget_width / 2)
                    widget.widget().setTitleAlign('center')

            widget.setPos(x, y)
            y += widget_height + 8  # 使用真实高度

    def auto_switch_mode(self):
        """
        Decide whether to draw the node with proxy mode.
        (this is called at the start in the "self.paint()" function.)
        """
        if ITEM_CACHE_MODE is QtWidgets.QGraphicsItem.ItemCoordinateCache:
            return
        if self.viewer() is None:
            return
        rect = self.sceneBoundingRect()
        l = self.viewer().mapToGlobal(
            self.viewer().mapFromScene(rect.topLeft()))
        r = self.viewer().mapToGlobal(
            self.viewer().mapFromScene(rect.topRight()))
        # width is the node width in screen
        width = r.x() - l.x()

        self.set_proxy_mode(width < Settings.get_instance().node_proxy_size.value)

    def _update_proxy_text_position(self):
        if not self._proxy_mode:
            return
        rect = self.boundingRect()
        text_rect = self._proxy_text_item.boundingRect()
        x = rect.center().x() - text_rect.width() / 2
        y = rect.center().y() - text_rect.height() / 2
        self._proxy_text_item.setPos(x, y)

    def set_proxy_mode(self, mode):
        """
        Set whether to draw the node with proxy mode.
        (proxy mode toggles visibility for some qgraphic items in the node.)

        Args:
            mode (bool): true to enable proxy mode.
        """
        if mode is self._proxy_mode:
            return
        self._proxy_mode = mode

        visible = not mode  # 正常模式下可见

        # disable overlay item.
        self._x_item.proxy_mode = self._proxy_mode

        # node widget visibility.
        for w in self._widgets.values():
            w.widget().setVisible(visible)

        # port text is not visible in vertical layout.
        if self.layout_direction is LayoutDirectionEnum.VERTICAL.value:
            port_text_visible = False
        else:
            port_text_visible = visible

        # input port text visibility.
        for port, text in self._input_items.items():
            if port.display_name:
                text.setVisible(port_text_visible)

        # output port text visibility.
        for port, text in self._output_items.items():
            if port.display_name:
                text.setVisible(port_text_visible)

        self._text_item.setVisible(visible)
        self._icon_item.setVisible(visible)
        # proxy 大标题（仅 proxy 模式显示）
        self._proxy_text_item.setVisible(mode)

        # 更新 proxy 文字内容（防止 name 改变）
        if mode:
            self._proxy_text_item.setPlainText(self.name)
            self._update_proxy_text_position()
