# -*- coding: utf-8 -*-
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from PyQt5.QtCore import pyqtSignal, QObject, QTimer
from loguru import logger

from app.scheduler.workflow_scheduler import WorkflowScheduler


@dataclass
class ExecutionTask:
    """封装执行任务的实体"""
    mode: str  # 'full', ‘subgraph', 'to', 'from', 'node', 'selected'
    target: Any  # node or list of nodes
    sort: bool = True
    triggered_data: dict = None
    task_id: str = None


class CanvasRunner(QObject):
    # --- 信号定义 ---
    workflow_started = pyqtSignal()
    workflow_finished = pyqtSignal()
    workflow_error = pyqtSignal(str)
    workflow_cancelled = pyqtSignal()
    workflow_paused = pyqtSignal()
    workflow_resumed = pyqtSignal()
    node_status_changed = pyqtSignal(str, object)
    property_changed = pyqtSignal(object)
    node_vars_changed = pyqtSignal()
    queue_size_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._task_queue = deque()
        self._is_running = False
        self._current_task: Optional[ExecutionTask] = None

        # 1. 初始化常驻调度器
        self._scheduler = self._init_scheduler()

        # 2. 建立永久信号连接 (只连接一次)
        self._setup_permanent_connections()

    def _init_scheduler(self):
        """创建唯一的调度器实例"""
        return WorkflowScheduler(
            graph=self.parent.graph,
            component_map=self.parent.component_map,
            get_node_status=self.parent.get_node_status,
            get_python_exe=lambda: self.parent.env_data.get("path"),
            parent=self.parent,
        )

    def _setup_permanent_connections(self):
        """连接调度器信号到内部处理函数"""
        s = self._scheduler

        # 基础转发信号
        s.node_status_changed.connect(self.node_status_changed.emit)
        s.property_changed.connect(self.property_changed.emit)
        s.node_vars_changed.connect(self.node_vars_changed.emit)

        # 状态控制信号
        s.finished.connect(self._handle_scheduler_finished)
        s.error.connect(self._handle_scheduler_error)
        s.cancelled.connect(self._handle_scheduler_cancelled)

        # 逻辑联动信号 (对应原代码中的 UI 更新逻辑)
        s.node_status_changed.connect(self._on_status_changed_ui_update)

        # 如果调度器支持 backdrop_finished
        if hasattr(s, 'backdrop_finished'):
            s.backdrop_finished.connect(self._handle_backdrop_finished)

    # --- 兼容旧代码的 UI 调用接口 ---

    def run_workflow(self):
        nodes = self.parent.property_panel.get_current_execution_order()
        if nodes:
            self._enqueue(ExecutionTask('selected', nodes, sort=False))
        else:
            selected_nodes = self.parent.graph.selected_nodes()
            self._enqueue(ExecutionTask('full', selected_nodes, sort=True))

    def run_full(self, nodes=None, triggered_data=None, task_id=None, sort=True):
        self._enqueue(ExecutionTask('full', nodes, sort=sort, triggered_data=triggered_data, task_id=task_id))

    def run_subgraph(self, nodes=None, triggered_data=None, task_id=None):
        self._enqueue(ExecutionTask('subgraph', nodes, triggered_data=triggered_data, task_id=task_id))

    def run_to(self, target_node, triggered_data=None, task_id=None):
        self._enqueue(ExecutionTask('to', target_node, triggered_data=triggered_data, task_id=task_id))

    def run_from(self, start_node, triggered_data=None, task_id=None):
        self._enqueue(ExecutionTask('from', start_node, triggered_data=triggered_data, task_id=task_id))

    def run_node(self, node):
        self._enqueue(ExecutionTask('node', node))

    # --- 队列核心逻辑 ---

    def _enqueue(self, task: ExecutionTask):
        """任务入队并尝试启动"""
        self._task_queue.append(task)
        # 1. 创建执行记录
        self.parent.execution_record.create_record(
            exec_id=task.task_id,
            canvas_name=self.parent.workflow_name,
            trigger_type=task.mode,
            input_data=task.triggered_data
        )
        self.queue_size_changed.emit(len(self._task_queue))
        logger.info(f"[Runner] 任务入队: {task.mode}. 当前队列长度: {len(self._task_queue)}")

        if not self._is_running:
            self._process_next_task()

    def _process_next_task(self):
        """处理队列中的下一个任务"""
        if not self._task_queue:
            self._is_running = False
            self._current_task = None
            logger.info("[Runner] 所有任务执行完毕。")
            return

        self._is_running = True
        self._current_task = self._task_queue.popleft()
        self.queue_size_changed.emit(len(self._task_queue))
        self.parent.execution_record.update_record(
            self._current_task.task_id, "running", output_data={}
        )

        # 2. 通知 UI 启动
        self.workflow_started.emit()

        # 3. 启动执行
        task = self._current_task
        try:
            if task.mode in ['full', 'selected']:
                nodes = task.target or self.parent.graph.selected_nodes()
                self._scheduler.run_full(nodes=nodes, sort=task.sort)
            elif task.mode == 'subgraph':
                self._scheduler.run_subgraph(task.target)
            elif task.mode == 'to':
                self._scheduler.run_to(task.target)
            elif task.mode == 'from':
                self._scheduler.run_from(task.target)
            elif task.mode == 'node':
                self._scheduler.run(task.target)
        except Exception as e:
            logger.exception(f"[Runner] 调度器启动失败: {e}")
            self._handle_scheduler_error(str(e))

    def store_output(self, output):
        self.parent.execution_record.update_record(self._current_task.task_id, "running", output_data=output)

    def get_trigger_data(self, task_id: str) -> dict:
        """根据 task_id 获取触发数据"""
        # 优先从当前任务对象获取
        if self._current_task and self._current_task.task_id == task_id:
            return self._current_task.triggered_data or {}

    # --- 内部信号处理槽 (Proxy Slots) ---

    def _handle_scheduler_finished(self):
        """调度器正常完成"""
        if self._current_task:
            self.parent.execution_record.update_record(
                self._current_task.task_id, "success", output_data={}
            )
            # 如果是 workflow 模式，执行完后刷新一次列表
            if self._current_task.mode == 'selected':
                self._update_ui_deferred()

        self.workflow_finished.emit()
        logger.info(f"[Runner] 任务完成: {self._current_task.mode if self._current_task else 'None'}")
        QTimer.singleShot(100, self._process_next_task)

    def _handle_scheduler_error(self, msg):
        """调度器报错"""
        if self._current_task:
            self.parent.execution_record.update_record(
                self._current_task.task_id, "failed", error_msg=msg
            )
            if self._current_task.mode == 'selected':
                self._update_ui_deferred()

        self.workflow_error.emit(msg)
        logger.error(f"[Runner] 任务失败: {msg}")
        QTimer.singleShot(100, self._process_next_task)

    def _handle_scheduler_cancelled(self):
        """调度器取消"""
        # 取消通常意味着清空队列或停止后续
        self.workflow_cancelled.emit()
        logger.warning("[Runner] 任务被取消")
        # 如果需要取消后续所有任务：
        # self.stop_workflow()
        # 如果只需要跳到下一个：
        QTimer.singleShot(100, self._process_next_task)

    def _handle_backdrop_finished(self):
        """处理 backdrop_finished 信号"""
        if self._current_task and self._current_task.target:
            QTimer.singleShot(50, lambda: self.parent.property_panel.update_properties(self._current_task.target))

    def _on_status_changed_ui_update(self):
        """节点状态改变时的 UI 联动"""
        if self._current_task and self._current_task.mode == 'selected':
            self._update_ui_deferred()

    def _update_ui_deferred(self):
        """延迟更新 UI 避免卡顿"""
        QTimer.singleShot(50, self.parent.property_panel.update_node_list_content)

    # --- 控制逻辑 ---

    def stop_workflow(self):
        """终止当前执行并清空队列"""
        self._task_queue.clear()
        self.queue_size_changed.emit(0)
        if self._scheduler:
            self._scheduler.cancel()
        self._is_running = False
        self._current_task = None
        self.workflow_cancelled.emit()
        self._update_ui_deferred()

    def pause_workflow(self):
        if hasattr(self._scheduler, '_executor'):
            self._scheduler._executor.pause()
            self.workflow_paused.emit()

    def resume_workflow(self):
        if hasattr(self._scheduler, '_executor'):
            self._scheduler._executor.resume()
            self.workflow_resumed.emit()

    def is_paused(self) -> bool:
        if hasattr(self._scheduler, '_executor'):
            return self._scheduler._executor.ctx.is_paused()
        return False