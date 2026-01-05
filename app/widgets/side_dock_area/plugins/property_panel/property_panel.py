# -*- coding: utf-8 -*-
from collections import OrderedDict

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect, QParallelAnimationGroup, QEasingCurve, pyqtProperty, \
    pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPen, QFont, QPainterPath
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QFrame)
from qfluentwidgets import SmoothScrollArea, StrongBodyLabel, IconWidget, FluentIcon, TransparentToolButton

from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.scan_components import ComponentScanner
from app.widgets.side_dock_area.plugins.property_panel.flow_control_panel import FlowControlPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.global_panel import GlobalPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_list_panel import NodeListPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_panel import NodePanelWidget


class FuturisticCard(QFrame):
    """
    极致科技感卡片容器：
    - 集成数字化 HUD 头部。
    - 新增关闭（销毁）按钮。
    - 采用 pyqtProperty 驱动高性能渲染。
    """
    closed = pyqtSignal(object)  # 发射自身实例用于关闭逻辑

    def __init__(self, parent=None, title="Unknown Node", icon=FluentIcon.DEVELOPER_TOOLS):
        super().__init__(parent)
        self.is_active = False
        self._custom_opacity = 1.0
        self._last_rect = QRect()
        self._border_path = QPainterPath()

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("PropertyCard")

        # 内部布局
        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)

        # 1. 顶部 HUD 区域
        self.header_hud = QWidget()
        self.header_hud.setFixedHeight(45)
        header_layout = QHBoxLayout(self.header_hud)
        header_layout.setContentsMargins(18, 0, 10, 0)

        # 图标和标题
        self.icon_widget = IconWidget(icon, self.header_hud)
        self.icon_widget.setFixedSize(18, 18)
        self.title_label = StrongBodyLabel(title, self.header_hud)
        self.title_label.setFont(QFont("Segoe UI Semibold", 10))

        # 数字化关闭按钮
        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, self.header_hud)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("移除此卡片")
        self.close_btn.clicked.connect(lambda: self.closed.emit(self))
        # 初始隐藏，只有在活跃或堆叠中才显示（由父级控制）

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

        self.update_style()

    @pyqtProperty(float)
    def cardOpacity(self):
        return self._custom_opacity

    @cardOpacity.setter
    def cardOpacity(self, v):
        self._custom_opacity = v
        self.update()

    def set_active(self, active: bool, level: int = 0, animate: bool = True):
        self.is_active = active
        target_op = 1.0 if active else max(0.3, 1.0 - level * 0.3)

        if animate:
            self.op_ani = QPropertyAnimation(self, b"cardOpacity")
            self.op_ani.setDuration(400)
            self.op_ani.setEndValue(target_op)
            self.op_ani.setEasingCurve(QEasingCurve.OutCubic)
            self.op_ani.start()
        else:
            self.cardOpacity = target_op

        self.update_style()

    def update_style(self):
        neon_blue = "#00a2ff" if self.is_active else "#666666"
        bg_color = "#1e1e1e" if self.is_active else "#141414"
        self.title_label.setStyleSheet(f"color: {neon_blue};")

        # 关闭按钮悬停红色警告色
        self.close_btn.setStyleSheet("""
            TransparentToolButton { border-radius: 4px; padding: 4px; }
            TransparentToolButton:hover { background-color: rgba(255, 60, 60, 0.2); }
        """)

        self.setStyleSheet(f"""
            QWidget#PropertyCard {{
                background-color: {bg_color};
                border-top: 2px solid {neon_blue};
                border-left: 1px solid #2d2d2d;
                border-right: 1px solid #2d2d2d;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }}
        """)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._custom_opacity)
        if self._last_rect != self.rect():
            self._border_path = QPainterPath()
            self._border_path.addRoundedRect(QtCore.QRectF(self.rect()), 14, 14)
            self._last_rect = self.rect()
        p.fillPath(self._border_path, QBrush(QColor(30, 30, 30)))
        if self.is_active:
            grad = QLinearGradient(0, 0, self.width(), 0)
            grad.setColorAt(0, QColor(0, 162, 255, 0))
            grad.setColorAt(0.5, QColor(0, 162, 255, 180))
            grad.setColorAt(1, QColor(0, 162, 255, 0))
            p.setPen(QPen(grad, 4))
            p.drawLine(20, 1, self.width() - 20, 1)
        p.setPen(QPen(QColor(255, 255, 255, 5)))
        for i in range(0, self.height(), 5):
            p.drawLine(0, i, self.width(), i)
        super().paintEvent(event)


class PropertyPanel(QWidget):
    """
    终极版属性面板：
    - 支持点击“X”按钮关闭历史卡片。
    - 自动重排剩余卡片。
    - 极致流畅的 Resize 同步。
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
            # 绑定关闭信号
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

        # 1. 如果关闭的是活跃卡片，尝试寻找下一个可激活的节点
        is_active = (self._history_stack[-1] == card)
        self._history_stack.remove(card)
        card.hide()

        if is_active:
            if self._history_stack:
                # 将最后一张卡片作为新的活跃卡片
                next_card = self._history_stack[-1]
                self.update_properties(getattr(next_card, '_node_ref', None))
            else:
                # 没有任何卡片了，显示全局变量
                self.update_properties(None)
        else:
            # 只是关闭了背景中的卡片，重新排布剩余卡片位置
            self._sync_stack_layout(animate=True)

    def _sync_stack_layout(self, animate=True):
        if animate:
            self.anim_group.stop()
            self.anim_group.clear()

        self.stage.setUpdatesEnabled(False)
        w, h = self.stage.width(), self.stage.height()
        if w <= 10: w, h = self.width(), self.height()

        stack_count = len(self._history_stack)
        for i, card in enumerate(self._history_stack):
            card.show()
            card.raise_()
            level = (stack_count - 1) - i
            card.set_active(level == 0, level, animate=animate)
            target_y = i * self._header_reveal_h
            target_rect = QRect(0, target_y, w, h - target_y)

            if animate:
                anim = QPropertyAnimation(card, b"geometry")
                anim.setDuration(500)
                anim.setStartValue(card.geometry())
                anim.setEndValue(target_rect)
                curve = QEasingCurve.OutBack if level == 0 else QEasingCurve.OutQuart
                anim.setEasingCurve(curve)
                self.anim_group.addAnimation(anim)
            else:
                card.setGeometry(target_rect)

        if animate:
            self.anim_group.start()
        self.stage.setUpdatesEnabled(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._history_stack:
            self._sync_stack_layout(animate=False)

    def eventFilter(self, obj, event):
        if event.type() == event.MouseButtonPress:
            # 关键：如果点击的是卡片内的子按钮（如关闭按钮），不触发“飞升”切换逻辑
            if obj.childAt(event.pos()) == obj.findChild(TransparentToolButton):
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

    # ========================
    # 外部业务接口兼容 (保持)
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
                return [(p.name, p.label, p.type) for p in comp_ports]
        return [(p.name(), p.name(), ArgumentType.JSON) for p in
                (node.input_ports() if is_input else node.output_ports())]

    def get_node_description(self, node):
        if not node or "StatusDynamicNode_" not in node.model.type_: return ""
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
            self.global_panel_widget.delete_output_from_global_var(self.main_window, node,
                                                                                            port_name)

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
        for card in self._node_panel_cache.values(): card.deleteLater()
        self._node_panel_cache.clear()
        self._history_stack.clear()