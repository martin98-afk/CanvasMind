# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.ipython_console.variable_explorer import VariableExplorerWidget
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.widgets.ipython_console.ipython_console import (
    EmbeddedIPythonConsole,
    IPythonConsoleManager,
)


class MultiConsoleToolWindow(ToolWindow):
    name = "多终端调试面板"
    icon = get_icon("调试")
    singleton = True
    default_position = DockPosition.BOTTOM
    CATEGORIES = ["组件开发"]
    _var_explorer = None
    _console_manager = None

    def setup_ui(self):
        central_layout = QVBoxLayout(self)
        central_layout.setContentsMargins(0, 0, 0, 0)
        # 创建变量浏览器
        self._var_explorer = VariableExplorerWidget(
            parent=self,
            kernel_manager=None,  # 先不设置内核管理器
        )
        # 创建Console管理器
        self._console_manager = IPythonConsoleManager(
            parent=self,
            package_manager=self.homepage.package_manager,
            var_explorer=self._var_explorer,
        )

        # 创建垂直分割器
        splitter = ModernSplitter(Qt.Vertical)
        splitter.addWidget(self._var_explorer)
        splitter.addWidget(self._console_manager)
        splitter.setSizes([300, 400])  # 变量浏览器较小，控制台较大

        central_layout.addWidget(splitter)

    def get_current_console(self):
        """
        获取当前激活的Console
        :return:
        """
        return self._console_manager.get_current_console()

    @property
    def var_explorer(self):
        return self._var_explorer

    @property
    def console_manager(self):
        return self._console_manager
