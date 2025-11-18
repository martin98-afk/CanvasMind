# -*- coding: utf-8 -*-
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
from NodeGraphQt import BaseNode
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QFrame, QFileDialog, QListWidgetItem, QWidget, \
    QStackedWidget, QHBoxLayout, QApplication, QSizePolicy
from loguru import logger
from qfluentwidgets import CardWidget, BodyLabel, PushButton, ListWidget, SmoothScrollArea, SegmentedWidget, \
    ProgressBar, FluentIcon, InfoBar, InfoBarPosition, TransparentToolButton, RoundMenu, Action, TransparentPushButton, \
    TransparentDropDownToolButton, SubtitleLabel, CaptionLabel, StrongBodyLabel

from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.utils.utils import serialize_for_json, get_icon, canvas_file_dump_path, topological_sort
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit
from app.widgets.dialog_widget.custom_messagebox import CustomTwoInputDialog
from app.widgets.node_widget.longtext_dialog import LongTextEditorDialog
from app.widgets.tree_widget.variable_tree import VariableTreeWidget


# --- 添加一个自定义信号的类，用于在卡片大小改变时通知布局更新 ---
class ExpandableCardWidget(CardWidget):
    sizeChanged = pyqtSignal()  # 自定义信号

    def __init__(self, parent=None):
        super().__init__(parent)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sizeChanged.emit()  # 当大小改变时发射信号


