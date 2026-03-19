# -*- coding: utf-8 -*-
import functools
import json
import os
import platform
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

from PyQt5.QtCore import pyqtSignal, QProcess, Qt, QTimer, QSize, QPoint
from PyQt5.QtGui import QTextCursor, QColor, QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem
from PyQt5.QtWidgets import (
    QWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QFrame, QAbstractItemView, QStackedWidget
)
from qfluentwidgets import (
    ComboBox, PrimaryPushButton, TableWidget,
    FluentIcon, InfoBar, SearchLineEdit, TextEdit, MessageBox,
    StateToolTip, SimpleCardWidget,
    TransparentToolButton, IconWidget, CaptionLabel, Pivot,
    RoundMenu, Action, SwitchButton, ListWidget
)
from qfluentwidgets import (LineEdit, BodyLabel, StrongBodyLabel)

from app.interfaces.package_manager_interface.utils.package_list_thread import PackageListThread
from app.interfaces.package_manager_interface.utils.ssh_exec_thread import SSHExecThread
from app.interfaces.package_manager_interface.utils.ssh_upload_and_exec_thread import SSHUploadAndExecThread
from app.interfaces.package_manager_interface.widgets.ssh_confiig_dialog import SSHAddrDialog
from app.interfaces.package_manager_interface.widgets.task_card import TaskCardWidget
from app.utils.config import Settings
from app.utils.env_operation import EnvironmentManager
from app.utils.utils import get_icon, resource_path
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.dialog_widget.custom_messagebox import (
    CustomComboDialog, CustomInputDialog
)


