from PyQt5.QtCore import pyqtSignal, QObject, QTimer
from qtpy import QtCore

from app.scheduler.workflow_scheduler import WorkflowScheduler
from app.widgets.dialog_widget.intervention_dialog import InterventionDialog


class CanvasRunner(QObject):
    workflow_started = pyqtSignal()
    workflow_finished = pyqtSignal()
    workflow_error = pyqtSignal(str)
    workflow_cancelled = pyqtSignal()
    workflow_paused = pyqtSignal()  # ← 新增
    workflow_resumed = pyqtSignal()  # ← 新增
    node_status_changed = pyqtSignal(str, object)
    property_changed = pyqtSignal(object)
    node_vars_changed = pyqtSignal()

    def __init__(self, get_python_exe, parent=None):
        super().__init__(parent)
        self._scheduler = None
        self.get_python_exe = get_python_exe
        self.parent = parent

    def _create_scheduler(self):
        if self._scheduler:
            self._scheduler.cancel()
        self._scheduler = WorkflowScheduler(
            graph=self.parent.graph,
            component_map=self.parent.component_map,
            get_node_status=self.parent.get_node_status,
            get_python_exe=self.get_python_exe,
            kernel_manager=self.parent.ipython_kernel,
            global_variables=self.parent.global_variables,
            parent=self.parent,
        )
        self._scheduler.node_status_changed.connect(self.node_status_changed.emit)
        self._scheduler.property_changed.connect(self.property_changed.emit)
        return self._scheduler

    def run_workflow(self):
        """执行所有选中节点的工作流"""
        self._scheduler = self._create_scheduler()
        self._connect_signals(self._scheduler)
        nodes = self.parent.property_panel.get_current_execution_order()
        if nodes:
            self._scheduler.run_full(nodes=nodes, sort=False)
            for sig in [
                self._scheduler.backdrop_finished,
                self._scheduler.finished,
                self._scheduler.error,
                self._scheduler.cancelled,
                self._scheduler.node_status_changed
            ]:
                sig.connect(
                    lambda: QTimer.singleShot(50, self.parent.property_panel.update_node_list_content)
                )
            self._scheduler.backdrop_finished.connect(
                lambda: QTimer.singleShot(50, lambda: self.parent.property_panel.update_properties(nodes))
            )
        else:
            self._scheduler.run_full(nodes=self.parent.graph.selected_nodes())

    def run_full(self, nodes=None, sort=True):
        scheduler = self._create_scheduler()
        self._connect_signals(scheduler)
        if nodes is None:
            nodes = self.parent.graph.selected_nodes()
        scheduler.run_full(nodes=nodes, sort=sort)

    def run_to(self, target_node):
        scheduler = self._create_scheduler()
        self._connect_signals(scheduler)
        scheduler.run_to(target_node)

    def run_node(self, node):
        scheduler = self._create_scheduler()
        self._connect_signals(scheduler)
        scheduler.run(node)

    def run_from(self, start_node):
        scheduler = self._create_scheduler()
        self._connect_signals(scheduler)
        scheduler.run_from(start_node)

    def _connect_signals(self, scheduler):
        self.workflow_started.emit()
        scheduler.finished.connect(self.workflow_finished.emit)
        scheduler.error.connect(self.workflow_error.emit)
        scheduler.node_vars_changed.connect(self.node_vars_changed.emit)

    def stop_workflow(self):
        if self._scheduler:
            self._scheduler.cancel()
            self._scheduler = None
            self.workflow_cancelled.emit()

    def pause_workflow(self):
        """暂停执行（可恢复）"""
        if self._scheduler and self._scheduler._executor:
            self._scheduler._executor.pause()
            self.workflow_paused.emit()

    def resume_workflow(self):
        """继续执行（从暂停处恢复）"""
        if self._scheduler and self._scheduler._executor:
            self._scheduler._executor.resume()
            self.workflow_resumed.emit()

    def is_paused(self) -> bool:
        """查询当前是否处于暂停状态"""
        if self._scheduler and self._scheduler._executor:
            return self._scheduler._executor.ctx.is_paused()
        return False

    def show_intervention_dialog(self, title, message, schema, callback):
        """
        弹出人工干预对话框
        :param callback: 这是一个函数，当用户点击确定时调用，传入结果字典
        """
        # 确保在主线程弹出 UI
        if QtCore.QThread.currentThread() != self.thread():
            # 如果在子线程，使用信号或者 metaObject 触发
            QtCore.QMetaObject.invokeMethod(self, "show_intervention_dialog",
                                            QtCore.Qt.BlockingQueuedConnection,
                                            QtCore.Q_ARG(str, title),
                                            QtCore.Q_ARG(str, message),
                                            QtCore.Q_ARG(dict, schema),
                                            QtCore.Q_ARG(object, callback))
            return

        # 创建并显示对话框
        dialog = InterventionDialog(title, message, schema, self.parent)

        # 也可以修改按钮文本
        dialog.yesButton.setText("确认并继续")
        dialog.cancelButton.hide()

        if dialog.exec():
            # 用户点击了“确认”
            result_data = dialog.get_result()
            callback(result_data)
        else:
            # 用户取消了，这里可以不写回文件，或者写回一个特殊标记
            # 节点端检测到超时或特定标记会抛出异常终止
            pass