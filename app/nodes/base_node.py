import json
import os
import pickle
import re
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
    htmlReady = QtCore.pyqtSignal(str, bool)
    stream_data_updated = QtCore.pyqtSignal(object)


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

        # 数据存储
        self._output_values = {}
        self._input_values = {}
        self.column_select = {}
        self._node_logs = ""
        self._realtime_logs = ""
        self._bound_to_persistent_log = False
        # --- 性能优化相关 ---
        self._var_key_cache = {}  # 缓存端口对应的全局变量Key
        self._stream_buffer = set()  # 记录哪些端口有待同步的数据更新
        self._ui_update_timer = QtCore.QTimer()
        self._ui_update_timer.setSingleShot(True)
        self._ui_update_timer.timeout.connect(self._sync_buffer_to_global)
        self._ui_update_interval = 150  # 刷新频率 (ms)

        self.signals.intercepted_msg_signal.connect(self._message_router)
        self.signals.stream_data_updated.connect(self._on_stream_data_received)
        self.model.add_property("persistent_id", str(uuid.uuid4()))

    @property
    def persistent_id(self):
        return self.model.get_property("persistent_id")

    @property
    def safe_name(self):
        pattern = r'\s+'
        return re.sub(pattern, '_', self.name())

    def _get_var_key(self, port_name):
        if port_name not in self._var_key_cache:
            self._var_key_cache[port_name] = f"{self.safe_name}__{port_name}"
        return self._var_key_cache[port_name]

    # 当节点改名时清空缓存
    def on_name_changed(self, old_name, new_name):
        self._var_key_cache.clear()

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

    def rename_variable(self, old_names: list[str], new_names: list[str]):
        """
        极速重命名：使用正则单次扫描 + 预筛选
        """
        if not old_names:
            return

        # 1. 预编译正则：将所有旧变量名合并成一个模式，且按长度降序排列（防止短名误伤长名）
        # 结果类似于: (node_vars\.Node11__out|node_vars\.Node1__out)
        mapping = dict(zip(old_names, new_names))
        pattern = re.compile('|'.join(map(re.escape, sorted(old_names, key=len, reverse=True))))

        # 替换函数：从映射表中取值
        def _replace_func(match):
            return mapping[match.group(0)]

        def _process_value(val):
            # 类型检查效率优化：优先处理最常见的字符串
            val_type = type(val)

            if val_type is str:
                # 预过滤：如果字符串里连 "node_vars." 都没有，直接跳过正则，极大地提速
                if "node_vars." in val or "input." in val:
                    return pattern.sub(_replace_func, val)
                return val

            if val_type is list:
                # 列表推导式效率高于 loop.append
                return [_process_value(i) for i in val]

            if val_type is dict:
                # 字典推导式
                return {k: _process_value(v) for k, v in val.items()}

            return val

        # 2. 遍历属性：直接通过 model 内部字典遍历，避免调用 get_property 的额外开销
        for prop_name, current_val in self.model.custom_properties.items():
            if current_val is None:
                continue

            new_val = _process_value(current_val)

            # 3. 仅在值真正改变时才调用 set_property (触发UI刷新)
            if current_val != new_val:
                self.set_property(prop_name, new_val, push_undo=False)

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
        if value.startswith(params.get("type", "")):
            value = value.split("node_vars.")[1]
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
        处理流式输出：仅更新内存数据并标记脏数据
        """
        try:
            if self._output_values is None: self._output_values = {}

            for port_name, info in params.items():
                new_data = info.get("data")
                data_type = info.get("data_type", "str")
                old_val = self._output_values.get(port_name)

                # 高性能增量更新
                if data_type == "str":
                    self._output_values[port_name] = (old_val or "") + str(new_data)
                elif data_type == "list":
                    if not isinstance(old_val, list): old_val = []
                    if isinstance(new_data, list):
                        old_val.extend(new_data)
                    else:
                        old_val.append(new_data)
                    self._output_values[port_name] = old_val
                elif data_type == "dict":
                    if not isinstance(old_val, dict): old_val = {}
                    if isinstance(new_data, dict): old_val.update(new_data)
                    self._output_values[port_name] = old_val
                else:
                    self._output_values[port_name] = new_data

                # 标记该端口需要同步
                self._stream_buffer.add(port_name)

            # 触发异步节流刷新
            self.signals.stream_data_updated.emit(None)  # 信号内容不再重要，因为数据在内存里

        except Exception as e:
            logger.error(f"流式结果处理失败: {e}")

    def _on_stream_data_received(self, _):
        """收到流信号时，仅启动/重置计时器"""
        if not self._ui_update_timer.isActive():
            self._ui_update_timer.start(self._ui_update_interval)

    def _sync_buffer_to_global(self):
        """
        【核心优化】在计时器触发时，一次性同步所有累积的数据并刷新一次 UI
        """
        if not self.parent_window or not self._stream_buffer:
            return

        has_changed = False
        scheduler = self.parent_window.scheduler

        # 1. 批量同步到全局变量 (不逐个发射信号)
        for port_name in self._stream_buffer:
            var_key = self._get_var_key(port_name)
            var_obj = self.parent_window.global_variables.node_vars.get(var_key)

            if var_obj and var_obj.update_policy != "固定" and scheduler:
                # 获取最新的内存值
                current_val = self._output_values.get(port_name)
                # 使用静默更新方法（见下文）
                scheduler.update_node_variable_silent(var_key, current_val, var_obj.update_policy)
                has_changed = True

        # 2. 清空缓冲区
        self._stream_buffer.clear()

        # 3. 统一触发一次 UI 刷新信号
        if has_changed:
            scheduler.node_vars_changed.emit()

        # 4. 如果当前节点被选中，刷新属性面板
        if self.parent_window.property_panel:
            if self.selected() and len(self.parent_window.graph.selected_nodes()) == 1:
                # 确保 update_properties 内部只更新值，不重建整个面板
                self.parent_window.property_panel.update_properties(self)

    def _handle_ui_ask(self, params: dict, msg: ComponentMessage):
        """
        处理来自组件的人工干预请求
        """
        title = params.get("title", "人工干预")
        message = params.get("message", "")
        response_file = params.get("response_file")
        schema = params.get("schema")
        # 确保响应文件目录存在
        os.makedirs(os.path.dirname(response_file), exist_ok=True)

        def on_confirmed(result_data):
            # 将用户输入的结果写入文件，节点那边就会感知到
            with open(response_file, 'wb') as f:
                pickle.dump(result_data, f)

        # 逻辑： 1. 弹出对话框 2. 用户输入 3. 写入文件
        self.parent_window.show_intervention_dialog(title, message, schema, on_confirmed)

    def _handle_unknown_method(self, params: dict, msg: ComponentMessage):
        logger.warning(f"收到未知指令: {msg.method}")