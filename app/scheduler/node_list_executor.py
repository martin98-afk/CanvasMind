# -*- coding: utf-8 -*-
import time
import traceback
from typing import List, Optional, Any

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal
from loguru import logger

from app.nodes.create_backdrop_node import ControlFlowBackdrop


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)  # 保持兼容，可发送任意对象
    # 新增信号用于批量执行
    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str)  # (node_id, result)
    node_error = pyqtSignal(str)        # (node_id, error_message)


class NodeListExecutor(QRunnable):
    """
    异步执行节点列表的执行器
    不依赖 CanvasPage，仅通过信号通信
    """

    def __init__(
        self,
        main_window,  # 保留兼容性（但 execute_sync 不再需要它）
        nodes: List,
        python_exe: Optional[str] = None,
        scheduler: Optional[Any] = None,
    ):
        super().__init__()
        self.signals = WorkerSignals()
        self.main_window = main_window  # 可用于日志等，但不用于核心逻辑
        self.nodes = nodes
        self.python_exe = python_exe
        self._is_cancelled = False
        # ✅ 关键：由调度器注入 component_map
        self.component_map = {}
        self.scheduler = scheduler

    def cancel(self):
        """请求取消执行"""
        self._is_cancelled = True

    def _check_cancel(self) -> bool:
        """检查是否被取消"""
        return self._is_cancelled

    def run(self):
        """在工作线程中执行节点列表"""
        try:
            for node in self.nodes:
                if self._is_cancelled:
                    logger.info("执行被用户取消")
                    return

                # 发出节点开始信号
                self.signals.node_started.emit(node.id)

                try:
                    if getattr(node, "execute_sync", None) is not None:
                        # 获取组件类
                        comp_cls = self.component_map.get(node.FULL_PATH)
                        if comp_cls is None:
                            raise ValueError(f"未找到组件类: {node.FULL_PATH}")
                        # 执行节点（同步）
                        node.execute_sync(
                            comp_cls,
                            python_executable=self.python_exe,
                            check_cancel=self._check_cancel
                        )
                    elif isinstance(node, ControlFlowBackdrop):
                        self.scheduler._execute_backdrop_sync(node)
                    else:
                        pass

                    if self._is_cancelled:
                        return

                    # 发出节点完成信号
                    self.signals.node_finished.emit(node.id)

                except Exception as e:
                    logger.error(f"节点 {node.name()} 执行失败: {e}")
                    logger.error(traceback.format_exc())
                    self.signals.node_error.emit(node.id)
                    # 出错后停止后续执行（符合你当前逻辑）
                    return

            # 短暂延迟确保 UI 更新
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