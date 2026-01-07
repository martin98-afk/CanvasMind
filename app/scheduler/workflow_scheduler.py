# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Optional, Callable

from NodeGraphQt import BackdropNode
from PyQt5.QtCore import QObject, pyqtSignal, QThreadPool
from loguru import logger

from app.components.base import GlobalVariableContext
from app.nodes.status_node import NodeStatus
from app.scheduler.node_list_executor import NodeListExecutor
from app.server_manager.ipython_server.ipython_kernel_manager import IPythonKernelManager
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
            get_node_status: Callable,
            get_python_exe: Callable[[], Optional[str]],
            kernel_manager: IPythonKernelManager,
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
        self.kernel_manager = kernel_manager
        self._executor = None

    def set_node_status(self, node, status):
        self.node_status_changed.emit(node.id, status)

    def update_node_variable(self, name, value, policy):
        node_var_obj = self.parent.global_variables.node_vars.get(name)
        if policy == "更新":
            node_var_obj.value = value
        elif policy == "追加":
            current_value = node_var_obj.value
            # 尝试进行追加操作
            try:
                # --- 处理字符串 ---
                if isinstance(current_value, list):
                    if isinstance(value, list):
                        node_var_obj.value = current_value + value
                    else:
                        # 如果当前是列表，但新值不是列表，将新值作为一个元素追加
                        node_var_obj.value = current_value + [value]
                # --- 处理字典 ---
                elif isinstance(current_value, dict):
                    if isinstance(value, dict):
                        # 合并字典，新值会覆盖同名键的旧值
                        node_var_obj.value = {**current_value, **value}
                    else:
                        logger.warning(f"无法将非字典值 {value} (type: {type(value)}) 追加到字典变量 '{name}'。")
                # --- 其他类型 ---
                else:
                    # 对于其他类型，尝试直接相加，如果失败则覆盖
                    node_var_obj.value = [current_value, value]
            except TypeError as e:
                # 如果相加操作不支持（例如 list + int），则记录警告并覆盖
                logger.warning(f"追加变量 '{name}' 失败: {e}. 将覆盖旧值。")
                node_var_obj.value = value
            except Exception as e:
                # 捕获其他任何可能的异常，记录警告并覆盖
                logger.error(f"追加变量 '{name}' 时发生未知错误: {e}. 将覆盖旧值。")
                node_var_obj.value = value
        self.node_vars_changed.emit()

    def get_executable_nodes(self, nodes=[]):
        """获取所有顶层可执行节点（排除循环内部节点）"""
        all_nodes = self.graph.all_nodes() if len(nodes) == 0 else nodes

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
                scheduler=self
            )
            self._executor.signals.log_start.connect(self.parent.log_window.start_run)
            self._executor.signals.log_message.connect(self.parent.log_window.push_log)
            self._executor.signals.log_error.connect(self.parent.log_window.on_error)
            self._executor.signals.log_finished.connect(self.parent.log_window.on_finished)
            self._executor.component_map = self.component_map
            self._executor.signals.backdrop_finished.connect(self.backdrop_finished)
            self._executor.signals.finished.connect(self._on_finished)
            self._executor.signals.error.connect(lambda message: self._on_error(message, nodes))

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
        if self._executor and hasattr(self._executor, 'ctx'):
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