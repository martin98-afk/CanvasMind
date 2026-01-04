# -*- coding: utf-8 -*-
from collections import OrderedDict
from NodeGraphQt import BaseNode
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QStackedWidget, QSizePolicy
from loguru import logger
from qfluentwidgets import SmoothScrollArea, TransparentDropDownToolButton

from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.scan_components import ComponentScanner
from app.widgets.side_dock_area.plugins.property_panel.flow_control_panel import FlowControlPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.global_panel import GlobalPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_list_panel import NodeListPanelWidget
from app.widgets.side_dock_area.plugins.property_panel.node_panel import NodePanelWidget


class PropertyPanel(QWidget):
    """
    优化后的主属性面板控件。
    采用对象池（LRU缓存）机制，解决大图表下的性能问题与界面闪烁。
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setMinimumWidth(280)

        # === 性能优化：面板缓存 ===
        # 使用 OrderedDict 实现 LRU 缓存，key 为 node.id，value 为 panel_widget
        self._node_panel_cache = OrderedDict()
        self._max_cache_size = 50  # 最大缓存50个节点面板，超过则释放最旧的

        self._global_panel_built = False
        self._allowed_update = False
        self.current_node = None

        # === UI 初始化 ===
        self.main_stacked = QStackedWidget(self)

        # 1. 节点展示区域 (Index 0)
        self._setup_node_panel()
        # 2. 全局变量展示区域 (Index 1)
        self._setup_global_panel()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_stacked)

        # 内部状态记录
        self._current_global_tab = 'custom'
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # === 显式定义外部接口需要的属性引用 ===
        self.node_list_panel_widget = None
        self.flow_control_panel_widget = None
        self.node_panel_widget = None
        self.global_panel_widget = None  # 全局变量面板

        # 兼容旧代码的属性占位
        self._column_list_widgets = {}
        self._text_edit_widgets = {}
        self._internal_nodes_card_expanded = {}
        self.segmented_widget = None  # 移至具体 Panel 内部管理
        self.stacked_widget = None

    def _setup_node_panel(self):
        """初始化节点面板容器"""
        self.node_container = QWidget()
        self.node_vbox = QVBoxLayout(self.node_container)
        self.node_vbox.setContentsMargins(0, 0, 0, 0)

        # 核心：使用 StackedWidget 管理缓存的节点面板
        self.node_panel_stack = QStackedWidget()
        self.node_vbox.addWidget(self.node_panel_stack)

        self.main_stacked.addWidget(self.node_container)  # index 0

    def _setup_global_panel(self):
        """初始化全局变量面板容器"""
        self.global_container = QWidget()
        self.global_vbox = QVBoxLayout(self.global_container)
        self.global_vbox.setContentsMargins(0, 0, 0, 0)
        self.main_stacked.addWidget(self.global_container)  # index 1

    def set_scrollbar(self, widget):
        """公共方法：为组件设置平滑滚动条"""
        scroll = SmoothScrollArea(self)
        scroll.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background-color: transparent; border: none;")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        scroll.setWidget(widget)
        return scroll

    def update_properties(self, node, node_changed=False):
        """核心更新接口"""
        if not self._allowed_update:
            return

        if not node:
            self.current_node = None
            self._show_global_variables_panel()
            self.main_stacked.setCurrentIndex(1)
            return

        self.main_stacked.setCurrentIndex(0)

        is_list = isinstance(node, list)
        cache_key = "MULTI_SELECT_PANEL" if is_list else node.id

        # 1. 获取或创建面板
        if cache_key in self._node_panel_cache:
            target_panel = self._node_panel_cache.pop(cache_key)
        else:
            target_panel = self._create_panel_instance(node)
            if not target_panel: return
            self.node_panel_stack.addWidget(target_panel)

            if len(self._node_panel_cache) >= self._max_cache_size:
                _, old_panel = self._node_panel_cache.popitem(last=False)
                # 清理被淘汰面板的引用，防止悬空指针
                if old_panel == self.node_list_panel_widget: self.node_list_panel_widget = None
                if old_panel == self.flow_control_panel_widget: self.flow_control_panel_widget = None
                if old_panel == self.node_panel_widget: self.node_panel_widget = None

                self.node_panel_stack.removeWidget(old_panel)
                old_panel.deleteLater()

        # 2. 更新缓存排序
        self._node_panel_cache[cache_key] = target_panel
        self.node_panel_stack.setCurrentWidget(target_panel)
        self.current_node = node if not is_list else None

        # === 3. 关键修复：同步外部访问的属性引用 ===
        if is_list:
            self.node_list_panel_widget = target_panel
        elif isinstance(node, ControlFlowBackdrop):
            self.flow_control_panel_widget = target_panel
        elif isinstance(node, BaseNode):
            self.node_panel_widget = target_panel

        # 4. 执行刷新
        if hasattr(target_panel, 'update_data'):
            target_panel.update_data(node)
        elif hasattr(target_panel, 'build_ui'):
            target_panel.build_ui(node)

    # === 4. 增加防御性代理方法 (防止面板未创建时调用报错) ===
    def update_node_list_content(self):
        """兼容外部 main_widget.py 的调用"""
        if self.node_list_panel_widget and hasattr(self.node_list_panel_widget, 'update_node_list_content'):
            self.node_list_panel_widget.update_node_list_content()

    def _refresh_node_vars_page(self):
        """兼容外部调用"""
        if self.global_panel_widget:
            self.global_panel_widget._refresh_node_vars_page()

    def _create_panel_instance(self, node):
        """工厂方法：根据节点类型创建对应的面板实例"""
        if isinstance(node, list):
            return NodeListPanelWidget(self.main_window, self, node)
        elif isinstance(node, ControlFlowBackdrop):
            return FlowControlPanelWidget(self.main_window, self, node)
        elif isinstance(node, BaseNode):
            return NodePanelWidget(self.main_window, self, node)
        return None

    def set_allowed_update(self, allowed: bool):
        """接口函数：设置是否允许刷新"""
        self._allowed_update = allowed

    def get_port_info(self, node, is_input=True):
        """接口函数：获取端口信息"""
        full_path = getattr(node, 'FULL_PATH', None)
        if full_path and hasattr(self.main_window, 'component_map'):
            comp_cls = self.main_window.component_map.get(full_path)
            if comp_cls:
                comp_ports = getattr(comp_cls, 'inputs' if is_input else 'outputs', [])
                port_dict = {p.name(): p for p in (node.input_ports() if is_input else node.output_ports())}
                result = []
                for comp_def in comp_ports:
                    port_name = comp_def.name
                    result.append((port_name, comp_def.label, comp_def.type))
                # 补充动态端口
                for port in (node.input_ports() if is_input else node.output_ports()):
                    if port.name() not in [r[0] for r in result]:
                        result.append((port.name(), port.name(), ArgumentType.JSON))
                return result

        if node.has_property(f"{'input' if is_input else 'output'}_ports"):
            ports = node.input_ports() if is_input else node.output_ports()
            port_defs = node.get_property(f"{'input' if is_input else 'output'}_ports")
            type_dict = {item.value: item for item in ArgumentType}
            return [(p.name(), p.name(), type_dict[pd["type"]]) for p, pd in zip(ports, port_defs)]
        else:
            return [(p.name(), p.name(), ArgumentType.JSON) for p in
                    (node.input_ports() if is_input else node.output_ports())]

    def get_node_description(self, node):
        """接口函数：获取节点描述"""
        if not node or "StatusDynamicNode_" not in node.model.type_:
            return ""
        comp_cls = ComponentScanner().get_component_by_uuid(node.uuid)
        return comp_cls.description if comp_cls else ""

    def _show_global_variables_panel(self):
        """展示全局变量面板（懒加载）"""
        if not self._global_panel_built:
            if not hasattr(self, 'global_panel_widget') or not self.global_panel_widget:
                self.global_panel_widget = GlobalPanelWidget(self.main_window, self, self.global_vbox)
            self.global_panel_widget.build_ui()
            self._global_panel_built = True

    # ========================
    # 全局变量与外部组件交互代理 (保留原有全部接口)
    # ========================
    def _on_global_variables_changed(self, var_type, var_name, action):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.on_global_variables_changed(var_type, var_name, action)

    def _refresh_node_vars_page(self):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget._refresh_node_vars_page()

    def _copy_as_expression(self, prefix, var_name):
        if hasattr(self, 'global_panel_widget') and self.global_panel_widget:
            self.global_panel_widget.copy_as_expression(prefix, var_name)

    def _add_output_to_global_variable(self, node, port_name):
        self._show_global_variables_panel()
        self.global_panel_widget.add_output_to_global_var(self.main_window, node, port_name)

    def _delete_output_from_global_variable(self, node, port_name):
        if hasattr(self, 'global_panel_widget'):
            self.global_panel_widget.delete_output_from_global_var(self.main_window, node, port_name)

    def _is_output_in_global_variable(self, node, port_name):
        self._show_global_variables_panel()
        return self.global_panel_widget.is_output_in_global_var(self.main_window, node, port_name)

    def _delete_custom_variable(self, var_name, var_type):
        if self.global_panel_widget: self.global_panel_widget.delete_variable(var_type, var_name)

    def _add_new_custom_variable(self):
        if self.global_panel_widget: self.global_panel_widget.add_new_custom_variable()

    def _edit_custom_variable(self, var_name, current_value):
        if self.global_panel_widget: self.global_panel_widget.edit_custom_variable(var_name, current_value)

    def _locate_node_by_variable_name(self, var_name):
        return self.global_panel_widget.locate_node_by_name(var_name) if self.global_panel_widget else None

    def get_current_execution_order(self):
        # 此时需要从缓存中找到那个唯一的 ListPanel 实例
        panel = self._node_panel_cache.get("MULTI_SELECT_PANEL")
        return panel.get_current_order() if panel else []

    def reset_current_components(self):
        panel = self._node_panel_cache.get("MULTI_SELECT_PANEL")
        if panel: panel.reset_components()

    def _clear_node_layout(self):
        """保留方法名兼容，现在主要用于清空缓存（如切换图表时）"""
        for panel in self._node_panel_cache.values():
            self.node_panel_stack.removeWidget(panel)
            panel.deleteLater()
        self._node_panel_cache.clear()
        self._column_list_widgets.clear()
        self._text_edit_widgets.clear()