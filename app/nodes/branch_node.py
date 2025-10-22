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
                    "default": "branch",
                    "label": "分支名称",
                },
            }
            processed_schema = {}
            for field_name, field_def in condition_schema.items():
                field_type_enum = PropertyType(field_def["type"])
                processed_schema[field_name] = {
                    "type": field_type_enum.name,
                    "label": field_def.get("label", field_name),
                    "choices": field_def.get("choices", []),
                    "default": field_def.get("default", "")
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
            execute_all_widget = CheckBoxWidgetWrapper(
                parent=self.view,
                name="execute_all_matches",
                text="执行所有满足条件的分支",
                state=False  # 默认关闭：只执行第一条
            )
            self.add_custom_widget(execute_all_widget, tab="properties")

        def _sanitize_port_name(self, name: str) -> str:
            if not name:
                name = "branch"
            name = re.sub(r"[^a-zA-Z0-9_]", "_", str(name))
            if name and name[0].isdigit():
                name = "b_" + name
            return name

        def _sync_output_ports(self):
            """同步输出端口：严格按表单顺序重建，仅当端口名未变时恢复连线，同时同步名称回表单"""
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")

            # 1. 生成期望端口名列表（按顺序，自动去重），同时记录映射关系
            expected_names = []
            used_names = set()
            name_mapping = {}  # {原始索引: 最终端口名}

            for i, cond in enumerate(conditions):
                raw_name = cond.get("name", "branch").strip() or "branch"
                port_name = self._sanitize_port_name(raw_name)
                base = port_name
                counter = 1
                while port_name in used_names:
                    port_name = f"{base}_{counter}"
                    counter += 1
                used_names.add(port_name)
                expected_names.append(port_name)
                name_mapping[i] = port_name

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

            # 5. 恢复连线：仅当"旧端口名 == 新端口名"且新端口存在
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

            # 6. 将生成的端口名称同步回表单（仅在名称发生变化时）
            self._sync_names_to_form(conditions, name_mapping)

        def _sync_names_to_form(self, conditions, name_mapping):
            """将生成的端口名称同步回表单"""
            updated_conditions = []
            name_changed = False

            for i, cond in enumerate(conditions):
                original_name = cond.get("name", "branch").strip() or "branch"
                generated_name = name_mapping.get(i, "branch")

                # 检查是否需要更新名称
                # 如果原始名称不符合规范（如包含特殊字符、以数字开头等）或与生成的名称不同，则更新
                sanitized_original = self._sanitize_port_name(original_name)
                needs_update = sanitized_original != generated_name

                if needs_update:
                    new_cond = cond.copy()
                    new_cond["name"] = generated_name
                    updated_conditions.append(new_cond)
                    name_changed = True
                else:
                    updated_conditions.append(cond)

            # 如果有名称变化，更新表单值（避免无限循环）
            if name_changed and updated_conditions != conditions:
                # 临时断开信号连接以避免循环触发
                widget = self.widget.get_custom_widget()
                try:
                    widget.valueChanged.disconnect(self._on_conditions_changed)
                except TypeError:
                    # 信号可能未连接，忽略
                    pass

                # 更新表单值
                self.set_property("conditions", updated_conditions)

                # 重新连接信号
                widget.valueChanged.connect(self._on_conditions_changed)

        def execute_sync(self, *args, **kwargs):
            """
            条件分支节点的 execute_sync：判断激活分支，并递归禁用未激活分支的整个子图。
            """
            self.init_logger()
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
            execute_all = self.get_property("execute_all_matches")  # 👈 新增

            activated_branches = []  # 改为列表，支持多分支

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
                        activated_branches.append(branch_name)
                        # 如果只执行第一条，遇到第一个就 break
                        if not execute_all:
                            break
                except Exception as e:
                    self._log_message(self.persistent_id, f"条件表达式错误 [{expr}]: {e}\n")
                    continue

            if not activated_branches and enable_else:
                activated_branches = ["else"]

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
                is_active = (port_name in activated_branches)  # 👈 改为判断是否在列表中

                for downstream_port in port.connected_ports():
                    downstream_node = downstream_port.node()
                    if downstream_node:
                        _disable_subgraph(downstream_node, not is_active)

            self.clear_output_value()  # 先清空
            for branch in activated_branches:
                self.set_output_value(branch, inputs)

    return ConditionalBranchNode