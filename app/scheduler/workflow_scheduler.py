# -*- coding: utf-8 -*-
import json
from collections import deque, defaultdict
from typing import List, Dict, Any, Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger
from app.nodes.status_node import NodeStatus
from app.utils.threading_utils import NodeListExecutor
from app.utils.utils import get_port_node


class WorkflowScheduler(QObject):
    """
    工作流调度器：统一处理全图执行、执行到节点、从节点开始执行等逻辑
    完全解耦 UI，仅依赖 graph、component_map 和状态回调
    """
    node_started = pyqtSignal(str)      # node_id
    node_finished = pyqtSignal(str)
    node_error = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        graph,
        component_map: Dict[str, Any],
        get_node_status: Callable,
        set_node_status: Callable,
        get_python_exe: Callable[[], Optional[str]],
        parent=None
    ):
        super().__init__(parent)
        self.graph = graph
        self.component_map = component_map
        self.get_node_status = get_node_status
        self.set_node_status = set_node_status
        self.get_python_exe = get_python_exe
        self._executor = None

    def run_full(self):
        """执行整个工作流（排除 Backdrop）"""
        all_nodes = [n for n in self.graph.all_nodes() if not hasattr(n, 'is_backdrop') or not n.is_backdrop]
        if not all_nodes:
            self.error.emit("工作流中没有可执行节点")
            return

        execution_order = self._topological_sort(all_nodes)
        if execution_order is None:
            self.error.emit("检测到循环依赖，无法执行")
            return

        self._execute_nodes(execution_order)

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
        # 下游子图也需拓扑排序（虽然通常无环，但保险起见）
        execution_order = self._topological_sort(nodes)
        if execution_order is None:
            self.error.emit("检测到循环依赖，无法执行")
            return
        self._execute_nodes(execution_order)

    def _get_ancestors_and_self(self, node):
        """获取 node 及其所有上游节点（DFS）"""
        visited = set()
        result = []

        def dfs(n):
            if n in visited:
                return
            visited.add(n)
            for input_port in n.input_ports():
                for out_port in input_port.connected_ports():
                    upstream = get_port_node(out_port)
                    dfs(upstream)
            result.append(n)

        dfs(node)
        return result

    def _get_descendants_and_self(self, node):
        """获取 node 及其所有下游节点（DFS）"""
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
                    dfs(downstream)

        dfs(node)
        return result

    def _topological_sort(self, nodes: List) -> Optional[List]:
        """对节点列表进行拓扑排序，检测循环依赖"""
        if not nodes:
            return []

        # 构建子图依赖
        in_degree = {node: 0 for node in nodes}
        graph_deps = defaultdict(list)

        node_set = set(nodes)
        for node in nodes:
            for input_port in node.input_ports():
                for upstream_out in input_port.connected_ports():
                    upstream = get_port_node(upstream_out)
                    if upstream in node_set:
                        graph_deps[upstream].append(node)
                        in_degree[node] += 1

        # Kahn 算法
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

    def _execute_nodes(self, nodes: List):
        """启动异步执行器"""
        try:
            for node in nodes:
                self.set_node_status(node, NodeStatus.NODE_STATUS_PENDING)  # 推荐
            self._executor = NodeListExecutor(
                main_window=None,  # 不再使用
                nodes=nodes,
                python_exe=self.get_python_exe()
            )

            # 注入 component_map（关键！）
            self._executor.component_map = self.component_map

            # 连接信号
            self._executor.signals.node_started.connect(self.node_started)
            self._executor.signals.node_finished.connect(self.node_finished)
            self._executor.signals.node_error.connect(self.node_error)
            self._executor.signals.finished.connect(self._on_finished)
            self._executor.signals.error.connect(self._on_error)

            from PyQt5.QtCore import QThreadPool
            QThreadPool.globalInstance().start(self._executor)

        except Exception as e:
            import traceback
            logger.error(traceback.format_exc())
            self.error.emit(f"启动执行器失败: {str(e)}")

    def cancel(self):
        """取消当前执行"""
        if self._executor:
            self._executor.cancel()

    def _on_finished(self, _=None):
        self.finished.emit()

    def _on_error(self, msg: str = ""):
        self.error.emit(msg or "执行过程中发生未知错误")