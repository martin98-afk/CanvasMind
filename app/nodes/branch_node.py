import re

from NodeGraphQt import BaseNode
from PyQt5 import QtCore

from app.components.base import PropertyType, GlobalVariableContext
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.status_node import StatusNode
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.utils import resource_path, draw_square_port
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
            # === 初始化属性控件（但不立即同步端口）===
            self._init_properties()
            self.add_input('input', True, painter_func=draw_square_port)
            # === 关键：延迟绑定监听器 + 延迟首次同步 ===
            self._delayed_setup()

            self._sync_timer = None

        # 替换 _delayed_setup 中的 connect
        def _delayed_setup(self):
            # === 固定输入端口 ===
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
            self._sync_timer.start(100)

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
            if self.selected():
                QtCore.QTimer.singleShot(100, lambda: parent_window.property_panel.update_properties(self))

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

        def _get_all_downstream_nodes(self, start_node, visited=None):
            """获取所有下游节点"""
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

        def _get_all_upstream_nodes(self, start_node, visited=None):
            """获取所有上游节点（从条件分支节点开始向上）"""
            if visited is None:
                visited = set()

            if start_node.id in visited:
                return set()

            visited.add(start_node.id)
            upstream_nodes = {start_node}

            for input_port in start_node.input_ports():
                for connected_port in input_port.connected_ports():
                    upstream_node = connected_port.node()
                    if upstream_node and upstream_node.id not in visited:
                        upstream_nodes.update(self._get_all_upstream_nodes(upstream_node, visited))

            return upstream_nodes

        def _find_all_paths_to_nodes(self, start_node, target_nodes, current_path=None, all_paths=None):
            """找到从起始节点到目标节点的所有路径"""
            if current_path is None:
                current_path = []
            if all_paths is None:
                all_paths = []

            current_path = current_path + [start_node]

            if start_node in target_nodes:
                all_paths.append(current_path.copy())
                return all_paths

            # 避免循环
            if start_node in current_path[:-1]:
                return all_paths

            for output_port in start_node.output_ports():
                for connected_port in output_port.connected_ports():
                    downstream_node = connected_port.node()
                    if downstream_node and downstream_node not in current_path:
                        self._find_all_paths_to_nodes(downstream_node, target_nodes, current_path, all_paths)

            return all_paths

        def _get_all_reachable_nodes(self, start_nodes):
            """获取从起始节点集合可以到达的所有节点"""
            all_reachable = set()
            visited = set()

            def traverse_from_nodes(nodes):
                for node in nodes:
                    if node.id in visited:
                        continue
                    visited.add(node.id)
                    all_reachable.add(node)
                    for output_port in node.output_ports():
                        for connected_port in output_port.connected_ports():
                            downstream_node = connected_port.node()
                            if downstream_node and downstream_node.id not in visited:
                                traverse_from_nodes([downstream_node])

            traverse_from_nodes(start_nodes)
            return all_reachable

        def _determine_node_activation_status(self, node, active_branch_nodes, inactive_branch_nodes):
            """
            确定节点的激活状态：
            - 如果节点被任何激活分支的路径可达，则激活
            - 如果节点只被未激活分支的路径可达，则禁用
            - 如果节点被激活和未激活分支的路径都可达，则激活（只要有激活路径）
            """
            # 检查节点是否被激活分支的路径可达
            active_reachable = False
            for active_start in active_branch_nodes:
                reachable_from_active = self._get_all_downstream_nodes(active_start, set())
                if node in reachable_from_active:
                    active_reachable = True
                    break

            # 检查节点是否被未激活分支的路径可达
            inactive_reachable = False
            for inactive_start in inactive_branch_nodes:
                reachable_from_inactive = self._get_all_downstream_nodes(inactive_start, set())
                if node in reachable_from_inactive:
                    inactive_reachable = True
                    break

            # 决定激活状态
            if active_reachable:
                return True  # 只要有激活路径可达，就激活
            elif inactive_reachable:
                return False  # 只有未激活路径可达，就禁用
            else:
                return False  # 默认禁用（不在任何分支路径上）

        def execute_sync(self, *args, **kwargs):
            """
            条件分支节点的 execute_sync：判断激活分支，正确处理节点激活状态。
            """
            self.init_logger()
            # === [前面的输入收集、表达式求值逻辑保持不变] ===
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
                        safe_key = f"input_{port_name}_{safe_name}_{upstream.name()}"
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

            # === 获取所有输出端口的下游节点 ===
            graph = self.graph
            if graph is None:
                return {}

            # 获取所有输出端口的下游节点
            active_downstream_nodes = []
            inactive_downstream_nodes = []

            for port in self.output_ports():
                port_name = port.name()
                is_active = (port_name in activated_branches)

                for downstream_port in port.connected_ports():
                    downstream_node = downstream_port.node()
                    if downstream_node:
                        if is_active:
                            active_downstream_nodes.append(downstream_node)
                        else:
                            inactive_downstream_nodes.append(downstream_node)

            # 获取所有受影响的节点（激活和未激活分支的下游）
            all_affected_nodes = set()
            for node in active_downstream_nodes + inactive_downstream_nodes:
                all_affected_nodes.update(self._get_all_downstream_nodes(node, set()))

            # 确定每个节点的激活状态并设置
            for node in all_affected_nodes:
                should_activate = self._determine_node_activation_status(
                    node, active_downstream_nodes, inactive_downstream_nodes
                )

                if should_activate:
                    node.set_disabled(False)
                else:
                    node.set_disabled(True)
                    # 清空输出值
                    if hasattr(node, '_output_values'):
                        node._output_values = {}

            self.clear_output_value()  # 先清空
            for branch in activated_branches:
                self.set_output_value(branch, inputs["input"] if len(inputs["input"]) > 1 else inputs["input"][0])

    return ConditionalBranchNode