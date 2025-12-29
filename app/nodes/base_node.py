import time
import uuid

import numpy as np
from NodeGraphQt import NodeObject, BaseNode
from NodeGraphQt.base.commands import NodeVisibleCmd
from NodeGraphQt.constants import NodePropWidgetEnum
from loguru import logger

from app.utils.node_logger import NodeLogHandler
from app.utils.utils import _safe_equal
from app.widgets.dialog_widget.component_log_message_box import LogMessageBox

import numpy as np
from PyQt5 import QtWidgets


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


class BasicNodeWithGlobalProperty(NodeObject):
    """
    所有业务节点的基类
    """

    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self.parent_window = None
        self._output_values = {}
        self._input_values = {}
        self.column_select = {}
        self._node_logs = ""
        self._realtime_logs = ""
        self._bound_to_persistent_log = False
        self.model.add_property("persistent_id", str(uuid.uuid4()))

    @property
    def persistent_id(self):
        return self.model.get_property("persistent_id")

    # ===========================日志处理=================================================
    def init_logger(self):
        self.log_capture = NodeLogHandler(self.persistent_id, self._log_message, use_file_logging=True)

    def _log_message(self, node_id, message):
        if isinstance(message, str) and message.strip():
            if not message.endswith('\n'):
                message += '\n'
            self._realtime_logs += message

            # ✅ 通过 scheduler 推送日志（线程安全）
            if hasattr(self, '_log_message_emitter'):
                # 注意：这里假设你已将 run_id 存在 _current_run_id
                self._log_message_emitter(self._current_run_id, message)

            # 兼容旧弹窗（如果需要）
            if hasattr(self, 'log_capture') and self.log_capture and self.log_capture.log_window:
                try:
                    self.log_capture.log_window.add_log_entry(message)
                except Exception as e:
                    logger.error(f"Error sending log to window: {e}")

    def get_logs(self):
        """从持久化日志文件读取内容（最多5000行）"""
        if not hasattr(self, "log_capture"):
            self.init_logger()
        try:
            return self.log_capture.read_log_file()
        except Exception as e:
            logger.warning(f"读取日志失败: {e}")
            return "日志读取失败。"

    def show_logs(self):
        log_content = self.get_logs()
        w = LogMessageBox(log_content, self.parent_window)

        self.log_capture.set_log_window(w)
        # ---
        w.show()

    def set_output_value(self, port_name, value):
        if self._output_values is None:
            self._output_values = {}
        self._output_values[port_name] = value

    def clear_output_value(self):
        self._output_values = {}

    def get_output_value(self, port_name):
        if self._output_values is None:
            return None
        return self._output_values.get(port_name)