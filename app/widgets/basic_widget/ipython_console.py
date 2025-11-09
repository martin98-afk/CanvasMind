import json
import os
import sys
import tempfile
import uuid
from base64 import b64encode
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSplitter, QPushButton, QVBoxLayout, QWidget
from qtconsole.manager import QtKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget
)
from qfluentwidgets import TabBar, ComboBox, CommandBar, Action, FluentIcon
from spyder.widgets.collectionseditor import CollectionsEditorWidget

TEMP_DIR = tempfile.gettempdir()


# --- 1. 环境管理器模拟 (Mock) ---
class MockPackageManagerManager:
    def list_envs(self):
        return ["3.14"]

    def get_python_exe(self, env_name):
        if env_name == "env39":
            path = sys.executable.replace("python.exe", "envs/env39/python.exe")
        elif env_name == "env310":
            path = sys.executable.replace("python.exe", "envs/env310/python.exe")
        elif env_name == "env311":
            path = sys.executable.replace("python.exe", "envs/env311/python.exe")
        elif env_name == "3.14":
            path = r"D:\work\CanvasMind\envs\miniconda\envs\3.14\python.exe"
        else:  # base
            path = sys.executable
        return path


class MockPackageManager:
    def __init__(self):
        self.mgr = MockPackageManagerManager()


# --- 2. 环境选择器 ---
class EnvironmentSelector(QWidget):
    env_changed = Signal(str)

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


