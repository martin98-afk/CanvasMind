# app/widgets/workflow_manager.py
import os

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QFileDialog
from qfluentwidgets import (
    TabBar, CommandBar, Action, FluentIcon,
    InfoBar, MessageBox
)

from app.interfaces.canvas_interface import CanvasPage


class WorkflowManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflow_manager")
        self.parent = parent
        self.file_paths = []  # 记录每个 Tab 对应的文件路径

        # === TabBar + StackedWidget ===
        self.tab_bar = TabBar(self)
        self.stacked_widget = QStackedWidget(self)

        self.tab_bar.setAddButtonVisible(True)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close)
        self.tab_bar.tabAddRequested.connect(self.new_workflow)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)

        # 布局
        layout = QVBoxLayout(self)
        layout.addWidget(self.tab_bar)
        layout.addWidget(self.stacked_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 默认新建一个工作流
        self.new_workflow()

    def new_workflow(self):
        canvas = CanvasPage(self.parent)
        canvas.file_path = None
        index = self.stacked_widget.addWidget(canvas)
        self.tab_bar.addTab(routeKey=f"未命名 {index + 1}", text=f"未命名 {index + 1}")
        self.tab_bar.setCurrentIndex(index)
        self.file_paths.append(None)

    def _on_tab_close(self, index):
        if self.tab_bar.count() <= 1:
            return  # 至少保留一个 Tab

        self.stacked_widget.removeWidget(self.stacked_widget.widget(index))
        self.file_paths.pop(index)
        self.tab_bar.removeTab(index)

    def _on_tab_changed(self, index):
        if index >= 0:
            self.stacked_widget.setCurrentIndex(index)