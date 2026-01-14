# -*- coding: utf-8 -*-
from NodeGraphQt.constants import (
    NodeEnum, PortTypeEnum,
    LayoutDirectionEnum
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


class NodeActionButton(QtWidgets.QGraphicsItem):
    """
    极致动效矢量按钮。
    采用 ComfyUI 高端视觉风格，带悬停呼吸反馈。
    """

    def __init__(self, parent, icon_type, tooltip, color, hover_color):
        super(NodeActionButton, self).__init__(parent)
        self.setAcceptHoverEvents(True)
        self.icon_type = icon_type  # 'collapse', 'expand', 'run', 'debug', 'close'
        self.setToolTip(tooltip)

        self.color = QtGui.QColor(color)
        self.hover_color = QtGui.QColor(hover_color)
        self._hovered = False
        self._rect = QtCore.QRectF(0, 0, 28, 28)

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 1. 绘制高级交互反馈：带发光感
        if self._hovered:
            glow_color = self.hover_color.lighter(120)
            glow_color.setAlpha(180)
            painter.setBrush(glow_color)
            painter.setPen(QtGui.QPen(self.hover_color, 1.5))
            painter.drawRoundedRect(self._rect, 8, 8)
        else:
            # 默认状态下微弱背景
            painter.setBrush(QtGui.QColor(255, 255, 255, 10))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(self._rect, 8, 8)

        # 2. 矢量图标优化 (抗锯齿优化)
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 240), 2.0)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)

        m = 8.5
        r = self._rect
        cx, cy = r.center().x(), r.center().y()

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
            path.moveTo(r.left() + m + 1, r.top() + m - 1)
            path.lineTo(r.right() - m + 2, cy)
            path.lineTo(r.left() + m + 1, r.bottom() - m + 1)
            path.closeSubpath()
            painter.setBrush(QtGui.QColor(255, 255, 255, 220))
            painter.drawPath(path)
        elif self.icon_type == 'debug':
            # 优化版精致甲虫图标
            painter.drawEllipse(QtCore.QRectF(cx - 4, cy - 3, 8, 9))
            painter.drawLine(QtCore.QPointF(cx, cy - 3), QtCore.QPointF(cx, cy + 6))
            # 触角
            painter.drawArc(QtCore.QRectF(cx - 2.5, cy - 5, 5, 4), 0, 180 * 16)
            # 简化版腿部
            for i in [-1, 1]:
                painter.drawLine(QtCore.QPointF(cx + 4 * i, cy), QtCore.QPointF(cx + 6.5 * i, cy - 1))
                painter.drawLine(QtCore.QPointF(cx + 4 * i, cy + 3), QtCore.QPointF(cx + 7 * i, cy + 3))
                painter.drawLine(QtCore.QPointF(cx + 4 * i, cy + 6), QtCore.QPointF(cx + 6.5 * i, cy + 7))
        elif self.icon_type == 'zoom':
            o = 8.0
            l = 5.0

            # 左上折角 (顶点在左上，向右和向下延伸)
            painter.drawLine(QtCore.QPointF(cx - o, cy - o), QtCore.QPointF(cx - o + l, cy - o))
            painter.drawLine(QtCore.QPointF(cx - o, cy - o), QtCore.QPointF(cx - o, cy - o + l))

            # 右上折角 (顶点在右上，向左和向下延伸)
            painter.drawLine(QtCore.QPointF(cx + o, cy - o), QtCore.QPointF(cx + o - l, cy - o))
            painter.drawLine(QtCore.QPointF(cx + o, cy - o), QtCore.QPointF(cx + o, cy - o + l))

            # 左下折角 (顶点在左下，向右和向上延伸)
            painter.drawLine(QtCore.QPointF(cx - o, cy + o), QtCore.QPointF(cx - o + l, cy + o))
            painter.drawLine(QtCore.QPointF(cx - o, cy + o), QtCore.QPointF(cx - o, cy + o - l))

            # 右下折角 (顶点在右下，向左和向上延伸)
            painter.drawLine(QtCore.QPointF(cx + o, cy + o), QtCore.QPointF(cx + o - l, cy + o))
            painter.drawLine(QtCore.QPointF(cx + o, cy + o), QtCore.QPointF(cx + o, cy + o - l))
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
    超级性能/美观迭代版。
    完全重构了绘制路径，解决了 LOD 残留和对齐的所有顽疾。
    """
    _align = None
    ICON_NODE_BASE = ":/icons/同心圆.svg"

    def __init__(self, name='', parent=None):
        super(CustomNodeItem, self).__init__(name, parent)
        self.setAcceptHoverEvents(True)
        self._is_collapsed = False

        # 缓存路径，用于性能优化
        self._cached_main_path = QtGui.QPainterPath()
        self._cached_header_path = QtGui.QPainterPath()

        # 初始化自定义信号
        self.custom_signals = CustomNodeSignals()
        self.center_signal = self.custom_signals.node_center_triggered
        self.rename_signal = self.custom_signals.rename_triggered
        self.run_signal = self.custom_signals.run_triggered
        self.delete_signal = self.custom_signals.node_delete_triggered
        self.debug_signal = self.custom_signals.node_debug_triggered
        self.collapsed_toggle = self.custom_signals.collapsed_toggle

        self._init_base_components()
        self._init_custom_buttons()

    def _init_base_components(self):
        """初始化节点基础显示组件并清除默认干扰"""
        pixmap = QtGui.QPixmap(self.ICON_NODE_BASE)
        if pixmap.size().height() > 30:
            pixmap = pixmap.scaledToHeight(30, QtCore.Qt.SmoothTransformation)
        self._icon_item.setPixmap(pixmap)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)

        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont("Inter", 14, QtGui.QFont.Bold)  # 推荐使用更现代的 Inter 字体
        self._text_item.setFont(font)

        self._proxy_text_item = QtWidgets.QGraphicsTextItem(self.name, self)
        self._proxy_text_item.setFont(QtGui.QFont("Segoe UI", 36, QtGui.QFont.Bold))
        self._proxy_text_item.setVisible(False)

    def _init_custom_buttons(self):
        """初始化抬头悬浮功能组"""
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

        self._set_action_btns_visible(False)

    def boundingRect(self):
        """扩展包围盒：顶部留白用于悬浮按钮，支持完美点击"""
        rect = super(CustomNodeItem, self).boundingRect()
        return rect.adjusted(0, -32, 0, 0)

    def _set_action_btns_visible(self, visible):
        """控制悬浮功能按钮的可见性"""
        self._center_btn.setVisible(visible)  # 控制可见
        self._run_btn.setVisible(visible)
        self._mute_btn.setVisible(visible)
        self._close_btn.setVisible(visible)

    def _update_elements_visibility(self):
        """统一管理所有子元素的绘制显隐"""
        is_drawing_content = not self._is_collapsed and not self._proxy_mode

        # 1. 挂件与端口文本
        for w in self._widgets.values():
            w.widget().setVisible(is_drawing_content)

        for text in list(self._input_items.values()) + list(self._output_items.values()):
            text.setVisible(is_drawing_content)

        # 2. 基础组件
        self._text_item.setVisible(not self._proxy_mode)
        self._icon_item.setVisible(not self._proxy_mode)
        self._collapse_btn.setVisible(not self._proxy_mode) # 折叠按钮通常在 proxy 下隐藏以保持简洁

        # 3. 代理组件
        self._proxy_text_item.setVisible(self._proxy_mode)

    def toggle_collapse(self):
        """执行折叠状态切换逻辑"""
        self._is_collapsed = not self._is_collapsed
        self.collapsed_toggle.emit(self._is_collapsed)
        self._collapse_btn.icon_type = "expand" if self._is_collapsed else "collapse"

        self._update_elements_visibility()

        # 触发布局重计算
        if self.layout_direction == LayoutDirectionEnum.HORIZONTAL.value:
            self._draw_node_horizontal()
        else:
            self._draw_node_vertical()
        self.update()

    def hoverEnterEvent(self, event):
        self._set_action_btns_visible(True)
        super(CustomNodeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._set_action_btns_visible(False)
        super(CustomNodeItem, self).hoverLeaveEvent(event)

    def _paint_horizontal(self, painter, option, widget):
        """极致渲染：磨砂黑底座 + 层次感灰色边框 + 霓虹渐变 Header"""
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 基础坐标系统
        full_rect = self.boundingRect()
        rect = QtCore.QRectF(full_rect.left(), full_rect.top() + 32,
                             full_rect.width(), full_rect.height() - 32)
        radius = 20.0  # 使用之前建议的更圆润的半径

        # 1. 绘制深色磨砂底座
        painter.setBrush(QtGui.QColor(32, 32, 35, 255))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        # 2. 绘制 Header (逻辑保持不变)
        header_h = max(self._text_item.boundingRect().height() + 8, 30.0)
        header_rect = QtCore.QRectF(rect.left(), rect.top(), rect.width(), header_h)
        base_color = QtGui.QColor(*self.color)

        gradient = QtGui.QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
        gradient.setColorAt(0, base_color.lighter(115))
        gradient.setColorAt(1, base_color)

        painter.setBrush(gradient)
        if not self._is_collapsed:
            path = QtGui.QPainterPath()
            path.moveTo(header_rect.bottomLeft())
            path.lineTo(header_rect.left(), header_rect.top() + radius)
            path.arcTo(header_rect.left(), header_rect.top(), radius * 2, radius * 2, 180, -90)
            path.lineTo(header_rect.right() - radius, header_rect.top())
            path.arcTo(header_rect.right() - radius * 2, header_rect.top(), radius * 2, radius * 2, 90, -90)
            path.lineTo(header_rect.bottomRight())
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawRoundedRect(header_rect, radius, radius)

        # --- 3. 核心修改：绘制有层次感的灰色边框 ---
        if self.selected:
            # 选中状态：保持原有的高亮选中颜色
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value), 2.5))
            painter.drawRoundedRect(rect, radius, radius)
        else:
            # 非选中状态：双层灰色效果
            painter.setBrush(QtCore.Qt.NoBrush)

            # 第一层：深灰色外廓线 (定义形状)
            # 使用比底色略亮的暗灰色
            outer_gray = QtGui.QPen(QtGui.QColor(60, 60, 65, 255), 1.2)
            painter.setPen(outer_gray)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

            # 第二层：浅灰色内高光 (增加层次感/立体感)
            # 在顶部和左侧模拟微弱的光照
            inner_highlight = QtGui.QPen(QtGui.QColor(255, 255, 255, 35), 0.8)
            painter.setPen(inner_highlight)
            # 稍微缩小矩形范围，形成内嵌感
            painter.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), radius - 1.0, radius - 1.0)

        painter.restore()

    def _paint_vertical(self, painter, option, widget):
        """复用水平均质感"""
        self._paint_horizontal(painter, option, widget)

    def _draw_node_horizontal(self):
        self.prepareGeometryChange()

        text_rect = self._text_item.boundingRect()
        header_height = max(text_rect.height() + 8.0, 30.0)

        # 刷新所有组件显隐状态
        self._update_elements_visibility()

        # 【关键修改】：将 _set_base_size 移出 if not self._proxy_mode 块
        # 无论是否在代理模式，都要确保节点物理尺寸正确
        self._set_base_size(add_h=header_height)

        if not self._proxy_mode:
            # ... 原有的布局代码 (文字、图标、折叠按钮对齐) ...
            self._set_text_color(self.text_color)
            rect = self.boundingRect()
            body_top = rect.top() + 32
            tx = (rect.width() - text_rect.width()) / 2
            ty = body_top + (header_height - text_rect.height()) / 2
            self._text_item.setPos(tx, ty)
            self._icon_item.setPos(rect.left() + 38, body_top + (header_height - 24) / 2)
            self._collapse_btn.setPos(rect.left() + 6, body_top + (header_height - 28) / 2)
            self.align_widgets(v_offset=header_height + 12.0)
        else:
            # 代理模式下的逻辑
            self._update_proxy_text_position()

        # 端口永远需要对齐（内部逻辑会自动处理可见性）
        self.align_ports(v_offset=header_height)

        # 按钮位置计算 (确保按钮位置也基于正确的物理尺寸)
        rect = self.boundingRect()
        btn_y = (rect.top() + 32) - 30
        spacing = 32
        self._close_btn.setPos(rect.right() - 32, btn_y)
        self._mute_btn.setPos(rect.right() - 32 - spacing, btn_y)
        self._run_btn.setPos(rect.right() - 32 - spacing * 2, btn_y)
        self._center_btn.setPos(rect.right() - 32 - spacing * 3, btn_y)

        self.update()

    def _draw_node_vertical(self):
        """垂直布局支持"""
        self._draw_node_horizontal()

    def _calc_size_horizontal(self):
        """
        动态尺寸计算算法优化。
        修改点：尺寸计算不再受 proxy_mode 导致的隐藏影响，只受折叠状态影响。
        """
        # 端口占位逻辑
        p_in_w = p_out_w = p_in_h = p_out_h = 0.0

        # 即使端口在渲染上不可见(proxy模式)，但在逻辑上它是存在的
        for port, text in self._input_items.items():
            # 这里原本是 if port.isVisible(): 改为始终计算(除非你将来需要逻辑隐藏端口)
            p_in_w = max(p_in_w, text.boundingRect().width() + 25)
            p_in_h += port.boundingRect().height() + 4

        for port, text in self._output_items.items():
            p_out_w = max(p_out_w, text.boundingRect().width() + 25)
            p_out_h += port.boundingRect().height() + 4

        # 如果是折叠模式，返回折叠后的尺寸
        if self._is_collapsed:
            tw = self._text_item.boundingRect().width()
            return max(tw + 140, 180), max(p_in_h, p_out_h, 40)

        # 非折叠模式下（包括 proxy_mode），我们需要保持完整的尺寸
        fm = QtGui.QFontMetrics(self._text_item.font())
        text_w = max(self._text_item.boundingRect().width(), fm.horizontalAdvance(self.name))

        # 挂件占位逻辑
        w_width = w_height = 0.0
        for widget in self._widgets.values():
            # 【关键修改】：不再判断 widget.isVisible()
            # 因为在 proxy 模式下 widget 被隐藏了，但我们依然需要它占据宽度
            real = widget.widget()
            sz = real.sizeHint() if real else widget.boundingRect().size()
            w_width = max(w_width, sz.width())
            w_height += sz.height() + 10

        # 总宽度计算
        width = max(text_w + 120, p_in_w + p_out_w + w_width + 40, 200)
        height = max(p_in_h, p_out_h, w_height) + 20
        return width, height

    def _set_text_color(self, color=None):
        """设置统一视觉规范的文本颜色"""
        muted_white = QtGui.QColor(225, 225, 225)
        for text in list(self._input_items.values()) + list(self._output_items.values()):
            text.setDefaultTextColor(muted_white)
        self._text_item.setDefaultTextColor(QtCore.Qt.white)
        self._proxy_text_item.setDefaultTextColor(QtGui.QColor(255, 255, 255, 120))

    def mousePressEvent(self, event):
        """右键点击优化：直接选中节点并处理"""
        if event.button() == QtCore.Qt.RightButton:
            if self.scene():
                self.scene().clearSelection()
                self.setSelected(True)
                event.accept()
        super(CustomNodeItem, self).mousePressEvent(event)

    @property
    def icon(self):
        return self._properties.get('icon', self.ICON_NODE_BASE)

    @icon.setter
    def icon(self, value=None):
        """
        核心修复：将图标路径写回 _properties，这样 NodeGraphQt 才能在保存时找到它。
        """
        self._properties['icon'] = value  # <--- 关键修复：保存数据

        if isinstance(value, QtGui.QIcon):
            pixmap = value.pixmap(24, 24)
        elif isinstance(value, str):
            pixmap = QtGui.QPixmap(value)
        else:
            pixmap = QtGui.QPixmap(self.ICON_NODE_BASE)

        if not pixmap.isNull():
            pixmap = pixmap.scaled(24, 24, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self._icon_item.setPixmap(pixmap)
        if self.scene():
            self.post_init()
        self.update()

    @AbstractNodeItem.name.setter
    def name(self, name=''):
        """名称同步 Setter"""
        self.rename_signal.emit(self.name, name)
        AbstractNodeItem.name.fset(self, name)
        self._text_item.setPlainText(name)
        self._proxy_text_item.setPlainText(name)
        if self.scene():
            self._draw_node_horizontal()
        self.update()

    def paint(self, painter, option, widget):
        """主绘制入口，集成 LOD 逻辑"""
        self.auto_switch_mode()
        if self.viewer() is None: return

        if self.layout_direction == LayoutDirectionEnum.HORIZONTAL.value:
            self._paint_horizontal(painter, option, widget)
        else:
            self._paint_vertical(painter, option, widget)

    def _add_port(self, port):
        """添加端口：解决动态添加后不刷新对齐的顽疾"""
        text = QtWidgets.QGraphicsTextItem(port.name, self)
        text.setFont(QtGui.QFont("Segoe UI", 9))
        text.setVisible(port.display_name)

        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        else:
            self._output_items[port] = text

        # 立即重发布局，确保动态端口立即可见并对齐
        self._draw_node_horizontal()
        return port

    def auto_switch_mode(self):
        """根据缩放比例自动管理 LOD 状态"""
        if self.viewer() is None: return
        rect = self.sceneBoundingRect()
        l = self.viewer().mapToGlobal(self.viewer().mapFromScene(rect.topLeft()))
        r = self.viewer().mapToGlobal(self.viewer().mapFromScene(rect.topRight()))
        self.set_proxy_mode((r.x() - l.x()) < Settings.get_instance().node_proxy_size.value)

    def set_proxy_mode(self, mode):
        """设置 LOD 代理模式，完美处理绘制逻辑切换"""
        if mode is self._proxy_mode: return
        self._proxy_mode = mode

        # 执行同步可见性
        self._update_elements_visibility()

        if hasattr(self, '_x_item'):
            self._x_item.proxy_mode = mode

        if mode:
            self._proxy_text_item.setPlainText(self.name)
            self._update_proxy_text_position()

        self.update()

    def _update_proxy_text_position(self):
        """代理文本位置精准计算"""
        rect = self.boundingRect()
        body_rect = rect.adjusted(0, 32, 0, 0)
        tr = self._proxy_text_item.boundingRect()
        self._proxy_text_item.setPos(
            body_rect.center().x() - tr.width() / 2,
            body_rect.center().y() - tr.height() / 2
        )

    def remove_widget(self, widget):
        """彻底移除挂件"""
        w = self._widgets.pop(widget.get_name(), None)
        if w:
            w.setParent(None)
            w.deleteLater()

    def set_align(self, align):
        self._align = align

    def _align_widgets_horizontal(self, v_offset):
        """水平布局下挂件的自适应对齐"""
        if not self._widgets: return
        rect = self.boundingRect()
        body_top = rect.top() + 32
        y = body_top + v_offset

        for widget in self._widgets.values():
            if not widget.isVisible(): continue
            real = widget.widget()
            size = real.sizeHint() if real else widget.boundingRect().size()
            # 始终保持居中，追求极致美感
            widget.setPos(rect.center().x() - (size.width() / 2), y)
            y += size.height() + 10