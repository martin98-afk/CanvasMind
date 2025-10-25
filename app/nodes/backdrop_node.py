# -*- coding: utf-8 -*-
from collections import OrderedDict, defaultdict, deque
from typing import Optional, List

from NodeGraphQt import BackdropNode, Port
from NodeGraphQt.base.commands import NodeVisibleCmd
from NodeGraphQt.constants import ITEM_CACHE_MODE, PortTypeEnum, Z_VAL_NODE
from NodeGraphQt.errors import PortError
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.port import CustomPortItem, PortItem
from PyQt5.QtWidgets import QUndoCommand
from qtpy import QtCore, QtGui, QtWidgets

from app.nodes.status_node import StatusNode
from app.utils.utils import get_port_node, draw_square_port


# ──────────────── Undo/Redo Command ────────────────

class ResizeBackdropCommand(QUndoCommand):
    """支持撤销/重做的 backdrop 尺寸调整命令"""
    def __init__(self, backdrop, old_pos, old_size, new_pos, new_size, description="Resize Backdrop"):
        super().__init__(description)
        self.backdrop = backdrop
        self.old_pos = old_pos
        self.old_size = old_size
        self.new_pos = new_pos
        self.new_size = new_size

    def undo(self):
        self.backdrop.view.setPos(*self.old_pos)
        self.backdrop.view.width = self.old_size[0]
        self.backdrop.view.height = self.old_size[1]
        self.backdrop.view.update()

    def redo(self):
        self.backdrop.view.setPos(*self.new_pos)
        self.backdrop.view.width = self.new_size[0]
        self.backdrop.view.height = self.new_size[1]
        self.backdrop.view.update()


# ──────────────── Backdrop Node ────────────────

