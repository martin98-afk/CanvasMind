# -*- coding: utf-8 -*-
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QHBoxLayout, QWidget

from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.ipython_console.ipython_console import EmbeddedIPythonConsole
from app.widgets.ipython_console.variable_explorer import VariableExplorerWidget
from app.interfaces.canvas_interaface.constants import CONSOLE_HEIGHT
from app.interfaces.canvas_interaface.utils.logger import get_logger

logger = get_logger("ConsoleManager")

class ConsoleManager:
    def __init__(self, parent):
        self.parent = parent
        self.console_container = None
        self.ipython_console = None
        self.var_explorer = None

    def create_console_panel(self):
        self.ipython_console = EmbeddedIPythonConsole(self.parent)
        self.var_explorer = VariableExplorerWidget(parent=self.parent, kernel_manager=None)
        self.console_container = QWidget(self.parent.canvas_widget)
        self.console_container.hide()
        self.console_container.setStyleSheet("background-color: #2d2d2d;")
        console_layout = QHBoxLayout(self.console_container)
        console_layout.setContentsMargins(0, 0, 0, 5)
        splitter = ModernSplitter(Qt.Horizontal)
        splitter.addWidget(self.var_explorer)
        splitter.addWidget(self.ipython_console)
        splitter.setSizes([400, 400])
        console_layout.addWidget(splitter)
        self.console_container.setFixedHeight(CONSOLE_HEIGHT)
        self._update_position()
        QTimer.singleShot(0, self.connect_kernel)

    def connect_kernel(self):
        python_exe = self.parent.get_current_python_exe()
        if python_exe:
            if self.ipython_console.kernel_manager.python_exe_path != python_exe or \
               not self.ipython_console.kernel_manager.get_kernel_info().get("is_alive"):
                self.ipython_console.kernel_manager.shutdown_kernel()
                if self.ipython_console.start_kernel(python_exe):
                    self.var_explorer.set_kernel_manager(self.ipython_console.kernel_manager)
                    self.var_explorer.start_auto_refresh()
                else:
                    logger.error("Failed to start IPython kernel")

    def toggle(self):
        if self.console_container.isVisible():
            self.hide()
        else:
            self.show()

    def show(self):
        self.console_container.show()
        self.ipython_console.setFocus()
        self._update_position()

    def hide(self):
        self.console_container.hide()
        self._update_position()

    def _update_position(self):
        if not self.console_container or not self.parent.canvas_widget:
            return
        cw = self.parent.canvas_widget
        h = self.console_container.height()
        self.console_container.setGeometry(40, cw.height() - h, cw.width() - 80, h)

    def shutdown(self):
        if self.ipython_console:
            self.ipython_console.stop_kernel()
        if self.var_explorer:
            self.var_explorer.set_kernel_manager(None)