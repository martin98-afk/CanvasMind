# -*- coding: utf-8 -*-
from NodeGraphQt.constants import (
    NodeEnum, PortTypeEnum,
    LayoutDirectionEnum
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_base import NodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from PyQt5 import QtWidgets, QtCore, QtGui
from qtpy import QtGui

from app.utils.config import Settings


class CustomNodeSignals(QtCore.QObject):
    """
    自定义信号类，负责节点交互触发的事件分发。
    """
    rename = QtCore.pyqtSignal(str, str)
    run_triggered = QtCore.pyqtSignal()
    node_delete_triggered = QtCore.pyqtSignal()
    node_debug_triggered = QtCore.pyqtSignal()


class NodeActionButton(QtWidgets.QGraphicsItem):
    """
    矢量图标按钮组件，支持运行、调试、删除、折叠等矢量图形绘制。
    """

    def __init__(self, parent, icon_type, tooltip, color, hover_color):
        super(NodeActionButton, self).__init__(parent)
        self.setAcceptHoverEvents(True)
        self.icon_type = icon_type  # 'collapse', 'expand', 'run', 'debug', 'close'
        self.setToolTip(tooltip)
        self.color = QtGui.QColor(color)
        self.hover_color = QtGui.QColor(hover_color)
        self._hovered = False
        self.clicked_func = None
        self._rect = QtCore.QRectF(0, 0, 16, 16)

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 绘制背景圆形反馈
        if self._hovered:
            painter.setBrush(self.hover_color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(self._rect, 3, 3)

        # 矢量图标绘制设置
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 220), 1.5)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)

        m = 4.5  # 矢量图标内部边距
        r = self._rect
        cx, cy = r.center().x(), r.center().y()

        # 使用 QPointF 避免浮点数类型转换报错
        if self.icon_type == 'collapse':
            painter.drawLine(QtCore.QPointF(r.left() + m, cy),
                             QtCore.QPointF(r.right() - m, cy))
        elif self.icon_type == 'expand':
            painter.drawLine(QtCore.QPointF(r.left() + m, cy),
                             QtCore.QPointF(r.right() - m, cy))
            painter.drawLine(QtCore.QPointF(cx, r.top() + m),
                             QtCore.QPointF(cx, r.bottom() - m))
        elif self.icon_type == 'run':
            path = QtGui.QPainterPath()
            path.moveTo(r.left() + m + 1, r.top() + m)
            path.lineTo(r.right() - m + 1, cy)
            path.lineTo(r.left() + m + 1, r.bottom() - m)
            path.closeSubpath()
            painter.setBrush(QtGui.QColor(255, 255, 255, 200))
            painter.drawPath(path)
        elif self.icon_type == 'debug':
            painter.drawEllipse(QtCore.QRectF(cx - 3.5, cy - 3.5, 7, 7))
            painter.drawPoint(QtCore.QPointF(cx, cy))
        elif self.icon_type == 'close':
            painter.drawLine(QtCore.QPointF(r.left() + m, r.top() + m),
                             QtCore.QPointF(r.right() - m, r.bottom() - m))
            painter.drawLine(QtCore.QPointF(r.right() - m, r.top() + m),
                             QtCore.QPointF(r.left() + m, r.bottom() - m))
        painter.restore()

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        event.accept()
        if self.clicked_func:
            self.clicked_func()


