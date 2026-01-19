# -*- coding: utf-8 -*-
from NodeGraphQt.constants import (
    NodeEnum, PortTypeEnum,
    Z_VAL_NODE_WIDGET
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_base import NodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from PyQt5 import QtWidgets, QtCore, QtGui

from app.utils.config import Settings

# ==============================================================================
# 高级感配色常量 (ComfyUI Style)
# ==============================================================================
COLOR_BG_GRAD_TOP = (40, 40, 45, 255)
COLOR_BG_GRAD_BOTTOM = (25, 25, 30, 255)
COLOR_SELECTED_GLOW = (255, 180, 0, 255)
COLOR_BORDER_NORMAL = (60, 60, 65, 255)


class CustomNodeSignals(QtCore.QObject):
    rename_triggered = QtCore.pyqtSignal(str, str)
    run_triggered = QtCore.pyqtSignal()
    node_delete_triggered = QtCore.pyqtSignal()
    node_debug_triggered = QtCore.pyqtSignal()
    node_center_triggered = QtCore.pyqtSignal()
    collapsed_toggle = QtCore.pyqtSignal(bool)
    exec_mode_toggle = QtCore.pyqtSignal(str)
    size_changed = QtCore.pyqtSignal(float, float)


class NodeResizeHandle(QtWidgets.QGraphicsItem):
    """
    节点右下角的缩放手柄
    """

    def __init__(self, parent=None):
        super(NodeResizeHandle, self).__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + 20)
        self.setCursor(QtCore.Qt.SizeFDiagCursor)
        self.setAcceptHoverEvents(True)
        self._hovered = False
        self._prev_pos = None
        self._icon_path = QtGui.QPainterPath()
        self._icon_path.moveTo(12, 0)
        self._icon_path.lineTo(0, 12)
        self._icon_path.moveTo(7, 0)
        self._icon_path.lineTo(0, 7)

    def boundingRect(self):
        return QtCore.QRectF(0, 0, 15, 15)

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        color = QtGui.QColor(255, 255, 255, 200 if self._hovered else 80)
        pen = QtGui.QPen(color, 2.0)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPath(self._icon_path)
        painter.restore()

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super(NodeResizeHandle, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super(NodeResizeHandle, self).hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._prev_pos = event.scenePos()
            event.accept()
        else:
            super(NodeResizeHandle, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton:
            pos = event.scenePos()
            if self._prev_pos is None:
                self._prev_pos = pos
                return
            delta = pos - self._prev_pos
            self._prev_pos = pos
            node = self.parentItem()
            if hasattr(node, 'resize_node_by_user'):
                node.resize_node_by_user(delta.x(), delta.y())
            event.accept()
        else:
            super(NodeResizeHandle, self).mouseMoveEvent(event)


class CustomDisabledItem(QtWidgets.QGraphicsItem):
    def __init__(self, parent=None, text=None):
        super(CustomDisabledItem, self).__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + 2)
        self.setVisible(False)
        self.proxy_mode = False
        self.color = (0, 0, 0, 255)
        self.text = text

    def _get_body_rect(self):
        if hasattr(self.parentItem(), 'get_node_body_rect'):
            return self.parentItem().get_node_body_rect()
        return self.parentItem().boundingRect()

    def boundingRect(self):
        rect = self._get_body_rect()
        margin = 10
        return rect.adjusted(-margin, -margin, margin, margin)

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self._get_body_rect()
        bg_color = QtGui.QColor(*self.color)
        bg_color.setAlpha(120)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, 20, 20)
        pen_w = 4.0 if not self.proxy_mode else 8.0
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 50, 50, 200), pen_w))
        painter.drawLine(rect.topLeft(), rect.bottomRight())
        painter.drawLine(rect.topRight(), rect.bottomLeft())
        if self.text and not self.proxy_mode:
            painter.setPen(QtGui.QColor(255, 255, 255))
            font = painter.font()
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, QtCore.Qt.AlignCenter, self.text)
        painter.restore()


class NodeActionButton(QtWidgets.QGraphicsItem):
    def __init__(self, parent, icon_type, tooltip, color, hover_color, is_permanent=False):
        super(NodeActionButton, self).__init__(parent)
        self.setAcceptHoverEvents(True)
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
        else:
            event.ignore()


