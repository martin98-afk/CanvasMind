from PyQt5.QtWidgets import QVBoxLayout

from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.widgets.ipython_console.ipython_console import EmbeddedIPythonConsole

class IPythonConsoleToolWindow(ToolWindow):
    name = "IPython 控制台"
    icon = get_icon("ipython")
    singleton = True
    default_position = DockPosition.BOTTOM  # 放在底部

    def setup_ui(self):

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.console = EmbeddedIPythonConsole(self.homepage)
        layout.addWidget(self.console)

    @property
    def kernel_manager(self):
        return self.console.get_kernel_manager()

    def start_kernel(self, python_exe: str):
        return self.console.start_kernel(python_exe)

    def stop_kernel(self):
        self.console.stop_kernel()

    def restart_kernel(self):
        self.console.restart_kernel()

    def execute_code(self, code: str, hidden: bool= False):
        self.console.execute_code(code, hidden)

    def set_focus(self):
        self.console.setFocus()