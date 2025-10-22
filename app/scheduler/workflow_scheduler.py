# -*- coding: utf-8 -*-
from collections import deque, defaultdict
from typing import List, Dict, Any, Optional, Callable

from NodeGraphQt import BackdropNode
from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger

from app.components.base import GlobalVariableContext
from app.nodes.status_node import NodeStatus
from app.scheduler.expression_engine import ExpressionEngine
from app.scheduler.node_list_executor import NodeListExecutor
from app.utils.utils import get_port_node


class WorkflowScheduler(QObject):
    """
    工作流调度器：支持条件分支控制流（通过 disabled 状态）
    - 执行前自动解锁所有节点
    - 条件分支节点可动态禁用下游
    - 调度器自动跳过 disabled 节点及其下游
    """
    node_started = pyqtSignal(str)  # node_id
    node_finished = pyqtSignal(str)
    node_error = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    node_status_changed = pyqtSignal(str, str)  # node_id, status
    property_changed = pyqtSignal(str)

    def __init__(
            self,
            graph,
            component_map: Dict[str, Any],
            get_node_status: Callable,
            get_python_exe: Callable[[], Optional[str]],
            global_variables: GlobalVariableContext,
            parent=None
    ):
        super().__init__(parent)
        self.parent = parent
        self.graph = graph
        self.global_variables = global_variables
        self.component_map = component_map
        self.get_node_status = get_node_status
        self.get_python_exe = get_python_exe
        self._executor = None

    def set_node_status(self, node, status):
        self.node_status_changed.emit(node.id, status)

    def get_executable_nodes(self):
        """获取所有顶层可执行节点（排除循环内部节点）"""
        all_nodes = self.graph.all_nodes()

        # 找出顶层循环 Backdrop
        loop_backdrops = [
            n for n in all_nodes
            if isinstance(n, BackdropNode)
        ]

        loop_internal_nodes = set()
        for backdrop in loop_backdrops:
            internal = backdrop.nodes()
            loop_internal_nodes.update(internal)

        executable_nodes = []
        for node in all_nodes:
            if node in loop_internal_nodes:
                continue
            executable_nodes.append(node)

        return executable_nodes

    def run_full(self):
        """执行整个工作流（排除 Backdrop）"""
        all_nodes = self.get_executable_nodes()
        if not all_nodes:
            self.error.emit("工作流中没有可执行节点")
            return

        execution_order = self._topological_sort(all_nodes)
        if execution_order is None:
            self.error.emit("检测到循环依赖，无法执行")
            return

        self._execute_nodes(execution_order)

    def run(self, node):
        """强制执行单个节点（即使 disabled）"""
        self._execute_nodes([node])

    def run_to(self, target_node):
        """执行到目标节点（含所有上游）"""
        nodes = self._get_ancestors_and_self(target_node)
        execution_order = self._topological_sort(nodes)
        if execution_order is None:
            self.error.emit("检测到循环依赖，无法执行")
            return
        self._execute_nodes(execution_order)

    def run_from(self, start_node):
        """从起始节点开始执行（含所有下游）"""
        nodes = self._get_descendants_and_self(start_node)
        execution_order = self._topological_sort(nodes)
        if execution_order is None:
            self.error.emit("检测到循环依赖，无法执行")
            return
        self._execute_nodes(execution_order)

    def _get_ancestors_and_self(self, node):
        visited = set()
        result = []

        def dfs(n):
            if n in visited:
                return
            visited.add(n)
            for input_port in n.input_ports():
                for out_port in input_port.connected_ports():
                    upstream = get_port_node(out_port)
                    if upstream:
                        dfs(upstream)
            result.append(n)

        dfs(node)
        return result

    def _get_descendants_and_self(self, node):
        visited = set()
        result = []

        def dfs(n):
            if n in visited:
                return
            visited.add(n)
            result.append(n)
            for output_port in n.output_ports():
                for in_port in output_port.connected_ports():
                    downstream = get_port_node(in_port)
                    if downstream:
                        dfs(downstream)

        dfs(node)
        return result

    def _topological_sort(self, nodes: List) -> Optional[List]:
        """对 active 节点（非 disabled）进行拓扑排序"""
        if not nodes:
            return []

        node_set = set(nodes)
        in_degree = {node: 0 for node in nodes}
        graph_deps = defaultdict(list)

        for node in nodes:
            for input_port in node.input_ports():
                for upstream_out in input_port.connected_ports():
                    upstream = get_port_node(upstream_out)
                    if upstream and upstream in node_set:
                        graph_deps[upstream].append(node)
                        in_degree[node] += 1

        queue = deque([n for n in nodes if in_degree[n] == 0])
        execution_order = []
        while queue:
            n = queue.popleft()
            execution_order.append(n)
            for neighbor in graph_deps[n]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(execution_order) != len(nodes):
            return None  # 存在环
        return execution_order

    def register_global_variable(self, nodes):
        for node in nodes:
            node.model.set_property("global_variable", self.global_variables.serialize())

    def _execute_nodes(self, nodes: List):
        """启动执行：先解锁所有节点，再执行 active 节点"""
        try:
            # ✅ 仍然做拓扑排序（保证依赖顺序），但接受其中包含后续会被禁用的节点
            execution_order = self._topological_sort(nodes)
            for node in execution_order:
                node.set_disabled(False)
                self.set_node_status(node, NodeStatus.NODE_STATUS_PENDING)
                if isinstance(node, BackdropNode):
                    for n in node.nodes():
                        n.set_disabled(False)
                        self.set_node_status(n, NodeStatus.NODE_STATUS_PENDING)

            if execution_order is None:
                self.error.emit("检测到循环依赖")
                return
            self.register_global_variable(execution_order)
            # 启动执行器
            self._executor = NodeListExecutor(
                main_window=None,
                nodes=execution_order,  # 传入拓扑序
                python_exe=self.get_python_exe(),
                scheduler=self
            )
            self._executor.component_map = self.component_map
            self._executor.signals.node_started.connect(self.node_started)
            self._executor.signals.node_finished.connect(self.node_finished)
            self._executor.signals.node_error.connect(self.node_error)
            self._executor.signals.finished.connect(self._on_finished)
            self._executor.signals.error.connect(lambda message: self._on_error(message, nodes))

            from PyQt5.QtCore import QThreadPool
            QThreadPool.globalInstance().start(self._executor)

        except Exception as e:
            import traceback
            logger.error(traceback.format_exc())
            self.error.emit(f"启动执行器失败: {str(e)}")

    def _execute_backdrop_sync(self, backdrop, check_cancel):
        """同步执行循环型 Backdrop（支持条件循环）"""
        try:
            # 获取上游结果
            input_data = []
            for input_port in backdrop.input_ports():
                connected = input_port.connected_ports()
                if connected:
                    if len(connected) == 1:
                        upstream = connected[0]
                        value = upstream.node()._output_values.get(upstream.name())
                        input_data = value
                    else:
                        input_data.extend(
                            [upstream.node()._output_values.get(upstream.name()) for upstream in connected]
                        )

            # 获取输入/输出代理节点
            input_proxy, output_proxy, execute_nodes = backdrop.get_nodes()
            if input_proxy is None or output_proxy is None:
                raise ValueError(f"循环体 {backdrop.name()} 缺少输入/输出代理节点")

            # 注册全局变量
            self.register_global_variable(execute_nodes)

            backdrop.model.set_property("current_index", 0)
            self.property_changed.emit(backdrop.id)

            # 根据循环模式执行
            if backdrop.TYPE == "iterate":
                results = self._execute_iterate_loop(backdrop, input_data, input_proxy, output_proxy, execute_nodes,
                                                     check_cancel)
            elif backdrop.TYPE == "loop":
                results = self._execute_condition_loop(backdrop, input_data, input_proxy, output_proxy, execute_nodes,
                                                       check_cancel)

            # 设置 Backdrop 的输出
            backdrop.set_output_value(results)
            self.set_node_status(backdrop, NodeStatus.NODE_STATUS_SUCCESS)

        except Exception as e:
            import traceback
            logger.error(f"执行循环 {backdrop.name()} 失败: {str(e)}")
            logger.error(traceback.format_exc())
            self.set_node_status(backdrop, NodeStatus.NODE_STATUS_FAILED)
            raise

    def _execute_iterate_loop(self, backdrop, input_data, input_proxy, output_proxy, execute_nodes, check_cancel):
        """执行迭代循环（遍历列表）"""
        if not isinstance(input_data, (list, tuple)):
            input_data = [input_data]

        results = []
        for index, data in enumerate(input_data):
            if check_cancel():
                return results

            input_proxy.set_output_value(data)

            # 执行内部节点（也收集输出，虽然不用于条件判断）
            internal_outputs = self._execute_internal_nodes(backdrop, execute_nodes, check_cancel)

            # 收集输出
            outputs = self._collect_outputs(output_proxy)
            backdrop.model.set_property("current_index", index + 1)
            self.property_changed.emit(backdrop.id)
            results.extend(outputs if isinstance(outputs, list) else [outputs])

        return results

    def _execute_condition_loop(self, backdrop, input_data, input_proxy, output_proxy, execute_nodes, check_cancel):
        """执行条件循环"""
        # 从 backdrop 属性获取循环配置
        loop_mode = backdrop.model.get_property("loop_mode")

        if loop_mode == 'count':
            return self._execute_count_loop(backdrop, input_data, input_proxy, output_proxy, execute_nodes,
                                            check_cancel)
        elif loop_mode == 'condition':
            return self._execute_condition_based_loop(backdrop, input_data, input_proxy, output_proxy, execute_nodes,
                                                      check_cancel)
        elif loop_mode == 'while':
            return self._execute_while_loop(backdrop, input_data, input_proxy, output_proxy, execute_nodes,
                                            check_cancel)
        else:
            raise ValueError(f"不支持的循环模式: {loop_mode}")

    def _execute_count_loop(self, backdrop, input_data, input_proxy, output_proxy, execute_nodes, check_cancel):
        """执行固定次数循环"""
        loop_nums = backdrop.model.get_property("loop_nums")
        outputs = None

        for index in range(loop_nums):
            if check_cancel():
                break

            input_proxy.set_output_value(input_data)
            # 执行内部节点（也收集输出，虽然不用于条件判断）
            internal_outputs = self._execute_internal_nodes(backdrop, execute_nodes, check_cancel)

            outputs = self._collect_outputs(output_proxy)
            input_data = outputs
            backdrop.model.set_property("current_index", index + 1)
            self.property_changed.emit(backdrop.id)

            if index < loop_nums - 1:  # 不是最后一次迭代
                input_data = outputs

        return outputs

    def _execute_condition_based_loop(self, backdrop, input_data, input_proxy, output_proxy, execute_nodes,
                                      check_cancel):
        """执行条件循环（基于条件表达式）"""
        max_iterations = backdrop.model.get_property("max_iterations")
        condition_expr = backdrop.model.get_property("loop_condition")
        outputs = None

        for index in range(max_iterations):
            if check_cancel():
                break

            input_proxy.set_output_value(input_data)
            # 执行内部节点并收集输出
            internal_outputs = self._execute_internal_nodes(backdrop, execute_nodes, check_cancel)

            outputs = self._collect_outputs(output_proxy)

            # 使用你的表达式引擎评估退出条件，注入内部节点输出
            should_continue = self._evaluate_condition_with_engine(condition_expr, outputs, backdrop, internal_outputs)
            if not should_continue:
                break

            input_data = outputs
            backdrop.model.set_property("current_index", index + 1)
            self.property_changed.emit(backdrop.id)

        return outputs

    def _execute_while_loop(self, backdrop, input_data, input_proxy, output_proxy, execute_nodes, check_cancel):
        """执行while循环"""
        max_iterations = backdrop.model.get_property("max_iterations")
        condition_expr = backdrop.model.get_property("loop_condition")
        outputs = None

        for index in range(max_iterations):
            if check_cancel():
                break

            # 首先检查while条件（使用当前输入数据和内部节点输出）
            # 在首次迭代时，内部节点尚未执行，所以 internal_outputs 为空
            # 这里我们先执行内部节点，再检查条件，符合大多数while循环的语义
            input_proxy.set_output_value(input_data)

            # 执行内部节点并收集输出
            internal_outputs = self._execute_internal_nodes(backdrop, execute_nodes, check_cancel)

            # 检查while条件（使用内部节点输出作为数据源）
            should_continue = self._evaluate_condition_with_engine(condition_expr, input_data, backdrop,
                                                                   internal_outputs)
            if not should_continue:
                # 如果条件不满足，收集当前输出并退出
                outputs = self._collect_outputs(output_proxy)
                break

            outputs = self._collect_outputs(output_proxy)
            input_data = outputs
            backdrop.model.set_property("current_index", index + 1)
            self.property_changed.emit(backdrop.id)

        return outputs

    def _execute_internal_nodes(self, backdrop, execute_nodes, check_cancel):
        """执行循环体内部节点，并收集输出结果"""
        internal_outputs = {}  # 收集内部节点的输出

        for node in execute_nodes:
            comp_cls = self.component_map.get(node.FULL_PATH)
            if check_cancel():
                return internal_outputs  # 提前返回收集到的结果

            self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING)
            self.property_changed.emit(backdrop.id)

            try:
                node.execute_sync(
                    comp_cls, python_executable=self.get_python_exe(), check_cancel=check_cancel
                )
                self.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
                self.property_changed.emit(backdrop.id)

                # 收集该节点的输出
                if hasattr(node, '_output_values'):
                    # 使用节点名称作为前缀，避免冲突
                    # node_name = re.sub(r'\s+|-', '_', node.name())
                    node_prefix = f"node_vars_{node.name()}"
                    for output_name, output_value in node._output_values.items():
                        # 使用 "节点名_输出端口名" 作为变量名
                        var_name = f"{node_prefix}_{output_name}"
                        internal_outputs[var_name] = output_value

            except Exception as e:
                self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
                self.property_changed.emit(backdrop.id)
                raise e
        return internal_outputs

    def _collect_outputs(self, output_proxy):
        """收集输出数据"""
        outputs = []
        for input_port in output_proxy.input_ports():
            connected = input_port.connected_ports()
            if connected:
                if len(connected) == 1:
                    upstream = connected[0]
                    value = upstream.node()._output_values.get(upstream.name())
                    outputs = value
                else:
                    outputs.extend(
                        [upstream.node()._output_values.get(upstream.name()) for upstream in connected]
                    )
        if not isinstance(outputs, list):
            return outputs

        return outputs if len(outputs) > 1 else (outputs[0] if outputs else None)

    def _evaluate_condition_with_engine(self, condition_expr, current_data, backdrop, internal_outputs=None):
        """使用表达式引擎评估条件表达式，并注入循环相关变量和内部节点输出"""
        if not condition_expr:
            return False

        try:
            engine = ExpressionEngine(self.global_variables)

            # 准备临时变量，这些变量将在表达式评估时可用
            temp_vars = {
                'data': current_data,  # 当前循环的数据
                'result': current_data,  # 同上（兼容别名）
                'current_index': backdrop.model.get_property("current_index"),  # 当前迭代索引
                'current_iteration': backdrop.model.get_property("current_index"),  # 当前迭代次数（从0开始）
                'iteration_count': backdrop.model.get_property("current_index") + 1,  # 当前迭代次数（从1开始）
                'loop_mode': backdrop.model.get_property("loop_mode"),  # 当前循环模式
                'max_iterations': backdrop.model.get_property("max_iterations"),  # 最大迭代次数
            }

            # 添加内部节点的输出作为临时变量
            if internal_outputs:
                temp_vars.update(internal_outputs)

            result = engine.evaluate_expression_block(condition_expr, temp_vars)
            # 将结果转换为布尔值
            if isinstance(result, str) and result.startswith('[ExprError:'):
                logger.warning(f"条件表达式评估失败: {condition_expr}, 错误: {result}")
                return False  # 表达式错误时停止循环

            return bool(result)

        except Exception as e:
            logger.warning(f"条件表达式评估异常: {condition_expr}, 错误: {e}")
            return False  # 异常时停止循环以防止无限循环

    def cancel(self):
        """取消当前执行"""
        if self._executor:
            self._executor.cancel()

    def _on_finished(self, _=None):
        self.finished.emit()

    def _on_error(self, msg: str, nodes: list):
        self.error.emit(msg or "执行过程中发生未知错误")
        # 节点报错把后续节点置为未运行
        for node in nodes:
            if getattr(node, "status", None) == NodeStatus.NODE_STATUS_PENDING:
                self.set_node_status(node, NodeStatus.NODE_STATUS_UNRUN)