class CustomNodeItem(NodeItem):
    """
    高度定制化的节点图形项，具有高级灰色质感和居中标题布局。
    """
    _align = None
    ICON_NODE_BASE = ":/icons/node_base.png"

    def __init__(self, name='node', parent=None):
        # 必须正确调用父类构造，防止 _properties 字典未初始化
        super(CustomNodeItem, self).__init__(name, parent)
        self.setAcceptHoverEvents(True)
        self._is_collapsed = False

        # 初始化自定义信号系统
        self.custom_signals = CustomNodeSignals()
        self.rename_signal = self.custom_signals.rename
        self.run_signal = self.custom_signals.run_triggered
        self.delete_signal = self.custom_signals.node_delete_triggered
        self.debug_signal = self.custom_signals.node_debug_triggered

        # 组件初始化
        self._init_base_components()
        self._init_custom_buttons()

    def _init_base_components(self):
        """初始化节点基础显示组件"""
        # 加载并缩放节点图标
        pixmap = QtGui.QPixmap(self.ICON_NODE_BASE)
        if pixmap.size().height() > 28:
            pixmap = pixmap.scaledToHeight(28, QtCore.Qt.SmoothTransformation)
        self._icon_item.setPixmap(pixmap)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)

        # 节点标题设置
        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold)
        self._text_item.setFont(font)

        # 代理文字显示设置
        self._proxy_text_item = QtWidgets.QGraphicsTextItem(self.name, self)
        self._proxy_text_item.setFont(QtGui.QFont("Arial", 35, QtGui.QFont.Bold))
        self._proxy_text_item.setVisible(False)

    def _init_custom_buttons(self):
        """初始化节点抬头交互按钮"""
        # 左侧折叠按钮
        self._collapse_btn = NodeActionButton(
            self, "collapse", "折叠/展开", "#444444", "#666666"
        )
        self._collapse_btn.clicked_func = self.toggle_collapse

        # 右侧快捷功能组
        self._run_btn = NodeActionButton(
            self, "run", "执行", "#27ae60", "#2ecc71"
        )
        self._run_btn.clicked_func = self.run_signal.emit

        self._mute_btn = NodeActionButton(
            self, "debug", "调试", "#f39c12", "#f1c40f"
        )
        self._mute_btn.clicked_func = self.debug_signal.emit

        self._close_btn = NodeActionButton(
            self, "close", "删除", "#c0392b", "#e74c3c"
        )
        self._close_btn.clicked_func = self.delete_signal.emit

        self._set_action_btns_visible(False)

    def _set_action_btns_visible(self, visible):
        """显示/隐藏右侧功能按钮"""
        self._run_btn.setVisible(visible)
        self._mute_btn.setVisible(visible)
        self._close_btn.setVisible(visible)

    def toggle_collapse(self):
        """执行节点折叠状态切换"""
        self._is_collapsed = not self._is_collapsed
        self._collapse_btn.icon_type = "expand" if self._is_collapsed else "collapse"

        # 隐藏/显示节点内挂件
        visible = not self._is_collapsed
        for w in self._widgets.values():
            w.widget().setVisible(visible)

        # 重新触发布局绘制
        if self.layout_direction == LayoutDirectionEnum.HORIZONTAL.value:
            self._draw_node_horizontal()
        else:
            self._draw_node_vertical()
        self.update()

    def hoverEnterEvent(self, event):
        if not self._proxy_mode:
            self._set_action_btns_visible(True)
        super(CustomNodeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._set_action_btns_visible(False)
        super(CustomNodeItem, self).hoverLeaveEvent(event)

    def _paint_horizontal(self, painter, option, widget):
        """绘制水平布局下的高级感背景"""
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.boundingRect()
        radius = 4.0

        # 1. 绘制工业白灰色主体背景
        body_color = QtGui.QColor(55, 55, 58)
        painter.setBrush(body_color)
        painter.setPen(QtGui.QPen(QtGui.QColor(30, 30, 30), 1.2))
        painter.drawRoundedRect(rect, radius, radius)

        # 2. 绘制抬头 Header 色块
        header_height = max(self._text_item.boundingRect().height() + 4, 24.0)
        header_rect = QtCore.QRectF(rect.left(), rect.top(), rect.width(), header_height)
        h_color = QtGui.QColor(*self.color)
        if not self.selected:
            h_color.setAlpha(200)

        path = QtGui.QPainterPath()
        path.addRoundedRect(header_rect, radius, radius)
        painter.setBrush(h_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPath(path)

        # 补齐底部圆角区域（展开模式）
        if not self._is_collapsed:
            painter.drawRect(QtCore.QRectF(
                rect.left(), rect.top() + header_height - radius, rect.width(), radius))

        # 3. 选中边框高亮
        if self.selected:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value), 2.0))
            painter.drawRoundedRect(rect, radius, radius)
        painter.restore()

    def _draw_node_horizontal(self):
        """核心布局更新逻辑"""
        MIN_HEADER_HEIGHT = 24.0
        text_rect = self._text_item.boundingRect()
        header_height = max(text_rect.height() + 4.0, MIN_HEADER_HEIGHT)

        if not self._proxy_mode:
            v_offset = (header_height - text_rect.height()) / 2.0
            port_text_visible = not self._is_collapsed

            # 修正：遍历 values() 隐藏端口文本，防止 unpack 报错
            for text in self._input_items.values():
                text.setVisible(port_text_visible)
            for text in self._output_items.values():
                text.setVisible(port_text_visible)

            self._set_base_size(add_h=header_height)
            self._set_text_color(self.text_color)

            # --- 物理对齐逻辑 ---
            rect = self.boundingRect()

            # 1. 标题文字居中对齐
            text_x = (rect.width() - text_rect.width()) / 2
            self._text_item.setPos(text_x, v_offset)

            # 2. 节点图标和折叠按钮紧靠在一起 (折叠按钮x=4, 图标紧随其后)
            # 左侧按钮占位约 20px, 图标位置固定在左侧按钮后方
            self._icon_item.setPos(rect.left() + 24, v_offset - 1.5)

            # 3. HTML/挂件位置更新
            self.align_widgets(v_offset=header_height + 10.0)

        self.align_ports(v_offset=header_height)

        # --- 功能按钮定位 ---
        rect = self.boundingRect()
        btn_y = rect.top() + (header_height - 16) / 2

        # 折叠按钮在最左侧
        self._collapse_btn.setPos(rect.left() + 4, btn_y)

        # 右侧功能按钮组紧凑对齐
        spacing = 18
        self._close_btn.setPos(rect.right() - 20, btn_y)
        self._mute_btn.setPos(rect.right() - 20 - spacing, btn_y)
        self._run_btn.setPos(rect.right() - 20 - spacing * 2, btn_y)

        self.update()
        if self._proxy_mode:
            self._update_proxy_text_position()

    def _calc_size_horizontal(self):
        """动态计算节点宽高，兼容 HTML 预览和挂件高度"""
        if self._is_collapsed:
            tw = self._text_item.boundingRect().width()
            return max(tw + 120, 160), 24

        font_metrics = QtGui.QFontMetrics(self._text_item.font())
        text_w = max(self._text_item.boundingRect().width(),
                     font_metrics.horizontalAdvance(self.name))
        text_h = self._text_item.boundingRect().height()

        # 端口尺寸计算
        p_in_w = p_out_w = p_in_h = p_out_h = 0.0
        port_width = 0.0
        for port, text in self._input_items.items():
            if not port.isVisible(): continue
            port_width = port.boundingRect().width()
            if text.isVisible():
                p_in_w = max(p_in_w, text.boundingRect().width())
            p_in_h += port.boundingRect().height()

        for port, text in self._output_items.items():
            if not port.isVisible(): continue
            port_width = port.boundingRect().width()
            if text.isVisible():
                p_out_w = max(p_out_w, text.boundingRect().width())
            p_out_h += port.boundingRect().height()

        # 挂件 (HTML预览等) 尺寸计算
        widget_width = widget_height = 0.0
        for widget in self._widgets.values():
            if not widget.isVisible(): continue
            real_widget = widget.widget()
            w_size = real_widget.sizeHint() if real_widget else widget.boundingRect().size()
            widget_width = max(widget_width, w_size.width())
            widget_height += w_size.height() + 10

        # 计算最终总宽度 (预留按钮和端口空间)
        width = max(port_width + (p_in_w + p_out_w) + max(text_w, widget_width) + 80,
                    self._proxy_text_item.boundingRect().width() + 20)
        # 计算最终总高度
        height = max(text_h + 10, p_in_h, p_out_h, widget_height) + 30
        return width, height

    def _set_text_color(self, color=None):
        """设置所有文字颜色"""
        for text in self._input_items.values():
            text.setDefaultTextColor(QtGui.QColor(220, 220, 220))
        for text in self._output_items.values():
            text.setDefaultTextColor(QtGui.QColor(220, 220, 220))
        self._text_item.setDefaultTextColor(QtGui.QColor("white"))
        self._proxy_text_item.setDefaultTextColor(QtGui.QColor("white"))

    def mousePressEvent(self, event):
        """处理鼠标点击事件，支持右键直接选中节点"""
        if event.button() == QtCore.Qt.RightButton:
            scene = self.scene()
            if scene:
                scene.clearSelection()
                event.accept()
                self.setSelected(True)
        super(CustomNodeItem, self).mousePressEvent(event)

    @property
    def icon(self):
        # 修正：确保从 _properties 安全读取
        return self._properties.get('icon', self.ICON_NODE_BASE)

    @icon.setter
    def icon(self, value=None):
        """设置节点图标并动态更新显示"""
        if isinstance(value, QtGui.QIcon):
            pixmap = value.pixmap(24, 24)
        elif isinstance(value, str):
            pixmap = QtGui.QPixmap(value)
        else:
            pixmap = QtGui.QPixmap(self.ICON_NODE_BASE)

        if not pixmap.isNull():
            pixmap = pixmap.scaled(24, 24, QtCore.Qt.KeepAspectRatio,
                                   QtCore.Qt.SmoothTransformation)
        self._icon_item.setPixmap(pixmap)
        if self.scene():
            self.post_init()
        self.update()

    @AbstractNodeItem.name.setter
    def name(self, name=''):
        """设置节点名称并同步到图形项"""
        self.rename_signal.emit(self.name, name)
        AbstractNodeItem.name.fset(self, name)
        if name == self._text_item.toPlainText():
            return
        self._text_item.setPlainText(name)
        self._proxy_text_item.setPlainText(name)
        if self.scene():
            self._draw_node_horizontal()
        self.update()

    def paint(self, painter, option, widget):
        """绘制节点主入口"""
        self.auto_switch_mode()
        if self.viewer() is None:
            return
        if self.layout_direction == LayoutDirectionEnum.HORIZONTAL.value:
            self._paint_horizontal(painter, option, widget)
        else:
            self._paint_vertical(painter, option, widget)

    def _add_port(self, port):
        """向节点添加端口图形项"""
        text = QtWidgets.QGraphicsTextItem(port.name, self)
        text.setFont(QtGui.QFont("Arial", 9))
        text.setDefaultTextColor(QtGui.QColor(200, 200, 200))
        text.setVisible(port.display_name)
        text.setCacheMode(QtWidgets.QGraphicsItem.NoCache)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        elif port.port_type == PortTypeEnum.OUT.value:
            self._output_items[port] = text
        return port

    def auto_switch_mode(self):
        """根据画布缩放级别动态切换 LOD 模式"""
        if self.viewer() is None:
            return
        rect = self.sceneBoundingRect()
        l = self.viewer().mapToGlobal(self.viewer().mapFromScene(rect.topLeft()))
        r = self.viewer().mapToGlobal(self.viewer().mapFromScene(rect.topRight()))
        self.set_proxy_mode((r.x() - l.x()) < Settings.get_instance().node_proxy_size.value)

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

    def _update_proxy_text_position(self):
        """更新 LOD 代理文本到节点中心位置"""
        rect = self.boundingRect()
        text_rect = self._proxy_text_item.boundingRect()
        self._proxy_text_item.setPos(
            rect.center().x() - text_rect.width() / 2,
            rect.center().y() - text_rect.height() / 2
        )

    def remove_widget(self, widget):
        """从节点移除挂件"""
        w = self._widgets.pop(widget.get_name(), None)
        if w:
            w.setParent(None)
            w.deleteLater()

    def set_align(self, align):
        """设置对齐方式"""
        self._align = align

    def _align_widgets_horizontal(self, v_offset):
        """水平布局下对齐节点内挂件"""
        if not self._widgets:
            return
        rect = self.boundingRect()
        y = rect.y() + v_offset
        for widget in self._widgets.values():
            if not widget.isVisible():
                continue
            real_widget = widget.widget()
            w_size = real_widget.sizeHint() if real_widget else widget.boundingRect().size()
            width = w_size.width()

            # 默认为居中对齐，确保 ComfyUI 挂件视觉美感
            x = rect.center().x() - (width / 2)
            widget.setPos(x, y)
            y += (w_size.height() if real_widget else widget.boundingRect().height()) + 8