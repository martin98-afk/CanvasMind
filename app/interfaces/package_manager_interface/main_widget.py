# -*- coding: utf-8 -*-
import functools
import json
import os
import platform
import re
from urllib.parse import urlparse

from PyQt5.QtCore import pyqtSignal, QProcess, Qt, QTimer, QSize, QPoint
from PyQt5.QtGui import QTextCursor, QColor, QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from PyQt5.QtWidgets import (
    QWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QFrame, QAbstractItemView, QStackedWidget
)
from qfluentwidgets import (
    ComboBox, PrimaryPushButton, TableWidget,
    FluentIcon, InfoBar, SearchLineEdit, TextEdit, MessageBox,
    StateToolTip, SimpleCardWidget,
    TransparentToolButton, IconWidget, CaptionLabel, Pivot,
    RoundMenu, Action
)
from qfluentwidgets import (LineEdit,
                            BodyLabel, StrongBodyLabel)

from app.interfaces.package_manager_interface.utils.package_list_thread import PackageListThread
from app.interfaces.package_manager_interface.utils.ssh_exec_thread import SSHExecThread
from app.interfaces.package_manager_interface.widgets.ssh_confiig_dialog import SSHAddrDialog
from app.utils.config import Settings
from app.utils.env_operation import EnvironmentManager
from app.utils.utils import get_icon
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
        self.process = None
        self.current_env = None
        self.current_env_data = None
        self.pkgs_data = []
        self.config = Settings.get_instance()

        self.ssh_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ssh_envs_cache.json")

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(16, 16, 16, 16)

        self.pivot = Pivot(self)
        self.pivot.addItem("local", "本地环境", lambda: self.on_mode_changed("local"))
        self.pivot.addItem("remote", "远程 SSH 环境", lambda: self.on_mode_changed("remote"))

        self.splitter = ModernSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(5)

        leftWidget = QWidget()
        leftLayout = QVBoxLayout(leftWidget)
        leftLayout.setContentsMargins(0, 0, 5, 0)
        searchLayout = QHBoxLayout()
        listIcon = IconWidget(FluentIcon.LIBRARY, self)
        listIcon.setFixedSize(24, 24)
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索包名 (Ctrl+F)")
        self.searchEdit.setFixedWidth(240)
        self.searchEdit.textChanged.connect(self.on_search_text_changed)
        self.searchEdit.searchSignal.connect(self.on_search_text_changed)
        self.searchEdit.clearSignal.connect(self.on_search_text_changed)
        searchLayout.addWidget(listIcon)
        searchLayout.addWidget(StrongBodyLabel("已安装包列表", self))
        searchLayout.addStretch(1)
        searchLayout.addWidget(self.searchEdit)

        self.packageTable = TableWidget(self)
        self._setup_package_table()
        leftLayout.addLayout(searchLayout)
        leftLayout.addWidget(self.packageTable)

        self.rightCard = SimpleCardWidget(self)
        rightLayout = QVBoxLayout(self.rightCard)

        self.titleLayout = QHBoxLayout()
        titleVBox = QVBoxLayout()

        envIcon = IconWidget(get_icon("python"), self)
        envIcon.setFixedSize(32, 32)
        statusInfoLayout = QVBoxLayout()
        self.pyVersionLabel = CaptionLabel("Python 版本: --", self)
        self.remoteDetailLabel = CaptionLabel("连接信息: 本地环境", self)  # 复用此标签显示连接地址
        statusInfoLayout.addWidget(self.pyVersionLabel)
        statusInfoLayout.addWidget(self.remoteDetailLabel)
        self.titleLayout.addWidget(envIcon)
        self.titleLayout.addLayout(statusInfoLayout)
        self.titleLayout.addStretch(1)
        self.titleLayout.addWidget(self.pivot)
        rightLayout.addLayout(self.titleLayout)

        self.configStack = QStackedWidget(self)

        self.localPanel = QWidget()
        lpLayout = QHBoxLayout(self.localPanel)
        lpLayout.setContentsMargins(0, 0, 0, 0)
        self.envCombo = ComboBox(self)
        self.envCombo.currentIndexChanged.connect(self.on_env_changed)

        self.refreshLocalBtn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refreshLocalBtn.setToolTip("刷新包列表")
        self.refreshLocalBtn.clicked.connect(lambda: self.load_packages(self.current_env_data))

        self.newEnvBtn = TransparentToolButton(FluentIcon.ADD, self)
        self.newEnvBtn.clicked.connect(self.create_env)
        self.cloneEnvBtn = TransparentToolButton(FluentIcon.COPY, self)
        self.cloneEnvBtn.clicked.connect(self.clone_env)
        self.deleteEnvBtn = TransparentToolButton(FluentIcon.DELETE, self)
        self.deleteEnvBtn.clicked.connect(self.delete_env)

        lpLayout.addWidget(self.envCombo, 1)
        lpLayout.addWidget(self.refreshLocalBtn)
        lpLayout.addWidget(self.newEnvBtn)
        lpLayout.addWidget(self.cloneEnvBtn)
        lpLayout.addWidget(self.deleteEnvBtn)  # 保持原名逻辑

        self.remotePanel = QWidget()
        rpLayout = QVBoxLayout(self.remotePanel)
        rpLayout.setContentsMargins(0, 0, 0, 0)
        rpTop = QHBoxLayout()
        self.remoteEnvCombo = ComboBox(self)
        self.remoteEnvCombo.currentIndexChanged.connect(self.on_env_changed)

        self.addSshBtn = TransparentToolButton(FluentIcon.ADD, self)
        self.addSshBtn.setToolTip("添加 SSH 环境")
        self.addSshBtn.clicked.connect(self.add_ssh_env_dialog)

        self.editSshBtn = TransparentToolButton(FluentIcon.EDIT, self)
        self.editSshBtn.setToolTip("编辑选中的 SSH 环境")
        self.editSshBtn.clicked.connect(self.edit_ssh_env_dialog)

        self.refreshRemoteBtn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refreshRemoteBtn.setToolTip("刷新包列表")
        self.refreshRemoteBtn.clicked.connect(lambda: self.load_packages(self.current_env_data))

        self.installDefaultBtn = TransparentToolButton(get_icon("工具包"), self)
        self.installDefaultBtn.setToolTip("安装默认依赖包")
        self.installDefaultBtn.clicked.connect(self.install_default_packages)

        self.delSshBtn = TransparentToolButton(FluentIcon.DELETE, self)
        self.delSshBtn.setToolTip("删除 SSH 环境")
        self.delSshBtn.clicked.connect(self.delete_ssh_env)

        rpTop.addWidget(self.remoteEnvCombo, 1)
        rpTop.addWidget(self.refreshRemoteBtn)
        rpTop.addWidget(self.addSshBtn)
        rpTop.addWidget(self.editSshBtn)
        rpTop.addWidget(self.installDefaultBtn)
        rpTop.addWidget(self.delSshBtn)

        rpLayout.addLayout(rpTop)

        self.configStack.addWidget(self.localPanel)
        self.configStack.addWidget(self.remotePanel)
        rightLayout.addWidget(self.configStack)

        self._init_pip_console(rightLayout)

        self.splitter.addWidget(leftWidget)
        self.splitter.addWidget(self.rightCard)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 5)
        self.mainLayout.addWidget(self.splitter)

        self.pivot.setCurrentItem("local")
        self.on_mode_changed("local")

    def _setup_package_table(self):
        self.packageTable.setColumnCount(3)
        self.packageTable.setHorizontalHeaderLabels(["名称", "版本", "操作"])
        self.packageTable.verticalHeader().hide()
        self.packageTable.setAlternatingRowColors(True)
        self.packageTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.packageTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.resizeSection(1, 120)
        header.resizeSection(2, 90)

    def _init_pip_console(self, layout):
        layout.addWidget(QFrame(frameShape=QFrame.HLine, styleSheet="color:#e5e5e5;"))
        layout.addWidget(StrongBodyLabel("命令控制台"))
        cl = QHBoxLayout()
        self.sourceCombo = ComboBox(self)
        self.sourceCombo.addItems(["在线源", "本地包"])
        self.sourceCombo.currentIndexChanged.connect(self._update_action_combo)
        self.actionCombo = ComboBox(self)
        cl.addWidget(self.sourceCombo, 1)
        cl.addWidget(self.actionCombo, 1)
        layout.addLayout(cl)

        self.packageEdit = LineEdit(self)
        self.packageEdit.setClearButtonEnabled(True)
        self.packageEdit.setPlaceholderText("输入包名...")

        self.fileSelectBtn = TransparentToolButton(FluentIcon.FOLDER, self)
        self.fileSelectBtn.setToolTip("选择本地安装包或文件夹")
        self.fileSelectBtn.clicked.connect(self.show_file_selection_menu)
        self.fileSelectBtn.hide()

        self.pkgLayout = QHBoxLayout()
        self.pkgLayout.addWidget(self.packageEdit, 1)
        self.pkgLayout.addWidget(self.fileSelectBtn)
        layout.addLayout(self.pkgLayout)

        self.execBtn = PrimaryPushButton("执行命令", self, icon=FluentIcon.PLAY)
        self.execBtn.clicked.connect(lambda: self.run_pip_command())
        layout.addWidget(self.execBtn)

        layout.addWidget(BodyLabel("终端输出:"))
        self.logEdit = TextEdit(self)
        self.logEdit.setReadOnly(True)
        self.logEdit.setStyleSheet("background-color:#282c34;color:#abb2bf;font-family:Consolas;")
        layout.addWidget(self.logEdit, 1)
        self._update_action_combo()

    def show_file_selection_menu(self):
        """显示文件/文件夹选择菜单"""
        menu = RoundMenu(parent=self)
        act_files = Action(FluentIcon.DOCUMENT, "选择多个文件", self)
        act_folder = Action(FluentIcon.FOLDER, "选择整个文件夹", self)
        act_files.triggered.connect(self.select_local_files)
        act_folder.triggered.connect(self.select_local_folder)
        menu.addAction(act_files)
        menu.addAction(act_folder)
        # 在按钮正下方弹出
        pos = self.fileSelectBtn.mapToGlobal(QPoint(0, self.fileSelectBtn.height()))
        menu.exec(pos)

    def select_local_files(self):
        """批量选择 .whl 或压缩包"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择本地安装包", "", "Python Packages (*.whl *.tar.gz *.zip);All Files (*)"
        )
        if files:
            # 用分号拼接多个路径
            self.packageEdit.setText(";".join(files))

    def select_local_folder(self):
        """选择文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择包含安装包的文件夹")
        if folder:
            self.packageEdit.setText(folder)

    def get_all_environments(self):
        all_envs = []
        for env in self.mgr.list_envs():
            all_envs.append({
                "name": env,
                "type": "local",
                "path": str(self.mgr.get_python_exe(env))
            })
        if os.path.exists(self.ssh_config_file):
            with open(self.ssh_config_file, 'r', encoding='utf-8') as f:
                ssh_list = json.load(f)
                for env in ssh_list:
                    env["type"] = "ssh"
                    all_envs.append(env)
        return all_envs

    def get_current_python_exe(self):
        if self.current_env_data:
            return self.current_env_data.get("path")
        return str(self.mgr.get_python_exe(self.current_env))

    def change_env(self, env_name):
        envs = self.mgr.list_envs()
        if env_name in envs:
            self.envCombo.setCurrentText(f"[Local] {env_name}")

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
            self.remoteDetailLabel.setText("路径: " + data["path"])  # 本地显示路径
            self.config.set(self.config.current_env_selected, data["name"])
            self.config.save_config()
        else:
            # 远程显示地址
            self.remoteDetailLabel.setText(f"地址: {data['host']}:{data.get('port', 22)}  |  用户: {data['user']}")

        self.load_packages(data)

    def load_packages(self, env_name_or_data):
        if not env_name_or_data: return
        if isinstance(env_name_or_data, str):
            env_data = {"type": "local", "name": env_name_or_data,
                        "path": str(self.mgr.get_python_exe(env_name_or_data))}
        else:
            env_data = env_name_or_data

        self.pyVersionLabel.setText("正在获取包列表...")
        self._log_color(f"> 正在同步环境: {env_data['name']} ...", "#61afef")

        if hasattr(self, '_pkg_thread') and self._pkg_thread.isRunning():
            self._pkg_thread.terminate()
            self._pkg_thread.wait()

        self._pkg_thread = PackageListThread(env_data)
        self._pkg_thread.packages_loaded.connect(self.on_load_packages)
        self._pkg_thread.error_occurred.connect(self.on_load_packages_error)
        self._pkg_thread.start()

    def on_load_packages(self, py_version, package_list):
        self.pyVersionLabel.setText(f"基础环境: {py_version}")
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
        self.pyVersionLabel.setText("获取版本失败")
        self._log_color(f"[错误] {str(e)}", "#e06c75")

    def _update_action_combo(self):
        current_source = self.sourceCombo.currentText()
        self.actionCombo.clear()
        if current_source == "在线源":
            self.fileSelectBtn.hide()
            self.actionCombo.addItems(["安装", "强制重装", "更新", "卸载"])
            self.packageEdit.setPlaceholderText("输入包名，例如 numpy")
        elif current_source == "本地包":
            self.fileSelectBtn.show()
            self.actionCombo.addItems(["离线安装", "联网安装"])
            self.packageEdit.setPlaceholderText("选择本地文件(支持多个)或文件夹...")

    def _repopulate_table(self, pkgs):
        """优化版：分批次加载表格，防止主线程卡死"""
        self.packageTable.setUpdatesEnabled(False)  # 关键：停止界面重绘
        self.packageTable.setSortingEnabled(False)
        self.packageTable.setRowCount(len(pkgs))  # 一次性分配内存，不要一个个 insertRow

        # 记录待处理的数据
        self._pending_pkgs = pkgs
        self._current_populate_index = 0
        self._batch_size = 20  # 每批处理 20 行，你可以根据流畅度调整

        # 清理之前的定时器（如果有）
        if hasattr(self, '_populate_timer'):
            self._populate_timer.stop()
        else:
            self._populate_timer = QTimer(self)
            self._populate_timer.timeout.connect(self._populate_batch)

        self._populate_timer.start(1)  # 1ms 后开始首批处理

    def _populate_batch(self):
        """分批填充逻辑"""
        start = self._current_populate_index
        end = min(start + self._batch_size, len(self._pending_pkgs))

        font = QFont("Segoe UI", 9)
        gray_color = QColor(150, 150, 150)

        for i in range(start, end):
            pkg = self._pending_pkgs[i]
            name = pkg.get("name", "")
            ver = pkg.get("version", "")

            # 名称项
            n_item = QTableWidgetItem(name)
            n_item.setFont(font)
            self.packageTable.setItem(i, 0, n_item)

            # 版本项
            v_item = QTableWidgetItem(ver)
            v_item.setFont(font)
            v_item.setForeground(gray_color)
            self.packageTable.setItem(i, 1, v_item)

            # --- 优化：只有在需要时才创建 Widget ---
            # 如果包很多，创建 Widget 是最慢的步骤
            self.packageTable.setCellWidget(i, 2, self._create_action_group(name))

        self._current_populate_index = end

        # 检查是否全部完成
        if end >= len(self._pending_pkgs):
            self._populate_timer.stop()
            self.packageTable.setSortingEnabled(True)
            self.packageTable.setUpdatesEnabled(True)  # 恢复重绘
            # 手动刷新一次布局
            self.packageTable.viewport().update()
        else:
            # 如果没做完，让出 CPU 给主进程处理 UI 事件，下一帧继续
            pass

    def _create_action_group(self, name):
        """辅助函数：创建操作按钮组"""
        bw = QWidget()
        bl = QHBoxLayout(bw)
        bl.setContentsMargins(4, 0, 4, 0)
        bl.setSpacing(4)
        bl.setAlignment(Qt.AlignCenter)

        ub = TransparentToolButton(get_icon("更新"), bw)
        ub.setToolTip(f"更新 {name}")
        ub.setFixedSize(26, 26)
        ub.setIconSize(QSize(14, 14))
        ub.clicked.connect(functools.partial(self.on_update_package_clicked, name))

        db = TransparentToolButton(FluentIcon.DELETE, bw)
        db.setToolTip(f"卸载 {name}")
        db.setFixedSize(26, 26)
        db.setIconSize(QSize(14, 14))
        db.clicked.connect(functools.partial(self.on_uninstall_package_clicked, name))

        bl.addWidget(ub)
        bl.addWidget(db)
        return bw

    def on_search_text_changed(self, text):
        """搜索防抖处理"""
        if hasattr(self, '_search_timer'):
            self._search_timer.stop()
        else:
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(lambda: self._do_search(self.searchEdit.text()))

        self._search_timer.start(200)  # 输入停止 200ms 后才执行过滤

    def _do_search(self, text):
        t = text.strip().lower()
        self.packageTable.setUpdatesEnabled(False)
        for r in range(self.packageTable.rowCount()):
            it = self.packageTable.item(r, 0)
            self.packageTable.setRowHidden(r, t not in it.text().lower() if it else False)
        self.packageTable.setUpdatesEnabled(True)

    def run_pip_command(self, action=None, package_input=None):
        if not self.current_env_data: return

        is_from_ui_btn = action is None
        ui_action = self.actionCombo.currentText()
        ui_source = self.sourceCombo.currentText()

        current_action = action or ui_action
        raw_input = package_input or self.packageEdit.text().strip()
        current_source = ui_source if is_from_ui_btn else "在线源"

        if self.current_env_data["type"] == "local":
            if not self.mgr.ensure_pip(self.current_env_data["path"], log_callback=self.logEdit.append): return

        cmd = ["-m", "pip"]

        if current_source == "在线源":
            if not raw_input and current_action != "卸载": return
            if current_action == "安装":
                cmd.extend(["install"])
                self._add_mirror_sources(cmd)
                cmd.append(raw_input)
            elif current_action == "强制重装":
                cmd.extend(["install", "--force-reinstall"])
                self._add_mirror_sources(cmd)
                cmd.append(raw_input)
            elif current_action == "更新":
                cmd.extend(["install", "-U"])
                self._add_mirror_sources(cmd)
                cmd.append(raw_input)
            elif current_action == "卸载":
                cmd.extend(["uninstall", "-y", raw_input])
        else:
            # 本地包逻辑处理
            if not raw_input: return
            cmd.append("install")
            if current_action == "离线安装":
                cmd.append("--no-index")
            else:
                self._add_mirror_sources(cmd)

            # 处理多文件/文件夹逻辑
            paths = raw_input.split(";")
            final_packages = []
            for p in paths:
                p = p.strip()
                if not p: continue
                if os.path.isdir(p):
                    # 如果是目录，搜索内部所有支持的包
                    for item in os.listdir(p):
                        if item.lower().endswith(('.whl', '.tar.gz', '.zip')):
                            final_packages.append(os.path.join(p, item))
                else:
                    final_packages.append(p)

            if not final_packages:
                self._log_color("[错误] 未找到有效的安装包文件", "#e06c75")
                return

            cmd.extend(final_packages)

        self._log_color(f"\n$ pip command: {current_action} {' '.join(cmd[2:])}", "#c678dd")
        if self.current_env_data["type"] == "local":
            self._start_process(self.current_env_data["path"], cmd)
        else:
            self._start_ssh_process(cmd)

    def _add_mirror_sources(self, cmd):
        mirrors = self.mgr.config.mirrors.value
        if not mirrors:
            return

        for i, url in enumerate(mirrors):
            # 第一个用 -i，后续用 --extra-index-url
            flag = "-i" if i == 0 else "--extra-index-url"

            parsed = urlparse(url)
            if parsed.hostname:
                cmd.extend([flag, url, "--trusted-host", parsed.hostname])

    def on_update_package_clicked(self, package_name):
        self.run_pip_command("更新", package_name)

    def on_uninstall_package_clicked(self, package_name):
        if MessageBox("确认卸载", f"确定卸载包 {package_name}？", self).exec():
            self.run_pip_command("卸载", package_name)

    def _start_process(self, python_exe, cmd):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_ready_read)
        self.process.finished.connect(self.on_finished)
        if platform.system() == "Windows":
            self.process.setProcessEnvironment(self._get_hidden_window_environment())
        self.process.start(python_exe, cmd)
        self.execBtn.setEnabled(False)

    def _get_hidden_window_environment(self):
        from PyQt5.QtCore import QProcessEnvironment
        return QProcessEnvironment.systemEnvironment()

    def on_ready_read(self):
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        self.logEdit.insertPlainText(data)
        self.logEdit.moveCursor(QTextCursor.End)

    def on_finished(self):
        self.logEdit.append("\n[完成]")
        self.execBtn.setEnabled(True)
        if self.current_env_data: self.load_packages(self.current_env_data)

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
        d = SSHAddrDialog(self)
        if d.exec():
            new_env = d.get_info()
            ssh_list = []
            if os.path.exists(self.ssh_config_file):
                with open(self.ssh_config_file, 'r', encoding='utf-8') as f:
                    ssh_list = json.load(f)

            ssh_list.append(new_env)
            with open(self.ssh_config_file, 'w', encoding='utf-8') as f:
                json.dump(ssh_list, f, ensure_ascii=False, indent=4)

            self.refresh_remote_envs()

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
        if MessageBox("确认删除", f"确定删除 SSH 配置 {name}？", self).exec():
            if os.path.exists(self.ssh_config_file):
                with open(self.ssh_config_file, 'r', encoding='utf-8') as f:
                    ssh_list = json.load(f)
                ssh_list = [e for e in ssh_list if e["name"] != name]
                with open(self.ssh_config_file, 'w', encoding='utf-8') as f:
                    json.dump(ssh_list, f, ensure_ascii=False, indent=4)
            self.refresh_remote_envs()

    def _start_ssh_process(self, cmd):
        self.execBtn.setEnabled(False)
        self._ssh_thread = SSHExecThread(self.current_env_data, cmd)
        self._ssh_thread.output_signal.connect(lambda x: self.logEdit.insertPlainText(x))
        self._ssh_thread.finished_signal.connect(self.on_finished)
        self._ssh_thread.start()

    def install_default_packages(self):
        if not self.current_env_data:
            InfoBar.warning("警告", "请先选择环境", parent=self)
            return
        pkgs = self.config.default_packages.value
        if not pkgs:
            InfoBar.warning("提示", "未配置默认安装包列表", parent=self)
            return
        pkgs_str = " ".join(pkgs)
        self.logEdit.append(f"\n> 准备安装默认包: {pkgs_str}")
        self.run_pip_command("安装", pkgs_str)

    def create_env(self, window=None):
        v_dlg = CustomComboDialog("Python 版本", list(self.config.python_versions.value), 0, window or self)
        if v_dlg.exec_():
            ver = v_dlg.get_text()
            n_dlg = CustomInputDialog("环境名称", currenttext=ver, parent=window or self)
            if n_dlg.exec_():
                name = n_dlg.get_text().strip() or ver
                self.mgr.download_and_install(ver, env_name=name, log_callback=self.logEdit.append)
                st = StateToolTip("安装中", "请稍候...", window or self)
                st.show()
                self.mgr.install_finished.connect(lambda r: (st.close(), self.refresh_env_list()))

    def clone_env(self):
        envs = self.mgr.list_envs()
        if not envs: return
        s_dlg = CustomComboDialog("源环境", envs, 0, self)
        if s_dlg.exec_():
            src = s_dlg.get_text()
            t_dlg = CustomInputDialog("新环境名", currenttext=f"{src}_clone", parent=self)
            if t_dlg.exec_():
                tar = t_dlg.get_text().strip()
                self.mgr.clone_env(src, tar, log_callback=self.logEdit.append)
                st = StateToolTip("克隆中", "请稍候...", self)
                st.show()
                self.mgr.install_finished.connect(lambda r: (st.close(), self.refresh_env_list()))

    def delete_env(self):
        if not self.current_env: return
        if MessageBox("确认", f"删除环境 {self.current_env}？", self).exec():
            self.mgr.remove_env(self.current_env)
            st = StateToolTip("删除中", "请稍候...", self)
            st.show()
            self.mgr.remove_finished.connect(lambda r: (st.close(), self.refresh_env_list()))

    def _log_color(self, text, color):
        self.logEdit.append(f'<span style="color:{color};">{text}</span>')
        self.logEdit.moveCursor(QTextCursor.End)
        # 获取滚动条对象
        scrollbar = self.logEdit.verticalScrollBar()
        # 强制设置到最大值
        scrollbar.setValue(scrollbar.maximum())