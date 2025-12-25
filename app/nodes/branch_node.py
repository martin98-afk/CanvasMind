import re
from PyQt5 import QtCore

from app.components.base import PropertyType, GlobalVariableContext
from app.nodes.base_node import BasicNodeWithGlobalProperty, CustomBaseNode
from app.nodes.status_node import StatusNode, NodeStatus
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.utils import resource_path, draw_square_port
from app.widgets.node_widget.checkbox_widget import CheckBoxWidgetWrapper
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper


def create_branch_node(parent_window):

    class ConditionalBranchNode(CustomBaseNode, StatusNode, BasicNodeWithGlobalProperty):
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

            # === 新增：条件索引 → 实际端口名的映射（用于执行时精准激活）===
            self._condition_index_to_port = {}

            # === 初始化属性控件（但不立即同步端口）===
            self._init_properties()
            self.add_input('input', True, painter_func=draw_square_port)
            # === 延迟绑定监听器 + 延迟首次同步 ===
            self._delayed_setup()

            self._sync_timer = None

        def _delayed_setup(self):
            widget = self.widget.get_custom_widget()
            widget.valueChanged.connect(self._on_conditions_changed)
            else_widget = self.get_widget("enable_else").get_custom_widget()
            else_widget.valueChanged.connect(self._on_conditions_changed)
            execute_all_widget = self.get_widget("execute_all_matches").get_custom_widget()
            execute_all_widget.valueChanged.connect(self._on_conditions_changed)
            self._sync_output_ports()

        def _on_conditions_changed(self):
            if self._sync_timer:
                self._sync_timer.stop()
                self._sync_timer.deleteLater()
            self._sync_timer = QtCore.QTimer()
            self._sync_timer.setSingleShot(True)
            self._sync_timer.timeout.connect(self._sync_output_ports)
            self._sync_timer.start(0)

        def _init_properties(self):
            condition_schema = {
                "expr": {
                    "type": PropertyType.LONGTEXT.value,
                    "default": "",
                    "label": "表达式公式，用 $$ 包裹",
                },
                "name": {
                    "type": PropertyType.TEXT.value,
                    "default": "branch{{id}}",
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
                state=False
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
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")

            # === 1. 生成唯一端口名并建立 condition_index → port_name 映射 ===
            expected_names = []
            used_names = set()
            self._condition_index_to_port.clear()

            for i, cond in enumerate(conditions):
                raw_name = cond.get("name", "branch").strip() or "branch"
                port_name = self._sanitize_port_name(raw_name)
                base = port_name
                counter = 1
                while port_name in used_names:
                    port_name = f"{base}{counter}"
                    counter += 1
                used_names.add(port_name)
                expected_names.append(port_name)
                self._condition_index_to_port[i] = port_name  # ✅ 关键：记录映射

            if enable_else:
                expected_names.append("else")

            # === 2. 保存当前连线 ===
            current_connections = {}
            for port in self.output_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)

            # === 3. 删除所有输出端口 ===
            for port in list(self.output_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_output(port.name())

            # === 4. 重建端口 ===
            for name in expected_names:
                self.add_output(name)

            # === 5. 恢复连线（仅当名称未变）===
            new_ports = {p.name(): p for p in self.output_ports()}
            for old_name, connected_list in current_connections.items():
                if old_name in new_ports:
                    new_port = new_ports[old_name]
                    for downstream_port in connected_list:
                        try:
                            if downstream_port.node() and downstream_port.node().graph:
                                new_port.connect_to(downstream_port, push_undo=False, emit_signal=False)
                        except Exception:
                            continue

            # === 6. 更新属性面板（如选中）===
            if self.selected():
                QtCore.QTimer.singleShot(100, lambda: parent_window.property_panel.update_properties(self))

        # ========== 执行逻辑 ==========

        def _get_all_downstream_nodes(self, start_node, visited=None):
            if visited is None:
                visited = set()
            if start_node.id in visited:
                return set()
            visited.add(start_node.id)
            downstream_nodes = {start_node}
            for output_port in start_node.output_ports():
                for connected_port in output_port.connected_ports():
                    downstream_node = connected_port.node()
                    if downstream_node and downstream_node.id not in visited:
                        downstream_nodes.update(self._get_all_downstream_nodes(downstream_node, visited))
            return downstream_nodes

        def _determine_node_activation_status(self, node, active_branch_nodes, inactive_branch_nodes):
            active_reachable = any(node in self._get_all_downstream_nodes(active_start, set())
                                   for active_start in active_branch_nodes)
            if active_reachable:
                return True
            inactive_reachable = any(node in self._get_all_downstream_nodes(inactive_start, set())
                                     for inactive_start in inactive_branch_nodes)
            return not inactive_reachable  # 默认禁用

        def execute_sync(self, *args, **kwargs):
            self.init_logger()
            global_variable = self.model.get_property("global_variable")
            gv = GlobalVariableContext()
            gv.deserialize(global_variable)

            inputs_raw = {}
            input_vars = {}
            for input_port in self.input_ports():
                port_name = input_port.name()
                connected = input_port.connected_ports()
                if connected:
                    inputs_raw[port_name] = [
                        upstream.node()._output_values.get(upstream.name()) for upstream in connected
                    ]
                    safe_key = f"input_{port_name}"
                    input_vars[safe_key] = inputs_raw[port_name]
                    for upstream in connected:
                        safe_name = upstream.node().name().replace(" ", "_")
                        safe_key = f"input_{safe_name}__{upstream.name()}"
                        input_vars[safe_key] = upstream.node()._output_values.get(upstream.name())

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

            # === 条件求值 + 获取真实端口名 ===
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")
            execute_all = self.get_property("execute_all_matches")

            activated_branches = []

            for i, cond in enumerate(conditions):
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
                        # ✅ 使用映射获取实际端口名（唯一、去重后）
                        port_name = self._condition_index_to_port.get(i, f"branch{i}")
                        activated_branches.append(port_name)
                        if not execute_all:
                            break
                except Exception as e:
                    self._log_message(self.persistent_id, f"条件表达式错误 [{expr}]: {e}\n")
                    continue

            if not activated_branches and enable_else:
                activated_branches = ["else"]

            # === 获取激活/未激活分支的下游节点 ===
            graph = self.graph
            if graph is None:
                return {}

            active_downstream_nodes = []
            inactive_downstream_nodes = []

            for port in self.output_ports():
                port_name = port.name()
                is_active = port_name in activated_branches
                for downstream_port in port.connected_ports():
                    downstream_node = downstream_port.node()
                    if downstream_node:
                        if is_active:
                            active_downstream_nodes.append(downstream_node)
                        else:
                            inactive_downstream_nodes.append(downstream_node)

            # === 收集所有受影响节点并设置状态 ===
            all_affected_nodes = set()
            for node in active_downstream_nodes + inactive_downstream_nodes:
                all_affected_nodes.update(self._get_all_downstream_nodes(node, set()))

            for node in all_affected_nodes:
                should_activate = self._determine_node_activation_status(
                    node, active_downstream_nodes, inactive_downstream_nodes
                )
                if should_activate:
                    node.set_disabled(False)
                else:
                    node.set_disabled(True)
                    parent_window.set_node_status(node, NodeStatus.NODE_STATUS_DISABLED)
                    if hasattr(node, '_output_values'):
                        node._output_values = {}

            # === 设置输出值 ===
            self.clear_output_value()
            input_val = inputs["input"] if len(inputs["input"]) > 1 else inputs["input"][0]
            for branch in activated_branches:
                self.set_output_value(branch, input_val)

    return ConditionalBranchNode