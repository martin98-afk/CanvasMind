import base64
import os
import pickle
import sys
import tempfile
import uuid

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget
from loguru import logger
from qfluentwidgets import TabBar, ComboBox, CommandBar, Action, FluentIcon
from qtconsole.manager import QtKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget
# 强制 PyInstaller 包含这些模块
from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget
)
from spyder.plugins.variableexplorer.widgets.namespacebrowser import NamespaceBrowser
from spyder.widgets.collectionseditor import CollectionsEditorWidget

from app.utils.utils import get_icon

TEMP_DIR = tempfile.gettempdir()


# --- 1. 环境管理器模拟 (Mock) ---
class MockPackageManagerManager:
    def list_envs(self):
        return ["3.14"]

    def get_python_exe(self, env_name):
        if env_name == "3.14":
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
        self.collection_widget = CollectionsEditorWidget(
            self, data={}, namespacebrowser=NamespaceBrowser(self)
        )
        self.collection_widget.setStyleSheet(dark_qss)
        self.layout.addWidget(self.collection_widget)

        # 存储上次变量快照，用于检测变化
        self._last_snapshot_hash = None
        self._last_variables = {}

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_variables)
        self.auto_refresh_timer.setInterval(1000)  # 增加到1秒，减少刷新频率

        # 改为延迟启动：比如等第一个 console 准备好后再启动
        QTimer.singleShot(3000, self._maybe_start_timer)  # 延迟3秒尝试启动

    def _maybe_start_timer(self):
        """尝试启动定时器，仅当已有有效 kernel"""
        if self._has_active_kernel():
            self.auto_refresh_timer.start()
        else:
            # 如果还没准备好，再试一次（最多重试几次）
            QTimer.singleShot(1000, self._maybe_start_timer)

    def _has_active_kernel(self):
        current_console = self.get_current_console()
        return current_console is not None and current_console.kernel_client is not None

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
        self._temp_file = os.path.join(TEMP_DIR, f"spyder_vars_{uuid.uuid4().hex}.pkl")

        # 执行代码：获取变量并序列化到临时文件
        code = f'''
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os

from PIL import Image
from collections import OrderedDict

# 获取所有非内置、非函数、非类型的变量，并且可序列化
_snapshot = OrderedDict()
locals = globals().copy()
for _k, _v in locals.items():
    if (not _k.startswith('_') and 
            not callable(_v) and 
            not isinstance(_v, type) and (
            # 基础类型
            _v is None or
            isinstance(_v, (bool, int, float, complex, str, bytes)) or
            # 容器（递归检查交给 pickle，这里只看顶层类型）
            isinstance(_v, (list, tuple, set, frozenset, dict)) or
            # NumPy
            isinstance(_v, (np.ndarray, np.generic)) or
            # Pandas
            isinstance(_v, (pd.DataFrame, pd.Series)) or
            # Image
            isinstance(_v, Image.Image) or
            # Matplotlib
            isinstance(_v, (plt.Figure, plt.Axes)) or
            # 忽略文件
            isinstance(_v, (os.PathLike, os.DirEntry))
        )):
        try:
            pickle.dumps(_v, protocol=pickle.HIGHEST_PROTOCOL)
            _snapshot[_k] = _v
        except Exception as e:
            pass
        
# 保存到临时文件
with open(r"{self._temp_file}", "wb") as f:
    pickle.dump(_snapshot, f)

print("变量快照已保存")
'''
        current_console.console.execute(code, hidden=True)
        QTimer.singleShot(300, self._load_from_temp)

    def _load_from_temp(self):
        try:
            if hasattr(self, '_temp_file') and os.path.exists(self._temp_file):
                with open(self._temp_file, 'rb') as f:
                    data = pickle.load(f)
                os.remove(self._temp_file)

                # 检查数据是否有变化，避免不必要的刷新
                # 创建一个简化的哈希用于比较
                def safe_hashable_repr(value):
                    """尝试生成一个可用于哈希的稳定表示"""
                    try:
                        # 尝试 pickle（最通用，能处理 numpy、pandas 等）
                        return base64.b64encode(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)).decode('utf-8')
                    except Exception:
                        # 如果不可 pickle，回退到类型+id（避免崩溃）
                        return f"{type(value)}@{id(value)}"

                current_hash_data = {k: safe_hashable_repr(v) for k, v in data.items()}
                current_data_hash = hash(str(sorted(current_hash_data.items())))

                if current_data_hash == self._last_snapshot_hash:
                    # 数据没有变化，不刷新
                    return

                self._last_snapshot_hash = current_data_hash
                self._last_variables = data

                # 直接设置原始数据到变量浏览器
                self.collection_widget.set_data(data)
            else:
                logger.error("临时文件不存在")
        except Exception as e:
            logger.error(f"加载变量失败: {e}")

    def refresh_variables_manually(self):
        """手动刷新变量"""
        self.refresh_variables()


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
        self.tab_bar.addTab(routeKey=str(uuid.uuid4()), text=tab_title)
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
        restart_action = Action(get_icon("远程重启"), "重新运行Console", self)
        restart_action.triggered.connect(self.restart_kernel)
        commandBar.addAction(restart_action)

        # 添加常用功能
        clear_action = Action(get_icon("清空参数"), "清空画面", self)
        clear_action.triggered.connect(lambda: self.execute_code("%clear"))
        commandBar.addAction(clear_action)

        reset_action = Action(get_icon("删除变量"), "重置变量", self)
        reset_action.triggered.connect(lambda: self.execute_code("%reset -f"))
        commandBar.addAction(reset_action)

        # 添加分隔符
        commandBar.addSeparator()

        # 添加常用功能
        whos_action = Action(FluentIcon.VIEW, "whos", self)
        whos_action.triggered.connect(lambda: self.execute_code("%whos"))
        commandBar.addAction(whos_action)

        # 添加路径相关功能
        pwd_action = Action(FluentIcon.FOLDER, "pwd", self)
        pwd_action.triggered.connect(lambda: self.execute_code("%pwd"))
        commandBar.addAction(pwd_action)

        ls_action = Action(get_icon("ls"), "ls", self)
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
            logger.error(f"启动 kernel 失败: {e}")
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