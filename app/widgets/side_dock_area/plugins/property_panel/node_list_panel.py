# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer, QMimeData
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget

# 注意：这里确保调用的是我们刚才优化过的、支持 use_logic 和视觉排序的 topological_sort
from app.utils.utils import topological_sort
from app.widgets.side_dock_area.plugins.property_panel.draggable_container import DraggableContainer


class NodeListPanelWidget(QWidget):
    """
    深度优化版多节点列表面板。
    保留功能：拖拽排序记忆、手动分割、增量刷新。
    新增功能：支持变量逻辑依赖 ($node_vars)、支持视觉位置 (左上->右下) 自动对齐。
    """

    def __init__(self, main_window, parent_panel, nodes):
        super().__init__(parent_panel)
        self.main_window = main_window
        self.parent_panel = parent_panel

        self._current_components = []
        self._user_execution_order = {}  # 核心记忆：{tuple_of_ids: [ordered_nodes]}
        self._column_list_widgets = {}
        self._component_nodes_list = {}

        self._setup_ui()
        self.update_data(nodes)

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)
        self.nodes_card = DraggableContainer(self)
        self.scroll_area = self.parent_panel.set_scrollbar(self.nodes_card)
        self.main_layout.addWidget(self.scroll_area, 1)

    def update_data(self, nodes):
        """
        更新数据并保持用户记忆。
        这里接入了逻辑依赖识别，如果两个节点有变量引用，它们会被自动划入同一个子图。
        """
        # 1. 调用增强版拓扑排序 (核心改动：加入 use_logic=True)
        # 这会自动处理 $node_vars.xxx$ 并按照视觉坐标排序
        new_components = topological_sort(nodes, split_components=True, use_logic=True) or []

        # 2. 严格保留你原来的“顺序记忆”比对算法
        new_node_sets = [set(n.id for n in comp) for comp in new_components]
        current_user_order = self._user_execution_order.copy()
        final_components = []
        processed_new_indices = set()

        # 根据之前的记忆 key（ID 集合）来匹配新的连通分量
        for old_key_node_ids, old_ordered_nodes in current_user_order.items():
            old_node_set = set(old_key_node_ids)
            matched_indices = []
            first_match_positions = []

            for i, new_node_set in enumerate(new_node_sets):
                if i in processed_new_indices: continue
                # 如果旧组件的节点集合与新组件有交集，说明是同一个逻辑块
                if old_node_set & new_node_set:
                    for j, node in enumerate(old_ordered_nodes):
                        if node.id in new_node_set:
                            first_match_positions.append(j)
                            matched_indices.append(i)
                            break

            if matched_indices:
                # 保持旧有的相对先后顺序
                sorted_pairs = sorted(zip(first_match_positions, matched_indices))
                for _, idx in sorted_pairs:
                    final_components.append(new_components[idx])
                    processed_new_indices.add(idx)

        # 补充新出现的（不在记忆中的）分量
        for i, comp in enumerate(new_components):
            if i not in processed_new_indices:
                final_components.append(comp)

        self._current_components = final_components

        # 3. 刷新 UI
        self._refresh_ui_from_current_components()

    def update_node_list_content(self):
        """增量刷新状态图标（无需重新布局）"""
        if not self._component_nodes_list:
            return

        for list_id, node_list in self._component_nodes_list.items():
            list_widget = self._column_list_widgets.get(list_id)
            if list_widget:
                try:
                    status_list = [n.get_property("_status") for n in node_list]
                    name_list = [n.name() for n in node_list]
                    list_widget.update_content(status_list, name_list)
                except Exception as e:
                    from loguru import logger
                    logger.error(f"刷新节点列表状态失败: {e}")

    def _refresh_ui_from_current_components(self):
        """渲染卡片列表 (供 DraggableContainer 回调)"""
        v_bar = self.scroll_area.verticalScrollBar()
        scroll_pos = v_bar.value()

        layout = self.nodes_card.layout()
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w and w != self.nodes_card.insert_line:
                w.deleteLater()

        self._component_nodes_list.clear()
        self._column_list_widgets.clear()

        for i, comp in enumerate(self._current_components):
            self._create_component_card(layout, i)

        layout.addStretch(1)
        QTimer.singleShot(10, lambda: v_bar.setValue(scroll_pos))

        # 更新记忆指纹：确保手动拖拽排序后，该顺序被记录
        self._user_execution_order.clear()
        for comp in self._current_components:
            if comp:
                key = tuple(sorted(n.id for n in comp))
                self._user_execution_order[key] = comp.copy()

    def _create_component_card(self, parent_layout, index):
        """创建单个子图卡片"""
        from qfluentwidgets import CardWidget, TransparentToolButton, FluentIcon, BodyLabel
        from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList
        from PyQt5.QtGui import QDrag

        component = self._current_components[index]
        # 内部排序同样使用增强版排序 (split_components=False)
        # 这保证了卡片内部节点顺序也符合逻辑依赖和视觉位置
        topo_sorted = topological_sort(component, split_components=False, use_logic=True) or component

        component_card = CardWidget(self.nodes_card)
        comp_layout = QVBoxLayout(component_card)
        component_card._component_index = index

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

        # 标题
        header = QHBoxLayout()
        header.addWidget(BodyLabel(f"子图 {index + 1} ({len(topo_sorted)} 节点)"))
        header.addStretch()

        # 手动切分按钮 (保留原始功能)
        split_btn = TransparentToolButton(FluentIcon.CUT)
        split_btn.clicked.connect(lambda: self._split_component_at_selection(index))
        header.addWidget(split_btn)
        comp_layout.addLayout(header)

        # 节点列表生成
        list_id = f"component_{index}"
        self._component_nodes_list[list_id] = topo_sorted
        status_list = [n.get_property("_status") for n in topo_sorted]
        name_list = [n.name() for n in topo_sorted]

        node_list_widget = InternalNodeList(status_list, name_list, self)
        node_list_widget.itemDoubleClicked.connect(
            lambda item: self.main_window.canvas_widget.zoom_to_nodes(
                [topo_sorted[node_list_widget.row(item)]._view]
            )
        )

        node_list_widget.setFixedHeight(max(40 * len(topo_sorted), 40))
        comp_layout.addWidget(node_list_widget)
        self._column_list_widgets[list_id] = node_list_widget

        parent_layout.addWidget(component_card)

    def _split_component_at_selection(self, index):
        """
        手动分割逻辑：保留功能。
        它会强制把一个子图拆成两个，拆分后的顺序会进入 _user_execution_order 记忆。
        """
        comp = self._current_components[index]
        list_id = f"component_{index}"
        widget = self._column_list_widgets.get(list_id)
        sel = widget.get_current_selected_row() if widget else -1

        split_pt = sel + 1 if sel >= 0 else len(comp) // 2
        if 0 < split_pt < len(comp):
            # 这里的切分会改变 _current_components 的结构
            self._current_components[index:index + 1] = [comp[:split_pt], comp[split_pt:]]
            # 刷新会触发 _user_execution_order 的重新采样，从而记住这次切分
            self._refresh_ui_from_current_components()

    def get_current_order(self):
        res = []
        for c in self._current_components: res.extend(c)
        return res

    def reset_components(self):
        self._current_components = []
        self._user_execution_order.clear()
        self._refresh_ui_from_current_components()