# --- 3. 优化的变量浏览器 ---
class SpyderCollectionsVariableExplorer(QWidget):
    def __init__(self, parent=None, console_manager=None):
        super().__init__(parent)
        self.console_manager = console_manager
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 深色 QSS
        dark_qss = """
        CollectionsEditorTableView {
            background-color: #19232D;
            color: #FFFFFF;
            alternate-background-color: #1A2029;
            gridline-color: #32414B;
            selection-background-color: #3D5DAE;
            selection-color: #FFFFFF;
        }
        QDialog, QWidget {
            background-color: #19232D;
            color: #FFFFFF;
        }
        QHeaderView::section {
            background-color: #262F3A;
            color: #FFFFFF;
            padding: 4px;
            border: 1px solid #32414B;
        }
        QTableView::item {
            padding: 4px;
        }
        """

        # 初始空数据
        self.collection_widget = CollectionsEditorWidget(self, data={})
        self.collection_widget.setStyleSheet(dark_qss)
        self.layout.addWidget(self.collection_widget)

        # 自动刷新定时器
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_variables)
        self.auto_refresh_timer.setInterval(500)  # 每秒刷新一次
        self.auto_refresh_timer.start()

    def get_current_console(self):
        """获取当前活动的console"""
        if self.console_manager:
            return self.console_manager.get_current_console()
        return None

    def refresh_variables(self):
        current_console = self.get_current_console()
        if not current_console or not current_console.kernel_client:
            return

        # 生成临时文件路径
        self._temp_file = os.path.join(TEMP_DIR, f"spyder_vars_{uuid.uuid4().hex}.json")

        # 执行代码：将变量写入临时文件（使用safe_repr保持类型信息）
        code = f'''
import json
import os
_snapshot = {{k: v for k, v in globals().items() if not k.startswith('_') and not callable(v) and not isinstance(v, type) and not hasattr(v, '__module__')}}

def safe_repr(obj, max_len=1000):
    """安全的repr函数，避免pickle问题"""
    try:
        # 检查是否是基本类型或可序列化类型
        if isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        elif isinstance(obj, (list, tuple)):
            if len(obj) > 100:  # 限制长度
                return f"<{{type(obj).__name__}} of length {{len(obj)}}>"
            return [safe_repr(item, max_len) for item in obj[:100]]
        elif isinstance(obj, dict):
            if len(obj) > 100:  # 限制长度
                return f"<dict of length {{len(obj)}}>"
            return {{k: safe_repr(v, max_len) for k, v in list(obj.items())[:100]}}
        elif isinstance(obj, (set, frozenset)):
            return f"<{{type(obj).__name__}} of length {{len(obj)}}>"
        else:
            # 对于其他类型，返回类型信息和字符串表示
            return f"<{{type(obj).__name__}}: {{str(obj)[:max_len]}}>"
    except:
        return f"<unrepresentable: {{type(obj).__name__}}>"

_vars = {{k: safe_repr(v) for k, v in _snapshot.items()}}
with open(r"{self._temp_file}", "w", encoding="utf-8") as f:
    json.dump(_vars, f, ensure_ascii=False, indent=2)
print("变量已导出")
'''
        current_console.console.execute(code, hidden=True)
        QTimer.singleShot(200, self._load_from_temp)

    def _load_from_temp(self):
        try:
            if hasattr(self, '_temp_file') and os.path.exists(self._temp_file):
                with open(self._temp_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                os.remove(self._temp_file)

                # 设置数据到变量浏览器
                self.collection_widget.set_data(data)
            else:
                print("临时文件不存在")
        except Exception as e:
            print(f"加载变量失败: {e}")


# --- 4. 嵌入式 Console + TabBar ---
class IPythonConsoleWithTabBar(QWidget):
    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.package_manager = package_manager
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Console 管理器（多标签）
        self.console_manager = IPythonConsoleManager(
            parent=self, package_manager=self.package_manager
        )
        self.layout.addWidget(self.console_manager)

    def get_current_console(self):
        return self.console_manager.get_current_console()


# --- 5. Console 管理器（多标签） ---
class IPythonConsoleManager(QWidget):
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
        """标签切换时更新变量浏览器"""
        self.stacked_widget.setCurrentIndex(index)
        # 通知主窗口更新变量浏览器的console引用
        if hasattr(self.parent().parent(), 'var_explorer'):
            # 刷新变量以显示当前控制台的变量
            QTimer.singleShot(100, self.parent().parent().var_explorer.refresh_variables)

    def add_new_console_tab(self):
        console_widget = EmbeddedIPythonConsole(
            parent=self.stacked_widget, package_manager=self.package_manager
        )
        console_widget.start_kernel()
        initial_env = console_widget.get_current_env_name()
        tab_title = f"Console ({initial_env})" if initial_env else "Console"

        index = self.stacked_widget.addWidget(console_widget)
        self.tab_bar.addTab(routeKey=str(index), text=tab_title)
        self.tab_bar.setCurrentIndex(index)
        self.stacked_widget.setCurrentIndex(index)
        console_widget.env_selector.env_changed.connect(
            lambda path, idx=index: self.update_tab_title(idx)
        )

    def update_tab_title(self, index):
        console_widget = self.stacked_widget.widget(index)
        if isinstance(console_widget, EmbeddedIPythonConsole):
            env_name = console_widget.get_current_env_name()
            self.tab_bar.setTabText(index, f"Console ({env_name})")

    def close_console_tab(self, index):
        console_widget = self.stacked_widget.widget(index)
        if console_widget:
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


# --- 6. 嵌入式 Console ---
class EmbeddedIPythonConsole(QWidget):
    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        commandBar = CommandBar()
        # 环境选择器
        title_label = QLabel("环境选择: ")
        title_label.setStyleSheet("font: 12px 'Segoe UI', 'Microsoft YaHei'; color: white;")
        commandBar.addWidget(title_label)
        self.env_selector = EnvironmentSelector(parent=self, package_manager=package_manager)
        commandBar.addWidget(self.env_selector)
        # 添加常用工具按钮
        self.add_common_tools(commandBar)

        self.layout.addWidget(commandBar)

        # Console
        self.console = RichJupyterWidget()
        self.console.set_default_style(colors='linux')
        self.console.banner = "IPython Console (Embedded)\n"

        self.layout.addWidget(self.console)

        # Kernel
        self.kernel_manager = None
        self.kernel_client = None
        self.env_selector.env_changed.connect(self.start_kernel)

    def add_common_tools(self, commandBar):
        """添加常用的IPython工具操作按钮"""
        # 添加分隔符
        commandBar.addSeparator()
        restart_action = Action(FluentIcon.SYNC, "重新运行Console", self)
        restart_action.triggered.connect(self.restart_kernel)
        commandBar.addAction(restart_action)
        # 添加常用功能
        whos_action = Action(FluentIcon.VIEW, "whos", self)
        whos_action.triggered.connect(lambda: self.execute_code("%whos"))
        commandBar.addAction(whos_action)

        reset_action = Action(FluentIcon.ROTATE, "reset", self)
        reset_action.triggered.connect(lambda: self.execute_code("%reset -f"))
        commandBar.addAction(reset_action)

        # 添加分隔符
        commandBar.addSeparator()

        # 添加路径相关功能
        pwd_action = Action(FluentIcon.FOLDER, "pwd", self)
        pwd_action.triggered.connect(lambda: self.execute_code("%pwd"))
        commandBar.addAction(pwd_action)

        ls_action = Action(FluentIcon.FOLDER, "ls", self)
        ls_action.triggered.connect(lambda: self.execute_code("%ls"))
        commandBar.addAction(ls_action)

        # 添加分隔符
        commandBar.addSeparator()

        # 添加变量查看功能
        globals_action = Action(FluentIcon.ZOOM, "查看 globals", self)
        globals_action.triggered.connect(lambda: self.execute_code("globals()"))
        commandBar.addAction(globals_action)

    def restart_kernel(self):
        """重新启动Kernel"""
        print("正在重新启动 Kernel...")
        self.start_kernel()

    def execute_code(self, code):
        """执行代码到当前console"""
        if self.kernel_client:
            self.console.execute(code)
        else:
            print("Kernel 未启动，请先启动环境。")

    def start_kernel(self):
        python_exe = self.env_selector.get_current_python_exe()
        if not python_exe:
            print("错误：无法获取当前 Python 解释器路径！")
            return
        if not os.path.exists(python_exe):
            print(f"错误：Python 解释器路径不存在: {python_exe}")
            return

        self.shutdown_kernel()

        try:
            import uuid
            connection_file = os.path.join(tempfile.gettempdir(), f'kernel_{uuid.uuid4().hex}.json')
            env = os.environ.copy()
            python_dir = os.path.dirname(python_exe)
            env_python_path = os.path.join(python_dir, "Lib", "site-packages")
            env['PATH'] = python_dir + os.pathsep + env.get('PATH', '')
            env['PYTHONPATH'] = env_python_path
            env['PYTHONEXECUTABLE'] = python_exe
            env.pop('PYTHONHOME', None)

            self.kernel_manager = QtKernelManager(connection_file=connection_file)
            self.kernel_manager.start_kernel(executable=python_exe, env=env)
            self.kernel_client = self.kernel_manager.client()
            self.kernel_client.start_channels()

            self.console.kernel_manager = self.kernel_manager
            self.console.kernel_client = self.kernel_client
            self.console.set_default_style(colors='linux')

        except Exception as e:
            print(f"启动 kernel 失败: {e}")
            import traceback
            traceback.print_exc()

    def shutdown_kernel(self):
        if self.kernel_client:
            try:
                self.kernel_client.stop_channels()
            except Exception:
                pass
        if self.kernel_manager:
            try:
                self.kernel_manager.shutdown_kernel(now=True)
            except Exception:
                pass
        self.kernel_client = None
        self.kernel_manager = None

    def closeEvent(self, event):
        self.shutdown_kernel()
        super().closeEvent(event)

    def execute(self, code: str):
        if self.kernel_client:
            self.console.execute(code)
        else:
            print("Kernel 未启动，请先启动环境。")

    def get_current_env_name(self):
        return self.env_selector.combo.currentText()


# --- 7. 主窗口 ---
class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPython Console + 变量浏览器")
        self.resize(1000, 700)

        self.package_manager = MockPackageManager()

        # 创建中央部件
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)

        # 创建Console管理器
        self.console_manager = IPythonConsoleWithTabBar(
            parent=self, package_manager=self.package_manager
        )

        # 创建变量浏览器，传入console管理器引用
        self.var_explorer = SpyderCollectionsVariableExplorer(
            parent=self, console_manager=self.console_manager.console_manager
        )

        # 创建垂直分割器
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.var_explorer)
        splitter.addWidget(self.console_manager)
        splitter.setSizes([300, 400])  # 变量浏览器较小，控制台较大

        central_layout.addWidget(splitter)
        self.setCentralWidget(central_widget)


# --- 启动 ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec())