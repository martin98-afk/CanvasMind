import functools
import json
import re
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal, QProcess, Qt, QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTextEdit,
    QInputDialog, QTableWidgetItem, QSplitter, QPushButton, QHeaderView, QSizePolicy, QLabel
)
from qfluentwidgets import (
    ComboBox, PrimaryPushButton, LineEdit, TableWidget,
    FluentIcon, InfoBar, SearchLineEdit, TextEdit, PushButton, MessageBox, BodyLabel
)

from app.utils.env_operation import EnvironmentManager


class PackageSummaryThread(QThread):
    """异步获取包摘要信息的线程"""
    summary_ready = pyqtSignal(str, str)  # package_name, summary
    error_occurred = pyqtSignal(str, str)  # package_name, error

    def __init__(self, python_exe, package_name):
        super().__init__()
        self.python_exe = python_exe
        self.package_name = package_name
        self._is_terminated = False

    def terminate(self):
        self._is_terminated = True
        super().terminate()

    def run(self):
        if self._is_terminated:
            return

        try:
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "show", self.package_name],
                capture_output=True,
                text=True,
                check=True,
                timeout=10  # 设置超时时间，避免长时间等待
            )
            output = result.stdout.strip()
            summary = ""
            for line in output.split('\n'):
                if line.startswith('Summary:'):
                    summary = line.split(':', 1)[1].strip()
                    break

            if not self._is_terminated:
                self.summary_ready.emit(self.package_name, summary or "No summary")
        except subprocess.TimeoutExpired:
            if not self._is_terminated:
                self.error_occurred.emit(self.package_name, "获取超时")
        except Exception as e:
            if not self._is_terminated:
                self.error_occurred.emit(self.package_name, str(e))


class SummaryManager:
    """包摘要管理器，限制并发线程数量"""

    def __init__(self, max_threads=5):
        self.max_threads = max_threads
        self.active_threads = {}
        self.pending_tasks = []
        self.python_exe = None

    def set_python_exe(self, python_exe):
        self.python_exe = python_exe

    def add_task(self, package_name, row, column, callback):
        """添加获取包摘要的任务"""
        if len(self.active_threads) < self.max_threads:
            # 直接启动线程
            self._start_thread(package_name, row, column, callback)
        else:
            # 添加到待处理队列
            self.pending_tasks.append((package_name, row, column, callback))

    def _start_thread(self, package_name, row, column, callback):
        """启动获取包摘要的线程"""
        if not self.python_exe:
            return

        thread = PackageSummaryThread(self.python_exe, package_name)
        thread.summary_ready.connect(lambda name, summary: callback(row, column, name, summary))
        thread.error_occurred.connect(lambda name, error: callback(row, column, name, f"错误: {error}"))

        # 保存线程引用
        self.active_threads[package_name] = {
            'thread': thread,
            'callback': callback,
            'row': row,
            'column': column
        }

        thread.start()

    def on_thread_finished(self, package_name):
        """线程完成时调用"""
        if package_name in self.active_threads:
            del self.active_threads[package_name]

        # 处理待处理的任务
        if self.pending_tasks and len(self.active_threads) < self.max_threads:
            package_name, row, column, callback = self.pending_tasks.pop(0)
            self._start_thread(package_name, row, column, callback)

    def cancel_all(self):
        """取消所有线程和待处理任务"""
        # 终止所有活跃线程
        for info in list(self.active_threads.values()):
            thread = info['thread']
            if thread.isRunning():
                thread.terminate()
                thread.wait()
        self.active_threads.clear()

        # 清空待处理队列
        self.pending_tasks.clear()


