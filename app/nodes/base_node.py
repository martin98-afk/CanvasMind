# -*- coding: utf-8 -*-
import json
import re
import uuid

from NodeGraphQt import NodeObject
from PyQt5 import QtCore
from PyQt5.QtCore import QObject
from loguru import logger

# 导入业务相关的组件协议
from app.components.base import PROGRESS_MARKER, ComponentMessage
from app.plugins.plugin_manager import NodePluginManager
from app.utils.node_logger import NodeLogHandler
from app.widgets.dialog_widget.component_log_message_box import LogMessageBox


class NodeSignals(QObject):
    """节点核心信号管理器"""
    intercepted_msg_signal = QtCore.pyqtSignal(dict)
    htmlReady = QtCore.pyqtSignal(object, bool)
    stream_data_updated = QtCore.pyqtSignal(object)
    portsReady = QtCore.pyqtSignal()


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
        self.set_icon(":/icons/同心圆.svg")

        # 1. 启动插件管理器并自动加载
        self.plugin_manager = NodePluginManager()
        # --- 核心数据存储 ---
        self._output_values = {}
        self._input_values = {}
        self.column_select = {}
        self._node_logs = ""
        self._realtime_logs = ""
        self._bound_to_persistent_log = False

        # --- 动态控件管理 ---
        # 用于记录每个端口动态创建的图像预览控件，避免重复创建
        self._inline_widgets = {}  # 统一管理所有动态创建的 widget (image/text/chart)
        self._visual_dirty_buffer = set()  # 记录待更新 UI 的端口名
        self._visual_config = {}  # 记录哪些端口需要 display

        # --- 性能优化：UI 刷新节流控制 ---
        self._stream_buffer = set()  # 记录待同步到全局变量的端口
        self._ui_update_timer = QtCore.QTimer()
        self._ui_update_timer.setSingleShot(True)
        # 核心逻辑：统一由这个 timer 处理全局变量同步 + UI 控件刷新
        self._ui_update_timer.timeout.connect(self._sync_and_refresh_ui)
        self._ui_update_interval = 300  # 稍微延长刷新间隔(300ms)以减轻 WebEngine 压力

        # 初始化持久化 ID
        self.model.add_property("persistent_id", str(uuid.uuid4()))
        # 记录节点是否被折叠
        self.model.add_property("_collapsed", False)
        self.model.add_property("_exec_mode", "subprocess")
        # 绑定核心信号
        if hasattr(self.view, "collapsed_toggle"):
            self.view.set_align("center")
            self.view.collapsed_toggle.connect(
                lambda toggled: self.model.set_property("_collapsed", toggled)
            )
            self.view.exec_mode_signal.connect(
                lambda mode: self.model.set_property("_exec_mode", mode)
            )
            self.view.center_signal.connect(lambda: self.parent_window.center_to([self]))
            self.view.delete_signal.connect(lambda: self.parent_window.delete_node(self))
            self.view.run_signal.connect(lambda: self.parent_window.run_node(self))
        self.signals.intercepted_msg_signal.connect(self._message_router)
        self.signals.stream_data_updated.connect(lambda _: self._ui_update_timer.start(300))

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
                    logger.exception(f"Error sending log to window: {e}")

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
                    logger.exception(f"解析拦截消息失败: {e}")

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
        """根据消息 Method 调度插件"""
        msg = ComponentMessage(**msg_dict)

        # 优先查找通用插件 (如 ui.ask)
        plugin = self.plugin_manager.get_plugin(msg.method)
        if plugin:
            plugin.handle(self, msg.params, msg)
        elif msg.method == "stream.output" or msg.method == "stream_output":
            self._handle_stream_output(msg.params, msg)

    def _process_visual_updates(self):
        """根据 Data Type 调度显示插件"""
        for port_name in list(self._visual_dirty_buffer):
            should_display, plugin_type = self._visual_config.get(port_name, (False, "str"))
            data = self._output_values.get(port_name)

            if not should_display:
                self._remove_inline_widget(port_name)
                continue

            # 调用特定数据类型的插件
            plugin = self.plugin_manager.get_plugin(plugin_type)
            if plugin:
                plugin.handle(self, {port_name: {"data": data}})
        self._visual_dirty_buffer.clear()

    # =========================== 内部流转逻辑 ===============================

    def _handle_stream_output(self, params: dict, msg: ComponentMessage):
        """只负责把数据存起来，并标记 dirty"""
        extra = getattr(msg, 'extra', {})
        for port_name, info in params.items():
            d_type = info.get("data_type", "str")
            plugin_type = info.get("plugin", None)
            # 数据存储与合并...
            self._output_values[port_name] = self._merge_data(port_name, info.get("data"), d_type)
            # 记录配置
            self._visual_config[port_name] = (extra.get('display', False), plugin_type)
            self._visual_dirty_buffer.add(port_name)
            self._stream_buffer.add(port_name)
        self.signals.stream_data_updated.emit(None)

    def _merge_data(self, port_name, new_data, data_type):
        """简单的数据合并逻辑"""
        old = self._output_values.get(port_name)
        if data_type == "str": return (old or "") + str(new_data)
        if data_type == "list":
            if not isinstance(old, list): old = []
            if isinstance(new_data, list):
                old.extend(new_data)
            else:
                old.append(new_data)
            return old
        return new_data

    def _get_var_key(self, port_name):
        """生成全局变量映射 Key"""
        safe_name = self.name()
        safe_port_name = port_name
        for pattern, replacement in self.PATTERNS.items():
            safe_name = re.sub(pattern, replacement, safe_name)
            safe_port_name = re.sub(pattern, replacement, safe_port_name)
        return f"{safe_name}__{safe_port_name}"

    def _sync_buffer_to_global(self):
        """同步全局变量的逻辑"""
        if not self.parent_window or not self._stream_buffer:
            return
        has_changed = False
        scheduler = self.parent_window.scheduler
        for port_name in self._stream_buffer:
            var_key = self._get_var_key(port_name)
            var_obj = self.parent_window.global_variables.node_vars.get(var_key)
            if var_obj and var_obj.update_policy != "固定" and scheduler:
                current_val = self._output_values.get(port_name)
                scheduler.update_node_variable(var_key, current_val, var_obj.update_policy)
                has_changed = True
        self._stream_buffer.clear()
        if has_changed:
            scheduler.node_vars_changed.emit()
        if self.parent_window.property_panel and self.selected():
            self.parent_window.property_panel.update_properties(self)

    # =========================== UI 辅助 (供插件调用) ===============================

    def _add_inline_widget(self, key, widget, tab):
        if key in self.model._custom_prop:
            self.model._custom_prop.pop(key)
        self.view.set_proxy_mode(False)
        self.add_custom_widget(widget, tab=tab)
        self._inline_widgets[key] = widget
        self.view.draw_node()

    def _remove_inline_widget(self, port_name):
        for k in list(self._inline_widgets.keys()):
            if k.endswith(f"_{port_name}"):
                w = self._inline_widgets.pop(k)
                self.view.remove_widget(w)

    def hide_inline_widgets(self):
        """隐藏指定类型的动态控件"""
        for widget_base_key in self._inline_widgets.keys():
            self.view.remove_widget(self._inline_widgets[widget_base_key])
            self._inline_widgets.get(widget_base_key).deleteLater()
        self._inline_widgets.clear()
        self.view.draw_node()

    def _sync_and_refresh_ui(self):
        self._process_visual_updates()
        self._sync_buffer_to_global()