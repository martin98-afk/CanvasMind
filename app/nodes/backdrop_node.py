# -*- coding: utf-8 -*-
from collections import OrderedDict, defaultdict, deque
from typing import Optional, List

from NodeGraphQt import BackdropNode, Port
from NodeGraphQt.constants import ITEM_CACHE_MODE
from NodeGraphQt.constants import PortTypeEnum, Z_VAL_NODE
from NodeGraphQt.errors import PortError
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.port import CustomPortItem
from NodeGraphQt.qgraphics.port import PortItem
from PyQt5 import QtCore, QtGui, QtWidgets
from Qt import QtCore, QtGui, QtWidgets

from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.status_node import StatusNode
from app.utils.utils import get_port_node, draw_square_port


class ControlFlowBackdrop(BackdropNode, StatusNode, BasicNodeWithGlobalProperty):
    """
    支持控制流的增强型 Backdrop
    - 可配置为 Loop / iterate
    - 动态添加输入/输出端口
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
        # === 初始化默认端口默认多输入/多输出端口 ===
        self.add_input("inputs", multi_input=True, display_name=True)
        self.add_output("outputs", display_name=True)
        # === 添加默认多输入/多输出端口 ===
        self.model.add_property("current_index", 0)
        self.model.add_property("loop_nums", 5)
        self.model.add_property("max_iterations", 1000)


    @property
    def control_flow_type(self):
        return self._control_flow_type

    def get_loop_config(self):
        return self._loop_config

    def get_branch_config(self):
        return self._branch_config

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

        # 构建子图依赖
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

        # Kahn 算法
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

    def add_input(self, name='input', multi_input=False, display_name=True, color=None, locked=False,
                  painter_func=None):
        """手动实现 add_input（模仿 BaseNode）"""
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
        """手动实现 add_output（模仿 BaseNode）"""
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
        """
        Returns all nodes connected from the output ports.

        Returns:
            dict: {<output_port>: <node_list>}
        """
        nodes = OrderedDict()
        for p in self.output_ports():
            nodes[p] = [cp.node() for cp in p.connected_ports()]
        return nodes

    def input_ports(self):
        """
        Return all input ports.

        Returns:
            list[NodeGraphQt.Port]: node input ports.
        """
        return self._inputs

    def output_ports(self):
        """
        Return all output ports.

        Returns:
            list[NodeGraphQt.Port]: node output ports.
        """
        return self._outputs

    def inputs(self):
        return {p.name(): p for p in self._inputs}

    def outputs(self):
        return {p.name(): p for p in self._outputs}

    def accepted_port_types(self, port):
        """
        Returns a dictionary of connection constrains of the port types
        that allow for a pipe connection to this node.

        Args:
            port (NodeGraphQt.Port): port object.

        Returns:
            dict: {<node_type>: {<port_type>: [<port_name>]}}
        """
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
        """
        Returns a dictionary of connection constrains of the port types
        that are NOT allowed for a pipe connection to this node.

        Args:
            port (NodeGraphQt.Port): port object.

        Returns:
            dict: {<node_type>: {<port_type>: [<port_name>]}}
        """
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
        """
        Callback triggered when a new pipe connection is made.

        *The default of this function does nothing re-implement if you require
        logic to run for this event.*

        Note:
            to work with undo & redo for this method re-implement
            :meth:`BaseNode.on_input_disconnected` with the reverse logic.

        Args:
            in_port (NodeGraphQt.Port): source input port from this node.
            out_port (NodeGraphQt.Port): output port that connected to this node.
        """
        return

    def on_input_disconnected(self, in_port, out_port):
        """
        Callback triggered when a pipe connection has been disconnected
        from a INPUT port.

        *The default of this function does nothing re-implement if you require
        logic to run for this event.*

        Note:
            to work with undo & redo for this method re-implement
            :meth:`BaseNode.on_input_connected` with the reverse logic.

        Args:
            in_port (NodeGraphQt.Port): source input port from this node.
            out_port (NodeGraphQt.Port): output port that was disconnected.
        """
        return

    def set_output_value(self, value):
        self._output_values[self._outputs[0].name()] = value

    def get_output_value(self, name):
        return self._output_values.get(name)

    def get_input(self, port):
        """
        Get input port by the name or index.

        Args:
            port (str or int): port name or index.

        Returns:
            NodeGraphQt.Port: node port.
        """
        if type(port) is int:
            if port < len(self._inputs):
                return self._inputs[port]
        elif type(port) is str:
            return self.inputs().get(port, None)

    def get_output(self, port):
        """
        Get output port by the name or index.

        Args:
            port (str or int): port name or index.

        Returns:
            NodeGraphQt.Port: node port.
        """
        if type(port) is int:
            if port < len(self._outputs):
                return self._outputs[port]
        elif type(port) is str:
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


class ControlFlowBackdropNodeItem(BackdropNodeItem):
    """
    支持端口绘制的 Backdrop 节点图形项
    - 保留 Backdrop 的视觉样式（标题栏、半透明背景）
    - 添加输入/输出端口支持（复用 NodeItem 的端口逻辑）
    """

    def __init__(self, name='循环控制器', text='', parent=None):
        super().__init__(name=name, text=text, parent=parent)
        self.setZValue(Z_VAL_NODE)  # 确保层级正确

        # === 端口管理（照抄 NodeItem）===
        self._input_items = OrderedDict()   # {PortItem: QGraphicsTextItem}
        self._output_items = OrderedDict()  # {PortItem: QGraphicsTextItem}

    # === 端口添加逻辑（照抄 NodeItem._add_port）===
    def _add_port(self, port):
        """添加端口图形项"""
        text = QtWidgets.QGraphicsTextItem(port.name, self)
        text.setFont(QtGui.QFont("Arial", 8))
        text.setVisible(port.display_name)
        text.setCacheMode(ITEM_CACHE_MODE)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        elif port.port_type == PortTypeEnum.OUT.value:
            self._output_items[port] = text
        return port

    # === 公共接口（照抄 NodeItem）===
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

    # === 端口对齐（照抄 NodeItem._align_ports_horizontal）===
    def align_ports(self, v_offset=0.0):
        """水平布局端口（Backdrop 固定为水平）"""
        width = self._width
        txt_offset = 4  # PortEnum.CLICK_FALLOFF.value - 2
        spacing = 1

        # 输入端口（左侧）
        inputs = [p for p in self.inputs if p.isVisible()]
        if inputs:
            port_width = inputs[0].boundingRect().width()
            port_height = inputs[0].boundingRect().height()
            port_x = (port_width / 2) * -1
            port_y = v_offset
            for port in inputs:
                port.setPos(port_x, port_y)
                port_y += port_height + spacing
            # 输入文本
            for port, text in self._input_items.items():
                if port.isVisible():
                    txt_x = port.boundingRect().width() / 2 - txt_offset
                    text.setPos(txt_x, port.y() - 1.5)

        # 输出端口（右侧）
        outputs = [p for p in self.outputs if p.isVisible()]
        if outputs:
            port_width = outputs[0].boundingRect().width()
            port_height = outputs[0].boundingRect().height()
            port_x = width - (port_width / 2)
            port_y = v_offset
            for port in outputs:
                port.setPos(port_x, port_y)
                port_y += port_height + spacing
            # 输出文本
            for port, text in self._output_items.items():
                if port.isVisible():
                    txt_width = text.boundingRect().width() - txt_offset
                    txt_x = port.x() - txt_width
                    text.setPos(txt_x, port.y() - 1.5)

    # === 重写 paint 以支持端口 ===
    def paint(self, painter, option, widget):
        """先绘制 Backdrop 背景，端口由父类机制自动绘制"""
        super().paint(painter, option, widget)

    # === 重写 draw_node 以对齐端口 ===
    def draw_node(self):
        """在 Backdrop 尺寸确定后对齐端口"""
        # 等待 backdrop 尺寸稳定（延迟对齐）
        QtCore.QTimer.singleShot(50, self._align_ports_later)

    def _align_ports_later(self):
        """延迟对齐端口（确保尺寸已计算）"""
        # 估算标题栏高度（Backdrop 固定为 26px）
        title_height = 26.0
        self.align_ports(v_offset=title_height + 5.0)

    # === 重写 set_width/set_height 以触发端口对齐 ===
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