class PropertyPanel(CardWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setMinimumWidth(280)
        # === 全局变量缓存 ===
        self._custom_var_cards = {}
        self._node_var_cards = {}
        self._env_var_cards = {}
        self._global_panel_built = False
        self._allowed_update = False
        # === 顶层堆叠：两个独立的 ScrollArea ===
        self.main_stacked = QStackedWidget(self)
        # --- 节点面板（带独立 ScrollArea）---
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
        # --- 全局变量面板（带独立 ScrollArea）---
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

    def set_allowed_update(self, allowed: bool):
        self._allowed_update = allowed

    # ========================
    # 全局变量信号响应（增量更新）
    # ========================
    def _on_global_variables_changed(self, var_type: str, var_name: str, action: str):
        if not self._global_panel_built:
            return
        global_vars = self.main_window.global_variables
        if var_type == "node_vars":
            if action == "add" or action == "update":
                if var_name not in self._node_var_cards:
                    if hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
                        card = self._create_variable_card(var_name, global_vars.node_vars[var_name])
                        self.node_vars_layout.addWidget(card)
                        self._node_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._node_var_cards:
                    card = self._node_var_cards.pop(var_name)
                    card.deleteLater()
            elif action == "clear":
                global_vars.clear_node_vars(var_name)
                self._refresh_node_vars_page()
        elif var_type == "custom":
            if action == "add" or action == "update":
                if var_name not in self._custom_var_cards:
                    if hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                        card = self._create_dict_row(var_name, global_vars.custom[var_name].value)
                        self.custom_vars_layout.addWidget(card)
                        self._custom_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._custom_var_cards:
                    card = self._custom_var_cards.pop(var_name)
                    card.deleteLater()
        elif var_type == "env":
            if action == "add" or action == "update":
                if var_name not in self._env_var_cards:
                    if hasattr(global_vars, 'env'):
                        value = getattr(global_vars.env, var_name, None)
                        if value is not None:
                            card = self._create_env_var_row(var_name, value)
                            self.env_vars_layout.addWidget(card)
                            self._env_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._env_var_cards:
                    card = self._env_var_cards.pop(var_name)
                    card.deleteLater()

    # ========================
    # 节点面板相关
    # ========================
    def _clear_node_layout(self):
        self._column_list_widgets.clear()
        self._text_edit_widgets.clear()
        # 清理内部节点卡片状态
        self._internal_nodes_card_expanded.clear()
        while self.node_vbox.count():
            child = self.node_vbox.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def get_port_info(self, node, is_input=True):
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
        if not self._allowed_update:
            return

        is_backdrop_change = (
                node is not None
                and node is self.current_node
                # 检查是否为 ControlFlowBackdrop 且是同一个实例
                and isinstance(node, ControlFlowBackdrop)
                and not node_changed
        )

        if is_backdrop_change:
            # 尝试更新现有Backdrop的状态
            try:
                self._update_existing_backdrop_data(node)
                return
            except Exception:
                pass

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
            if isinstance(node, ControlFlowBackdrop):
                self.current_node = node
                self._update_control_flow_properties(node, current_segment)
            elif isinstance(node, list):
                self._build_node_list_ui(node)
            elif isinstance(node, BaseNode):
                self.current_node = node
                self._build_node_ui(node, current_segment)
            self.main_stacked.setCurrentIndex(0)

    def _update_existing_backdrop_data(self, node):
        """
        尝试更新现有 ControlFlowBackdrop 的状态。
        如果成功更新（即找到了需要更新的UI组件），则返回 True。
        如果无法更新（例如UI组件未缓存），则返回 False。
        """
        # 检查是否有缓存的UI组件用于更新
        if not hasattr(self, '_backdrop_progress_label') or not hasattr(self, '_backdrop_progress_bar') or not hasattr(
                self, '_backdrop_internal_nodes_list'):
            # 如果没有缓存的组件，无法进行局部更新，返回 False
            return False

        # 更新进度信息
        flow_type = getattr(node, 'TYPE', 'unknown')
        current = node.model.get_property('current_index')
        if flow_type == "loop":
            loop_mode = node.model.get_property("loop_mode")
            if loop_mode == 'count':
                total = node.model.get_property("loop_nums")
            else:
                total = node.model.get_property("max_iterations")
        elif flow_type == "iterate":
            input_data = []
            for input_port in node.input_ports():
                connected = input_port.connected_ports()
                if connected:
                    if len(connected) == 1:
                        upstream = connected[0]
                        value = upstream.node()._output_values.get(upstream.name())
                        input_data = value
                    else:
                        input_data.extend(
                            [upstream.node()._output_values.get(upstream.name()) for upstream in connected]
                        )
            if not isinstance(input_data, (list, tuple, dict)):
                input_data = [input_data]
            total = len(input_data)
        else:
            total = 0

        # 更新标签文本
        if self._backdrop_progress_label:
            self._backdrop_progress_label.setText(f"进度: {current}/{total}")

        # 更新进度条值
        if self._backdrop_progress_bar:
            progress_value = int(current / max(1, total) * 100) if total > 0 else 0
            self._backdrop_progress_bar.setValue(progress_value)

        # 更新内部节点列表
        if self._backdrop_internal_nodes_list:
            _, _, internal_nodes = node.get_nodes()
            # 仅更新列表项的文本，不重建整个列表
            list_widget = self._backdrop_internal_nodes_list
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if i < len(internal_nodes):  # 防止索引越界
                    n = internal_nodes[i]
                    status = self.main_window.get_node_status(n)
                    status_text = {
                        "running": "🟡 运行中",
                        "success": "🟢 成功",
                        "failed": "🔴 失败",
                        "unrun": "⚪ 未运行",
                        "pending": "🔵 待运行"
                    }.get(status, status)
                    item.setText(f"{status_text} - {n.name()}")
                else:

                    item.setText("")  # 或者 item.setHidden(True)
                    # 注意：移除项可能需要更复杂的逻辑，这里保持数量不变仅更新文本
            # 如果节点数量增加了，需要添加新的项
            if len(internal_nodes) > list_widget.count():
                if list_widget.count() != len(internal_nodes):
                    return False  # 长度不匹配，需要重新构建
        # 成功更新了UI组件
        return True

    def _build_node_list_ui(self, nodes):
        """
        清理并构建节点面板，支持基于节点交集的用户自定义执行顺序，并优化稳定性。
        规则：
        1. 节点集合完全相同的连通图，保持原有顺序和位置。
        2. 节点集合有交集但不完全相同的连通图，尝试在原位置附近重建（应用旧顺序，拓扑排序新节点）。
        3. 新增的、与任何历史连通图无交集的连通图，追加到末尾。
        4. 用户手动调整的顺序 (_user_execution_order) 会被应用和更新。
        """
        # 1. 获取当前连通分量
        new_components = topological_sort(nodes, split_components=True)
        if new_components is None:
            new_components = []
        logger.debug(f"New components from topological_sort: {[len(c) for c in new_components]}")

        # 2. 准备数据结构
        # 将 new_components 转换为 node_id 集合列表，方便后续比较
        new_node_sets = [set(n.id for n in comp) for comp in new_components]
        # 获取当前用户定义的顺序（key是排序过的node_id元组，value是按用户顺序排列的节点列表）
        current_user_order = self._user_execution_order.copy()

        # 3. 创建最终排序结果列表
        final_components = []
        processed_new_indices = set() # 记录已处理的新组件索引

        # 4. 遍历用户定义的顺序，尝试映射到新组件
        # 优先处理用户有明确顺序偏好的连通图
        for old_key_node_ids, old_ordered_nodes in current_user_order.items():
            topo_order = [n.id for n in old_ordered_nodes]
            old_node_set = set(old_key_node_ids)
            # 寻找与 old_node_set 有交集的 new_component
            overlaped_component_index = []
            overlaped_id = []
            for i, new_node_set in enumerate(new_node_sets):
                if i in processed_new_indices:
                    continue  # 跳过已匹配的新组件
                overlap = len(old_node_set & new_node_set)
                if overlap > 1:
                    # 存储第一个匹配想的节点id
                    for j, nid in enumerate(topo_order):
                        if nid in new_node_set:
                            overlaped_id.append(j)
                            overlaped_component_index.append(i)
                            break

            # 并将有交集的子连通图按照原拓扑排序的关系顺序进行添加
            overlaped_component_index = [overlaped_component_index[k] for k in np.argsort(overlaped_id)]

            if len(overlaped_component_index) > 0:
                for matched_new_idx in overlaped_component_index:
                    # 找到匹配项
                    matched_new_component = new_components[matched_new_idx]
                    # 记录为已处理
                    processed_new_indices.add(matched_new_idx)
                    final_components.append(matched_new_component)  # 添加拓扑排序后的组件

        # 5. 处理剩余未被映射的新组件（即新增的连通图）
        for i, comp in enumerate(new_components):
            if i not in processed_new_indices:
                final_components.append(comp) # 添加拓扑排序后的组件

        # 7. 重建UI
        self._clear_node_layout()
        title = BodyLabel(f"⏬ 连通图执行顺序")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.node_vbox.addWidget(title)

        # 主卡片
        nodes_card = CardWidget(self)
        nodes_layout = QVBoxLayout(nodes_card)
        nodes_layout.setContentsMargins(10, 10, 10, 10)

        title_btn_layout = QHBoxLayout()
        title = BodyLabel("连通图列表：")
        title_btn_layout.addWidget(title)
        title_btn_layout.addStretch()
        nodes_layout.addLayout(title_btn_layout)

        # 为每个连通分量创建单独的卡片并保存引用
        self._component_cards = []
        final_ordered_components = []
        for i in range(len(final_components)):
            # 此时 final_ordered_components[i] 已经是拓扑排序后的节点列表
            component_card, comp_order = self._create_component_card(nodes_layout, i, final_components)
            final_ordered_components.append(comp_order)
            self._component_cards.append(component_card)
        # 6. 更新当前组件列表
        self._current_components = final_ordered_components
        nodes_layout.addStretch(1)
        self.node_vbox.addWidget(nodes_card)
        self.node_vbox.addStretch(1)

        # 8. 更新 _user_execution_order 以反映当前最终的排序
        updated_user_order = {}
        for comp_nodes in final_ordered_components:
            if comp_nodes:
                node_ids = tuple(sorted(n.id for n in comp_nodes))
                # value 现在是拓扑排序后的节点列表
                updated_user_order[node_ids] = comp_nodes.copy()
        self._user_execution_order = updated_user_order
        logger.debug(f"Updated _user_execution_order keys: {list(self._user_execution_order.keys())}")

    def _create_component_card(self, parent_layout, index, components):
        """
        创建单个连通分量的卡片
        """
        component = components[index]
        topo_sorted_component = topological_sort(component, split_components=False)
        if topo_sorted_component is None:  # 理论上不应发生
            topo_sorted_component = component
        # --- 修改结束 ---

        component_card = CardWidget(self)
        component_layout = QVBoxLayout(component_card)
        component_layout.setContentsMargins(8, 8, 8, 8)

        # 连通分量标题行，包含名称和上下移动按钮
        header_layout = QHBoxLayout()
        component_title = BodyLabel(f"子连通图 {index + 1} ({len(topo_sorted_component)} 个节点)")
        header_layout.addWidget(component_title)

        # 上下移动按钮
        move_up_btn = TransparentToolButton(FluentIcon.UP)
        move_down_btn = TransparentToolButton(FluentIcon.DOWN)

        # 设置按钮的固定大小
        move_up_btn.setFixedSize(24, 24)
        move_down_btn.setFixedSize(24, 24)

        # 连接按钮信号
        move_up_btn.clicked.connect(lambda _, idx=index: self._move_component(idx, -1))
        move_down_btn.clicked.connect(lambda _, idx=index: self._move_component(idx, 1))

        # 禁用边界按钮
        if index == 0:  # 第一个组件，禁用上移按钮
            move_up_btn.setEnabled(False)
        if index == len(components) - 1:  # 最后一个组件，禁用下移按钮
            move_down_btn.setEnabled(False)

        header_layout.addWidget(move_up_btn)
        header_layout.addWidget(move_down_btn)
        component_layout.addLayout(header_layout)

        # 创建列表显示该连通分量的节点
        component_list = ListWidget(self)
        num_items = len(topo_sorted_component)  # 使用拓扑排序后的长度
        estimated_height_for_items = num_items * 40
        total_estimated_height = estimated_height_for_items
        component_list.setFixedHeight(total_estimated_height)

        # 存储节点对象，以便在双击时访问
        # 注意：现在存储的是拓扑排序后的节点列表
        self._component_nodes_list = getattr(self, '_component_nodes_list', {})
        list_identifier = f"component_{index}"
        self._component_nodes_list[list_identifier] = topo_sorted_component  # 存储拓扑排序后的列表

        # 遍历拓扑排序后的节点列表
        for n in topo_sorted_component:  # 使用 topo_sorted_component
            status = self.main_window.get_node_status(n)
            status_text = {
                "running": "🟡 运行中",
                "success": "🟢 成功",
                "failed": "🔴 失败",
                "unrun": "⚪ 未运行",
                "pending": "🔵 待运行"
            }.get(status, status)
            item_text = f"{status_text} - {n.name()}"
            item = QListWidgetItem(item_text)
            component_list.addItem(item)

        # --- 添加双击事件处理 ---
        def on_item_double_clicked(item):
            # 获取当前点击项的索引
            row = component_list.row(item)
            # 根据索引从存储的组件列表中获取对应的节点对象
            # 注意：现在 _component_nodes_list[list_identifier] 是拓扑排序后的
            if 0 <= row < len(topo_sorted_component):  # 使用 topo_sorted_component 长度
                node_to_center = topo_sorted_component[row]  # 从拓扑排序列表获取
                self.main_window.canvas_widget.zoom_to_nodes([node_to_center._view])

        # 连接双击信号到处理函数
        component_list.itemDoubleClicked.connect(on_item_double_clicked)
        # ------------------------

        component_layout.addWidget(component_list)
        parent_layout.addWidget(component_card)
        return component_card, topo_sorted_component

    def _move_component(self, index, direction):
        """
        移动连通分量的位置
        :param index: 当前组件索引
        :param direction: 移动方向，-1为上移，1为下移
        """
        if not hasattr(self, '_current_components') or not self._current_components or len(
                self._current_components) <= 1:
            return  # 没有组件或只有一个组件，无法移动

        # 执行移动操作
        if direction == -1 and index > 0:  # 上移
            # 交换组件数据
            self._current_components[index], self._current_components[index - 1] = \
                self._current_components[index - 1], self._current_components[index]
            # 交换组件卡片在列表中的位置
            self._component_cards[index], self._component_cards[index - 1] = \
                self._component_cards[index - 1], self._component_cards[index]
        elif direction == 1 and index < len(self._current_components) - 1:  # 下移
            # 交换组件数据
            self._current_components[index], self._current_components[index + 1] = \
                self._current_components[index + 1], self._current_components[index]
            # 交换组件卡片在列表中的位置
            self._component_cards[index], self._component_cards[index + 1] = \
                self._component_cards[index + 1], self._component_cards[index]
        else:
            return  # 无效移动

        # 重新排列组件卡片在布局中的位置
        self._rearrange_component_cards()
        # --- 保存用户自定义顺序 ---
        # 清空旧的用户顺序记录
        self._user_execution_order.clear()
        # 为当前排列的每个连通分量重新建立记录
        for comp_nodes in self._current_components:
            if comp_nodes:  # 确保组件非空
                node_ids = tuple(sorted(n.id for n in comp_nodes))  # 使用排序元组作为稳定键
                self._user_execution_order[node_ids] = comp_nodes.copy()  # 存储当前顺序

    def _rearrange_component_cards(self):
        """
        重新排列组件卡片在布局中的位置
        """
        # 获取主布局中的内容布局（跳过标题行）
        nodes_card = self.node_vbox.itemAt(1).widget()  # 假设第一个是nodes_card
        nodes_layout = nodes_card.layout()

        # 清空内容布局（除了标题）
        for i in reversed(range(nodes_layout.count())):
            if i > 0:  # 保留标题行
                item = nodes_layout.itemAt(i)
                if item.widget() and item.widget() != nodes_layout.itemAt(0).widget():
                    nodes_layout.removeItem(item)

        # 按照新的顺序重新添加组件卡片
        for i, component_card in enumerate(self._component_cards):
            # 更新标题和按钮状态
            self._update_card_header(component_card, i)
            nodes_layout.addWidget(component_card)

    def _update_card_header(self, component_card, new_index):
        """
        更新组件卡片的标题和按钮状态
        """
        # 获取布局中的标题标签和按钮
        component_layout = component_card.layout()
        header_layout = component_layout.itemAt(0).layout()  # 假设标题在第一个位置

        # 找到标题标签并更新文本
        title_label = None
        up_btn = None
        down_btn = None

        for i in range(header_layout.count()):
            widget = header_layout.itemAt(i).widget()
            if isinstance(widget, BodyLabel):
                title_label = widget
            elif isinstance(widget, TransparentToolButton):
                if widget._icon == FluentIcon.UP:
                    up_btn = widget
                elif widget._icon == FluentIcon.DOWN:
                    down_btn = widget

        # 更新标题文本
        if title_label:
            current_component = self._current_components[new_index]
            title_label.setText(f"子联通图 {new_index + 1} ({len(current_component)} 个节点)")

        # 更新按钮状态
        if up_btn:
            up_btn.setEnabled(new_index > 0)
        if down_btn:
            down_btn.setEnabled(new_index < len(self._current_components) - 1)

        # 重新连接按钮信号，传递新的索引
        if up_btn:
            up_btn.disconnect()  # 先断开旧连接
            up_btn.clicked.connect(lambda _, idx=new_index: self._move_component(idx, -1))
        if down_btn:
            down_btn.disconnect()  # 先断开旧连接
            down_btn.clicked.connect(lambda _, idx=new_index: self._move_component(idx, 1))

    def get_current_execution_order(self):
        """
        获取当前排列的节点执行顺序
        返回按当前顺序排列的所有节点列表
        """
        if not hasattr(self, '_current_components') or not self._current_components:
            return []

        # 将所有连通分量中的节点按当前顺序连接成一个列表
        execution_order = []
        for component in self._current_components:
            execution_order.extend(component)

        return execution_order

    def reset_current_components(self):
        """
        重置当前组件列表
        """
        self._current_components = []

    def _build_node_ui(self, node, current_segment=None):
        if not hasattr(node, '_input_values'):
            node._input_values = {}
        if not hasattr(node, 'column_select'):
            node.column_select = {}
        title = SubtitleLabel(f"📌 {node.name()}")
        title.setWordWrap(True)
        self.node_vbox.addWidget(title)
        description = self.get_node_description(node)
        if description and description.strip():
            desc_label = BodyLabel(f"📝 {description}")
            desc_label.setWordWrap(True)
            self.node_vbox.addWidget(desc_label)
        self._add_seperator(self.node_vbox)
        self.segmented_widget = SegmentedWidget(self)
        self.stacked_widget = QStackedWidget(self)
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)

        # 添加输入输出端口信息
        # 1. 判断按是否有输入输出端口
        has_input_ports = False
        has_output_ports = False

        # 方法1：通过 component_class（如果存在）
        if hasattr(node, 'component_class') and node.component_class:
            comp_cls = node.component_class
            has_input_ports = len(getattr(comp_cls, 'inputs', [])) > 0
            has_output_ports = len(getattr(comp_cls, 'outputs', [])) > 0
        # 方法2：兜底：用当前实例端口（适用于非动态节点）
        else:
            has_input_ports = len(node.input_ports()) > 0
            has_output_ports = len(node.output_ports()) > 0
        # 2. 如果有输入输出端口则进行构建
        if has_input_ports:
            self.segmented_widget.addItem('input', '输入端口')
            self._populate_input_ports(node, input_layout)
            input_layout.addStretch(1)
            self.stacked_widget.addWidget(input_widget)

        if has_output_ports:
            self.segmented_widget.addItem('output', '输出端口')
            self._populate_output_ports(node, output_layout)
            output_layout.addStretch(1)
            self.stacked_widget.addWidget(output_widget)

        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)
        self.node_vbox.addWidget(self.segmented_widget)
        self.node_vbox.addWidget(self.stacked_widget)
        if current_segment in ['input', 'output']:
            self.segmented_widget.setCurrentItem(current_segment)
        else:
            self.segmented_widget.setCurrentItem('input')

    def _update_existing_node_data(self, node):
        for port_name, _, port_type in self.get_port_info(node, is_input=True):
            input_port = node.get_input(port_name)
            connected = input_port.connected_ports() if input_port else []
            if len(connected) == 1:
                upstream = connected[0]
                original_data = upstream.node().get_output_value(upstream.name())
            elif connected:
                original_data = [up.node().get_output_value(up.name()) for up in connected]
            else:
                original_data = node._input_values.get(port_name, "暂无数据")
            if port_name in self._column_list_widgets:
                list_widget = self._column_list_widgets[port_name]
                if isinstance(original_data, pd.DataFrame) and not original_data.empty:
                    current_columns = list(original_data.columns)
                    existing_items = [list_widget.item(i).text() for i in range(list_widget.count())]
                    if set(current_columns) != set(existing_items):
                        self.update_properties(node)
                        return
                    selected_columns = node.column_select.get(port_name, [])
                    for i in range(list_widget.count()):
                        item = list_widget.item(i)
                        item.setCheckState(Qt.Checked if item.text() in selected_columns else Qt.Unchecked)
            current_selected_data = self._get_current_input_value(node, port_name, original_data)
            self._update_text_edit_for_port(port_name, current_selected_data)

        for port_name, _, port_type in self.get_port_info(node, is_input=False):
            display_data = node.get_output_value(port_name)
            if display_data is None:
                display_data = "暂无数据"
            self._update_text_edit_for_port(port_name, display_data)

    def _populate_input_ports(self, node, layout):
        port_infos = self.get_port_info(node, is_input=True)
        if not port_infos:
            layout.addWidget(BodyLabel("  无输入端口"))
            return
        for port_name, port_label, port_type in port_infos:
            port_label = BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}")
            port_label.setWordWrap(True)
            layout.addWidget(port_label)
            input_port = node.get_input(port_name)
            connected = input_port.connected_ports() if input_port else []
            if len(connected) == 1:
                upstream = connected[0]
                original_data = upstream.node().get_output_value(upstream.name())
            elif connected:
                original_data = [up.node().get_output_value(up.name()) for up in connected]
            else:
                original_data = "暂无数据"
            if port_type == ArgumentType.CSV and isinstance(original_data, pd.DataFrame) and not original_data.empty:
                self._add_column_selector_widget_to_layout(node, port_name, original_data, layout)
                current_selected_data = self._get_current_input_value(node, port_name, original_data)
            elif port_type == ArgumentType.CSV and isinstance(original_data, str) and Path(original_data).is_file():
                sample_data = pd.read_csv(original_data, nrows=5)
                self._add_column_selector_widget_to_layout(node, port_name, sample_data, layout)
                current_selected_data = self._get_current_input_value(node, port_name, original_data)
            else:
                current_selected_data = original_data
            self._add_text_edit_to_layout(
                current_selected_data,
                port_type=port_type,
                port_name=port_name,
                layout=layout,
                node=node
            )

    def _populate_output_ports(self, node, layout):
        port_infos = self.get_port_info(node, is_input=False)
        if not port_infos:
            layout.addWidget(BodyLabel("  无输出端口"))
            return
        for port_name, port_label, port_type in port_infos:
            port_label = BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}")
            port_label.setWordWrap(True)
            layout.addWidget(port_label)
            output_values = getattr(node, '_output_values', None)
            if output_values is None:
                # 初始化为空 dict，避免跳过渲染
                output_values = {}
            display_data = output_values.get(port_name)
            if display_data is None:
                try:
                    display_data = node.model.get_property(port_name)
                except KeyError:
                    display_data = "暂无数据"
            if port_type == ArgumentType.UPLOAD:
                self._add_upload_widget_to_layout(node, port_name, layout)
            self._add_text_edit_to_layout(
                display_data,
                port_type=port_type,
                port_name=port_name,
                layout=layout,
                node=node,
                is_output=True
            )

    def _add_seperator(self, layout):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        layout.addWidget(separator)

    def _on_segmented_changed(self, item_key):
        if item_key == 'input':
            self.stacked_widget.setCurrentIndex(0)
        elif item_key == 'output':
            self.stacked_widget.setCurrentIndex(1)

    def _get_current_input_value(self, node, port_name, original_data):
        selected_columns = node.column_select.get(port_name, [])
        if selected_columns and isinstance(original_data, pd.DataFrame):
            try:
                if len(selected_columns) == 1:
                    return original_data[selected_columns[0]]
                else:
                    return original_data[selected_columns]
            except Exception as e:
                return f"列选择错误: {str(e)}"
        else:
            return original_data

    def _add_column_selector_widget_to_layout(self, node, port_name, data, layout):
        if not isinstance(data, pd.DataFrame) or data.empty:
            return

        columns = list(data.columns)
        if not columns:
            return

        # --- 新增：列选择卡片 ---
        column_card = CardWidget(self)
        initial_max_height = 200  # 初始显示的最大高度
        column_card.setMaximumHeight(initial_max_height)
        column_card.setMinimumHeight(initial_max_height)
        # 用于存储该卡片的展开/收缩状态 (使用 port_name 作为唯一标识)
        node_id = node.id
        port_identifier = f"{node_id}_{port_name}"  # 组合 node_id 和 port_name 确保唯一性
        if not hasattr(self, '_column_selector_card_expanded'):
            self._column_selector_card_expanded = {}
        self._column_selector_card_expanded[port_identifier] = False
        card_layout = QVBoxLayout(column_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(8)
        # --- 新增：标题和展开/收缩按钮布局 ---
        title_btn_layout = QHBoxLayout()
        title_label = BodyLabel("列选择:")
        title_btn_layout.addWidget(title_label)
        title_btn_layout.addStretch()
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)
        expand_btn.setFixedSize(QSize(26, 20))

        def toggle_expand():
            is_expanded = self._column_selector_card_expanded[port_identifier]
            if is_expanded:
                # 收起
                column_card.setMaximumHeight(initial_max_height)
                column_card.setMinimumHeight(initial_max_height)
                expand_btn.setIcon(get_icon("放大"))
                self._column_selector_card_expanded[port_identifier] = False
            else:
                # 展开
                # 计算展开所需的高度 (估算每个列表项大约 35 像素)
                num_items = list_widget.count()
                estimated_height_for_items = num_items * 39
                # 估算布局填充和标题的高度
                padding_height = card_layout.contentsMargins().top() + card_layout.contentsMargins().bottom()
                # 标题和按钮布局的高度 (BodyLabel + Layout spacing)
                title_height = title_label.sizeHint().height() + card_layout.spacing()
                total_estimated_height = padding_height + title_height + estimated_height_for_items
                # 如果需要完全展开，可以设置固定高度
                column_card.setFixedHeight(total_estimated_height + 40)
                expand_btn.setIcon(get_icon("缩小"))
                self._column_selector_card_expanded[port_identifier] = True
            # 调用布局无效化以触发更新
            # 由于 column_card 在 self.node_vbox 中，需要更新父布局
            self.node_vbox.invalidate()

        expand_btn.clicked.connect(toggle_expand)
        title_btn_layout.addWidget(expand_btn)
        card_layout.addLayout(title_btn_layout)
        # --- 结束新增 ---
        list_widget = ListWidget(self)
        list_widget.setSelectionMode(ListWidget.NoSelection)
        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            list_widget.addItem(item)

        selected_columns = node.column_select.get(port_name, [])
        if not selected_columns and columns:
            selected_columns = columns.copy()
            node.column_select[port_name] = selected_columns
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setCheckState(Qt.Checked if item.text() in selected_columns else Qt.Unchecked)

        card_layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        select_all_btn = PushButton("全选", self)
        clear_btn = PushButton("清空", self)

        def select_all():
            # 阻止 itemChanged 信号，避免每次设置状态都触发更新
            list_widget.blockSignals(True)
            try:
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    item.setCheckState(Qt.Checked)
            finally:
                # 确保无论如何都要恢复信号连接
                list_widget.blockSignals(False)
            # 手动触发一次更新
            _on_selection_changed()

        def clear_all():
            # 阻止 itemChanged 信号
            list_widget.blockSignals(True)
            try:
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    item.setCheckState(Qt.Unchecked)
            finally:
                # 确保无论如何都要恢复信号连接
                list_widget.blockSignals(False)
            # 手动触发一次更新
            _on_selection_changed()

        def _on_selection_changed():
            # 这个函数现在只在全选/全清或单个项改变时被调用
            current_selected = [
                list_widget.item(i).text()
                for i in range(list_widget.count())
                if list_widget.item(i).checkState() == Qt.Checked
            ]
            node.column_select[port_name] = current_selected
            # 这里只获取选中的列数据，避免全量传递
            selected_data_subset = data[current_selected] if current_selected else pd.DataFrame()
            self._update_text_edit_for_port(port_name, selected_data_subset)

        # 连接 itemChanged 信号，用于单个项的勾选/取消勾选
        list_widget.itemChanged.connect(_on_selection_changed)

        select_all_btn.clicked.connect(select_all)
        clear_btn.clicked.connect(clear_all)

        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(clear_btn)
        card_layout.addLayout(btn_layout)

        layout.addWidget(column_card)
        # 存储 list_widget 以便后续更新
        self._column_list_widgets[port_name] = list_widget

    def _add_text_edit_to_layout(self, text, port_type=None, port_name=None, layout=None, node=None, is_output=False):
        tree_widget = VariableTreeWidget(text, port_type, parent=self.main_window)
        info_card = CardWidget(self)
        info_card.setMaximumHeight(300)
        card_layout = QVBoxLayout(info_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_text = "数据信息:"
        title_label = BodyLabel(title_text)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        if is_output and node is not None:
            add_global_btn = TransparentPushButton(text="全局变量", icon=FluentIcon.ADD, parent=self)
            add_global_btn.clicked.connect(
                lambda _, n=node, p=port_name: self._add_output_to_global_variable(n, p)
            )
            title_layout.addWidget(add_global_btn)
        browse_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)
        browse_btn.setFixedSize(QSize(26, 20))
        browse_btn.clicked.connect(tree_widget.show_detail)
        title_layout.addWidget(browse_btn)
        card_layout.addLayout(title_layout)
        card_layout.addWidget(tree_widget)
        if layout is None:
            layout = self.node_vbox
        layout.addWidget(info_card)

        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(
                Action(
                    FluentIcon.COPY, "复制为表达式", parent=self,
                    triggered=lambda: self._copy_as_expression("node_vars", f"{node.name()}_{port_name}")
                )
            )
            menu.exec_(info_card.mapToGlobal(pos))

        if is_output:
            info_card.setContextMenuPolicy(Qt.CustomContextMenu)
            info_card.customContextMenuRequested.connect(show_context_menu)
        if port_name is not None:
            self._text_edit_widgets[port_name] = tree_widget
        return tree_widget

    def _update_text_edit_for_port(self, port_name, new_value):
        if port_name not in self._text_edit_widgets:
            return
        widget = self._text_edit_widgets[port_name]
        if isinstance(widget, VariableTreeWidget):
            widget.set_data(new_value)

    def _add_upload_widget_to_layout(self, node, port_name, layout):
        upload_widget = QWidget()
        upload_layout = QVBoxLayout(upload_widget)
        upload_layout.setSpacing(4)
        upload_layout.setContentsMargins(0, 0, 0, 0)
        upload_button = PushButton("📁 上传文件", self)
        upload_button.clicked.connect(lambda _, p=port_name, n=node: self._select_upload_file(p, n))
        upload_layout.addWidget(upload_button)
        layout.addWidget(upload_widget)

    def _select_upload_file(self, port_name, node):
        current_path = node._output_values.get(port_name, "")
        directory = os.path.dirname(current_path) if current_path else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "上传文件", directory, "All Files (*)"
        )
        if not file_path:
            return

        src_path = Path(file_path)
        if not src_path.exists():
            InfoBar.error("文件不存在", f"所选文件 {file_path} 不存在", parent=self.parent_window)
            return

        # ✅ 定义目标目录：项目根目录下的 uploads/
        upload_root = canvas_file_dump_path() / "uploads"

        upload_root.mkdir(exist_ok=True, parents=True)

        # ✅ 生成唯一文件名（避免覆盖）
        safe_name = re.sub(r'[^\w\.-]', '_', src_path.stem)
        suffix = src_path.suffix
        unique_name = f"{safe_name}_{node.persistent_id}{suffix}"
        dst_path = upload_root / unique_name

        # ✅ 复制文件
        try:
            import shutil
            shutil.copy2(src_path, dst_path)
            logger.info(f"已上传并复制文件: {src_path} -> {dst_path}")
        except Exception as e:
            logger.error(f"文件复制失败: {e}")
            InfoBar.error("上传失败", f"无法复制文件：{e}", parent=self.parent_window)
            return

        # ✅ 设置节点输出为新的相对路径
        node._output_values[port_name] = str(dst_path)

        # 刷新 UI
        self.update_properties(node)

        InfoBar.success("上传成功", f"文件已保存至：{dst_path.name}", parent=self.main_window, duration=2000)

    def get_node_description(self, node):
        if hasattr(node, 'component_class'):
            return getattr(node.component_class, 'description', '')
        try:
            return node.model.get_property('description')
        except KeyError:
            return ''

    # ========================
    # ControlFlowBackdrop 相关
    # ========================
    def _update_control_flow_properties(self, node, current_segment=None):
        # --- 清理之前的Backdrop缓存 ---
        # 在构建新UI前，清理旧的缓存引用（如果有的话）
        if hasattr(self, '_backdrop_progress_label'):
            delattr(self, '_backdrop_progress_label')
        if hasattr(self, '_backdrop_progress_bar'):
            delattr(self, '_backdrop_progress_bar')
        if hasattr(self, '_backdrop_internal_nodes_list'):
            delattr(self, '_backdrop_internal_nodes_list')

        title = SubtitleLabel(f"🔁 {node.NODE_NAME}")
        self.node_vbox.addWidget(title)

        flow_type = getattr(node, 'TYPE', 'unknown')
        current = node.model.get_property('current_index')
        if flow_type == "loop":
            loop_mode = node.model.get_property("loop_mode")
            if loop_mode == 'count':
                total = node.model.get_property("loop_nums")
            else:
                total = node.model.get_property("max_iterations")
        elif flow_type == "iterate":
            input_data = []
            for input_port in node.input_ports():
                connected = input_port.connected_ports()
                if connected:
                    if len(connected) == 1:
                        upstream = connected[0]
                        value = upstream.node()._output_values.get(upstream.name())
                        input_data = value
                    else:
                        input_data.extend(
                            [upstream.node()._output_values.get(upstream.name()) for upstream in connected]
                        )
            if not isinstance(input_data, (list, tuple, dict)):
                input_data = [input_data]
            total = len(input_data)
            node.model.set_property("loop_nums", total)
        else:
            total = 0

        # --- 缓存进度标签和进度条 ---
        progress_label = StrongBodyLabel(f"进度: {current}/{total}")
        self.node_vbox.addWidget(progress_label)
        self._backdrop_progress_label = progress_label  # 缓存

        progress_bar = ProgressBar(self, useAni=False)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(int(current / max(1, total) * 100) if total > 0 else 0)
        self.node_vbox.addWidget(progress_bar)
        self._backdrop_progress_bar = progress_bar  # 缓存

        if flow_type == "loop":
            self._add_loop_config_section(node)

        self._add_internal_nodes_section(node)  # 这个方法会缓存内部节点列表
        self.node_vbox.addStretch()

        # ... (输入输出端口的构建逻辑保持不变) ...
        self.segmented_widget = SegmentedWidget()
        self.segmented_widget.addItem('input', '输入端口')
        self.segmented_widget.addItem('output', '输出端口')
        self.stacked_widget = QStackedWidget(self)
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        self._populate_input_ports(node, input_layout)
        input_layout.addStretch(1)
        self.stacked_widget.addWidget(input_widget)
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        self._populate_output_ports(node, output_layout)
        output_layout.addStretch(1)
        self.stacked_widget.addWidget(output_widget)
        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)
        self.node_vbox.addWidget(self.segmented_widget)
        self.node_vbox.addWidget(self.stacked_widget)
        self.node_vbox.addStretch(1)
        if current_segment in ['input', 'output']:
            self.segmented_widget.setCurrentItem(current_segment)
        else:
            self.segmented_widget.setCurrentItem('input')

    def _add_internal_nodes_section(self, node):
        nodes_card = CardWidget(self)
        node_id = node.id
        self._internal_nodes_card_expanded[node_id] = False
        nodes_layout = QVBoxLayout(nodes_card)
        nodes_layout.setContentsMargins(10, 10, 10, 10)

        title_btn_layout = QHBoxLayout()
        title = BodyLabel("区域内部节点：")
        title_btn_layout.addWidget(title)
        title_btn_layout.addStretch()

        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)
        expand_btn.setFixedSize(QSize(26, 20))

        def toggle_expand():
            is_expanded = self._internal_nodes_card_expanded[node_id]
            if is_expanded:
                nodes_card.setMaximumHeight(initial_max_height)
                nodes_card.setMinimumHeight(initial_max_height)
                expand_btn.setIcon(get_icon("放大"))
                self._internal_nodes_card_expanded[node_id] = False
            else:
                nodes_card.setFixedHeight(total_estimated_height)
                expand_btn.setIcon(get_icon("缩小"))
                self._internal_nodes_card_expanded[node_id] = True
            self.node_vbox.invalidate()

        expand_btn.clicked.connect(toggle_expand)
        title_btn_layout.addWidget(expand_btn)
        nodes_layout.addLayout(title_btn_layout)

        # 生成内部节点列表数据
        _, _, internal_nodes = node.get_nodes()
        # 创建列表
        internal_nodes_list = ListWidget(self)
        if not internal_nodes:
            internal_nodes_list.addItem(QListWidgetItem("暂无内部节点"))
        else:
            for n in internal_nodes:
                status = self.main_window.get_node_status(n)
                status_text = {
                    "running": "🟡 运行中",
                    "success": "🟢 成功",
                    "failed": "🔴 失败",
                    "unrun": "⚪ 未运行",
                    "pending": "🔵 待运行"
                }.get(status, status)
                item_text = f"{status_text} - {n.name()}"
                item = QListWidgetItem(item_text)
                internal_nodes_list.addItem(item)

        num_items = internal_nodes_list.count()
        estimated_height_for_items = num_items * 40
        padding_height = 25
        title_height = 20
        total_estimated_height = padding_height + title_height + estimated_height_for_items
        initial_max_height = min(total_estimated_height, 200)
        nodes_card.setMaximumHeight(initial_max_height)
        nodes_card.setMinimumHeight(initial_max_height)
        nodes_layout.addWidget(internal_nodes_list)
        self.node_vbox.addWidget(nodes_card)

        # --- 缓存内部节点列表 ---
        self._backdrop_internal_nodes_list = internal_nodes_list

    def _add_loop_config_section(self, node):
        config_card = CardWidget(self)
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(10, 10, 10, 10)

        from qfluentwidgets import ComboBox, SpinBox
        mode_combo = ComboBox(self)
        mode_combo.addItems(['固定次数', '条件循环', 'While循环'])
        mode_combo.setCurrentText({
                                      'count': '固定次数',
                                      'condition': '条件循环',
                                      'while': 'While循环'
                                  }.get(node.model.get_property("loop_mode"), '固定次数'))

        def on_mode_changed(text):
            mode_map = {'固定次数': 'count', '条件循环': 'condition', 'While循环': 'while'}
            node.model.set_property("loop_mode", mode_map.get(text, "count"))
            # ✅ 关键：触发完整刷新，确保控件正确重建
            self.update_properties(node, node_changed=True)

        mode_combo.currentTextChanged.connect(on_mode_changed)
        config_layout.addWidget(BodyLabel("循环模式:"))
        config_layout.addWidget(mode_combo)

        current_mode = node.model.get_property("loop_mode")
        if current_mode == 'count':
            max_iter_spin = SpinBox(self)
            max_iter_spin.setRange(1, 10000)
            current_max = node.model.get_property("loop_nums")
            max_iter_spin.setValue(current_max)

            def on_max_iter_changed(value):
                node.model.set_property('loop_nums', value)
                self._update_existing_backdrop_data(node)

            max_iter_spin.valueChanged.connect(on_max_iter_changed)

            config_layout.addWidget(BodyLabel("循环次数:"))
            config_layout.addWidget(max_iter_spin)
        else:
            # === 条件表达式输入行（带放大按钮）===
            expr_layout = QHBoxLayout()
            expr_label = BodyLabel("条件表达式:")
            expr_layout.addWidget(expr_label)
            global_vars = getattr(self.main_window, 'global_variables', None)
            extra_keys = ['data', 'result', 'current_index', 'current_iteration', 'iteration_count', 'loop_mode',
                          'max_iterations']
            _, _, internal_nodes = node.get_nodes()
            # 将内部节点的输出端口按node_vars.nodename_portname填写key
            for n in internal_nodes:
                name = re.sub(r'\s+', '_', n.name())
                for port in n.output_ports():
                    extra_keys.append(f"node_vars.{name}_{port.name()}")
            condition_edit = VariableCompletionTextEdit(
                get_variable_list_func=lambda keys=extra_keys: global_vars.get_vars(keys),
                parent=self
            )
            condition_edit.setMaximumHeight(60)
            condition_edit.setPlaceholderText("请输入条件表达式")
            current_condition = node.model.get_property("loop_condition")
            condition_edit.setText(current_condition)

            def on_condition_changed():
                node.model.set_property('loop_condition', condition_edit.toPlainText())

            condition_edit.cursorPositionChanged.connect(on_condition_changed)
            # ✅ 添加放大图标按钮
            browse_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)
            browse_btn.setFixedSize(QSize(26, 20))
            browse_btn.clicked.connect(
                lambda _, edit=condition_edit, key=extra_keys: self._open_long_text_editor(edit, key)
            )
            expr_layout.addWidget(browse_btn)

            config_layout.addLayout(expr_layout)

            config_layout.addWidget(condition_edit)

            # 最大迭代次数
            max_iter_spin = SpinBox(self)
            max_iter_spin.setRange(1, 10000)
            current_max_iter = node.model.get_property("max_iterations")
            max_iter_spin.setValue(current_max_iter)

            def on_max_iterations_changed(value):
                node.model.set_property('max_iterations', value)
                self._update_existing_backdrop_data(node)

            max_iter_spin.valueChanged.connect(on_max_iterations_changed)

            config_layout.addWidget(BodyLabel("最大迭代次数:"))
            config_layout.addWidget(max_iter_spin)

        self.node_vbox.addWidget(config_card)

    def _open_long_text_editor(self, line_edit, key):
        # ✅ 根据你的实际路径导入 LongTextEditorDialog
        dialog = LongTextEditorDialog(
            content=line_edit.toPlainText(), extra_keys=key, parent=self.window(), main_window=self.main_window
        )
        if dialog.exec():
            new_text = dialog.text_edit.toPlainText().strip()
            line_edit.setText(new_text)

    def _add_output_to_global_variable(self, node, port_name: str):
        value = node._output_values.get(port_name)
        if value is None:
            InfoBar.warning(
                title="警告",
                content=f"端口 {port_name} 当前无有效输出值",
                parent=self.main_window,
                position=InfoBarPosition.TOP_RIGHT
            )
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

    # ========================
    # 全局变量面板（只构建一次）
    # ========================
    def _show_global_variables_panel(self):
        if self._global_panel_built:
            return
        title = SubtitleLabel("🌍 全局变量")
        self.global_vbox.addWidget(title)
        self.global_segmented = SegmentedWidget(self)
        self.global_segmented.addItem('env', '环境变量')
        self.global_segmented.addItem('node', '节点变量')
        self.global_segmented.addItem('custom', '自定义变量')
        self.global_segmented.setCurrentItem('node')
        self.global_stacked = QStackedWidget(self)
        self.env_page = self._create_env_page()
        self.node_page = self._create_node_vars_page()
        self.custom_page = self._create_custom_vars_page()
        self.global_stacked.addWidget(self.env_page)
        self.global_stacked.addWidget(self.node_page)
        self.global_stacked.addWidget(self.custom_page)
        self.global_stacked.setCurrentIndex(1)
        self.global_segmented.currentItemChanged.connect(self._on_global_tab_changed)
        self.global_vbox.addWidget(self.global_segmented)
        self.global_vbox.addWidget(self.global_stacked)
        self._global_panel_built = True

    def _on_global_tab_changed(self, key):
        if key == 'env':
            index = 0
        elif key == 'node':
            index = 1
        else:
            index = 2
        self.global_stacked.setCurrentIndex(index)

    def _create_custom_vars_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = TransparentPushButton(text="自定义变量 (custom)", icon=get_icon("自定义变量"), parent=self)
        layout.addWidget(title)
        add_custom_btn = TransparentPushButton(text="新增自定义变量", parent=self, icon=FluentIcon.ADD)
        add_custom_btn.clicked.connect(self._add_new_custom_variable)
        layout.addWidget(add_custom_btn)
        self.custom_vars_container = QWidget()
        self.custom_vars_layout = QVBoxLayout(self.custom_vars_container)
        self.custom_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_vars_layout.setSpacing(6)
        layout.addWidget(self.custom_vars_container)
        layout.addStretch()
        self._refresh_custom_vars_page()
        return widget

    def _create_node_vars_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        title = TransparentPushButton(text="节点输出变量 (node_vars)", icon=get_icon("节点变量"), parent=self)
        layout.addWidget(title)
        self.node_vars_container = QWidget()
        self.node_vars_layout = QVBoxLayout(self.node_vars_container)
        self.node_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.node_vars_layout.setSpacing(8)
        layout.addWidget(self.node_vars_container)
        layout.addStretch(1)
        self._refresh_node_vars_page()
        return widget

    def _create_env_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = TransparentPushButton(text="环境变量 (env)", icon=get_icon("环境变量"), parent=self)
        layout.addWidget(title)
        add_env_btn = TransparentPushButton(text="新增环境变量", parent=self, icon=FluentIcon.ADD)
        add_env_btn.clicked.connect(self._add_new_env_variable)
        layout.addWidget(add_env_btn)
        self.env_vars_container = QWidget()
        self.env_vars_layout = QVBoxLayout(self.env_vars_container)
        self.env_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.env_vars_layout.setSpacing(6)
        layout.addWidget(self.env_vars_container)
        self._refresh_env_page()
        layout.addStretch()
        return widget

    # ========================
    # 全局变量 UI 构建（增量更新）
    # ========================
    def _refresh_custom_vars_page(self):
        # custom
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        current_custom = set(global_vars.custom.keys()) if hasattr(global_vars, 'custom') else set()
        existing_custom = set(self._custom_var_cards.keys())
        for name in current_custom - existing_custom:
            var_obj = global_vars.custom[name]
            card = self._create_dict_row(name, var_obj.value)
            self.custom_vars_layout.addWidget(card)
            self._custom_var_cards[name] = card
        for name in existing_custom - current_custom:
            card = self._custom_var_cards.pop(name)
            card.deleteLater()
        for name in current_custom & existing_custom:
            var_obj = global_vars.custom[name]
            card = self._custom_var_cards[name]
            if card.layout().count() >= 2:
                value_label = card.layout().itemAt(1).widget()
                if isinstance(value_label, BodyLabel):
                    try:
                        preview = json.dumps(var_obj.value, ensure_ascii=False, default=str)[:40] + "..."\
                            if isinstance(var_obj.value, (dict, list)) else str(var_obj.value)[:40]
                    except:
                        preview = "<无法预览>"
                    value_label.setText(preview)

    def _refresh_node_vars_page(self):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        # node_vars
        current_node_vars = set(global_vars.node_vars.keys()) if hasattr(global_vars, 'node_vars') else set()
        existing_node_vars = set(self._node_var_cards.keys())
        for name in current_node_vars - existing_node_vars:
            node_var_obj = global_vars.node_vars[name]
            card = self._create_variable_card(name, node_var_obj)
            self.node_vars_layout.addWidget(card)
            self._node_var_cards[name] = card
        for name in existing_node_vars - current_node_vars:
            card = self._node_var_cards.pop(name)
            card.deleteLater()
        for name in current_node_vars & existing_node_vars:
            node_var_obj = global_vars.node_vars[name]
            card = self._node_var_cards[name]
            if hasattr(card, 'strategy_combo'):
                combo = card.strategy_combo
                if combo.property("policy") != node_var_obj.update_policy:
                    combo.blockSignals(True)
                    combo.setCurrentText(node_var_obj.update_policy)
                    combo.blockSignals(False)
            if hasattr(card, 'tree_widget'):
                card.tree_widget.set_data(node_var_obj.value)

    def _refresh_env_page(self):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars or not hasattr(global_vars, 'env'):
            return
        all_env_vars = global_vars.env.get_all_env_vars()
        current_env = {k: v for k, v in all_env_vars.items() if k != 'start_time'}
        existing_env = set(self._env_var_cards.keys())
        for key in current_env.keys() - existing_env:
            card = self._create_env_var_row(key, current_env[key])
            self.env_vars_layout.addWidget(card)
            self._env_var_cards[key] = card
        for key in existing_env - current_env.keys():
            card = self._env_var_cards.pop(key)
            card.deleteLater()
        for key in current_env.keys() & existing_env:
            card = self._env_var_cards[key]
            value = current_env[key]
            if card.layout().count() >= 2:
                value_label = card.layout().itemAt(1).widget()
                if isinstance(value_label, BodyLabel):
                    try:
                        preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." \
                            if isinstance(value, (dict, list)) else str(value)[:40]
                    except:
                        preview = "<无法预览>"
                    value_label.setText(preview)
        if not current_env and self.env_vars_layout.count() == 0:
            self.env_vars_layout.addWidget(BodyLabel("暂无环境变量"))

    def _create_dict_row(self, name: str, value):
        card = CardWidget(self)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        name_label = CaptionLabel(f"{name}:")
        try:
            preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." \
                if isinstance(value, (dict, list)) else str(value)[:40]
        except:
            preview = "<无法预览>"
        value_label = CaptionLabel(preview)
        value_label.setWordWrap(True)
        value_label.setStyleSheet("color: #888888;")
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(16, 16)
        del_btn.clicked.connect(lambda _, n=name: self._delete_custom_variable(n, 'custom'))
        layout.addWidget(name_label)
        layout.addWidget(value_label)
        layout.addStretch()
        layout.addWidget(del_btn)

        def show_context_menu(pos):
            current_val = self.main_window.global_variables.custom.get(name)
            current_val = current_val.value if current_val is not None else "<已删除>"
            menu = RoundMenu(parent=self)
            menu.addActions(
                [
                    Action(
                        FluentIcon.COPY, "复制为表达式", parent=self,
                        triggered=lambda: self._copy_as_expression("custom", name)
                    ),
                    Action(
                        FluentIcon.EDIT, "编辑变量", parent=self,
                        triggered=lambda: self._edit_custom_variable(name, current_val)
                    )
                ]
            )
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    def _create_variable_card(self, name: str, node_var_obj):
        parts = name.split("_")
        if len(parts) == 2:
            node_name = parts[0]
            port_name = parts[1]
        else:
            if re.match(r'\d+', parts[1]):
                node_name = "_".join(parts[:2])
                port_name = "_".join(parts[2:])
            else:
                node_name = parts[0]
                port_name = "_".join(parts[1:])

        # 根据规则，将 safe_node_name_candidate 中的下划线替换回空格，得到原始名称候选
        node_name = re.sub(r'_(?=\d+$)', " ", node_name)

        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)
        title_layout = QHBoxLayout()
        title = CaptionLabel(f"{node_name}\n{port_name}")
        title_layout.addWidget(title)
        # 节点变量更新策略
        strategy_combo = TransparentDropDownToolButton(icon=get_icon(node_var_obj.update_policy), parent=self)
        strategy_combo.setProperty("policy", node_var_obj.update_policy)
        strategy_combo.setProperty("node_var_name", name)
        menu = RoundMenu(parent=strategy_combo)
        menu.addAction(
            Action(get_icon("固定"), '固定',
                   triggered=lambda checked=False, btn=strategy_combo: self._on_node_var_strategy_changed("固定", btn))
        )
        menu.addAction(
            Action(get_icon("更新"), '更新',
                   triggered=lambda checked=False, btn=strategy_combo: self._on_node_var_strategy_changed("更新", btn))
        )
        menu.addAction(
            Action(get_icon("追加"), '追加',
                   triggered=lambda checked=False, btn=strategy_combo: self._on_node_var_strategy_changed("追加", btn))
        )
        strategy_combo.setMenu(menu)
        title_layout.addStretch()
        title_layout.addWidget(strategy_combo)
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.clicked.connect(lambda _, n=name: self._delete_custom_variable(n, 'node_vars'))
        title_layout.addWidget(del_btn)
        layout.addLayout(title_layout)
        tree = VariableTreeWidget(node_var_obj.value, parent=self.main_window)
        tree.setMinimumHeight(80)
        tree.setMaximumHeight(120)
        layout.addWidget(tree)

        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addActions(
                [
                    Action(
                        FluentIcon.COPY, "复制为表达式", parent=self,
                        triggered=lambda: self._copy_as_expression("node_vars", name)
                    ),
                    Action(
                        FluentIcon.DELETE, "清空变量结果", parent=self,
                        triggered=lambda:
                        self.main_window.global_variables_changed.emit("node_vars", name, "clear")
                    ),
                    Action(
                        FluentIcon.FIT_PAGE, "跳转到该节点", parent=self,
                        triggered=lambda: self._locate_node_by_variable_name(name)
                    )
                ]

            )
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        card.strategy_combo = strategy_combo

        # 节点变量双击自动跳转到对应节点
        def on_card_double_clicked(event):
            if event.button() == Qt.LeftButton:
                self._locate_node_by_variable_name(name)

        card.mouseDoubleClickEvent = on_card_double_clicked
        card.setCursor(Qt.PointingHandCursor)  # 可选：改变鼠标指针提示可点击

        card.tree_widget = tree
        card.node_var_name = name
        return card

    def _locate_node_by_variable_name(self, var_name: str):
        """根据全局变量名定位到对应的节点"""
        # 从 var_name 解析出 safe_node_name_candidate
        # 从左边分割一两次获取到端口名
        parts = var_name.split("_")
        if len(parts) < 2:
            logger.warning(f"无法从变量名 '{var_name}' 解析出节点名称")
            return
        elif len(parts) == 2:
            safe_node_name_candidate = parts[0]
        else:
            if re.match(r'\d+', parts[1]):
                safe_node_name_candidate = "_".join(parts[:2])
            else:
                safe_node_name_candidate = parts[0]

        # 根据规则，将 safe_node_name_candidate 中的下划线替换回空格，得到原始名称候选
        original_name_candidate = re.sub(r'_(?=\d+$)', " ", safe_node_name_candidate)

        # 尝试通过名称查找节点
        node_graph = self.main_window.graph  # 获取 NodeGraphQt 实例
        if not node_graph:
            logger.warning("无法获取节点图实例")
            return

        # 尝试1: 使用原始名称候选查找 (例如 "My Node_1" -> "My Node 1")
        found_node = node_graph.get_node_by_name(original_name_candidate)
        if not found_node:
            logger.warning(f"未找到与变量名 '{var_name}' 对应的节点 "
                           f"(尝试名称: '{original_name_candidate}', '{safe_node_name_candidate}')")
            InfoBar.warning(
                title="未找到节点",
                content=f"无法定位到变量 '{var_name}' 对应的节点。",
                parent=self.main_window,
                position=InfoBarPosition.TOP_RIGHT
            )
            return
        self.main_window.canvas_widget.zoom_to_nodes([found_node._view])

    def _create_env_var_row(self, key: str, value):
        card = CardWidget(self)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        name_label = CaptionLabel(f"{key} : ")
        try:
            preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." \
                if isinstance(value, (dict, list)) else str(value)[:40]
        except:
            preview = "<无法预览>"
        value_label = CaptionLabel(preview)
        value_label.setWordWrap(True)
        value_label.setStyleSheet("color: #888888;")
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(16, 16)
        del_btn.clicked.connect(lambda _, k=key: self._delete_env_variable(k))
        layout.addWidget(name_label)
        layout.addWidget(value_label)
        layout.addStretch()
        layout.addWidget(del_btn)

        def show_context_menu(pos):
            current_val = getattr(self.main_window.global_variables.env, key, None)
            menu = RoundMenu(parent=self)
            menu.addAction(Action(FluentIcon.COPY, "复制为表达式", parent=self,
                                  triggered=lambda: self._copy_as_expression("env", key)))
            menu.addAction(Action(FluentIcon.EDIT, "编辑变量", parent=self,
                                  triggered=lambda: self._edit_env_variable(key, current_val)))
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    # ========================
    # 全局变量操作
    # ========================
    def _delete_custom_variable(self, var_name: str, var_type: str):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        try:
            if var_type == 'custom' and hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                del global_vars.custom[var_name]
            elif var_type == 'node_vars' and hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
                del global_vars.node_vars[var_name]
                node = self._locate_node_by_variable_name(var_name)
                if hasattr(node, "refresh_node_outports"):
                    QtCore.QTimer.singleShot(0, node.refresh_node_outports)
                if hasattr(node, "_sync_outputs_ports"):
                    QtCore.QTimer.singleShot(0, node._sync_outputs_ports)

            self._refresh_custom_vars_page()
            self.main_window.global_variables_changed.emit(var_type, var_name, "delete")
            InfoBar.success("已删除", f"变量 '{var_name}' 已移除", parent=self.main_window, duration=1500)
        except Exception as e:
            InfoBar.error("删除失败", str(e), parent=self.main_window)

    def _on_node_var_strategy_changed(self, text: str, button: TransparentDropDownToolButton):
        button.setIcon(get_icon(text))
        var_name = button.property('node_var_name')
        if not var_name:
            return
        button.setProperty("policy", text)
        global_vars = getattr(self.main_window, 'global_variables', None)
        if global_vars and hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
            global_vars.node_vars[var_name].update_policy = text

    def _add_new_custom_variable(self):
        dialog = CustomTwoInputDialog(
            title1="变量名",
            title2="变量值",
            placeholder1="变量名（如 threshold）",
            placeholder2="变量值（如 0.5）",
            parent=self.main_window
        )
        if dialog.exec():
            name, value_str = dialog.get_text()
            if not name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            try:
                if value_str.lower() in ('true', 'false'):
                    value = value_str.lower() == 'true'
                elif '.' in value_str:
                    value = float(value_str)
                else:
                    value = int(value_str)
            except ValueError:
                value = value_str
            global_vars = getattr(self.main_window, 'global_variables', None)
            if global_vars:
                global_vars.set(name, value)
                self._refresh_custom_vars_page()
                self.main_window.global_variables_changed.emit("custom", name, "add")
                InfoBar.success("已添加", f"自定义变量 {name}", parent=self.main_window)

    def _add_new_env_variable(self):
        dialog = CustomTwoInputDialog(
            title1="环境变量名",
            title2="环境变量值",
            placeholder1="变量名（如 API_KEY）",
            placeholder2="变量值",
            parent=self.main_window
        )
        if dialog.exec():
            name, value = dialog.get_text()
            if not name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            global_vars = getattr(self.main_window, 'global_variables', None)
            if global_vars:
                global_vars.env.set_env_var(name, value)
                self._refresh_env_page()
                self.main_window.global_variables_changed.emit("env", name, "add")
                InfoBar.success("已添加", f"环境变量 {name}", parent=self.main_window)

    def _delete_env_variable(self, key: str):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        global_vars.env.delete_env_var(key)
        self._refresh_env_page()
        self.main_window.global_variables_changed.emit("env", key, "delete")
        InfoBar.success("已删除", f"环境变量 {key}", parent=self.main_window, duration=1500)

    def _copy_as_expression(self, prefix: str, var_name: str):
        var_name = re.sub(r'\s+', '_', var_name)
        expr = f"${prefix}.{var_name}$"
        clipboard = QApplication.clipboard()
        clipboard.setText(expr)
        InfoBar.success(
            title="已复制",
            content=f"表达式已复制：{expr}",
            parent=self.main_window,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500
        )

    def _edit_custom_variable(self, var_name: str, current_value):
        dialog = CustomTwoInputDialog(
            title1="变量名",
            title2="变量值",
            placeholder1="变量名（如 threshold）",
            placeholder2="变量值（如 0.5）",
            text1=var_name,
            text2=str(current_value),
            parent=self.main_window
        )
        if dialog.exec():
            new_name, new_value_str = dialog.get_text()
            if not new_name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            if new_name == var_name and new_value_str == str(current_value):
                return
            try:
                if new_value_str.lower() in ('true', 'false'):
                    new_value = new_value_str.lower() == 'true'
                elif '.' in new_value_str:
                    new_value = float(new_value_str)
                else:
                    new_value = int(new_value_str)
            except ValueError:
                new_value = new_value_str
            global_vars = getattr(self.main_window, 'global_variables', None)
            if not global_vars:
                return
            if new_name != var_name and var_name in global_vars.custom:
                del global_vars.custom[var_name]
                self.main_window.global_variables_changed.emit("custom", var_name, "delete")
                self.main_window.global_variables_changed.emit("custom", new_name, "add")
            global_vars.set(new_name, new_value)
            self._refresh_custom_vars_page()
            InfoBar.success("已更新", f"变量 {new_name}", parent=self.main_window)

    def _edit_env_variable(self, key: str, current_value):
        dialog = CustomTwoInputDialog(
            title1="环境变量名",
            title2="环境变量值",
            placeholder1="变量名（如 API_KEY）",
            placeholder2="变量值",
            text1=key,
            text2=str(current_value) if current_value is not None else "",
            parent=self.main_window
        )
        if dialog.exec():
            new_key, new_value = dialog.get_text()
            if not new_key:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            if new_key == key and new_value == current_value:
                return
            global_vars = getattr(self.main_window, 'global_variables', None)
            if not global_vars:
                return
            if new_key != key:
                global_vars.env.delete_env_var(key)
                self.main_window.global_variables_changed.emit("env", key, "delete")
                self.main_window.global_variables_changed.emit("env", new_key, "add")
            try:
                global_vars.env.set_env_var(new_key, new_value)
            except Exception as e:
                InfoBar.error("设置环境变量失败", f"错误信息：{e.__str__()}", parent=self.main_window)
                return
            self._refresh_env_page()
            InfoBar.success("已更新", f"环境变量 {new_key}", parent=self.main_window)
