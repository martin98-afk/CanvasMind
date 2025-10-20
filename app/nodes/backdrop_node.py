# -*- coding: utf-8 -*-
from collections import OrderedDict, defaultdict, deque
from typing import Optional, List

from NodeGraphQt import BackdropNode, Port
from NodeGraphQt.constants import ITEM_CACHE_MODE, PortTypeEnum, Z_VAL_NODE
from NodeGraphQt.errors import PortError
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.port import CustomPortItem, PortItem
from qtpy import QtCore, QtGui, QtWidgets

from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.status_node import StatusNode
from app.utils.utils import get_port_node, draw_square_port


class ControlFlowBackdrop(BackdropNode, StatusNode, BasicNodeWithGlobalProperty):
    """
    支持控制流的增强型 Backdrop
    - 可配置为 Loop / iterate
    - 动态添加输入/输出端口
    - 自动根据相交节点调整大小
    - 节点完全脱离时自动移除并断连
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
        self._contained_nodes = set()  # 显式记录当前归属的节点 ID
        # === 初始化默认端口 ===
        self.add_input("inputs", multi_input=True, display_name=True)
        self.add_output("outputs", display_name=True)

        # === 添加属性 ===
        self.model.add_property("current_index", 0)
        self.model.add_property("loop_nums", 5)
        self.model.add_property("max_iterations", 1000)

        # 延迟初始化自动管理（确保 graph 已绑定）
        QtCore.QTimer.singleShot(0, self._setup_auto_management)

    def _setup_auto_management(self):
        """监听场景变化以自动管理节点归属"""
        if not self.graph:
            return

        scene = self.graph.scene()
        if scene and not hasattr(self, '_scene_connected'):
            try:
                scene.changed.connect(self._on_scene_changed)
                self._scene_connected = True
            except (TypeError, RuntimeError):
                pass  # 已连接或对象已销毁

        # 初始调整
        self.auto_resize_to_fit_intersecting_nodes()

    def _on_scene_changed(self, region=None):
        """场景变化时防抖触发自动调整"""
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QtCore.QTimer()
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self.auto_resize_to_fit_intersecting_nodes)
        self._resize_timer.start(80)

    # ──────────────── 节点归属与几何计算 ────────────────

    def _get_backdrop_scene_rect(self):
        """获取 backdrop 在场景中的 QRectF"""
        pos = self.view.scenePos()
        return QtCore.QRectF(pos.x(), pos.y(), self.view.width, self.view.height)

    def _get_node_scene_rect(self, node):
        """获取普通节点在场景中的 QRectF"""
        pos = node.view.scenePos()
        return QtCore.QRectF(pos.x(), pos.y(), node.view.width, node.view.height)

    def _get_currently_contained_nodes(self):
        """返回当前显式记录的有效节点对象列表"""
        nodes = []
        for nid in self._contained_nodes:
            node = self.graph.get_node_by_id(nid)
            if node is not None:
                nodes.append(node)
        return nodes

    # ──────────────── 自动调整与清理 ────────────────

    def auto_resize_to_fit_intersecting_nodes(self, padding=40, min_width=150, min_height=100):
        """根据所有与 backdrop 相交的节点，自动调整大小并管理归属"""
        self.graph.begin_undo('"{}" auto resize'.format(self.name()))
        if not self.graph:
            return

        # Step 1: 获取当前所有与 backdrop 相交的节点
        backdrop_rect = self._get_backdrop_scene_rect()
        current_intersecting = set()
        for node in self.graph.all_nodes():
            if node is self:
                continue
            node_rect = self._get_node_scene_rect(node)
            if backdrop_rect.intersects(node_rect):
                current_intersecting.add(node)

        # Step 2: 获取旧的节点集合
        old_nodes = set(self._get_currently_contained_nodes())

        # Step 3: 移除已脱离的节点
        for node in (old_nodes - current_intersecting):
            self._remove_node_and_cleanup(node)

        # Step 4: 处理无节点情况
        if not current_intersecting:
            self.view.width = min_width
            self.view.height = min_height
            self._contained_nodes.clear()
            return

        # Step 5: 计算新包围盒
        min_x = min(n.view.scenePos().x() for n in current_intersecting)
        min_y = min(n.view.scenePos().y() for n in current_intersecting)
        max_x = max(n.view.scenePos().x() + n.view.width for n in current_intersecting)
        max_y = max(n.view.scenePos().y() + n.view.height for n in current_intersecting)

        new_width = max(max_x - min_x + 2 * padding, min_width)
        new_height = max(max_y - min_y + 2 * padding, min_height)
        new_pos_x = min_x - padding
        new_pos_y = min_y - padding

        # Step 6: 更新 backdrop
        self.view.setPos(new_pos_x, new_pos_y)
        self.view.width = new_width
        self.view.height = new_height

        # Step 7: 更新记录
        self._contained_nodes = {n.id for n in current_intersecting}
        self.graph.end_undo()

    def _remove_node_and_cleanup(self, node):
        """从 backdrop 中移除节点，并断开其与内部 proxy 端口的连接"""
        if node.id not in self._contained_nodes:
            return

        self._contained_nodes.discard(node.id)

        # 获取内部 proxy 节点
        input_proxy, output_proxy, _ = self.get_nodes()

        # 断开与 input_proxy 的连接（node 作为 input_proxy 的下游）
        if input_proxy:
            for out_port in input_proxy.output_ports():
                for conn in list(out_port.connected_ports()):
                    if conn.node() == node:
                        out_port.disconnect_from(conn)

        # 断开与 output_proxy 的连接（node 作为 output_proxy 的上游）
        if output_proxy:
            for in_port in output_proxy.input_ports():
                for conn in list(in_port.connected_ports()):
                    if conn.node() == node:
                        in_port.disconnect_from(conn)

    # ──────────────── 覆盖 nodes() 以支持相交判断 ────────────────

    def nodes(self):
        """
        返回所有与当前 Backdrop 区域 **相交** 的节点（而非完全包含）
        """
        if not self.graph:
            return []

        backdrop_rect = self._get_backdrop_scene_rect()
        intersecting_nodes = []

        for node in self.graph.all_nodes():
            if node is self:
                continue
            node_rect = self._get_node_scene_rect(node)
            if backdrop_rect.intersects(node_rect):
                intersecting_nodes.append(node)

        return intersecting_nodes

    # ──────────────── 以下为原有业务逻辑（保持不变）────────────────

    def get_nodes(self):
        """获取控制流区域内输入、输出端口以及经过拓扑排序后的执行节点"""
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
        """对节点列表进行拓扑排序，检测循环依赖"""
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
            return None  # 存在环
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
        self._output_values[self._outputs[0].name()] = value

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