class EnvManagerUI(QWidget):
    env_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.home = parent
        self.setObjectName("EnvManagerUI")
        self.resize(1100, 750)
        StyleSheet.PACKAGE_MANAGER.apply(self)

        self.mgr = EnvironmentManager()
        self.config = Settings.get_instance()

        self.current_env = None
        self.current_env_data = None
        self.pkgs_data = []
        self.ssh_config_file = str(Path(resource_path("envs")) / "ssh_envs_cache.json")

        self.tasks = {}
        self.main_log = []  # 主日志缓冲区
        self.current_viewing_task_id = None  # None 表示主控制台

        self._init_ui()

        self.pivot.setCurrentItem("local")
        self.on_mode_changed("local")

    def _init_ui(self):
        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(16, 16, 16, 16)

        self.pivot = Pivot(self)
        self.pivot.addItem("local", self.tr("本地环境"), lambda: self.on_mode_changed("local"))
        self.pivot.addItem("remote", self.tr("远程 SSH"), lambda: self.on_mode_changed("remote"))

        self.splitter = ModernSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(5)

        leftWidget = self._create_left_panel()

        self.rightCard = SimpleCardWidget(self)
        rightLayout = QVBoxLayout(self.rightCard)

        rightLayout.addLayout(self._create_header())

        self.configStack = QStackedWidget(self)
        self._init_local_panel()
        self._init_remote_panel()
        self.configStack.addWidget(self.localPanel)
        self.configStack.addWidget(self.remotePanel)
        rightLayout.addWidget(self.configStack)

        self._init_pip_console(rightLayout)

        self.splitter.addWidget(leftWidget)
        self.splitter.addWidget(self.rightCard)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 5)
        self.mainLayout.addWidget(self.splitter)

    def _create_left_panel(self):
        leftWidget = QWidget()
        leftLayout = QVBoxLayout(leftWidget)
        leftLayout.setContentsMargins(0, 0, 5, 0)

        searchLayout = QHBoxLayout()
        listIcon = IconWidget(FluentIcon.LIBRARY, self)
        listIcon.setFixedSize(24, 24)
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText(self.tr("搜索包名 (Ctrl+F)"))
        self.searchEdit.setFixedWidth(240)
        self.searchEdit.textChanged.connect(self.on_search_text_changed)
        self.searchEdit.searchSignal.connect(self.on_search_text_changed)
        self.searchEdit.clearSignal.connect(self.on_search_text_changed)
        searchLayout.addWidget(listIcon)
        searchLayout.addWidget(StrongBodyLabel(self.tr("已安装包列表"), self))
        searchLayout.addStretch(1)
        searchLayout.addWidget(self.searchEdit)

        self.packageTable = TableWidget(self)
        self._setup_package_table()
        leftLayout.addLayout(searchLayout)
        leftLayout.addWidget(self.packageTable)
        return leftWidget

    def _create_header(self):
        self.titleLayout = QHBoxLayout()

        envIcon = IconWidget(get_icon("python"), self)
        envIcon.setFixedSize(32, 32)
        statusInfoLayout = QVBoxLayout()
        self.pyVersionLabel = CaptionLabel(self.tr("Python 版本: --"), self)
        self.remoteDetailLabel = CaptionLabel(self.tr("连接信息: 本地环境"), self)
        statusInfoLayout.addWidget(self.pyVersionLabel)
        statusInfoLayout.addWidget(self.remoteDetailLabel)

        self.titleLayout.addWidget(envIcon)
        self.titleLayout.addLayout(statusInfoLayout)
        self.titleLayout.addStretch(1)
        self.titleLayout.addWidget(self.pivot)
        return self.titleLayout

    def _init_local_panel(self):
        self.localPanel = QWidget()
        lpLayout = QHBoxLayout(self.localPanel)
        lpLayout.setContentsMargins(0, 0, 0, 0)
        self.envCombo = ComboBox(self)
        self.envCombo.setMaxVisibleItems(12)
        self.envCombo.currentIndexChanged.connect(self.on_env_changed)

        self.refreshLocalBtn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refreshLocalBtn.setToolTip(self.tr("刷新包列表"))
        self.refreshLocalBtn.clicked.connect(lambda: self.load_packages(self.current_env_data))

        self.newEnvBtn = TransparentToolButton(FluentIcon.ADD, self)
        self.newEnvBtn.clicked.connect(self.create_env)
        self.cloneEnvBtn = TransparentToolButton(FluentIcon.COPY, self)
        self.cloneEnvBtn.clicked.connect(self.clone_env)
        self.installDefaultBtn = TransparentToolButton(get_icon("工具包"), self)
        self.installDefaultBtn.setToolTip(self.tr("安装默认依赖包"))
        self.installDefaultBtn.clicked.connect(self.install_default_packages)
        self.deleteEnvBtn = TransparentToolButton(FluentIcon.DELETE, self)
        self.deleteEnvBtn.clicked.connect(self.delete_env)

        lpLayout.addWidget(self.envCombo, 1)
        lpLayout.addWidget(self.refreshLocalBtn)
        lpLayout.addWidget(self.newEnvBtn)
        lpLayout.addWidget(self.cloneEnvBtn)
        lpLayout.addWidget(self.installDefaultBtn)
        lpLayout.addWidget(self.deleteEnvBtn)

    def _init_remote_panel(self):
        self.remotePanel = QWidget()
        rpLayout = QVBoxLayout(self.remotePanel)
        rpLayout.setContentsMargins(0, 0, 0, 0)
        rpTop = QHBoxLayout()
        self.remoteEnvCombo = ComboBox(self)
        self.remoteEnvCombo.setMaxVisibleItems(12)
        self.remoteEnvCombo.currentIndexChanged.connect(self.on_env_changed)

        self.addSshBtn = TransparentToolButton(FluentIcon.ADD, self)
        self.addSshBtn.setToolTip(self.tr("添加 SSH 环境"))
        self.addSshBtn.clicked.connect(self.add_ssh_env_dialog)

        self.editSshBtn = TransparentToolButton(FluentIcon.EDIT, self)
        self.editSshBtn.setToolTip(self.tr("编辑 SSH 环境"))
        self.editSshBtn.clicked.connect(self.edit_ssh_env_dialog)

        self.refreshRemoteBtn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refreshRemoteBtn.setToolTip(self.tr("刷新包列表"))
        self.refreshRemoteBtn.clicked.connect(lambda: self.load_packages(self.current_env_data))

        self.installDefaultBtn = TransparentToolButton(get_icon("工具包"), self)
        self.installDefaultBtn.setToolTip(self.tr("安装默认依赖包"))
        self.installDefaultBtn.clicked.connect(self.install_default_packages)

        self.delSshBtn = TransparentToolButton(FluentIcon.DELETE, self)
        self.delSshBtn.setToolTip(self.tr("删除 SSH 环境"))
        self.delSshBtn.clicked.connect(self.delete_ssh_env)

        rpTop.addWidget(self.remoteEnvCombo, 1)
        rpTop.addWidget(self.refreshRemoteBtn)
        rpTop.addWidget(self.addSshBtn)
        rpTop.addWidget(self.editSshBtn)
        rpTop.addWidget(self.installDefaultBtn)
        rpTop.addWidget(self.delSshBtn)

        rpLayout.addLayout(rpTop)

    def _init_pip_console(self, layout):
        layout.addWidget(QFrame(frameShape=QFrame.HLine, styleSheet="color:#e5e5e5;"))

        headerLayout = QHBoxLayout()
        headerLayout.addWidget(StrongBodyLabel(self.tr("任务与命令控制台")))
        headerLayout.addStretch(1)
        uv_label = StrongBodyLabel(self.tr("使用 uv 极速安装"))
        self.uvSwitch = SwitchButton(self)
        self.uvSwitch.setChecked(True)
        headerLayout.addWidget(uv_label)
        headerLayout.addWidget(self.uvSwitch)
        layout.addLayout(headerLayout)

        cl = QHBoxLayout()
        self.sourceCombo = ComboBox(self)
        self.sourceCombo.addItems([self.tr("在线搜索"), self.tr("本地文件")])
        self.sourceCombo.currentIndexChanged.connect(self._update_action_combo)
        self.actionCombo = ComboBox(self)
        cl.addWidget(self.sourceCombo, 1)
        cl.addWidget(self.actionCombo, 1)
        layout.addLayout(cl)

        self.packageEdit = LineEdit(self)
        self.packageEdit.setClearButtonEnabled(True)
        self.packageEdit.setPlaceholderText(self.tr("请输入包名，例如 numpy..."))

        self.fileSelectBtn = TransparentToolButton(FluentIcon.FOLDER, self)
        self.fileSelectBtn.setToolTip(self.tr("选择文件/文件夹"))
        self.fileSelectBtn.clicked.connect(self.show_file_selection_menu)
        self.fileSelectBtn.hide()

        self.pkgLayout = QHBoxLayout()
        self.pkgLayout.addWidget(self.packageEdit, 1)
        self.pkgLayout.addWidget(self.fileSelectBtn)
        layout.addLayout(self.pkgLayout)

        self.execBtn = PrimaryPushButton(self.tr("发布任务"), self, icon=FluentIcon.PLAY)
        self.execBtn.clicked.connect(lambda: self.run_pip_command())
        layout.addWidget(self.execBtn)

        layout.addWidget(BodyLabel(self.tr("任务列表与日志:")))

        self.consoleSplitter = ModernSplitter(Qt.Horizontal)
        self.consoleSplitter.setHandleWidth(3)

        self.taskListWidget = ListWidget(self)
        self.taskListWidget.setFrameShape(QFrame.NoFrame)
        self.taskListWidget.setFixedWidth(280)

        # 添加主控制台固定项
        self.mainConsoleItem = QListWidgetItem(self.taskListWidget)
        self.mainConsoleItem.setText(f" > {self.tr('系统主控制台')}")
        self.mainConsoleItem.setData(Qt.UserRole, "MAIN_LOG_ENTRY")
        self.mainConsoleItem.setSizeHint(QSize(260, 40))

        self.taskListWidget.itemClicked.connect(self._on_task_item_clicked)
        self.taskListWidget.hide()

        self.logEdit = TextEdit(self)
        self.logEdit.setReadOnly(True)
        self.logEdit.setStyleSheet("background-color:#282c34;color:#abb2bf;font-family:Consolas;")

        self.consoleSplitter.addWidget(self.taskListWidget)
        self.consoleSplitter.addWidget(self.logEdit)
        self.consoleSplitter.setStretchFactor(1, 1)

        layout.addWidget(self.consoleSplitter, 1)

        self._update_action_combo()

    # --- API ---
    def get_current_python_exe(self):
        """
        获取当前选中的 Python 解释器路径
        供外部模块 (如 CodeEditorWidget) 调用
        """
        if self.current_env_data and "path" in self.current_env_data:
            return self.current_env_data.get("path")

        # 兜底逻辑
        if self.current_env:
            return str(self.mgr.get_python_exe(self.current_env))

        return "python"

    def change_env(self, env_name):
        """
        外部请求切换环境
        """
        envs = self.mgr.list_envs()
        if env_name in envs:
            idx = self.envCombo.findText(f"[Local] {env_name}")
            if idx >= 0:
                self.pivot.setCurrentItem("local")
                self.on_mode_changed("local")
                self.envCombo.setCurrentIndex(idx)

    # --- End API ---

    def create_task(self, name, env_data, worker, is_remote=False):
        if self.taskListWidget.isHidden():
            self.taskListWidget.show()
            self.consoleSplitter.setSizes([280, 700])

        task_id = str(uuid.uuid4())

        item = QListWidgetItem(self.taskListWidget)
        item.setSizeHint(QSize(260, 80))

        env_name = env_data.get("name", "Unknown")
        card = TaskCardWidget(task_id, name, env_name, self.taskListWidget)
        card.cancel_signal.connect(self.cancel_task)

        self.taskListWidget.setItemWidget(item, card)
        self.taskListWidget.setCurrentItem(item)

        self.tasks[task_id] = {
            'id': task_id,
            'name': name,
            'worker': worker,
            'log': [],
            'env': env_data,
            'item': item,
            'card': card,
            'status': 'running',
            'is_remote': is_remote
        }

        if is_remote:
            worker.output_signal.connect(lambda text: self.on_task_log(task_id, text))
            worker.finished_signal.connect(lambda: self.on_task_finished(task_id))
            worker.start()
        else:
            worker.readyReadStandardOutput.connect(lambda: self.on_local_process_output(task_id))
            worker.finished.connect(lambda exit_code=0, status=None: self.on_task_finished(task_id))
            worker.start()

        self._switch_log_view(task_id)

        start_msg = f"> {self.tr('任务')} '{name}' {self.tr('已启动')}，{self.tr('环境')}: [{env_name}]..."
        self._log_color(start_msg, "#61afef", task_id)
        card.set_status(self.tr("运行中..."), "#009faa")

    def cancel_task(self, task_id):
        if task_id not in self.tasks: return
        task = self.tasks[task_id]
        if task['status'] != 'running': return

        worker = task['worker']
        self._log_color(f"\n[{self.tr('警告')}] {self.tr('用户取消了该任务')}。", "#e06c75", task_id)

        if task['is_remote']:
            if hasattr(worker, 'terminate'):
                worker.terminate()
                worker.wait()
        else:
            if worker.state() != QProcess.NotRunning:
                worker.kill()

        task['status'] = 'cancelled'
        task['card'].set_status(self.tr("已取消"), "#e06c75", finished=True)
        self.on_task_finished(task_id, forced_status=self.tr("已取消"))

    def on_local_process_output(self, task_id):
        if task_id not in self.tasks: return
        task = self.tasks[task_id]
        process = task['worker']
        data = process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        self.on_task_log(task_id, data)

    def on_task_log(self, task_id, text):
        if task_id not in self.tasks: return

        # 1. 存入缓冲区
        self.tasks[task_id]['log'].append(text)

        # 2. 如果当前正在看这个任务，立即显示
        if self.current_viewing_task_id == task_id:
            self._append_log_chunk(text)

    def _append_log_chunk(self, text):
        """
        智能追加日志：
        如果是 HTML 样式的状态信息，使用 append (自动换行);
        如果是普通文本（进程输出），使用 insertPlainText (保留原始流式换行)
        """
        if text.strip().startswith("<span"):
            # HTML 状态信息，作为新段落追加
            self.logEdit.append(text)
        else:
            # 普通文本流，插入光标处
            self.logEdit.insertPlainText(text)
        self.logEdit.moveCursor(QTextCursor.End)

    def on_task_finished(self, task_id, forced_status=None):
        if task_id not in self.tasks: return
        task = self.tasks[task_id]

        if task['status'] == 'finished' and not forced_status:
            return

        # 获取完整日志文本
        full_log = "".join(task['log'])
        exit_code = 0 if task['is_remote'] else task['worker'].exitCode()

        # 判定是否触发了元数据损坏错误
        is_metadata_error = "uninstall-no-record-file" in full_log or "METADATA" in full_log

        status_text = forced_status or self.tr("完成")
        color = "#e06c75" if (forced_status == self.tr("已取消") or exit_code != 0) else "#98c379"

        if exit_code != 0 and not forced_status:
            status_text = self.tr("失败")

            # --- 自动修复逻辑开始 ---
            if is_metadata_error:
                self._log_color(f"\n[系统检测] 发现损坏的包元数据，正在尝试自动修复...", "#d19a66", task_id)
                cleaned = self._cleanup_broken_package_metadata(full_log, task['env'].get('path', ''))
                if cleaned:
                    for f in cleaned:
                        self._log_color(f" -> 已移除损坏的目录: {f}", "#d19a66", task_id)
                    self._log_color("修复完成，请尝试重新执行任务。", "#98c379", task_id)
                    task['card'].set_status(self.tr("已修复，请重试"), "#d19a66", finished=True)
                else:
                    self._log_color("未找到可清理的目录，请手动检查 site-packages。", "#e06c75", task_id)
            # --- 自动修复逻辑结束 ---

        task['status'] = 'finished'
        if not is_metadata_error:  # 如果已经设为“已修复”，就不覆盖状态
            task['card'].set_status(status_text, color, finished=True)

        self._log_color(f"\n[{status_text}]", color, task_id)

        # 只有成功时才刷新列表，减少文件锁竞争
        if exit_code == 0 and self.current_env_data and task['env']['name'] == self.current_env_data['name']:
            self.load_packages(self.current_env_data)

    def _on_task_item_clicked(self, item):
        # 检查是否点击了主控制台
        if item.data(Qt.UserRole) == "MAIN_LOG_ENTRY":
            self._switch_log_view(None)
            return

        for tid, data in self.tasks.items():
            if data['item'] == item:
                self._switch_log_view(tid)
                break

    def _switch_log_view(self, task_id):
        """切换视图时，逐条回放日志以保留格式"""
        self.current_viewing_task_id = task_id
        self.logEdit.clear()

        if task_id is None:
            # 回放主日志
            for chunk in self.main_log:
                self._append_log_chunk(chunk)
        elif task_id in self.tasks:
            # 遍历历史记录，使用智能追加函数
            for chunk in self.tasks[task_id]['log']:
                self._append_log_chunk(chunk)

    def _log_color(self, text, color, task_id=None):
        html = f'<span style="color:{color};">{text}</span>'

        if task_id and task_id in self.tasks:
            # 分发到具体任务
            self.on_task_log(task_id, html)
        else:
            # 记录到主控制台缓冲区
            self.main_log.append(html)
            # 如果当前正在看主控制台，则立即显示
            if self.current_viewing_task_id is None:
                self._append_log_chunk(html)

    def get_uv_path(self):
        """
        获取 uv 的路径，支持在 PATH 找不到时检查默认安装目录
        """
        # 1. 首先检查环境变量 PATH
        uv_in_path = shutil.which("uv")
        if uv_in_path:
            return uv_in_path

        # 2. 如果 PATH 找不到，检查默认安装位置 (Windows)
        if platform.system() == "Windows":
            default_path = Path.home() / ".local" / "bin" / "uv.exe"
            if default_path.exists():
                return str(default_path)
        else:
            # Linux/macOS 默认位置
            default_path = Path.home() / ".local" / "bin" / "uv"
            if default_path.exists():
                return str(default_path)

        return None

    def is_uv_installed(self):
        return self.get_uv_path() is not None

    def install_uv_logic(self):
        # 修复权限报错：添加 -ExecutionPolicy Bypass
        if platform.system() == "Windows":
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"]
        else:
            cmd = ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]

        process = QProcess(self)
        process.setProgram(cmd[0])
        process.setArguments(cmd[1:])

        fake_env = {"name": "System", "type": "local"}
        self.create_task(self.tr("安装 uv"), fake_env, process, is_remote=False)

    def run_pip_command(self, action=None, package_input=None, force_no_uv=False):
        if not self.current_env_data: return

        # === 关键修复：解决 Windows 文件占用 (OS Error 32) ===
        if platform.system() == "Windows":
            if hasattr(self, '_pkg_thread') and self._pkg_thread.isRunning():
                self._pkg_thread.terminate()
                self._pkg_thread.wait()
                self.pyVersionLabel.setText(self.tr("列表刷新已暂停，准备执行任务..."))

        use_uv = (not force_no_uv) and self.uvSwitch.isChecked() and self.current_env_data["type"] == "local"
        if use_uv and not self.is_uv_installed():
            res = MessageBox(self.tr("未检测到 uv"), self.tr("是否立即安装 uv 以启用加速功能？"), self).exec()
            if res:
                self.install_uv_logic()
            else:
                self.uvSwitch.setChecked(False)
            return

        ui_action = self.actionCombo.currentText()
        ui_source = self.sourceCombo.currentText()
        current_action = action or ui_action
        raw_input = package_input or self.packageEdit.text().strip()

        if not raw_input and self.tr("卸载") not in current_action: return

        cmd_result = self._generate_pip_command(use_uv, current_action, ui_source, raw_input)
        if not cmd_result: return
        executable, args, upload_files = cmd_result

        display_name = f"{current_action} {raw_input}"
        if len(display_name) > 25:
            display_name = display_name[:25] + "..."

        if self.current_env_data["type"] == "ssh":
            if upload_files:
                is_req = self.tr("Requirements") in current_action
                worker = SSHUploadAndExecThread(
                    self.current_env_data, upload_files, current_action, is_requirements=is_req
                )
                self.create_task(display_name, self.current_env_data, worker, is_remote=True)
            else:
                worker = SSHExecThread(self.current_env_data, args)
                self.create_task(display_name, self.current_env_data, worker, is_remote=True)
        else:
            process = QProcess(self)
            process.setProcessChannelMode(QProcess.MergedChannels)
            if platform.system() == "Windows":
                from PyQt5.QtCore import QProcessEnvironment
                process.setProcessEnvironment(QProcessEnvironment.systemEnvironment())

            process.setProgram(executable)
            process.setArguments(args)
            self.create_task(display_name, self.current_env_data, process, is_remote=False)

    def _generate_pip_command(self, use_uv, action, source, input_text):
        upload_files = None

        if use_uv:
            # 关键修复：使用 get_uv_path 获取绝对路径，而不是简单的 "uv"
            executable = self.get_uv_path() or "uv"
            if self.tr("卸载") in action:
                cmd = ["pip", "uninstall", "--python", self.current_env_data["path"]]
            else:
                cmd = ["pip", "install", "--python", self.current_env_data["path"]]
        else:
            executable = self.current_env_data.get("path", "python")
            if self.tr("卸载") in action:
                cmd = ["-m", "pip", "uninstall", "-y"]
            else:
                cmd = ["-m", "pip", "install"]

        if self.tr("Requirements") in action:
            cmd.extend(["-r", input_text])
            self._add_mirror_sources(cmd)
            if self.current_env_data["type"] == "ssh" and source == self.tr("本地文件"):
                upload_files = [input_text]
        elif source == self.tr("在线搜索"):
            input_list = input_text.split(" ") if input_text else []
            if self.tr("卸载") in action:
                cmd.extend(input_list)
            elif action == self.tr("强制重装"):
                cmd.extend(["--force-reinstall"] + input_list)
                self._add_mirror_sources(cmd)
            elif action == self.tr("更新"):
                cmd.extend(["-U"] + input_list)
                self._add_mirror_sources(cmd)
            else:
                cmd.extend(input_list)
                self._add_mirror_sources(cmd)
        else:
            if self.tr("离线") in action:
                cmd.append("--no-index")
            else:
                self._add_mirror_sources(cmd)

            paths = [p.strip() for p in input_text.split(";") if p.strip()]
            final_packages = []

            for p in paths:
                if os.path.isdir(p):
                    for item in os.listdir(p):
                        if item.lower().endswith(('.whl', '.tar.gz', '.zip')):
                            final_packages.append(os.path.join(p, item))
                else:
                    final_packages.append(p)

            if self.current_env_data["type"] == "ssh":
                upload_files = paths
            else:
                cmd.extend(final_packages)

        return executable, cmd, upload_files

    def _add_mirror_sources(self, cmd):
        mirrors = self.mgr.config.mirrors.value
        if not mirrors: return
        for i, url in enumerate(mirrors):
            flag = "-i" if i == 0 else "--extra-index-url"
            parsed = urlparse(url)
            if parsed.hostname:
                cmd.extend([flag, url, "--trusted-host", parsed.hostname])

    def _setup_package_table(self):
        self.packageTable.setColumnCount(3)
        self.packageTable.setHorizontalHeaderLabels([self.tr("名称"), self.tr("版本"), self.tr("操作")])
        self.packageTable.verticalHeader().hide()
        self.packageTable.setAlternatingRowColors(True)
        self.packageTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.packageTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.resizeSection(1, 120)
        header.resizeSection(2, 90)

    def _update_action_combo(self):
        current_source = self.sourceCombo.currentText()
        self.actionCombo.clear()
        if current_source == self.tr("在线搜索"):
            self.fileSelectBtn.hide()
            self.actionCombo.addItems([self.tr("安装"), self.tr("强制重装"), self.tr("更新"), self.tr("卸载")])
            self.packageEdit.setPlaceholderText(self.tr("请输入包名，例如 numpy"))
        elif current_source == self.tr("本地文件"):
            self.fileSelectBtn.show()
            self.actionCombo.addItems(
                [self.tr("安装 (Whl/Zip)"), self.tr("离线安装 (Whl/Zip)"), self.tr("Requirements 安装")])
            self.packageEdit.setPlaceholderText(self.tr("请选择本地 .whl 或 requirements.txt 文件..."))

    def show_file_selection_menu(self):
        menu = RoundMenu(parent=self)
        act_req = Action(FluentIcon.DOCUMENT, self.tr("选择 requirements.txt"), self)
        act_files = Action(FluentIcon.ADD, self.tr("选择安装包 (whl/tar.gz)"), self)
        act_folder = Action(FluentIcon.FOLDER, self.tr("选择文件夹"), self)

        act_req.triggered.connect(self.select_requirements_file)
        act_files.triggered.connect(self.select_local_files)
        act_folder.triggered.connect(self.select_local_folder)

        menu.addAction(act_req)
        menu.addSeparator()
        menu.addAction(act_files)
        menu.addAction(act_folder)
        pos = self.fileSelectBtn.mapToGlobal(QPoint(0, self.fileSelectBtn.height()))
        menu.exec(pos)

    def select_requirements_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择 Requirements 文件"), "", "Text Files (*.txt);;All Files (*)"
        )
        if file:
            self.packageEdit.setText(file)
            self.actionCombo.setCurrentText(self.tr("Requirements 安装"))

    def select_local_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, self.tr("选择安装包"), "", "Python Packages (*.whl *.tar.gz *.zip);All Files (*)"
        )
        if files:
            self.packageEdit.setText(";".join(files))

    def select_local_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("选择文件夹"))
        if folder:
            self.packageEdit.setText(folder)

    def get_all_environments(self):
        all_envs = []
        for env in self.mgr.list_envs():
            all_envs.append({"name": env, "type": "local", "path": str(self.mgr.get_python_exe(env))})
        if os.path.exists(self.ssh_config_file):
            with open(self.ssh_config_file, 'r', encoding='utf-8') as f:
                ssh_list = json.load(f)
                for env in ssh_list:
                    env["type"] = "ssh"
                    all_envs.append(env)
        return all_envs

    def refresh_env_list(self):
        self.envCombo.blockSignals(True)
        self.envCombo.clear()
        envs = self.mgr.list_envs()
        for env in envs:
            path = str(self.mgr.get_python_exe(env))
            self.envCombo.addItem(f"[Local] {env}", userData={"type": "local", "name": env, "path": path})
        last_selected = self.config.current_env_selected.value
        idx = self.envCombo.findText(f"[Local] {last_selected}")
        self.envCombo.setCurrentIndex(idx if idx >= 0 else 0)
        self.envCombo.blockSignals(False)
        self.on_env_changed()

    def on_env_changed(self):
        combo = self.envCombo if self.configStack.currentIndex() == 0 else self.remoteEnvCombo
        data = combo.currentData()
        if not data: return
        self.current_env_data = data
        self.current_env = data["name"]

        if data["type"] == "local":
            self.mgr.refresh_env_config()
            self.remoteDetailLabel.setText(f"{self.tr('路径')}: {data['path']}")
            self.config.set(self.config.current_env_selected, data["name"])
            self.config.save_config()
        else:
            self.remoteDetailLabel.setText(
                f"{self.tr('地址')}: {data['host']}:{data.get('port', 22)} | User: {data['user']}")

        self.load_packages(data)

    def load_packages(self, env_data):
        if not env_data: return
        for task in self.tasks.values():
            if task['status'] == 'running' and not task['is_remote']:
                self._log_color("> 任务执行中，暂缓刷新列表以防止文件冲突。", "#abb2bf")
                return
        if isinstance(env_data, str):
            env_data = {"type": "local", "name": env_data, "path": str(self.mgr.get_python_exe(env_data))}

        self.pyVersionLabel.setText(self.tr("正在加载包列表..."))
        if hasattr(self, '_pkg_thread') and self._pkg_thread.isRunning():
            self._pkg_thread.terminate()
            self._pkg_thread.wait()

        self._log_color(f"> 正在同步环境: {env_data['name']} ...", "#61afef")
        self._pkg_thread = PackageListThread(env_data)
        self._pkg_thread.packages_loaded.connect(self.on_load_packages)
        self._pkg_thread.error_occurred.connect(self.on_load_packages_error)
        self._pkg_thread.start()

    def on_load_packages(self, py_version, package_list):
        self.pyVersionLabel.setText(f"Python: {py_version}")
        self.packageTable.setRowCount(0)
        try:
            match = re.search(r"\[.*\]", package_list, re.S)
            pkgs = json.loads(match.group(0)) if match else []
        except:
            pkgs = []
        self.pkgs_data = pkgs
        self._repopulate_table(pkgs)
        self._log_color(f"[完成] 共加载 {len(pkgs)} 个包", "#98c379")

    def on_load_packages_error(self, e):
        self.pyVersionLabel.setText(self.tr("加载版本失败"))
        self._log_color(f"[Error] {str(e)}", "#e06c75")

    def _repopulate_table(self, pkgs):
        self.packageTable.setUpdatesEnabled(False)
        self.packageTable.setSortingEnabled(False)
        self.packageTable.setRowCount(len(pkgs))
        self._pending_pkgs = pkgs
        self._current_populate_index = 0
        self._batch_size = 20
        if hasattr(self, '_populate_timer'):
            self._populate_timer.stop()
        else:
            self._populate_timer = QTimer(self)
            self._populate_timer.timeout.connect(self._populate_batch)
        self._populate_timer.start(1)

    def _populate_batch(self):
        start = self._current_populate_index
        end = min(start + self._batch_size, len(self._pending_pkgs))
        font = QFont("Segoe UI", 9)
        gray_color = QColor(150, 150, 150)
        for i in range(start, end):
            pkg = self._pending_pkgs[i]
            name = pkg.get("name", "")
            ver = pkg.get("version", "")
            n_item = QTableWidgetItem(name)
            n_item.setFont(font)
            self.packageTable.setItem(i, 0, n_item)
            v_item = QTableWidgetItem(ver)
            v_item.setFont(font)
            v_item.setForeground(gray_color)
            self.packageTable.setItem(i, 1, v_item)
            self.packageTable.setCellWidget(i, 2, self._create_action_group(name))
        self._current_populate_index = end
        if end >= len(self._pending_pkgs):
            self._populate_timer.stop()
            self.packageTable.setSortingEnabled(True)
            self.packageTable.setUpdatesEnabled(True)
            self.packageTable.viewport().update()

    def _create_action_group(self, name):
        bw = QWidget()
        bl = QHBoxLayout(bw)
        bl.setContentsMargins(4, 0, 4, 0)
        bl.setSpacing(4)
        bl.setAlignment(Qt.AlignCenter)
        ub = TransparentToolButton(get_icon("更新"), bw)
        ub.setToolTip(f"{self.tr('更新')} {name}")
        ub.setFixedSize(26, 26)
        ub.setIconSize(QSize(14, 14))
        ub.clicked.connect(functools.partial(self.run_pip_command, self.tr("更新"), name))
        db = TransparentToolButton(FluentIcon.DELETE, bw)
        db.setToolTip(f"{self.tr('卸载')} {name}")
        db.setFixedSize(26, 26)
        db.setIconSize(QSize(14, 14))
        db.clicked.connect(functools.partial(self.on_uninstall_package_clicked, name))
        bl.addWidget(ub)
        bl.addWidget(db)
        return bw

    def on_uninstall_package_clicked(self, package_name):
        if MessageBox(self.tr("确认"), f"{self.tr('确定卸载')} {package_name}?", self).exec():
            self.run_pip_command(self.tr("卸载"), package_name)

    def on_search_text_changed(self, text):
        if hasattr(self, '_search_timer'):
            self._search_timer.stop()
        else:
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(lambda: self._do_search(self.searchEdit.text()))
        self._search_timer.start(200)

    def _do_search(self, text):
        t = text.strip().lower()
        self.packageTable.setUpdatesEnabled(False)
        for r in range(self.packageTable.rowCount()):
            it = self.packageTable.item(r, 0)
            self.packageTable.setRowHidden(r, t not in it.text().lower() if it else False)
        self.packageTable.setUpdatesEnabled(True)

    def on_mode_changed(self, mode):
        if mode == "local":
            self.configStack.setCurrentIndex(0)
            self.refresh_env_list()
        else:
            self.configStack.setCurrentIndex(1)
            self.refresh_remote_envs()

    def refresh_remote_envs(self):
        self.remoteEnvCombo.blockSignals(True)
        self.remoteEnvCombo.clear()
        ssh_list = []
        if os.path.exists(self.ssh_config_file):
            with open(self.ssh_config_file, 'r', encoding='utf-8') as f:
                ssh_list = json.load(f)
        for env in ssh_list:
            env["type"] = "ssh"
            self.remoteEnvCombo.addItem(f"[SSH] {env['name']}", userData=env)
        if self.remoteEnvCombo.count() > 0:
            self.remoteEnvCombo.setCurrentIndex(0)
        self.remoteEnvCombo.blockSignals(False)
        self.on_env_changed()

    def add_ssh_env_dialog(self):
        """
        添加 SSH 环境对话框
        功能：支持单个 Python 文件添加，或指定目录（如 envs）批量扫描并自动以环境文件夹命名
        """
        d = SSHAddrDialog(self)
        if d.exec():
            info = d.get_info()

            # 1. 显示状态提示，存入 self 防止提前销毁
            self.stateTooltip = StateToolTip(self.tr("正在扫描远程环境"), self.tr("请稍候..."), self)
            self.stateTooltip.show()

            # 2. 构造单行命令：兼容文件和目录搜索
            # 搜索当前路径及其下 4 层目录中名为 python 或 python3.x 的可执行文件
            search_path = info['path'].rstrip('/')
            # 使用原生 find 的逻辑：匹配包含 bin/python 的路径，不使用管道符
            cmd = f"find {search_path} -maxdepth 4 -type f -executable \( -name 'python' -o -name 'python3*' \)"

            # 【注意】这里必须传入 is_raw=True (需配合你修改后的 SSHExecThread 类)
            self.scan_worker = SSHExecThread(info, cmd, is_raw=True)

            # 用于收集所有输出行
            collected_outputs = []

            def handle_output(line):
                if line.strip():
                    collected_outputs.append(line.strip())

            def on_process_finished():
                if hasattr(self, 'stateTooltip'):
                    self.stateTooltip.close()

                found_paths = [
                    p for p in collected_outputs
                    if p.startswith('/') and not p.endswith('-config') and 'python' in p.lower()
                ]

                # 如果没有搜到有效的，兜底使用用户填的原始路径
                if not found_paths:
                    found_paths = [info['path']]

                try:
                    ssh_list = []
                    if os.path.exists(self.ssh_config_file):
                        with open(self.ssh_config_file, 'r', encoding='utf-8') as f:
                            ssh_list = json.load(f)

                    for p in found_paths:
                        new_entry = info.copy()
                        new_entry["path"] = p

                        parts = p.split('/')

                        # 命名逻辑：如果是从目录扫出来的，提取环境文件夹名
                        # 例如: /langchain/bin/python3.8 -> 名字提取为 langchain
                        if p != info['path'] and len(parts) >= 3:
                            if parts[-2] == 'bin':
                                env_name = parts[-3]  # langchain
                            else:
                                env_name = parts[-2]
                            new_entry["name"] = env_name
                        else:
                            # 单文件模式或路径太短，用用户起的名字或文件名
                            new_entry["name"] = info["name"] if info["name"] else parts[-1]

                        # 排重：Host + Port + Path 唯一
                        is_duplicate = any(
                            e['host'] == new_entry['host'] and
                            e['port'] == new_entry['port'] and
                            e['path'] == new_entry['path']
                            for e in ssh_list
                        )

                        if not is_duplicate:
                            ssh_list.append(new_entry)

                    with open(self.ssh_config_file, 'w', encoding='utf-8') as f:
                        json.dump(ssh_list, f, ensure_ascii=False, indent=4)

                    self.refresh_remote_envs()
                    InfoBar.success(self.tr("扫描完成"), f"成功添加 {len(found_paths)} 个环境", parent=self)

                except Exception as e:
                    InfoBar.error(self.tr("保存失败"), str(e), parent=self)

            # 信号连接
            self.scan_worker.output_signal.connect(handle_output)
            self.scan_worker.finished_signal.connect(on_process_finished)

            # 如果 Worker 有错误信号也连上，防止连接失败导致卡死
            if hasattr(self.scan_worker, 'error_signal'):
                self.scan_worker.error_signal.connect(lambda err: (
                    self.stateTooltip.get().close() if hasattr(self, 'stateTooltip') else None,
                    InfoBar.error(self.tr("连接失败"), str(err), parent=self)
                ))

            self.scan_worker.start()

    def edit_ssh_env_dialog(self):
        if self.remoteEnvCombo.currentIndex() == -1: return
        old_data = self.remoteEnvCombo.currentData()
        d = SSHAddrDialog(self, data=old_data)
        if d.exec():
            new_info = d.get_info()
            if os.path.exists(self.ssh_config_file):
                with open(self.ssh_config_file, 'r', encoding='utf-8') as f:
                    ssh_list = json.load(f)
                for i, env in enumerate(ssh_list):
                    if env["name"] == old_data["name"] and env["host"] == old_data["host"]:
                        ssh_list[i] = new_info
                        break
                with open(self.ssh_config_file, 'w', encoding='utf-8') as f:
                    json.dump(ssh_list, f, ensure_ascii=False, indent=4)
                self.refresh_remote_envs()

    def delete_ssh_env(self):
        if self.remoteEnvCombo.currentIndex() == -1: return
        name = self.remoteEnvCombo.currentData()["name"]
        if MessageBox(self.tr("确认"), f"{self.tr('确定删除 SSH 配置')} {name}?", self).exec():
            if os.path.exists(self.ssh_config_file):
                with open(self.ssh_config_file, 'r', encoding='utf-8') as f:
                    ssh_list = json.load(f)
                ssh_list = [e for e in ssh_list if e["name"] != name]
                with open(self.ssh_config_file, 'w', encoding='utf-8') as f:
                    json.dump(ssh_list, f, ensure_ascii=False, indent=4)
            self.refresh_remote_envs()

    def install_default_packages(self):
        if not self.current_env_data:
            InfoBar.warning(self.tr("警告"), self.tr("请先选择环境"), parent=self)
            return
        pkgs = self.config.default_packages.value
        if not pkgs:
            InfoBar.warning(self.tr("提示"), self.tr("未配置默认安装包"), parent=self)
            return
        pkgs_str = " ".join(pkgs)
        self.run_pip_command(self.tr("安装"), pkgs_str, force_no_uv=True)

    def create_env(self, window=None):
        v_dlg = CustomComboDialog(self.tr("选择 Python 版本"), list(self.config.python_versions.value), 0,
                                  window or self)
        if v_dlg.exec_():
            ver = v_dlg.get_text()
            n_dlg = CustomInputDialog(self.tr("环境名称"), currenttext=ver, parent=window or self)
            if n_dlg.exec_():
                name = n_dlg.get_text().strip() or ver
                self._log_color(f"> {self.tr('正在创建环境')} {name}...", "#abb2bf")

                def _on_creation_finished(result):
                    st.close()
                    if result:
                        self.refresh_env_list()
                        self.env_changed.emit()
                        self._log_color(f"> {self.tr('环境创建成功，正在切换')}...", "#98c379")
                        self.change_env(name)
                        pkgs = self.config.default_packages.value
                        if pkgs:
                            self._log_color(f"> {self.tr('检测到默认包配置，开始发布自动安装任务')}...", "#61afef")
                            self.install_default_packages()
                        else:
                            self._log_color(f"> {self.tr('未配置默认包，流程结束')}。", "#abb2bf")
                    else:
                        self._log_color(self.tr('环境创建失败'), "#e06c75")

                try:
                    self.mgr.install_finished.disconnect()
                except TypeError:
                    pass

                self.mgr.install_finished.connect(_on_creation_finished)
                self.mgr.download_and_install(ver, env_name=name, log_callback=lambda m: self._log_color(m, "#abb2bf"))
                st = StateToolTip(self.tr("正在安装"), self.tr("请稍候..."), window or self)
                st.show()

    def clone_env(self):
        envs = self.mgr.list_envs()
        if not envs: return
        s_dlg = CustomComboDialog(self.tr("源环境"), envs, 0, self)
        if s_dlg.exec_():
            src = s_dlg.get_text()
            t_dlg = CustomInputDialog(self.tr("新环境名称"), currenttext=f"{src}_clone", parent=self)
            if t_dlg.exec_():
                tar = t_dlg.get_text().strip()
                self.mgr.clone_env(src, tar, log_callback=lambda m: self._log_color(m, "#abb2bf"))
                st = StateToolTip(self.tr("正在克隆"), self.tr("请稍候..."), self)
                st.show()
                self.mgr.install_finished.connect(
                    lambda r: (st.close(), self.refresh_env_list(), self.env_changed.emit())
                )

    def delete_env(self):
        if not self.current_env: return
        if MessageBox(self.tr("确认"), f"{self.tr('删除环境')} {self.current_env}?", self).exec():
            self.mgr.remove_env(self.current_env)
            st = StateToolTip(self.tr("正在删除"), self.tr("请稍候..."), self)
            st.show()
            self.mgr.remove_finished.connect(
                lambda r: (st.close(), self.refresh_env_list(), self.env_changed.emit())
            )

    def _cleanup_broken_package_metadata(self, log_text, env_path):
        """
        解析错误日志，定位损坏的包元数据文件夹并删除
        """
        # 匹配规则 1: uv 的 uninstall-no-record-file 错误
        # 匹配规则 2: os error 2 (系统找不到指定的文件) 指向的 METADATA 路径
        patterns = [
            r"Cannot uninstall ([\w\-\.]+) None",
            r"failed to open file `(.+?\.dist-info)\\METADATA`"
        ]

        # 兼容 Windows 与 macOS/Linux 的 site-packages 路径
        env_path_obj = Path(env_path)
        if env_path_obj.is_file():
            env_path_obj = env_path_obj.parent
        env_root = env_path_obj.parent if env_path_obj.name in ("bin", "Scripts") else env_path_obj

        site_packages = None
        if platform.system() == "Windows":
            win_site = env_root / "Lib" / "site-packages"
            if win_site.exists():
                site_packages = str(win_site)
            else:
                # 针对某些环境结构的适配
                fallback = env_root.parent / "Lib" / "site-packages"
                if fallback.exists():
                    site_packages = str(fallback)
        else:
            lib_dir = env_root / "lib"
            if lib_dir.exists():
                candidates = sorted(lib_dir.glob("python*/site-packages"))
                if candidates:
                    site_packages = str(candidates[-1])

        cleaned_folders = []

        # 尝试根据路径直接匹配 (最准确)
        if "METADATA" in log_text:
            match = re.search(r"[`'](.+?\.dist-info)[\\/]METADATA[`']", log_text)
            if match:
                folder_path = match.group(1)
                if os.path.exists(folder_path):
                    try:
                        shutil.rmtree(folder_path)
                        cleaned_folders.append(os.path.basename(folder_path))
                    except Exception as e:
                        self._log_color(f"清理失败: {str(e)}", "#e06c75")

        # 尝试根据包名模糊匹配
        if "uninstall-no-record-file" in log_text:
            match = re.search(r"Cannot uninstall ([\w\-\.]+)", log_text)
            if match:
                pkg_name = match.group(1).replace("-", "_").lower()
                if site_packages and os.path.exists(site_packages):
                    for folder in os.listdir(site_packages):
                        # 寻找该包对应的 .dist-info 文件夹
                        if folder.lower().startswith(pkg_name) and folder.endswith(".dist-info"):
                            full_path = os.path.join(site_packages, folder)
                            try:
                                shutil.rmtree(full_path)
                                cleaned_folders.append(folder)
                            except:
                                pass

        return cleaned_folders