class EnvManagerUI(QWidget):
    env_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("EnvManagerUI")
        self.resize(1000, 600)

        self.mgr = EnvironmentManager()
        self.process = None
        self.current_env = None
        self.pkgs_data = []  # 保存完整包列表数据
        self.package_summaries = {}  # 缓存包摘要信息
        self.summary_manager = SummaryManager(max_threads=3)  # 限制并发线程数

        # ---------- 顶部环境选择 ----------
        self.envCombo = ComboBox(self)
        self.refresh_env_list()
        self.envCombo.currentIndexChanged.connect(self.on_env_changed)

        self.newEnvBtn = PrimaryPushButton("新建环境", self, icon=FluentIcon.ADD)
        self.newEnvBtn.clicked.connect(self.create_env)

        self.deleteEnvBtn = PushButton("删除环境", self, icon=FluentIcon.DELETE)
        self.deleteEnvBtn.clicked.connect(self.delete_env)

        self.refreshEnvBtn = PushButton("刷新", self, icon=FluentIcon.SYNC)
        self.refreshEnvBtn.clicked.connect(self.on_env_changed)

        topLayout = QHBoxLayout()
        topLayout.addWidget(BodyLabel("Python环境:"))
        topLayout.addWidget(self.envCombo, stretch=1)
        topLayout.addWidget(self.newEnvBtn)
        topLayout.addWidget(self.deleteEnvBtn)
        topLayout.addWidget(self.refreshEnvBtn)

        # ---------- 第二行操作 ----------
        self.actionCombo = ComboBox(self)
        self.actionCombo.addItems(["安装", "强制重装", "更新", "卸载"])

        self.packageEdit = LineEdit(self)
        self.packageEdit.setPlaceholderText("输入包名，例如 numpy 或 numpy==1.24.0")

        self.execBtn = PrimaryPushButton("执行", self, icon=FluentIcon.PLAY)
        self.execBtn.clicked.connect(self.run_pip_command)

        actionLayout = QHBoxLayout()
        actionLayout.addWidget(self.actionCombo)
        actionLayout.addWidget(self.packageEdit, stretch=1)
        actionLayout.addWidget(self.execBtn)

        # ---------- 包列表区域 ----------
        # 搜索框放在包列表上方
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索已安装包...")
        self.searchEdit.textChanged.connect(self.on_search_text_changed)
        self.searchEdit.searchSignal.connect(self.on_search_text_changed)
        # 包列表表格
        self.packageTable = TableWidget(self)
        self.packageTable.setColumnCount(3)
        self.packageTable.setHorizontalHeaderLabels(["包名", "版本", "操作"])

        # 设置列宽
        header = self.packageTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 包名
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 版本
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 操作
        self.packageTable.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        packageLayout = QVBoxLayout()
        packageLayout.addLayout(topLayout)
        packageLayout.addLayout(actionLayout)
        packageLayout.addWidget(self.searchEdit)  # 搜索框在列表上方
        packageLayout.addWidget(self.packageTable, stretch=1)  # 列表填满剩余区域

        packageWidget = QWidget()
        packageWidget.setLayout(packageLayout)

        # ---------- 日志窗口 ----------
        self.logEdit = TextEdit(self)
        self.logEdit.setReadOnly(True)

        # 使用 QSplitter 让包列表和日志可拖拽分配空间
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(packageWidget)  # 左：搜索框 + 包列表
        splitter.addWidget(self.logEdit)  # 右：日志
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # ---------- 总布局 ----------
        mainLayout = QVBoxLayout(self)
        mainLayout.addWidget(splitter, stretch=1)  # 中间占满
        self.setLayout(mainLayout)

        if self.envCombo.count() > 0:
            self.on_env_changed()
        else:
            self.logEdit.append("⚠️ 没有检测到任何环境，请点击\"新建环境\"创建。")

    def get_current_python_exe(self):
        """获取当前环境 Python 的路径"""
        return self.mgr.get_python_exe(self.current_env)

    def refresh_env_list(self):
        self.envCombo.clear()
        envs = self.mgr.list_envs()
        self.envCombo.addItems(envs)

    def on_env_changed(self):
        # 取消所有正在运行的摘要获取线程
        self.summary_manager.cancel_all()
        self.package_summaries.clear()
        self.current_env = self.envCombo.currentText()
        if self.current_env:
            self.load_packages(self.current_env)

    def load_packages(self, env_name):
        """调用 pip list 获取环境中的包并填充表格"""
        self.packageTable.setRowCount(0)
        try:
            python_exe = str(self.mgr.get_python_exe(env_name))
        except Exception as e:
            self.logEdit.append(f"[错误] {e}")
            return

        try:
            result = subprocess.run(
                [python_exe, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.strip()
            # 提取 JSON 部分（第一个 [ 到最后一个 ]）
            match = re.search(r"\[.*\]", output, re.S)
            if match:
                pkgs = json.loads(match.group(0))
            else:
                pkgs = []
        except subprocess.CalledProcessError as e:
            # pip 可能把信息输出到 stderr
            stderr = e.stderr if hasattr(e, "stderr") else ""
            self.logEdit.append(f"[错误] 获取包列表失败: {stderr or e}")
            pkgs = []
        except Exception as e:
            self.logEdit.append(f"[错误] 获取包列表失败: {e}")
            pkgs = []

        # 保存完整数据，供搜索使用
        self.pkgs_data = pkgs
        self._repopulate_table(pkgs)

    def _repopulate_table(self, pkgs):
        """根据传入 pkgs 列表刷新表格（内部使用）"""
        # 取消所有正在运行的摘要获取线程
        self.summary_manager.cancel_all()
        self.package_summaries.clear()

        self.packageTable.setRowCount(0)
        # 设置Python解释器路径
        if self.current_env:
            python_exe = str(self.mgr.get_python_exe(self.current_env))
            self.summary_manager.set_python_exe(python_exe)

        for row, pkg in enumerate(pkgs):
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            self.packageTable.insertRow(row)
            self.packageTable.setItem(row, 0, QTableWidgetItem(name))
            self.packageTable.setItem(row, 1, QTableWidgetItem(version))

            # 异步获取包摘要
            # self._get_package_summary_async(name, row, 2)

            # 操作按钮：更新、卸载
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            update_btn = PushButton(text="更新")
            update_btn.setToolTip(f"更新 {name}")
            update_btn.clicked.connect(functools.partial(self.on_update_package_clicked, name))

            uninstall_btn = PushButton(text="卸载")
            uninstall_btn.setToolTip(f"卸载 {name}")
            uninstall_btn.clicked.connect(functools.partial(self.on_uninstall_package_clicked, name))

            btn_layout.addWidget(update_btn)
            btn_layout.addWidget(uninstall_btn)
            btn_layout.addStretch()

            self.packageTable.setCellWidget(row, 2, btn_widget)

    def _get_package_summary_async(self, package_name, row, column):
        """异步获取包的简短描述"""
        if not self.current_env:
            return

        # 检查是否已有缓存
        if package_name in self.package_summaries:
            summary = self.package_summaries[package_name]
            item = self.packageTable.item(row, column)
            if item:
                item.setText(summary)
            return

        # 添加到摘要管理器
        self.summary_manager.add_task(
            package_name, row, column,
            self._on_summary_result
        )

    def _on_summary_result(self, row, column, package_name, result):
        """包摘要获取完成或失败"""
        # 更新缓存
        self.package_summaries[package_name] = result

        # 更新表格
        item = self.packageTable.item(row, column)
        if item:
            item.setText(result)

        # 通知摘要管理器线程已完成
        self.summary_manager.on_thread_finished(package_name)

    def on_search_text_changed(self, text):
        """按搜索文本过滤已安装包"""
        text = text.strip().lower()
        if not text:
            filtered = self.pkgs_data
        else:
            filtered = [p for p in self.pkgs_data if text in p.get("name", "").lower()]
        self._repopulate_table(filtered)

    def run_pip_command(self):
        """通过顶部操作区执行通用的安装/更新/卸载（针对 packageEdit 中的包名）"""
        if not self.current_env:
            InfoBar.error("错误", "请选择环境", parent=self)
            return

        try:
            python_exe = str(self.mgr.get_python_exe(self.current_env))
        except Exception as e:
            InfoBar.error("错误", str(e), parent=self)
            return

        if not self.mgr.ensure_pip(python_exe, log_callback=self.logEdit.append):
            InfoBar.error("错误", "pip 安装失败", parent=self)
            return

        action = self.actionCombo.currentText()
        package = self.packageEdit.text().strip()
        if not package:
            InfoBar.error("错误", "请输入包名", parent=self)
            return

        if action == "安装":
            cmd = ["-m", "pip", "install", package]
        elif action == "强制重装":
            cmd = ["-m", "pip", "install", "--force-reinstall", package]
        elif action == "更新":
            cmd = ["-m", "pip", "install", "-U", package]
        elif action == "卸载":
            cmd = ["-m", "pip", "uninstall", "-y", package]
        else:
            return

        # 启动 QProcess 执行并实时输出
        self._start_process(python_exe, cmd)

    def on_update_package_clicked(self, package_name):
        """行内更新按钮处理"""
        # 相当于运行 `pip install -U package_name`
        if not self.current_env:
            InfoBar.error("错误", "请选择环境", parent=self)
            return
        python_exe = str(self.mgr.get_python_exe(self.current_env))
        if not self.mgr.ensure_pip(python_exe, log_callback=self.logEdit.append):
            InfoBar.error("错误", "pip 安装失败", parent=self)
            return
        cmd = ["-m", "pip", "install", "-U", package_name]
        self.logEdit.append(f"> {self.current_env} :: update {package_name}\n")
        self._start_process(python_exe, cmd)

    def on_uninstall_package_clicked(self, package_name):
        """行内卸载按钮处理"""
        if not self.current_env:
            InfoBar.error("错误", "请选择环境", parent=self)
            return
        python_exe = str(self.mgr.get_python_exe(self.current_env))
        if not self.mgr.ensure_pip(python_exe, log_callback=self.logEdit.append):
            InfoBar.error("错误", "pip 安装失败", parent=self)
            return
        cmd = ["-m", "pip", "uninstall", "-y", package_name]
        self.logEdit.append(f"> {self.current_env} :: uninstall {package_name}\n")
        self._start_process(python_exe, cmd)

    def delete_env(self):
        """删除当前选中的环境"""
        if not self.current_env:
            InfoBar.error("错误", "请选择要删除的环境", parent=self)
            return

        env_name = self.current_env
        msg_box = MessageBox("确认删除", f"确定要删除环境 {env_name} 吗？此操作不可恢复！", self)
        if msg_box.exec_():
            try:
                self.mgr.remove_env(env_name)
                self.mgr.remove_finished.connect(
                    self.refresh_env_list(),
                    InfoBar.success("成功", f"环境 {env_name} 已删除", parent=self),
                    self.env_changed.emit()
                )

                if self.envCombo.count() > 0:
                    self.envCombo.setCurrentIndex(0)
                else:
                    self.current_env = None
                    self.packageTable.setRowCount(0)

            except Exception as e:
                InfoBar.error("错误", f"删除环境失败: {str(e)}", parent=self)

    def _start_process(self, python_exe, cmd):
        """启动 QProcess（封装）"""
        # 若已有进程正在运行，先终止它
        if self.process and self.process.state() != QProcess.NotRunning:
            try:
                self.process.kill()
            except Exception:
                pass

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        # 连接实时输出
        self.process.readyReadStandardOutput.connect(self.on_ready_read)
        self.process.readyReadStandardError.connect(self.on_ready_read)
        self.process.finished.connect(self.on_finished)

        # start with executable and args
        self.process.start(python_exe, cmd)

    def on_ready_read(self):
        if not self.process:
            return
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        if data:
            self.logEdit.moveCursor(QTextCursor.End)
            self.logEdit.insertPlainText(data)
            self.logEdit.moveCursor(QTextCursor.End)

    def on_finished(self):
        self.logEdit.append("\n[完成] 操作已结束。")
        # 操作结束后刷新包列表
        if self.current_env:
            # 添加一个小延迟，确保pip操作完全完成
            QTimer.singleShot(1000, lambda: self.load_packages(self.current_env))

    def create_env(self):
        """新建环境：选择版本并自动下载安装"""
        version, ok = QInputDialog.getItem(
            self, "新建环境", "选择 Python 版本：",
            list(self.mgr.MINICONDA_URLS.keys()), 0, False
        )
        if not ok or not version:
            return

        try:
            self.mgr.download_and_install(version, log_callback=self.logEdit.append)
            self.mgr.install_finished.connect(
                lambda: (
                    self.refresh_env_list(),
                    InfoBar.success("成功", f"Python {version} 已安装", parent=self),
                    self.envCombo.setCurrentText(version),
                    self.env_changed.emit()
                )
            )
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            InfoBar.error("错误", str(e), parent=self)

