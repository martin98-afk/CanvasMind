import logging
import time
import uuid
from PyQt5 import QtCore
from app.components.base import PropertyType
from app.nodes.status_node import StatusNode
from app.trigger_plugins.base_trigger import TRIGGER_PLUGINS
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
        description = "支持手动、Webhook、定时触发。具备触发节流及 UI 编辑防抖功能。"

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self.set_icon(":/icons/触发器.svg")

            # 加载插件注册表
            self.plugins = TRIGGER_PLUGINS
            # 核心修改：按插件存储 Widget 列表 { "插件名": [widget1, widget2] }
            self.plugin_widgets = {name: [] for name in self.plugins.keys()}

            self._active_plugin_name = None
            self._last_execution_time = 0.0
            self._last_trigger_data = {}

            # 初始化基础属性定义
            self.property_defs = {
                "trigger_type": {
                    "type": PropertyType.CHOICE,
                    "label": "触发器类型",
                    "choices": ["停止触发", "运行时触发"] + list(self.plugins.keys()),
                    "default": "停止触发"
                },
                "run_strategy": {
                    "type": PropertyType.CHOICE,
                    "label": "运行策略",
                    "choices": ["从此处运行", "运行到此处"],
                    "default": "从此处运行"
                },
                "enable_throttle": {"type": PropertyType.BOOL, "label": "启用节流", "default": False},
                "throttle_interval": {"type": PropertyType.FLOAT, "label": "节流间隔(s)", "default": 1.0}
            }

            # UI 防抖
            self._ui_sync_timer = QtCore.QTimer()
            self._ui_sync_timer.setSingleShot(True)
            self._ui_sync_timer.timeout.connect(self._do_backend_sync)

            # 生成 UI
            self._generate_widgets()
            self.add_input("input", multi_input=True, painter_func=draw_square_port)
            self.add_output('output')

            # 信号绑定
            self.signals.execution_requested.connect(self._on_execution_signal_received)
            self.view.delete_signal.connect(self.on_deleted)
            self._patch_view_drawing()

        def _generate_widgets(self):
            """通用的 UI 生成逻辑，包含插件 Widget 的归类存储"""
            # 1. 首先处理基础属性
            for i, (name, conf) in enumerate(self.property_defs.items()):
                self._create_and_add_widget(name, conf, 200 - i)

            # 2. 循环处理每个插件的专属属性
            for p_name, plugin in self.plugins.items():
                props = plugin.get_properties()
                for i, (name, conf) in enumerate(props.items()):
                    # 将生成的 widget 存入对应插件的列表中
                    widget = self._create_and_add_widget(name, conf, 100 - i)
                    if widget:
                        self.plugin_widgets[p_name].append(widget)

        def _create_and_add_widget(self, name, conf, z_value):
            """内部工具：根据配置创建 Widget 并添加到节点"""
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

            if w:
                w.get_custom_widget().valueChanged.connect(self._request_sync)
                self.add_custom_widget(w, tab="Properties")
                self.set_property(name, conf.get("default"))
                return w
            return None

        def _patch_view_drawing(self):
            """核心：根据 plugin_widgets 映射表直接控制显隐"""
            orig = self.view._draw_node_horizontal

            def patched(*args, **kwargs):
                if not self.view._proxy_mode and not self.view._is_collapsed:
                    curr_type = self.get_property("trigger_type")

                    # 遍历插件 Widget 映射表
                    for p_name, widgets in self.plugin_widgets.items():
                        is_active = (curr_type == p_name)
                        # 一个插件下的所有 widget 同步显隐
                        for w in widgets:
                            w.setVisible(is_active)

                return orig(*args, **kwargs)

            self.view._draw_node_horizontal = patched

        def _request_sync(self):
            # 立即触发重绘以应用 setVisible 变更
            self.view._draw_node_horizontal()
            # 延迟触发后端同步（防抖）
            self._ui_sync_timer.stop()
            self._ui_sync_timer.start(500)

        def _do_backend_sync(self):
            curr_type = self.get_property("trigger_type")
            canvas = self.parent_window.workflow_name

            if self._active_plugin_name in self.plugins:
                self.plugins[self._active_plugin_name].deactivate(self.persistent_id)
                self._active_plugin_name = None

            if curr_type in self.plugins:
                plugin = self.plugins[curr_type]
                # 只提取属于该插件定义的属性
                props = {k: self.get_property(k) for k in plugin.get_properties()}
                plugin.activate(canvas, self.persistent_id, self.trigger_execution, props)
                self._active_plugin_name = curr_type

            logging.info(f"触发器后端切换完成: {curr_type}")

        def trigger_execution(self, data=None, tid=None):
            if self.get_property("enable_throttle"):
                if time.time() - self._last_execution_time < self.get_property("throttle_interval"):
                    return
            self._last_execution_time = time.time()
            self.signals.execution_requested.emit(data or {}, tid or uuid.uuid4().hex)

        def _on_execution_signal_received(self, data, tid):
            self._last_trigger_data = data
            runner = getattr(self.parent_window, 'canvas_runner', None)
            if not runner: return

            method = runner.run_from if self.get_property("run_strategy") == "从此处运行" else runner.run_to
            method(self, triggered_data=data, task_id=tid)

        def execute_sync(self, *args, **kwargs):
            self.set_output_value("output", self._last_trigger_data)
            if self.get_property("trigger_type") == "运行时触发":
                self.trigger_execution(self._last_trigger_data)
            return {"output": self._last_trigger_data}

        def on_deleted(self):
            self._ui_sync_timer.stop()
            if self._active_plugin_name in self.plugins:
                self.plugins[self._active_plugin_name].deactivate(self.persistent_id)

    return TriggerNode