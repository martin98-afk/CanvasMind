# backdrop_executor.py
import datetime
import re
import traceback

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
        if not isinstance(input_data, (list, tuple)):
            input_data = [input_data]

        results = []
        for idx, item in enumerate(input_data):
            if self.ctx.is_cancelled():
                break
            self.ctx.wait_if_paused()  # ← 关键：支持暂停
            if self.ctx.is_cancelled():
                break
            input_proxy.set_output_value(item)
            internal_results = self._execute_subgraph(execute_nodes, f"iter_{idx}")
            output = self._collect_output(output_proxy)
            results.append(output)
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
        """执行 backdrop 内部节点，使用 execute_node，不创建 NodeListExecutor"""
        results_map = {}
        for node in nodes:
            self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_PENDING)

        for node in nodes:
            if self.ctx.is_cancelled():
                break
            self.ctx.wait_if_paused()  # ← 关键：支持暂停
            if self.ctx.is_cancelled():
                break
            if node.get_property("disabled"):
                continue
            self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING)
            self.scheduler.property_changed.emit(self.backdrop)
            try:
                # 使用统一 execute_node
                execute_node(
                    node=node,
                    component_map=self.component_map,
                    python_exe=self.python_exe,
                    kernel_manager=self.kernel_manager,
                    scheduler=self.scheduler,
                    global_variable=self.global_variables,
                    execution_context=self.ctx,
                    log_start_func=self.log_start.emit,
                    log_message_func=self.log_message.emit,
                    log_error_func=self.log_error.emit,
                    log_finish_func=self.log_finished.emit,
                    run_id_postfix=f"{self.backdrop.name()}:{iteration_tag}"
                )
                self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
                self.scheduler.property_changed.emit(self.backdrop)
                # 收集输出用于条件判断
                if hasattr(node, '_output_values'):
                    node_name = re.sub(r'\s+', '_', node.name())
                    for port, val in node._output_values.items():
                        results_map[f"node_vars_{node_name}__{port}"] = val

            except Exception as e:
                self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
                self.scheduler.property_changed.emit(self.backdrop)
                raise  # 向上抛出，终止 backdrop

        return results_map

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