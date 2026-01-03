import json
import uuid

from NodeGraphQt import NodeObject, BaseNode
from NodeGraphQt.base.commands import NodeVisibleCmd
from NodeGraphQt.constants import NodePropWidgetEnum
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QObject
from loguru import logger

from app.components.base import PROGRESS_MARKER, ComponentMessage
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import _safe_equal
from app.widgets.dialog_widget.component_log_message_box import LogMessageBox


class NodeSignals(QObject):
    intercepted_msg_signal = QtCore.pyqtSignal(dict)
    htmlReady = QtCore.pyqtSignal(str)
    stream_data_updated = QtCore.pyqtSignal(str, object)


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
        self.signals = NodeSignals()
        self.parent_window = None
        self._output_values = {}
        self._input_values = {}
        self.column_select = {}
        self._node_logs = ""
        self._realtime_logs = ""
        self._bound_to_persistent_log = False
        self.signals.intercepted_msg_signal.connect(self._message_router)
        # --- 防抖/节流相关配置 ---
        self._ui_update_timer = QtCore.QTimer()
        self._ui_update_timer.setSingleShot(True)  # 设置为单次触发
        self._ui_update_timer.timeout.connect(self._trigger_ui_update)
        self._ui_update_interval = 150  # 刷新频率限制：150ms 刷新一次 UI
        self.signals.stream_data_updated.connect(self._on_stream_data_received)
        self.model.add_property("persistent_id", str(uuid.uuid4()))

    @property
    def persistent_id(self):
        return self.model.get_property("persistent_id")

    # ===========================日志处理=================================================
    def init_logger(self):
        self.log_capture = NodeLogHandler(self.persistent_id, self._log_message, use_file_logging=True)

    def _log_message(self, node_id, message):
        message = self._parse_and_filter_logs(message)
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

    def _parse_and_filter_logs(self, raw_text):
        """
        从原始日志中过滤出特殊的标记信息，并返回清洗后的日志
        """
        if not raw_text:
            return ""

        clean_lines = []
        lines = raw_text.splitlines()

        for line in lines:
            if PROGRESS_MARKER in line:
                try:
                    # 提取 JSON 部分
                    json_str = line.split(PROGRESS_MARKER)[1].strip()
                    data = json.loads(json_str)
                    # 触发截获处理程序
                    self.signals.intercepted_msg_signal.emit(data)
                    # 注意：这里我们不把这行放入 clean_lines，这样 UI 日志面板就不会显示这行 JSON
                    continue
                except Exception as e:
                    logger.error(f"解析拦截消息失败: {e}")

            clean_lines.append(line)

        return "\n".join(clean_lines)

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

    # --- 中间消息通信协议接收 ---
    def _message_router(self, msg_dict: dict):
        """
        根据 method 动态分发消息
        """
        try:
            # 1. 验证并解析协议
            msg = ComponentMessage(**msg_dict)

            # 2. 提取命名空间和动作
            parts = msg.method.split(".")
            namespace = parts[0] if len(parts) > 1 else "default"
            action = parts[1] if len(parts) > 1 else parts[0]

            # 3. 动态寻找处理函数: _handle_{namespace}_{action}
            handler_name = f"_handle_{namespace}_{action}"
            handler = getattr(self, handler_name, self._handle_unknown_method)

            # 4. 异步执行处理逻辑
            handler(msg.params, msg)

        except Exception as e:
            logger.error(f"消息路由失败: {e}")

    # --- 通用中间消息通信协议处理器 ---
    # --- 节点全局变量处理逻辑 ---
    def _handle_global_variable_clear(self, params: dict, msg: ComponentMessage):
        """
        处理全局变量清空逻辑
        """
        value = params.get("value", "")
        if value.startswith(type):
            value = value.split(".")[1]
        if self.parent_window:
            self.parent_window._on_global_variables_changed(
                var_type="node_vars",
                var_name=value,
                action="clear"
            )

    def _handle_global_variable_add(self, params: dict, msg: ComponentMessage):
        """
        处理全局变量添加逻辑
        """
        value = params.get("value", "")
        if value and self.parent_window:
            self.parent_window.property_panel._add_output_to_global_variable(
                node=self,
                port_name=value,
            )

    def _handle_global_variable_delete(self, params: dict, msg: ComponentMessage):
        """
        处理全局变量删除逻辑
        """
        value = params.get("value", "")
        if value and self.parent_window:
            self.parent_window.property_panel._delete_output_from_global_variable(
                node=self,
                port_name=value,
            )

    # --- 结果流式输出处理逻辑 ---
    def _handle_stream_output(self, params: dict, msg: ComponentMessage):
        """
        处理节点中需要流式输出的结果。
        params 结构示例:
        {
            "output_port_1": {"data": "增加的文本", "data_type": "str"},
            "output_port_2": {"data": [1, 2, 3], "data_type": "list"}
        }
        """
        try:
            for port_name, info in params.items():
                new_data = info.get("data")
                data_type = info.get("data_type", "str")

                # 确保输出字典已初始化
                if self._output_values is None:
                    self._output_values = {}

                # 获取旧值并进行增量更新
                old_value = self._output_values.get(port_name)

                if data_type == "str":
                    # 字符串连接（适用于 LLM 文本流）
                    updated_value = (old_value if old_value else "") + str(new_data)
                    self.set_output_value(port_name, updated_value)

                elif data_type == "list":
                    # 列表追加（适用于 批量处理/采集 任务）
                    if old_value is None or not isinstance(old_value, list):
                        old_value = []
                    if isinstance(new_data, list):
                        old_value.extend(new_data)
                    else:
                        old_value.append(new_data)
                    self.set_output_value(port_name, old_value)

                elif data_type == "dict":
                    # 字典合并（适用于 状态更新/指标 监控）
                    if old_value is None or not isinstance(old_value, dict):
                        old_value = {}
                    if isinstance(new_data, dict):
                        old_value.update(new_data)
                    self.set_output_value(port_name, old_value)

                else:
                    # 默认行为：直接覆盖
                    self.set_output_value(port_name, new_data)

                # ✅ 发送流式更新信号，通知 UI 刷新（例如预览窗口、实时图表）
                # 建议在 NodeSignals 中定义 stream_data_updated 信号
                if hasattr(self.signals, 'stream_data_updated'):
                    self.signals.stream_data_updated.emit(port_name, self._output_values[port_name])

        except Exception as e:
            logger.error(f"流式结果处理失败: {e}")

    def _on_stream_data_received(self, port_name, value):
        """
        当收到流式数据时，不立即刷新 UI，而是开启/重启计时器
        """
        # 如果计时器没在跑，就启动它；如果在跑，就让它继续跑（节流模式）
        # 或者使用 singleShot 重新开始（防抖模式），这里推荐节流
        if not self._ui_update_timer.isActive():
            self._ui_update_timer.start(self._ui_update_interval)

    def _trigger_ui_update(self):
        """
        真正触发 UI 刷新的地方（在主线程执行）
        """
        if self.parent_window and self.parent_window.property_panel:
            if self.selected() and len(self.parent_window.graph.selected_nodes()) == 1:
                # 刷新属性面板
                self.parent_window.property_panel.update_properties(self)

    def _handle_data_preview(self, params: dict, msg: ComponentMessage):
        # 处理数据预览逻辑，比如弹出小窗显示表格预览
        pass

    def _handle_unknown_method(self, params: dict, msg: ComponentMessage):
        logger.warning(f"收到未知指令: {msg.method}")