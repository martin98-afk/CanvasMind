# -*- coding: utf-8 -*-
import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QSizePolicy, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer, QMimeData
from qfluentwidgets import SubtitleLabel

from app.utils.utils import topological_sort
from app.widgets.side_dock_area.plugins.property_panel.draggable_container import DraggableContainer


class NodeListPanelWidget(QWidget):
    """
    优化后的多节点列表面板。
    支持拖拽排序记忆、增量更新和连通图分割。
    """

    def __init__(self, main_window, parent_panel, nodes):
        super().__init__(parent_panel)
        self.main_window = main_window
        self.parent_panel = parent_panel

        self._current_components = []
        self._user_execution_order = {}
        self._column_list_widgets = {}
        self._component_nodes_list = {}

        self._setup_ui()
        self.update_data(nodes)

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)

        # 标题
        self.title_label = SubtitleLabel("⏬ 连通图执行顺序")
        self.main_layout.addWidget(self.title_label)

        # 创建你提供的可拖拽容器
        # 注意：现在 self 就是 panel_widget
        self.nodes_card = DraggableContainer(self)

        # 将容器包装进滚动区域
        self.scroll_area = self.parent_panel.set_scrollbar(self.nodes_card)
        self.main_layout.addWidget(self.scroll_area, 1)

    def update_data(self, nodes):
        """外部调用接口：更新数据并刷新 UI"""
        # 1. 拓扑排序与顺序记忆逻辑 (保留你原有的逻辑)
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
                if i in processed_new_indices: continue
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

        # 2. 调用刷新
        self._refresh_ui_from_current_components()

    def update_node_list_content(self):
        """
        外部调用接口：增量刷新节点列表中的状态图标和名称。
        用于在节点运行过程中实时更新 UI，而不触发重新布局。
        """
        if not self._component_nodes_list:
            return

        for list_id, node_list in self._component_nodes_list.items():
            # 获取对应的 InternalNodeList 控件
            list_widget = self._column_list_widgets.get(list_id)
            if list_widget:
                try:
                    # 获取最新的状态和名称
                    status_list = [self.main_window.get_node_status(n) for n in node_list]
                    name_list = [n.name() for n in node_list]

                    # 调用 InternalNodeList 自身的增量更新方法
                    list_widget.update_content(status_list, name_list)
                except Exception as e:
                    from loguru import logger
                    logger.error(f"刷新节点列表状态失败: {e}")

    def _refresh_ui_from_current_components(self):
        """渲染卡片列表 (供 DraggableContainer 回调)"""
        # 记录当前滚动位置
        v_bar = self.scroll_area.verticalScrollBar()
        scroll_pos = v_bar.value()

        # 清理容器布局 (除了插入线 Indicator)
        layout = self.nodes_card.layout()
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w and w != self.nodes_card.insert_line:
                w.deleteLater()

        self._component_nodes_list.clear()
        self._column_list_widgets.clear()

        # 重新创建卡片
        # 为了保持 NodeListPanelWidget 完整，建议直接把 _create_component_card 移入此类
        for i, comp in enumerate(self._current_components):
            self._create_component_card(layout, i)

        layout.addStretch(1)

        # 恢复滚动位置
        QTimer.singleShot(10, lambda: v_bar.setValue(scroll_pos))

        # 更新顺序记忆
        self._user_execution_order.clear()
        for comp in self._current_components:
            if comp:
                key = tuple(sorted(n.id for n in comp))
                self._user_execution_order[key] = comp.copy()

    def _create_component_card(self, parent_layout, index):
        """创建单个连通图卡片 (复用你之前的逻辑)"""
        from qfluentwidgets import CardWidget, TransparentToolButton, FluentIcon, BodyLabel
        from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList
        from PyQt5.QtGui import QDrag

        component = self._current_components[index]
        topo_sorted = topological_sort(component, split_components=False) or component

        component_card = CardWidget(self.nodes_card)
        comp_layout = QVBoxLayout(component_card)
        component_card._component_index = index

        # 拖拽发起逻辑
        def mouseMoveEvent(event):
            if not (event.buttons() & Qt.LeftButton): return
            drag = QDrag(component_card)
            mime = QMimeData()
            mime.setText(f"component_index:{index}")
            drag.setMimeData(mime)
            drag.setPixmap(component_card.grab())
            component_card.hide()
            drag.exec_(Qt.MoveAction)
            component_card.show()

        component_card.mouseMoveEvent = mouseMoveEvent

        # 标题栏
        header = QHBoxLayout()
        header.addWidget(BodyLabel(f"子连通图 {index + 1} ({len(topo_sorted)} 节点)"))
        split_btn = TransparentToolButton(FluentIcon.CUT)
        split_btn.clicked.connect(lambda: self._split_component_at_selection(index))
        header.addStretch()
        header.addWidget(split_btn)
        comp_layout.addLayout(header)

        # 节点列表
        list_id = f"component_{index}"
        self._component_nodes_list[list_id] = topo_sorted
        status_list = [self.main_window.get_node_status(n) for n in topo_sorted]
        name_list = [n.name() for n in topo_sorted]
        node_list_widget = InternalNodeList(status_list, name_list, self)
        def on_double_click(item):
            row = node_list_widget.row(item)
            if 0 <= row < len(topo_sorted):
                node = topo_sorted[row]
                self.main_window.canvas_widget.zoom_to_nodes([node._view])

        node_list_widget.itemDoubleClicked.connect(on_double_click)
        node_list_widget.setFixedHeight(max(40 * len(topo_sorted), 40))
        comp_layout.addWidget(node_list_widget)
        self._column_list_widgets[list_id] = node_list_widget

        parent_layout.addWidget(component_card)

    def _split_component_at_selection(self, index):
        """连通图分割逻辑"""
        comp = self._current_components[index]
        list_id = f"component_{index}"
        widget = self._column_list_widgets.get(list_id)
        sel = widget.get_current_selected_row() if widget else -1
        split_pt = sel + 1 if sel >= 0 else len(comp) // 2
        if 0 < split_pt < len(comp):
            self._current_components[index:index + 1] = [comp[:split_pt], comp[split_pt:]]
            self._refresh_ui_from_current_components()

    def get_current_order(self):
        res = []
        for c in self._current_components: res.extend(c)
        return res

    def reset_components(self):
        self._current_components = []
        self._user_execution_order.clear()
        self._refresh_ui_from_current_components()