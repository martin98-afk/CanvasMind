import re

from PyQt5 import QtCore

from app.components.base import PropertyType, GlobalVariableContext
from app.nodes.base.status_node import StatusNode
from app.scheduler.expression_engine import ExpressionEngine
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.custom_nodegraphqt.custom_port_item import draw_square_port
from app.widgets.node_widget.propeprty_widgets.checkbox_widget import CheckBoxWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.dynamic_form_widget import DynamicFormWidgetWrapper


def create_branch_node(parent_window):
    class ConditionalBranchNode(CustomBaseNode, StatusNode):
        category: str = "控制流"
        __identifier__ = 'control_flow'
        NODE_NAME = '条件分支'
        FULL_PATH = f"{category}/{NODE_NAME}"
        description = ("根据条件执行不同的分支, 第一个输入为实际用来判断逻辑的数据，后续输入为逻辑判断输入，可以替代动态表单接收由逻辑判断节点"
                       "计算的布尔值，当逻辑判断输入有连接时会优先使用其连接节点的数据进行分支判断。")

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self.set_icon(":/icons/条件分支.png")
            self.model.port_deletion_allowed = True
            self.view.rename_signal.connect(parent_window.rename_node_vars)
            # 条件索引 → 实际输出端口名的映射
            self._condition_index_to_port = {}

            self._init_properties()
            # 初始主数据输入端口
            self.add_input('input', True, painter_func=draw_square_port)

            self._delayed_setup()
            self._sync_timer = None

        def _delayed_setup(self):
            widget = self.widget.get_custom_widget()
            widget.valueChanged.connect(self._on_conditions_changed)
            else_widget = self.get_widget("enable_else").get_custom_widget()
            else_widget.valueChanged.connect(self._on_conditions_changed)
            execute_all_widget = self.get_widget("execute_all_matches").get_custom_widget()
            execute_all_widget.valueChanged.connect(self._on_conditions_changed)
            self._sync_all_ports()

        def _on_conditions_changed(self):
            if self._sync_timer:
                self._sync_timer.stop()
                self._sync_timer.deleteLater()
            self._sync_timer = QtCore.QTimer()
            self._sync_timer.setSingleShot(True)
            self._sync_timer.timeout.connect(self._sync_all_ports)
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
                z_value=3
            )
            self.add_custom_widget(self.widget, tab='Properties')

            checkbox_widget = CheckBoxWidgetWrapper(
                parent=self.view,
                name="enable_else",
                text="启用默认分支（else）",
                state=True,
                window=parent_window,
                z_value=2
            )
            self.add_custom_widget(checkbox_widget, tab="properties")
            execute_all_widget = CheckBoxWidgetWrapper(
                parent=self.view,
                name="execute_all_matches",
                text="执行所有满足条件的分支",
                state=False,
                window=parent_window,
                z_value=1
            )
            self.add_custom_widget(execute_all_widget, tab="properties")

        def _sanitize_port_name(self, name: str) -> str:
            if not name:
                name = "branch"
            name = re.sub(r"[^a-zA-Z0-9_]", "_", str(name))
            if name and name[0].isdigit():
                name = "b_" + name
            return name

        def _sync_all_ports(self):
            """同步输入和输出端口"""
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")

            # 1. 确定预期的端口列表
            expected_output_names = []
            expected_input_cond_names = []  # 只有普通分支有输入端口
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

                expected_output_names.append(port_name)
                expected_input_cond_names.append(f"{port_name}_condition")
                self._condition_index_to_port[i] = port_name

            if enable_else:
                expected_output_names.append("else")
                # 注意：这里不向 expected_input_cond_names 添加 else_condition

            # 2. 保存现有连线 (输入和输出)
            old_connections = {"in": {}, "out": {}}
            for port in self.input_ports():
                if port.name() != "input":
                    connected = port.connected_ports()
                    if connected:
                        old_connections["in"][port.name()] = list(connected)

            for port in self.output_ports():
                connected = port.connected_ports()
                if connected:
                    old_connections["out"][port.name()] = list(connected)

            # 3. 删除旧的动态端口
            for port in list(self.output_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_output(port.name())

            for port in list(self.input_ports()):
                if port.name().endswith("_condition"):
                    port.clear_connections(push_undo=False, emit_signal=False)
                    self.delete_input(port.name())

            # 4. 重建端口
            for name in expected_output_names:
                self.add_output(name)

            for name in expected_input_cond_names:
                # 增加输入端口用来做同步判断
                self.add_input(name, multi_input=False)

            # 5. 恢复连线
            new_in_ports = {p.name(): p for p in self.input_ports()}
            new_out_ports = {p.name(): p for p in self.output_ports()}

            for name, connected_list in old_connections["in"].items():
                if name in new_in_ports:
                    for up_port in connected_list:
                        try:
                            up_port.connect_to(new_in_ports[name], push_undo=False, emit_signal=False)
                        except:
                            pass

            for name, connected_list in old_connections["out"].items():
                if name in new_out_ports:
                    for down_port in connected_list:
                        try:
                            new_out_ports[name].connect_to(down_port, push_undo=False, emit_signal=False)
                        except:
                            pass

            if self.selected():
                QtCore.QTimer.singleShot(100, lambda: parent_window.property_panel.update_properties(self))

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
            return not inactive_reachable

        def execute_sync(self, *args, global_variable=None, **kwargs):
            self.init_logger()
            gv = GlobalVariableContext()
            gv.deserialize(global_variable)

            # 收集所有输入
            inputs_raw = {}
            input_vars = {}
            for input_port in self.input_ports():
                port_name = input_port.name()
                connected = input_port.connected_ports()
                if connected:
                    if input_port.model.multi_connection:
                        inputs_raw[port_name] = [
                            upstream.node()._output_values.get(upstream.name()) for upstream in connected
                        ]
                        safe_key = f"input_{port_name}"
                        input_vars[safe_key] = inputs_raw[port_name]
                        for upstream in connected:
                            safe_name = upstream.node().name().replace(" ", "_")
                            safe_key = f"input_{safe_name}__{upstream.name()}"
                            input_vars[safe_key] = upstream.node()._output_values.get(upstream.name())
                    else:
                        inputs_raw[port_name] = connected[0].node()._output_values.get(connected[0].name())
                        # 当前节点输入端口key
                        safe_key = f"input_{port_name}"
                        input_vars[safe_key] = inputs_raw[port_name]
                        safe_name = connected[0].node().name().replace(" ", "_")
                        # 上游节点输出端口key
                        safe_key = f"input_{safe_name}__{connected[0].name()}"
                        input_vars[safe_key] = inputs_raw[port_name]

            expr_engine = ExpressionEngine(global_vars_context=gv)
            conditions = self.get_property("conditions") or []
            enable_else = self.get_property("enable_else")
            execute_all = self.get_property("execute_all_matches")

            activated_branches = []
            any_condition_matched = False

            # === 遍历分支判断逻辑 ===
            for i, cond in enumerate(conditions):
                port_name = self._condition_index_to_port.get(i, f"branch{i}")
                cond_input_name = f"{port_name}_condition"

                # 检查输入端口是否有连接
                input_port = self.get_input(cond_input_name)
                if input_port and input_port.connected_ports():
                    # 1. 优先使用端口值
                    port_val = inputs_raw.get(cond_input_name, False)
                    result = bool(port_val)
                else:
                    # 2. 如果没连接，使用属性里的表达式
                    expr = cond.get("expr", "").strip()
                    if not expr:
                        result = False
                    else:
                        try:
                            if expr_engine.is_pure_expression_block(expr):
                                result = expr_engine.evaluate_expression_block(expr, local_vars=input_vars)
                            else:
                                evaluated_str = expr_engine.evaluate_template(expr, local_vars=input_vars)
                                result = bool(
                                    evaluated_str and evaluated_str.strip() and "[ExprError:" not in evaluated_str)
                        except Exception as e:
                            self._log_message(self.persistent_id, f"条件表达式错误 [{expr}]: {e}\n")
                            result = False

                if result:
                    activated_branches.append(port_name)
                    any_condition_matched = True
                    if not execute_all:
                        break

            # === Else 分支逻辑：仅当没有任何分支满足且启用了else时执行 ===
            if not any_condition_matched and enable_else:
                activated_branches = ["else"]

            # === 状态更新与下游控制 ===
            graph = self.graph
            if graph is None: return {}

            active_downstream_nodes = []
            inactive_downstream_nodes = []

            for port in self.output_ports():
                p_name = port.name()
                is_active = p_name in activated_branches
                for downstream_port in port.connected_ports():
                    downstream_node = downstream_port.node()
                    if downstream_node:
                        if is_active:
                            active_downstream_nodes.append(downstream_node)
                        else:
                            inactive_downstream_nodes.append(downstream_node)

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

            # 设置输出
            self.clear_output_value()
            main_in = inputs_raw.get("input", [None])
            out_val = main_in if len(main_in) > 1 else main_in[0]
            for branch in activated_branches:
                self.set_output_value(branch, out_val)

    return ConditionalBranchNode
