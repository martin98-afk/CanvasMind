import sys
import os
import tempfile

from PyQt5.QtWidgets import QHBoxLayout, QLabel
from qtpy.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QStackedWidget
)
from qtpy.QtCore import Signal
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.manager import QtKernelManager

# 需要安装 qfluentwidgets: pip install qfluentwidgets
from qfluentwidgets import TabBar, ComboBox


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


# --- 2. 环境选择器 (EnvSelector) ---
class EnvironmentSelector(QWidget):
    env_changed = Signal(str)

    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        # 减少布局间距
        self.layout.setSpacing(2)  # 设置间距为2像素，可以根据需要调整
        self.layout.setContentsMargins(0, 0, 0, 0)  # 减少边距

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


# --- 3. 集成环境选择器的 IPython 控制台 (EmbeddedIPythonConsoleWithEnv) ---
class EmbeddedIPythonConsole(QWidget):
    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        # 减少布局间距
        self.layout.setSpacing(2)  # 设置间距为2像素
        self.layout.setContentsMargins(0, 0, 0, 0)  # 减少边距

        # 创建环境选择器
        env_widget = QWidget(self)
        env_layout = QHBoxLayout(env_widget)
        title_label = QLabel("Console 环境选择: ")
        title_label.setStyleSheet("font: 12px 'Segoe UI', 'Microsoft YaHei', 'PingFang SC';color: white;")
        env_layout.addWidget(title_label)
        self.env_selector = EnvironmentSelector(parent=self, package_manager=package_manager)
        env_layout.addWidget(self.env_selector, stretch=1)
        self.layout.addWidget(env_widget)

        # 创建控制台主体
        self.console = RichJupyterWidget(parent=self)
        # 在创建实例时就设置深色主题
        self.console.set_default_style(colors='linux')
        self.console.banner = "IPython Console (Embedded - Dynamic Env)\n"
        self.layout.addWidget(self.console)

        # 初始化 kernel 相关变量
        self.kernel_manager = None
        self.kernel_client = None

        # 连接环境选择器信号
        self.env_selector.env_changed.connect(self.start_kernel)

    def start_kernel(self):
        """
        启动或重启一个基于指定 python_exe 的 kernel。
        """
        python_exe = self.env_selector.get_current_python_exe()
        if not python_exe:
            print("错误：无法获取当前 Python 解释器路径！")
            return

        if not os.path.exists(python_exe):
            print(f"错误：Python 解释器路径不存在: {python_exe}")
            return

        # 先关闭旧的 kernel（如果存在）
        self.shutdown_kernel()

        try:
            # 创建临时连接文件
            import uuid
            connection_file = os.path.join(tempfile.gettempdir(), f'kernel_{uuid.uuid4().hex}.json')

            # 准备环境变量 - 完全替换环境以确保使用目标环境
            env = os.environ.copy()
            python_dir = os.path.dirname(python_exe)
            env_python_path = os.path.join(os.path.dirname(python_exe), "Lib", "site-packages")

            # 设置环境变量确保使用正确的 Python 环境
            env['PATH'] = python_dir + os.pathsep + env.get('PATH', '')
            # 完全替换 PYTHONPATH，只使用目标环境的路径
            env['PYTHONPATH'] = env_python_path
            env['PYTHONEXECUTABLE'] = python_exe

            # 移除可能影响的其他环境变量
            env.pop('PYTHONHOME', None)

            # 创建 QtKernelManager
            self.kernel_manager = QtKernelManager(connection_file=connection_file)

            # 启动 kernel
            self.kernel_manager.start_kernel(
                executable=python_exe,
                env=env
            )

            # 获取 client
            self.kernel_client = self.kernel_manager.client()
            self.kernel_client.start_channels()

            # 绑定到 console
            self.console.kernel_manager = self.kernel_manager
            self.console.kernel_client = self.kernel_client

            # kernel 启动后，再次强制应用深色主题
            # 这可能有助于确保样式在 kernel 完全加载后生效
            self.console.set_default_style(colors='linux')

        except Exception as e:
            print(f"启动 kernel 失败: {e}")
            import traceback
            traceback.print_exc()

    def shutdown_kernel(self):
        """关闭当前 kernel"""
        if self.kernel_client:
            try:
                self.kernel_client.stop_channels()
            except Exception:
                pass  # 可能已经断开
        if self.kernel_manager:
            try:
                self.kernel_manager.shutdown_kernel(now=True)
            except Exception:
                pass  # 可能已经关闭
        self.kernel_client = None
        self.kernel_manager = None

    def closeEvent(self, event):
        self.shutdown_kernel()
        super().closeEvent(event)

    def execute(self, code: str):
        """从外部执行代码"""
        if self.kernel_client:
            self.console.execute(code)
        else:
            print("Kernel 未启动，请先启动环境。")

    def get_current_env_name(self):
        """获取当前选择的环境名称"""
        return self.env_selector.combo.currentText()


