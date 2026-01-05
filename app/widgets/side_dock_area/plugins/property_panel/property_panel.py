# -*- coding: utf-8 -*-
from collections import OrderedDict

from PyQt5.QtCore import Qt, QPropertyAnimation, QRect, QParallelAnimationGroup, QEasingCurve, QTimer
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QStyleOption, QStyle,
                             QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QFrame)
from qfluentwidgets import SmoothScrollArea, StrongBodyLabel, IconWidget, FluentIcon

from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.scan_components import ComponentScanner
from app.widgets.side_dock_area.plugins.property_panel.flow_control_panel import FlowControlPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.global_panel import GlobalPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_list_panel import NodeListPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_panel import NodePanelWidget


class FuturisticCard(QFrame):
    """
    科技感卡片容器：
    1. 自带顶部 HUD 标题栏（在堆叠露出的 42px 区域显示）。
    2. 支持动态流光边框和深度投影。
    """

    def __init__(self, parent=None, title="Unknown Node", icon=FluentIcon.DEVELOPER_TOOLS):
        super().__init__(parent)
        self.is_active = False
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("PropertyCard")

        # 内部布局
        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)

        # 1. 顶部 HUD 区域 (露出区域)
        self.header_hud = QWidget()
        self.header_hud.setFixedHeight(42)
        header_layout = QHBoxLayout(self.header_hud)
        header_layout.setContentsMargins(15, 0, 15, 0)

        self.icon_widget = IconWidget(icon, self.header_hud)
        self.icon_widget.setFixedSize(18, 18)

        self.title_label = StrongBodyLabel(title, self.header_hud)
        self.title_label.setStyleSheet("color: #0078d7; font-size: 13px;")

        header_layout.addWidget(self.icon_widget)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.card_layout.addWidget(self.header_hud)

        # 2. 内容区域 (放置真正的业务面板)
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(2, 0, 2, 2)
        self.card_layout.addWidget(self.content_area, 1)

        self.update_style()

    def set_title(self, title):
        self.title_label.setText(title)

    def set_active(self, active: bool):
        if self.is_active != active:
            self.is_active = active
            self.update_style()

    def update_style(self):
        # 活跃状态：霓虹蓝，非活跃状态：暗银色
        main_color = "#0078d7" if self.is_active else "#454545"
        bg_color = "#202020" if self.is_active else "#1a1a1a"

        self.setStyleSheet(f"""
            QWidget#PropertyCard {{
                background-color: {bg_color};
                border-top: 2px solid {main_color};
                border-left: 1px solid #333333;
                border-right: 1px solid #333333;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
        """)

        if self.is_active:
            self.title_label.setStyleSheet("color: #0078d7; font-weight: bold;")
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(25)
            eff.setColor(QColor(0, 120, 215, 120))
            eff.setOffset(0, -2)
            self.setGraphicsEffect(eff)
        else:
            self.title_label.setStyleSheet("color: #888888;")
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.8)  # 底层卡片半透明，增加视差感
            self.setGraphicsEffect(eff)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)


