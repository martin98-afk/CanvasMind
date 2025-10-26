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

        def _find_merge_point(self, start_nodes):
            """
            从多个起始节点开始，找到它们的合并点（第一个共同的下游节点）。
            如果没有合并点，则返回None。
            """
            if not start_nodes:
                return None
            if len(start_nodes) == 1:
                # 如果只有一个分支，需要继续遍历找到所有下游节点
                # 但通常单一分支没有明确的合并点，除非有后续的汇聚逻辑
                return None

            # 为每个起始节点计算其下游节点集合
            downstream_sets = []
            for start_node in start_nodes:
                visited = set()
                downstream_nodes = set()

                def traverse_downstream(node):
                    if node.id in visited:
                        return
                    visited.add(node.id)
                    downstream_nodes.add(node)
                    for output_port in node.output_ports():
                        for connected_port in output_port.connected_ports():
                            downstream_node = connected_port.node()
                            if downstream_node and downstream_node.id not in visited:
                                traverse_downstream(downstream_node)

                traverse_downstream(start_node)
                downstream_sets.append(downstream_nodes)

            # 找到所有下游集合的交集（合并点）
            if not downstream_sets:
                return None

            merge_candidates = set.intersection(*downstream_sets) if len(downstream_sets) > 1 else downstream_sets[0]

            # 找到最早的合并点（离分支节点最近的）
            # 通过广度优先搜索来找到第一个共同节点
            from collections import deque

            queues = {i: deque([start_node]) for i, start_node in enumerate(start_nodes)}
            visited_by_branch = {i: {start_node.id} for i, start_node in enumerate(start_nodes)}
            all_visited = set(start_node.id for start_node in start_nodes)

            while any(q for q in queues.values()):
                for branch_idx, queue in queues.items():
                    if queue:
                        current_node = queue.popleft()
                        # 检查是否是合并点
                        if sum(1 for v in visited_by_branch.values() if current_node.id in v) > 1:
                            # 找到合并点
                            return current_node

                        # 遍历下游节点
                        for output_port in current_node.output_ports():
                            for connected_port in output_port.connected_ports():
                                downstream_node = connected_port.node()
                                if downstream_node:
                                    node_id = downstream_node.id
                                    if node_id not in visited_by_branch[branch_idx]:
                                        visited_by_branch[branch_idx].add(node_id)
                                        all_visited.add(node_id)
                                        queue.append(downstream_node)

            return None

        def _disable_parallel_paths_only(self, active_branch_nodes, inactive_branch_nodes):
            """
            只禁用并行路径，直到合并点。
            - active_branch_nodes: 激活分支的起始节点列表
            - inactive_branch_nodes: 未激活分支的起始节点列表
            """
            # 找到所有分支的合并点
            all_branch_start_nodes = active_branch_nodes + inactive_branch_nodes
            merge_point = self._find_merge_point(all_branch_start_nodes)

            # 禁用未激活分支的路径，直到合并点（不包括合并点）
            visited_inactive = set()
            for start_node in inactive_branch_nodes:
                self._disable_path_until_merge(start_node, merge_point, visited_inactive)

            # 激活激活分支的路径，直到合并点（不包括合并点）
            visited_active = set()
            for start_node in active_branch_nodes:
                self._enable_path_until_merge(start_node, merge_point, visited_active)

        def _disable_path_until_merge(self, start_node, merge_point, visited_set):
            """递归禁用路径直到合并点（不包括合并点本身）"""
            if start_node.id in visited_set:
                return
            visited_set.add(start_node.id)

            # 如果当前节点是合并点，则停止递归
            if merge_point and start_node.id == merge_point.id:
                return

            # 禁用当前节点
            start_node.set_disabled(True)
            start_node._output_values = {}

            # 递归处理下游节点
            for output_port in start_node.output_ports():
                for connected_port in output_port.connected_ports():
                    downstream_node = connected_port.node()
                    if downstream_node:
                        self._disable_path_until_merge(downstream_node, merge_point, visited_set)

        def _enable_path_until_merge(self, start_node, merge_point, visited_set):
            """递归启用路径直到合并点（不包括合并点本身）"""
            if start_node.id in visited_set:
                return
            visited_set.add(start_node.id)

            # 如果当前节点是合并点，则停止递归
            if merge_point and start_node.id == merge_point.id:
                return

            # 启用当前节点
            start_node.set_disabled(False)

            # 递归处理下游节点
            for output_port in start_node.output_ports():
                for connected_port in output_port.connected_ports():
                    downstream_node = connected_port.node()
                    if downstream_node:
                        self._enable_path_until_merge(downstream_node, merge_point, visited_set)

        def execute_sync(self, *args, **kwargs):
            """
            条件分支节点的 execute_sync：判断激活分支，只禁用并行部分直到合并点。
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

            # === 优化：只禁用并行路径，直到合并点 ===
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

            # 只禁用并行部分，直到合并点
            if active_downstream_nodes or inactive_downstream_nodes:
                self._disable_parallel_paths_only(active_downstream_nodes, inactive_downstream_nodes)

            self.clear_output_value()  # 先清空
            for branch in activated_branches:
                self.set_output_value(branch, inputs)

    return ConditionalBranchNode