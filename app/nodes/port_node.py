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