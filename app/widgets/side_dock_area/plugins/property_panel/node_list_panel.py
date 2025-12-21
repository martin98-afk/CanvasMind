# -*- coding: utf-8 -*-
import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QListWidgetItem
from qfluentwidgets import (
    CardWidget, BodyLabel, SubtitleLabel,
    TransparentToolButton, FluentIcon
)

from app.utils.utils import topological_sort
from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList


class NodeListPanelWidget:
    """处理节点列表（连通图）UI的子模块"""

    def __init__(self, main_window, parent_panel, parent_layout):
        self.main_window = main_window
        self.parent_panel = parent_panel
        self.parent_layout = parent_layout

        # 当前组件（用户可编辑的连通图列表）
        self._current_components = []  # List[List[Node]]
        self._user_execution_order = {}  # key: tuple(sorted node ids), value: ordered node list

        # UI references
        self._component_cards = []
        self._component_nodes_list = {}      # list_id -> node list
        self._column_list_widgets = {}       # list_id -> InternalNodeList
        self._selected_row_in_component = {}  # list_id -> selected row (optional, for UX hint)

        # Top-level container
        self.nodes_card = None

    def build_ui(self, nodes):
        """首次构建或重置为拓扑排序结果"""
        new_components = topological_sort(nodes, split_components=True) or []

        # 尝试保留用户历史顺序中与新拓扑有交集的部分
        new_node_sets = [set(n.id for n in comp) for comp in new_components]
        current_user_order = self._user_execution_order.copy()
        final_components = []
        processed_new_indices = set()

        for old_key_node_ids, old_ordered_nodes in current_user_order.items():
            old_node_set = set(old_key_node_ids)
            matched_indices = []
            first_match_positions = []
            for i, new_node_set in enumerate(new_node_sets):
                if i in processed_new_indices:
                    continue
                if old_node_set & new_node_set:
                    # 找到 old_ordered_nodes 中第一个出现在 new_node_set 的位置
                    for j, node in enumerate(old_ordered_nodes):
                        if node.id in new_node_set:
                            first_match_positions.append(j)
                            matched_indices.append(i)
                            break
            if matched_indices:
                # 按 old 中出现顺序排序新组件
                sorted_pairs = sorted(zip(first_match_positions, matched_indices))
                for _, idx in sorted_pairs:
                    final_components.append(new_components[idx])
                    processed_new_indices.add(idx)

        # 添加未匹配的新组件（保持拓扑顺序）
        for i, comp in enumerate(new_components):
            if i not in processed_new_indices:
                final_components.append(comp)

        self._current_components = final_components
        self._refresh_ui_from_current_components()

    def _refresh_ui_from_current_components(self):
        """根据 self._current_components 重建整个 UI"""
        # 清空 parent_layout（移除标题和容器）
        while self.parent_layout.count():
            item = self.parent_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # 重建标题
        title = SubtitleLabel("⏬ 连通图执行顺序")
        self.parent_layout.addWidget(title)

        # 容器
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.nodes_card = QWidget(self.parent_panel)
        nodes_layout = QVBoxLayout(self.nodes_card)
        nodes_layout.setContentsMargins(10, 10, 10, 10)

        # 重置内部映射
        self._component_cards = []
        self._component_nodes_list.clear()
        self._column_list_widgets.clear()
        self._selected_row_in_component.clear()

        # 创建卡片
        for i, comp in enumerate(self._current_components):
            card, _ = self._create_component_card(nodes_layout, i)
            self._component_cards.append(card)

        nodes_layout.addStretch(1)
        scroll = self.parent_panel.set_scrollbar(self.nodes_card)
        layout.addWidget(scroll, 1)
        self.parent_layout.addWidget(widget)

        # 更新用户执行顺序（用于下次 build_ui 时对齐）
        self._user_execution_order.clear()
        for comp in self._current_components:
            if comp:
                key = tuple(sorted(n.id for n in comp))
                self._user_execution_order[key] = comp.copy()

    def _create_component_card(self, parent_layout, index):
        component = self._current_components[index]
        topo_sorted = topological_sort(component, split_components=False) or component

        component_card = CardWidget(self.parent_panel)
        comp_layout = QVBoxLayout(component_card)
        comp_layout.setContentsMargins(8, 8, 8, 8)

        # Header
        header_layout = QHBoxLayout()
        title_label = BodyLabel(f"子连通图 {index + 1} ({len(topo_sorted)} 个节点)")
        header_layout.addWidget(title_label)

        # 按钮
        move_up_btn = TransparentToolButton(FluentIcon.UP)
        move_up_btn.setToolTip("向上移动")
        move_down_btn = TransparentToolButton(FluentIcon.DOWN)
        move_down_btn.setToolTip("向下移动")
        split_btn = TransparentToolButton(FluentIcon.CUT)  # 分割图标
        split_btn.setToolTip("分割成两个连通图")

        for btn in (move_up_btn, move_down_btn, split_btn):
            btn.setFixedSize(24, 24)

        move_up_btn.setEnabled(index > 0)
        move_down_btn.setEnabled(index < len(self._current_components) - 1)

        move_up_btn.clicked.connect(lambda _, idx=index: self._move_component(idx, -1))
        move_down_btn.clicked.connect(lambda _, idx=index: self._move_component(idx, 1))
        split_btn.clicked.connect(lambda _, idx=index: self._split_component_at_selection(idx))

        header_layout.addStretch(1)
        header_layout.addWidget(move_up_btn)
        header_layout.addWidget(move_down_btn)
        header_layout.addWidget(split_btn)

        comp_layout.addLayout(header_layout)

        # 节点列表
        list_id = f"component_{index}"
        self._component_nodes_list[list_id] = topo_sorted

        status_list = [self.main_window.get_node_status(n) for n in topo_sorted]
        name_list = [n.name() for n in topo_sorted]

        node_list_widget = InternalNodeList(status_list, name_list, self.parent_panel)
        node_list_widget.setFixedHeight(max(40 * len(topo_sorted), 40))

        # 双击定位
        def on_double_click(item):
            row = node_list_widget.row(item)
            if 0 <= row < len(topo_sorted):
                node = topo_sorted[row]
                self.main_window.canvas_widget.zoom_to_nodes([node._view])

        node_list_widget.itemDoubleClicked.connect(on_double_click)

        comp_layout.addWidget(node_list_widget)
        self._column_list_widgets[list_id] = node_list_widget

        parent_layout.addWidget(component_card)
        return component_card, topo_sorted

    def _move_component(self, index, direction):
        if len(self._current_components) <= 1:
            return
        if direction == -1 and index > 0:
            self._current_components[index - 1], self._current_components[index] = \
                self._current_components[index], self._current_components[index - 1]
        elif direction == 1 and index < len(self._current_components) - 1:
            self._current_components[index], self._current_components[index + 1] = \
                self._current_components[index + 1], self._current_components[index]
        else:
            return
        self._refresh_ui_from_current_components()

    def _split_component_at_selection(self, index):
        if index >= len(self._current_components):
            return
        comp = self._current_components[index]
        if len(comp) <= 1:
            return

        list_id = f"component_{index}"
        node_list_widget = self._column_list_widgets.get(list_id)
        if node_list_widget:
            selected_row = node_list_widget.get_current_selected_row()
            # 分割点：在选中节点之后（选中第 i 行 → 分割点 = i+1）
            split_point = selected_row + 1 if selected_row >= 0 else len(comp) // 2
        else:
            split_point = len(comp) // 2

        if split_point <= 0 or split_point >= len(comp):
            return  # 无效分割点

        part1 = comp[:split_point]
        part2 = comp[split_point:]

        # 替换原组件为两个
        self._current_components[index:index + 1] = [part1, part2]
        self._refresh_ui_from_current_components()

    def update_node_list_content(self):
        """更新所有节点列表的状态文本"""
        if not self._component_nodes_list:
            return
        for list_id, node_list in self._component_nodes_list.items():
            widget = self._column_list_widgets.get(list_id)
            if widget:
                status_list = [self.main_window.get_node_status(n) for n in node_list]
                name_list = [n.name() for n in node_list]
                widget.update_content(status_list, name_list)

    def get_current_order(self):
        """返回当前执行顺序（平铺）"""
        result = []
        for comp in self._current_components:
            result.extend(comp)
        return result

    def reset_components(self):
        """重置为自动拓扑排序（丢弃用户修改）"""
        self._current_components = []
        self._user_execution_order.clear()
        # 注意：调用方需重新调用 build_ui(nodes)