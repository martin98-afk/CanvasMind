from collections import OrderedDict

from NodeGraphQt.constants import NodeEnum, ICON_NODE_BASE
from NodeGraphQt.qgraphics.node_base import NodeItem
from NodeGraphQt.qgraphics.node_overlay_disabled import XDisabledItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from PyQt5 import QtWidgets
from Qt import QtCore
from qtpy import QtGui


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
        self._properties['icon'] = ICON_NODE_BASE
        self._icon_item = QtWidgets.QGraphicsPixmapItem(pixmap, self)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont()
        font.setPointSize(16)  # 推荐 10~12
        font.setBold(False)  # 可选
        self._text_item.setFont(font)
        self._x_item = XDisabledItem(self, 'DISABLED')
        self._input_items = OrderedDict()
        self._output_items = OrderedDict()
        self._widgets = OrderedDict()
        self._proxy_mode = False
        self._proxy_mode_threshold = 70

    @property
    def icon(self):
        return self._properties['icon']

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
        self.align_icon(h_offset=1.5, v_offset=label_v_offset - 1.5)
        self.align_ports(v_offset=header_height)  # ⬅️ ports 下移
        self.align_widgets(v_offset=header_height + 8.0)  # ⬅️ widgets 下移

        self.update()

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
        text_w = max(self._text_item.boundingRect().width(), font_metrics.horizontalAdvance(self.name)) + 50
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
                widget_height += w_height + 10
            else:
                w_width = widget.boundingRect().width()
                w_height = widget.boundingRect().height()
                if w_width > widget_width:
                    widget_width = w_width
                widget_height += w_height + 10

        side_padding = 0.0
        if all([widget_width, p_input_text_width, p_output_text_width]):
            port_text_width = max([p_input_text_width, p_output_text_width])
            port_text_width *= 2
        elif widget_width:
            side_padding = 0

        width = port_width + max([text_w, port_text_width]) + side_padding
        height = max([text_h, p_input_height, p_output_height, widget_height])
        if widget_width:
            # add additional width for node widget.
            width += widget_width
        height *= 1.05
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