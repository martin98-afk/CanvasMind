import traceback
from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger

from app.nodes.status_node import NodeStatus
from app.scheduler.single_node_executor import execute_node
from app.utils.utils import get_port_node
from NodeGraphQt.nodes.port_node import PortInputNode, PortOutputNode


class GroupNodeExecutor(QObject):
    """
    专门用于执行 GroupNode（组节点）的执行器。
    核心逻辑：
    1. 提取组节点外部输入 -> 注入内部 PortInputNode
    2. 拓扑执行内部所有子节点
    3. 提取内部 PortOutputNode 数据 -> 写回组节点外部输出
    """
    finished = pyqtSignal(object, object)
    error = pyqtSignal(str)
    log_start = pyqtSignal(str)
    log_message = pyqtSignal(str, str)
    log_error = pyqtSignal(str)
    log_finished = pyqtSignal(str)

    def __init__(
            self,
            group_node,
            scheduler,
            python_exe,
            kernel_manager,
            global_variables,
            execution_context,
            parent=None
    ):
        super().__init__(parent)
        self.group_node = group_node
        self.scheduler = scheduler
        self.python_exe = python_exe
        self.kernel_manager = kernel_manager
        self.global_variables = global_variables
        self.ctx = execution_context

    def execute(self):
        """主执行逻辑"""
        try:
            self.scheduler.set_node_status(self.group_node, NodeStatus.NODE_STATUS_RUNNING)

            # 1. 获取子图内部的所有节点实例
            # 注意：这里假设你的 GroupNode 类有一个方法能获取内部所有节点实例
            # 如果是实时执行，通常需要从 group_node.get_sub_graph() 获取，
            # 如果是静默执行，可能需要根据 session 数据临时创建实例
            internal_nodes = self._get_internal_node_instances()
            
            if not internal_nodes:
                logger.warning(f"组节点 {self.group_node.name()} 内部没有节点")
                self.scheduler.set_node_status(self.group_node, NodeStatus.NODE_STATUS_SUCCESS)
                return

            # 2. 【难点 1】同步输入：组节点外部 -> 内部 PortInputNode
            self._sync_external_to_internal(internal_nodes)

            # 3. 执行内部子图（拓扑排序执行）
            self._execute_internal_subgraph(internal_nodes)

            # 4. 【难点 2】同步输出：内部 PortOutputNode -> 组节点外部
            self._sync_internal_to_external(internal_nodes)

            self.scheduler.set_node_status(self.group_node, NodeStatus.NODE_STATUS_SUCCESS)

        except Exception as e:
            logger.error(f"GroupNode {self.group_node.name()} 执行失败: {e}")
            logger.error(traceback.format_exc())
            self.scheduler.set_node_status(self.group_node, NodeStatus.NODE_STATUS_FAILED)
            self.error.emit(str(e))
            raise

    def _get_internal_node_instances(self):
        """
        获取组节点内的所有节点实例。
        如果组节点是展开状态，可以从 sub_graph 中直接获取。
        """
        sub_graph = self.group_node.get_sub_graph()
        if sub_graph:
            return sub_graph.all_nodes()
        
        # 如果组节点未展开，通常需要 scheduler 协助通过 session 数据在内存中实例化
        # 这里简化处理，假设 scheduler 已经处理好或提供相应接口
        return getattr(self.group_node, "_internal_nodes", [])

    def _sync_external_to_internal(self, internal_nodes):
        """
        将组节点（外部）接收到的数据传递给内部的 PortInputNode。
        """
        # A. 收集组节点外部输入端口的数据
        external_input_data = {}
        for port in self.group_node.input_ports():
            val = None
            for out_port in port.connected_ports():
                upstream = get_port_node(out_port)
                if upstream and hasattr(upstream, '_output_values'):
                    val = upstream._output_values.get(out_port.name())
                    break 
            external_input_data[port.name()] = val

        # B. 寻找内部 PortInputNode 并赋值
        for node in internal_nodes:
            if isinstance(node, PortInputNode):
                # 匹配逻辑：内部 PortInputNode 的名字通常等于组节点输入端口的名字
                port_name = node.name()
                if port_name in external_input_data:
                    data = external_input_data[port_name]
                    # PortInputNode 在子图内部扮演“源头”角色，设置其输出值
                    # 根据你的 SubGraph 源码，输出端口名通常也是 port_name
                    node.set_output_value(data)
                    logger.debug(f"同步输入: 组端口[{port_name}] -> 内部节点[{node.name()}] 数据: {data}")

    def _sync_internal_to_external(self, internal_nodes):
        """
        将内部 PortOutputNode 的执行结果提取出来，存入组节点的输出缓存。
        """
        results = {}
        for node in internal_nodes:
            if isinstance(node, PortOutputNode):
                port_name = node.name()
                # 提取该节点输入端口收到的数据
                # PortOutputNode 只有一个输入端口，名字也叫 port_name
                val = self._get_node_input_value(node, port_name)
                results[port_name] = val
                logger.debug(f"同步输出: 内部节点[{node.name()}] -> 组端口[{port_name}] 数据: {val}")
                self.group_node.set_output_value(port_name, val)

    def _get_node_input_value(self, node, port_name):
        """从节点指定输入端口获取其上游传递来的值"""
        port = node.get_input(port_name)
        if not port: return None
        for cp in port.connected_ports():
            upstream = cp.node()
            if hasattr(upstream, '_output_values'):
                return upstream._output_values.get(cp.name())
        return None

    def _execute_internal_subgraph(self, nodes):
        """
        执行子图内部节点。
        此处可以使用简单的拓扑遍历，或者复用 BackdropExecutor 中的并行执行逻辑。
        """
        # 排除掉 PortInputNode 和 PortOutputNode，或者让 execute_node 处理它们（通常它们是空操作）
        # 1. 过滤掉禁用的节点
        executable_nodes = [n for n in nodes if not n.get_property("disabled")]
        
        # 2. 拓扑排序或按序执行
        # 简单起见，这里采用拓扑执行逻辑
        for node in nodes:
            if self.ctx.is_cancelled(): break
            self.ctx.wait_if_paused()

            # PortInputNode 不需要执行（数据已由 _sync_external_to_internal 注入）
            if isinstance(node, PortInputNode):
                self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
                continue
            
            # PortOutputNode 只需要确保状态，数据同步在最后一步
            if isinstance(node, PortOutputNode):
                self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
                continue

            # 执行具体业务节点
            self._run_single_subnode(node)

    def _run_single_subnode(self, node):
        """包装单个子节点的执行"""
        try:
            execute_node(
                node=node, 
                python_exe=self.python_exe,
                kernel_manager=self.kernel_manager, 
                scheduler=self.scheduler,
                global_variable=self.global_variables, 
                execution_context=self.ctx,
                log_start_func=self.log_start.emit, 
                log_message_func=self.log_message.emit,
                log_error_func=self.log_error.emit, 
                log_finish_func=self.log_finished.emit,
                run_id_postfix=f"Group:{self.group_node.name()}",
                semaphore=self.scheduler.execution_semaphore,
                callback_func=lambda: self.scheduler.property_changed.emit(self.group_node)
            )
        except Exception as e:
            logger.error(f"子节点 {node.name()} 执行失败: {e}")
            raise e