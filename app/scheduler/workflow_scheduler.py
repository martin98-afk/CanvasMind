# -*- coding: utf-8 -*-
from collections import deque, defaultdict
from typing import List, Dict, Any, Optional, Callable

from NodeGraphQt import BackdropNode
from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger

from app.components.base import GlobalVariableContext
from app.nodes.status_node import NodeStatus
from app.scheduler.node_list_executor import NodeListExecutor
from app.utils.utils import get_port_node


class WorkflowScheduler(QObject):
    """
    工作流调度器：支持条件分支控制流（通过 disabled 状态）
    - 执行前自动解锁所有节点
    - 条件分支节点可动态禁用下游
    - 调度器自动跳过 disabled 节点及其下游
    """
    node_started = pyqtSignal(str)      # node_id
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
            if (n.type_ == "control_flow.ControlFlowBackdrop"
                and n.control_flow_type == "loop"
                and not hasattr(n, 'parent'))
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
        """同步执行循环型 Backdrop（在主线程中调用）"""
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
            # 1. 获取输入数据（来自 backdrop 的 inputs 端口）
            if not isinstance(input_data, (list, tuple, dict)) and backdrop.TYPE == "loop":
                input_data = [input_data]
            # 2. 查找输入/输出代理节点
            input_proxy, output_proxy, execute_nodes = backdrop.get_nodes()
            if input_proxy is None or output_proxy is None:
                raise ValueError(f"循环体 {backdrop.name()} 缺少输入/输出代理节点")

            # 3. 拓扑排序内部节点
            if execute_nodes is None:
                raise ValueError(f"循环体 {backdrop.name()} 内部存在依赖环")
            # 注册全局变量
            self.register_global_variable(execute_nodes)

            backdrop.model.set_property("current_index", 0)
            self.property_changed.emit(backdrop.id)
            # 4. 循环执行逻辑
            if backdrop.TYPE == "iterate":
                results = []
                for index, data in enumerate(input_data):
                    input_proxy.set_output_value(data)
                    # 执行内部节点（同步）
                    for node in execute_nodes:
                        comp_cls = self.component_map.get(node.FULL_PATH)
                        if check_cancel():
                            return
                        self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING)
                        self.property_changed.emit(backdrop.id)
                        try:
                            node.execute_sync(
                                comp_cls, python_executable=self.get_python_exe(), check_cancel=check_cancel
                            )
                            self.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
                        except Exception as e:
                            self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
                            self.property_changed.emit(backdrop.id)
                            raise e
                    # 收集输出
                    inputs = []
                    for input_port in output_proxy.input_ports():
                        connected = input_port.connected_ports()

                        if connected:
                            if len(connected) == 1:
                                upstream = connected[0]
                                value = upstream.node()._output_values.get(upstream.name())
                                inputs.append(value)
                            else:
                                inputs.extend(
                                    [upstream.node()._output_values.get(upstream.name()) for upstream in connected]
                                )
                    backdrop.model.set_property("current_index", index+1)
                    self.property_changed.emit(backdrop.id)
                    results.extend(inputs)
            # 5. 迭代执行逻辑
            elif backdrop.TYPE == "loop":
                results = None
                for index in range(backdrop.model.get_property("loop_nums")):   # 暂时只支持迭代指定次数
                    input_proxy.set_output_value(input_data)
                    # 执行内部节点（同步）
                    for node in execute_nodes:
                        comp_cls = self.component_map.get(node.FULL_PATH)
                        if check_cancel():
                            return
                        self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING)
                        self.property_changed.emit(backdrop.id)
                        try:
                            node.execute_sync(
                                comp_cls, python_executable=self.get_python_exe(), check_cancel=check_cancel
                            )
                            self.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
                            self.property_changed.emit(backdrop.id)
                        except Exception as e:
                            self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
                            raise e
                    # 收集输出
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
                    input_data = outputs
                    backdrop.model.set_property("current_index", index+1)
                    self.property_changed.emit(backdrop.id)

                results = outputs
            # 6. 设置 Backdrop 的输出
            backdrop.set_output_value(results)
            self.set_node_status(backdrop, NodeStatus.NODE_STATUS_SUCCESS)
        except:
            import traceback
            logger.error(traceback.format_exc())

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