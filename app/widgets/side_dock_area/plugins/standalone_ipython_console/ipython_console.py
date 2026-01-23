from PyQt5.QtWidgets import QVBoxLayout
from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.widgets.ipython_console.ipython_console import IPythonConsoleManager


class IPythonConsoleToolWindow(ToolWindow):
    name = "IPython 控制台"
    icon = get_icon("ipython")
    singleton = True
    default_position = DockPosition.BOTTOM

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 使用管理器替换原有单体 Console
        # 注意：这里传入 package_manager 和 var_explorer（根据你之前的定义）
        self.console = IPythonConsoleManager(
            parent=self,
            package_manager=self.homepage.parent.package_manager,
            init_console=False    # 禁用初始化，画布统一由 主界面控制创建主控制台
        )
        # 用于记录：{workflow_path_or_id: console_id}
        self._main_console_mapping = {}
        layout.addWidget(self.console)

    def get_or_create_main_console(self, workflow_id, env_name, name="Main"):
        """
        获取或创建指定工作流的主进程 ID。
        如果该工作流已经有关联的 ID，直接返回；否则新建一个。
        """
        if workflow_id in self._main_console_mapping:
            cid = self._main_console_mapping[workflow_id]
            # 检查该 console 是否还存在（防止用户手动关掉了 Tab）
            if self.console._get_console_by_id_or_current(cid):
                return cid

        # 创建新的主进程控制台
        new_id = self.add_console(env_name=env_name, tab_name=name, closable=False)
        self._main_console_mapping[workflow_id] = new_id
        return new_id

    def get_main_id_for_workflow(self, workflow_id):
        """仅查询，不创建"""
        return self._main_console_mapping.get(workflow_id)

    @property
    def kernel_manager(self):
        """兼容旧逻辑：返回当前激活 Tab 的内核管理器"""
        return self.console.get_kernel_manager()

    def get_kernel_manager_by_id(self, console_id=None):
        """新逻辑：通过 ID 获取特定内核管理器"""
        return self.console.get_kernel_manager(console_id=console_id)

    def interrupt_kernel(self, console_id=None):
        """中断内核：支持 ID 路由"""
        return self.console.interrupt_kernel(console_id=console_id)

    def start_kernel(self, python_exe: str, env_name: str, console_id=None):
        """启动内核：支持 ID 路由"""
        # 注意：如果 Manager 内部 start_kernel 需要 path，确保 Manager 已实现该转发
        return self.console.start_kernel(python_exe, env_name, console_id=console_id)

    def stop_kernel(self, console_id=None):
        """停止内核：支持 ID 路由"""
        self.console.stop_kernel(console_id=console_id)

    def restart_kernel(self, console_id=None):
        """重启内核：支持 ID 路由"""
        self.console.restart_kernel(console_id=console_id)

    def execute_code(self, code: str, hidden: bool = False, console_id=None):
        """执行代码：支持 ID 路由"""
        self.console.execute_code(code, hidden, console_id=console_id)

    def set_focus(self, console_id=None):
        """设置焦点"""
        target = self.console._get_target_console(console_id)
        if target:
            target.console.setFocus()
        else:
            self.console.setFocus()

    # --- 针对多控制台的新增快捷方法 ---

    def add_console(self, env_name=None, tab_name=None, closable=True):
        """手动添加一个新控制台并返回其 ID"""
        return self.console.add_new_console_tab(env_name=env_name, tab_name=tab_name, closable=closable)

    def close_console_by_id(self, console_id):
        """供外部调用的关闭接口"""
        return self.console.close_console_by_id(console_id)