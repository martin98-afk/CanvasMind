# -*- coding: utf-8 -*-
import json
import os
import pickle
import re
import uuid
import base64

from NodeGraphQt import NodeObject
from PyQt5 import QtCore
from PyQt5.QtCore import QObject
from PyQt5.QtGui import QImage
from loguru import logger

# 导入业务相关的组件协议
from app.components.base import PROGRESS_MARKER, ComponentMessage
from app.utils.node_logger import NodeLogHandler
from app.widgets.dialog_widget.component_log_message_box import LogMessageBox

# 导入图像预览控件
# 确保该路径指向你之前优化过的那个 ImageWidgetWrapper 所在的模块
from app.widgets.node_widget.image_widget import ImageWidgetWrapper


class NodeSignals(QObject):
    """节点核心信号管理器"""
    intercepted_msg_signal = QtCore.pyqtSignal(dict)
    htmlReady = QtCore.pyqtSignal(str, bool)
    stream_data_updated = QtCore.pyqtSignal(object)


class BasicNodeWithGlobalProperty(NodeObject):
    """
    所有业务节点的基类
    集成了日志处理、中间协议分发、流式数据同步以及动态预览控件生成。
    """
    PATTERNS = {
        r'\s+': '_',
        r'\.+': '_'
    }

    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self.signals = NodeSignals()
        self.parent_window = None

        # --- 核心数据存储 ---
        self._output_values = {}
        self._input_values = {}
        self.column_select = {}
        self._node_logs = ""
        self._realtime_logs = ""
        self._bound_to_persistent_log = False

        # --- 动态控件管理 ---
        # 用于记录每个端口动态创建的图像预览控件，避免重复创建
        self._inline_image_widgets = {}

        # --- 性能优化：UI 刷新节流控制 ---
        self._stream_buffer = set()  # 记录待同步到全局变量的端口
        self._ui_update_timer = QtCore.QTimer()
        self._ui_update_timer.setSingleShot(True)
        self._ui_update_timer.timeout.connect(self._sync_buffer_to_global)
        self._ui_update_interval = 150  # 刷新频率限制 (ms)

        # 绑定核心信号
        self.signals.intercepted_msg_signal.connect(self._message_router)
        self.signals.stream_data_updated.connect(self._on_stream_data_received)

        # 初始化持久化 ID
        self.model.add_property("persistent_id", str(uuid.uuid4()))

    @property
    def persistent_id(self):
        return self.model.get_property("persistent_id")

    @property
    def safe_name(self):
        """获取符合 Python 变量命名的节点名"""
        pattern = r'\s+'
        return re.sub(pattern, '_', self.name())

    # =========================== 日志与协议解析逻辑 =================================

    def init_logger(self):
        """初始化节点专属日志处理器"""
        self.log_capture = NodeLogHandler(self.persistent_id, self._log_message, use_file_logging=True)

    def _log_message(self, node_id, message):
        """
        处理来自 Subprocess 的原始日志输出
        """
        # 1. 解析日志，提取并截获中间协议数据
        message = self._parse_and_filter_logs(message)

        if isinstance(message, str) and message.strip():
            if not message.endswith('\n'):
                message += '\n'
            self._realtime_logs += message

            # 2. 通过 scheduler 推送日志（用于主界面日志面板同步）
            if hasattr(self, '_log_message_emitter'):
                run_id = getattr(self, '_current_run_id', "default")
                self._log_message_emitter(run_id, message)

            # 3. 同步到旧弹窗窗口（如果已打开）
            if hasattr(self, 'log_capture') and self.log_capture and self.log_capture.log_window:
                try:
                    self.log_capture.log_window.add_log_entry(message)
                except Exception as e:
                    logger.error(f"Error sending log to window: {e}")

    def _parse_and_filter_logs(self, raw_text):
        """
        扫描日志行，拦截并解析特定的 JSON 协议数据 (PROGRESS_MARKER)
        """
        if not raw_text:
            return ""

        clean_lines = []
        lines = raw_text.splitlines()

        for line in lines:
            if PROGRESS_MARKER in line:
                try:
                    # 提取数据部分：[PROGRESS_DATA] {...JSON...}
                    json_str = line.split(PROGRESS_MARKER)[1].strip()
                    data = json.loads(json_str)

                    # 发送信号至消息路由中心
                    self.signals.intercepted_msg_signal.emit(data)

                    # 拦截成功后，该行不进入常规 UI 日志面板，保持日志整洁
                    continue
                except Exception as e:
                    logger.error(f"解析拦截消息失败: {e}")

            clean_lines.append(line)

        return "\n".join(clean_lines)

    def get_logs(self):
        """从持久化日志文件读取历史内容"""
        if not hasattr(self, "log_capture"):
            self.init_logger()
        try:
            return self.log_capture.read_log_file()
        except Exception as e:
            logger.warning(f"读取日志失败: {e}")
            return "日志读取失败。"

    def show_logs(self):
        """弹出详细日志查看窗口"""
        log_content = self.get_logs()
        w = LogMessageBox(log_content, self.parent_window)
        if hasattr(self, "log_capture"):
            self.log_capture.set_log_window(w)
        w.show()

    # =========================== 数据输出与变量管理 =================================

    def set_output_value(self, port_name, value):
        if self._output_values is None: self._output_values = {}
        self._output_values[port_name] = value

    def clear_output_value(self):
        self._output_values = {}

    def get_output_value(self, port_name):
        if self._output_values is None: return None
        return self._output_values.get(port_name)

    def rename_variable(self, old_names: list[str], new_names: list[str]):
        """
        极速重命名优化：使用正则单次扫描全量替换属性中的变量名
        """
        if not old_names: return

        mapping = dict(zip(old_names, new_names))
        pattern = re.compile('|'.join(map(re.escape, sorted(old_names, key=len, reverse=True))))

        def _replace_func(match):
            return mapping[match.group(0)]

        def _process_value(val):
            val_type = type(val)
            if val_type is str:
                # 预过滤提高效率
                if "node_vars." in val or "input." in val:
                    return pattern.sub(_replace_func, val)
                return val
            if val_type is list:
                return [_process_value(i) for i in val]
            if val_type is dict:
                return {k: _process_value(v) for k, v in val.items()}
            return val

        for prop_name, current_val in self.model.custom_properties.items():
            if current_val is None: continue
            new_val = _process_value(current_val)
            if current_val != new_val:
                self.set_property(prop_name, new_val, push_undo=False)

    # =========================== 消息分发与动态控件处理 ===============================

    def _message_router(self, msg_dict: dict):
        """
        分发处理来自拦截协议的消息
        """
        try:
            msg = ComponentMessage(**msg_dict)
            parts = msg.method.split(".")
            namespace = parts[0] if len(parts) > 1 else "default"
            action = parts[1] if len(parts) > 1 else parts[0]

            handler_name = f"_handle_{namespace}_{action}"
            handler = getattr(self, handler_name, self._handle_unknown_method)
            handler(msg.params, msg)
        except Exception as e:
            logger.error(f"消息路由失败: {e}")

    def _get_var_key(self, port_name):
        """生成全局变量映射 Key"""
        safe_name = self.name()
        safe_port_name = port_name
        for pattern, replacement in self.PATTERNS.items():
            safe_name = re.sub(pattern, replacement, safe_name)
            safe_port_name = re.sub(pattern, replacement, safe_port_name)
        return f"{safe_name}__{safe_port_name}"

    def _handle_stream_output(self, params: dict, msg: ComponentMessage):
        """
        核心消息处理器：处理流式输出。支持文本/列表增量同步，以及动态图像流探测。
        """
        try:
            if self._output_values is None: self._output_values = {}

            for port_name, info in params.items():
                new_data = info.get("data")
                data_type = info.get("data_type", "str")

                # --- 动态图像流处理判断 ---
                # 逻辑：如果数据显式声明为 image，或者内容是 Base64 图像
                is_image = (data_type == "image") or \
                           (isinstance(new_data, str) and new_data.startswith("data:image"))

                if is_image:
                    self._update_inline_image_widget(port_name, new_data)
                    # 图像流通常仅作 UI 预览，不一定需要实时同步庞大的 Base64 字符串到全局变量中
                    # 如果需要下游节点继续处理该数据，可以取消下面这一行的注释
                    # self._output_values[port_name] = new_data
                    continue

                # --- 标准数据增量同步逻辑 ---
                old_val = self._output_values.get(port_name)
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

                self._stream_buffer.add(port_name)

            # 触发 UI 节流刷新
            self.signals.stream_data_updated.emit(None)

        except Exception as e:
            logger.error(f"流式结果处理失败: {e}")

    def _update_inline_image_widget(self, port_name, image_data):
        """
        动态创建或更新节点内部的图像预览控件
        """
        # 1. 如果数据是 Base64 格式，则先转换为 QImage
        processed_val = image_data
        if isinstance(image_data, str) and image_data.startswith("data:image"):
            try:
                # 剥离 data:image/png;base64, 部分
                _, encoded = image_data.split(",", 1)
                img_bytes = base64.b64decode(encoded)
                processed_val = QImage.fromData(img_bytes)
            except Exception as e:
                logger.error(f"预览图像 Base64 解码失败: {e}")
                return

        # 2. 判断是否已存在该端口的预览控件
        if port_name not in self._inline_image_widgets:
            # 动态创建一个 ImageWidgetWrapper
            widget_name = f"preview_{port_name}"
            image_wrapper = ImageWidgetWrapper(
                parent=self.view,
                name=widget_name,
                default=processed_val,
                window=self.parent_window
            )

            # 将控件添加到节点 UI。指定 tab 为 'Preview'，若不存在会自动创建
            if widget_name in self.model._custom_prop:
                self.model._custom_prop.pop(widget_name)
            self.add_custom_widget(image_wrapper, tab='Preview')
            self._inline_image_widgets[port_name] = image_wrapper

            # 重要：动态添加 Widget 后必须强制节点重绘，否则节点尺寸不会撑开
            self.view.draw_node()
            logger.info(f"节点已动态添加图像预览控件: {port_name}")
        else:
            # 已存在控件，直接更新其值
            self._inline_image_widgets[port_name].set_value(processed_val)

    # =========================== 变量同步与节流逻辑 =================================

    def _on_stream_data_received(self, _):
        """接收到流更新信号，启动或重置计时器"""
        if not self._ui_update_timer.isActive():
            self._ui_update_timer.start(self._ui_update_interval)

    def _sync_buffer_to_global(self):
        """
        在计时器触发时，一次性同步所有累积的脏数据到全局变量中，极大减少信号开销。
        """
        if not self.parent_window or not self._stream_buffer:
            return

        has_changed = False
        scheduler = self.parent_window.scheduler

        for port_name in self._stream_buffer:
            var_key = self._get_var_key(port_name)
            var_obj = self.parent_window.global_variables.node_vars.get(var_key)

            if var_obj and var_obj.update_policy != "固定" and scheduler:
                # 从内存取最新的累积结果
                current_val = self._output_values.get(port_name)
                # 静默更新全局变量值
                scheduler.update_node_variable(var_key, current_val, var_obj.update_policy)
                has_changed = True

        self._stream_buffer.clear()

        # 统一触发一次全局 UI 刷新
        if has_changed:
            scheduler.node_vars_changed.emit()

        # 若当前节点处于选中状态且属性面板开启，更新其值显示
        if self.parent_window.property_panel:
            if self.selected() and len(self.parent_window.graph.selected_nodes()) == 1:
                self.parent_window.property_panel.update_properties(self)

    # =========================== 其它指令处理器 =================================

    def _handle_global_variable_clear(self, params: dict, msg: ComponentMessage):
        value = params.get("value", "")
        if value.startswith(params.get("type", "")):
            value = value.split("node_vars.")[1]
        if self.parent_window:
            self.parent_window._on_global_variables_changed(
                var_type="node_vars", var_name=value, action="clear"
            )

    def _handle_global_variable_add(self, params: dict, msg: ComponentMessage):
        value = params.get("value", "")
        if value and self.parent_window:
            self.parent_window.property_panel._add_output_to_global_variable(
                node=self, port_name=value,
            )

    def _handle_global_variable_delete(self, params: dict, msg: ComponentMessage):
        value = params.get("value", "")
        if value and self.parent_window:
            self.parent_window.property_panel._delete_output_from_global_variable(
                node=self, port_name=value,
            )

    def _handle_ui_ask(self, params: dict, msg: ComponentMessage):
        """处理人工干预对话框请求"""
        title = params.get("title", "人工干预")
        message = params.get("message", "")
        response_file = params.get("response_file")
        schema = params.get("schema")
        os.makedirs(os.path.dirname(response_file), exist_ok=True)

        def on_confirmed(result_data):
            with open(response_file, 'wb') as f:
                pickle.dump(result_data, f)

        self.parent_window.show_intervention_dialog(title, message, schema, on_confirmed)

    def _handle_unknown_method(self, params: dict, msg: ComponentMessage):
        logger.warning(f"收到未知指令: {msg.method}")