class ControlFlowBackdrop(BackdropNode, StatusNode):
    """
    支持控制流的增强型 Backdrop
    - 智能包含：需显著重叠 + 延迟确认
    - 自动移除完全脱离的节点
    - 支持 Undo/Redo
    """
    TYPE: str
    category = "控制流"
    __identifier__ = 'control_flow'
    NODE_NAME = '控制流区域'
    FULL_PATH = f"{category}/{NODE_NAME}"

    def __init__(self):
        BackdropNode.__init__(self, ControlFlowBackdropNodeItem)
        self._inputs = []
        self._outputs = []
        self._output_values = {}
        self._input_values = {}
        self._contained_nodes = set()      # 已确认包含的节点 ID
        self._pending_nodes = {}           # {node_id: QTimer} —— 待确认的节点
        self._overlap_threshold = 0.4      # 40% 重叠才视为“进入”
        self._confirm_delay_ms = 300       # 延迟 300ms 确认
        self._remove_threshold = 0.1       # <10% 视为“脱离”

        # === 初始化端口 ===
        self.add_input("inputs", multi_input=True, display_name=True)
        self.add_output("outputs", display_name=True)

        # === 添加属性 ===
        self.model.add_property("current_index", 0)
        self.model.add_property("loop_nums", 5)
        self.model.add_property("max_iterations", 1000)
        self.model.add_property("loop_condition", "")
        self.model.add_property("loop_mode", "count") # count, condition, while

        # 延迟初始化自动管理
        QtCore.QTimer.singleShot(0, self._setup_auto_management)

    def _setup_auto_management(self):
        """监听场景变化"""
        if not self.graph:
            return

        scene = self.graph.scene()
        if scene and not hasattr(self, '_scene_connected'):
            try:
                scene.changed.connect(self._on_scene_changed)
                self._scene_connected = True
            except (TypeError, RuntimeError):
                pass

        # 初始调整（无延迟）
        self._perform_auto_resize_with_undo()

    def _on_scene_changed(self, region=None):
        """场景变化时动态管理节点归属"""
        if not self.graph:
            return

        # 清理已销毁节点的 pending timer
        for nid in list(self._pending_nodes.keys()):
            if self.graph.get_node_by_id(nid) is None:
                timer = self._pending_nodes.pop(nid)
                timer.stop()

        # 检查所有节点
        for node in self.graph.all_nodes():
            if node is self:
                continue

            is_significantly_inside = self._is_node_significantly_inside(node, self._overlap_threshold)

            if is_significantly_inside:
                # 启动或刷新确认 timer
                if node.id not in self._pending_nodes:
                    timer = QtCore.QTimer()
                    timer.setSingleShot(True)
                    # 使用默认参数捕获当前 node.id
                    timer.timeout.connect(lambda nid=node.id: self._confirm_node_inclusion(nid))
                    self._pending_nodes[node.id] = timer
                self._pending_nodes[node.id].start(self._confirm_delay_ms)
            else:
                # 取消 pending
                if node.id in self._pending_nodes:
                    self._pending_nodes[node.id].stop()
                    del self._pending_nodes[node.id]

        # 检查是否需要移除已脱离的节点
        self._check_for_removals()

    def _is_node_significantly_inside(self, node, node_threshold=0.3, backdrop_threshold=0.2):
        # 排除内部端口节点
        if node.type_ in ("control_flow.CustomPortInputNode", "control_flow.CustomPortOutputNode"):
            return False

        backdrop_rect = self._get_backdrop_scene_rect()
        node_rect = self._get_node_scene_rect(node)

        # 检查节点中心点
        node_center = node_rect.center()
        if backdrop_rect.contains(node_center):
            return True

        # 检查交集面积
        intersect = backdrop_rect.intersected(node_rect)
        if intersect.isEmpty():
            return False

        overlap_area = intersect.width() * intersect.height()
        node_area = node_rect.width() * node_rect.height()
        backdrop_area = backdrop_rect.width() * backdrop_rect.height()

        # 更严格的判断：需要同时满足多个条件
        node_overlap_ratio = overlap_area / node_area if node_area > 1e-6 else 0
        backdrop_overlap_ratio = overlap_area / backdrop_area if backdrop_area > 1e-6 else 0

        # 如果节点大部分面积在backdrop内，或者backdrop大部分面积被节点覆盖
        if node_overlap_ratio >= node_threshold or backdrop_overlap_ratio >= backdrop_threshold:
            # 额外检查：节点是否在backdrop的合理范围内
            backdrop_center = backdrop_rect.center()
            node_center = node_rect.center()
            distance = ((backdrop_center.x() - node_center.x()) ** 2 +
                        (backdrop_center.y() - node_center.y()) ** 2) ** 0.5

            max_distance = (backdrop_rect.width() + backdrop_rect.height()) / 2
            if distance <= max_distance * 1.5:  # 节点中心在backdrop范围的1.5倍内
                return True

        return False

    def _confirm_node_inclusion(self, node_id):
        """延迟确认：节点确实要加入"""
        if node_id in self._pending_nodes:
            del self._pending_nodes[node_id]

        node = self.graph.get_node_by_id(node_id)
        if not node:
            return

        # 再次检查是否仍显著在内
        if self._is_node_significantly_inside(node, self._overlap_threshold):
            self._perform_auto_resize_with_undo()

    def _check_for_removals(self):
        """检查并移除已脱离的节点"""
        current_contained = set()
        for node in self._get_currently_contained_nodes():
            # 如果节点已基本脱离，且不在 pending 中，则移除
            if (not self._is_node_significantly_inside(node, self._remove_threshold)
                and node.id not in self._pending_nodes):
                self._remove_node_and_cleanup(node)
            else:
                current_contained.add(node)

        self._contained_nodes = {n.id for n in current_contained}

    def _perform_auto_resize_with_undo(self, padding=40, min_width=150, min_height=100):
        """执行带 undo 支持的自动 resize"""
        if not self.graph:
            return

        # 收集所有应包含的节点：已确认 + pending 中的
        nodes_to_include = set()
        for node in self.graph.all_nodes():
            if node is self:
                continue
            if node.type_ in ("control_flow.CustomPortInputNode", "control_flow.CustomPortOutputNode"):
                continue
            if (node.id in self._contained_nodes or
                node.id in self._pending_nodes or
                self._is_node_significantly_inside(node, self._overlap_threshold)):
                nodes_to_include.add(node)

        # 计算新尺寸
        if not nodes_to_include:
            new_width, new_height = min_width, min_height
            new_pos = (self.view.scenePos().x(), self.view.scenePos().y())
        else:
            min_x = min(n.view.scenePos().x() for n in nodes_to_include)
            min_y = min(n.view.scenePos().y() for n in nodes_to_include)
            max_x = max(n.view.scenePos().x() + n.view.width for n in nodes_to_include)
            max_y = max(n.view.scenePos().y() + n.view.height for n in nodes_to_include)

            new_width = max(max_x - min_x + 2 * padding, min_width)
            new_height = max(max_y - min_y + 2 * padding, min_height)
            new_pos = (min_x - padding, min_y - padding)

        # 保存旧状态
        old_pos = (self.view.scenePos().x(), self.view.scenePos().y())
        old_size = (self.view.width, self.view.height)

        # 仅当有显著变化时才 push undo
        pos_changed = abs(old_pos[0] - new_pos[0]) > 1 or abs(old_pos[1] - new_pos[1]) > 1
        size_changed = abs(old_size[0] - new_width) > 1 or abs(old_size[1] - new_height) > 1

        if pos_changed or size_changed:
            command = ResizeBackdropCommand(
                self, old_pos, old_size, new_pos, (new_width, new_height)
            )
            self.graph.undo_stack().push(command)
        # 更新记录（无论是否变化）
        self._contained_nodes = {n.id for n in nodes_to_include}

        self._layout_internal_port_nodes()

    def _layout_internal_port_nodes(self):
        input_proxy, output_proxy, _ = self.get_nodes()
        if not input_proxy and not output_proxy:
            return

        # 获取 backdrop 的场景坐标
        backdrop_x = self.view.scenePos().x()
        backdrop_y = self.view.scenePos().y()
        backdrop_w = self.view.width
        backdrop_h = self.view.height

        padding = 40

        if input_proxy:
            # 左上角内侧：x = backdrop_x + padding, y = backdrop_y + padding
            new_x = backdrop_x + padding
            new_y = backdrop_y + padding
            input_proxy.view.setPos(new_x, new_y)

        if output_proxy:
            # 右上角内侧：x = backdrop_x + backdrop_w - node_w - padding
            node_w = output_proxy.view.width
            new_x = backdrop_x + backdrop_w - node_w - padding
            new_y = backdrop_y + padding
            output_proxy.view.setPos(new_x, new_y)

    # ──────────────── 几何辅助方法 ────────────────

    def _get_backdrop_scene_rect(self):
        pos = self.view.scenePos()
        return QtCore.QRectF(pos.x(), pos.y(), self.view.width, self.view.height)

    def _get_node_scene_rect(self, node):
        pos = node.view.scenePos()
        return QtCore.QRectF(pos.x(), pos.y(), node.view.width, node.view.height)

    def _get_currently_contained_nodes(self):
        nodes = []
        for nid in self._contained_nodes:
            node = self.graph.get_node_by_id(nid)
            if node is not None:
                nodes.append(node)
        return nodes

    # ──────────────── 节点移除与清理 ────────────────

    def _remove_node_and_cleanup(self, node):
        if node.id not in self._contained_nodes:
            return

        self._contained_nodes.discard(node.id)

        input_proxy, output_proxy, _ = self.get_nodes()

        # 断开与 input_proxy 的连接
        if input_proxy:
            for out_port in input_proxy.output_ports():
                for conn in list(out_port.connected_ports()):
                    if conn.node() == node:
                        out_port.disconnect_from(conn)

        # 断开与 output_proxy 的连接
        if output_proxy:
            for in_port in output_proxy.input_ports():
                for conn in list(in_port.connected_ports()):
                    if conn.node() == node:
                        in_port.disconnect_from(conn)

    def set_property(self, name, value, push_undo=True):
        """
        Set the value on the node custom property.

        Args:
            name (str): name of the property.
            value (object): property data (python built in types).
            push_undo (bool): register the command to the undo stack. (default: True)
        """
        # prevent signals from causing a infinite loop.
        if self.get_property(name) == value:
            return

        if name == 'visible':
            if self.graph:
                undo_cmd = NodeVisibleCmd(self, value)
                if push_undo:
                    self.graph.undo_stack().push(undo_cmd)
                else:
                    undo_cmd.redo()
                return
        elif name == 'disabled':
            # redraw the connected pipes in the scene.
            ports = self.view.inputs + self.view.outputs
            for port in ports:
                for pipe in port.connected_pipes:
                    pipe.update()
        super(BackdropNode, self).set_property(name, value, push_undo)

    def set_disabled(self, mode=False):
        """
        Set the node state to either disabled or enabled.

        Args:
            mode(bool): True to disable node.
        """
        self.set_property('disabled', mode)

    # ──────────────── 覆盖 nodes() 以返回当前包含的节点 ────────────────

    def nodes(self):
        """返回当前已确认包含的节点（用于内部逻辑）"""
        return self._get_currently_contained_nodes()

    # ──────────────── 以下为原有业务逻辑（保持不变）────────────────

    def get_nodes(self):
        execute_nodes = []
        input_proxy, output_proxy = None, None
        for node in self.nodes():
            if node.type_ == "control_flow.ControlFlowInputPort":
                input_proxy = node
            elif node.type_ == "control_flow.ControlFlowOutputPort":
                output_proxy = node
            else:
                execute_nodes.append(node)
        return input_proxy, output_proxy, self._topological_sort(execute_nodes)

    def _topological_sort(self, nodes: List) -> Optional[List]:
        if not nodes:
            return []

        in_degree = {node: 0 for node in nodes}
        graph_deps = defaultdict(list)

        node_set = set(nodes)
        for node in nodes:
            for input_port in node.input_ports():
                for upstream_out in input_port.connected_ports():
                    upstream = get_port_node(upstream_out)
                    if upstream in node_set:
                        graph_deps[upstream].append(node)
                        in_degree[node] += 1

        queue = deque([n for n in nodes if in_degree[n] == 0])
        execution_order = []
        while queue:
            n = queue.popleft()
            execution_order.append(n)
            for neighbor in graph_deps[n]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(execution_order) != len(nodes):
            return None
        return execution_order

    # ──────────────── 端口管理（保持不变）────────────────

    def add_input(self, name='input', multi_input=False, display_name=True, color=None, locked=False,
                  painter_func=None):
        if name in self.inputs().keys():
            raise ValueError(f'输入端口 "{name}" 已存在')
        view = self.view.add_input(name, multi_input, display_name, locked, painter_func=draw_square_port)
        if color:
            view.color = color
            view.border_color = [min(255, max(0, i + 80)) for i in color]
        port = Port(self, view)
        port.model.type_ = PortTypeEnum.IN.value
        port.model.name = name
        port.model.display_name = display_name
        port.model.multi_connection = multi_input
        port.model.locked = locked
        self._inputs.append(port)
        self.model.inputs[port.name()] = port.model
        return port

    def add_output(self, name='output', multi_output=True, display_name=True, color=None, locked=False,
                   painter_func=None):
        if name in self.outputs().keys():
            raise ValueError(f'输出端口 "{name}" 已存在')
        view = self.view.add_output(name, multi_output, display_name, locked)
        if color:
            view.color = color
            view.border_color = [min(255, max(0, i + 80)) for i in color]
        port = Port(self, view)
        port.model.type_ = PortTypeEnum.OUT.value
        port.model.name = name
        port.model.display_name = display_name
        port.model.multi_connection = multi_output
        port.model.locked = locked
        self._outputs.append(port)
        self.model.outputs[port.name()] = port.model
        return port

    def connected_output_nodes(self):
        nodes = OrderedDict()
        for p in self.output_ports():
            nodes[p] = [cp.node() for cp in p.connected_ports()]
        return nodes

    def input_ports(self):
        return self._inputs

    def output_ports(self):
        return self._outputs

    def inputs(self):
        return {p.name(): p for p in self._inputs}

    def outputs(self):
        return {p.name(): p for p in self._outputs}

    def accepted_port_types(self, port):
        ports = self._inputs + self._outputs
        if port not in ports:
            raise PortError('Node does not contain port "{}"'.format(port))
        accepted_types = self.graph.model.port_accept_connection_types(
            node_type=self.type_,
            port_type=port.type_(),
            port_name=port.name()
        )
        return accepted_types

    def rejected_port_types(self, port):
        ports = self._inputs + self._outputs
        if port not in ports:
            raise PortError('Node does not contain port "{}"'.format(port))
        rejected_types = self.graph.model.port_reject_connection_types(
            node_type=self.type_,
            port_type=port.type_(),
            port_name=port.name()
        )
        return rejected_types

    def on_input_connected(self, in_port, out_port):
        return

    def on_input_disconnected(self, in_port, out_port):
        return

    def set_output_value(self, value):
        self._output_values = {self._outputs[0].name(): value}

    def get_output_value(self, name):
        return self._output_values.get(name)

    def get_input(self, port):
        if isinstance(port, int):
            if port < len(self._inputs):
                return self._inputs[port]
        elif isinstance(port, str):
            return self.inputs().get(port, None)

    def get_output(self, port):
        if isinstance(port, int):
            if port < len(self._outputs):
                return self._outputs[port]
        elif isinstance(port, str):
            return self.outputs().get(port, None)


