# -*- coding: utf-8 -*-
from NodeGraphQt import BackdropNode, Port
from NodeGraphQt.constants import ITEM_CACHE_MODE
from NodeGraphQt.errors import PortError
from NodeGraphQt.nodes.port_node import PortInputNode, PortOutputNode
from NodeGraphQt.qgraphics.node_port_in import PortInputNodeItem
from NodeGraphQt.qgraphics.node_port_out import PortOutputNodeItem
from NodeGraphQt.qgraphics.port import CustomPortItem
from Qt import QtCore, QtGui, QtWidgets
from collections import OrderedDict
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.port import PortItem
from NodeGraphQt.constants import PortTypeEnum, Z_VAL_NODE
from PyQt5 import QtCore, QtGui, QtWidgets


class CustomPortInputNode(PortInputNode):
    __identifier__ = 'control_flow'
    category = "控制流"
    NODE_NAME = '输入端口'
    FULL_PATH = f"{category}/{NODE_NAME}"

    def __init__(self, qgraphics_item=None, parent_port=None):
        super(CustomPortInputNode, self).__init__(qgraphics_item or PortInputNodeItem)
        self._parent_port = parent_port
        self.add_output()
        self._output_values = {}

    def set_output_value(self, value):
        self._output_values[self._outputs[0].name()] = value

    def get_output_value(self, name):
        return self._output_values.get(name)


class CustomPortOutputNode(PortOutputNode):
    __identifier__ = 'control_flow'
    category = "控制流"
    NODE_NAME = '输出端口'
    FULL_PATH = f"{category}/{NODE_NAME}"

    def __init__(self, qgraphics_item=None, parent_port=None):
        super(CustomPortOutputNode, self).__init__(qgraphics_item or PortOutputNodeItem)
        self._parent_port = parent_port
        self.add_input()
        self._input_values = {}

    def get_input_value(self):
        return self._input_values


class ControlFlowBackdrop(BackdropNode):
    """
    支持控制流的增强型 Backdrop
    - 可配置为 Loop / Branch
    - 动态添加输入/输出端口
    """
    category = "控制流"
    __identifier__ = 'control_flow'
    NODE_NAME = '控制流区域'
    FULL_PATH = f"{category}/{NODE_NAME}"

    def __init__(self):
        super(ControlFlowBackdrop, self).__init__(ControlFlowBackdropNodeItem)
        self._inputs = []
        self._outputs = []
        self._output_values = {}
        # === 初始化默认端口 ===
        self.add_input("inputs", multi_input=True, display_name=True)
        self.add_output("outputs", display_name=True)
        # === 添加默认多输入/多输出端口 ===
        self._control_flow_type = None  # 'loop' or 'branch'
        self._loop_config = {}
        self._branch_config = {}
        self.set_as_loop()

    def set_as_loop(self):
        """配置为循环体"""
        self._control_flow_type = "loop"
        self.set_name("🔁 循环体")

    def set_as_branch(self, condition_port: str = "condition"):
        """配置为条件分支"""
        self._control_flow_type = "branch"
        self.set_name("🔀 条件分支")
        # 添加条件输入端口
        self.add_input(condition_port)
        # 可选：添加输出端口（用于合并分支结果）
        self.add_output("result")

    @property
    def control_flow_type(self):
        return self._control_flow_type

    def get_loop_config(self):
        return self._loop_config

    def get_branch_config(self):
        return self._branch_config

    def add_input(self, name='input', multi_input=False, display_name=True, color=None, locked=False,
                  painter_func=None):
        """手动实现 add_input（模仿 BaseNode）"""
        if name in self.inputs().keys():
            raise ValueError(f'输入端口 "{name}" 已存在')
        view = self.view.add_input(name, multi_input, display_name, locked)
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