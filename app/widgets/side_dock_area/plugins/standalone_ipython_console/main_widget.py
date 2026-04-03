from PyQt5.QtWidgets import QVBoxLayout

from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.widgets.ipython_console.ipython_console import EmbeddedIPythonConsole


class IPythonConsoleToolWindow(ToolWindow):
    name = "IPython 控制台"
    icon = get_icon("ipython")
    singleton = False
    default_position = DockPosition.BOTTOM
    CATEGORIES = ["运行画布"]
    display_order = 60

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.console = EmbeddedIPythonConsole(
            self.homepage, self.homepage.parent.package_manager
        )
        layout.addWidget(self.console)

    @property
    def kernel_manager(self):
        return self.console.get_kernel_manager()

    def interrupt_kernel(self):
        return self.console.interrupt_kernel()

    def start_kernel(self, env_data: dict):
        return self.console.start_kernel(env_data)

    def stop_kernel(self):
        self.console.stop_kernel()

    def restart_kernel(self):
        self.console.restart_kernel()

    def execute_code(self, code: str, hidden: bool = False):
        self.console.execute_code(code, hidden)

    def set_focus(self):
        self.console.setFocus()