class ControlFlowLoopNode(ControlFlowBackdrop):
    category = "控制流"
    NODE_NAME = "循环控制流区域"
    TYPE = "loop"
    FULL_PATH = f"{category}/{NODE_NAME}"


class ControlFlowIterateNode(ControlFlowBackdrop):
    category = "控制流"
    NODE_NAME = "迭代控制流区域"
    TYPE = "iterate"
    FULL_PATH = f"{category}/{NODE_NAME}"


# ──────────────── 图形项（保持不变）────────────────

class ControlFlowBackdropNodeItem(BackdropNodeItem):
    def __init__(self, name='控制流区域', text='', parent=None):
        super().__init__(name=name, text=text, parent=parent)
        self.setZValue(Z_VAL_NODE)
        self._input_items = OrderedDict()
        self._output_items = OrderedDict()

    def _add_port(self, port):
        text = QtWidgets.QGraphicsTextItem(port.name, self)
        text.setFont(QtGui.QFont("Arial", 8))
        text.setVisible(port.display_name)
        text.setCacheMode(ITEM_CACHE_MODE)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        elif port.port_type == PortTypeEnum.OUT.value:
            self._output_items[port] = text
        return port

    def add_input(self, name='input', multi_port=False, display_name=True, locked=False, painter_func=None):
        if painter_func:
            port = CustomPortItem(self, painter_func)
        else:
            port = PortItem(self)
        port.name = name
        port.port_type = PortTypeEnum.IN.value
        port.multi_connection = multi_port
        port.display_name = display_name
        port.locked = locked
        return self._add_port(port)

    def add_output(self, name='output', multi_port=False, display_name=True, locked=False, painter_func=None):
        if painter_func:
            port = CustomPortItem(self, painter_func)
        else:
            port = PortItem(self)
        port.name = name
        port.port_type = PortTypeEnum.OUT.value
        port.multi_connection = multi_port
        port.display_name = display_name
        port.locked = locked
        return self._add_port(port)

    @property
    def inputs(self):
        return list(self._input_items.keys())

    @property
    def outputs(self):
        return list(self._output_items.keys())

    def align_ports(self, v_offset=0.0):
        width = self._width
        txt_offset = 4
        spacing = 1

        inputs = [p for p in self.inputs if p.isVisible()]
        if inputs:
            port_width = inputs[0].boundingRect().width()
            port_height = inputs[0].boundingRect().height()
            port_x = (port_width / 2) * -1
            port_y = v_offset
            for port in inputs:
                port.setPos(port_x, port_y)
                port_y += port_height + spacing
            for port, text in self._input_items.items():
                if port.isVisible():
                    txt_x = port.boundingRect().width() / 2 - txt_offset
                    text.setPos(txt_x, port.y() - 1.5)

        outputs = [p for p in self.outputs if p.isVisible()]
        if outputs:
            port_width = outputs[0].boundingRect().width()
            port_height = outputs[0].boundingRect().height()
            port_x = width - (port_width / 2)
            port_y = v_offset
            for port in outputs:
                port.setPos(port_x, port_y)
                port_y += port_height + spacing
            for port, text in self._output_items.items():
                if port.isVisible():
                    txt_width = text.boundingRect().width() - txt_offset
                    txt_x = port.x() - txt_width
                    text.setPos(txt_x, port.y() - 1.5)

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)

    def draw_node(self):
        QtCore.QTimer.singleShot(50, self._align_ports_later)

    def _align_ports_later(self):
        title_height = 26.0
        self.align_ports(v_offset=title_height + 5.0)

    @AbstractNodeItem.width.setter
    def width(self, width=0.0):
        AbstractNodeItem.width.fset(self, width)
        self._sizer.set_pos(self._width, self._height)
        self.draw_node()

    @AbstractNodeItem.height.setter
    def height(self, height=0.0):
        AbstractNodeItem.height.fset(self, height)
        self._sizer.set_pos(self._width, self._height)
        self.draw_node()