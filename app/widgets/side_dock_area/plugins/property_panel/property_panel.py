# -*- coding: utf-8 -*-
from collections import OrderedDict

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect, QParallelAnimationGroup, QEasingCurve, pyqtProperty, \
    pyqtSignal, QTimer, QPointF, QRectF
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPen, QFont, QPainterPath
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QFrame, QGraphicsOpacityEffect)
from qfluentwidgets import SmoothScrollArea, StrongBodyLabel, IconWidget, FluentIcon, TransparentToolButton

# 保持业务相关的引用（根据你的项目环境确保这些能正常 import）
from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.scan_components import ComponentScanner
from app.widgets.side_dock_area.plugins.property_panel.flow_control_panel import FlowControlPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.global_panel import GlobalPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_list_panel import NodeListPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_panel import NodePanelWidget


class FuturisticCard(QFrame):
    """
    还原最初视觉风格的极致优化版卡片：
    - 视觉：顶部 2px 蓝色/灰色条，左右深色 1px 边框，背景 #1e1e1e/#141414。
    - 逻辑：无半透明，非活跃字体变灰，Resize 防抖，QPainter 路径缓存绘制。
    """
    closed = pyqtSignal(object)

    def __init__(self, parent=None, title="Unknown Node", icon=FluentIcon.DEVELOPER_TOOLS):
        super().__init__(parent)
        self.is_active = False
        self._custom_opacity = 1.0
        self._last_rect = QRect()
        self._border_path = QPainterPath()

        # 还原最初的颜色配置
        self.COLOR_ACTIVE_TOP = QColor("#00a2ff")  # 活跃顶部蓝色
        self.COLOR_INACTIVE_TOP = QColor("#666666")  # 非活跃顶部灰色
        self.COLOR_SIDE = QColor("#2d2d2d")  # 左右深色边框
        self.COLOR_TEXT_DIM = QColor("#828282")  # 非活跃文字灰色

        self.BG_ACTIVE = QColor("#1e1e1e")  # 活跃背景
        self.BG_INACTIVE = QColor("#141414")  # 非活跃背景

        self.SCAN_LINE_PEN = QPen(QColor(255, 255, 255, 5), 1)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("PropertyCard")
        # 移除背景样式，全部由 paintEvent 处理
        self.setStyleSheet("QWidget#PropertyCard { background: transparent; border: none; }")

        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)

        # 1. 顶部 HUD
        self.header_hud = QWidget()
        self.header_hud.setFixedHeight(45)
        header_layout = QHBoxLayout(self.header_hud)
        header_layout.setContentsMargins(18, 0, 10, 0)

        self.icon_widget = IconWidget(icon, self.header_hud)
        self.icon_widget.setFixedSize(18, 18)
        self.title_label = StrongBodyLabel(title, self.header_hud)
        self.title_label.setFont(QFont("Segoe UI Semibold", 13))

        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, self.header_hud)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            TransparentToolButton { border-radius: 4px; padding: 4px; }
            TransparentToolButton:hover { background-color: rgba(255, 60, 60, 0.2); }
        """)

        self.close_btn_opacity = QGraphicsOpacityEffect(self.close_btn)
        self.close_btn.setGraphicsEffect(self.close_btn_opacity)
        self.close_btn.clicked.connect(lambda: self.closed.emit(self))

        header_layout.addWidget(self.icon_widget)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.close_btn)
        self.card_layout.addWidget(self.header_hud)

        # 2. 内容区域
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(4, 2, 4, 4)
        self.card_layout.addWidget(self.content_area, 1)

    @pyqtProperty(float)
    def cardOpacity(self):
        return self._custom_opacity

    @cardOpacity.setter
    def cardOpacity(self, v):
        self._custom_opacity = 1.0  # 强制不透明
        self.update()

    def set_title(self, title):
        """动态更新卡片标题"""
        self.title_label.setText(title)

    def set_active(self, active: bool, level: int = 0, animate: bool = True):
        self.is_active = active
        # 字体颜色逻辑
        text_color = self.COLOR_ACTIVE_TOP if active else self.COLOR_TEXT_DIM
        self.title_label.setStyleSheet(f"color: {text_color.name()};")

        # 按钮透明度区分
        # self.close_btn_opacity.setOpacity(1.0 if active else 0.4)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        r = 14.0  # 圆角半径

        # 1. 缓存背景路径（仅顶部圆角）
        if self._last_rect != self.rect():
            self._border_path = QPainterPath()
            # 创建仅顶部圆角的路径
            self._border_path.moveTo(0, r)
            self._border_path.arcTo(0, 0, r * 2, r * 2, 180, -90)  # 左上
            self._border_path.lineTo(rect.width() - r, 0)
            self._border_path.arcTo(rect.width() - r * 2, 0, r * 2, r * 2, 90, -90)  # 右上
            self._border_path.lineTo(rect.width(), rect.height())
            self._border_path.lineTo(0, rect.height())
            self._border_path.closeSubpath()
            self._last_rect = self.rect()

        # 2. 填充背景色
        p.fillPath(self._border_path, QBrush(self.BG_ACTIVE if self.is_active else self.BG_INACTIVE))

        # 3. 绘制扫描线 (步长10提高性能)
        p.setPen(self.SCAN_LINE_PEN)
        for i in range(0, self.height(), 10):
            p.drawLine(0, i, self.width(), i)

        # 4. 还原最初的边框逻辑
        # 顶部 2px 颜色条
        top_pen = QPen(self.COLOR_ACTIVE_TOP if self.is_active else self.COLOR_INACTIVE_TOP, 2)
        p.setPen(top_pen)
        # 绘制顶部圆弧部分的线条
        p.drawArc(QtCore.QRectF(0, 0, r * 2, r * 2), 90 * 16, 90 * 16)  # 左上弧
        p.drawLine(QtCore.QPointF(r, 0), QtCore.QPointF(rect.width() - r, 0))  # 顶平线
        p.drawArc(QtCore.QRectF(rect.width() - r * 2, 0, r * 2, r * 2), 0 * 16, 90 * 16)  # 右上弧

        # 左右 1px 深色边框
        side_pen = QPen(self.COLOR_SIDE, 1)
        p.setPen(side_pen)
        p.drawLine(QtCore.QPointF(0, r), QtCore.QPointF(0, rect.height()))  # 左
        p.drawLine(QtCore.QPointF(rect.width(), r), QtCore.QPointF(rect.width(), rect.height()))  # 右


class PropertyPanel(QWidget):
    """
    极致优化版属性面板：
    - 引入 Resize 防抖计时器，避免在拖动窗口边缘时进行高频几何重排和 raise_() 调用。
    - 批量处理 setUpdatesEnabled 状态，消除动画过程中的闪烁。
    """

    def __init__(self, main_window, parent=None, max_history=3, header_height=45):
        super().__init__(parent)
        self.main_window = main_window
        self._max_history = max_history
        self._header_reveal_h = header_height

        self.setMinimumWidth(280)
        self.setMinimumHeight(250)

        self._node_panel_cache = OrderedDict()
        self._max_cache_size = 50
        self._history_stack = []
        self._allowed_update = False
        self._global_panel_built = False
        self.current_node = None

        # Resize 防抖计时器
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_timeout)
        self._is_resizing = False

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("UltimatePropertyPanel")
        self.setStyleSheet("#UltimatePropertyPanel { background-color: transparent; }")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.stage = QWidget()
        self.main_layout.addWidget(self.stage)

        self.node_list_panel_widget = None
        self.flow_control_panel_widget = None
        self.node_panel_widget = None
        self.global_panel_widget = None

        self.anim_group = QParallelAnimationGroup(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(300, lambda: self._sync_stack_layout(animate=False))

    def update_properties(self, node, node_changed=False):
        if not self._allowed_update:
            return

        if node is None:
            cache_key = "GLOBAL_DASHBOARD"
        elif isinstance(node, list):
            cache_key = "MULTI_LIST_VIEW"
        else:
            cache_key = node.id

        if cache_key in self._node_panel_cache:
            target_card = self._node_panel_cache[cache_key]
        else:
            target_card = self._create_card_widget(node, cache_key)
            if not target_card: return
            self._node_panel_cache[cache_key] = target_card
            target_card.installEventFilter(self)
            target_card.closed.connect(self._close_card)

            if len(self._node_panel_cache) > self._max_cache_size:
                k, c = self._node_panel_cache.popitem(last=False)
                if c in self._history_stack: self._history_stack.remove(c)
                c.deleteLater()

        if target_card in self._history_stack:
            self._history_stack.remove(target_card)
        self._history_stack.append(target_card)

        if len(self._history_stack) > self._max_history:
            abandoned = self._history_stack.pop(0)
            abandoned.hide()

        self._refresh_card_content(target_card, node, cache_key)
        self.current_node = node if not isinstance(node, list) else None
        self._sync_stack_layout(animate=True)

    def _close_card(self, card):
        """关闭并移除历史卡片逻辑"""
        if card not in self._history_stack:
            return

        is_active = (self._history_stack[-1] == card)
        self._history_stack.remove(card)
        card.hide()

        if is_active:
            if self._history_stack:
                next_card = self._history_stack[-1]
                self.update_properties(getattr(next_card, '_node_ref', None))
            else:
                self.update_properties(None)
        else:
            self._sync_stack_layout(animate=True)

    def _sync_stack_layout(self, animate=True):
        # 如果正在进行窗口拖拽缩放，跳过带有动画的请求，避免坐标冲突
        if self._is_resizing and animate:
            return

        if animate:
            self.anim_group.stop()
            self.anim_group.clear()

        # 批量禁止渲染，极大减少 Layout 反复计算开销
        self.stage.setUpdatesEnabled(False)

        w, h = self.stage.width(), self.stage.height()
        if w <= 10: w, h = self.width(), self.height()

        stack_count = len(self._history_stack)
        for i, card in enumerate(self._history_stack):
            card.show()
            # 只有在动画过程中才 raise，避免非必要的图形层级重算
            if animate:
                card.raise_()

            level = (stack_count - 1) - i
            card.set_active(level == 0, level, animate=animate)
            target_y = i * self._header_reveal_h
            target_rect = QRect(0, target_y, w, h - target_y)

            if animate:
                anim = QPropertyAnimation(card, b"geometry")
                anim.setDuration(400)  # 稍微缩短时间，增加灵敏度感
                anim.setStartValue(card.geometry())
                anim.setEndValue(target_rect)
                curve = QEasingCurve.OutCubic if level == 0 else QEasingCurve.OutQuart
                anim.setEasingCurve(curve)
                self.anim_group.addAnimation(anim)
            else:
                card.setGeometry(target_rect)

        if animate and self.anim_group.animationCount() > 0:
            self.anim_group.start()

        self.stage.setUpdatesEnabled(True)

    def resizeEvent(self, event):
        """防抖 Resize 逻辑"""
        self._is_resizing = True
        new_w = event.size().width()

        # 1. 在拖动过程中，仅快速同步修改卡片的宽度，不改变位置和高度
        # 这对于 Qt 绘图引擎来说是廉价的。
        for card in self._history_stack:
            if card.isVisible():
                curr_geo = card.geometry()
                card.setGeometry(curr_geo.x(), curr_geo.y(), new_w, curr_geo.height())

        # 2. 启动计时器。如果 50ms 内不再 resize，说明停止了拖拽，再刷新纵向布局。
        self._resize_timer.start(50)
        super().resizeEvent(event)

    def _on_resize_timeout(self):
        self._is_resizing = False
        self._sync_stack_layout(animate=False)

    def eventFilter(self, obj, event):
        if event.type() == event.MouseButtonPress:
            # 过滤点击关闭按钮时的事件
            btn = obj.findChild(TransparentToolButton)
            if btn and obj.childAt(event.pos()) == btn:
                return False

            if obj in self._history_stack and self._history_stack[-1] != obj:
                if 0 <= event.pos().y() <= self._header_reveal_h:
                    self.update_properties(getattr(obj, '_node_ref', None))
                    return True
        return super().eventFilter(obj, event)

    def _create_card_widget(self, node, key):
        title, icon = self._get_metadata(node, key)
        card = FuturisticCard(self.stage, title=title, icon=icon)

        if key == "GLOBAL_DASHBOARD":
            self.global_panel_widget = GlobalPanelWidget(self.main_window, self, card.content_layout)
            card._logic = self.global_panel_widget
            card._is_logic_class = True
        else:
            if key == "MULTI_LIST_VIEW":
                logic = NodeListPanelWidget(self.main_window, self, node)
            elif isinstance(node, ControlFlowBackdrop):
                logic = FlowControlPanelWidget(self.main_window, self, node)
            else:
                logic = NodePanelWidget(self.main_window, self, node)
            card.content_layout.addWidget(logic)
            card._logic = logic
            card._is_logic_class = False

        card._node_ref = node
        return card

    def _refresh_card_content(self, card, node, key):
        # --- 新增：刷新卡片标题，应对重命名 ---
        new_title, _ = self._get_metadata(node, key)
        card.set_title(new_title)
        # -----------------------------------

        if getattr(card, "_is_logic_class", False):
            card._logic.build_ui()
            self._global_panel_built = True
        else:
            if key == "MULTI_LIST_VIEW":
                self.node_list_panel_widget = card._logic
            elif isinstance(node, ControlFlowBackdrop):
                self.flow_control_panel_widget = card._logic
            else:
                self.node_panel_widget = card._logic

            if hasattr(card._logic, 'update_data'):
                card._logic.update_data(node)
            elif hasattr(card._logic, 'build_ui'):
                card._logic.build_ui(node)

    def _get_metadata(self, node, key):
        if key == "GLOBAL_DASHBOARD": return "全局变量", FluentIcon.GLOBE
        if key == "MULTI_LIST_VIEW": return f"连通图列表", FluentIcon.IOT
        if isinstance(node, ControlFlowBackdrop): return node.NODE_NAME, FluentIcon.SYNC
        return node.name(), FluentIcon.INFO

    # --- 外部业务接口 ---

    def set_scrollbar(self, widget):
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background-color: transparent;")
        scroll.setStyleSheet("SmoothScrollArea { background-color: transparent; border: none; }")
        scroll.setWidget(widget)
        return scroll

    def get_port_info(self, node, is_input=True):
        full_path = getattr(node, 'FULL_PATH', None)
        if full_path and hasattr(self.main_window, 'component_map'):
            comp_cls = self.main_window.component_map.get(full_path)
            if comp_cls:
                comp_ports = getattr(comp_cls, 'inputs' if is_input else 'outputs', [])
                return [(p.name, p.label, p.type) for p in comp_ports]
        return [(p.name(), p.name(), ArgumentType.JSON) for p in
                (node.input_ports() if is_input else node.output_ports())]

    def get_node_description(self, node):
        if hasattr(node, 'description'):
            return node.description
        if not node or "StatusDynamicNode_" not in node.model.type_:
            return ""
        comp_cls = ComponentScanner().get_component_by_uuid(node.uuid)
        return comp_cls.description if comp_cls else ""

    def _on_global_variables_changed(self, var_type, var_name, action):
        if self.global_panel_widget: self.global_panel_widget.on_global_variables_changed(var_type, var_name, action)

    def _refresh_node_vars_page(self):
        if self.global_panel_widget: self.global_panel_widget._refresh_node_vars_page()

    def _copy_as_expression(self, prefix, var_name):
        if self.global_panel_widget: self.global_panel_widget.copy_as_expression(prefix, var_name)

    def _add_output_to_global_variable(self, node, port_name):
        self.update_properties(None)
        self.global_panel_widget.add_output_to_global_var(self.main_window, node, port_name)

    def _delete_output_from_global_variable(self, node, port_name):
        if self.global_panel_widget:
            self.global_panel_widget.delete_output_from_global_var(self.main_window, node, port_name)

    def _is_output_in_global_variable(self, node, port_name):
        if not self._global_panel_built:
            self.update_properties(None)
        return self.global_panel_widget.is_output_in_global_var(self.main_window, node, port_name)

    def update_node_list_content(self):
        if self.node_list_panel_widget:
            self.node_list_panel_widget.update_node_list_content()

    def get_current_execution_order(self):
        return self.node_list_panel_widget.get_current_order() if self.node_list_panel_widget else []

    def reset_current_components(self):
        if self.node_list_panel_widget: self.node_list_panel_widget.reset_components()

    def set_allowed_update(self, allowed: bool):
        self._allowed_update = allowed

    def _clear_node_layout(self):
        # 优化销毁逻辑，确保无内存残留
        for card in self._node_panel_cache.values():
            card.closed.disconnect()
            card.deleteLater()
        self._node_panel_cache.clear()
        self._history_stack.clear()