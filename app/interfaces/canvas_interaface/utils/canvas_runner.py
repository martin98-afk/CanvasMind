# -*- coding: utf-8 -*-
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from PyQt5.QtCore import pyqtSignal, QObject, QTimer
from loguru import logger

from app.interfaces.canvas_interaface.utils.execution_manager import ExecutionManager
from app.scheduler.workflow_scheduler import WorkflowScheduler


@dataclass
class ExecutionTask:
    """封装执行任务的实体"""
    mode: str  # 'full', 'to', 'from', 'node', 'workflow'
    target: Any  # node or list of nodes
    sort: bool = True
    task_id: str = None


class CanvasRunner(QObject):
    workflow_started = pyqtSignal()
    workflow_finished = pyqtSignal()
    workflow_error = pyqtSignal(str)
    workflow_cancelled = pyqtSignal()
    workflow_paused = pyqtSignal()
    workflow_resumed = pyqtSignal()
    node_status_changed = pyqtSignal(str, object)
    property_changed = pyqtSignal(object)
    node_vars_changed = pyqtSignal()

    # 任务队列状态信号
    queue_size_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._scheduler: Optional[WorkflowScheduler] = None
        self._task_queue = deque()
        self._is_running = False

    def _create_scheduler(self):
        """创建调度器"""
        scheduler = WorkflowScheduler(
            graph=self.parent.graph,
            component_map=self.parent.component_map,
            get_node_status=self.parent.get_node_status,
            get_python_exe=lambda: self.parent.env_data.get("path"),
            kernel_manager=self.parent.ipython_kernel.kernel_manager,
            global_variables=self.parent.global_variables,
            parent=self.parent,
        )
        scheduler.node_status_changed.connect(self.node_status_changed.emit)
        scheduler.property_changed.connect(self.property_changed.emit)
        return scheduler

    # --- 兼容旧代码的 UI 调用接口 ---

    def run_workflow(self):
        """执行所有选中节点的工作流（兼容主界面运行按钮）"""
        # 获取属性面板当前的执行顺序
        nodes = self.parent.property_panel.get_current_execution_order()
        if nodes:
            # 如果有特定顺序，传入节点列表且不自动排序
            self._enqueue(ExecutionTask('workflow', nodes, sort=False))
        else:
            # 否则运行当前选中的节点
            selected_nodes = self.parent.graph.selected_nodes()
            self._enqueue(ExecutionTask('full', selected_nodes, sort=True))

    def run_full(self, nodes=None, sort=True):
        self._enqueue(ExecutionTask('full', nodes, sort=sort))

    def run_to(self, target_node, task_id=None):
        self._enqueue(ExecutionTask('to', target_node, task_id=task_id))

    def run_from(self, start_node, task_id=None):
        """由 TriggerNode 触发器调用"""
        self._enqueue(ExecutionTask('from', start_node, task_id=task_id))

    def run_node(self, node):
        self._enqueue(ExecutionTask('node', node))

    # --- 队列核心逻辑 ---

    def _enqueue(self, task: ExecutionTask):
        """任务入队并尝试启动"""
        self._task_queue.append(task)
        self.queue_size_changed.emit(len(self._task_queue))
        logger.info(f"[Runner] 任务入队: {task.mode}. 当前队列长度: {len(self._task_queue)}")

        if not self._is_running:
            self._process_next_task()

    def _process_next_task(self):
        """处理队列中的下一个任务"""
        if not self._task_queue:
            self._is_running = False
            logger.info("[Runner] 所有任务执行完毕。")
            return

        self._is_running = True
        task = self._task_queue.popleft()
        self.queue_size_changed.emit(len(self._task_queue))

        # 创建调度器
        self._scheduler = self._create_scheduler()
        self._connect_signals(self._scheduler, task)
        # 启动执行
        try:
            if task.mode in ['full', 'workflow']:
                nodes = task.target or self.parent.graph.selected_nodes()
                self._scheduler.run_full(nodes=nodes, sort=task.sort)
            elif task.mode == 'to':
                self._scheduler.run_to(task.target)
            elif task.mode == 'from':
                self._scheduler.run_from(task.target)
            elif task.mode == 'node':
                self._scheduler.run(task.target)
        except Exception as e:
            logger.exception(f"[Runner] 启动任务失败: {e}")
            self._on_task_finished()

    def _connect_signals(self, scheduler, task):
        """连接信号，并保留 UI 更新逻辑"""
        self.workflow_started.emit()

        # 任务结束后的队列回环
        # --- 1. 创建执行记录 ---
        em = ExecutionManager()
        exec_id = em.create_record(
            exec_id=task.task_id,
            canvas_name=self.parent.workflow_name,
            trigger_type=task.mode
        )

        # --- 2. 增强信号处理 ---
        def on_finished():
            em.update_record(exec_id, "success", output_data={})
            self._on_task_finished()

        def on_error(msg):
            em.update_record(exec_id, "failed", error_msg=msg)
            self._on_task_error(msg)

        scheduler.finished.connect(on_finished)
        scheduler.error.connect(on_error)
        scheduler.cancelled.connect(self._on_task_finished)

        scheduler.node_vars_changed.connect(self.node_vars_changed.emit)

        def update_ui():
            QTimer.singleShot(50, self.parent.property_panel.update_node_list_content)

        if task.mode == 'workflow':
            scheduler.finished.connect(update_ui)
            scheduler.error.connect(update_ui)
            scheduler.cancelled.connect(update_ui)
            scheduler.node_status_changed.connect(update_ui)

        # 如果调度器支持 backdrop_finished 信号
        if hasattr(scheduler, 'backdrop_finished'):
            scheduler.backdrop_finished.connect(
                lambda: QTimer.singleShot(50, lambda: self.parent.property_panel.update_properties(task.target))
            )

    def _on_task_finished(self):
        logger.info("[Runner] 当前任务结束。")
        self.workflow_finished.emit()
        QTimer.singleShot(100, self._process_next_task)

    def _on_task_error(self, error_msg):
        logger.error(f"[Runner] 任务执行出错: {error_msg}")
        self.workflow_error.emit(error_msg)
        QTimer.singleShot(100, self._process_next_task)

    # --- 控制逻辑 ---

    def stop_workflow(self):
        self._task_queue.clear()
        self.queue_size_changed.emit(0)
        if self._scheduler:
            self._scheduler.cancel()
            self._scheduler = None
        self._is_running = False
        self.workflow_cancelled.emit()

    def pause_workflow(self):
        if self._scheduler and hasattr(self._scheduler, '_executor'):
            self._scheduler._executor.pause()
            self.workflow_paused.emit()

    def resume_workflow(self):
        if self._scheduler and hasattr(self._scheduler, '_executor'):
            self._scheduler._executor.resume()
            self.workflow_resumed.emit()

    def is_paused(self) -> bool:
        if self._scheduler and hasattr(self._scheduler, '_executor'):
            return self._scheduler._executor.ctx.is_paused()
        return False