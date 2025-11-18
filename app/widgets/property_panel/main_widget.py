# -*- coding: utf-8 -*-
import re

from NodeGraphQt import BaseNode
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget, \
    QStackedWidget, QSizePolicy
from loguru import logger
from qfluentwidgets import CardWidget, SmoothScrollArea, InfoBar, InfoBarPosition, TransparentDropDownToolButton

from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.utils.utils import serialize_for_json
from app.widgets.property_panel.node_panel import NodePanelWidget
from app.widgets.property_panel.flow_control_panel import FlowControlPanelWidget
from app.widgets.property_panel.global_panel import GlobalPanelWidget
from app.widgets.property_panel.node_list_panel import NodeListPanelWidget


class ExpandableCardWidget(CardWidget):
    """自定义卡片，用于在大小改变时发出信号"""
    sizeChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sizeChanged.emit()


class PropertyPanel(CardWidget):
    """
    主属性面板控件，负责协调和管理各个子面板模块。
    该控件现在主要负责：
    1. 初始化主布局和堆叠控件。
    2. 管理当前显示的节点和面板状态。
    3. 提供公共的更新接口（update_properties）。
    4. 协调各子模块的交互。
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setMinimumWidth(280)

        # === 全局变量缓存 (可能仍需在主控件维护) ===
        self._custom_var_cards = {}
        self._node_var_cards = {}
        self._env_var_cards = {}
        self._global_panel_built = False
        self._allowed_update = False

        # === 顶层堆叠：两个独立的 ScrollArea ===
        self.main_stacked = QStackedWidget(self)

        # --- 节点面板（带独立 ScrollArea）---
        self._setup_node_panel()
        # --- 全局变量面板（带独立 ScrollArea）---
        self._setup_global_panel()

        # --- 主布局 ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_stacked)

        self.current_node = None
        self._user_execution_order = {}
        self._column_list_widgets = {}
        self._text_edit_widgets = {}
        self.segmented_widget = None
        self.stacked_widget = None
        self._current_global_tab = 'custom'
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # --- 用于存储内部节点卡片状态 ---
        self._internal_nodes_card_expanded = {}

    def _setup_node_panel(self):
        """初始化节点面板的滚动区域和容器"""
        node_scroll = SmoothScrollArea(self)
        node_scroll.viewport().setStyleSheet("background-color: transparent;")
        node_scroll.setWidgetResizable(True)
        node_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        node_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.node_container = QWidget()
        self.node_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.node_vbox = QVBoxLayout(self.node_container)
        self.node_vbox.setContentsMargins(10, 10, 10, 10)
        self.node_vbox.setSpacing(8)

        node_scroll.setWidget(self.node_container)
        self.main_stacked.addWidget(node_scroll)  # index 0

    def _setup_global_panel(self):
        """初始化全局变量面板的滚动区域和容器"""
        global_scroll = SmoothScrollArea(self)
        global_scroll.viewport().setStyleSheet("background-color: transparent;")
        global_scroll.setWidgetResizable(True)
        global_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        global_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.global_container = QWidget()
        self.global_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.global_vbox = QVBoxLayout(self.global_container)
        self.global_vbox.setContentsMargins(10, 10, 10, 10)
        self.global_vbox.setSpacing(8)

        global_scroll.setWidget(self.global_container)
        self.main_stacked.addWidget(global_scroll)  # index 1

    def set_allowed_update(self, allowed: bool):
        self._allowed_update = allowed

    # ========================
    # 全局变量信号响应（增量更新）
    # ========================
    def _on_global_variables_changed(self, var_type: str, var_name: str, action: str):
        """
        原有方法名，现在作为代理方法，将信号转发给 GlobalPanelWidget。
        """
        # 委托给 GlobalPanelWidget 处理
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            # 调用子模块的处理方法
            self.global_panel_widget.on_global_variables_changed(var_type, var_name, action)

    # ========================
    # 节点面板相关
    # ========================
    def _clear_node_layout(self):
        """清理节点面板布局"""
        # 委托给 NodePanelWidget 或相关子面板处理
        # 清理主控件维护的缓存
        self._column_list_widgets.clear()
        self._text_edit_widgets.clear()
        self._internal_nodes_card_expanded.clear()
        # 清理主节点容器布局
        while self.node_vbox.count():
            child = self.node_vbox.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def get_port_info(self, node, is_input=True):
        """获取端口信息，此方法逻辑较为独立，可保留在此"""
        # === 优先通过 FULL_PATH 从 main_window.component_map 获取组件类 ===
        full_path = getattr(node, 'FULL_PATH', None)
        if full_path and hasattr(self.main_window, 'component_map'):
            comp_cls = self.main_window.component_map.get(full_path)
            if comp_cls:
                comp_ports = getattr(comp_cls, 'inputs' if is_input else 'outputs', [])
                port_dict = {p.name(): p for p in (node.input_ports() if is_input else node.output_ports())}
                result = []
                for comp_def in comp_ports:
                    port_name = comp_def.name
                    if port_name in port_dict:
                        result.append((port_name, comp_def.label, comp_def.type))
                    else:
                        result.append((port_name, comp_def.label, comp_def.type))
                # 补充动态端口（如有）
                for port in (node.input_ports() if is_input else node.output_ports()):
                    if port.name() not in [r[0] for r in result]:
                        result.append((port.name(), port.name(), ArgumentType.TEXT))
                return result
        # === 旧逻辑（兼容非动态节点）===
        if node.has_property(f"{'input' if is_input else 'output'}_ports"):
            ports = node.input_ports() if is_input else node.output_ports()
            port_defs = node.get_property(f"{'input' if is_input else 'output'}_ports")
            type_dict = {item.value: item for item in ArgumentType}
            return [(p.name(), p.name(), type_dict[pd["type"]]) for p, pd in zip(ports, port_defs)]
        else:
            return [(p.name(), p.name(), ArgumentType.TEXT) for p in
                    (node.input_ports() if is_input else node.output_ports())]

    def update_properties(self, node, node_changed=False):
        """核心更新方法，根据节点类型选择对应的子面板进行更新"""
        if not self._allowed_update:
            return

        is_backdrop_change = (
                node is not None
                and node is self.current_node
                and isinstance(node, ControlFlowBackdrop)
                and not node_changed
        )
        if is_backdrop_change:
            # 尝试更新现有Backdrop的状态
            # 委托给 FlowControlPanelWidget 处理
            if hasattr(self, 'flow_control_panel_widget') and self.flow_control_panel_widget:
                try:
                    self.flow_control_panel_widget.update_backdrop_data(node)
                    return
                except Exception as e:
                    logger.warning(f"更新现有Backdrop状态失败: {e}")
                    pass  # 继续执行全量更新

        # 原有的全量更新逻辑
        current_segment = None
        if self.segmented_widget:
            current_segment = self.segmented_widget.currentRouteKey()
        if hasattr(self, 'global_segmented'):
            self._current_global_tab = self.global_segmented.currentRouteKey()

        if not node:
            self.current_node = node
            self._show_global_variables_panel()
            self.main_stacked.setCurrentIndex(1)
        else:
            # 清理并构建节点面板
            self._clear_node_layout()

            # 根据节点类型创建对应的子面板
            if isinstance(node, ControlFlowBackdrop):
                self.current_node = node
                self._update_control_flow_properties(node, current_segment)
            elif isinstance(node, list):
                self._build_node_list_ui(node)
            elif isinstance(node, BaseNode):
                self.current_node = node
                self._build_node_ui(node, current_segment)

            self.main_stacked.setCurrentIndex(0)

    def _update_control_flow_properties(self, node, current_segment=None):
        """更新控制流节点属性"""
        # 委托给 FlowControlPanelWidget
        if not hasattr(self, 'flow_control_panel_widget') or not self.flow_control_panel_widget:
            self.flow_control_panel_widget = FlowControlPanelWidget(self.main_window, self, self.node_vbox)
        self.flow_control_panel_widget.build_ui(node, current_segment)

    def _build_node_list_ui(self, nodes):
        """构建节点列表UI"""
        # 委托给 NodeListPanelWidget
        if not hasattr(self, 'node_list_panel_widget') or not self.node_list_panel_widget:
            self.node_list_panel_widget = NodeListPanelWidget(self.main_window, self, self.node_vbox)
        self.node_list_panel_widget.build_ui(nodes)

    def _build_node_ui(self, node, current_segment=None):
        """构建普通节点UI"""
        # 委托给 NodePanelWidget
        if not hasattr(self, 'node_panel_widget') or not self.node_panel_widget:
            self.node_panel_widget = NodePanelWidget(self.main_window, self, self.node_vbox)
        self.node_panel_widget.build_ui(node, current_segment)

    def get_current_execution_order(self):
        """获取当前执行顺序"""
        if hasattr(self, 'node_list_panel_widget') and self.node_list_panel_widget:
            return self.node_list_panel_widget.get_current_order()
        return []

    def reset_current_components(self):
        """重置组件列表"""
        if hasattr(self, 'node_list_panel_widget') and self.node_list_panel_widget:
            self.node_list_panel_widget.reset_components()

    def get_node_description(self, node):
        """获取节点描述"""
        if hasattr(node, 'component_class'):
            return getattr(node.component_class, 'description', '')
        try:
            return node.model.get_property('description')
        except KeyError:
            return ''

    # ========================
    # 全局变量面板（只构建一次）
    # ========================
    def _show_global_variables_panel(self):
        """构建全局变量面板"""
        if self._global_panel_built:
            return
        # 委托给 GlobalPanelWidget
        if not hasattr(self, 'global_panel_widget') or not self.global_panel_widget:
            self.global_panel_widget = GlobalPanelWidget(self.main_window, self, self.global_vbox)
        self.global_panel_widget.build_ui()
        self._global_panel_built = True

    # ========================
    # 全局变量操作
    # ========================
    # 这些方法也可以委托给 GlobalPanelWidget
    def _delete_custom_variable(self, var_name: str, var_type: str):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.delete_variable(var_type, var_name)

    def _on_node_var_strategy_changed(self, text: str, button: TransparentDropDownToolButton):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.change_node_var_strategy(text, button)

    def _add_new_custom_variable(self):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.add_new_custom_variable()

    def _add_new_env_variable(self):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.add_new_env_variable()

    def _delete_env_variable(self, key: str):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.delete_env_variable(key)

    def _copy_as_expression(self, prefix: str, var_name: str):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.copy_as_expression(prefix, var_name)

    def _edit_custom_variable(self, var_name: str, current_value):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.edit_custom_variable(var_name, current_value)

    def _edit_env_variable(self, key: str, current_value):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.edit_env_variable(key, current_value)

    # 其他辅助方法（如 _locate_node_by_variable_name, _add_output_to_global_variable 等）
    # 也可以根据需要委托给 GlobalPanelWidget 或其他子模块
    def _locate_node_by_variable_name(self, var_name: str):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            return self.global_panel_widget.locate_node_by_name(var_name)
        # 否则返回 None 或记录日志
        logger.warning(f"GlobalPanelWidget not found, cannot locate node for {var_name}")
        return None

    def _add_output_to_global_variable(self, node, port_name: str):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.add_output_to_global_var(self.main_window, node, port_name)
        else:
            # 原有逻辑的后备实现（如果 GlobalPanelWidget 未初始化）
            value = node._output_values.get(port_name)
            if value is None:
                InfoBar.warning(
                    title="警告",
                    content=f"端口 {port_name} 当前无有效输出值",
                    parent=self.main_window,
                    position=InfoBarPosition.TOP_RIGHT
                )
                return
            safe_node_name = re.sub(r'\s+', '_', node.name())
            var_name = f"{safe_node_name}_{port_name}"
            self.main_window.global_variables.set_output(
                node_id=safe_node_name, output_name=port_name, output_value=serialize_for_json(value)
            )
            if hasattr(node, "refresh_node_outports"):
                QtCore.QTimer.singleShot(100, node.refresh_node_outports)
            if hasattr(node, "_sync_outputs_ports"):
                QtCore.QTimer.singleShot(100, node._sync_outputs_ports)
            self.main_window.global_variables_changed.emit("node_vars", var_name, "add")
            InfoBar.success(
                title="成功",
                content=f"已添加全局变量：{var_name}",
                parent=self.main_window,
                position=InfoBarPosition.TOP_RIGHT
            )

    def _refresh_node_vars_page(self):
        """
        代理方法：调用 GlobalPanelWidget 的 _refresh_node_vars_page 方法。
        用于修复外部调用（如 node_list_executor.py）导致的 AttributeError。
        """
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            try:
                # 调用子模块的刷新方法
                self.global_panel_widget._refresh_node_vars_page()
            except AttributeError:
                # 如果子模块中也没有此方法（理论上不应该发生），则记录错误
                logger.error("GlobalPanelWidget is missing '_refresh_node_vars_page' method.")
        else:
            # 如果子模块未初始化，记录警告
            logger.warning("GlobalPanelWidget not initialized, cannot refresh node vars page.")