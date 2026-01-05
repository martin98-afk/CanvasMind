# -*- coding: utf-8 -*-
import os
import re
from collections import OrderedDict
from NodeGraphQt import BaseNode
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect, QParallelAnimationGroup, QEasingCurve, QTimer, pyqtProperty
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QStyleOption, QStyle,
                             QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QFrame)
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPen, QFont, QPainterPath
from loguru import logger
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
    极致科技感卡片：
    - 采用 3D 深度渲染及磨砂玻璃质感
    - 独立属性控制透明度，支持平滑视差切换
    """

    def __init__(self, parent=None, title="Unknown Node", icon=FluentIcon.DEVELOPER_TOOLS):
        super().__init__(parent)
        self.is_active = False
        self._custom_opacity = 1.0
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("PropertyCard")

        # 容器布局
        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)

        # 1. 顶部 HUD 区域 (露出点)
        self.header_hud = QWidget()
        self.header_hud.setFixedHeight(45)
        header_layout = QHBoxLayout(self.header_hud)
        header_layout.setContentsMargins(18, 0, 18, 0)

        self.icon_widget = IconWidget(icon, self.header_hud)
        self.icon_widget.setFixedSize(18, 18)

        self.title_label = StrongBodyLabel(title, self.header_hud)
        self.title_label.setFont(QFont("Segoe UI Semibold", 10))

        header_layout.addWidget(self.icon_widget)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.card_layout.addWidget(self.header_hud)

        # 2. 核心内容区域
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

    def set_active(self, active: bool, level: int = 0):
        self.is_active = active
        # 活跃层级动画：0为最前
        target_op = 1.0 if active else max(0.4, 1.0 - level * 0.25)
        self.op_ani = QPropertyAnimation(self, b"cardOpacity")
        self.op_ani.setDuration(450)
        self.op_ani.setEndValue(target_op)
        self.op_ani.setEasingCurve(QEasingCurve.OutQuint)
        self.op_ani.start()
        self.update_style()

    def update_style(self):
        neon_blue = "#00a2ff" if self.is_active else "#666666"
        bg_color = "#1e1e1e" if self.is_active else "#151515"

        self.title_label.setStyleSheet(f"color: {neon_blue};")
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

        # 绘制背景实体，防止透视叠加
        path = QPainterPath()
        path.addRoundedRect(QtCore.QRectF(self.rect()), 14, 14)
        p.fillPath(path, QBrush(QColor(32, 32, 32)))

        # 如果活跃，绘制顶部流光
        if self.is_active:
            grad = QLinearGradient(0, 0, self.width(), 0)
            grad.setColorAt(0, QColor(0, 162, 255, 0))
            grad.setColorAt(0.5, QColor(0, 162, 255, 200))
            grad.setColorAt(1, QColor(0, 162, 255, 0))
            p.setPen(QPen(grad, 4))
            p.drawLine(20, 1, self.width() - 20, 1)

        # 数字化网格/扫描线 (提升科技感)
        p.setPen(QPen(QColor(255, 255, 255, 4)))
        for i in range(0, self.height(), 4):
            p.drawLine(0, i, self.width(), i)

        super().paintEvent(event)


class PropertyPanel(QWidget):
    """
    终极版属性面板：
    - 强制高度约束，适配 Splitter 展开。
    - 3 级 Parallax 堆叠 + 弹性位移。
    - 全局面板 & 节点面板 统一视窗管理。
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        # === 核心物理约束 (修复你的 Splitter 问题) ===
        self.setMinimumWidth(280)
        self.setMinimumHeight(250)  # 确保三层堆叠时有足够的垂直呼吸空间

        # === 状态核心 ===
        self._node_panel_cache = OrderedDict()
        self._max_cache_size = 50
        self._history_stack = []
        self._allowed_update = False
        self._global_panel_built = False
        self.current_node = None

        # === 视觉基调 ===
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("UltimatePropertyPanel")
        self.setStyleSheet("#UltimatePropertyPanel { background-color: transparent; }")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 容器舞台
        self.stage = QWidget()
        self.main_layout.addWidget(self.stage)

        # 外部引用
        self.node_list_panel_widget = None
        self.flow_control_panel_widget = None
        self.node_panel_widget = None
        self.global_panel_widget = None

        # 动画引擎
        self.anim_group = QParallelAnimationGroup(self)
        self._header_reveal_h = 45

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def update_properties(self, node, node_changed=False):
        """主入口逻辑"""
        if not self._allowed_update:
            return

        # 1. 唯一 Cache Key 计算
        if node is None:
            cache_key = "GLOBAL_DASHBOARD"
        elif isinstance(node, list):
            cache_key = "MULTI_LIST_VIEW"
        else:
            cache_key = node.id

        # 2. 调度或新建卡片
        if cache_key in self._node_panel_cache:
            target_card = self._node_panel_cache[cache_key]
        else:
            target_card = self._create_futuristic_card(node, cache_key)
            if not target_card: return
            self._node_panel_cache[cache_key] = target_card
            target_card.installEventFilter(self)

            if len(self._node_panel_cache) > self._max_cache_size:
                _, old_c = self._node_panel_cache.popitem(last=False)
                if old_c in self._history_stack: self._history_stack.remove(old_c)
                old_c.deleteLater()

        # 3. 历史栈管理（最近选中的移到最前/最后）
        if target_card in self._history_stack:
            self._history_stack.remove(target_card)
        self._history_stack.append(target_card)

        if len(self._history_stack) > 3:
            oldest = self._history_stack.pop(0)
            oldest.hide()

        # 4. 刷新业务数据
        self._refresh_inner_data(target_card, node, cache_key)
        self.current_node = node if not isinstance(node, list) else None

        # 5. 执行 3D 堆叠动画
        self._run_stack_animation()

    def _create_futuristic_card(self, node, key):
        """工厂方法：构建卡片并插入业务 UI"""
        title, icon = self._get_metadata(node, key)
        card = FuturisticCard(self.stage, title=title, icon=icon)

        # 核心：确保 Widget 被添加到 card.content_layout 中
        if key == "GLOBAL_DASHBOARD":
            # 兼容逻辑类版本的 GlobalPanelWidget
            self.global_panel_widget = GlobalPanelWidget(self.main_window, self, card.content_layout)
            card._logic = self.global_panel_widget
        elif key == "MULTI_LIST_VIEW":
            logic = NodeListPanelWidget(self.main_window, self, node)
            card.content_layout.addWidget(logic)
            card._logic = logic
        elif isinstance(node, ControlFlowBackdrop):
            logic = FlowControlPanelWidget(self.main_window, self, node)
            card.content_layout.addWidget(logic)
            card._logic = logic
        else:
            logic = NodePanelWidget(self.main_window, self, node)
            card.content_layout.addWidget(logic)
            card._logic = logic

        card._node_ref = node
        return card

    def _get_metadata(self, node, key):
        if key == "GLOBAL_DASHBOARD": return "全局变量", FluentIcon.GLOBE
        if key == "MULTI_LIST_VIEW": return f"连通图列表", FluentIcon.IOT
        if isinstance(node, ControlFlowBackdrop): return node.NODE_NAME, FluentIcon.SYNC
        return node.name(), FluentIcon.INFO

    def _refresh_inner_data(self, card, node, key):
        """下发增量更新指令"""
        if key == "GLOBAL_DASHBOARD":
            card._logic.build_ui()
            self._global_panel_built = True
        else:
            # 更新 PropertyPanel 自身引用，确保 main_widget 指向当前活跃面板
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

    def _run_stack_animation(self):
        """
        极致视差动画：
        - 越新的卡片越靠下（Y轴大），露出底层卡片头部。
        - 顶层卡片进入时带有 Back 弹性。
        """
        self.anim_group.stop()
        self.anim_group.clear()

        w, h = self.stage.width(), self.stage.height()
        if w <= 10: w, h = self.width(), self.height()

        stack_size = len(self._history_stack)
        for i, card in enumerate(self._history_stack):
            card.show()
            card.raise_()

            # level: 0位最前
            level = (stack_size - 1) - i
            card.set_active(level == 0, level)

            # 坐标算法：i=0时Y=0, i=2时Y=90。顶层下移，底部露出。
            target_y = i * self._header_reveal_h
            target_rect = QRect(0, target_y, w, h - target_y)

            anim = QPropertyAnimation(card, b"geometry")
            anim.setDuration(500)
            anim.setStartValue(card.geometry())
            anim.setEndValue(target_rect)

            # 只有活跃卡片使用弹性入场，历史卡片平滑移动
            curve = QEasingCurve.OutBack if level == 0 else QEasingCurve.OutQuart
            anim.setEasingCurve(curve)
            self.anim_group.addAnimation(anim)

        self.anim_group.start()

    def eventFilter(self, obj, event):
        """极致交互：点击任何露出的 HUD 区域实现飞升"""
        if event.type() == event.MouseButtonPress:
            # 判断点击的是否是背景中的历史卡片
            if obj in self._history_stack and self._history_stack[-1] != obj:
                if 0 <= event.pos().y() <= self._header_reveal_h:
                    self.update_properties(getattr(obj, '_node_ref', None))
                    return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._history_stack:
            # 延迟刷新坐标，确保容器大小已稳定
            QTimer.singleShot(0, self._run_stack_animation)

    # ========================
    # 外部业务接口兼容 (全保留)
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