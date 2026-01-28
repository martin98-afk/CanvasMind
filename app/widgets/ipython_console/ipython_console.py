import uuid

from PyQt5 import QtCore
from loguru import logger
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QStackedWidget
)
from qfluentwidgets import TabBar, ComboBox, CommandBar, Action, FluentIcon, TabCloseButtonDisplayMode
from qtconsole.rich_jupyter_widget import RichJupyterWidget

from app.server_manager.ipython_server.ipython_kernel_manager import IPythonKernelManager, LocalConnectWorker
from app.server_manager.ipython_server.remote_ipython_kernel import RemoteIPythonKernelManager, RemoteConnectWorker
from app.utils.utils import get_icon


class EnvironmentSelector(QWidget):
    """环境选择器：支持本地和 SSH 环境"""
    env_changed = pyqtSignal(dict)  # 改为发送字典

    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.combo = ComboBox()
        self.package_manager = package_manager
        self._env_list = []  # 缓存环境数据

        self.combo.currentTextChanged.connect(self.on_environment_changed)
        self.load_envs()
        self.layout.addWidget(self.combo)

    def load_envs(self):
        if self.package_manager:
            self._env_list = self.package_manager.get_all_environments()
            # 显示名称，如果为 ssh 类型，标注一下
            display_names = [
                f"[{e['type'].upper()}] {e['name']}" for e in self._env_list
            ]
            self.combo.addItems(display_names)

    def on_environment_changed(self, text):
        index = self.combo.currentIndex()
        if 0 <= index < len(self._env_list):
            env_data = self._env_list[index]
            self.env_changed.emit(env_data)

    def get_current_env_data(self):
        index = self.combo.currentIndex()
        if 0 <= index < len(self._env_list):
            return self._env_list[index]
        return None


