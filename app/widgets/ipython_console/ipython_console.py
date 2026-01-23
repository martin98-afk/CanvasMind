import uuid
from loguru import logger
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QStackedWidget
)
from qfluentwidgets import TabBar, ComboBox, CommandBar, Action, FluentIcon
from qtconsole.rich_jupyter_widget import RichJupyterWidget

from app.server_manager.ipython_server.ipython_kernel_manager import IPythonKernelManager
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
        self.setMinimumWidth(300)
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
        # 透明背景
        self.console.setStyleSheet("background-color: transparent;")
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
        if self.kernel_manager.is_alive():
            self.kernel_manager.shutdown_kernel()

    def execute_code(self, code, hidden=False):
        """执行代码"""
        self.console.execute(code, hidden)

    def interrupt_kernel(self):
        """中断正在运行的代码"""
        return self.kernel_manager.interrupt_kernel()

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
    """控制台标签管理器 - 适配多内核并行及 ID 访问"""

    def __init__(self, parent=None, package_manager=None, var_explorer=None, init_console=True):
        super().__init__(parent)
        self.package_manager = package_manager
        self.var_explorer = var_explorer
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 核心映射字典：{console_id: console_widget}
        self.consoles = {}

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

        if len(package_manager.mgr.list_envs()) > 0 and init_console:
            self.add_new_console_tab()

    def on_tab_changed(self, index):
        """标签切换"""
        self.stacked_widget.setCurrentIndex(index)
        self.set_var_explorer()

    def set_var_explorer(self):
        kernel_manager = self.get_current_kernel_manager()
        if kernel_manager and self.var_explorer:
            self.var_explorer.stop_auto_refresh()
            self.var_explorer.set_kernel_manager(kernel_manager)
            self.var_explorer.start_auto_refresh()

    def add_new_console_tab(self, env_name=None):
        """
        创建新控制台标签
        :param env_name: 可选，指定环境名称（需存在于 package_manager 中）
        :return: console_id 唯一标识符
        """
        console_id = str(uuid.uuid4())
        console_widget = EmbeddedIPythonConsole(
            parent=self.stacked_widget, package_manager=self.package_manager
        )
        self.consoles[console_id] = console_widget

        if env_name:
            # 这会自动触发 env_selector 的 currentTextChanged 信号
            # 从而调用 console_widget.start_kernel
            console_widget.env_selector.combo.setCurrentText(env_name)

        initial_env = console_widget.env_selector.combo.currentText()
        tab_title = f"Console ({initial_env})" if initial_env else "Console"

        index = self.stacked_widget.addWidget(console_widget)
        # 在 qfluentwidgets 中，routeKey 存储在 TabItem 中
        self.tab_bar.addTab(routeKey=console_id, text=tab_title)
        self.tab_bar.setCurrentIndex(index)
        self.stacked_widget.setCurrentIndex(index)

        # 闭包记录当前 ID 方便更新标题
        console_widget.env_selector.env_changed.connect(
            lambda path, cid=console_id: self.update_tab_title_by_id(cid)
        )
        self.set_var_explorer()
        return console_id

    def update_tab_title_by_id(self, console_id):
        """【新增】通过 ID 更新标题，解决 Tab 移动后 index 不准的问题"""
        idx = self.tab_bar.tabIndex(console_id)
        if idx != -1:
            console_widget = self.consoles.get(console_id)
            env_name = console_widget.env_selector.combo.currentText()
            self.tab_bar.setTabText(idx, f"Console ({env_name})")

    def update_tab_title(self, index):
        """保持原有的 index 标题更新逻辑（兼容性保留）"""
        console_widget = self.stacked_widget.widget(index)
        if isinstance(console_widget, EmbeddedIPythonConsole):
            env_name = console_widget.env_selector.combo.currentText()
            self.tab_bar.setTabText(index, f"Console ({env_name})")

    def close_console_tab(self, index):
        """【优化】完善关闭逻辑"""
        # 获取 ID 用于从字典移除
        tab_item = self.tab_bar.tabItem(index)
        if tab_item:
            console_id = tab_item.routeKey
            self.consoles.pop(console_id, None)

        console_widget = self.stacked_widget.widget(index)
        if console_widget:
            console_widget.kernel_manager.shutdown_kernel()
            console_widget.close()
            self.stacked_widget.removeWidget(console_widget)
            self.tab_bar.removeTab(index)

            # 处理关闭后的焦点切换
            if self.tab_bar.currentIndex() == -1 and self.tab_bar.count() > 0:
                new_index = min(index, self.tab_bar.count() - 1)
                self.tab_bar.setCurrentIndex(new_index)
            elif self.tab_bar.count() > 0:
                # 强制刷新一下当前的 stack 显示，防止“东西还在”
                self.stacked_widget.setCurrentIndex(self.tab_bar.currentIndex())

        # 当前如果没有任何控制台，停止变量同步
        if self.tab_bar.count() == 0:
            if self.var_explorer:
                self.var_explorer.stop_auto_refresh()

    def get_current_console(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index >= 0:
            return self.stacked_widget.widget(current_index)
        return None

    def get_current_kernel_manager(self):
        console = self.get_current_console()
        return console.get_kernel_manager() if console else None

    # --- 兼容性/功能扩展接口 ---

    def _get_console_by_id_or_current(self, console_id=None):
        """路由辅助：有 ID 用 ID，没 ID 用当前"""
        if console_id:
            return self.consoles.get(console_id)
        return self.get_current_console()

    def close_console_by_id(self, console_id):
        """
        根据指定的 console_id 关闭控制台
        :param console_id: add_new_console_tab 返回的唯一 ID
        """
        if not console_id or console_id not in self.consoles:
            logger.warning(f"尝试关闭不存在的控制台 ID: {console_id}")
            return False

        # 1. 找到该 ID 对应的 Tab 索引
        index = self.tab_bar.tabIndex(console_id)

        if index != -1:
            # 2. 调用原有的 close_console_tab 逻辑，确保 UI 和 内存同步清理
            logger.info(f"正在通过 ID {console_id} 关闭第 {index} 个标签页")
            self.close_console_tab(index)
            return True
        else:
            # 如果 Tab 不在了但字典还在（异常情况），手动清理字典
            logger.error(f"Tab 中未找到 ID {console_id}，正在强制清理字典映射")
            console_widget = self.consoles.pop(console_id, None)
            if console_widget:
                console_widget.kernel_manager.shutdown_kernel()
                console_widget.close()
                console_widget.deleteLater()
            return False

    def execute_code(self, code, hidden=False, console_id=None):
        target = self._get_console_by_id_or_current(console_id)
        if target:
            target.execute_code(code, hidden)

    def interrupt_kernel(self, console_id=None):
        target = self._get_console_by_id_or_current(console_id)
        return target.interrupt_kernel() if target else False

    def start_kernel(self, python_exe, console_id=None):
        target = self._get_console_by_id_or_current(console_id)
        if target:
            target.start_kernel(python_exe)

    def restart_kernel(self, console_id=None):
        target = self._get_console_by_id_or_current(console_id)
        if target:
            target.restart_kernel()

    def stop_kernel(self, console_id=None):
        target = self._get_console_by_id_or_current(console_id)
        if target:
            target.stop_kernel()

    def get_kernel_manager(self, console_id=None):
        target = self._get_console_by_id_or_current(console_id)
        return target.get_kernel_manager() if target else None