# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer, QMimeData
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget
from loguru import logger
from qfluentwidgets import CardWidget, TransparentToolButton, FluentIcon, BodyLabel

from app.utils.utils import topological_sort
from app.widgets.side_dock_area.plugins.property_panel.draggable_container import DraggableContainer
from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList


class NodeListPanelWidget(QWidget):
    def __init__(self, main_window, parent_panel, nodes):
        super().__init__(parent_panel)
        self.main_window = main_window
        self.parent_panel = parent_panel

        # 核心数据结构
        self._current_components = []  # 存储 List[List[Node]]，且内部已排好序
        self._component_history = []  # 记录组件指纹顺序，用于顺序记忆

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

    def _get_comp_fingerprint(self, nodes):
        """生成连通图的唯一指纹（用于顺序记忆）"""
        return tuple(sorted(n.id for n in nodes))

    def update_data(self, nodes):
        """核心逻辑：增量更新并保持用户拖拽后的顺序"""
        # 1. 直接获取带逻辑依赖的拓扑排序分量
        # 这里的 split_components=True 返回的是 List[List[Node]]
        # 且每个 List[Node] 内部已经是排好序的了
        raw_components = topological_sort(nodes, split_components=True, use_logic=True) or []

        # 2. 顺序记忆对齐逻辑
        # 我们根据“节点成员”构建指纹，匹配历史顺序
        new_comp_map = {self._get_comp_fingerprint(c): c for c in raw_components}
        final_ordered_components = []

        # 先按历史记忆填充
        still_exists_fingerprints = []
        for fp in self._component_history:
            if fp in new_comp_map:
                final_ordered_components.append(new_comp_map.pop(fp))
                still_exists_fingerprints.append(fp)

        # 再补充新出现的组件
        for fp, comp in new_comp_map.items():
            final_ordered_components.append(comp)
            still_exists_fingerprints.append(fp)

        self._current_components = final_ordered_components
        self._component_history = still_exists_fingerprints  # 更新记忆

        self._refresh_ui()

    def _refresh_ui(self):
        """渲染 UI 面板"""
        v_bar = self.scroll_area.verticalScrollBar()
        scroll_pos = v_bar.value()

        # 清空布局（保留插入指示线）
        layout = self.nodes_card.layout()
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item.widget() and item.widget() != self.nodes_card.insert_line:
                item.widget().deleteLater()

        self._component_nodes_list.clear()
        self._column_list_widgets.clear()

        # 循环创建卡片
        for i, comp in enumerate(self._current_components):
            self._add_component_card(layout, i, comp)

        layout.addStretch(1)
        QTimer.singleShot(10, lambda: v_bar.setValue(scroll_pos))

    def _add_component_card(self, layout, index, nodes):
        """封装单个卡片的创建逻辑"""

        card = CardWidget(self.nodes_card)
        card._component_index = index
        card_layout = QVBoxLayout(card)

        # 内部 ID 绑定
        list_id = f"comp_{index}"
        self._component_nodes_list[list_id] = nodes

        # 拖拽逻辑：只需传递 index
        def mouseMoveEvent(event):
            if event.buttons() != Qt.LeftButton: return
            drag = QDrag(card)
            mime = QMimeData()
            mime.setText(f"component_index:{index}")
            drag.setMimeData(mime)
            card.hide()
            drag.exec_(Qt.MoveAction)
            card.show()

        card.mouseMoveEvent = mouseMoveEvent

        # Header
        header = QHBoxLayout()
        header.addWidget(BodyLabel(f"执行分量 {index + 1} ({len(nodes)} 节点)"))
        header.addStretch()
        split_btn = TransparentToolButton(FluentIcon.CUT)
        split_btn.clicked.connect(lambda: self._split_at(index))
        header.addWidget(split_btn)
        card_layout.addLayout(header)

        # Node List
        status_list = [self.main_window.get_node_status(n) for n in nodes]
        name_list = [n.name() for n in nodes]
        node_list_widget = InternalNodeList(status_list, name_list, self)

        # 双击定位
        node_list_widget.itemDoubleClicked.connect(
            lambda item: self.main_window.canvas_widget.zoom_to_nodes(
                [nodes[node_list_widget.row(item)]._view]
            )
        )

        node_list_widget.setFixedHeight(max(38 * len(nodes), 40))
        card_layout.addWidget(node_list_widget)

        self._column_list_widgets[list_id] = node_list_widget
        layout.addWidget(card)

    def _split_at(self, index):
        """在选中的位置强行打断连通图顺序"""
        comp = self._current_components[index]
        widget = self._column_list_widgets.get(f"comp_{index}")
        sel_row = widget.get_current_selected_row() if widget else -1

        split_idx = sel_row + 1 if sel_row >= 0 else len(comp) // 2
        if 0 < split_idx < len(comp):
            # 将一个 List 分裂为两个，并更新记忆指纹
            part1, part2 = comp[:split_idx], comp[split_idx:]
            self._current_components[index:index + 1] = [part1, part2]

            # 更新历史顺序指纹列表，确保下次 update_data 依然保持这个手动分割的顺序
            new_history = []
            for c in self._current_components:
                new_history.append(self._get_comp_fingerprint(c))
            self._component_history = new_history

            self._refresh_ui()

    def update_node_list_content(self):
        """增量刷新节点状态，不触发重绘"""
        for list_id, nodes in self._component_nodes_list.items():
            widget = self._column_list_widgets.get(list_id)
            if widget:
                try:
                    stats = [self.main_window.get_node_status(n) for n in nodes]
                    names = [n.name() for n in nodes]
                    widget.update_content(stats, names)
                except Exception as e:
                    logger.error(f"UI增量更新失败: {e}")

    def get_current_order(self):
        """获取最终执行序列"""
        return [node for comp in self._current_components for node in comp]

    def reset_components(self):
        self._current_components = []
        self._component_history = []
        self._refresh_ui()