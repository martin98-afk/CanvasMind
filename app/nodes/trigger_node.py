import time
import uuid
from PyQt5 import QtCore
from loguru import logger

from app.components.base import PropertyType
from app.nodes.status_node import StatusNode
from app.trigger_plugins.plugin_manager import TriggerPluginManager
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.custom_nodegraphqt.custom_port_item import draw_square_port
from app.widgets.node_widget.propeprty_widgets.combobox_widget import ComboBoxWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.file_select_widget import FileSelectWrapper
from app.widgets.node_widget.propeprty_widgets.spinbox_widget import NumberWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.text_edit_widget import TextWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.checkbox_widget import CheckBoxWidgetWrapper


def create_trigger_node(parent_window):
    class TriggerNode(CustomBaseNode, StatusNode):
        category: str = "触发器"
        __identifier__ = 'general'
        NODE_NAME = '触发器'
        FULL_PATH = f"{category}/{NODE_NAME}"
        description = "支持手动、Webhook、定时触发。数据由 Runner 统一管理。"

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self.set_icon(":/icons/触发器.svg")

            # 插件管理
            self.plugins = TriggerPluginManager().plugins
            self.plugin_widgets = {name: [] for name in self.plugins.keys()}

            self._active_plugin_name = None
            self._last_execution_time = 0.0
            # 用于保存对 Runner 信号的引用，方便解除绑定
            self._error_trigger_connected = False
            # 属性定义
            self.property_defs = {
                "trigger_type": {
                    "type": PropertyType.CHOICE,
                    "label": "触发器类型",
                    "choices": ["停止触发", "运行时触发", "运行失败触发"] + list(self.plugins.keys()),
                    "default": "停止触发"
                },
                "run_strategy": {
                    "type": PropertyType.CHOICE,
                    "label": "运行策略",
                    "choices": list(parent_window.run_strategies.keys()),
                    "default": "从此处运行",
                    "description": "选择运行策略，从此处运行: 从当前节点运行；运行到此处：从该节点的前置节点运行到此处；运行所在子图：运行触发器所在的连通图上所有节点；运行所有节点：运行画布的所有节点"
                },
                "enable_throttle": {
                    "type": PropertyType.BOOL, "label": "启用节流", "default": False,
                    "description": "是否启用节流，节流将限制触发器每秒触发的次数。"
                },
                "throttle_interval": {
                    "type": PropertyType.FLOAT, "label": "节流间隔(s)", "default": 1.0,
                    "description": "节流间隔，单位为秒。"
                }
            }

            # UI 防抖
            self._ui_sync_timer = QtCore.QTimer()
            self._ui_sync_timer.setSingleShot(True)
            self._ui_sync_timer.timeout.connect(self._do_backend_sync)

            # 初始化 UI
            self._generate_widgets()
            self.add_input("input", multi_input=True, painter_func=draw_square_port)
            self.add_output('output')

            # 信号绑定
            self.signals.execution_requested.connect(self._on_execution_signal_received)
            self._patch_view_drawing()
            self.view.rename_signal.connect(parent_window.rename_node_vars)
            self.view.rename_signal.connect(self._do_backend_sync)

        # --- UI 逻辑 (保持不变) ---
        def _generate_widgets(self):
            for i, (name, conf) in enumerate(self.property_defs.items()):
                widget = self._create_and_add_widget(name, conf, 200 - i)
                if "description" in conf:
                    widget.setToolTip(conf["description"])
            for p_name, plugin in self.plugins.items():
                props = plugin.get_properties(self)
                for i, (name, conf) in enumerate(props.items()):
                    widget = self._create_and_add_widget(name, conf, 100 - i)
                    if "description" in conf:
                        widget.setToolTip(conf["description"])
                    if widget: self.plugin_widgets[p_name].append(widget)

        def _create_and_add_widget(self, name, conf, z_value):
            p_type = conf["type"]
            label = conf["label"]
            w = None
            if p_type == PropertyType.CHOICE:
                w = ComboBoxWidgetWrapper(self.view, name, label, conf["choices"], z_value, self.parent_window)
            elif p_type == PropertyType.BOOL:
                w = CheckBoxWidgetWrapper(self.view, name, label, conf["default"], self.parent_window, z_value)
            elif p_type == PropertyType.TEXT:
                w = TextWidgetWrapper(self.view, name, label, p_type, str(conf["default"]), self.parent_window, z_value)
            elif p_type == PropertyType.FILE:
                w = FileSelectWrapper(self.view, name, label, conf["default"], self.parent_window, z_value)
            elif p_type == PropertyType.FLOAT:
                w = NumberWidgetWrapper(self.view, name, label, conf["default"], "float", self.parent_window, z_value)
            elif p_type == PropertyType.INT:
                w = NumberWidgetWrapper(self.view, name, label, conf["default"], "int", self.parent_window, z_value)
            if w:
                w.get_custom_widget().valueChanged.connect(self._request_sync)
                self.add_custom_widget(w, tab="Properties")
                return w
            return None

        def _patch_view_drawing(self):
            orig = self.view._draw_node_horizontal

            def patched(*args, **kwargs):
                if not self.view._proxy_mode and not self.view._is_collapsed:
                    curr_type = self.get_property("trigger_type")
                    for p_name, widgets in self.plugin_widgets.items():
                        for w in widgets: w.setVisible(curr_type == p_name)
                return orig(*args, **kwargs)

            self.view._draw_node_horizontal = patched

        def _request_sync(self):
            self.view._draw_node_horizontal()
            self._ui_sync_timer.stop()
            self._ui_sync_timer.start(500)

        def _do_backend_sync(self):
            curr_type = self.get_property("trigger_type")
            runner = self.parent_window.canvas_runner

            # 1. 处理失败触发器的信号绑定/解绑
            if curr_type == "运行失败触发":
                if not self._error_trigger_connected:
                    runner.workflow_error.connect(self._handle_runner_error_event)
                    self._error_trigger_connected = True
                    logger.info(f"节点 {self.NODE_NAME} 已激活失败监听。")
            else:
                if self._error_trigger_connected:
                    runner.workflow_error.disconnect(self._handle_runner_error_event)
                    self._error_trigger_connected = False

            # 2. 处理触发器插件的激活/反激活
            if self._active_plugin_name in self.plugins:
                self.plugins[self._active_plugin_name].deactivate(self.persistent_id)
                self._active_plugin_name = None

            if curr_type in self.plugins:
                plugin = self.plugins[curr_type]
                props = {k: self.get_property(k) for k in plugin.get_properties(self)}
                plugin.activate(self.parent_window.workflow_name, self, self.trigger_execution, props)
                self._active_plugin_name = curr_type

        def _handle_runner_error_event(self, error_msg):
            """当 Runner 报错时被调用"""
            logger.warning(f"检测到运行失败，触发异常处理工作流: {error_msg}")
            # 携带错误信息触发
            data = {
                "status": "error",
                "message": error_msg,
                "timestamp": time.time()
            }
            self.trigger_execution(data=data)

        # --- 核心逻辑改进：生产者 ---
        def trigger_execution(self, data=None, tid=None):
            """外部触发插件的回调：负责向 Runner 提交任务"""
            if self.get_property("enable_throttle"):
                if time.time() - self._last_execution_time < self.get_property("throttle_interval"):
                    return
            self._last_execution_time = time.time()

            # 生成任务 ID 并发送信号
            # 注意：此处产生的 tid 会进入 Runner 的 ExecutionTask
            task_id = tid or f"TRIG_{uuid.uuid4().hex[:8]}"
            self.signals.execution_requested.emit(data or {}, task_id)

        def _on_execution_signal_received(self, data, tid):
            """由信号触发，真正调用 Runner 的执行接口"""
            strategy = self.get_property("run_strategy")
            # 这里的 parent_window.run_strategies 内部应调用 runner.run_to/run_from 等
            method = self.parent_window.run_strategies.get(strategy)
            if method:
                # 传入数据和 ID，Runner 内部会封装成 ExecutionTask 入队
                method(self if strategy != "运行所有节点" else None, triggered_data=data, task_id=tid)

        # --- 核心逻辑改进：消费者 ---
        def execute_sync(self, *args, **kwargs):
            """
            引擎执行到本节点时：
            1. 从 kwargs 获取当前任务 ID
            2. 向 Runner 索要属于该 ID 的触发数据
            """
            inputs_raw = {}
            for input_port in self.input_ports():
                port_name = input_port.name()
                connected = input_port.connected_ports()
                if connected:
                    if input_port.model.multi_connection:
                        inputs_raw[port_name] = [up.node()._output_values.get(up.name()) for up in connected]
                    else:
                        inputs_raw[port_name] = connected[0].node()._output_values.get(connected[0].name())
            # 将输入变量应用于触发器的回调函数
            self.plugins[self._active_plugin_name].callback(self.persistent_id, inputs_raw)
            # 从 Runner 中领数据 (不再从节点自身变量拿)
            trigger_data = {}
            # 如果没有 task_id (如手动点击执行节点)，尝试获取 runner 当前正在跑的任务数据
            if self.parent_window.canvas_runner._current_task:
                trigger_data = self.parent_window.canvas_runner._current_task.triggered_data or {}

            # 设置节点输出
            self.set_output_value("output", trigger_data)

            # 处理运行时连动触发
            if self.get_property("trigger_type") == "运行时触发":
                self.trigger_execution(trigger_data)

            return {"output": trigger_data}

        def on_deleted(self):
            self._ui_sync_timer.stop()
            if self._active_plugin_name in self.plugins:
                self.plugins[self._active_plugin_name].deactivate(self.persistent_id)

    return TriggerNode