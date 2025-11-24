# /app/interfaces/canvas_interface/node_operations.py
import uuid
from PyQt5.QtCore import QTimer, QPoint, Qt
from PyQt5.QtWidgets import QFrame
from qfluentwidgets import TransparentToolButton, FluentIcon, RoundMenu, Action
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.utils.utils import get_icon
from app.interfaces.canvas_interaface.constants import MAX_VISIBLE_QUICK_BUTTONS
from .logger import get_logger
from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager

logger = get_logger("NodeOperations")

class NodeOperations:
    def __init__(self, parent, graph, component_map, manager, thread_pool):
        self.parent = parent
        self.graph = graph
        self.component_map = component_map
        self.manager = manager
        self.thread_pool = thread_pool
        self._hidden_quick_components = []

    def create_next_node(self, key, icon_path=None):
        selected_nodes = self.graph.selected_nodes()
        try:
            node = self.graph.create_node(key)
        except Exception:
            node_type = self.parent.node_type_map.get(key)
            node = self.graph.create_node(node_type)
        QTimer.singleShot(0, lambda: self.parent.property_panel.update_properties(node))
        if icon_path and isinstance(icon_path, str):
            node.set_icon(icon_path)
        if selected_nodes:
            node_x = selected_nodes[0].x_pos()
            node_y = selected_nodes[0].y_pos()
            node.set_pos(node_x + selected_nodes[0].view.width + 100, node_y)
        else:
            viewer = self.graph.viewer()
            viewport_center = viewer.viewport().rect().center()
            scene_center = viewer.mapToScene(viewport_center)
            node.set_pos(scene_center.x(), scene_center.y())

    def create_backdrop_node(self, key):
        selected_nodes = self.graph.selected_nodes()
        input_port_node = None
        output_port_node = None
        other_nodes = []

        for node in selected_nodes:
            if node.type_ == "control_flow.ControlFlowInputPort":
                input_port_node = node
            elif node.type_ == "control_flow.ControlFlowOutputPort":
                output_port_node = node
            elif isinstance(node, ControlFlowBackdrop):
                MessageManager.error("错误", "当前版本不支持嵌套循环或迭代结构！", self.parent)
                return
            else:
                other_nodes.append(node)

        viewer = self.graph.viewer()
        viewport_center = viewer.viewport().rect().center()
        scene_center = viewer.mapToScene(viewport_center)
        center_x, center_y = scene_center.x(), scene_center.y()

        if not selected_nodes:
            input_port_node = self.graph.create_node("control_flow.ControlFlowInputPort")
            output_port_node = self.graph.create_node("control_flow.ControlFlowOutputPort")
            input_port_node.set_pos(center_x - 500, center_y - input_port_node.view.height)
            output_port_node.set_pos(center_x + 500, center_y + output_port_node.view.height + 200)
            nodes_to_wrap = [input_port_node, output_port_node]
        else:
            unconnected_inputs = []
            unconnected_outputs = []
            for node in other_nodes:
                for input_port in node.input_ports():
                    if not input_port.connected_ports():
                        unconnected_inputs.append((node, input_port))
                for output_port in node.output_ports():
                    if not output_port.connected_ports():
                        unconnected_outputs.append((node, output_port))

            if not input_port_node:
                input_port_node = self.graph.create_node("control_flow.ControlFlowInputPort")
                if other_nodes:
                    min_x = min(n.x_pos() for n in other_nodes)
                    avg_y = sum(n.y_pos() for n in other_nodes) / len(other_nodes)
                    input_port_node.set_pos(min_x - 300, avg_y - input_port_node.view.height / 2)
                else:
                    input_port_node.set_pos(center_x - 250, center_y - input_port_node.view.height / 2)

            if not output_port_node:
                output_port_node = self.graph.create_node("control_flow.ControlFlowOutputPort")
                if other_nodes:
                    max_x = max(n.x_pos() + n.view.width for n in other_nodes)
                    avg_y = sum(n.y_pos() for n in other_nodes) / len(other_nodes)
                    output_port_node.set_pos(max_x + 150, avg_y - output_port_node.view.height / 2)
                else:
                    output_port_node.set_pos(center_x + 250, center_y - output_port_node.view.height / 2)

            nodes_to_wrap = other_nodes + [input_port_node, output_port_node]

        if not nodes_to_wrap:
            MessageManager.warning("创建失败", "没有可包裹的节点！", self.parent)
            return

        backdrop_node = self.graph.create_node(f"control_flow.{key}")
        backdrop_node.wrap_nodes(nodes_to_wrap)
        [node.set_selected(True) for node in nodes_to_wrap]
        QTimer.singleShot(0, lambda: self.parent.property_panel.update_properties(backdrop_node))

        if key == "ControlFlowIterateNode":
            backdrop_node.model.set_property("loop_nums", 3)

    def delete_selected_nodes(self, graph):
        for node in graph.selected_nodes():
            if isinstance(node, ControlFlowBackdrop):
                for port in node.input_ports():
                    port.clear_connections(push_undo=True, emit_signal=True)
                for port in node.output_ports():
                    port.clear_connections(push_undo=True, emit_signal=True)
        graph.delete_nodes(graph.selected_nodes())
        self.parent._invalidate_node_cache()

    def _copy_selected_nodes(self):
        selected_nodes = self.graph.selected_nodes()
        if not selected_nodes:
            return
        self.parent._clipboard_data = self.graph.copy_nodes()
        MessageManager.info("复制成功", f"已复制 {len(selected_nodes)} 个节点", self.parent)

    def _paste_nodes(self):
        if not self.parent._clipboard_data:
            return
        selected_nodes = self.graph.selected_nodes()
        if selected_nodes:
            avg_x = sum(n.pos()[0] for n in selected_nodes) / len(selected_nodes)
            avg_y = sum(n.pos()[1] for n in selected_nodes) / len(selected_nodes)
            offset = (50, 50)
        else:
            viewer = self.graph.viewer()
            center = viewer.mapToScene(viewer.rect().center())
            avg_x, avg_y = center.x(), center.y()
            offset = (0, 0)
        pasted_nodes = self.graph.paste_nodes(self.parent._clipboard_data)
        if pasted_nodes:
            min_x = min(n.pos()[0] for n in pasted_nodes)
            min_y = min(n.pos()[1] for n in pasted_nodes)
            for node in pasted_nodes:
                node.set_property("persistent_id", str(uuid.uuid4()))
                x, y = node.pos()
                new_x = x - min_x + avg_x + offset[0]
                new_y = y - min_y + avg_y + offset[1]
                node.set_pos(new_x, new_y)
            MessageManager.info("粘贴成功", f"已粘贴 {len(pasted_nodes)} 个节点", self.parent)
        self.parent._invalidate_node_cache()

    def create_floating_nodes(self):
        container = self.parent.nodes_container = TransparentToolButton(parent=self.parent.canvas_widget)
        self.parent.nodes_container = QWidget(self.parent.canvas_widget)
        self.parent.nodes_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._update_nodes_container_position()

        layout = self.parent.node_layout = QVBoxLayout(self.parent.nodes_container)
        layout.setSpacing(3)
        layout.setContentsMargins(0, 0, 0, 0)

        buttons = [
            ("更新", "创建迭代", lambda: self.create_backdrop_node("ControlFlowIterateNode")),
            ("无限", "创建循环", lambda: self.create_backdrop_node("ControlFlowLoopNode")),
            ("条件分支", "创建分支", lambda: self.create_next_node("control_flow.ControlFlowBranchNode")),
            ("代码执行", "创建代码编辑", lambda: self.create_next_node("dynamic.DYNAMIC_CODE")),
            ("工具", "创建工具调用", lambda: self.create_next_node("dynamic.StatusDynamicNode_大模型组件_工具调用")),
        ]

        for icon_name, tooltip, slot in buttons:
            btn = TransparentToolButton(get_icon(icon_name), self.parent)
            btn.setIconSize(20, 20)
            btn.setToolTip(tooltip)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #555;")
        layout.addWidget(separator)

        self.parent.visible_quick_container = QWidget(self.parent.nodes_container)
        self.parent.visible_quick_layout = QVBoxLayout(self.parent.visible_quick_container)
        self.parent.visible_quick_layout.setSpacing(3)
        self.parent.visible_quick_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.parent.visible_quick_container)

        self.parent.more_quick_button = TransparentToolButton(FluentIcon.MORE, self.parent)
        self.parent.more_quick_button.setIconSize(20, 20)
        self.parent.more_quick_button.setToolTip("更多快捷组件")
        self.parent.more_quick_menu = RoundMenu(parent=self.parent)
        self.parent.more_quick_button.clicked.connect(self._show_more_quick_menu)
        layout.addWidget(self.parent.more_quick_button)

        self.parent.add_quick_btn = TransparentToolButton(FluentIcon.ADD, self.parent)
        self.parent.add_quick_btn.setIconSize(20, 20)
        self.parent.add_quick_btn.setToolTip("添加快捷组件")
        self.parent.add_quick_btn.clicked.connect(self.parent.quick_manager.open_add_dialog)
        layout.addWidget(self.parent.add_quick_btn)

        self.parent.nodes_container.setLayout(layout)
        self.parent.nodes_container.show()
        self._refresh_quick_buttons()

    def _show_more_quick_menu(self):
        self.parent.more_quick_menu.clear()
        for full_path, icon_path in self._hidden_quick_components:
            comp_name = full_path.split("/")[-1].replace(".py", "")
            icon = self._resolve_icon(icon_path)
            action = Action(
                icon, f"创建 {comp_name}",
                triggered=lambda _, fp=full_path, ip=icon_path: self.create_next_node(fp, ip)
            )
            action.setProperty("full_path", full_path)
            self.parent.more_quick_menu.addAction(action)
        self.parent.more_quick_menu.exec_(self.parent.more_quick_button.mapToGlobal(QPoint(0, self.parent.more_quick_button.height())))

    def _resolve_icon(self, icon_path):
        from PyQt5.QtGui import QIcon
        if icon_path and icon_path.startswith("builtin:\\"):
            icon_name = icon_path.split("\\")[-1]
            return FluentIcon[icon_name]
        elif icon_path and QIcon(icon_path).isNull() is False:
            return QIcon(icon_path)
        return FluentIcon.APPLICATION

    def _refresh_quick_buttons(self):
        all_quick = self.parent.quick_manager.get_quick_components()
        while self.parent.visible_quick_layout.count():
            item = self.parent.visible_quick_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.parent.more_quick_menu.clear()
        self._hidden_quick_components = []

        for i, qc in enumerate(all_quick):
            full_path = qc["full_path"]
            comp_name = full_path.split("/")[-1].replace(".py", "")
            icon_path = qc.get("icon_path")
            icon = self._resolve_icon(icon_path)

            if i < MAX_VISIBLE_QUICK_BUTTONS:
                btn = TransparentToolButton(icon, self.parent)
                btn.setIconSize(20, 20)
                btn.setToolTip(f"创建 {comp_name}")
                btn.setProperty("full_path", full_path)
                btn.clicked.connect(lambda _, fp=full_path, ip=icon_path: self.create_next_node(fp, ip))
                btn.setContextMenuPolicy(Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, b=btn, fp=full_path: self._show_quick_button_menu(b, fp, pos)
                )
                self.parent.visible_quick_layout.addWidget(btn)
            else:
                self._hidden_quick_components.append((full_path, icon_path))

        self.parent.more_quick_button.setVisible(len(self._hidden_quick_components) > 0)
        QTimer.singleShot(0, self._update_nodes_container_position)

    def _show_quick_button_menu(self, button, full_path, pos):
        menu = RoundMenu()
        menu.addAction(Action("从快捷栏移除", triggered=lambda: self.parent.quick_manager.remove_component(full_path)))
        menu.exec_(button.mapToGlobal(pos))

    def _update_nodes_container_position(self):
        if hasattr(self.parent, 'nodes_container') and self.parent.canvas_widget:
            self.parent.nodes_container.adjustSize()
            y = max(50, (self.parent.canvas_widget.height() - self.parent.nodes_container.height()) // 2)
            self.parent.nodes_container.move(0, y)

    def _request_recommendations(self, node):
        full_path = getattr(node, 'FULL_PATH', None)
        if not full_path:
            self.parent.nav_view.clear_recommendations()
            return
        from app.scheduler.node_recommendation_engine import RecommendationTask
        task = RecommendationTask(self.manager.recommendation_engine, full_path)
        task.signals.finished.connect(self.parent.nav_view.add_recommendations)
        task.signals.error.connect(lambda msg: logger.error(f"推荐失败: {msg}"))
        self.thread_pool.start(task)
        self.parent._current_recommendation_task = task