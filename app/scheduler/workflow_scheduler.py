# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Optional, Callable

from NodeGraphQt import BackdropNode
from PyQt5.QtCore import QObject, pyqtSignal, QThreadPool
from loguru import logger

from app.nodes.base.status_node import NodeStatus
from app.scheduler.node_list_executor import NodeListExecutor
from app.utils.utils import get_port_node, topological_sort


class WorkflowScheduler(QObject):
    """
    工作流调度器：支持条件分支控制流（通过 disabled 状态）
    - 执行前自动解锁所有节点
    - 条件分支节点可动态禁用下游
    - 调度器自动跳过 disabled 节点及其下游
    """

    finished = pyqtSignal()
    error = pyqtSignal(str)
    cancelled = pyqtSignal()
    backdrop_finished = pyqtSignal()
    node_status_changed = pyqtSignal(str, str)  # node_id, status
    property_changed = pyqtSignal(object)
    node_vars_changed = pyqtSignal()

    def __init__(
        self,
        graph,
        component_map: Dict[str, Any],
        get_python_exe: Callable[[], Optional[str]],
        parent=None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.graph = graph
        self.component_map = component_map
        self.get_python_exe = get_python_exe
        self._executor = None

    @property
    def global_variables(self):
        return self.parent.global_variables

    @property
    def kernel_manager(self):
        return self.parent.ipython_kernel.kernel_manager

    def set_node_status(self, node, status):
        self.node_status_changed.emit(node.id, status)

    def update_node_variable(self, name, value, policy):
        """静默更新，不发送信号

        收集(Collect)：始终转为列表追加，每次更新作为独立元素
            首次收集：value → [value]
            后续收集：[a, b] + c → [a, b, c]
        合并(Merge)：同类型数据合并
            列表 + 列表：extend
            字符串 + 字符串：拼接
            数值 + 数值：相加
            字典 + 字典：merge
        """
        node_var_obj = self.parent.global_variables.node_vars.get(name)
        if not node_var_obj:
            return

        if policy == "更新":
            node_var_obj.value = value
        elif policy == "收集":
            curr = node_var_obj.value
            if isinstance(curr, list):
                curr.append(value)
            elif curr is None:
                node_var_obj.value = [value]
            else:
                node_var_obj.value = [curr, value]
        elif policy == "合并":
            curr = node_var_obj.value
            if isinstance(curr, list) and isinstance(value, list):
                curr.extend(value)
            elif isinstance(curr, str) and isinstance(value, str):
                node_var_obj.value = curr + value
            elif isinstance(curr, (int, float)) and isinstance(value, (int, float)):
                node_var_obj.value = curr + value
            elif isinstance(curr, dict) and isinstance(value, dict):
                curr.update(value)
            else:
                node_var_obj.value = value

    def get_executable_nodes(self, nodes=[]):
        """获取所有顶层可执行节点（排除循环内部节点）"""
        all_nodes = self.graph.all_nodes() if len(nodes) == 0 else nodes

        # 找出顶层循环 Backdrop
        loop_backdrops = [n for n in all_nodes if isinstance(n, BackdropNode)]

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

    def run_full(self, nodes=[], sort=True):
        """执行整个工作流（排除 Backdrop）"""
        if sort:
            nodes = self.get_executable_nodes(nodes)
            nodes = topological_sort(nodes)
            if nodes is None:
                self.error.emit("检测到循环依赖，无法执行")
                return
        self._execute_nodes(nodes)

    def run(self, node):
        """强制执行单个节点（即使 disabled）"""
        self._execute_nodes([node])

    def run_subgraph(self, node):
        """
        运行节点所在的整个连通子图
        1. 找到所有逻辑上连通的节点（不分上下游）
        2. 若连通节点在 Backdrop 中，则包含整个 Backdrop 及其内部节点
        3. 过滤出顶层可执行节点并排序执行
        """
        # 1. 获取所有连通的“原始”节点集合
        all_connected = self._get_connected_nodes(node)

        # 2. 转换为执行器需要的顶层节点列表（排除 Backdrop 内部节点，保留 Backdrop 自身）
        # 这里直接复用你已有的 get_executable_nodes
        executable_nodes = self.get_executable_nodes(list(all_connected))

        # 3. 拓扑排序
        execution_order = topological_sort(executable_nodes)
        if execution_order is None:
            self.error.emit("该子图检测到循环依赖，无法执行")
            return

        logger.info(f"执行连通子图: 找到 {len(execution_order)} 个顶层执行单元")
        self._execute_nodes(execution_order)

    def run_to(self, target_node):
        """执行到目标节点（含所有上游）"""
        nodes = self._get_ancestors_and_self(target_node)
        execution_order = topological_sort(nodes)
        if execution_order is None:
            self.error.emit("检测到循环依赖，无法执行")
            return
        self._execute_nodes(execution_order)

    def run_from(self, start_node):
        """从起始节点开始执行（含所有下游）"""
        nodes = self._get_descendants_and_self(start_node)
        execution_order = topological_sort(nodes)
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

    def _get_connected_nodes(self, start_node):
        """使用无向遍历查找所有连通节点，并处理 Backdrop 包含关系"""
        all_nodes = self.graph.all_nodes()

        # 预计算：节点 -> 所属 Backdrop 的映射
        node_to_backdrop = {}
        backdrops = [n for n in all_nodes if isinstance(n, BackdropNode)]
        for b in backdrops:
            for internal_node in b.nodes():
                node_to_backdrop[internal_node] = b

        visited = set()
        stack = [start_node]

        while stack:
            curr = stack.pop()
            if curr in visited:
                continue
            visited.add(curr)

            # --- 扩展逻辑 A: 处理 Backdrop 关联 ---
            # 情况1: 如果当前节点在某个 Backdrop 里，把 Backdrop 及其内部所有节点都标记为连通
            if curr in node_to_backdrop:
                b = node_to_backdrop[curr]
                if b not in visited:
                    stack.append(b)
                for internal in b.nodes():
                    if internal not in visited:
                        stack.append(internal)

            # # 情况2: 如果当前节点本身就是 Backdrop，把内部所有节点加进来
            # if isinstance(curr, BackdropNode):
            #     for internal in curr.nodes():
            #         if internal not in visited:
            #             stack.append(internal)

            # --- 扩展逻辑 B: 处理 端口 物理连接 (无向) ---
            # 检查所有输入端口（找上游）
            for port in curr.input_ports():
                for conn_port in port.connected_ports():
                    neighbor = get_port_node(conn_port)
                    if neighbor and neighbor not in visited:
                        stack.append(neighbor)

            # 检查所有输出端口（找下游）
            for port in curr.output_ports():
                for conn_port in port.connected_ports():
                    neighbor = get_port_node(conn_port)
                    if neighbor and neighbor not in visited:
                        stack.append(neighbor)

        return visited

    def _execute_nodes(self, nodes: List):
        """启动执行：先解锁所有节点，再执行 active 节点"""
        try:
            for node in nodes:
                node.set_disabled(False)
                self.set_node_status(node, NodeStatus.NODE_STATUS_PENDING)
                if isinstance(node, BackdropNode):
                    for n in node.nodes():
                        n.set_disabled(False)
                        self.set_node_status(n, NodeStatus.NODE_STATUS_PENDING)

            if nodes is None:
                self.error.emit("检测到循环依赖")
                return
            # 启动执行器
            self._executor = NodeListExecutor(
                main_window=self.parent,
                nodes=nodes,  # 传入拓扑序
                python_exe=self.get_python_exe(),
                kernel_manager=self.kernel_manager,
                scheduler=self,
            )
            self._executor.signals.log_start.connect(self.parent.log_window.start_run)
            self._executor.signals.log_message.connect(self.parent.log_window.push_log)
            self._executor.signals.log_error.connect(self.parent.log_window.on_error)
            self._executor.signals.log_finished.connect(
                self.parent.log_window.on_finished
            )
            self._executor.component_map = self.component_map
            self._executor.signals.backdrop_finished.connect(self.backdrop_finished)
            self._executor.signals.finished.connect(self._on_finished)
            self._executor.signals.error.connect(
                lambda message: self._on_error(message, nodes)
            )

            QThreadPool.globalInstance().start(self._executor)

        except Exception as e:
            import traceback

            logger.error(traceback.format_exc())
            self.error.emit(f"启动执行器失败: {str(e)}")

    def cancel(self):
        """取消当前执行"""
        if self._executor:
            self._executor.cancel()
            self.cancelled.emit()

    def pause(self):
        """暂停当前执行（可恢复）"""
        if self._executor:
            self._executor.pause()

    def resume(self):
        """继续当前执行（从暂停处恢复）"""
        if self._executor:
            self._executor.resume()

    def is_paused(self) -> bool:
        if self._executor and hasattr(self._executor, "ctx"):
            return self._executor.ctx.is_paused()
        return False

    def _on_finished(self, _=None):
        self.finished.emit()

    def _on_error(self, msg: str, nodes: list):
        self.error.emit(msg or "执行过程中发生未知错误")
        # 节点报错把后续节点置为未运行
        for node in nodes:
            if getattr(node, "status", None) == NodeStatus.NODE_STATUS_PENDING:
                self.set_node_status(node, NodeStatus.NODE_STATUS_UNRUN)
