# -*- coding: utf-8 -*-
from NodeGraphQt import BaseNode
from NodeGraphQt.base.commands import NodeVisibleCmd
from NodeGraphQt.constants import NodePropWidgetEnum
from PyQt5 import QtWidgets

from app.utils.utils import _safe_equal


class PropertyChangedCmd(QtWidgets.QUndoCommand):
    """
    Node property changed command.
    """

    def __init__(self, node, name, value):
        QtWidgets.QUndoCommand.__init__(self)
        self.setText('property "{}:{}"'.format(node.name(), name))
        self.node = node
        self.name = name
        self.old_val = node.get_property(name)
        self.new_val = value

    def set_node_property(self, name, value):
        """
        updates the node view and model.
        """
        # set model data.
        model = self.node.model
        model.set_property(name, value)

        # set view data.
        view = self.node.view

        # view widgets.
        if hasattr(view, 'widgets') and name in view.widgets.keys():
            # Use safe comparison to prevent infinite loop
            if not _safe_equal(view.widgets[name].get_value(), value):
                view.widgets[name].set_value(value)

        # view properties.
        if name in view.properties.keys():
            if name == 'pos':
                name = 'xy_pos'
            setattr(view, name, value)

        # emit property changed signal.
        graph = self.node.graph
        graph.property_changed.emit(self.node, self.name, value)

    def undo(self):
        if not _safe_equal(self.old_val, self.new_val):
            self.set_node_property(self.name, self.old_val)

    def redo(self):
        if not _safe_equal(self.old_val, self.new_val):
            self.set_node_property(self.name, self.new_val)

class CustomBaseNode(BaseNode):

    def set_property(self, name, value, push_undo=True):
        """
        Set the value on the node custom property.

        Args:
            name (str): name of the property.
            value (object): property data (python built in types).
            push_undo (bool): register the command to the undo stack. (default: True)
        """
        # prevent signals from causing a infinite loop.
        current = self.get_property(name)

        # 如果是同一个对象引用，直接返回（可选优化）
        if current is value:
            return

        if _safe_equal(current, value):
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
        # prevent nodes from have the same name.
        if self.graph and name == 'name':
            value = self.graph.get_unique_name(value)
            self.NODE_NAME = value

        if self.graph:
            undo_cmd = PropertyChangedCmd(self, name, value)
            if name == 'name':
                undo_cmd.setText(
                    'renamed "{}" to "{}"'.format(self.name(), value)
                )
            if push_undo:
                undo_stack = self.graph.undo_stack()
                undo_stack.push(undo_cmd)
            else:
                undo_cmd.redo()
        else:
            if hasattr(self.view, name):
                setattr(self.view, name, value)
            try:
                self.model.set_property(name, value)
            except:
                self.model.add_property(name, value)

        # redraw the node for custom properties.
        if self.model.is_custom_property(name):
            self.view.draw_node()

    def add_custom_widget(self, widget, widget_type=None, tab=None):
        """
        Add a custom node widget into the node.

        see example :ref:`Embedding Custom Widgets`.

        Note:
            The ``value_changed`` signal from the added node widget is wired
            up to the :meth:`NodeObject.set_property` function.

        Args:
            widget (NodeBaseWidget): node widget class object.
            widget_type: widget flag to display in the
                :class:`NodeGraphQt.PropertiesBinWidget`
                (default: :attr:`NodeGraphQt.constants.NodePropWidgetEnum.HIDDEN`).
            tab (str): name of the widget tab to display in.
        """
        widget_type = widget_type or NodePropWidgetEnum.HIDDEN.value
        self.create_property(widget.get_name(),
                             widget.get_value(),
                             widget_type=widget_type,
                             tab=tab)
        widget.value_changed.connect(lambda k, v: self.set_property(k, v))
        widget._node = self
        self.view.add_widget(widget)
        #: redraw node to address calls outside the "__init__" func.
        self.view.draw_node()

        widget.parent()