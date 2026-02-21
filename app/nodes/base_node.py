# -*- coding: utf-8 -*-
import collections
import re
import uuid

from app.nodes.node_zmq import NodeZmqTransceiver

# 尝试导入高性能 json 库，如果不存在则回退
try:
    import orjson as json
except ImportError:
    import json

from NodeGraphQt import NodeObject
from PyQt5 import QtCore
from PyQt5.QtCore import QObject, QTimer
from loguru import logger
from typing import Dict, Any, Set

# 导入业务相关的组件协议
from app.components.base import ComponentMessage, PROGRESS_MARKER
from app.node_plugins.plugin_manager import NodePluginManager
from app.utils.node_logger import NodeLogHandler
from app.widgets.dialog_widget.component_log_message_box import LogMessageBox


# =========================================================================
# 节点基类
# =========================================================================

class NodeSignals(QObject):
    """节点核心信号管理器"""
    intercepted_msg_signal = QtCore.pyqtSignal(dict)
    htmlReady = QtCore.pyqtSignal(object, bool)
    stream_data_updated = QtCore.pyqtSignal(object)
    portsReady = QtCore.pyqtSignal()
    execution_requested = QtCore.pyqtSignal(object, str)  # incoming_data, task_id
    # 参数: payload(dict), node_instance(object)
    intervention_requested_signal = QtCore.pyqtSignal(dict)

    @QtCore.pyqtSlot(dict)
    def receive_zmq_data(self, data: dict):
        self.intercepted_msg_signal.emit(data)

    @QtCore.pyqtSlot(dict)
    def receive_zmq_intervention(self, payload: dict):
        self.intervention_requested_signal.emit(payload)