# --- 4. IPython 控制台管理器 (IPythonConsoleManager) ---
class IPythonConsoleManager(QWidget):
    def __init__(self, parent=None, package_manager=None):
        super().__init__(parent)
        self.package_manager = package_manager
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)  # 减少边距

        # 使用 qfluentwidgets 的 TabBar 和 Qt 的 QStackedWidget
        self.tab_bar = TabBar()
        self.tab_bar.setScrollable(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.setTabMaximumWidth(150)
        self.stacked_widget = QStackedWidget()

        # TabBar 添加按钮
        self.tab_bar.setMovable(True)
        self.tab_bar.setAddButtonVisible(True)  # 显示 "+" 添加按钮

        # 布局
        self.layout.addWidget(self.tab_bar)
        self.layout.addWidget(self.stacked_widget)

        # 连接信号
        self.tab_bar.tabAddRequested.connect(self.add_new_console_tab)
        self.tab_bar.tabCloseRequested.connect(self.close_console_tab)
        self.tab_bar.currentChanged.connect(self.stacked_widget.setCurrentIndex)

        self.add_new_console_tab()

    def add_new_console_tab(self):
        console_widget = EmbeddedIPythonConsole(
            parent=self.stacked_widget, package_manager=self.package_manager
        )
        console_widget.start_kernel()
        initial_env = console_widget.get_current_env_name()
        tab_title = f"Console ({initial_env})" if initial_env else "Console"

        # 添加到 StackedWidget 和 TabBar
        index = self.stacked_widget.addWidget(console_widget)
        self.tab_bar.addTab(
            routeKey=str(index),  # 使用索引作为路由键
            text=tab_title,
            icon=None  # 可以设置图标
        )

        # 选中新建的标签页
        self.tab_bar.setCurrentIndex(index)
        self.stacked_widget.setCurrentIndex(index)
        # 连接环境改变信号更新标签标题
        console_widget.env_selector.env_changed.connect(
            lambda path, idx=index: self.update_tab_title(idx)
        )

    def update_tab_title(self, index):
        """根据指定索引的控制台当前环境更新标签页标题"""
        console_widget = self.stacked_widget.widget(index)
        if isinstance(console_widget, EmbeddedIPythonConsole):
            env_name = console_widget.get_current_env_name()
            self.tab_bar.setTabText(index, f"Console ({env_name})")

    def close_console_tab(self, index):
        """关闭指定索引的控制台标签页"""
        console_widget = self.stacked_widget.widget(index)
        if console_widget:
            console_widget.close()
            self.stacked_widget.removeWidget(console_widget)
            self.tab_bar.removeTab(index)

            # 如果关闭的是当前页，尝试切换到其他页
            if self.tab_bar.currentIndex() == -1 and self.tab_bar.count() > 0:
                # 选择下一个或上一个标签
                new_index = min(index, self.tab_bar.count() - 1)
                self.tab_bar.setCurrentIndex(new_index)

    # --- 新增：获取当前活动的控制台 ---
    def get_current_console(self):
        """获取当前活动的 EmbeddedIPythonConsole 实例"""
        current_index = self.stacked_widget.currentIndex()
        if current_index >= 0:
            return self.stacked_widget.widget(current_index)
        return None
    # --- 新增结束 ---


# --- 5. 主窗口 (DemoWindow) ---
class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-Console IPython Demo")
        self.resize(1000, 700)

        self.package_manager = MockPackageManager()

        self.console_manager = IPythonConsoleManager(
            parent=self, package_manager=self.package_manager
        )

        self.setCentralWidget(self.console_manager)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec())