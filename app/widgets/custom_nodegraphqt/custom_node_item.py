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
COLOR_SELECTED_GLOW = (255, 180, 0, 255)  # 选中时的金橙色光晕
COLOR_BORDER_NORMAL = (60, 60, 65, 255)


class CustomNodeSignals(QtCore.QObject):
    rename_triggered = QtCore.pyqtSignal(str, str)
    run_triggered = QtCore.pyqtSignal()
    node_delete_triggered = QtCore.pyqtSignal()
    node_debug_triggered = QtCore.pyqtSignal()
    node_center_triggered = QtCore.pyqtSignal()
    collapsed_toggle = QtCore.pyqtSignal(bool)
    exec_mode_toggle = QtCore.pyqtSignal(str)


class CustomDisabledItem(QtWidgets.QGraphicsItem):
    """
    定制禁用遮罩。
    """

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
            font.setPointSize(12);
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, QtCore.Qt.AlignCenter, self.text)
        painter.restore()


class NodeActionButton(QtWidgets.QGraphicsItem):
    """
    矢量操作按钮 - 优化交互：平时透明，悬浮显色
    """

    def __init__(self, parent, icon_type, tooltip, color, hover_color, is_permanent=False):
        super(NodeActionButton, self).__init__(parent)
        self.setAcceptHoverEvents(True)
        self.setZValue(Z_VAL_NODE_WIDGET + 10)
        self.icon_type = icon_type
        self.setToolTip(tooltip)
        self.color = QtGui.QColor(color)
        self.hover_color = QtGui.QColor(hover_color)
        self.is_permanent = is_permanent  # 是否是常驻显示颜色的按钮（如模式切换）
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

        # 核心逻辑：如果是悬浮按钮且未悬浮，背景设为透明/极淡；常驻按钮或悬浮时显色
        if self._hovered:
            painter.setBrush(self.hover_color)
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1.5))
        elif self.is_permanent:
            painter.setBrush(self.color)
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 0.5))
        else:
            # 幽灵模式：平时只有淡淡的轮廓和图标
            painter.setBrush(QtGui.QColor(255, 255, 255, 15))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 30), 1.0))

        painter.drawRoundedRect(self._rect, 8, 8)

        # 绘制图标
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
            path.moveTo(cx + 2, cy - 7);
            path.lineTo(cx - 4, cy + 1);
            path.lineTo(cx + 1, cy + 1);
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
        self._hovered = True; self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False; self.update()

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

        if hasattr(self, '_x_item'): self._x_item.setParentItem(None)
        self._x_item = CustomDisabledItem(self, "DISABLED")
        self._x_item.setZValue(Z_VAL_NODE_WIDGET + 20)

        self._init_base_components()
        self._init_custom_buttons()

    def _init_base_components(self):
        pixmap = QtGui.QPixmap(self.ICON_NODE_BASE)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(28, 28, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self._icon_item.setPixmap(pixmap)
        self._properties['icon'] = self.ICON_NODE_BASE
        # 确保 Icon 层级足够
        self._icon_item.setZValue(self.zValue() + 1)

        self._text_item = NodeTextItem(self.name, self)
        self._text_item.setFont(QtGui.QFont("Segoe UI", 13, QtGui.QFont.DemiBold))

        self._proxy_text_item = QtWidgets.QGraphicsTextItem(self.name, self)
        self._proxy_text_item.setFont(QtGui.QFont("Segoe UI", 36, QtGui.QFont.Bold))
        self._proxy_text_item.setVisible(False)

    def _init_custom_buttons(self):
        # 悬浮操作组：is_permanent=False (平时不显示颜色)
        self._center_btn = NodeActionButton(self, "zoom", "聚焦", "#3498db", "#2980b9", False)
        self._center_btn.clicked_func = self.center_signal.emit

        self._collapse_btn = NodeActionButton(self, "collapse", "折叠", "transparent", "rgba(255,255,255,40)", True)
        self._collapse_btn.clicked_func = self.toggle_collapse

        self._run_btn = NodeActionButton(self, "run", "执行", "#27ae60", "#2ecc71", False)
        self._run_btn.clicked_func = self.run_signal.emit

        self._mute_btn = NodeActionButton(self, "debug", "调试", "#f39c12", "#f1c40f", False)
        self._mute_btn.clicked_func = self.debug_signal.emit

        self._close_btn = NodeActionButton(self, "close", "删除", "#c0392b", "#e74c3c", False)
        self._close_btn.clicked_func = self.delete_signal.emit

        # 模式切换按钮：is_permanent=True (常驻颜色)
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
        self._center_btn.setVisible(visible);
        self._run_btn.setVisible(visible)
        self._mute_btn.setVisible(visible);
        self._close_btn.setVisible(visible)

    def _update_elements_visibility(self):
        is_drawing = not self._is_collapsed and not self._proxy_mode
        for w in self._widgets.values(): w.widget().setVisible(is_drawing)
        for text in list(self._input_items.values()) + list(self._output_items.values()): text.setVisible(is_drawing)
        self._text_item.setVisible(not self._proxy_mode)
        self._icon_item.setVisible(not self._proxy_mode)
        self._collapse_btn.setVisible(not self._proxy_mode)
        self._exec_mode_btn.setVisible(not self._proxy_mode)
        self._proxy_text_item.setVisible(self._proxy_mode)

    def toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self.collapsed_toggle.emit(self._is_collapsed)
        self._collapse_btn.icon_type = "expand" if self._is_collapsed else "collapse"
        self._update_elements_visibility();
        self._draw_node_horizontal();
        self.update()

    def hoverEnterEvent(self, event):
        self._set_action_btns_visible(True); super(CustomNodeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.boundingRect().contains(event.pos()): self._set_action_btns_visible(False)
        super(CustomNodeItem, self).hoverLeaveEvent(event)

    def _paint_horizontal(self, painter, option, widget):
        painter.save();
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.get_node_body_rect();
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
        painter.setBrush(bg_gradient);
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        header_h = max(self._text_item.boundingRect().height() + 10, 34.0)
        header_rect = QtCore.QRectF(rect.left(), rect.top(), rect.width(), header_h)
        base_color = QtGui.QColor(*self.color)
        head_grad = QtGui.QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
        head_grad.setColorAt(0, base_color.lighter(110));
        head_grad.setColorAt(1, base_color)

        painter.setBrush(head_grad)
        if not self._is_collapsed:
            path = QtGui.QPainterPath()
            path.moveTo(header_rect.bottomLeft());
            path.lineTo(header_rect.left(), header_rect.top() + radius)
            path.arcTo(header_rect.left(), header_rect.top(), radius * 2, radius * 2, 180, -90)
            path.lineTo(header_rect.right() - radius, header_rect.top())
            path.arcTo(header_rect.right() - radius * 2, header_rect.top(), radius * 2, radius * 2, 90, -90)
            path.lineTo(header_rect.bottomRight());
            path.closeSubpath();
            painter.drawPath(path)
        else:
            painter.drawRoundedRect(header_rect, radius, radius)

        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(
            QtGui.QPen(QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value), 2.5) if self.selected else QtGui.QPen(
                QtGui.QColor(*COLOR_BORDER_NORMAL), 1.2))
        painter.drawRoundedRect(rect, radius, radius)
        painter.restore()

    def _draw_node_horizontal(self):
        self.prepareGeometryChange()
        header_h = max(self._text_item.boundingRect().height() + 10.0, 34.0)
        self._update_elements_visibility();
        self._set_base_size(add_h=header_h)
        rect = self.get_node_body_rect()

        if not self._proxy_mode:
            self._set_text_color(self.text_color)
            tw = self._text_item.boundingRect().width()
            th = self._text_item.boundingRect().height()

            # --- 修正居中逻辑：计算整体宽度并布局 ---
            icon_w = 20  # 预留 Icon 宽度
            spacing = 8
            total_content_w = icon_w + spacing + tw
            start_x = rect.center().x() - total_content_w / 2 - spacing

            # 设置 Icon 位置 (确保在文字左侧)
            self._icon_item.setPos(start_x, rect.top() + (header_h - 20) / 2)
            # 设置文字位置
            self._text_item.setPos(start_x + icon_w + spacing, rect.top() + (header_h - th) / 2)

            self._collapse_btn.setPos(rect.left() + 6, rect.top() + (header_h - 28) / 2)
            self._exec_mode_btn.setPos(rect.right() - 34, rect.top() + (header_h - 28) / 2)

            self.align_widgets(v_offset=header_h + 12.0)
        else:
            self._update_proxy_text_position()

        self.align_ports(v_offset=header_h + 2.0)
        btn_y = rect.top() - 32;
        spacing = 32
        self._close_btn.setPos(rect.right() - 28, btn_y);
        self._mute_btn.setPos(rect.right() - 28 - spacing, btn_y)
        self._run_btn.setPos(rect.right() - 28 - spacing * 2, btn_y);
        self._center_btn.setPos(rect.right() - 28 - spacing * 3, btn_y)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton: event.ignore(); return
        if event.button() == QtCore.Qt.RightButton:
            if self.scene(): self.scene().clearSelection(); self.setSelected(True); event.accept()
        super(CustomNodeItem, self).mousePressEvent(event)

    @AbstractNodeItem.name.setter
    def name(self, name=''):
        self.rename_signal.emit(self.name, name)
        AbstractNodeItem.name.fset(self, name)
        self._text_item.setPlainText(name);
        self._proxy_text_item.setPlainText(name)
        self._draw_node_horizontal();
        self.update()

    def _calc_size_horizontal(self):
        p_in_w = p_out_w = p_in_h = p_out_h = 0.0
        for port, text in self._input_items.items():
            p_in_w = max(p_in_w, text.boundingRect().width() + 30);
            p_in_h += port.boundingRect().height() + 6
        for port, text in self._output_items.items():
            p_out_w = max(p_out_w, text.boundingRect().width() + 30);
            p_out_h += port.boundingRect().height() + 6
        if self._is_collapsed: return max(self._text_item.boundingRect().width() + 160, 200), max(p_in_h, p_out_h, 40)
        w_width = w_height = 0.0
        for widget in self._widgets.values():
            real = widget.widget();
            sz = real.sizeHint() if real else widget.boundingRect().size()
            w_width = max(w_width, sz.width());
            w_height += sz.height() + 10
        width = max(self._text_item.boundingRect().width() + 160, p_in_w + p_out_w + w_width + 40, 220)
        height = max(p_in_h, p_out_h, w_height) + 25
        return width, height

    def _set_text_color(self, color=None):
        muted = QtGui.QColor(225, 225, 225)
        for text in list(self._input_items.values()) + list(self._output_items.values()): text.setDefaultTextColor(
            muted)
        self._text_item.setDefaultTextColor(QtCore.Qt.white);
        self._proxy_text_item.setDefaultTextColor(QtGui.QColor(255, 255, 255, 120))

    def auto_switch_mode(self):
        if self.viewer() is None: return
        rect = self.sceneBoundingRect()
        l = self.viewer().mapToGlobal(self.viewer().mapFromScene(rect.topLeft()))
        r = self.viewer().mapToGlobal(self.viewer().mapFromScene(rect.topRight()))
        self.set_proxy_mode((r.x() - l.x()) < Settings.get_instance().node_proxy_size.value)

    def set_proxy_mode(self, mode):
        if mode is self._proxy_mode: return
        self._proxy_mode = mode;
        self._update_elements_visibility()
        if hasattr(self, '_x_item'): self._x_item.proxy_mode = mode
        if mode: self._update_proxy_text_position()
        self.update()

    def _update_proxy_text_position(self):
        rect = self.get_node_body_rect();
        tr = self._proxy_text_item.boundingRect()
        self._proxy_text_item.setPos(rect.center().x() - tr.width() / 2, rect.center().y() - tr.height() / 2)

    def _draw_node_vertical(self):
        self._draw_node_horizontal()

    def _paint_vertical(self, painter, option, widget):
        self._paint_horizontal(painter, option, widget)

    def _add_port(self, port):
        text = QtWidgets.QGraphicsTextItem(port.name, self);
        text.setFont(QtGui.QFont("Segoe UI", 9));
        text.setVisible(port.display_name)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        else:
            self._output_items[port] = text
        self._draw_node_horizontal();
        return port

    def remove_widget(self, widget):
        w = self._widgets.pop(widget.get_name(), None)
        if w: w.setParent(None); w.deleteLater()

    def set_align(self, align):
        self._align = align

    def _align_widgets_horizontal(self, v_offset):
        if not self._widgets: return
        rect = self.get_node_body_rect();
        y = rect.top() + v_offset
        for widget in self._widgets.values():
            if not widget.isVisible(): continue
            real = widget.widget();
            size = real.sizeHint() if real else widget.boundingRect().size()
            widget.setPos(rect.center().x() - (size.width() / 2), y);
            y += size.height() + 10