class PropertyPanel(QWidget):
    """
    终极科技版属性面板：
    - 全局变量面板与节点面板统一堆叠。
    - 解决了非全局面板显示空白的问题。
    - 增加 HUD 标题识别历史卡片。
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setMinimumWidth(300)

        # === 核心状态 ===
        self._node_panel_cache = OrderedDict()
        self._max_cache_size = 50
        self._history_stack = []
        self._allowed_update = False
        self._global_panel_built = False
        self.current_node = None

        # === 视觉基调 ===
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("PropertyPanel { background-color: #0f0f0f; }")  # 极深色底

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 舞台区域
        self.stage = QWidget()
        self.main_layout.addWidget(self.stage)

        # 外部引用
        self.node_list_panel_widget = None
        self.flow_control_panel_widget = None
        self.node_panel_widget = None
        self.global_panel_widget = None

        # 动画组
        self.anim_group = QParallelAnimationGroup(self)
        self._header_h = 42

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def update_properties(self, node, node_changed=False):
        """核心入口"""
        if not self._allowed_update:
            return

        # 1. 确定 Cache Key
        if node is None:
            cache_key = "GLOBAL_VARS"
        elif isinstance(node, list):
            cache_key = "MULTI_SELECT"
        else:
            cache_key = node.id

        # 2. 获取或创建卡片
        if cache_key in self._node_panel_cache:
            target_card = self._node_panel_cache[cache_key]
        else:
            target_card = self._build_new_card(node, cache_key)
            if not target_card: return
            self._node_panel_cache[cache_key] = target_card
            target_card.installEventFilter(self)

            if len(self._node_panel_cache) > self._max_cache_size:
                k, c = self._node_panel_cache.popitem(last=False)
                if c in self._history_stack: self._history_stack.remove(c)
                c.deleteLater()

        # 3. 维护历史栈（最近选中的在列表最后，代表最前方）
        if target_card in self._history_stack:
            self._history_stack.remove(target_card)
        self._history_stack.append(target_card)

        if len(self._history_stack) > 3:
            old = self._history_stack.pop(0)
            old.hide()

        # 4. 刷新数据内容（修复空白的关键）
        self._refresh_card_logic(target_card, node, cache_key)
        self.current_node = node if not isinstance(node, list) else None

        # 5. 执行动画
        self._play_stack_animation()

    def _build_new_card(self, node, cache_key):
        """创建卡片并植入业务面板"""
        # 根据类型确定标题和图标
        title = "Unknown"
        icon = FluentIcon.DEVELOPER_TOOLS

        if cache_key == "GLOBAL_VARS":
            title = "全局变量"
            icon = FluentIcon.GLOBE
        elif cache_key == "MULTI_SELECT":
            title = f"连通图列表"
            icon = FluentIcon.IOT
        elif isinstance(node, ControlFlowBackdrop):
            title = node.NODE_NAME
            icon = FluentIcon.SYNC
        else:
            title = node.name()
            icon = FluentIcon.INFO

        card = FuturisticCard(self.stage, title=title, icon=icon)

        # 业务逻辑植入
        if cache_key == "GLOBAL_VARS":
            # 全局面板是逻辑类，直接传入卡片的 content_layout
            self.global_panel_widget = GlobalPanelWidget(self.main_window, self, card.content_layout)
            card._logic = self.global_panel_widget
        elif cache_key == "MULTI_SELECT":
            # 节点列表是 Widget，需要 addWidget
            self.node_list_panel_widget = NodeListPanelWidget(self.main_window, self, node)
            card.content_layout.addWidget(self.node_list_panel_widget)
            card._logic = self.node_list_panel_widget
        elif isinstance(node, ControlFlowBackdrop):
            self.flow_control_panel_widget = FlowControlPanelWidget(self.main_window, self, node)
            card.content_layout.addWidget(self.flow_control_panel_widget)
            card._logic = self.flow_control_panel_widget
        else:
            self.node_panel_widget = NodePanelWidget(self.main_window, self, node)
            card.content_layout.addWidget(self.node_panel_widget)
            card._logic = self.node_panel_widget

        card._node_ref = node
        return card

    def _refresh_card_logic(self, card, node, cache_key):
        """调用子面板的刷新接口"""
        if cache_key == "GLOBAL_VARS":
            card._logic.build_ui()
            self._global_panel_built = True
        else:
            # 更新外部引用名，确保 main_widget 的调用有效
            if cache_key == "MULTI_SELECT":
                self.node_list_panel_widget = card._logic
            elif isinstance(node, ControlFlowBackdrop):
                self.flow_control_panel_widget = card._logic
            else:
                self.node_panel_widget = card._logic

            if hasattr(card._logic, 'update_data'):
                card._logic.update_data(node)
            elif hasattr(card._logic, 'build_ui'):
                card._logic.build_ui(node)

    def _play_stack_animation(self):
        """三级视差动画"""
        self.anim_group.stop()
        self.anim_group.clear()

        w, h = self.stage.width(), self.stage.height()
        if w <= 10: w, h = self.width(), self.height()

        count = len(self._history_stack)
        for i, card in enumerate(self._history_stack):
            card.show()
            card.raise_()

            is_active = (i == count - 1)
            card.set_active(is_active)

            # 位置计算：
            # i=0(最底层) -> y=0
            # i=2(活跃层) -> y=84, 露出底下的两个头部
            target_y = i * self._header_h
            target_rect = QRect(0, target_y, w, h - target_y)

            anim = QPropertyAnimation(card, b"geometry")
            anim.setDuration(500)
            anim.setStartValue(card.geometry())
            anim.setEndValue(target_rect)
            anim.setEasingCurve(QEasingCurve.OutBack if is_active else QEasingCurve.OutCubic)
            self.anim_group.addAnimation(anim)

        self.anim_group.start()

    def eventFilter(self, obj, event):
        """点击露出区域自动切回历史"""
        if event.type() == event.MouseButtonPress:
            if obj in self._history_stack and self._history_stack[-1] != obj:
                if 0 <= event.pos().y() <= self._header_h:
                    self.update_properties(getattr(obj, '_node_ref', None))
                    return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._history_stack:
            QTimer.singleShot(0, self._play_stack_animation)

    # ========================
    # 业务接口保持 (适配 PortWidget 等外部调用)
    # ========================
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
                port_dict = {p.name(): p for p in (node.input_ports() if is_input else node.output_ports())}
                result = []
                for comp_def in comp_ports:
                    result.append((comp_def.name, comp_def.label, comp_def.type))
                return result
        return [(p.name(), p.name(), ArgumentType.JSON) for p in
                (node.input_ports() if is_input else node.output_ports())]

    def get_node_description(self, node):
        if not node or "StatusDynamicNode_" not in node.model.type_: return ""
        comp_cls = ComponentScanner().get_component_by_uuid(node.uuid)
        return comp_cls.description if comp_cls else ""

    def _show_global_variables_panel(self):
        self.update_properties(None)

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
        if self.global_panel_widget: self.global_panel_widget.delete_output_from_global_var(self.main_window, node,
                                                                                            port_name)

    def _is_output_in_global_variable(self, node, port_name):
        if not self._global_panel_built: self.update_properties(None)
        return self.global_panel_widget.is_output_in_global_var(self.main_window, node, port_name)

    def update_node_list_content(self):
        if self.node_list_panel_widget: self.node_list_panel_widget.update_node_list_content()

    def get_current_execution_order(self):
        return self.node_list_panel_widget.get_current_order() if self.node_list_panel_widget else []

    def reset_current_components(self):
        if self.node_list_panel_widget: self.node_list_panel_widget.reset_components()

    def set_allowed_update(self, allowed: bool):
        self._allowed_update = allowed

    def _clear_node_layout(self):
        for card in self._node_panel_cache.values(): card.deleteLater()
        self._node_panel_cache.clear()
        self._history_stack.clear()