class CustomNodeItem(NodeItem):
    current_mode = "subprocess"
    ICON_NODE_BASE = ":/icons/同心圆.svg"

    def __init__(self, name='', parent=None):
        super(CustomNodeItem, self).__init__(name, parent)
        self.setAcceptHoverEvents(True)
        self._is_collapsed = False
        self.custom_signals = CustomNodeSignals()
        self.center_signal = self.custom_signals.node_center_triggered
        self.rename_signal = self.custom_signals.rename_triggered
        self.run_signal = self.custom_signals.run_triggered
        self.delete_signal = self.custom_signals.node_delete_triggered
        self.debug_signal = self.custom_signals.node_debug_triggered
        self.collapsed_toggle = self.custom_signals.collapsed_toggle
        self.exec_mode_signal = self.custom_signals.exec_mode_toggle
        self.size_changed = self.custom_signals.size_changed

        if hasattr(self, '_x_item'): self._x_item.setParentItem(None)
        self._x_item = CustomDisabledItem(self, "DISABLED")
        self._x_item.setZValue(Z_VAL_NODE_WIDGET + 20)

        # -------------------
        # 初始化尺寸变量
        # -------------------
        self._user_width = 0.0
        self._user_height = 0.0
        self._size_initialized = False  # 标记是否已经从 Model 同步过尺寸

        self._init_base_components()
        self._init_custom_buttons()

        self._resize_handle = NodeResizeHandle(self)
        self._resize_handle.setVisible(True)

        self._port_height = 0.0
        self._widget_height = 0.0

    def _init_base_components(self):
        pixmap = QtGui.QPixmap(self.ICON_NODE_BASE)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(35, 35, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self._icon_item.setPixmap(pixmap)
        self._properties['icon'] = self.ICON_NODE_BASE
        self._icon_item.setZValue(self.zValue() + 1)
        font_type = Settings().get_instance().canvas_font_type.value
        self._text_item = NodeTextItem(self.name, self)
        self._text_item.setFont(QtGui.QFont(font_type, 14, QtGui.QFont.DemiBold))

        self._proxy_text_item = QtWidgets.QGraphicsTextItem(self.name, self)
        self._proxy_text_item.setFont(QtGui.QFont(font_type, 36, QtGui.QFont.Bold))
        self._proxy_text_item.setVisible(False)

    def _init_custom_buttons(self):
        self._center_btn = NodeActionButton(self, "zoom", "聚焦", "#3498db", "#2980b9", False)
        self._center_btn.clicked_func = self.center_signal.emit
        self._collapse_btn = NodeActionButton(self, "collapse", "折叠控件", "transparent", "rgba(255,255,255,40)", True)
        self._collapse_btn.clicked_func = self.toggle_collapse
        self._run_btn = NodeActionButton(self, "run", "执行", "#27ae60", "#2ecc71", False)
        self._run_btn.clicked_func = self.run_signal.emit
        self._mute_btn = NodeActionButton(self, "debug", "调试", "#f39c12", "#f1c40f", False)
        self._mute_btn.clicked_func = self.debug_signal.emit
        self._close_btn = NodeActionButton(self, "close", "删除", "#c0392b", "#e74c3c", False)
        self._close_btn.clicked_func = self.delete_signal.emit
        self._exec_mode_btn = NodeActionButton(self, "exec_subprocess", "执行模式", "#9b59b6", "#8e44ad", True)
        self._exec_mode_btn.clicked_func = self._toggle_exec_mode
        self._exec_mode_btn.setVisible(True)
        self._set_action_btns_visible(False)

    def _toggle_exec_mode(self, mode=None):
        if mode:
            self.current_mode = mode
        else:
            self.current_mode = "ipython" if self.current_mode == "subprocess" else "subprocess"
        if self.current_mode == "subprocess":
            self._exec_mode_btn.icon_type = "exec_subprocess"
            self._exec_mode_btn.color = QtGui.QColor("#9b59b6")
            self._exec_mode_btn.hover_color = QtGui.QColor("#8e44ad")
        else:
            self._exec_mode_btn.icon_type = "exec_ipython"
            self._exec_mode_btn.color = QtGui.QColor("#3498db")
            self._exec_mode_btn.hover_color = QtGui.QColor("#2980b9")
        if mode is None: self.exec_mode_signal.emit(self.current_mode)
        self.update()

    def get_node_body_rect(self):
        rect = super(CustomNodeItem, self).boundingRect()
        return rect if rect.width() > 0 else QtCore.QRectF(0, 0, 200, 50)

    def boundingRect(self):
        return self.get_node_body_rect().adjusted(-5, -40, 5, 5)

    def shape(self):
        path = QtGui.QPainterPath()
        path.addRoundedRect(self.get_node_body_rect(), 12, 12)
        path.addEllipse(self._collapse_btn.boundingRect().translated(self._collapse_btn.pos()))
        path.addEllipse(self._exec_mode_btn.boundingRect().translated(self._exec_mode_btn.pos()))
        if self._close_btn.isVisible():
            for btn in [self._center_btn, self._run_btn, self._mute_btn, self._close_btn]:
                path.addEllipse(btn.boundingRect().translated(btn.pos()))
        return path

    def _set_action_btns_visible(self, visible):
        self.prepareGeometryChange()
        self._center_btn.setVisible(visible)
        self._run_btn.setVisible(visible)
        self._mute_btn.setVisible(visible)
        self._close_btn.setVisible(visible)

    def _update_elements_visibility(self):
        widgets_visible = not self._is_collapsed and not self._proxy_mode
        for w in self._widgets.values():
            w.widget().setVisible(widgets_visible)
        ports_visible = not self._proxy_mode
        for text in list(self._input_items.values()) + list(self._output_items.values()):
            text.setVisible(ports_visible)
        self._text_item.setVisible(not self._proxy_mode)
        self._icon_item.setVisible(not self._proxy_mode)
        self._collapse_btn.setVisible(not self._proxy_mode)
        self._exec_mode_btn.setVisible(not self._proxy_mode)
        self._proxy_text_item.setVisible(self._proxy_mode)
        self._resize_handle.setVisible(widgets_visible)

    def toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self.collapsed_toggle.emit(self._is_collapsed)
        self._collapse_btn.icon_type = "expand" if self._is_collapsed else "collapse"
        self._update_elements_visibility()
        self._draw_node_horizontal()
        self.update()

    def update_layout(self):
        self._draw_node_horizontal()
        self.update()

    # -----------------------------------------------------------
    # 尺寸同步：在 paint 首次调用时同步 Model 里的 width/height
    # -----------------------------------------------------------
    def _sync_size_from_model(self):
        if self._size_initialized: return
        # 尝试获取关联的 Node 对象
        # NodeItem.node 属性会返回 self._node (但它是 protected)
        # 这里为了稳妥，直接访问 NodeItem.__init__ 里可能没被赋初始值的 _node
        # 但通常 paint 调用时 _node 已经存在
        if hasattr(self, '_node') and self._node:
            w = self._node.get_property('width')
            h = self._node.get_property('height')
            if w is not None and h is not None:
                # 只有大于0的值才有效
                if float(w) > 0 and float(h) > 0:
                    self._user_width = float(w)
                    self._user_height = float(h)
                    self._size_initialized = True
                    # 重新计算一次布局
                    self._draw_node_horizontal()

    def resize_node_by_user(self, dx, dy):
        calc_w, calc_h = self._calc_size_horizontal(ignore_user_size=True)
        if self._user_width == 0: self._user_width = calc_w
        if self._user_height == 0: self._user_height = calc_h

        self._user_width += dx
        self._user_height += dy

        if self._user_width < calc_w: self._user_width = calc_w
        if self._user_height < calc_h: self._user_height = calc_h

        # 保存到 _properties，确保 JSON 序列化时包含
        self._properties['width'] = self._user_width
        self._properties['height'] = self._user_height

        # 同时尝试更新 NodeObject 的 model（如果 NodeObject 已经连接）
        if hasattr(self, '_node') and self._node:
            # 注意：这里我们只更新 model，不触发 set_property 信号以免循环
            self._node.model.set_property('width', self._user_width)
            self._node.model.set_property('height', self._user_height)

        self.size_changed.emit(self._user_width, self._user_height)
        self._draw_node_horizontal()
        self.update()

    def hoverEnterEvent(self, event):
        self._set_action_btns_visible(True)
        super(CustomNodeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.boundingRect().contains(event.pos()):
            self._set_action_btns_visible(False)
        super(CustomNodeItem, self).hoverLeaveEvent(event)

    def _calc_size_horizontal(self, ignore_user_size=False):
        p_input_h = 0.0
        p_output_h = 0.0
        if self._input_items:
            p_input_h = (len(self._input_items) * 22.0) + 10.0
        if self._output_items:
            p_output_h = (len(self._output_items) * 22.0) + 10.0
        port_height = max(p_input_h, p_output_h)

        in_txt_w = 0.0
        out_txt_w = 0.0
        for text in self._input_items.values():
            in_txt_w = max(in_txt_w, text.boundingRect().width())
        for text in self._output_items.values():
            out_txt_w = max(out_txt_w, text.boundingRect().width())
        p_width = in_txt_w + out_txt_w + 50.0

        widget_height = 0.0
        w_width = 0.0

        if not self._is_collapsed:
            for widget in self._widgets.values():
                real = widget.widget()
                if real:
                    sz = real.sizeHint()
                    w_width = max(w_width, sz.width())
                    widget_height += sz.height() + 8.0
                else:
                    sz = widget.boundingRect().size()
                    w_width = max(w_width, sz.width())
                    widget_height += sz.height() + 8.0
            if widget_height > 0:
                widget_height += 10.0
        else:
            widget_height = 0.0
            w_width = 0.0

        self._port_height = port_height
        self._widget_height = widget_height

        min_width = max(
            self._text_item.boundingRect().width() + 120,
            p_width,
            w_width + 20,
            200
        )

        header_height = max(self._text_item.boundingRect().height() + 10.0, 34.0)
        final_port_height = max(port_height, 10.0) if not self._is_collapsed else port_height
        if self._is_collapsed and final_port_height == 0:
            final_port_height = 5.0

        min_height = header_height + final_port_height + widget_height

        if ignore_user_size:
            return min_width, min_height

        final_width = max(min_width, self._user_width)
        final_height = max(min_height, self._user_height)
        return final_width, final_height

    def _draw_node_horizontal(self):
        self.prepareGeometryChange()

        header_h = max(self._text_item.boundingRect().height() + 10.0, 34.0)
        width, height = self._calc_size_horizontal()
        self._width = width
        self._height = height

        self.align_ports(v_offset=header_h)

        rect = self.get_node_body_rect()

        if not self._is_collapsed and not self._proxy_mode:
            self._resize_handle.setPos(rect.width() - 15, rect.height() - 15)
            self._resize_handle.setVisible(True)
        else:
            self._resize_handle.setVisible(False)

        if not self._proxy_mode:
            self._set_text_color(self.text_color)
            tw = self._text_item.boundingRect().width()
            th = self._text_item.boundingRect().height()

            icon_w = 20
            spacing = 4
            total_content_w = icon_w + spacing + tw
            start_x = rect.center().x() - total_content_w / 2

            self._icon_item.setPos(start_x, rect.top() + (header_h - 18) / 2)
            self._text_item.setPos(start_x + icon_w + spacing, rect.top() + (header_h - th) / 2)

            self._collapse_btn.setPos(rect.left() + 6, rect.top() + (header_h - 28) / 2)
            self._exec_mode_btn.setPos(rect.right() - 34, rect.top() + (header_h - 28) / 2)

            if not self._is_collapsed:
                widget_start_y = rect.top() + header_h + self._port_height + 5.0
                self._align_widgets_stacked(widget_start_y, rect.width(), rect.height())
        else:
            self._update_proxy_text_position()

        btn_y = rect.top() - 32
        spacing = 32
        self._close_btn.setPos(rect.right() - 28, btn_y)
        self._mute_btn.setPos(rect.right() - 28 - spacing, btn_y)
        self._run_btn.setPos(rect.right() - 28 - spacing * 2, btn_y)
        self._center_btn.setPos(rect.right() - 28 - spacing * 3, btn_y)

    def _align_widgets_stacked(self, start_y, node_width, node_height):
        if not self._widgets: return

        padding_x = 10.0
        spacing_y = 8.0
        bottom_padding = 10.0

        # 计算可用空间
        available_height_total = node_height - start_y - bottom_padding

        total_fixed_height = 0
        expandable_widgets = []

        # 第一次遍历：找出哪些控件需要拉伸 (Expanding)
        for widget in self._widgets.values():
            if not widget.isVisible(): continue
            real = widget.widget()  # ProxyWidget 内部的 _NodeGroupBox
            # 简化逻辑：如果是 QWidget，检查 Policy
            if real:
                h = real.sizeHint().height()

                # 获取实际包含的子控件 (你的 _NodeGroupBox.get_node_widget)
                actual_widget = None
                if hasattr(real, 'get_node_widget'):
                    actual_widget = real.get_node_widget()

                is_expanding = False
                if actual_widget:
                    policy = actual_widget.sizePolicy().verticalPolicy()
                    is_expanding = (policy == QtWidgets.QSizePolicy.Expanding or
                                    policy == QtWidgets.QSizePolicy.MinimumExpanding)

                if is_expanding:
                    expandable_widgets.append((widget, real))

                total_fixed_height += h + spacing_y
            else:
                h = widget.boundingRect().height()
                total_fixed_height += h + spacing_y

        # 计算分配给每个拉伸控件的额外高度
        extra_space = max(0, available_height_total - total_fixed_height)
        extra_per_widget = 0
        if expandable_widgets:
            extra_per_widget = extra_space / len(expandable_widgets)

        # 第二次遍历：应用位置和尺寸
        current_y = start_y
        for widget in self._widgets.values():
            if not widget.isVisible(): continue
            proxy_widget = widget
            real_widget = widget.widget()

            h = 0
            if real_widget:
                h = real_widget.sizeHint().height()

                # 重新判断是否 Expanding 以决定是否加高度
                actual_widget = None
                if hasattr(real_widget, 'get_node_widget'):
                    actual_widget = real_widget.get_node_widget()

                is_expanding = False
                if actual_widget:
                    policy = actual_widget.sizePolicy().verticalPolicy()
                    is_expanding = (policy == QtWidgets.QSizePolicy.Expanding or
                                    policy == QtWidgets.QSizePolicy.MinimumExpanding)

                if is_expanding:
                    h += extra_per_widget
            else:
                h = proxy_widget.boundingRect().height()

            proxy_widget.setPos(self.boundingRect().x() + 5 + padding_x, current_y)
            target_width = node_width - (padding_x * 2)

            if real_widget:
                real_widget.setFixedSize(int(target_width), int(h))
                real_widget.resize(int(target_width), int(h))

            current_y += h + spacing_y

    def _paint_horizontal(self, painter, option, widget):
        # 【关键修复】在 paint 中进行一次延迟的尺寸同步
        # 因为 deserialization 过程中，Model 的属性写入可能晚于 Item 的初始化
        if not self._size_initialized:
            self._sync_size_from_model()

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.get_node_body_rect()
        radius = 12.0

        if self.selected:
            glow_color = QtGui.QColor(*COLOR_SELECTED_GLOW)
            glow_color.setAlpha(50)
            for i in range(1, 4):
                painter.setPen(QtGui.QPen(glow_color, i * 2))
                painter.drawRoundedRect(rect.adjusted(-i, -i, i, i), radius + i, radius + i)

        bg_gradient = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
        bg_gradient.setColorAt(0, QtGui.QColor(*COLOR_BG_GRAD_TOP))
        bg_gradient.setColorAt(1, QtGui.QColor(*COLOR_BG_GRAD_BOTTOM))
        painter.setBrush(bg_gradient)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        header_h = max(self._text_item.boundingRect().height() + 10, 34.0)
        header_rect = QtCore.QRectF(rect.left(), rect.top(), rect.width(), header_h)
        base_color = QtGui.QColor(*self.color)
        head_grad = QtGui.QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
        head_grad.setColorAt(0, base_color.lighter(110))
        head_grad.setColorAt(1, base_color)

        painter.setBrush(head_grad)

        path = QtGui.QPainterPath()
        path.moveTo(header_rect.bottomLeft())
        path.lineTo(header_rect.left(), header_rect.top() + radius)
        path.arcTo(header_rect.left(), header_rect.top(), radius * 2, radius * 2, 180, -90)
        path.lineTo(header_rect.right() - radius, header_rect.top())
        path.arcTo(header_rect.right() - radius * 2, header_rect.top(), radius * 2, radius * 2, 90, -90)
        path.lineTo(header_rect.bottomRight())
        path.closeSubpath()
        painter.drawPath(path)

        painter.setBrush(QtCore.Qt.NoBrush)
        border_color = QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value) if self.selected else QtGui.QColor(
            *COLOR_BORDER_NORMAL)
        painter.setPen(QtGui.QPen(border_color, 2.5 if self.selected else 1.2))
        painter.drawRoundedRect(rect, radius, radius)

        painter.restore()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton: event.ignore(); return
        if event.button() == QtCore.Qt.RightButton:
            if self.scene(): self.scene().clearSelection(); self.setSelected(True); event.accept()
        super(CustomNodeItem, self).mousePressEvent(event)

    @AbstractNodeItem.name.setter
    def name(self, name=''):
        self.rename_signal.emit(self.name, name)
        AbstractNodeItem.name.fset(self, name)
        self._text_item.setPlainText(name)
        self._proxy_text_item.setPlainText(name)
        self._draw_node_horizontal()
        self.update()

    def _set_text_color(self, color=None):
        muted = QtGui.QColor(225, 225, 225)
        for text in list(self._input_items.values()) + list(self._output_items.values()):
            text.setDefaultTextColor(muted)
        self._text_item.setDefaultTextColor(QtCore.Qt.white)
        self._proxy_text_item.setDefaultTextColor(QtGui.QColor(255, 255, 255, 120))

    def auto_switch_mode(self):
        if self.viewer() is None: return
        rect = self.sceneBoundingRect()
        l = self.viewer().mapToGlobal(self.viewer().mapFromScene(rect.topLeft()))
        r = self.viewer().mapToGlobal(self.viewer().mapFromScene(rect.topRight()))
        self.set_proxy_mode((r.x() - l.x()) < Settings.get_instance().node_proxy_size.value)

    def set_proxy_mode(self, mode):
        if mode is self._proxy_mode: return
        self._proxy_mode = mode
        self._update_elements_visibility()
        if hasattr(self, '_x_item'): self._x_item.proxy_mode = mode
        self._draw_node_horizontal()
        self.update()

    def _update_proxy_text_position(self):
        rect = self.get_node_body_rect()
        tr = self._proxy_text_item.boundingRect()
        self._proxy_text_item.setPos(rect.center().x() - tr.width() / 2, rect.center().y() - tr.height() / 2)

    def _draw_node_vertical(self):
        self._draw_node_horizontal()

    def _paint_vertical(self, painter, option, widget):
        self._paint_horizontal(painter, option, widget)

    def _add_port(self, port):
        text = QtWidgets.QGraphicsTextItem(port.name, self)
        text.setFont(QtGui.QFont("Segoe UI", 9))
        text.setVisible(port.display_name)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        else:
            self._output_items[port] = text
        self._draw_node_horizontal()
        return port

    def remove_widget(self, widget):
        w = self._widgets.pop(widget.get_name(), None)
        if w:
            w.setParent(None)
            w.deleteLater()

            # 【关键修复】删除控件时，重置用户手动设置的高度
            # 这样节点就会自动“回缩”到剩余内容所需的最小尺寸
            self._user_height = 0

            # 同时也建议重置宽度，防止宽度过大留白，看你需求
            # self._user_width = 0

            # 更新 Model，确保持久化数据也同步重置
            if hasattr(self, '_node') and self._node:
                self._node.model.set_property('height', 0.0)

            # 强制刷新布局
            self._draw_node_horizontal()
            self.update()