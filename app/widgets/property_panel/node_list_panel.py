# -*- coding: utf-8 -*-
import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QListWidgetItem, QWidget, QSizePolicy
from loguru import logger
from qfluentwidgets import CardWidget, BodyLabel, ListWidget, \
    FluentIcon, TransparentToolButton, SubtitleLabel, SmoothScrollArea

from app.utils.utils import topological_sort
from app.widgets.property_panel.internal_node_list import InternalNodeList


class NodeListPanelWidget:
    """处理节点列表（连通图）UI的子模块"""

    def __init__(self, main_window, parent_panel, parent_layout):
        self.main_window = main_window
        self.parent_panel = parent_panel # PropertyPanel 的实例
        self.parent_layout = parent_layout # PropertyPanel 中的 node_vbox

        # 存储当前组件列表和卡片引用
        self._current_components = []
        self._component_cards = []
        self._component_nodes_list = {}
        self._user_execution_order = {}
        self._column_list_widgets = {}
        self._text_edit_widgets = {}

    def build_ui(self, nodes):
        """构建节点列表UI"""
        new_components = topological_sort(nodes, split_components=True)
        if new_components is None:
            new_components = []

        new_node_sets = [set(n.id for n in comp) for comp in new_components]
        current_user_order = self._user_execution_order.copy()
        final_components = []
        processed_new_indices = set()

        for old_key_node_ids, old_ordered_nodes in current_user_order.items():
            topo_order = [n.id for n in old_ordered_nodes]
            old_node_set = set(old_key_node_ids)
            overlaped_component_index = []
            overlaped_id = []
            for i, new_node_set in enumerate(new_node_sets):
                if i in processed_new_indices:
                    continue
                overlap = len(old_node_set & new_node_set)
                if overlap > 0:
                    for j, nid in enumerate(topo_order):
                        if nid in new_node_set:
                            overlaped_id.append(j)
                            overlaped_component_index.append(i)
                            break
            overlaped_component_index = [overlaped_component_index[k] for k in np.argsort(overlaped_id)]
            if len(overlaped_component_index) > 0:
                for matched_new_idx in overlaped_component_index:
                    matched_new_component = new_components[matched_new_idx]
                    processed_new_indices.add(matched_new_idx)
                    final_components.append(matched_new_component)

        for i, comp in enumerate(new_components):
            if i not in processed_new_indices:
                final_components.append(comp)
        title = SubtitleLabel(f"⏬ 连通图执行顺序")
        self.parent_layout.addWidget(title)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.nodes_card = QWidget(self.parent_panel)
        nodes_layout = QVBoxLayout(self.nodes_card)
        nodes_layout.setContentsMargins(10, 10, 10, 10)
        self._component_cards = []
        final_ordered_components = []
        for i in range(len(final_components)):
            component_card, comp_order = self._create_component_card(nodes_layout, i, final_components)
            final_ordered_components.append(comp_order)
            self._component_cards.append(component_card)

        self._current_components = final_ordered_components
        nodes_layout.addStretch(1)
        scroll = self.parent_panel.set_scrollbar(self.nodes_card)
        layout.addWidget(scroll, 1)
        self.parent_layout.addWidget(widget)

        updated_user_order = {}
        for comp_nodes in final_ordered_components:
            if comp_nodes:
                node_ids = tuple(sorted(n.id for n in comp_nodes))
                updated_user_order[node_ids] = comp_nodes.copy()
        self._user_execution_order = updated_user_order

    def _create_component_card(self, parent_layout, index, components):
        component = components[index]
        topo_sorted_component = topological_sort(component, split_components=False)
        if topo_sorted_component is None:
            topo_sorted_component = component

        component_card = CardWidget(self.parent_panel)
        component_layout = QVBoxLayout(component_card)
        component_layout.setContentsMargins(8, 8, 8, 8)

        header_layout = QHBoxLayout()
        component_title = BodyLabel(f"子连通图 {index + 1} ({len(topo_sorted_component)} 个节点)")
        header_layout.addWidget(component_title)
        move_up_btn = TransparentToolButton(FluentIcon.UP)
        move_down_btn = TransparentToolButton(FluentIcon.DOWN)
        move_up_btn.setFixedSize(24, 24)
        move_down_btn.setFixedSize(24, 24)
        move_up_btn.clicked.connect(lambda _, idx=index: self._move_component(idx, -1))
        move_down_btn.clicked.connect(lambda _, idx=index: self._move_component(idx, 1))
        if index == 0:
            move_up_btn.setEnabled(False)
        if index == len(components) - 1:
            move_down_btn.setEnabled(False)
        header_layout.addWidget(move_up_btn)
        header_layout.addWidget(move_down_btn)
        component_layout.addLayout(header_layout)

        num_items = len(topo_sorted_component)
        estimated_height_for_items = num_items * 40
        total_estimated_height = estimated_height_for_items

        list_identifier = f"component_{index}"
        self._component_nodes_list[list_identifier] = topo_sorted_component
        status_list = [self.main_window.get_node_status(n) for n in topo_sorted_component]
        name_list = [n.name() for n in topo_sorted_component]
        component_list = InternalNodeList(status_list, name_list, self.parent_panel)
        component_list.setFixedHeight(total_estimated_height)

        def on_item_double_clicked(item):
            row = component_list.row(item)
            if 0 <= row < len(topo_sorted_component):
                node_to_center = topo_sorted_component[row]
                self.main_window.canvas_widget.zoom_to_nodes([node_to_center._view])

        component_list.itemDoubleClicked.connect(on_item_double_clicked)
        component_layout.addWidget(component_list)
        parent_layout.addWidget(component_card)
        return component_card, topo_sorted_component

    def _move_component(self, index, direction):
        if not self._current_components or len(self._current_components) <= 1:
            return
        if direction == -1 and index > 0:
            self._current_components[index], self._current_components[index - 1] = \
                self._current_components[index - 1], self._current_components[index]
            self._component_cards[index], self._component_cards[index - 1] = \
                self._component_cards[index - 1], self._component_cards[index]
        elif direction == 1 and index < len(self._current_components) - 1:
            self._current_components[index], self._current_components[index + 1] = \
                self._current_components[index + 1], self._current_components[index]
            self._component_cards[index], self._component_cards[index + 1] = \
                self._component_cards[index + 1], self._component_cards[index]
        else:
            return
        self._rearrange_component_cards()
        self._user_execution_order.clear()
        for comp_nodes in self._current_components:
            if comp_nodes:
                node_ids = tuple(sorted(n.id for n in comp_nodes))
                self._user_execution_order[node_ids] = comp_nodes.copy()

    def _rearrange_component_cards(self):
        nodes_layout = self.nodes_card.layout()
        # 移除strech
        nodes_layout.removeItem(nodes_layout.itemAt(nodes_layout.count() - 1))
        for i in reversed(range(nodes_layout.count())):
            if i > 0:
                item = nodes_layout.itemAt(i)
                if item.widget() and item.widget() != nodes_layout.itemAt(0).widget():
                    nodes_layout.removeItem(item)
        for i, component_card in enumerate(self._component_cards):
            self._update_card_header(component_card, i)
            nodes_layout.addWidget(component_card)
        nodes_layout.addStretch(1)

    def _update_card_header(self, component_card, new_index):
        component_layout = component_card.layout()
        header_layout = component_layout.itemAt(0).layout()
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
        if title_label:
            current_component = self._current_components[new_index]
            title_label.setText(f"子联通图 {new_index + 1} ({len(current_component)} 个节点)")
        if up_btn:
            up_btn.setEnabled(new_index > 0)
        if down_btn:
            down_btn.setEnabled(new_index < len(self._current_components) - 1)
        if up_btn:
            up_btn.disconnect()
            up_btn.clicked.connect(lambda _, idx=new_index: self._move_component(idx, -1))
        if down_btn:
            down_btn.disconnect()
            down_btn.clicked.connect(lambda _, idx=new_index: self._move_component(idx, 1))

    def get_current_order(self):
        """获取当前排列的节点执行顺序"""
        if not self._current_components:
            return []
        execution_order = []
        for component in self._current_components:
            execution_order.extend(component)
        return execution_order

    def reset_components(self):
        """重置当前组件列表"""
        self._current_components = []
