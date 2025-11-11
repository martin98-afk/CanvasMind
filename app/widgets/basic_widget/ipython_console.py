import uuid
from loguru import logger
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QStackedWidget
)
from qfluentwidgets import TabBar, ComboBox, CommandBar, Action, FluentIcon
from qtconsole.rich_jupyter_widget import RichJupyterWidget

from app.utils.ipython_kernel_manager import IPythonKernelManager
from app.utils.utils import get_icon


class EnvironmentSelector(QWidget):
    """环境选择器（保持原有功能）"""
    env_changed = pyqtSignal(str)

    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.combo = ComboBox()
        self.package_manager = package_manager
        self.combo.currentTextChanged.connect(self.on_environment_changed)
        self.load_env_combos()
        self.layout.addWidget(self.combo)

    def load_env_combos(self):
        if self.package_manager:
            envs = self.package_manager.mgr.list_envs()
            self.combo.addItems(envs)

    def on_environment_changed(self, text):
        if self.package_manager and text:
            try:
                python_exe = str(self.package_manager.mgr.get_python_exe(text))
                self.env_changed.emit(python_exe)
            except Exception as e:
                print(f"获取环境 {text} 的Python路径失败: {str(e)}")

    def get_current_python_exe(self):
        current_text = self.combo.currentText()
        if self.package_manager and current_text:
            try:
                return str(self.package_manager.mgr.get_python_exe(current_text))
            except Exception as e:
                print(f"获取环境 {current_text} 的Python路径失败: {str(e)}")
                return None
        return None


class EmbeddedIPythonConsole(QWidget):
    """嵌入式IPython控制台GUI组件"""

    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.package_manager = package_manager
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        # 命令栏
        commandBar = CommandBar()
        if package_manager is not None:
            title_label = QLabel("环境选择: ")
            title_label.setStyleSheet("font: 12px 'Segoe UI', 'Microsoft YaHei'; color: white;")
            commandBar.addWidget(title_label)
            self.env_selector = EnvironmentSelector(parent=self, package_manager=package_manager)
            commandBar.addWidget(self.env_selector)
            commandBar.addSeparator()
            self.env_selector.env_changed.connect(self.start_kernel)

        self.add_common_tools(commandBar)
        self.layout.addWidget(commandBar)
        # 控制台
        self.console = RichJupyterWidget()
        self.console.set_default_style(colors='linux')
        self.console.banner = "IPython Console (Embedded)\n"
        self.layout.addWidget(self.console)

        # 内核管理器
        self.kernel_manager = IPythonKernelManager()

        if hasattr(self, "env_selector") and self.env_selector.get_current_python_exe():
            self.start_kernel(self.env_selector.get_current_python_exe())

    def add_common_tools(self, commandBar):
        """添加常用工具按钮"""
        restart_action = Action(get_icon("远程重启"), "重新运行Console", self)
        restart_action.triggered.connect(self.restart_kernel)
        commandBar.addAction(restart_action)

        clear_action = Action(get_icon("清空参数"), "清空画面", self)
        clear_action.triggered.connect(lambda: self.execute_code("%clear"))
        commandBar.addAction(clear_action)

        reset_action = Action(get_icon("删除变量"), "重置变量", self)
        reset_action.triggered.connect(lambda: self.execute_code("%reset -f"))
        commandBar.addAction(reset_action)

        commandBar.addSeparator()

        whos_action = Action(FluentIcon.VIEW, "whos", self)
        whos_action.triggered.connect(lambda: self.execute_code("%whos"))
        commandBar.addAction(whos_action)

        pwd_action = Action(FluentIcon.FOLDER, "pwd", self)
        pwd_action.triggered.connect(lambda: self.execute_code("%pwd"))
        commandBar.addAction(pwd_action)

        ls_action = Action(get_icon("ls"), "ls", self)
        ls_action.triggered.connect(lambda: self.execute_code("%ls"))
        commandBar.addAction(ls_action)

        commandBar.addSeparator()

        globals_action = Action(FluentIcon.ZOOM, "查看 globals", self)
        globals_action.triggered.connect(lambda: self.execute_code("globals()"))
        commandBar.addAction(globals_action)

    def restart_kernel(self):
        """重新启动Kernel"""
        logger.info("正在重新启动 Kernel...")
        self.kernel_manager.shutdown_kernel()
        self.start_kernel(self.kernel_manager.python_exe_path)

    def stop_kernel(self):
        """停止内核"""
        logger.info("正在停止 Kernel...")
        self.kernel_manager.shutdown_kernel()

    def execute_code(self, code, hidden=False):
        """执行代码"""
        self.console.execute(code, hidden)

    def start_kernel(self, python_exe_path=None):
        """启动内核"""
        if python_exe_path is None:
            python_exe_path = self.env_selector.get_current_python_exe()

        if self.kernel_manager.start_kernel(python_exe_path):
            # 设置控制台的内核管理器和客户端
            self.console.kernel_manager = self.kernel_manager.kernel_manager
            self.console.kernel_client = self.kernel_manager.kernel_client
            return True
        else:
            logger.error("Kernel启动失败")
            return False

    def get_kernel_manager(self):
        """获取内核管理器"""
        return self.kernel_manager


