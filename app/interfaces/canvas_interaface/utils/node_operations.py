# /app/interfaces/canvas_interface/node_operations.py
import shutil
import uuid

import orjson
from NodeGraphQt import GroupNode
from NodeGraphQt.nodes.port_node import PortInputNode, PortOutputNode
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
from qfluentwidgets import Theme, getIconColor, FluentIcon
from qtpy import QtWidgets

from app.interfaces.canvas_interaface.widgets.graph_menu import CustomGraphMenu
from app.interfaces.canvas_interaface.utils.message_manager import MessageManager
from app.nodes.backdrop_node import (
    ControlFlowBackdrop,
    ControlFlowIterateNode,
    ControlFlowLoopNode,
)
from app.nodes.branch_node import create_branch_node
from app.nodes.dynamic_code_node import create_dynamic_code_node
from app.nodes.ai_code_node import create_ai_code_node
from app.nodes.execute_node import create_node_class
from app.nodes.group_node import GroupPortOutputNode, GroupPortInputNode
from app.nodes.multimedia_node import create_media_node
from app.nodes.port_node import CustomPortInputNode, CustomPortOutputNode
from app.nodes.sticky_note import create_sticky_note_node
from app.nodes.trigger_node import create_trigger_node
from app.scan_components import ComponentScanner
from app.utils.utils import get_icon
from app.widgets.custom_nodegraphqt.sticky_note_item import StickyNoteItem
from .logger import get_logger

logger = get_logger("NodeOperations")


