# -*- coding: utf-8 -*-
import time
import traceback
import concurrent.futures
from threading import Lock, BoundedSemaphore
from typing import List, Optional, Any

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, QTimer
from loguru import logger

from app.nodes.backdrop_node import ControlFlowBackdrop
from app.scan_components import ComponentScanner
from app.scheduler.backdrop_executor import BackdropExecutor
from app.scheduler.execution_context import ExecutionContext
from app.scheduler.single_node_executor import execute_node


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)
    backdrop_finished = pyqtSignal()
    log_start = pyqtSignal(str)
    log_message = pyqtSignal(str, str)
    log_error = pyqtSignal(str)
    log_finished = pyqtSignal(str)


class NodeListExecutor(QRunnable):
    def __init__(self, main_window, nodes: List, python_exe: Optional[str] = None,
                 kernel_manager: Optional[Any] = None, scheduler: Optional[Any] = None):
        super().__init__()
        self.signals = WorkerSignals()
        self.main_window = main_window
        self.nodes = nodes
        self.python_exe = python_exe
        self.scheduler = scheduler
        self.kernel_manager = kernel_manager
        self.ctx = ExecutionContext()

        # 并行配置
        self.run_parallel = self.main_window.config.run_parallel.value
        self.max_workers = self.main_window.config.run_parallel_max_workers.value
        # 全局资源：信号量限流。如果 scheduler 没有，则创建一个。
        if not hasattr(self.scheduler, "execution_semaphore"):
            self.scheduler.execution_semaphore = BoundedSemaphore(self.max_workers)

        self._error_occurred = False

    def cancel(self):
        self.ctx.cancel()

    def pause(self):
        self.ctx.pause()

    def resume(self):
        self.ctx.resume()

    def run(self):
        component_map, _ = ComponentScanner().get_components()
        try:
            if self.run_parallel:
                self._run_graph_parallel(self.nodes, component_map)
            else:
                self._run_sequential(self.nodes, component_map)

            if not self.ctx.is_cancelled() and not self._error_occurred:
                time.sleep(0.3)
                self.signals.finished.emit("画布执行完毕")
        except Exception as e:
            if not self.ctx.is_cancelled():
                logger.error(traceback.format_exc())
                self.signals.error.emit(str(e))
        finally:
            QTimer.singleShot(100, lambda: self.scheduler.unregister_global_variable(self.nodes))

    def _run_sequential(self, nodes, component_map):
        for node in nodes:
            if self.ctx.is_cancelled() or self._error_occurred: break
            self.ctx.wait_if_paused()
            if node.get_property("disabled"): continue
            self._execute_node_logic(node, component_map)

    def _run_graph_parallel(self, nodes, component_map):
        """通用的拓扑并行执行逻辑"""
        node_map = {n.id: n for n in nodes}
        in_degree = {n.id: 0 for n in nodes}
        children = {n.id: [] for n in nodes}

        # 1. 建图
        for node in nodes:
            if not hasattr(node, "input_ports"): continue
            for ip in node.input_ports():
                for cp in ip.connected_ports():
                    upstream = cp.node()
                    if upstream.id in node_map:
                        children[upstream.id].append(node.id)
                        in_degree[node.id] += 1

        # 2. 线程池执行 (无限线程池，但实际运行受信号量控制)
        lock = Lock()
        active_futures = set()
        ready_queue = [n for n in nodes if in_degree[n.id] == 0]

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            def submit(n):
                if self.ctx.is_cancelled() or self._error_occurred: return
                f = executor.submit(self._task_wrapper, n, component_map)
                active_futures.add(f)

            for n in ready_queue: submit(n)

            while True:
                with lock:
                    if not active_futures: break
                    fs = list(active_futures)

                done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.FIRST_COMPLETED)
                for f in done:
                    with lock:
                        active_futures.remove(f)
                    finished_node = f.result()
                    if self._error_occurred or self.ctx.is_cancelled(): continue
                    with lock:
                        for cid in children.get(finished_node.id, []):
                            in_degree[cid] -= 1
                            if in_degree[cid] == 0: submit(node_map[cid])

    def _task_wrapper(self, node, component_map):
        try:
            if not node.get_property("disabled"):
                self._execute_node_logic(node, component_map)
            return node
        except Exception as e:
            self._error_occurred = True
            raise e

    def _execute_node_logic(self, node, component_map):
        """执行单个节点逻辑（含 Backdrop 递归）"""
        if self.ctx.is_cancelled(): return
        self.ctx.wait_if_paused()

        if isinstance(node, ControlFlowBackdrop):
            # 循环节点：内部也支持并行
            be = BackdropExecutor(
                backdrop=node, scheduler=self.scheduler,
                component_map=component_map, python_exe=self.python_exe,
                kernel_manager=self.kernel_manager, global_variables=self.scheduler.global_variables,
                execution_context=self.ctx,
                run_parallel=self.run_parallel  # 传递并行标志
            )
            be.log_start.connect(self.signals.log_start)
            be.log_message.connect(self.signals.log_message)
            be.log_error.connect(self.signals.log_error)
            be.log_finished.connect(self.signals.log_finished)
            be.execute()
            self.signals.backdrop_finished.emit()
        else:
            execute_node(
                node=node, python_exe=self.python_exe,
                kernel_manager=self.kernel_manager, scheduler=self.scheduler,
                global_variable=self.scheduler.global_variables, execution_context=self.ctx,
                log_start_func=self.signals.log_start.emit, log_message_func=self.signals.log_message.emit,
                log_error_func=self.signals.log_error.emit, log_finish_func=self.signals.log_finished.emit,
                semaphore=self.scheduler.execution_semaphore  # 传递信号量
            )