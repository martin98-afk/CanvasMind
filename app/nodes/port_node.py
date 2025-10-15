# -*- coding: utf-8 -*-
from NodeGraphQt.nodes.port_node import PortInputNode, PortOutputNode
from NodeGraphQt.qgraphics.node_port_in import PortInputNodeItem
from NodeGraphQt.qgraphics.node_port_out import PortOutputNodeItem

from app.nodes.base_node import BasicNodeWithGlobalProperty


class CustomPortInputNode(PortInputNode, BasicNodeWithGlobalProperty):
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


class CustomPortOutputNode(PortOutputNode, BasicNodeWithGlobalProperty):
    __identifier__ = 'control_flow'
    category = "控制流"
    NODE_NAME = '输出端口'
    FULL_PATH = f"{category}/{NODE_NAME}"

    def __init__(self, qgraphics_item=None, parent_port=None):
        super(CustomPortOutputNode, self).__init__(qgraphics_item or PortOutputNodeItem)
        self._parent_port = parent_port
        self.add_input(multi_input=True)
        self._input_values = {}