import uuid
from PyQt5.QtCore import pyqtSignal, QObject
from app.scheduler.workflow_scheduler import WorkflowScheduler


class CanvasMultiRunner(QObject):
    """
    独立的多任务运行器，不影响主画布的运行状态按钮
    """
    task_started = pyqtSignal(str)  # task_id
    task_finished = pyqtSignal(str)
    task_error = pyqtSignal(str, str)
    # 仅用于通知 UI 更新节点颜色，不触发属性面板刷新
    node_status_changed = pyqtSignal(str, str, object)  # task_id, node_id, status

    def __init__(self, canvas_page):
        super().__init__(canvas_page)
        self.canvas = canvas_page
        self._active_tasks = {}  # {task_id: {"scheduler": s, "console_id": c}}

    def run_parallel(self, nodes, task_name="Parallel_Task"):
        """一键开启后台并行任务"""
        if not nodes: return

        task_id = f"task_{uuid.uuid4().hex[:6]}"

        # 1. 申请完全独立的控制台
        console_label = f"BACKEND: {task_name}"
        console_id = self.canvas.ipython_kernel.add_console(env_name=console_label)

        # 2. 启动该任务专用的内核
        python_exe = self.canvas.get_current_python_exe()
        self.canvas.ipython_kernel.start_kernel(python_exe, console_id=console_id)

        # 3. 创建独立调度器
        km = self.canvas.ipython_kernel.get_kernel_manager_by_id(console_id)
        scheduler = WorkflowScheduler(
            graph=self.canvas.graph,
            component_map=self.canvas.component_map,
            get_node_status=self.canvas.get_node_status,
            get_python_exe=self.canvas.get_current_python_exe,
            kernel_manager=km,
            global_variables=self.canvas.global_variables,
            parent=self.canvas,
        )

        # 4. 记录并连接信号
        self._active_tasks[task_id] = {"scheduler": scheduler, "console_id": console_id}

        scheduler.finished.connect(lambda: self._on_task_finished(task_id))
        scheduler.error.connect(lambda msg: self.task_error.emit(task_id, msg))
        scheduler.node_status_changed.connect(
            lambda node_id, status: self.node_status_changed.emit(task_id, node_id, status)
        )

        # 5. 开始执行
        self.task_started.emit(task_id)
        scheduler.run_full(nodes=nodes, sort=True)
        return task_id

    def _on_task_finished(self, task_id):
        if task_id in self._active_tasks:
            # 任务完成后可以根据策略决定是否保留控制台
            self.task_finished.emit(task_id)

    def cancel_task(self, task_id):
        if task_id in self._active_tasks:
            info = self._active_tasks.pop(task_id)
            info["scheduler"].cancel()
            self.canvas.ipython_kernel.stop_kernel(info["console_id"])

    def cancel_all(self):
        for tid in list(self._active_tasks.keys()):
            self.cancel_task(tid)