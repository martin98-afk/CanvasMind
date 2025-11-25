from PyQt5.QtWidgets import QVBoxLayout

from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.widgets.ipython_console.ipython_console import EmbeddedIPythonConsole

class IPythonConsoleToolWindow(ToolWindow):
    name = "IPython 控制台"
    icon = get_icon("console")
    singleton = True
    default_position = DockPosition.BOTTOM  # 放在底部

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.console = EmbeddedIPythonConsole(self.canvas_page)
        layout.addWidget(self.console)

    def start_kernel(self, python_exe: str):
        return self.console.start_kernel(python_exe)

    def stop_kernel(self):
        self.console.stop_kernel()

    def execute(self, code: str):
        self.console.execute(code)

    def set_focus(self):
        self.console.setFocus()