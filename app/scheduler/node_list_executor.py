# -*- coding: utf-8 -*-
import time
import traceback
from typing import List, Optional, Any

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal
from loguru import logger

from app.nodes.backdrop_node import ControlFlowBackdrop
from app.nodes.status_node import NodeStatus


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)
    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str)
    node_error = pyqtSignal(str)


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
                if getattr(node, 'disabled', lambda: False)():
                    # 跳过禁用节点，标记为 skipped（不影响下游）
                    if self.scheduler:
                        self.scheduler.set_node_status(node, NodeStatus.NODE_STATUS_UNRUN)
                    # 不发出 started/finished 信号（或可选发出 skipped 信号）
                    continue

                # 执行正常节点
                self.signals.node_started.emit(node.id)

                try:
                    if getattr(node, "execute_sync", None) is not None:
                        comp_cls = self.component_map.get(getattr(node, "FULL_PATH", None))
                        node.execute_sync(
                            comp_cls,
                            python_executable=self.python_exe,
                            check_cancel=self._check_cancel
                        )
                    elif isinstance(node, ControlFlowBackdrop):
                        if self.scheduler:
                            self.scheduler._execute_backdrop_sync(
                                node,
                                check_cancel=self._check_cancel
                            )
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