class IPythonConsoleManager(QWidget):
    """控制台标签管理器"""

    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.package_manager = package_manager
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.tab_bar = TabBar()
        self.tab_bar.setScrollable(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.setTabMaximumWidth(150)
        self.tab_bar.setAddButtonVisible(True)
        self.stacked_widget = QStackedWidget()

        self.layout.addWidget(self.tab_bar)
        self.layout.addWidget(self.stacked_widget)

        self.tab_bar.tabAddRequested.connect(self.add_new_console_tab)
        self.tab_bar.tabCloseRequested.connect(self.close_console_tab)
        self.tab_bar.currentChanged.connect(self.on_tab_changed)

        self.add_new_console_tab()

    def on_tab_changed(self, index):
        """标签切换"""
        self.stacked_widget.setCurrentIndex(index)

    def add_new_console_tab(self):
        console_widget = EmbeddedIPythonConsole(
            parent=self.stacked_widget, package_manager=self.package_manager
        )
        initial_env = console_widget.env_selector.combo.currentText()
        tab_title = f"Console ({initial_env})" if initial_env else "Console"

        index = self.stacked_widget.addWidget(console_widget)
        self.tab_bar.addTab(routeKey=str(uuid.uuid4()), text=tab_title)
        self.tab_bar.setCurrentIndex(index)
        self.stacked_widget.setCurrentIndex(index)
        console_widget.env_selector.env_changed.connect(
            lambda path, idx=index: self.update_tab_title(idx)
        )

    def update_tab_title(self, index):
        console_widget = self.stacked_widget.widget(index)
        if isinstance(console_widget, EmbeddedIPythonConsole):
            env_name = console_widget.env_selector.combo.currentText()
            self.tab_bar.setTabText(index, f"Console ({env_name})")

    def close_console_tab(self, index):
        console_widget = self.stacked_widget.widget(index)
        if console_widget:
            console_widget.kernel_manager.shutdown_kernel()
            console_widget.close()
            self.stacked_widget.removeWidget(console_widget)
            self.tab_bar.removeTab(index)
            if self.tab_bar.currentIndex() == -1 and self.tab_bar.count() > 0:
                new_index = min(index, self.tab_bar.count() - 1)
                self.tab_bar.setCurrentIndex(new_index)

    def get_current_console(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index >= 0:
            return self.stacked_widget.widget(current_index)
        return None

    def get_current_kernel_manager(self):
        """获取当前控制台的内核管理器"""
        console = self.get_current_console()
        if console:
            return console.get_kernel_manager()
        return None