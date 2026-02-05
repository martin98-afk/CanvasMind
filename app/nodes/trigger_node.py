import logging

from PyQt5 import QtCore

from app.components.base import PropertyType
from app.nodes.status_node import StatusNode
from app.scheduler.trigger_manager import WebhookManager, SchedulerManager
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.custom_nodegraphqt.custom_port_item import draw_square_port
from app.widgets.node_widget.propeprty_widgets.combobox_widget import ComboBoxWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.text_edit_widget import TextWidgetWrapper


def create_trigger_node(parent_window):
    class TriggerNode(CustomBaseNode, StatusNode):
        category: str = "触发器"
        __identifier__ = 'general'
        NODE_NAME = '触发器'
        FULL_PATH = f"{category}/{NODE_NAME}"
        description = "流程的入口或终点。支持手动、Webhook、定时触发。可配置执行范围。"

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self.set_icon(":/icons/触发器.svg")

            # 内部记录上一次注册的信息，用于更新时清理旧服务
            self._last_webhook_endpoint = None
            self._last_cron_id = None
            self._last_trigger_data = {}

            # 1. 定义属性结构
            self.property_defs = {
                "trigger_type": {
                    "type": PropertyType.CHOICE,
                    "label": "触发器类型",
                    "choices": ["手动触发", "Webhook", "定时触发"],
                    "default": "手动触发",
                    "description": "选择如何启动此画布"
                },
                "run_strategy": {
                    "type": PropertyType.CHOICE,
                    "label": "运行策略",
                    "choices": ["从此处运行", "运行到此处"],
                    "default": "从此处运行",
                    "description": "从此处运行：执行下游节点；运行到此处：从头运行到此节点停止"
                },
                "webhook_endpoint": {
                    "type": PropertyType.TEXT,
                    "label": "Webhook 路由",
                    "default": f"/api/v1/trigger/{self.persistent_id}",
                    "description": "外部请求此地址将触发运行"
                },
                "cron_expression": {
                    "type": PropertyType.TEXT,
                    "label": "Cron 表达式",
                    "default": "*/30 * * * * *",
                    "description": "定时触发的 Cron 表达式 (如: */5 * * * * *)"
                }
            }

            # 2. 生成 UI 控件
            self._generate_parms_widget()

            # 3. 设置端口 (支持多输入作为终点)
            self.add_input("input", multi_input=True, painter_func=draw_square_port)
            self.add_output('output')

            # 4. 建立信号连接
            self.signals.execution_requested.connect(self._on_execution_signal_received)
            self.view.delete_signal.connect(self.on_deleted)
            # 5. 初始化同步
            QtCore.QTimer.singleShot(100, self._sync_services_and_ui)

        def _generate_parms_widget(self):
            """使用你要求的控件构建方式生成属性控件"""
            custom_widgets_num = len(self.property_defs) + 10

            for i, (prop_name, prop_def) in enumerate(self.property_defs.items()):
                prop_type = prop_def.get("type", PropertyType.TEXT)
                default = prop_def.get("default", "")
                label = prop_def.get("label", prop_name)
                description = prop_def.get("description", "")
                z_val = custom_widgets_num - i

                if prop_type == PropertyType.CHOICE:
                    choices = prop_def.get("choices", [])
                    widget = ComboBoxWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, items=choices,
                        window=parent_window, z_value=z_val
                    )
                    widget.get_custom_widget().valueChanged.connect(self._sync_services_and_ui)
                    if description: widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="properties")
                    self.set_property(prop_name, default if default in choices else choices[0])

                elif prop_type == PropertyType.TEXT:
                    widget = TextWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, type=prop_type,
                        default=str(default), window=parent_window, z_value=z_val
                    )
                    if description: widget.setToolTip(description)
                    self.add_custom_widget(widget, tab='Properties')

        def _sync_services_and_ui(self):
            trigger_type = self.get_property("trigger_type")
            # 获取单例实例
            wm = WebhookManager()
            sm = SchedulerManager()

            # 1. 总是先尝试清理旧的（防止残留）
            if self._last_webhook_endpoint:
                wm.unregister(self._last_webhook_endpoint)
            sm.remove_job(self.persistent_id)

            # 2. 根据当前模式注册
            if trigger_type == "Webhook":
                endpoint = self.get_property("webhook_endpoint")
                # 注册回调，传入 TriggerNode 的 trigger_execution 方法
                wm.register(endpoint, self.trigger_execution)
                self._last_webhook_endpoint = endpoint

            elif trigger_type == "定时触发":
                cron = self.get_property("cron_expression")
                if cron:
                    sm.add_job(self.persistent_id, self.trigger_execution, cron)

        def trigger_execution(self, incoming_data=None):
            """
            外部调用接口 (由 Webhook 服务器或 Scheduler 线程调用)
            """
            # 发射信号，将执行请求转交给主 UI 线程处理
            print(f"收到外部触发信号: {incoming_data}")
            self.signals.execution_requested.emit(incoming_data or {})

        def _on_execution_signal_received(self, incoming_data):
            """
            在 UI 线程中真正启动画布逻辑
            """
            print(f"收到内部触发信号: {incoming_data}")
            self._last_trigger_data = incoming_data
            strategy = self.get_property("run_strategy")

            if not hasattr(self.parent_window, 'canvas_runner'):
                logging.warning("parent_window 缺少 canvas_runner，无法启动运行。")
                return

            if strategy == "从此处运行":
                self.parent_window.canvas_runner.run_from(start_node=self)
            else:
                self.parent_window.canvas_runner.run_to(target_node=self)

        def execute_sync(self, *args, global_variable=None, **kwargs):
            """
            画布运行到本节点时的核心逻辑
            """
            self.init_logger()
            self._log_message(self.persistent_id, f"触发器 [ {self.get_property('trigger_type')} ] 已激活。\n")

            # 将触发时携带的数据（如 Webhook Body）存入输出，供下游使用
            output_val = self._last_trigger_data
            self.set_output_value("output", output_val)

            # 如果是“运行到此处”，可以在这里做最后的汇总处理
            return {"output": output_val}

        def on_deleted(self):
            """节点删除时自动注销后台服务"""
            if self._last_webhook_endpoint and hasattr(self.parent_window, 'webhook_manager'):
                self.parent_window.webhook_manager.unregister(self._last_webhook_endpoint)
            if self._last_cron_id and hasattr(self.parent_window, 'scheduler_manager'):
                self.parent_window.scheduler_manager.remove_job(self._last_cron_id)

    return TriggerNode