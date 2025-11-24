from PyQt5.QtCore import pyqtSignal, QObject, QTimer
from qtpy import QtCore

from app.scheduler.workflow_scheduler import WorkflowScheduler


class CanvasRunner(QObject):
    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str)
    node_error = pyqtSignal(str)
    workflow_started = pyqtSignal()
    workflow_finished = pyqtSignal()
    workflow_error = pyqtSignal(str)
    workflow_cancelled = pyqtSignal()
    node_status_changed = pyqtSignal(str, object)  # node_id, status
    property_changed = pyqtSignal(object)  # for property panel

    def __init__(self, ipython_kernel, parent=None):
        super().__init__(parent)
        self._scheduler = None
        self.ipython_kernel = ipython_kernel
        self.parent = parent

    def _create_scheduler(self):
        if self._scheduler:
            self._scheduler.cancel()
        self._scheduler = WorkflowScheduler(
            graph=self.parent.graph,
            component_map=self.parent.component_map,
            get_node_status=self.parent.get_node_status,
            get_python_exe=self.parent.get_current_python_exe,
            kernel_manager=self.ipython_kernel,
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
        if self.parent.property_panel.get_current_execution_order():
            nodes = self.parent.property_panel.get_current_execution_order()
            self._scheduler.run_full(nodes=nodes, sort=False)
            self._scheduler.node_started.connect(
                lambda : QtCore.QTimer.singleShot(
                    50, self.parent.property_panel.node_list_panel_widget.update_node_list_content
                )
            )
            self._scheduler.backdrop_finished.connect(
                lambda: QtCore.QTimer.singleShot(
                    50, lambda: self.parent.property_panel.update_properties(nodes)
                )
            )
            self._scheduler.node_finished.connect(
                lambda: QtCore.QTimer.singleShot(
                    50, self.parent.property_panel.node_list_panel_widget.update_node_list_content
                )
            )
            self._scheduler.finished.connect(
                lambda: QtCore.QTimer.singleShot(
                    50, self.parent.property_panel.node_list_panel_widget.update_node_list_content
                )
            )
            self._scheduler.error.connect(
                lambda: QtCore.QTimer.singleShot(
                    50, self.parent.property_panel.node_list_panel_widget.update_node_list_content
                )
            )
            self._scheduler.cancelled.connect(
                lambda: QtCore.QTimer.singleShot(
                    50, self.parent.property_panel.node_list_panel_widget.update_node_list_content
                )
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
        scheduler.node_started.connect(self.node_started.emit)
        scheduler.node_finished.connect(self.node_finished.emit)
        scheduler.node_error.connect(self.node_error.emit)
        scheduler.finished.connect(self.workflow_finished.emit)
        scheduler.error.connect(self.workflow_error.emit)

    def stop_workflow(self):
        if self._scheduler:
            self._scheduler.cancel()
            self._scheduler = None
            self.workflow_cancelled.emit()
