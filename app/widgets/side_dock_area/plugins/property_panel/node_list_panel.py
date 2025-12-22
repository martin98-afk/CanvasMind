# -*- coding: utf-8 -*-
import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QListWidgetItem, QFrame
from PyQt5.QtCore import Qt, QMimeData, QTimer
from PyQt5.QtGui import QDrag, QPainter, QColor
from qfluentwidgets import (
    CardWidget, BodyLabel, SubtitleLabel,
    TransparentToolButton, FluentIcon, InfoBar, InfoBarPosition
)

from app.utils.utils import topological_sort
from app.widgets.side_dock_area.plugins.property_panel.draggable_container import DraggableContainer
from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList


# ===== 主控件 =====
class NodeListPanelWidget:
    def __init__(self, main_window, parent_panel, parent_layout):
        self.main_window = main_window
        self.parent_panel = parent_panel
        self.parent_layout = parent_layout

        self._current_components = []
        self._user_execution_order = {}

        self._component_cards = []
        self._component_nodes_list = {}
        self._column_list_widgets = {}
        self._selected_row_in_component = {}

        self.nodes_card = None

    def build_ui(self, nodes):
        new_components = topological_sort(nodes, split_components=True) or []
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
                    for j, node in enumerate(old_ordered_nodes):
                        if node.id in new_node_set:
                            first_match_positions.append(j)
                            matched_indices.append(i)
                            break
            if matched_indices:
                sorted_pairs = sorted(zip(first_match_positions, matched_indices))
                for _, idx in sorted_pairs:
                    final_components.append(new_components[idx])
                    processed_new_indices.add(idx)

        for i, comp in enumerate(new_components):
            if i not in processed_new_indices:
                final_components.append(comp)

        self._current_components = final_components
        self._refresh_ui_from_current_components()

    def _refresh_ui_from_current_components(self):
        while self.parent_layout.count():
            item = self.parent_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        title = SubtitleLabel("⏬ 连通图执行顺序")
        self.parent_layout.addWidget(title)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.nodes_card = DraggableContainer(self)
        nodes_layout = self.nodes_card.layout()
        nodes_layout.setSpacing(8)  # 与容器一致

        self._component_cards = []
        self._component_nodes_list.clear()
        self._column_list_widgets.clear()
        self._selected_row_in_component.clear()

        for i, comp in enumerate(self._current_components):
            card = self._create_component_card(nodes_layout, i)
            self._component_cards.append(card)

        nodes_layout.addStretch(1)

        scroll_area = self.parent_panel.set_scrollbar(self.nodes_card)
        layout.addWidget(scroll_area, 1)
        self.parent_layout.addWidget(widget)

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

        component_card._drag_start_pos = None
        component_card._component_index = index

        def card_mouse_press(event):
            if event.button() == Qt.LeftButton:
                component_card._drag_start_pos = event.pos()
            event.accept()

        def card_mouse_move(event):
            if not (event.buttons() & Qt.LeftButton):
                return
            if component_card._drag_start_pos is None:
                return
            if (event.pos() - component_card._drag_start_pos).manhattanLength() < 5:
                return

            drag = QDrag(component_card)
            mime = QMimeData()
            mime.setText(f"component_index:{component_card._component_index}")
            drag.setMimeData(mime)

            # 创建半透明预览图
            pixmap = component_card.grab()
            ghost = pixmap.copy()
            painter = QPainter(ghost)
            painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            painter.fillRect(ghost.rect(), QColor(0, 0, 0, 120))
            painter.end()
            drag.setPixmap(ghost)
            drag.setHotSpot(event.pos())

            # ✅ 隐藏原卡片，避免视觉重叠
            component_card.setVisible(False)
            drag.exec_(Qt.MoveAction)
            component_card.setVisible(True)  # 恢复

        component_card.mousePressEvent = card_mouse_press
        component_card.mouseMoveEvent = card_mouse_move
        component_card.setMouseTracking(True)

        # Header
        header_layout = QHBoxLayout()
        title_label = BodyLabel(f"子连通图 {index + 1} ({len(topo_sorted)} 个节点)")
        title_label.setToolTip("拖拽整个卡片可调整执行顺序")
        title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # ✅ 关键：让标题不拦截鼠标事件
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        header_layout.addWidget(title_label)

        # 分割按钮
        split_btn = TransparentToolButton(FluentIcon.CUT)
        split_btn.setFixedSize(28, 28)
        split_btn.setToolTip("在选中的节点之后分割\n（未选中则在中间分割）")
        if len(topo_sorted) <= 1:
            split_btn.hide()
        split_btn.clicked.connect(lambda _, idx=index: self._split_component_at_selection(idx))

        header_layout.addStretch(1)
        header_layout.addWidget(split_btn)

        comp_layout.addLayout(header_layout)

        # 节点列表（保持不变）
        list_id = f"component_{index}"
        self._component_nodes_list[list_id] = topo_sorted

        status_list = [self.main_window.get_node_status(n) for n in topo_sorted]
        name_list = [n.name() for n in topo_sorted]

        node_list_widget = InternalNodeList(status_list, name_list, self.parent_panel)
        node_list_widget.setFixedHeight(max(40 * len(topo_sorted), 40))

        def on_double_click(item):
            row = node_list_widget.row(item)
            if 0 <= row < len(topo_sorted):
                node = topo_sorted[row]
                self.main_window.canvas_widget.zoom_to_nodes([node._view])

        node_list_widget.itemDoubleClicked.connect(on_double_click)

        comp_layout.addWidget(node_list_widget)
        self._column_list_widgets[list_id] = node_list_widget

        parent_layout.addWidget(component_card)
        return component_card

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
            split_point = selected_row + 1 if selected_row >= 0 else len(comp) // 2
        else:
            split_point = len(comp) // 2

        if split_point <= 0 or split_point >= len(comp):
            return

        part1 = comp[:split_point]
        part2 = comp[split_point:]

        self._current_components[index:index + 1] = [part1, part2]
        self._refresh_ui_from_current_components()

        InfoBar.info(
            "已分割",
            f"子连通图 {index + 1} 已分割为两个",
            duration=1500,
            parent=self.main_window
        )

    def update_node_list_content(self):
        if not self._component_nodes_list:
            return
        for list_id, node_list in self._component_nodes_list.items():
            widget = self._column_list_widgets.get(list_id)
            if widget:
                status_list = [self.main_window.get_node_status(n) for n in node_list]
                name_list = [n.name() for n in node_list]
                widget.update_content(status_list, name_list)

    def get_current_order(self):
        result = []
        for comp in self._current_components:
            result.extend(comp)
        return result

    def reset_components(self):
        self._current_components = []
        self._user_execution_order.clear()