class EmbeddedIPythonConsole(QWidget):
    """嵌入式IPython控制台GUI组件 - 支持本地/远程双内核管理器"""

    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.package_manager = package_manager
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 1. 初始化内核管理器
        self.local_km = IPythonKernelManager()
        self.remote_km = RemoteIPythonKernelManager()
        self.current_km = None  # 追踪当前正在使用的内核

        # 2. 构建命令栏 (CommandBar)
        commandBar = CommandBar()
        if package_manager is not None:
            title_label = QLabel(" 环境选择: ")
            title_label.setStyleSheet("font: 12px 'Segoe UI', 'Microsoft YaHei'; color: white;")
            commandBar.addWidget(title_label)
            self.env_selector = EnvironmentSelector(parent=self, package_manager=package_manager)
            commandBar.addWidget(self.env_selector)
            commandBar.addSeparator()
            # 绑定环境切换信号
            self.env_selector.env_changed.connect(self.start_kernel)

        # 调用 add_common_tools (报错的地方)
        self.add_common_tools(commandBar)
        self.layout.addWidget(commandBar)

        # 3. 控制台
        self.console = RichJupyterWidget()
        self.console.setStyleSheet("background-color: transparent;")
        self.console.set_default_style(colors='linux')
        self.console.banner = "IPython Console (Ready)\n"
        self.layout.addWidget(self.console)

        # 4. 尝试启动默认环境
        if self.env_selector:
            initial_env = self.env_selector.get_current_env_data()
            if initial_env:
                self.start_kernel(initial_env)

    @property
    def kernel_manager(self):
        """返回当前正在使用的内核管理器"""
        return self.current_km

    def add_common_tools(self, commandBar):
        """添加常用工具按钮 - 确保这个方法在类定义内"""
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

    def start_kernel(self, env_data: dict):
        """启动内核"""
        self.stop_kernel()  # 先停止旧的

        # 1. 禁用界面组件，防止重复点击
        self.env_selector.setEnabled(False)
        env_type = env_data.get('type', 'local')
        self.env_selector.combo.setCurrentText(env_data['name'])
        success = False

        if env_type == 'ssh':
            self.console._append_plain_text(f"[*] 正在通过 SSH 连接远程内核: {env_data['host']}...\n")
            self.console._append_plain_text("[*] 准备建立异步连接...\n")

            # 2. 启动后台线程
            self.conn_worker = RemoteConnectWorker(self.remote_km, env_data)
            self.current_km = self.remote_km
        else:
            self.console._append_plain_text(f"[*] 正在启动本地环境: {env_data['name']}...\n")
            python_path = env_data['path'] if isinstance(env_data, dict) else env_data

            self.conn_worker = LocalConnectWorker(self.local_km, python_path)
            self.current_km = self.local_km

            # 绑定通用信号
        self.conn_worker.status_update.connect(lambda msg: self.console._append_plain_text(f"{msg}\n"))
        self.conn_worker.finished.connect(self._on_kernel_started_done)
        self.conn_worker.start()

    def _on_kernel_started_done(self, success, error_msg):
        """连接结束的回调 (本地/远程通用)"""
        self.env_selector.setEnabled(True)

        if success:
            # 绑定控制台组件到当前活跃的管理器
            self.console.kernel_manager = self.current_km.kernel_manager
            self.console.kernel_client = self.current_km.kernel_client

            mode = "远程" if self.current_km == self.remote_km else "本地"
            self.console._append_plain_text(f"[+] {mode}内核连接成功！\n")
        else:
            self.console._append_plain_text(f"[-] 连接失败: {error_msg}\n")
            self.current_km = None

    def restart_kernel(self):
        env_data = self.env_selector.get_current_env_data()
        if env_data: self.start_kernel(env_data)

    def stop_kernel(self):
        # 停止所有可能的残留内核
        if self.local_km.is_alive(): self.local_km.shutdown_kernel()
        if hasattr(self.remote_km, 'shutdown_kernel'): self.remote_km.shutdown_kernel()
        self.current_km = None

    def execute_code(self, code, hidden=False):
        if self.current_km: self.console.execute(code, hidden)

    def interrupt_kernel(self):
        return self.current_km.interrupt_kernel() if self.current_km else False

    def get_kernel_manager(self):
        return self.current_km


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

    def set_var_explorer(self):
        kernel_manager = self.get_current_kernel_manager()
        if kernel_manager and self.var_explorer:
            self.var_explorer.stop_auto_refresh()
            self.var_explorer.set_kernel_manager(kernel_manager)
            self.var_explorer.start_auto_refresh()

    def add_new_console_tab(self, env_name=None, tab_name=None, closable=True):
        """创建新控制台标签"""
        console_id = str(uuid.uuid4())
        # 创建 widget 时，其内部会根据 selector 默认值启动一次 start_kernel
        console_widget = EmbeddedIPythonConsole(
            parent=self.stacked_widget, package_manager=self.package_manager
        )
        self.consoles[console_id] = console_widget

        # 如果指定了环境名称，需要手动切换 selector 的当前项
        if env_name:
            for i in range(console_widget.env_selector.combo.count()):
                # 这里根据包含关系判断，因为显示文本可能有 [SSH] 前缀
                if env_name in console_widget.env_selector.combo.itemText(i):
                    console_widget.env_selector.combo.setCurrentIndex(i)
                    break

        # 获取当前选中的环境信息用于显示标题
        current_env = console_widget.env_selector.get_current_env_data()
        env_display = current_env['name'] if current_env else "Unknown"
        tab_title = tab_name if tab_name else f"Console ({env_display})"

        index = self.stacked_widget.addWidget(console_widget)
        tab = self.tab_bar.addTab(routeKey=console_id, text=tab_title)

        if not closable:
            tab.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)

        self.tab_bar.setCurrentIndex(index)
        self.stacked_widget.setCurrentIndex(index)
        self.set_var_explorer()
        return console_id

    def on_tab_changed(self, index):
        """标签切换时更新变量浏览器"""
        self.stacked_widget.setCurrentIndex(index)
        # 延迟一下更新，确保 kernel 已经 start
        self.set_var_explorer()

    def get_current_kernel_manager(self):
        console = self.get_current_console()
        # 这里返回的是活跃的 km (可能是 local 也可能是 remote)
        return console.get_kernel_manager() if console else None

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

    def start_kernel(self, python_exe, env_name, console_id=None):
        target = self._get_console_by_id_or_current(console_id)
        if target:
            target.env_selector.combo.setCurrentText(env_name)
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