class NodeOperations:
    def __init__(self, parent, graph, recommendation_engine, thread_pool):
        self.parent = parent
        self.graph = graph
        self.recommendation_engine = recommendation_engine
        self.thread_pool = thread_pool
        self.graph_menu = None
        self._node_id_cache_valid = False  # 标记缓存是否有效
        self._current_recommendation_task = None  # 用于取消旧任务（可选）
        self._node_id_cache = {}  # 缓存：node_id -> node_object
        self.graph_menu = CustomGraphMenu(graph, self.parent.nav_panel, self.parent)

    def _reset_registered(self):
        self.node_type_map = {}
        self.node_uuid_map = {}
        self.name2type = {}

    # --- 内置节点注册 ---
    def _register_builtin_components(self):
        # AI代码生成节点
        ai_node = create_ai_code_node(self.parent)
        ai_node.__name__ = "AI_CODE"
        self.graph.register_node(ai_node)
        self.node_type_map[ai_node.FULL_PATH] = f"ai.{ai_node.__name__}"
        # 动态代码节点
        code_node = create_dynamic_code_node(self.parent)
        code_node.__name__ = "DYNAMIC_CODE"
        self.graph.register_node(code_node)
        self.node_type_map[code_node.FULL_PATH] = f"dynamic.{code_node.__name__}"
        # 迭代节点
        iterate_node = ControlFlowIterateNode
        iterate_node.__name__ = "ControlFlowIterateNode"
        self.graph.register_node(iterate_node)
        self.node_type_map[iterate_node.FULL_PATH] = (
            f"control_flow.ControlFlowIterateNode"
        )
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
        # 注释节点
        sticky_note = create_sticky_note_node(self.graph, self.parent)
        sticky_note.__name__ = "StickyNote"
        self.graph.register_node(sticky_note)
        # 注册分支节点
        branch_node = create_branch_node(self.parent)
        branch_node.__name__ = "ControlFlowBranchNode"
        self.graph.register_node(branch_node)
        self.node_type_map[branch_node.FULL_PATH] = (
            f"control_flow.{branch_node.__name__}"
        )
        # 子工作流节点
        trigger_node = create_trigger_node(self.parent)
        trigger_node.__name__ = "trigger"
        self.graph.register_node(trigger_node)
        self.node_type_map[trigger_node.FULL_PATH] = f"general.{trigger_node.__name__}"
        # 输入端口节点
        input_port_node = GroupPortInputNode
        input_port_node.__name__ = "GroupPortInputNode"
        self.graph.register_node(input_port_node)
        # 输出端口节点
        output_port_node = GroupPortOutputNode
        output_port_node.__name__ = "GroupPortOutputNode"
        self.graph.register_node(output_port_node)
        # 注册图表绘制节点
        media_node = create_media_node(self.parent)
        media_node.__name__ = "MediaNode"
        self.graph.register_node(media_node)
        self.node_type_map[media_node.FULL_PATH] = f"visualize.{media_node.__name__}"

    def register_components(self):
        try:
            self._reset_registered()
            self.graph._node_factory.clear_registered_nodes()
            self._register_builtin_components()
            component_map, file_map = ComponentScanner().get_components()
            node_class_names = []
            # 普通节点
            for full_path, comp_cls in component_map.items():
                if f"StatusDynamicNode_{comp_cls.uuid}" in node_class_names:
                    continue
                node_class = create_node_class(
                    full_path, file_map.get(full_path), self.parent
                )
                node_class.__name__ = f"StatusDynamicNode_{comp_cls.uuid}"
                node_class_names.append(node_class.__name__)
                self.graph.register_node(node_class)
                self.node_type_map[full_path] = f"dynamic.{node_class.__name__}"
                self.node_uuid_map[comp_cls.uuid] = f"dynamic.{node_class.__name__}"
                self.name2type[comp_cls.name] = f"dynamic.{node_class.__name__}"

        except Exception as e:
            logger.exception("register_components 执行失败！")  # ← 关键

    def setup_graph_menu(self, viewer):
        """注入函数"""
        left_panel = self.parent.nav_panel
        left_panel.draggable_tree.filter_changed_signal.connect(
            self.graph_menu.set_category_filter
        )
        initial_cats = left_panel.draggable_tree.tree._selected_categories
        self.graph_menu.set_category_filter(initial_cats)
        viewer._custom_menu = self.graph_menu
        original_context_menu_event = viewer.contextMenuEvent

        def custom_context_menu_event(event):
            # 获取点击位置的 Item
            item = viewer.itemAt(event.pos())

            show_custom_bg_menu = False

            if item is None:
                # 1. 点在完全空白处 -> 显示自定义菜单
                show_custom_bg_menu = True

            elif isinstance(item, StickyNoteItem):
                # 2. 点在 StickyNoteItem 上
                # 需要将 View 的坐标转为 Item 的局部坐标来判断点击位置
                # event.pos() 是 View 坐标 -> mapToScene -> mapFromScene
                scene_pos = viewer.mapToScene(event.pos())
                local_pos = item.mapFromScene(scene_pos)

                # 如果点击的是 Header 区域，显示原生菜单（比如删除节点）
                # 如果点击的是 躯干区域，显示自定义背景菜单
                if local_pos.y() > item._header_height:
                    show_custom_bg_menu = True
                else:
                    show_custom_bg_menu = False

            # 执行显示逻辑
            if show_custom_bg_menu:
                self.graph_menu.show_at_cursor(event.globalPos())
                event.accept()
            else:
                # 其他情况（点击了普通节点、Note的标题栏、Note内部的文字块）-> 原生逻辑
                original_context_menu_event(event)

        viewer.contextMenuEvent = custom_context_menu_event

    def setup_context_menu(self):
        self.setup_graph_menu(self.graph.viewer())
        # 画布右键菜单注册
        graph_menu = self.graph.get_context_menu("graph")
        graph_menu.add_command(
            "运行工作流", self.parent.canvas_runner.run_workflow, "Ctrl+R"
        )
        graph_menu.add_command("保存工作流", self.parent.save_full_workflow, "Ctrl+S")
        graph_menu.add_command("撤销", self.parent._undo, "Ctrl+Z")
        graph_menu.add_command("重做", self.parent._redo, "Ctrl+Y")  # 或 'Ctrl+Shift+Z'
        graph_menu.add_command("自动布局", self.parent._auto_layout_selected, "Ctrl+L")
        graph_menu.add_command(
            "删除选中",
            lambda graph: (
                self.parent.node_operations.delete_selected_nodes(graph),
                self.parent.property_panel.update_properties(None),
            ),
            "Del",
        )
        # 节点右键菜单注册
        nodes_menu = self.graph.get_context_menu("nodes")
        for special_node in [
            "visualize.MediaNode",
            "dynamic.DYNAMIC_CODE",
            "ai.AI_CODE",
            "control_flow.ControlFlowIterateNode",
            "control_flow.ControlFlowLoopNode",
            "control_flow.ControlFlowBranchNode",
            "general.trigger",
        ]:
            nodes_menu.add_command(
                "运行此节点",
                lambda graph, node: self.parent.run_node(node),
                node_type=special_node,
                icon=get_icon("运行"),
            )
            nodes_menu.add_command(
                "运行到此节点",
                lambda graph, node: self.parent.run_to(node),
                node_type=special_node,
                icon=get_icon("运行到此处"),
            )
            nodes_menu.add_command(
                "从此节点开始运行",
                lambda graph, node: self.parent.run_from(node),
                node_type=special_node,
                icon=get_icon("从此处运行"),
            )
            nodes_menu.add_separator(node_type=special_node)
            if special_node == "dynamic.DYNAMIC_CODE":
                nodes_menu.add_command(
                    "固化为组件",
                    lambda graph, node: node.save_to_component(),
                    node_type=special_node,
                    icon=get_icon("组件"),
                )
                nodes_menu.add_command(
                    "查看节点日志",
                    lambda graph, node: node.show_logs(),
                    node_type=special_node,
                    icon=get_icon("系统运行日志"),
                )
            elif special_node == "ai.AI_CODE":
                nodes_menu.add_command(
                    "固化为组件",
                    lambda graph, node: node.save_to_component(),
                    node_type=special_node,
                    icon=get_icon("组件"),
                )
                nodes_menu.add_command(
                    "查看节点日志",
                    lambda graph, node: node.show_logs(),
                    node_type=special_node,
                    icon=get_icon("系统运行日志"),
                )
            nodes_menu.add_separator(node_type=special_node)
            nodes_menu.add_command(
                "删除节点",
                lambda graph, node: self.delete_node(node),
                node_type=special_node,
                icon=QIcon(f":/qfluentwidgets/images/icons/Delete_white.svg"),
            )

        nodes_menu.add_commands(
            [
                {
                    "name": "运行此节点",
                    "func": lambda graph, node: self.parent.run_node(node),
                    "node_type": f"dynamic.StatusDynamicNode_*",
                    "icon": get_icon("运行"),
                },
                {
                    "name": "运行到此节点",
                    "func": lambda graph, node: self.parent.run_to(node),
                    "node_type": f"dynamic.StatusDynamicNode_*",
                    "icon": get_icon("运行到此处"),
                },
                {
                    "name": "从此节点运行",
                    "func": lambda graph, node: self.parent.run_from(node),
                    "node_type": f"dynamic.StatusDynamicNode_*",
                    "icon": get_icon("从此处运行"),
                },
                {"node_type": f"dynamic.StatusDynamicNode_*"},
                {
                    "name": "查看节点日志",
                    "func": lambda graph, node: node.show_logs(),
                    "node_type": f"dynamic.StatusDynamicNode_*",
                    "icon": get_icon("系统运行日志"),
                },
                {
                    "name": "调试模式",
                    "func": lambda graph, node: node._toggle_debug_mode(),
                    "node_type": f"dynamic.StatusDynamicNode_*",
                    "icon": get_icon("调试"),
                },
                {
                    "name": "编辑组件",
                    "func": lambda graph, node: self.edit_node(node),
                    "node_type": f"dynamic.StatusDynamicNode_*",
                    "icon": QIcon(f":/qfluentwidgets/images/icons/Edit_white.svg"),
                },
                {"node_type": f"dynamic.StatusDynamicNode_*"},
                {
                    "name": "查看节点文档",
                    "func": lambda graph, node: self.show_node_doc(node),
                    "node_type": f"dynamic.StatusDynamicNode_*",
                    "icon": get_icon("readme"),
                },
                {
                    "name": "删除节点",
                    "func": lambda graph, node: self.delete_node(node),
                    "node_type": f"dynamic.StatusDynamicNode_*",
                    "icon": QIcon(f":/qfluentwidgets/images/icons/Delete_white.svg"),
                },
            ]
        )

    def edit_node(self, node):
        self.parent.node_request_edit.emit(node.uuid)

    def show_node_doc(self, node):
        self.parent.side_dock_area.switch_to("节点说明")
        self.parent.node_doc.show_node_doc(node.name(), node.uuid)

    def on_node_created(self, node):
        self._node_id_cache[node.id] = node
        self._request_recommendations(node)

    def on_node_double_clicked(self, node):
        """双击节点事件"""
        if isinstance(node, GroupNode):
            # 展开组节点。注意：这需要 graph.widget 已经被添加到 UI 中
            self.graph.expand_group_node(node)

    def create_next_node_using_name(self, name):
        if name in self.name2type:
            self.create_next_node(self.name2type.get(name))
        else:
            MessageManager.error("错误", "未找到该组件！", self.parent)

    def create_next_node(self, key, icon_path=None):
        selected_nodes = self.graph.selected_nodes()
        viewer = self.graph.viewer()
        try:
            node = self.graph.create_node(key)
        except Exception:
            node_type = self.parent.node_type_map.get(key)
            node = self.graph.create_node(node_type)
        QTimer.singleShot(0, lambda: self.parent.property_panel.update_properties(node))
        if isinstance(icon_path, str) and icon_path.startswith("builtin:\\"):
            icon_name = icon_path.split("\\")[-1]
            icon_value = getattr(FluentIcon, icon_name).value
            icon_path = f":/qfluentwidgets/images/icons/{icon_value}_{getIconColor(Theme.AUTO)}.svg"
        if icon_path and isinstance(icon_path, str):
            node.set_icon(icon_path)
        if selected_nodes:
            node_x = selected_nodes[0].x_pos()
            node_y = selected_nodes[0].y_pos()
            node.set_pos(node_x + selected_nodes[0].view.width + 100, node_y)
            # 将视角移动到当前选择点+新建的点
            viewer.zoom_to_nodes([n.view for n in selected_nodes + [node]])
        else:
            viewport_center = viewer.viewport().rect().center()
            scene_center = viewer.mapToScene(viewport_center)
            node.set_pos(scene_center.x(), scene_center.y())

        return node

    def create_group_node(self):
        graph = self.graph
        selected_nodes = graph.selected_nodes()
        if not selected_nodes:
            return

        graph.begin_undo("创建智能组节点")
        selected_ids = set(n.id for n in selected_nodes)
        input_map = {}
        output_map = {}
        ext_in_conns = []
        ext_out_conns = []
        used_port_names = set()

        # --- 1. 扫描内外连接并【标记端口可删除】 ---
        for node in selected_nodes:
            # 强制标记，确保序列化时会记录 input_ports 和 output_ports 列表
            node.model.set_property("port_deletion_allowed", True)

            for in_port in node.input_ports():
                for cp in in_port.connected_ports():
                    if cp.node().id not in selected_ids:
                        key = (node.id, in_port.name())
                        if key not in input_map:
                            g_name = in_port.name()
                            idx = 1
                            while g_name in used_port_names:
                                g_name = f"{in_port.name()}_{idx}"
                                idx += 1
                            used_port_names.add(g_name)
                            input_map[key] = g_name
                        ext_in_conns.append((cp, input_map[key]))

            for out_port in node.output_ports():
                for cp in out_port.connected_ports():
                    if cp.node().id not in selected_ids:
                        key = (node.id, out_port.name())
                        if key not in output_map:
                            g_name = out_port.name()
                            idx = 1
                            while g_name in used_port_names:
                                g_name = f"{out_port.name()}_{idx}"
                                idx += 1
                            used_port_names.add(g_name)
                            output_map[key] = g_name
                        ext_out_conns.append((output_map[key], cp))

        # --- 2. 序列化并手动修正数据（适配你的反序列化器） ---
        raw_session = graph._serialize(selected_nodes)
        session_data = {
            "graph": raw_session.get("graph", {}),
            "nodes": raw_session.get("nodes", {}),
            "connections": [],
        }

        # 修复连线 Key 名：从 0/1 转换为 'in'/'out'
        if "connections" in raw_session:
            for conn in raw_session["connections"]:
                c_in = conn.get("in") or conn.get(0) or conn.get("0")
                c_out = conn.get("out") or conn.get(1) or conn.get("1")
                if c_in and c_out:
                    # 只有内部连线才进入 session_data，防止 AttributeError
                    if c_in[0] in selected_ids and c_out[0] in selected_ids:
                        session_data["connections"].append(
                            {"in": list(c_in), "out": list(c_out)}
                        )

        # --- 3. 注入内部端口节点（适配你的 build_connections 延时加载） ---
        xs = [n.x_pos() for n in selected_nodes]
        ys = [n.y_pos() for n in selected_nodes]
        min_x, max_x = min(xs), max(xs)
        center_y = (min(ys) + max(ys)) / 2

        for i, ((int_id, int_pname), g_name) in enumerate(input_map.items()):
            p_node_id = f"port_in_{g_name}"
            session_data["nodes"][p_node_id] = {
                "type_": PortInputNode.type_,
                "name": g_name,
                "pos": [min_x - 600, center_y + (i * 100)],
                "outputs": {g_name: {}},
                "custom": {},
            }
            session_data["connections"].append(
                {"out": [p_node_id, g_name], "in": [int_id, int_pname]}
            )

        for i, ((int_id, int_pname), g_name) in enumerate(output_map.items()):
            p_node_id = f"port_out_{g_name}"
            session_data["nodes"][p_node_id] = {
                "type_": PortOutputNode.type_,
                "name": g_name,
                "pos": [max_x + 600, center_y + (i * 100)],
                "inputs": {g_name: {}},
                "custom": {},
            }
            session_data["connections"].append(
                {"out": [int_id, int_pname], "in": [p_node_id, g_name]}
            )

        # --- 4. 创建并应用组节点 ---
        group_node = graph.create_node(
            "general.GroupNode", name="Group", pos=[(min_x + max_x) / 2, center_y]
        )
        group_node.model.set_property("port_deletion_allowed", True)

        for g_name in list(dict.fromkeys(input_map.values())):
            group_node.add_input(g_name)
        for g_name in list(dict.fromkeys(output_map.values())):
            group_node.add_output(g_name)

        graph_id, new_graph = self.parent.ui_manager.canvas_manager.create_sub_graph(
            "Group"
        )
        new_graph.deserialize_session(session_data)
        self.setup_graph_menu(new_graph)
        self.setup_graph_menu(self.graph)
        # 画布右键菜单注册
        graph_menu = new_graph.get_context_menu("graph")
        graph_menu.add_command("撤销", self.parent._undo, "Ctrl+Z")
        graph_menu.add_command("重做", self.parent._redo, "Ctrl+Y")  # 或 'Ctrl+Shift+Z'
        graph_menu.add_command(
            "删除选中",
            lambda graph: (
                self.parent.node_operations.delete_selected_nodes(graph),
                self.parent.property_panel.update_properties(None),
            ),
            "Del",
        )
        QTimer.singleShot(0, lambda: self.parent.ui_manager.update_position(True))
        group_node.graph_id = graph_id
        # --- 5. 恢复外部连线 ---
        g_inputs = group_node.inputs()
        g_outputs = group_node.outputs()
        for ext_out, g_in_name in ext_in_conns:
            ext_out.connect_to(g_inputs[g_in_name])
        for g_out_name, ext_in in ext_out_conns:
            g_outputs[g_out_name].connect_to(ext_in)

        # --- 6. 扫尾 ---
        graph.delete_nodes(selected_nodes)
        group_node.set_selected(True)
        graph.end_undo()

    def create_backdrop_node(self, key, init_io=True):
        selected_nodes = self.graph.selected_nodes()
        input_port_node = None
        output_port_node = None
        other_nodes = []

        for node in selected_nodes:
            if node.type_ == "control_flow.ControlFlowInputPort":
                input_port_node = node
            elif node.type_ == "control_flow.ControlFlowOutputPort":
                output_port_node = node
            elif isinstance(node, ControlFlowBackdrop) and init_io:
                MessageManager.error(
                    "错误", "当前版本不支持嵌套循环或迭代结构！", self.parent
                )
                return
            else:
                other_nodes.append(node)

        viewer = self.graph.viewer()
        viewport_center = viewer.viewport().rect().center()
        scene_center = viewer.mapToScene(viewport_center)
        center_x, center_y = scene_center.x(), scene_center.y()
        if init_io:
            if not selected_nodes:
                input_port_node = self.graph.create_node(
                    "control_flow.ControlFlowInputPort"
                )
                output_port_node = self.graph.create_node(
                    "control_flow.ControlFlowOutputPort"
                )
                input_port_node.set_pos(
                    center_x - 500, center_y - input_port_node.view.height
                )
                output_port_node.set_pos(
                    center_x + 500, center_y + output_port_node.view.height + 200
                )
                nodes_to_wrap = [input_port_node, output_port_node]
            else:
                unconnected_inputs = []
                unconnected_outputs = []
                for node in other_nodes:
                    if not hasattr(node, "input_ports"):
                        continue
                    for input_port in node.input_ports():
                        if not input_port.connected_ports():
                            unconnected_inputs.append((node, input_port))
                    for output_port in node.output_ports():
                        if not output_port.connected_ports():
                            unconnected_outputs.append((node, output_port))

                if not input_port_node:
                    input_port_node = self.graph.create_node(
                        "control_flow.ControlFlowInputPort"
                    )
                    if other_nodes:
                        min_x = min(n.x_pos() for n in other_nodes)
                        avg_y = sum(n.y_pos() for n in other_nodes) / len(other_nodes)
                        input_port_node.set_pos(
                            min_x - 300, avg_y - input_port_node.view.height / 2
                        )
                    else:
                        input_port_node.set_pos(
                            center_x - 250, center_y - input_port_node.view.height / 2
                        )

                if not output_port_node:
                    output_port_node = self.graph.create_node(
                        "control_flow.ControlFlowOutputPort"
                    )
                    if other_nodes:
                        max_x = max(n.x_pos() + n.view.width for n in other_nodes)
                        avg_y = sum(n.y_pos() for n in other_nodes) / len(other_nodes)
                        output_port_node.set_pos(
                            max_x + 150, avg_y - output_port_node.view.height / 2
                        )
                    else:
                        output_port_node.set_pos(
                            center_x + 250, center_y - output_port_node.view.height / 2
                        )

                nodes_to_wrap = other_nodes + [input_port_node, output_port_node]
        else:
            nodes_to_wrap = other_nodes

        backdrop_node = self.graph.create_node(key)
        backdrop_node.wrap_nodes(nodes_to_wrap)
        [node.set_selected(True) for node in nodes_to_wrap]
        QTimer.singleShot(
            0, lambda: self.parent.property_panel.update_properties(backdrop_node)
        )

        if "ControlFlowIterateNode" in key:
            backdrop_node.model.set_property("loop_nums", 3)

    def _delete_node_workspace_async(self, node_ids):
        """
        异步删除节点的工作目录，防止 IO 阻塞主线程
        :param node_ids: list of node ids
        """
        if not node_ids:
            return

        def cleanup_task():
            # 获取基础路径，假设你的工程路径在 self.parent.file_path
            base_path = self.parent.file_path.parent / "workspace"
            for n_id in node_ids:
                workspace_path = base_path / str(n_id)
                log_file = (
                    self.parent.file_path.parent / "node_logs" / f"node_{n_id}.log"
                )
                try:
                    if log_file.exists():
                        log_file.unlink()
                    if workspace_path.exists() and workspace_path.is_dir():
                        shutil.rmtree(workspace_path)
                        logger.info(f"Successfully deleted workspace: {workspace_path}")
                except Exception as e:
                    logger.error(f"Failed to delete workspace for node {n_id}: {e}")

        # 使用类中已有的 thread_pool 执行
        self.thread_pool.start(cleanup_task)

    def delete_node(self, node):
        """删除单个节点"""
        if not node:
            return

        node_id = node.get_property("persistent_id")
        if hasattr(node, "on_deleted"):
            node.on_deleted()
        # 2. 异步删除本地目录 (传入列表)
        self._delete_node_workspace_async([node_id])

        # 3. 图表操作
        node_name = node.name()
        self._invalidate_node_cache()
        self.graph.delete_node(node)
        self.parent.property_panel.pop_node_layout(node_name)
        self.parent.property_panel.update_properties(None)

    def delete_selected_nodes(self, graph):
        """批量删除选中节点（性能优化版）"""
        selected_nodes = graph.selected_nodes()
        if not selected_nodes:
            return

        node_ids_to_delete = []

        for node in selected_nodes:
            # 收集 ID
            node_ids_to_delete.append(node.get_property("persistent_id"))

            # 处理特殊节点的连接清理
            if isinstance(node, ControlFlowBackdrop):
                for port in node.input_ports():
                    port.clear_connections(push_undo=True, emit_signal=True)
                for port in node.output_ports():
                    port.clear_connections(push_undo=True, emit_signal=True)
            if hasattr(node, "on_deleted"):
                node.on_deleted()

        # 1. 批量异步删除本地磁盘文件
        self._delete_node_workspace_async(node_ids_to_delete)

        # 2. 批量从画布删除
        graph.delete_nodes(selected_nodes)

        # 3. 更新 UI 和缓存
        self._invalidate_node_cache()
        self.parent.property_panel.update_properties(None)

    def _copy_selected_nodes(self):
        selected_nodes = self.graph.selected_nodes()
        if not selected_nodes:
            return
        if self.graph.copy_nodes():
            MessageManager.info(
                "复制成功", f"已复制 {len(selected_nodes)} 个节点", self.parent
            )

    def _paste_nodes(self):
        clipboard = QtWidgets.QApplication.clipboard()
        cb_text = clipboard.text()
        if not cb_text:
            return
        try:
            cb_data = orjson.loads(cb_text)
        except:
            logger.exception("Invalid clipboard data")
            return
        if "nodes" not in cb_data:
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
        pasted_nodes = self.graph.paste_nodes(cb_data, False)
        if pasted_nodes:
            min_x = min(n.pos()[0] for n in pasted_nodes)
            min_y = min(n.pos()[1] for n in pasted_nodes)
            for node in pasted_nodes:
                node.set_property("persistent_id", str(uuid.uuid4()))
                x, y = node.pos()
                new_x = x - min_x + avg_x + offset[0]
                new_y = y - min_y + avg_y + offset[1]
                node.set_pos(new_x, new_y)
            MessageManager.info(
                "粘贴成功", f"已粘贴 {len(pasted_nodes)} 个节点", self.parent
            )
        self._invalidate_node_cache()

    def _request_recommendations(self, node):
        full_path = getattr(node, "FULL_PATH", None)
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

    def select_nodes_by_name(self, names):
        if not isinstance(names, (list, tuple)):
            names = [names]
        self.graph.clear_selection()
        for name in names:
            node = self.graph.get_node_by_name(name)
            if node:
                node.set_selected(True)
        self.graph.fit_to_selection()
