# -*- coding: utf-8 -*-
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QVBoxLayout

from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.widgets.ipython_console.variable_explorer import VariableExplorerWidget


class VariableExplorerToolWindow(ToolWindow):
    name = "变量浏览器"
    icon = get_icon("变量")
    singleton = True
    default_position = DockPosition.TOP  # 放在顶部

    def __init__(self, page):
        super().__init__(page)
        self.explorer.set_kernel_manager(page.ipython_kernel.kernel_manager)
        QTimer.singleShot(100, self.explorer.start_auto_refresh)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.explorer = VariableExplorerWidget(parent=self.homepage, kernel_manager=None)
        layout.addWidget(self.explorer)

    def set_kernel_manager(self, kernel_manager):
        self.explorer.set_kernel_manager(kernel_manager)

    def start_auto_refresh(self):
        self.explorer.start_auto_refresh()

    def stop_auto_refresh(self):
        self.explorer.stop_auto_refresh()

    def refresh(self):
        self.explorer.refresh()

    def cleanup(self):
        self.stop_auto_refresh()