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


class CustomNodeSignals(QtCore.QObject):
    """
    自定义信号类，负责节点交互触发的事件分发。
    """
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
    矢量操作按钮（支持悬浮和标题栏常驻）。
    """

    def __init__(self, parent, icon_type, tooltip, color, hover_color):
        super(NodeActionButton, self).__init__(parent)
        self.setAcceptHoverEvents(True)
        self.setZValue(Z_VAL_NODE_WIDGET + 10)
        self.icon_type = icon_type
        self.setToolTip(tooltip)
        self.color = QtGui.QColor(color)
        self.hover_color = QtGui.QColor(hover_color)
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

        # 绘制背景：常驻按钮使用实色填充增强识别度
        if self._hovered:
            painter.setBrush(self.hover_color)
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1.5))
        else:
            painter.setBrush(self.color)
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 0.5))

        painter.drawRoundedRect(self._rect, 8, 8)

        # 绘制图标
        pen = QtGui.QPen(QtCore.Qt.white, 2.0)
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
            painter.setBrush(QtCore.Qt.white);
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
            o, l = 8.0, 5.0
            painter.drawLine(QtCore.QPointF(cx - o, cy - o), QtCore.QPointF(cx - o + l, cy - o))
            painter.drawLine(QtCore.QPointF(cx - o, cy - o), QtCore.QPointF(cx - o, cy - o + l))
            painter.drawLine(QtCore.QPointF(cx + o, cy - o), QtCore.QPointF(cx + o - l, cy - o))
            painter.drawLine(QtCore.QPointF(cx + o, cy - o), QtCore.QPointF(cx + o, cy - o + l))
            painter.drawLine(QtCore.QPointF(cx - o, cy + o), QtCore.QPointF(cx - o + l, cy + o))
            painter.drawLine(QtCore.QPointF(cx - o, cy + o), QtCore.QPointF(cx - o, cy + o - l))
            painter.drawLine(QtCore.QPointF(cx + o, cy + o), QtCore.QPointF(cx + o - l, cy + o))
            painter.drawLine(QtCore.QPointF(cx + o, cy + o), QtCore.QPointF(cx + o, cy + o - l))
            painter.drawPoint(QtCore.QPointF(cx, cy))
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
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1.0, QtCore.Qt.DashLine))
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
    """
    全量功能修复版自定义节点。
    """
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

        self._init_base_components()
        self._init_custom_buttons()

    def _init_base_components(self):
        pixmap = QtGui.QPixmap(self.ICON_NODE_BASE)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(24, 24, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self._icon_item.setPixmap(pixmap)
        self._text_item = NodeTextItem(self.name, self)
        self._text_item.setFont(QtGui.QFont("Inter", 14, QtGui.QFont.Bold))
        self._proxy_text_item = QtWidgets.QGraphicsTextItem(self.name, self)
        self._proxy_text_item.setFont(QtGui.QFont("Segoe UI", 36, QtGui.QFont.Bold))
        self._proxy_text_item.setVisible(False)

    def _init_custom_buttons(self):
        self._center_btn = NodeActionButton(self, "zoom", "聚焦节点", "#3498db", "#2980b9")
        self._center_btn.clicked_func = self.center_signal.emit
        self._collapse_btn = NodeActionButton(self, "collapse", "折叠/展开", "#2C2C2E", "#444446")
        self._collapse_btn.clicked_func = self.toggle_collapse
        self._run_btn = NodeActionButton(self, "run", "执行", "#27ae60", "#2ecc71")
        self._run_btn.clicked_func = self.run_signal.emit
        self._mute_btn = NodeActionButton(self, "debug", "调试", "#f39c12", "#f1c40f")
        self._mute_btn.clicked_func = self.debug_signal.emit
        self._close_btn = NodeActionButton(self, "close", "删除", "#c0392b", "#e74c3c")
        self._close_btn.clicked_func = self.delete_signal.emit

        # 运行模式按钮：常驻显示在标题栏右侧
        self._exec_mode_btn = NodeActionButton(self, "exec_subprocess", "模式切换", "#9b59b6", "#8e44ad")
        self._exec_mode_btn.clicked_func = self._toggle_exec_mode
        self._exec_mode_btn.setVisible(True)  # 常驻显示

        self._set_action_btns_visible(False)

    def _toggle_exec_mode(self, mode=None):
        """同步切换执行模式 UI 状态"""
        if mode:
            self.current_mode = mode
        else:
            # 如果没传参数，则在内部翻转当前状态
            self.current_mode = "ipython" if self.current_mode == "subprocess" else "subprocess"

        if self.current_mode == "subprocess":
            self._exec_mode_btn.icon_type = "exec_subprocess"
            self._exec_mode_btn.setToolTip("运行模式: Subprocess (独立环境)")
            self._exec_mode_btn.color = QtGui.QColor("#9b59b6")  # 子进程-紫色
            self._exec_mode_btn.hover_color = QtGui.QColor("#8e44ad")
        else:
            self._exec_mode_btn.icon_type = "exec_ipython"
            self._exec_mode_btn.setToolTip("运行模式: IPython (驻留内存)")
            self._exec_mode_btn.color = QtGui.QColor("#3498db")  # IPython-蓝色
            self._exec_mode_btn.hover_color = QtGui.QColor("#2980b9")

        # 仅当主动点击触发（即 mode 为空时）才发送信号给外部逻辑节点同步属性
        if mode is None:
            self.exec_mode_signal.emit(self.current_mode)

        self.update()

    def get_node_body_rect(self):
        rect = super(CustomNodeItem, self).boundingRect()
        return rect if rect.width() > 0 else QtCore.QRectF(0, 0, 180, 40)

    def boundingRect(self):
        rect = self.get_node_body_rect()
        return rect.adjusted(-2, -35, 2, 2)

    def shape(self):
        path = QtGui.QPainterPath()
        path.addRoundedRect(self.get_node_body_rect(), 20, 20)
        # 常驻按钮（标题栏按钮）始终加入碰撞区域
        path.addEllipse(self._collapse_btn.boundingRect().translated(self._collapse_btn.pos()))
        path.addEllipse(self._exec_mode_btn.boundingRect().translated(self._exec_mode_btn.pos()))
        # 悬浮按钮组仅在显示时加入
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
        # _exec_mode_btn 不由悬浮逻辑控制，始终 Visible

    def _update_elements_visibility(self):
        is_drawing_content = not self._is_collapsed and not self._proxy_mode
        for w in self._widgets.values(): w.widget().setVisible(is_drawing_content)
        for text in list(self._input_items.values()) + list(self._output_items.values()): text.setVisible(
            is_drawing_content)
        self._text_item.setVisible(not self._proxy_mode)
        self._icon_item.setVisible(not self._proxy_mode)
        self._collapse_btn.setVisible(not self._proxy_mode)
        self._exec_mode_btn.setVisible(not self._proxy_mode)  # Proxy 模式下隐藏常驻按钮
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
        radius = 20.0
        painter.setBrush(QtGui.QColor(32, 32, 35, 255));
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)
        header_h = max(self._text_item.boundingRect().height() + 8, 30.0)
        header_rect = QtCore.QRectF(rect.left(), rect.top(), rect.width(), header_h)
        base_color = QtGui.QColor(*self.color)
        gradient = QtGui.QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
        gradient.setColorAt(0, base_color.lighter(115));
        gradient.setColorAt(1, base_color)
        painter.setBrush(gradient)
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
        if self.selected:
            painter.setPen(QtGui.QPen(QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value), 2.5))
            painter.drawRoundedRect(rect, radius, radius)
        else:
            painter.setPen(QtGui.QPen(QtGui.QColor(60, 60, 65, 255), 1.2))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        painter.restore()

    def _draw_node_horizontal(self):
        self.prepareGeometryChange()
        header_height = max(self._text_item.boundingRect().height() + 8.0, 30.0)
        self._update_elements_visibility();
        self._set_base_size(add_h=header_height)
        rect = self.get_node_body_rect()
        if not self._proxy_mode:
            self._set_text_color(self.text_color)
            tw, th = self._text_item.boundingRect().width(), self._text_item.boundingRect().height()
            self._text_item.setPos(rect.center().x() - tw / 2, rect.top() + (header_height - th) / 2)
            self._icon_item.setPos(rect.left() + 38, rect.top() + (header_height - 24) / 2)
            self._collapse_btn.setPos(rect.left() + 6, rect.top() + (header_height - 28) / 2)

            # 模式按钮：固定在 Header 内部右侧
            self._exec_mode_btn.setPos(rect.right() - 34, rect.top() + (header_height - 28) / 2)

            self.align_widgets(v_offset=header_height + 12.0)
        else:
            self._update_proxy_text_position()
        self.align_ports(v_offset=header_height)
        # 悬浮组位置（顶部上方）
        btn_y = rect.top() - 30;
        spacing = 32
        self._close_btn.setPos(rect.right() - 32, btn_y);
        self._mute_btn.setPos(rect.right() - 32 - spacing, btn_y)
        self._run_btn.setPos(rect.right() - 32 - spacing * 2, btn_y);
        self._center_btn.setPos(rect.right() - 32 - spacing * 3, btn_y)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton: event.ignore(); return
        if event.button() == QtCore.Qt.RightButton:
            if self.scene(): self.scene().clearSelection(); self.setSelected(True); event.accept()
        super(CustomNodeItem, self).mousePressEvent(event)

    def paint(self, painter, option, widget):
        self.auto_switch_mode()
        if self.viewer() is None: return
        self._paint_horizontal(painter, option, widget)

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
            p_in_w = max(p_in_w, text.boundingRect().width() + 25);
            p_in_h += port.boundingRect().height() + 4
        for port, text in self._output_items.items():
            p_out_w = max(p_out_w, text.boundingRect().width() + 25);
            p_out_h += port.boundingRect().height() + 4
        if self._is_collapsed: return max(self._text_item.boundingRect().width() + 140, 180), max(p_in_h, p_out_h, 40)
        w_width = w_height = 0.0
        for widget in self._widgets.values():
            real = widget.widget();
            sz = real.sizeHint() if real else widget.boundingRect().size()
            w_width = max(w_width, sz.width());
            w_height += sz.height() + 10
        width = max(self._text_item.boundingRect().width() + 120, p_in_w + p_out_w + w_width + 40, 200)
        height = max(p_in_h, p_out_h, w_height) + 20
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
