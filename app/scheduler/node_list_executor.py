# -*- coding: utf-8 -*-
import time
import traceback
from typing import List, Optional, Any

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, QTimer
from loguru import logger

from app.nodes.backdrop_node import ControlFlowBackdrop
from app.nodes.status_node import NodeStatus
from app.scheduler.backdrop_executor import BackdropExecutor
from app.scheduler.execute_single_node import execute_node


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)
    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str)
    node_error = pyqtSignal(str)
    backdrop_finished = pyqtSignal()
    log_start = pyqtSignal(str)  # run_id
    log_message = pyqtSignal(str, str)  # run_id, line
    log_error = pyqtSignal(str)
    log_finished = pyqtSignal(str)

class NodeListExecutor(QRunnable):
    """
    异步执行节点列表的执行器
    支持条件分支控制流：执行时跳过 disabled 节点
    """

    def __init__(
        self,
        main_window,
        nodes: List,
        python_exe: Optional[str] = None,
        kernel_manager: Optional[Any] = None,
        scheduler: Optional[Any] = None,
    ):
        super().__init__()
        self.signals = WorkerSignals()
        self.main_window = main_window
        self.nodes = nodes
        self.python_exe = python_exe
        self._is_cancelled = False
        self.component_map = {}
        self.scheduler = scheduler
        self.kernel_manager = kernel_manager

    def cancel(self):
        self._is_cancelled = True

    def _check_cancel(self) -> bool:
        return self._is_cancelled

    def run(self):
        """在工作线程中执行节点列表，动态跳过 disabled 节点"""
        try:
            for node in self.nodes:
                if self._is_cancelled:
                    logger.info("执行被用户取消")
                    return

                # ✅ 关键：检查节点是否被禁用
                if node.get_property("disabled"):
                    continue

                # 执行正常节点
                self.signals.node_started.emit(node.id)

                try:
                    if getattr(node, "execute_sync", None) is not None:
                        execute_node(
                            node=node,
                            component_map=self.component_map,
                            python_exe=self.python_exe,
                            kernel_manager=self.kernel_manager,
                            scheduler=self.scheduler,
                            global_variable=self.scheduler.global_variables,
                            check_cancel_func=self._check_cancel,
                            log_start_func=self.signals.log_start.emit,
                            log_message_func=self.signals.log_message.emit,
                            log_error_func=self.signals.log_error.emit,
                            log_finish_func=self.signals.log_finished.emit,
                            run_id_prefix=""  # 主流程不加前缀
                        )
                    elif isinstance(node, ControlFlowBackdrop):
                        # 创建 BackdropExecutor 并同步执行（在当前工作线程）
                        backdrop_executor = BackdropExecutor(
                            backdrop=node,
                            scheduler=self.scheduler,
                            component_map=self.component_map,
                            python_exe=self.python_exe,
                            kernel_manager=self.kernel_manager,
                            global_variables=self.scheduler.global_variables
                        )
                        # 连接日志信号
                        backdrop_executor.log_start.connect(self.signals.log_start)
                        backdrop_executor.log_message.connect(self.signals.log_message)
                        backdrop_executor.log_error.connect(self.signals.log_error)
                        backdrop_executor.log_finished.connect(self.signals.log_finished)

                        try:
                            backdrop_executor.execute()
                            self.signals.backdrop_finished.emit()
                        except Exception as e:
                            logger.error(f"Backdrop {node.name()} 执行异常: {e}")
                            self.signals.node_error.emit(node.id)
                            return
                    else:
                        pass

                    if self._is_cancelled:
                        return

                    self.signals.node_finished.emit(node.id)

                except Exception as e:
                    logger.error(f"节点 {node.name()} 执行失败: {e}")
                    logger.error(traceback.format_exc())
                    if self.scheduler:
                        self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
                    self.signals.node_error.emit(node.id)
                    return  # 出错停止（保持你原有逻辑）

            time.sleep(0.3)
            if not self._is_cancelled:
                self.signals.finished.emit("画布执行完毕")

        except Exception as e:
            if not self._is_cancelled:
                logger.error("执行器异常:")
                logger.error(traceback.format_exc())
                self.signals.error.emit(str(e))
            else:
                logger.info("执行被用户取消")
                self.signals.error.emit("执行被用户取消")
        finally:
            QTimer.singleShot(100, lambda: self.scheduler.unregister_global_variable(self.nodes))

    def push_log_message(self, run_id: str, line: str):
        """供节点调用，线程安全地推送日志"""
        self.signals.log_message.emit(run_id, line)