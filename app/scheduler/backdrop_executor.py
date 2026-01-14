# backdrop_executor.py
import concurrent
import re
import traceback
from threading import Lock

from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger

from app.nodes.status_node import NodeStatus
from app.scheduler.single_node_executor import execute_node
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.utils import get_port_node


class BackdropExecutor(QObject):
    """
    专门用于异步执行 ControlFlowBackdrop 的执行器
    支持 iterate / condition / while 等循环模式
    """
    finished = pyqtSignal(object, object)  # backdrop_id, results
    error = pyqtSignal(str)
    log_start = pyqtSignal(str)
    log_message = pyqtSignal(str, str)
    log_error = pyqtSignal(str)
    log_finished = pyqtSignal(str)

    def __init__(
            self,
            backdrop,
            scheduler,
            component_map,
            python_exe,
            kernel_manager,
            global_variables,
            execution_context,  # ← 新增
            run_parallel=False,
            parent=None
    ):
        super().__init__(parent)
        self.backdrop = backdrop
        self.scheduler = scheduler
        self.component_map = component_map
        self.python_exe = python_exe
        self.kernel_manager = kernel_manager
        self.global_variables = global_variables
        self.ctx = execution_context  # ← 共享上下文
        self.run_parallel = run_parallel

    def execute(self):
        """在工作线程中调用（由 QRunnable 包装）"""
        try:
            self.scheduler.set_node_status(self.backdrop, NodeStatus.NODE_STATUS_RUNNING)

            input_data = self._get_input_data()
            input_proxy, output_proxy, execute_nodes = self.backdrop.get_nodes()
            if not input_proxy or not output_proxy:
                raise ValueError(f"Backdrop {self.backdrop.name()} 缺少输入/输出代理节点")

            self.backdrop.model.set_property("current_index", 0)
            self.scheduler.property_changed.emit(self.backdrop)

            loop_type = self.backdrop.TYPE
            if loop_type == "iterate":
                results = self._run_iterate(input_data, input_proxy, output_proxy, execute_nodes)
            elif loop_type == "loop":
                results = self._run_condition_loop(input_data, input_proxy, output_proxy, execute_nodes)
            else:
                raise ValueError(f"不支持的 Backdrop 类型: {loop_type}")

            self.scheduler.set_node_status(self.backdrop, NodeStatus.NODE_STATUS_SUCCESS)
            self.backdrop.set_output_value(results)

        except Exception as e:
            logger.error(f"Backdrop {self.backdrop.name()} 执行失败: {e}")
            logger.error(traceback.format_exc())
            self.scheduler.set_node_status(self.backdrop, NodeStatus.NODE_STATUS_FAILED)
            self.error.emit(str(e))
            raise

    def _get_input_data(self):
        data = []
        for input_port in self.backdrop.input_ports():
            for out_port in input_port.connected_ports():
                upstream = get_port_node(out_port)
                if upstream and hasattr(upstream, '_output_values'):
                    data.append(upstream._output_values.get(out_port.name(), None))
        return data if len(data) != 1 else data[0]

    def _run_iterate(self, input_data, input_proxy, output_proxy, execute_nodes):
        # --- 新增：处理输入数据类型 ---
        iterable_items = []
        is_dict_mode = False

        if isinstance(input_data, dict):
            # 如果是字典，迭代 (key, value) 元组
            iterable_items = list(input_data.items())
            is_dict_mode = True
        elif isinstance(input_data, (list, tuple)):
            iterable_items = input_data
        else:
            # 兼容非容器类型，视作单元素列表
            iterable_items = [input_data]

        results = []
        for idx, item in enumerate(iterable_items):
            if self.ctx.is_cancelled():
                break
            self.ctx.wait_if_paused()

            if self.ctx.is_cancelled():
                break

            # --- 新增：属性增强 ---
            if is_dict_mode:
                # item 是 (key, value)
                current_key, current_val = item
                # 将 key 存入模型属性，方便 UI 监视
                self.backdrop.model.set_property("current_key", str(current_key))
                # 传递给输入代理的值可以是整个元组，或者仅是 value（取决于你的业务逻辑）
                # 这里推荐传递整个元组，或者在输入代理中增加逻辑拆分
                input_proxy.set_output_value(item)
            else:
                self.backdrop.model.set_property("current_key", None)
                input_proxy.set_output_value(item)

            # 执行子图
            self._execute_subgraph(execute_nodes, f"iter_{idx}")

            # 收集结果
            output = self._collect_output(output_proxy)
            results.append(output)

            # 更新进度
            self.backdrop.model.set_property("current_index", idx + 1)
            self.scheduler.property_changed.emit(self.backdrop)

        return results

    def _run_condition_loop(self, input_data, input_proxy, output_proxy, execute_nodes):
        loop_mode = self.backdrop.model.get_property("loop_mode")
        if loop_mode == "count":
            return self._run_count_loop(input_data, input_proxy, output_proxy, execute_nodes)
        elif loop_mode == "condition":
            return self._run_condition_based_loop(input_data, input_proxy, output_proxy, execute_nodes)
        elif loop_mode == "while":
            return self._run_while_loop(input_data, input_proxy, output_proxy, execute_nodes)
        else:
            raise ValueError(f"未知 loop_mode: {loop_mode}")

    def _run_count_loop(self, input_data, input_proxy, output_proxy, execute_nodes):
        max_iter = self.backdrop.model.get_property("loop_nums")
        current = input_data
        for idx in range(max_iter):
            if self.ctx.is_cancelled():
                break
            self.ctx.wait_if_paused()  # ← 关键：支持暂停
            if self.ctx.is_cancelled():
                break
            input_proxy.set_output_value(current)
            self._execute_subgraph(execute_nodes, f"count_{idx}")
            current = self._collect_output(output_proxy)
            self.backdrop.model.set_property("current_index", idx + 1)
            self.scheduler.property_changed.emit(self.backdrop)
        return current

    def _run_condition_based_loop(self, input_data, input_proxy, output_proxy, execute_nodes):
        max_iter = self.backdrop.model.get_property("max_iterations")
        condition = self.backdrop.model.get_property("loop_condition")
        current = input_data
        for idx in range(max_iter):
            if self.ctx.is_cancelled():
                break
            self.ctx.wait_if_paused()  # ← 关键：支持暂停
            if self.ctx.is_cancelled():
                break
            input_proxy.set_output_value(current)
            internal_outputs = self._execute_subgraph(execute_nodes, f"cond_{idx}")
            current = self._collect_output(output_proxy)
            if not self._evaluate_condition(condition, current, internal_outputs):
                break
            self.backdrop.model.set_property("current_index", idx + 1)
            self.scheduler.property_changed.emit(self.backdrop)
        return current

    def _run_while_loop(self, input_data, input_proxy, output_proxy, execute_nodes):
        max_iter = self.backdrop.model.get_property("max_iterations")
        condition = self.backdrop.model.get_property("loop_condition")
        current = input_data
        for idx in range(max_iter):
            if self.ctx.is_cancelled():
                break
            self.ctx.wait_if_paused()  # ← 关键：支持暂停
            if self.ctx.is_cancelled():
                break
            input_proxy.set_output_value(current)
            internal_outputs = self._execute_subgraph(execute_nodes, f"while_{idx}")
            if not self._evaluate_condition(condition, current, internal_outputs):
                break
            current = self._collect_output(output_proxy)
            self.backdrop.model.set_property("current_index", idx + 1)
            self.scheduler.property_changed.emit(self.backdrop)
        return current

    def _execute_subgraph(self, nodes, iteration_tag):
        """执行 Backdrop 内部子图"""
        results_map = {}
        for node in nodes:
            self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_PENDING)

        if self.run_parallel:
            # 使用拓扑排序执行子图，复用 execute_node 逻辑
            # 注意：这里需要传入信号量限流
            self._execute_subgraph_parallel(nodes, iteration_tag)
        else:
            # 原有的串行逻辑
            for node in nodes:
                if self.ctx.is_cancelled(): break
                self.ctx.wait_if_paused()
                if node.get_property("disabled"):
                    self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_DISABLED)
                    continue
                self._run_single_subnode(node, iteration_tag)

        # 收集结果用于表达式判断
        for node in nodes:
            if hasattr(node, '_output_values'):
                node_name = re.sub(r'\s+', '_', node.name())
                for port, val in node._output_values.items():
                    results_map[f"node_vars.{node_name}__{port}"] = val
        return results_map

    def _execute_subgraph_parallel(self, nodes, iteration_tag):
        """子图并行化：这里简化逻辑，直接借用逻辑或手动实现拓扑"""
        node_map = {n.id: n for n in nodes}
        in_degree = {n.id: 0 for n in nodes}
        children = {n.id: [] for n in nodes}
        for node in nodes:
            for ip in node.input_ports():
                for cp in ip.connected_ports():
                    if cp.node().id in node_map:
                        children[cp.node().id].append(node.id)
                        in_degree[node.id] += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(nodes) + 1) as executor:
            lock = Lock()
            futures = {}
            def submit(n):
                if self.ctx.is_cancelled(): return
                self.ctx.wait_if_paused()
                if node.get_property("disabled"):
                    self.scheduler.set_node_status(n, NodeStatus.NODE_STATUS_DISABLED)
                    return
                f = executor.submit(self._run_single_subnode, n, iteration_tag)
                futures[f] = n

            for n in [nd for nd in nodes if in_degree[nd.id] == 0]:
                submit(n)

            while futures:
                done, _ = concurrent.futures.wait(futures.keys(), return_when=concurrent.futures.FIRST_COMPLETED)
                for f in done:
                    node = futures.pop(f)
                    f.result() # 抛出异常
                    with lock:
                        for cid in children.get(node.id, []):
                            in_degree[cid] -= 1
                            if in_degree[cid] == 0: submit(node_map[cid])

    def _run_single_subnode(self, node, iteration_tag):
        """包装单个子节点的执行，调用 execute_node"""
        try:
            execute_node(
                node=node, python_exe=self.python_exe,
                kernel_manager=self.kernel_manager, scheduler=self.scheduler,
                global_variable=self.global_variables, execution_context=self.ctx,
                log_start_func=self.log_start.emit, log_message_func=self.log_message.emit,
                log_error_func=self.log_error.emit, log_finish_func=self.log_finished.emit,
                run_id_postfix=f"{self.backdrop.name()}:{iteration_tag}",
                semaphore=self.scheduler.execution_semaphore, # 必须传递
                callback_func=lambda: self.scheduler.property_changed.emit(self.backdrop)
            )
        except Exception as e:
            raise e

    def _collect_output(self, output_proxy):
        outputs = []
        for in_port in output_proxy.input_ports():
            for out_port in in_port.connected_ports():
                node = out_port.node()
                val = node._output_values.get(out_port.name())
                if val is None:
                    continue
                outputs.append(val)
        if len(outputs) == 0:
            return None
        return outputs[0] if len(outputs) == 1 else outputs

    def _evaluate_condition(self, expr, current_data, internal_outputs):
        engine = ExpressionEngine(self.global_variables)
        temp_vars = {
            'data': current_data,
            'result': current_data,
            'current_index': self.backdrop.model.get_property("current_index"),
            'iteration_count': self.backdrop.model.get_property("current_index") + 1,
            'max_iterations': self.backdrop.model.get_property("max_iterations"),
            'loop_mode': self.backdrop.model.get_property("loop_mode"),
        }
        if internal_outputs:
            temp_vars.update(internal_outputs)
        result = engine.evaluate_expression_block(expr, temp_vars)
        if isinstance(result, str) and result.startswith('[ExprError:'):
            return False
        return bool(result)