"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: branch_node.py
@time: 2025/10/15 15:38
@desc: 
"""
import re

from NodeGraphQt import BaseNode

from app.components.base import ArgumentType, PropertyType, ConnectionType, GlobalVariableContext
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.create_dynamic_node import CustomNodeItem
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import _evaluate_value_recursively
from app.widgets.node_widget.checkbox_widget import CheckBoxWidgetWrapper
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper


def create_branch_node(parent_window):

    class ConditionalBranchNode(BaseNode, BasicNodeWithGlobalProperty):
        __identifier__ = 'control_flow'
        NODE_NAME = '条件分支'

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.model.port_deletion_allowed = True
            self._node_logs = ""
            self._output_values = {}
            self._input_values = {}
            self.column_select = {}
            self.log_capture = NodeLogHandler(self.id, self._log_message, use_file_logging=True)

            # === 固定输入端口 ===
            self.add_input('input')

            # === 初始化属性（使用你的 DynamicFormWidget）===
            self._init_properties()

        def _init_properties(self):
            """初始化条件列表和 else 开关"""
            # 条件表单 schema
            condition_schema = {
                "expr": {
                    "type": PropertyType.LONGTEXT.value,
                    "default": "",
                    "label": "表达式公式，用 $$ 包裹",
                },
                "name": {
                    "type": PropertyType.TEXT.value,
                    "default": "",
                    "label": "分支名称",
                },
            }
            processed_schema = {}
            for field_name, field_def in condition_schema.items():
                field_type_enum = PropertyType(field_def["type"])
                processed_schema[field_name] = {
                    "type": field_type_enum.name,
                    "label": field_def.get("label", field_name),
                    "choices": field_def.get("choices", [])
                }
            # 使用你的 DynamicFormWidgetWrapper
            self.widget = DynamicFormWidgetWrapper(
                parent=self.view,
                name="conditions",
                label="分支条件",
                schema=processed_schema,
                window=parent_window,  # 如果不需要主窗口，可为 None
                z_value=100
            )
            self.widget.get_custom_widget().valueChanged.connect(self._sync_output_ports)
            self.add_custom_widget(self.widget, tab='Properties')

            # else 开关
            checkbox_widget = CheckBoxWidgetWrapper(
                    parent=self.view,
                    name="enable_else",
                    text="启用默认分支（else）",
                    state=True
                )
            checkbox_widget.get_custom_widget().valueChanged.connect(self._sync_output_ports)
            self.add_custom_widget(
                checkbox_widget,
                tab="properties"
            )

            # 设置默认值
            self.set_property("conditions", [{"expr": "True", "name": "branch1"}])
            self.set_property("enable_else", True)

        def _sanitize_port_name(self, name: str) -> str:
            """将分支名称转为合法端口名"""
            if not name:
                name = "branch"
            # 只保留字母、数字、下划线
            name = re.sub(r"[^a-zA-Z0-9_]", "_", str(name))
            if name[0].isdigit():
                name = "b_" + name
            return name

        def _sync_output_ports(self):
            """根据条件列表和 else 开关同步输出端口"""
            # 清除所有输出端口
            try:
                for port in list(self.output_ports()):
                    self.delete_output(port.name())
            except:
                pass

            # 添加条件分支端口
            conditions = self.get_property("conditions") or []
            used_names = set()
            for cond in conditions:
                raw_name = cond.get("name", "branch").strip()
                port_name = self._sanitize_port_name(raw_name)
                # 避免重复端口名（简单处理）
                counter = 1
                orig = port_name
                while port_name in used_names:
                    port_name = f"{orig}_{counter}"
                    counter += 1
                used_names.add(port_name)
                self.add_output(port_name)

            # 添加 else 端口
            try:
                if self.get_property("enable_else"):
                    self.add_output("else")
            except:
                pass

        def _log_message(self, node_id, message):
            if isinstance(message, str) and message.strip():
                if not message.endswith('\n'):
                    message += '\n'
                self._node_logs += message

        def get_logs(self):
            return self._node_logs if self._node_logs else "无日志可用。"

        def show_logs(self):
            from app.widgets.tree_widget.component_log_message_box import LogMessageBox
            log_content = self.get_logs()
            w = LogMessageBox(log_content, None)
            w.exec()

        def set_output_value(self, port_name, value):
            self._output_values[port_name] = value

        def clear_output_value(self):
            self._output_values = {}

        def get_output_value(self, port_name):
            return self._output_values.get(port_name)

        def on_run_complete(self, output):
            self._output_values = output

        # ✅ 关键：实现 execute_sync，但走条件路由逻辑
        def execute_sync(self, *args, **kwargs):
            """
            条件分支节点的 execute_sync 不执行外部脚本，
            而是在当前进程内完成条件判断和数据路由。
            """
            # === 全局变量 ===
            global_variable = self.model.get_property("global_variable")

            # === 【关键】创建表达式引擎并求值 ===
            gv = GlobalVariableContext()
            gv.deserialize(global_variable)

            # === 收集 inputs_raw ===
            inputs_raw = {}
            for input_port in self.input_ports():
                port_name = input_port.name()
                connected = input_port.connected_ports()
                if connected:
                    if len(connected) == 1:
                        upstream = connected[0]
                        value = upstream.node()._output_values.get(upstream.name())
                        inputs_raw[port_name] = value
                    else:
                        inputs_raw[port_name] = [
                            upstream.node()._output_values.get(upstream.name()) for upstream in connected
                        ]
                    if port_name in self.column_select:
                        inputs_raw[f"{port_name}_column_select"] = self.column_select.get(port_name)

            # === 构建 input_xxx 变量 ===
            input_vars = {}
            for k, v in inputs_raw.items():
                # 将 input.port_name 转为 input_port_name（避免点号）
                safe_key = f"input_{k}"
                input_vars[safe_key] = v

            # === 创建表达式引擎（带全局变量）===
            expr_engine = ExpressionEngine(global_vars_context=gv)

            # === 递归求值 params，传入 input_vars ===
            def _evaluate_with_inputs(value, engine, input_vars_dict):
                if isinstance(value, str):
                    return engine.evaluate_template(value, local_vars=input_vars_dict)
                elif isinstance(value, list):
                    return [_evaluate_with_inputs(v, engine, input_vars_dict) for v in value]
                elif isinstance(value, dict):
                    return {k: _evaluate_with_inputs(v, engine, input_vars_dict) for k, v in value.items()}
                else:
                    return value

            inputs = {k: _evaluate_with_inputs(v, expr_engine, input_vars) for k, v in inputs_raw.items()}

            # === 条件判断（互斥模式）===
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")

            output = {}

            for cond in conditions:
                expr = cond.get("expr", "").strip()
                if not expr:
                    continue

                try:
                    # 使用 ExpressionEngine 安全求值
                    result = expr_engine.evaluate_template(expr, local_vars=input_vars)
                    if result:
                        branch_name = self._sanitize_port_name(cond.get("name", "branch"))
                        output[branch_name] = inputs
                        print(branch_name)
                        break  # 互斥：只触发第一个满足的
                except Exception as e:
                    self._log_message(self.id, f"条件表达式错误 [{expr}]: {e}\n")
                    continue

            else:
                # 所有条件都不满足
                if enable_else:
                    output["else"] = inputs

            # === 设置输出值（供下游读取）===
            self._output_values = output

            # === 返回结果（符合 execute_sync 约定）===
            return output

    return ConditionalBranchNode