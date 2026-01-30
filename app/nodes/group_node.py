# -*- coding: utf-8 -*-
import uuid

from NodeGraphQt import GroupNode, Port
from NodeGraphQt.constants import PortTypeEnum
from NodeGraphQt.errors import PortRegistrationError
from NodeGraphQt.nodes.port_node import PortInputNode, PortOutputNode
from NodeGraphQt.qgraphics.node_group import GroupNodeItem
from NodeGraphQt.qgraphics.node_port_in import PortInputNodeItem
from NodeGraphQt.qgraphics.node_port_out import PortOutputNodeItem
from app.nodes.status_node import StatusNode


class GroupPortInputNode(PortInputNode):
    __identifier__ = 'group'
    category = "组节点"
    NODE_NAME = '输入端口'
    FULL_PATH = f"{category}/{NODE_NAME}"
    description = "组节点的输入端口"

    def __init__(self, qgraphics_item=None, parent_port=None):
        super(GroupPortInputNode, self).__init__(qgraphics_item or PortInputNodeItem)
        self.model.add_property("persistent_id", str(uuid.uuid4()))
        self._parent_port = parent_port
        self._output_values = {}

    def set_output_value(self, value):
        self._output_values[self._outputs[0].name()] = value

    def get_output_value(self, name):
        return self._output_values.get(name)

    def add_output(self, name='output', multi_output=True, display_name=True,
                   color=None, locked=False, painter_func=None):
        """
        Add output :class:`Port` to node.

        Warnings:
            Undo is NOT supported for this function.

        Args:
            name (str): name for the output port.
            multi_output (bool): allow port to have more than one connection.
            display_name (bool): display the port name on the node.
            color (tuple): initial port color (r, g, b) ``0-255``.
            locked (bool): locked state see :meth:`Port.set_locked`
            painter_func (function or None): custom function to override the drawing
                of the port shape see example: :ref:`Creating Custom Shapes`

        Returns:
            NodeGraphQt.Port: the created port object.
        """
        if name in self.outputs().keys():
            raise PortRegistrationError(
                'port name "{}" already registered.'.format(name))

        port_args = [name, multi_output, display_name, locked]
        if painter_func and callable(painter_func):
            port_args.append(painter_func)
        view = self.view.add_output(*port_args)

        if color:
            view.color = color
            view.border_color = [min([255, max([0, i + 80])]) for i in color]
        port = Port(self, view)
        port.model.type_ = PortTypeEnum.OUT.value
        port.model.name = name
        port.model.display_name = display_name
        port.model.multi_connection = multi_output
        port.model.locked = locked
        self._outputs.append(port)
        self.model.outputs[port.name()] = port.model
        return port


class GroupPortOutputNode(PortOutputNode):
    __identifier__ = 'group'
    category = "组节点"
    NODE_NAME = '输出端口'
    FULL_PATH = f"{category}/{NODE_NAME}"
    description = "组节点的输出端口"

    def __init__(self, qgraphics_item=None, parent_port=None):
        super(GroupPortOutputNode, self).__init__(qgraphics_item or PortOutputNodeItem)
        self.model.add_property("persistent_id", str(uuid.uuid4()))
        self._parent_port = parent_port
        self._input_values = {}

    def add_input(self, name='input', multi_input=False, display_name=True,
                  color=None, locked=False, painter_func=None):
        """
        Add input :class:`Port` to node.

        Warnings:
            Undo is NOT supported for this function.

        Args:
            name (str): name for the input port.
            multi_input (bool): allow port to have more than one connection.
            display_name (bool): display the port name on the node.
            color (tuple): initial port color (r, g, b) ``0-255``.
            locked (bool): locked state see :meth:`Port.set_locked`
            painter_func (function or None): custom function to override the drawing
                of the port shape see example: :ref:`Creating Custom Shapes`

        Returns:
            NodeGraphQt.Port: the created port object.
        """
        if name in self.inputs().keys():
            raise PortRegistrationError(
                'port name "{}" already registered.'.format(name))

        port_args = [name, multi_input, display_name, locked]
        if painter_func and callable(painter_func):
            port_args.append(painter_func)
        view = self.view.add_input(*port_args)

        if color:
            view.color = color
            view.border_color = [min([255, max([0, i + 80])]) for i in color]

        port = Port(self, view)
        port.model.type_ = PortTypeEnum.IN.value
        port.model.name = name
        port.model.display_name = display_name
        port.model.multi_connection = multi_input
        port.model.locked = locked
        self._inputs.append(port)
        self.model.inputs[port.name()] = port.model
        return port


def create_group_node_class(graph, parent_window):

    class CustomGroupNode(GroupNode, StatusNode):
        __identifier__ = 'general'
        NODE_NAME = 'GroupNode'

        def __init__(self):
            super(CustomGroupNode, self).__init__(qgraphics_item=GroupNodeItem)
            self.model.port_deletion_allowed = True
            self.set_color(50, 50, 50)  # 设置一个深色背景

    return CustomGroupNode
