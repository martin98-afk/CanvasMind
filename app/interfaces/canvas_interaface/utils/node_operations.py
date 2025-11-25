# /app/interfaces/canvas_interface/node_operations.py
import uuid

from PyQt5.QtCore import QTimer

from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager
from app.nodes.backdrop_node import ControlFlowBackdrop, ControlFlowIterateNode, ControlFlowLoopNode
from app.nodes.branch_node import create_branch_node
from app.nodes.dynamic_code_node import create_dynamic_code_node
from app.nodes.execute_node import create_node_class
from app.nodes.port_node import CustomPortInputNode, CustomPortOutputNode
from app.nodes.status_node import StatusNode
from app.scan_components import scan_components
from .logger import get_logger

logger = get_logger("NodeOperations")

class NodeOperations:
    def __init__(self, parent, graph, recommendation_engine, thread_pool):
        self.parent = parent
        self.graph = graph
        self.recommendation_engine = recommendation_engine
        self.thread_pool = thread_pool
        self.node_status = {}  # {node_id: status}
        self.node_type_map = {}
        self._node_id_cache = {}  # 缓存：node_id -> node_object
        self._registered_nodes = []
        self._node_id_cache_valid = False  # 标记缓存是否有效
        self._clipboard_data = None
        self._current_recommendation_task = None  # 用于取消旧任务（可选）

    # --- 节点注册 ---
    def _register_builtin_components(self):
        # 迭代节点
        code_node = create_dynamic_code_node(self.parent)
        code_node.__name__ = "DYNAMIC_CODE"
        self.graph.register_node(code_node)

        self.node_type_map[code_node.FULL_PATH] = f"dynamic.{code_node.__name__}"
        # 迭代节点
        iterate_node = ControlFlowIterateNode
        iterate_node.__name__ = "ControlFlowIterateNode"
        self.graph.register_node(iterate_node)
        self.node_type_map[iterate_node.FULL_PATH] = f"control_flow.ControlFlowIterateNode"
        # 循环节点
        loop_node = ControlFlowLoopNode
        loop_node.__name__ = "ControlFlowLoopNode"
        self.graph.register_node(loop_node)
        self.node_type_map[loop_node.FULL_PATH] = f"control_flow.{loop_node.__name__}"
        # 输入端口节点
        input_port_node = CustomPortInputNode
        input_port_node.__name__ = "ControlFlowInputPort"
        self.graph.register_node(input_port_node)
        # 输出端口节点
        output_port_node = CustomPortOutputNode
        output_port_node.__name__ = "ControlFlowOutputPort"
        self.graph.register_node(output_port_node)
        # 注册分支节点
        branch_node = create_branch_node(self.parent)
        branch_node.__name__ = "ControlFlowBranchNode"
        self.graph.register_node(branch_node)
        self.node_type_map[branch_node.FULL_PATH] = f"control_flow.{branch_node.__name__}"

    def register_components(self):
        self._registered_nodes.extend(list(self.graph.registered_nodes()))
        self.graph._node_factory.clear_registered_nodes()
        self.graph._context_menu = {}
        self.graph._register_context_menu()
        self.component_map, self.file_map = scan_components()
        # 重建推荐索引
        self.recommendation_engine._recommendation_cache.clear()
        self.recommendation_engine._build_index(self.component_map)  # 重建索引
        self._register_builtin_components()
        # 普通节点
        nodes_menu = self.graph.get_context_menu('nodes')
        for full_path, comp_cls in self.component_map.items():
            safe_name = full_path.replace("/", "_").replace(" ", "_").replace("-", "_")
            node_class = create_node_class(comp_cls, full_path, self.file_map.get(full_path), self.parent)
            node_class = type(f"Status{node_class.__name__}", (StatusNode, node_class), {})
            node_class.__name__ = f"StatusDynamicNode_{safe_name}"
            self.graph.register_node(node_class)
            self.node_type_map[full_path] = f"dynamic.{node_class.__name__}"
            if f"dynamic.{node_class.__name__}" not in self._registered_nodes:
                nodes_menu.add_command('运行此节点', lambda graph, node: self.parent.run_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('运行到此节点', lambda graph, node: self.parent.run_to(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('从此节点开始运行', lambda graph, node: self.parent.run_from(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('查看节点日志', lambda graph, node: node.show_logs(),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_separator()
                nodes_menu.add_command('调试模式', lambda graph, node: node._toggle_debug_mode(),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('编辑组件', lambda graph, node: self.parent.edit_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('删除节点', lambda graph, node: self.delete_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")

    def on_node_created(self, node):
        self._node_id_cache[node.id] = node
        self._request_recommendations(node)

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

    def delete_node(self, node):
        if node and node.id in self.parent.node_status:
            del self.parent.node_status[node.id]
        # 删除节点后，使缓存无效
        self._invalidate_node_cache()
        self.graph.delete_node(node)
        self.parent.property_panel.update_properties(None)

    def delete_selected_nodes(self, graph):
        for node in graph.selected_nodes():
            if isinstance(node, ControlFlowBackdrop):
                for port in node.input_ports():
                    port.clear_connections(push_undo=True, emit_signal=True)
                for port in node.output_ports():
                    port.clear_connections(push_undo=True, emit_signal=True)
        graph.delete_nodes(graph.selected_nodes())
        self._invalidate_node_cache()

    def _copy_selected_nodes(self):
        selected_nodes = self.graph.selected_nodes()
        if not selected_nodes:
            return
        self._clipboard_data = self.graph.copy_nodes()
        MessageManager.info("复制成功", f"已复制 {len(selected_nodes)} 个节点", self.parent)

    def _paste_nodes(self):
        if not self._clipboard_data:
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
        pasted_nodes = self.graph.paste_nodes(self._clipboard_data)
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
        self._invalidate_node_cache()

    def _request_recommendations(self, node):
        full_path = getattr(node, 'FULL_PATH', None)
        if not full_path:
            self.parent.nav_view.clear_recommendations()
            return
        from app.scheduler.node_recommendation_engine import RecommendationTask
        task = RecommendationTask(self.recommendation_engine, full_path)
        task.signals.finished.connect(self.parent.nav_view.add_recommendations)
        task.signals.error.connect(lambda msg: logger.error(f"推荐失败: {msg}"))
        self.thread_pool.start(task)
        self.parent._current_recommendation_task = task

    def _invalidate_node_cache(self):
        """当节点被创建或删除时，标记缓存无效"""
        self._node_id_cache_valid = False
        self._node_id_cache.clear()  # 可选，清空以节省内存

    def _get_node_by_id_cached(self, node_id):
        """原始方法，保留用于兼容性"""
        if node_id in self._node_id_cache:
            return self._node_id_cache[node_id]
        for node in self.graph.all_nodes():
            if node.id == node_id:
                return node
        return None