class BasicNodeWithGlobalProperty(NodeObject):
    """
    优化后的业务节点基类
    支持 ZMQ 流式传输、远程执行与人工干预
    """
    # --- 预编译正则表达式，避免在循环中重复编译 ---
    RE_SAFE_NAME = re.compile(r'\s+')
    RE_PATTERNS = {
        re.compile(r'\s+'): '_',
        re.compile(r'\.+'): '_'
    }

    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self.signals = NodeSignals()
        self.parent_window = None
        self.set_icon(":/icons/同心圆.svg")

        self.plugin_manager = NodePluginManager()

        # --- 核心数据存储优化 ---
        self._output_values: Dict[str, Any] = {}
        self._input_values: Dict[str, Any] = {}

        # 使用 deque 限制内存中存储的日志行数（例如保留最近1000行）
        self._log_buffer = collections.deque(maxlen=1000)
        self._last_intercepted_data = None  # 用于信号节流比较

        # --- ZMQ 通信组件 ---
        self._zmq_transceiver = None
        self._zmq_pub_port = 0
        self._zmq_svc_port = 0
        self._zmq_ip = "127.0.0.1"

        # --- 动态控件管理 ---
        self._inline_widgets = {}
        self._visual_dirty_buffer: Set[str] = set()
        self._visual_config = {}

        # --- UI 刷新节流控制 ---
        self._stream_buffer: Set[str] = set()
        self._ui_update_timer = QTimer()
        self._ui_update_timer.setSingleShot(True)
        self._ui_update_timer.timeout.connect(self._sync_and_refresh_ui)
        self._ui_update_interval = 300

        # 初始化属性
        self.model.add_property("persistent_id", str(uuid.uuid4()))
        self.model.add_property("_collapsed", False)
        self.model.add_property("_exec_mode", "subprocess")
        self.model.add_property("_data_select", {})

        # 绑定视图信号
        if hasattr(self.view, "collapsed_toggle"):
            self.view.collapsed_toggle.connect(self._on_collapsed_toggle)
            self.view.exec_mode_signal.connect(self._on_exec_mode_changed)
            self.view.center_signal.connect(lambda: self.parent_window.center_to([self]))
            self.view.delete_signal.connect(lambda: self.parent_window.delete_node(self))
            self.view.run_signal.connect(lambda: self.parent_window.run_node(self))

        self.signals.intercepted_msg_signal.connect(self._message_router)
        self.signals.stream_data_updated.connect(lambda _: self._ui_update_timer.start(self._ui_update_interval))

        # 绑定干预信号 (默认处理逻辑，也可在 Scheduler 中覆盖)
        self.signals.intervention_requested_signal.connect(self._default_intervention_handler)

    # --- 内部事件处理，减少 lambda 产生的匿名对象 ---
    def _on_collapsed_toggle(self, toggled):
        self.model.set_property("_collapsed", toggled)

    def _on_exec_mode_changed(self, mode):
        self.model.set_property("_exec_mode", mode)

    @property
    def persistent_id(self):
        return self.model.get_property("persistent_id")

    @property
    def safe_name(self):
        """优化后的 safe_name，使用预编译正则"""
        return self.RE_SAFE_NAME.sub('_', self.name())

    def set_property(self, name, value, push_undo=True):
        super().set_property(name, value, push_undo)
        if name in ['width', 'height'] and self.view and hasattr(self.view, 'update_size_from_property'):
            self.view.update_size_from_property(name, value)

    # =========================== ZMQ 环境配置与启动 (新增核心) =================================

    def setup_zmq_env(self, pub_port: int, svc_port: int, remote_ip: str = None) -> dict:
        """
        [Executor调用] 准备 ZMQ 环境
        :param pub_port: 分配的数据流端口 (PUB)
        :param svc_port: 分配的交互服务端口 (PAIR)
        :param remote_ip: 如果是远程SSH模式，传入远程IP；本地则传None
        :return: 传递给子进程的环境变量字典
        """
        self._zmq_pub_port = pub_port
        self._zmq_svc_port = svc_port

        # 确定连接 IP：如果是 SSH 且有 IP，则 UI 连远程；否则 UI 连本地
        if remote_ip:
            self._zmq_ip = remote_ip
        else:
            self._zmq_ip = "127.0.0.1"

        # 启动 UI 端的监听线程
        self._start_zmq_transceiver()

        # 返回环境变量，供 Executor 注入到进程中
        return {
            "NODE_ZMQ_PUB_PORT": str(pub_port),
            "NODE_ZMQ_SVC_PORT": str(svc_port)
        }

    def _start_zmq_transceiver(self):
        """启动后台通信线程"""
        # 停止旧线程
        self.stop_zmq()
        self._zmq_transceiver = NodeZmqTransceiver(self._zmq_ip, self._zmq_pub_port, self._zmq_svc_port)

        # 连接信号
        self._zmq_transceiver.stream_data_received.connect(self.signals.receive_zmq_data)
        self._zmq_transceiver.intervention_requested.connect(self.signals.receive_zmq_intervention)
        self._zmq_transceiver.connection_lost.connect(lambda err: logger.warning(f"ZMQ Error: {err}"))

        self._zmq_transceiver.start()

    def stop_zmq(self):
        """
        停止 ZMQ 线程并清理资源
        """
        if self._zmq_transceiver:
            # 1. 尝试优雅停止
            if hasattr(self._zmq_transceiver, 'stop'):
                self._zmq_transceiver.stop()

            # 2. 请求线程退出事件循环
            self._zmq_transceiver.quit()

            # 3. 等待线程结束 (设置超时防止界面卡死)
            if not self._zmq_transceiver.wait(2000):  # 等待2秒
                logger.warning(f"Node {self.name()}: ZMQ thread did not finish cleanly, forcing termination.")
                self._zmq_transceiver.terminate()  # 强制结束（兜底方案）
                self._zmq_transceiver.wait()

            # 4. 显式删除对象
            self._zmq_transceiver.deleteLater()
            self._zmq_transceiver = None

    def _on_zmq_intervention_req(self, payload: dict):
        """收到干预请求 -> 转发到主线程信号"""
        self.signals.intervention_requested_signal.emit(payload, self)

    def _default_intervention_handler(self, payload: dict):
        """
        [默认人工干预处理]
        如果外部没有连接此信号，这个槽函数会响应。
        弹出一个确认框，并将结果回传给节点。
        """
        # 解析 payload，例如: {"msg": "Confirm?", "data": {...}}
        msg = ComponentMessage(**payload)
        plugin = self.plugin_manager.get_plugin(msg.method)
        if plugin:
            response = plugin.handle(self, msg.params, msg)
        else:
            response = {"success": False, "msg": "Plugin not found"}
        # 回传给节点
        self.send_intervention_response(response)

    def send_intervention_response(self, data: dict):
        """将 UI 的决策发回给 ZMQ 节点"""
        if self._zmq_transceiver:
            self._zmq_transceiver.send_intervention_response(data)

    # =========================== 日志与协议解析逻辑 (保留原有逻辑) =================================

    def init_logger(self):
        self.log_capture = NodeLogHandler(self.persistent_id, self._log_message, use_file_logging=True)

    def _log_message(self, node_id, message):
        """
        处理来自 Subprocess 的日志输出（优化了字符串拼接性能）
        """
        # 1. 解析拦截协议
        clean_text = self._parse_and_filter_logs(message)

        if clean_text:
            # 使用 buffer 存储而不是直接字符串相加，避免 O(n^2) 拷贝
            self._log_buffer.append(clean_text)

            # 2. 通过 scheduler 推送日志
            if hasattr(self, '_log_message_emitter'):
                run_id = getattr(self, '_current_run_id', "default")
                self._log_message_emitter(run_id, clean_text + "\n")

            # 3. 同步到弹窗窗口
            if hasattr(self, 'log_capture') and self.log_capture and self.log_capture.log_window:
                try:
                    self.log_capture.log_window.add_log_entry(clean_text)
                except Exception as e:
                    logger.error(f"Error sending log to window: {e}")

    def _parse_and_filter_logs(self, raw_text: str) -> str:
        """
        极速解析逻辑：增加信号节流和高性能 JSON 解析
        """
        if not raw_text:
            return ""

        clean_lines = []
        lines = raw_text.splitlines()

        for line in lines:
            if PROGRESS_MARKER in line:
                try:
                    json_str = line.split(PROGRESS_MARKER)[1].strip()
                    # --- 信号节流：如果数据与上次完全一致，则不发射信号 ---
                    if json_str != self._last_intercepted_data:
                        # 使用 orjson 解析或标准 json
                        data = json.loads(json_str)
                        self.signals.intercepted_msg_signal.emit(data)
                        self._last_intercepted_data = json_str
                    continue
                except Exception as e:
                    logger.error(f"解析拦截消息失败: {e}")
            clean_lines.append(line)

        return "\n".join(clean_lines)

    def get_logs(self):
        """优先从 buffer 获取最新日志，buffer 满了从文件读"""
        if not self._log_buffer:
            if not hasattr(self, "log_capture"): self.init_logger()
            return self.log_capture.read_log_file()
        return "\n".join(self._log_buffer)

    def show_logs(self):
        log_content = self.get_logs()
        w = LogMessageBox(log_content, self.parent_window)
        if hasattr(self, "log_capture"):
            self.log_capture.set_log_window(w)
        w.show()

    # =========================== 变量与数据管理 =================================

    def set_output_value(self, port_name, value):
        self._output_values[port_name] = value

    def clear_output_value(self):
        self._output_values.clear()

    def get_output_value(self, port_name):
        return self._output_values.get(port_name)

    def rename_variable(self, old_names: list, new_names: list):
        if not old_names:
            return
        mapping = dict(zip(old_names, new_names))

        # --- 核心修复：移除边界断言，仅依赖长词优先精确匹配 ---
        sorted_names = sorted(old_names, key=len, reverse=True)
        # 直接拼接转义后的变量名（无边界断言）
        pattern_str = "|".join(map(re.escape, sorted_names))
        task_pattern = re.compile(pattern_str)

        def _replace_func(m):
            return mapping[m.group(0)]

        def _process_value(val):
            if isinstance(val, str):
                # 移除业务过滤（避免漏匹配），直接全局替换
                return task_pattern.sub(_replace_func, val)
            if isinstance(val, list):
                return [_process_value(i) for i in val]
            if isinstance(val, dict):
                return {k: _process_value(v) for k, v in val.items()}
            return val

        # --- 执行流程保持不变 ---
        updates = {}
        for prop_name, current_val in self.model.custom_properties.items():
            if current_val is None:
                continue
            new_val = _process_value(current_val)
            if current_val != new_val:
                updates[prop_name] = new_val

        for prop_name, new_val in updates.items():
            self.set_property(prop_name, new_val, push_undo=False)

    # =========================== 消息路由与 UI 刷新 ===============================

    def _message_router(self, msg_dict: dict):
        msg = ComponentMessage(**msg_dict)
        plugin = self.plugin_manager.get_plugin(msg.method)
        if plugin:
            plugin.handle(self, msg.params, msg)
        elif msg.method in ("stream.output", "stream_output"):
            self._handle_stream_output(msg.params, msg)

    def _handle_stream_output(self, params: dict, msg: ComponentMessage):
        """
        数据暂存优化：减少不必要的 dirty 标记
        """
        for port_name, info in params.items():
            d_type = info.get("data_type", "str")
            plugin_type = info.get("plugin")

            # 数据合并优化
            new_data = info.get("data")
            self._output_values[port_name] = self._merge_data(port_name, new_data, d_type)

            self._visual_config[port_name] = (plugin_type is not None, plugin_type)
            self._visual_dirty_buffer.add(port_name)
            self._stream_buffer.add(port_name)

        self.signals.stream_data_updated.emit(None)

    def _merge_data(self, port_name, new_data, data_type):
        """
        合并逻辑优化：避免 list 重复创建
        """
        old = self._output_values.get(port_name)
        if data_type == "str":
            return (old or "") + str(new_data)
        if data_type == "list":
            if not isinstance(old, list):
                old = []
            if isinstance(new_data, list):
                old.extend(new_data)  # 原地修改
            else:
                old.append(new_data)
            return old
        return new_data

    def _sync_and_refresh_ui(self):
        """
        统一节流刷新入口
        """
        # 1. 刷新可视化控件
        if self._visual_dirty_buffer:
            self._process_visual_updates()

        # 2. 同步全局变量
        if self._stream_buffer:
            self._sync_buffer_to_global()

    def _process_visual_updates(self):
        for port_name in list(self._visual_dirty_buffer):
            should_display, plugin_type = self._visual_config.get(port_name, (False, "str"))
            if not should_display:
                self._remove_inline_widget(port_name)
                continue
            plugin = self.plugin_manager.get_plugin(plugin_type)
            if plugin:
                data = self._output_values.get(port_name)
                plugin.handle(self, {port_name: {"data": data}})
        self._visual_dirty_buffer.clear()

    def _get_var_key(self, port_name):
        safe_name = self.name()
        safe_port_name = port_name
        # 使用预编译正则替换
        for pattern, replacement in self.RE_PATTERNS.items():
            safe_name = pattern.sub(replacement, safe_name)
            safe_port_name = pattern.sub(replacement, safe_port_name)
        return f"{safe_name}__{safe_port_name}"

    def _sync_buffer_to_global(self):
        if not self.parent_window or not self._stream_buffer:
            return

        has_changed = False
        scheduler = self.parent_window.scheduler
        global_vars = self.parent_window.global_variables

        for port_name in list(self._stream_buffer):
            var_key = self._get_var_key(port_name)
            var_obj = global_vars.node_vars.get(var_key)

            if var_obj and var_obj.update_policy != "固定" and scheduler:
                current_val = self._output_values.get(port_name)
                scheduler.update_node_variable(var_key, current_val, var_obj.update_policy)
                has_changed = True

        self._stream_buffer.clear()
        if has_changed:
            scheduler.node_vars_changed.emit()

        # 刷新属性面板
        if self.parent_window.property_panel and self.selected():
            self.parent_window.property_panel.update_properties(self)

    # =========================== UI 辅助 ===============================

    def _add_inline_widget(self, key, widget, tab):
        if key in self.model._custom_prop:
            self.model._custom_prop.pop(key)
        self.view.set_proxy_mode(False)
        self.add_custom_widget(widget, tab=tab)
        self._inline_widgets[key] = widget

    def _remove_inline_widget(self, port_name):
        suffix = f"_{port_name}"
        for k in list(self._inline_widgets.keys()):
            if k.endswith(suffix):
                w = self._inline_widgets.pop(k)
                self.view.remove_widget(w)

    def hide_inline_widgets(self):
        """隐藏指定类型的动态控件"""
        if self._inline_widgets:
            for w in self._inline_widgets.values():
                self.view.remove_widget(w)
            self._inline_widgets.clear()

    def on_deleted(self):
        """
        节点删除时的析构逻辑
        """
        # --- 1. 停止活跃任务 ---
        # 停止 UI 刷新定时器
        if hasattr(self, '_ui_update_timer') and self._ui_update_timer.isActive():
            self._ui_update_timer.stop()
            self._ui_update_timer.deleteLater()

        # 停止 ZMQ 线程
        self.stop_zmq()

        # --- 2. 清理数据缓存 (释放大内存) ---
        self._output_values.clear()
        self._input_values.clear()
        self._log_buffer.clear()
        self._visual_dirty_buffer.clear()
        self._stream_buffer.clear()
        self._last_intercepted_data = None

        # --- 3. 清理 UI 资源 ---
        self.hide_inline_widgets()

        # --- 4. 清理日志句柄 ---
        if hasattr(self, "log_capture") and self.log_capture:
            # 假设 NodeLogHandler 有 close 方法，如果没有建议加上
            if hasattr(self.log_capture, "close"):
                self.log_capture.close()
            # 解除引用
            self.log_capture = None

        # --- 5. 断开信号连接 (防止僵尸对象响应信号) ---
        try:
            # 断开自身信号管理器
            self.signals.disconnect()
        except Exception:
            pass  # 可能已经断开

        # 提示 GC
        import gc
        gc.collect()