import logging
import time
import uuid

from PyQt5 import QtCore

from app.components.base import PropertyType
from app.nodes.status_node import StatusNode
from app.scheduler.trigger_manager import WebhookManager, SchedulerManager, FileWatcherManager
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

            self.webhook_manager = WebhookManager()
            self.scheduler_manager = SchedulerManager()
            self.file_watcher_manager = FileWatcherManager()

            self._last_webhook_endpoint = None
            self._last_trigger_data = {}
            self._last_execution_time = 0.0

            # --- 新增：UI 防抖定时器 ---
            self._ui_sync_timer = QtCore.QTimer()
            self._ui_sync_timer.setSingleShot(True)
            self._ui_sync_timer.timeout.connect(self._do_backend_sync)

            self.property_defs = {
                "trigger_type": {
                    "type": PropertyType.CHOICE,
                    "label": "触发器类型",
                    "choices": ["停止触发", "运行时触发", "Webhook触发", "定时触发", "文件夹监听触发"],
                    "default": "停止触发"
                },
                "run_strategy": {
                    "type": PropertyType.CHOICE,
                    "label": "运行策略",
                    "choices": ["从此处运行", "运行到此处"],
                    "default": "从此处运行"
                },
                "enable_throttle": {
                    "type": PropertyType.BOOL,
                    "label": "启用执行节流",
                    "default": False
                },
                "throttle_interval": {
                    "type": PropertyType.FLOAT,
                    "label": "节流间隔 (秒)",
                    "default": 1.0
                },
                "webhook_endpoint": {
                    "type": PropertyType.TEXT,
                    "label": "Webhook 路由",
                    "default": f"/api/v1/trigger/{self.persistent_id}"
                },
                "cron_expression": {
                    "type": PropertyType.TEXT,
                    "label": "Cron 表达式",
                    "default": "*/30 * * * * *"
                },
                "watch_folder_path": {
                    "type": PropertyType.FILE,
                    "label": "监听文件夹路径",
                    "default": "folder"
                },
            }

            self.web_hook_widget = None
            self.crontab_widget = None
            self.watch_folder_widget = None
            self.throttle_interval_widget = None

            self._generate_parms_widget()

            self.add_input("input", multi_input=True, painter_func=draw_square_port)
            self.add_output('output')

            self.signals.execution_requested.connect(self._on_execution_signal_received)
            self.view.delete_signal.connect(self.on_deleted)

        def _generate_parms_widget(self):
            custom_widgets_num = len(self.property_defs) + 10

            for i, (prop_name, prop_def) in enumerate(self.property_defs.items()):
                prop_type = prop_def.get("type", PropertyType.TEXT)
                default = prop_def.get("default", "")
                label = prop_def.get("label", prop_name)
                z_val = custom_widgets_num - i

                if prop_type == PropertyType.CHOICE:
                    widget = ComboBoxWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, items=prop_def.get("choices", []),
                        window=parent_window, z_value=z_val
                    )
                    # 下拉框切换，通常建议立即同步
                    widget.get_custom_widget().valueChanged.connect(self._request_backend_sync)
                    self.add_custom_widget(widget, tab="properties")
                    self.set_property(prop_name, default)

                elif prop_type == PropertyType.BOOL:
                    widget = CheckBoxWidgetWrapper(
                        parent=self.view, name=prop_name, text=label, state=default,
                        window=parent_window, z_value=z_val
                    )
                    widget.get_custom_widget().valueChanged.connect(self._request_backend_sync)
                    self.add_custom_widget(widget, tab="properties")

                elif prop_type in PropertyType.TEXT:
                    widget = TextWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, type=prop_type,
                        default=str(default), window=parent_window, z_value=z_val
                    )
                    if prop_name == "webhook_endpoint":
                        self.web_hook_widget = widget
                    elif prop_name == "cron_expression":
                        self.crontab_widget = widget
                    widget.get_custom_widget().valueChanged.connect(self._request_backend_sync)
                    self.add_custom_widget(widget, tab='Properties')
                elif prop_type == PropertyType.FILE:
                    widget = FileSelectWrapper(
                        parent=self.view, name=prop_name, label=label, default=default, window=parent_window,
                        z_value=z_val
                    )
                    if prop_name == "watch_folder_path":
                        self.watch_folder_widget = widget
                    widget.get_custom_widget().valueChanged.connect(self._request_backend_sync)
                    self.add_custom_widget(widget, tab='Properties')
                elif prop_type == PropertyType.FLOAT:
                    widget = NumberWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, default=default, window=parent_window,
                        type=prop_type.name.lower(), z_value=custom_widgets_num - i
                    )
                    if prop_name == "throttle_interval":
                        self.throttle_interval_widget = widget
                    self.add_custom_widget(widget, tab='Properties')

        def _request_backend_sync(self):
            """当用户在输入时，重置定时器，只有停顿 500ms 后才执行后台同步"""
            # 先处理 UI 的显隐（立即执行）
            self._update_ui_visibility()
            # 重置定时器
            self._ui_sync_timer.stop()
            self._ui_sync_timer.start(500)  # 500 毫秒防抖

        def _sync_services_and_ui(self):
            """立即执行 UI 更新，并立即触发一次后台同步（用于下拉框/勾选框）"""
            self._update_ui_visibility()
            self._do_backend_sync()

        def _update_ui_visibility(self):
            """立即更新 UI 组件的可见性，不涉及后台注册"""
            trigger_type = self.get_property("trigger_type")

            if self.web_hook_widget: self.web_hook_widget.setVisible(trigger_type == "Webhook触发")
            if self.crontab_widget: self.crontab_widget.setVisible(trigger_type == "定时触发")
            if self.watch_folder_widget: self.watch_folder_widget.setVisible(trigger_type == "文件夹监听触发")
            self.view.draw_node()

        def _do_backend_sync(self):
            """真正执行后台服务注册/注销的操作"""
            trigger_type = self.get_property("trigger_type")
            canvas_name = parent_window.workflow_name

            # 1. 清理旧服务
            if self._last_webhook_endpoint:
                self.webhook_manager.unregister(self._last_webhook_endpoint)
            self.scheduler_manager.remove_job(self.persistent_id)
            self.file_watcher_manager.remove_watcher(self.persistent_id)
            # 2. 注册新服务
            if trigger_type == "Webhook触发":
                endpoint = self.get_property("webhook_endpoint")
                if endpoint:
                    self.webhook_manager.register(canvas_name, endpoint, self.trigger_execution)
                    self._last_webhook_endpoint = endpoint

            elif trigger_type == "定时触发":
                cron = self.get_property("cron_expression")
                if cron:
                    self.scheduler_manager.add_job(canvas_name, self.persistent_id, self.trigger_execution, cron)

            elif trigger_type == "文件夹监听触发":
                folder_path = self.get_property("watch_folder_path")
                if folder_path:
                    self.file_watcher_manager.add_watcher(
                        canvas_name, self.persistent_id, self.trigger_execution, folder_path
                    )

            logging.info(f"触发器后台服务同步完成: {trigger_type}")

        def trigger_execution(self, incoming_data=None, task_id=None):
            if self.get_property("enable_throttle"):
                current_time = time.time()
                interval = self.get_property("throttle_interval")
                if current_time - self._last_execution_time < interval:
                    return
                self._last_execution_time = current_time
            self.signals.execution_requested.emit(incoming_data or {}, task_id)

        def _on_execution_signal_received(self, incoming_data, task_id):
            self._last_trigger_data = incoming_data
            if not hasattr(self.parent_window, 'canvas_runner'): return

            if self.get_property("run_strategy") == "从此处运行":
                self.parent_window.canvas_runner.run_from(
                    start_node=self, triggered_data=self._last_trigger_data, task_id=task_id
                )
            else:
                self.parent_window.canvas_runner.run_to(
                    target_node=self, triggered_data=self._last_trigger_data, task_id=task_id
                )

        def execute_sync(self, *args, global_variable=None, **kwargs):
            try:
                self.init_logger()
                output_val = self._last_trigger_data
                self.set_output_value("output", output_val)
                return {"output": output_val}
            finally:
                if self.get_property("trigger_type") == "运行时触发":
                    self.signals.execution_requested.emit(self._last_trigger_data, uuid.uuid4().hex)

        def on_deleted(self):
            self._ui_sync_timer.stop()  # 停止定时器
            if self._last_webhook_endpoint:
                self.webhook_manager.unregister(self._last_webhook_endpoint)
            self.scheduler_manager.remove_job(self.persistent_id)
            self.file_watcher_manager.remove_watcher(self.persistent_id)

    return TriggerNode