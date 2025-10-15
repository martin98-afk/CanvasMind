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
from PyQt5 import QtCore

from app.components.base import PropertyType, GlobalVariableContext
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.create_dynamic_node import CustomNodeItem
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import get_icon
from app.widgets.node_widget.checkbox_widget import CheckBoxWidgetWrapper
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper


def create_branch_node(parent_window):
    class ConditionalBranchNode(BaseNode, BasicNodeWithGlobalProperty):
        __identifier__ = 'control_flow'
        NODE_NAME = '条件分支'

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.set_icon("./icons/条件分支.png")
            self.model.port_deletion_allowed = True
            self._node_logs = ""
            self._output_values = {}
            self._input_values = {}
            self.column_select = {}
            self.log_capture = NodeLogHandler(self.id, self._log_message, use_file_logging=True)

            # === 固定输入端口 ===
            self.add_input('input')

            # === 初始化属性控件（但不立即同步端口）===
            self._init_properties()

            # === 关键：延迟绑定监听器 + 延迟首次同步 ===
            QtCore.QTimer.singleShot(500, self._delayed_setup)

        def _delayed_setup(self):
            """延迟设置监听器和首次端口同步，确保属性已从序列化数据恢复"""
            # 绑定变化监听
            self.widget.get_custom_widget().valueChanged.connect(self._sync_output_ports)
            self.get_widget("enable_else").get_custom_widget().valueChanged.connect(self._sync_output_ports)
            # 首次同步端口（此时 get_property 已是保存的值）
            self._sync_output_ports()

        def _init_properties(self):
            """初始化条件列表和 else 开关（只创建 widget，不绑定逻辑）"""
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

            self.widget = DynamicFormWidgetWrapper(
                parent=self.view,
                name="conditions",
                label="分支条件",
                schema=processed_schema,
                window=parent_window,
                z_value=100
            )
            self.add_custom_widget(self.widget, tab='Properties')

            checkbox_widget = CheckBoxWidgetWrapper(
                parent=self.view,
                name="enable_else",
                text="启用默认分支（else）",
                state=True
            )
            self.add_custom_widget(checkbox_widget, tab="properties")

        def _sanitize_port_name(self, name: str) -> str:
            if not name:
                name = "branch"
            name = re.sub(r"[^a-zA-Z0-9_]", "_", str(name))
            if name and name[0].isdigit():
                name = "b_" + name
            return name

        def _sync_output_ports(self):
            """智能同步输出端口：保留有连线的端口，只清理无用且无连线的端口"""
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")

            # 1. 计算期望的端口名集合
            expected_names = set()
            used_names = set()
            for cond in conditions:
                raw_name = cond.get("name", "branch").strip() or "branch"
                port_name = self._sanitize_port_name(raw_name)
                counter = 1
                orig = port_name
                while port_name in used_names:
                    port_name = f"{orig}_{counter}"
                    counter += 1
                used_names.add(port_name)
                expected_names.add(port_name)

            if enable_else:
                expected_names.add("else")

            # 2. 获取当前所有输出端口
            current_ports = {port.name(): port for port in self.output_ports()}

            # 3. 决定哪些端口要删除：不在 expected 中 且 没有连线
            ports_to_delete = []
            for name, port in current_ports.items():
                if name not in expected_names:
                    # 检查是否有连线
                    if not port.connected_ports():
                        ports_to_delete.append(name)
                    else:
                        # 有连线，即使条件已删，也保留（避免断连）
                        pass

            # 4. 删除无用且无连线的端口
            for name in ports_to_delete:
                self.delete_output(name)

            # 5. 添加缺失的端口（expected 中有，但当前没有）
            for name in expected_names:
                if name not in current_ports:
                    self.add_output(name)

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

            # 记录哪个分支被激活
            activated_branch = None

            for cond in conditions:
                expr = cond.get("expr", "").strip()
                if not expr:
                    continue
                try:
                    if expr_engine.is_pure_expression_block(expr):
                        result = expr_engine.evaluate_expression_block(expr, local_vars=input_vars)
                    else:
                        # 非纯表达式（如混合模板），视为字符串，转为 bool
                        evaluated_str = expr_engine.evaluate_template(expr, local_vars=input_vars)
                        result = bool(evaluated_str and evaluated_str.strip() and "[ExprError:" not in evaluated_str)
                    if result:
                        branch_name = self._sanitize_port_name(cond.get("name", "branch"))
                        activated_branch = branch_name
                        break
                except Exception as e:
                    self._log_message(self.id, f"条件表达式错误 [{expr}]: {e}\n")
                    continue

            if activated_branch is None and enable_else:
                activated_branch = "else"

            # === 关键：控制下游节点的 disabled 状态 ===
            graph = self.graph  # 获取当前图实例
            if graph is None:
                return {}

            # 遍历所有输出端口
            for port in self.output_ports():
                port_name = port.name()
                is_active = (port_name == activated_branch)

                # 获取所有连接到该端口的下游节点
                connected_ports = port.connected_ports()
                for downstream_port in connected_ports:
                    downstream_node = downstream_port.node()
                    if downstream_node is None:
                        continue

                    # 设置 disabled 状态
                    downstream_node.set_disabled(not is_active)

            # 返回空 dict 或只包含激活分支的数据（可选）
            # 注意：如果下游节点被禁用，它们的 execute_sync 不会被调用
            return {activated_branch: inputs}

    return ConditionalBranchNode