import re

from NodeGraphQt import BaseNode
from PyQt5 import QtCore

from app.components.base import PropertyType, GlobalVariableContext
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.status_node import StatusNode
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import resource_path
from app.widgets.node_widget.checkbox_widget import CheckBoxWidgetWrapper
from app.widgets.node_widget.custom_node_item import CustomNodeItem
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper


def create_branch_node(parent_window):
    class ConditionalBranchNode(BaseNode, StatusNode, BasicNodeWithGlobalProperty):
        category: str = "控制流"
        __identifier__ = 'control_flow'
        NODE_NAME = '条件分支'
        FULL_PATH = f"{category}/{NODE_NAME}"

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.set_icon(resource_path("./icons/条件分支.png"))
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

            self._sync_timer = None

        # 替换 _delayed_setup 中的 connect
        def _delayed_setup(self):
            widget = self.widget.get_custom_widget()
            widget.valueChanged.connect(self._on_conditions_changed)
            else_widget = self.get_widget("enable_else").get_custom_widget()
            else_widget.valueChanged.connect(self._on_conditions_changed)
            self._sync_output_ports()

        def _on_conditions_changed(self):
            if self._sync_timer:
                self._sync_timer.stop()
                self._sync_timer.deleteLater()
            self._sync_timer = QtCore.QTimer()
            self._sync_timer.setSingleShot(True)
            self._sync_timer.timeout.connect(self._sync_output_ports)
            self._sync_timer.start(400)

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
            """同步输出端口：严格按表单顺序重建，仅当端口名未变时恢复连线"""
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")

            # 1. 生成期望端口名列表（按顺序，自动去重）
            expected_names = []
            used_names = set()
            for cond in conditions:
                raw_name = cond.get("name", "branch").strip() or "branch"
                port_name = self._sanitize_port_name(raw_name)
                base = port_name
                counter = 1
                while port_name in used_names:
                    port_name = f"{base}_{counter}"
                    counter += 1
                used_names.add(port_name)
                expected_names.append(port_name)

            if enable_else:
                expected_names.append("else")

            # 2. 记录当前所有端口的连线状态：{port_name: [connected_port_objects]}
            current_connections = {}
            for port in self.output_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)  # 保存下游端口引用

            # 3. 安全删除所有现有输出端口
            for port in list(self.output_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_output(port.name())

            # 4. 按 expected_names 顺序重建端口
            for name in expected_names:
                self.add_output(name)

            # 5. 恢复连线：仅当“旧端口名 == 新端口名”且新端口存在
            new_ports = {p.name(): p for p in self.output_ports()}
            for old_name, connected_list in current_connections.items():
                if old_name in new_ports:
                    new_port = new_ports[old_name]
                    for downstream_port in connected_list:
                        # 检查下游是否还存在（防 dangling reference）
                        try:
                            if downstream_port.node() and downstream_port.node().graph:
                                new_port.connect_to(downstream_port, push_undo=False, emit_signal=False)
                        except Exception as e:
                            # 忽略已失效的连接
                            continue

        def _log_message(self, node_id, message):
            if isinstance(message, str) and message.strip():
                if not message.endswith('\n'):
                    message += '\n'
                self._node_logs += message

        def get_logs(self):
            return self._node_logs if self._node_logs else "无日志可用。"

        def show_logs(self):
            from app.widgets.dialog_widget.component_log_message_box import LogMessageBox
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

        def execute_sync(self, *args, **kwargs):
            """
            条件分支节点的 execute_sync：判断激活分支，并递归禁用未激活分支的整个子图。
            """
            # === [前面的输入收集、表达式求值逻辑保持不变] ===
            global_variable = self.model.get_property("global_variable")
            gv = GlobalVariableContext()
            gv.deserialize(global_variable)

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

            input_vars = {}
            for k, v in inputs_raw.items():
                safe_key = f"input_{k}"
                input_vars[safe_key] = v

            expr_engine = ExpressionEngine(global_vars_context=gv)

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

            # === 条件判断 ===
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")
            activated_branch = None

            for cond in conditions:
                expr = cond.get("expr", "").strip()
                if not expr:
                    continue
                try:
                    if expr_engine.is_pure_expression_block(expr):
                        result = expr_engine.evaluate_expression_block(expr, local_vars=input_vars)
                    else:
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

            # === 关键：递归禁用未激活分支的整个子图 ===
            graph = self.graph
            if graph is None:
                return {}

            visited = set()  # 防止循环依赖

            def _disable_subgraph(start_node, disable):
                """递归禁用 start_node 及其所有下游节点"""
                if start_node.id in visited:
                    return
                visited.add(start_node.id)
                start_node.set_disabled(disable)
                # 继续禁用所有下游
                for output_port in start_node.output_ports():
                    for in_port in output_port.connected_ports():
                        downstream = in_port.node()
                        if downstream:
                            _disable_subgraph(downstream, disable)

            # 遍历所有输出端口
            for port in self.output_ports():
                port_name = port.name()
                is_active = (port_name == activated_branch)

                for downstream_port in port.connected_ports():
                    downstream_node = downstream_port.node()
                    if downstream_node:
                        _disable_subgraph(downstream_node, not is_active)

            # 设置输出值（可选）
            if activated_branch:
                self.set_output_value(activated_branch, inputs)

    return ConditionalBranchNode