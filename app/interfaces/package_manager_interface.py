# -*- coding: utf-8 -*-
import functools
import json
import platform
import re
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal, QProcess, Qt, QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView, QSizePolicy, QFileDialog
)
from loguru import logger
from qfluentwidgets import (
    ComboBox, PrimaryPushButton, LineEdit, TableWidget,
    FluentIcon, InfoBar, SearchLineEdit, TextEdit, PushButton, MessageBox, BodyLabel, StateToolTip
)

from app.utils.config import Settings
from app.utils.env_operation import EnvironmentManager, get_uv_path
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.dialog_widget.custom_messagebox import CustomComboDialog, CustomInputDialog


class PackageListThread(QThread):
    packages_loaded = pyqtSignal(str)
    error_occurred = pyqtSignal(Exception)

    def __init__(self, python_exe, parent=None):
        super().__init__(parent)
        self.python_exe = python_exe

    def run(self):
        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            result = subprocess.run(
                [get_uv_path(), "pip", "list", "--format=json", "--python", self.python_exe],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
                **kwargs
            )
            self.packages_loaded.emit(result.stdout.strip())
        except Exception as e:
            self.error_occurred.emit(e)


class EnvManagerUI(QWidget):
    env_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.home = parent
        self.setObjectName("EnvManagerUI")
        self.resize(1000, 600)
        StyleSheet.PACKAGE_MANAGER.apply(self)

        self.mgr = EnvironmentManager()
        self.process = None
        self.current_env = None
        self.pkgs_data = []

        # ---------- 顶部环境选择 ----------
        self.envCombo = ComboBox(self)
        self.refresh_env_list()
        self.envCombo.currentIndexChanged.connect(self.on_env_changed)

        self.newEnvBtn = PrimaryPushButton("新建", self, icon=FluentIcon.ADD)
        self.newEnvBtn.clicked.connect(self.create_env)

        self.cloneEnvBtn = PrimaryPushButton("克隆", self, icon=FluentIcon.COPY)
        self.cloneEnvBtn.clicked.connect(self.clone_env)

        self.deleteEnvBtn = PushButton("删除", self, icon=FluentIcon.DELETE)
        self.deleteEnvBtn.clicked.connect(self.delete_env)

        topLayout = QHBoxLayout()
        topLayout.addWidget(BodyLabel("Python环境:"))
        topLayout.addWidget(self.envCombo, stretch=1)
        topLayout.addWidget(self.newEnvBtn)
        topLayout.addWidget(self.cloneEnvBtn)
        topLayout.addWidget(self.deleteEnvBtn)

        # ---------- 第二行操作 ----------
        self.sourceCombo = ComboBox(self)
        self.sourceCombo.addItems(["在线", "本地"])
        self.sourceCombo.currentIndexChanged.connect(self._update_action_combo)

        self.actionCombo = ComboBox(self)

        self.packageEdit = LineEdit(self)
        self.packageEdit.setPlaceholderText("输入包名或本地文件路径...")

        self.execBtn = PrimaryPushButton("执行", self, icon=FluentIcon.PLAY)
        self.execBtn.clicked.connect(lambda: self.run_uv_command())

        self._update_action_combo()
        # ------------------------------

        actionLayout = QHBoxLayout()
        actionLayout.addWidget(self.sourceCombo)
        actionLayout.addWidget(self.actionCombo)
        actionLayout.addWidget(self.packageEdit, stretch=1)
        actionLayout.addWidget(self.execBtn)

        # ---------- 包列表区域 ----------
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索已安装包...")
        self.searchEdit.textChanged.connect(self.on_search_text_changed)

        self.packageTable = TableWidget(self)
        self.packageTable.setColumnCount(3)
        self.packageTable.setHorizontalHeaderLabels(["包名", "版本", "操作"])

        header = self.packageTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.packageTable.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        packageLayout = QVBoxLayout()
        packageLayout.addLayout(topLayout)
        packageLayout.addLayout(actionLayout)
        packageLayout.addWidget(self.searchEdit)
        packageLayout.addWidget(self.packageTable, stretch=1)

        packageWidget = QWidget()
        packageWidget.setLayout(packageLayout)

        # ---------- 日志窗口 ----------
        self.logEdit = TextEdit(self)
        self.logEdit.setReadOnly(True)

        splitter = ModernSplitter(Qt.Horizontal)
        splitter.addWidget(packageWidget)
        splitter.addWidget(self.logEdit)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        mainLayout = QVBoxLayout(self)
        mainLayout.addWidget(splitter, stretch=1)
        self.setLayout(mainLayout)

        if self.envCombo.count() > 0:
            self.on_env_changed()
        else:
            self.logEdit.append("⚠️ 没有检测到任何环境，请点击\"新建环境\"创建。")

    def _update_action_combo(self):
        current_source = self.sourceCombo.currentText()
        self.actionCombo.clear()
        if current_source == "在线":
            self.actionCombo.addItems(["安装", "强制重装", "更新", "卸载"])
            self.packageEdit.setPlaceholderText("输入包名，例如 numpy 或 numpy==1.24.0")
        elif current_source == "本地":
            self.actionCombo.addItems(["离线", "联网"])
            self.packageEdit.setPlaceholderText("选择本地 WHL 文件或输入路径...")

    def get_current_python_exe(self):
        return self.mgr.get_python_exe(self.current_env)

    def refresh_env_list(self):
        self.envCombo.clear()
        envs = self.mgr.list_envs()
        self.envCombo.addItems(envs)

    def on_env_changed(self):
        self.current_env = self.envCombo.currentText()
        if self.current_env:
            self.load_packages(self.current_env)

    def load_packages(self, env_name):
        self.logEdit.append(f"[信息] 正在加载环境 {env_name} 的包列表...")
        try:
            python_exe = str(self.mgr.get_python_exe(env_name))
        except Exception as e:
            self.logEdit.append(f"[错误] 获取 Python 路径失败: {e}")
            return

        if hasattr(self, '_pkg_thread') and self._pkg_thread.isRunning():
            self._pkg_thread.quit()
            self._pkg_thread.wait()

        self._pkg_thread = PackageListThread(python_exe)
        self._pkg_thread.packages_loaded.connect(self.on_load_packages)
        self._pkg_thread.error_occurred.connect(self.on_load_packages_error)
        self._pkg_thread.start()

    def on_load_packages(self, package_list):
        self.packageTable.setRowCount(0)
        match = re.search(r"\[.*\]", package_list, re.S)
        if match:
            pkgs = json.loads(match.group(0))
        else:
            pkgs = []
        self.pkgs_data = pkgs
        self._repopulate_table(pkgs)

    def on_load_packages_error(self, e):
        error_msg = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            error_msg = e.stderr.strip() or error_msg
        self.logEdit.append(f"[错误] 获取包列表失败: {error_msg}")

    def _repopulate_table(self, pkgs):
        self.packageTable.setRowCount(0)
        for row, pkg in enumerate(pkgs):
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            self.packageTable.insertRow(row)
            self.packageTable.setItem(row, 0, QTableWidgetItem(name))
            self.packageTable.setItem(row, 1, QTableWidgetItem(version))

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

    def on_search_text_changed(self, text):
        text = text.strip().lower()
        if not text:
            filtered = self.pkgs_data
        else:
            filtered = [p for p in self.pkgs_data if text in p.get("name", "").lower()]
        self._repopulate_table(filtered)

    # ✅ 核心：所有包操作使用 uv pip
    def run_uv_command(self, action=None, package_input=None):
        if not self.current_env:
            InfoBar.error("错误", "请选择环境", parent=self)
            return

        try:
            python_exe = str(self.mgr.get_python_exe(self.current_env))
        except Exception as e:
            InfoBar.error("错误", str(e), parent=self)
            return

        # uv 不需要 ensure_pip，可直接跳过
        source = self.sourceCombo.currentText() if action is None else "在线"
        action = self.actionCombo.currentText() if action is None else action
        package_input = self.packageEdit.text().strip() if package_input is None else package_input
        package_list = package_input.split() if package_input else []

        if source == "在线":
            if not package_list:
                InfoBar.error("错误", "请输入包名", parent=self)
                return

            cmd = [get_uv_path(), "pip"]
            if action == "安装":
                cmd.extend(["install"])
            elif action == "强制重装":
                cmd.extend(["install", "--reinstall"])  # uv 用 --reinstall
            elif action == "更新":
                cmd.extend(["install", "--upgrade"])
            elif action == "卸载":
                cmd = [get_uv_path(), "pip", "uninstall"]
            else:
                return

            if action != "卸载":
                self._add_mirror_sources(cmd)
            cmd.extend(package_list)
            cmd.extend(["--python", python_exe])

        elif source == "本地":
            file_paths = []
            if not package_list:
                file_paths, _ = QFileDialog.getOpenFileNames(
                    self,
                    "选择本地 WHL 包",
                    "",
                    "Python Wheels (*.whl);;All Files (*)"
                )
                if not file_paths:
                    return
            else:
                file_paths = package_list

            valid_whl_paths = [p for p in file_paths if p.lower().endswith('.whl')]
            invalid_paths = [p for p in file_paths if not p.lower().endswith('.whl')]
            if invalid_paths:
                InfoBar.warning("警告", f"跳过非 .whl 文件: {', '.join(invalid_paths)}", parent=self)
            if not valid_whl_paths:
                InfoBar.error("错误", "没有有效的 .whl 文件", parent=self)
                return

            cmd = [get_uv_path(), "pip", "install"]
            if "离线" in action:
                cmd.append("--no-index")
            cmd.extend(valid_whl_paths)
            self._add_mirror_sources(cmd)
            cmd.extend(["--python", python_exe])

        else:
            return

        self.logEdit.append(f"> 执行命令: {' '.join(cmd)}\n")
        self._start_process(cmd[0], cmd[1:])

    def _add_mirror_sources(self, cmd):
        mirrors = self.mgr.config.mirrors.value
        if mirrors:
            primary = mirrors[0]
            cmd.extend(["--index-url", primary])
            from urllib.parse import urlparse
            parsed = urlparse(primary)
            cmd.extend(["--trusted-host", parsed.hostname])
            for mirror in mirrors[1:]:
                cmd.extend(["--extra-index-url", mirror])
                parsed = urlparse(mirror)
                cmd.extend(["--trusted-host", parsed.hostname])

    def on_update_package_clicked(self, package_name):
        if not self.current_env:
            InfoBar.error("错误", "请选择环境", parent=self)
            return
        python_exe = str(self.mgr.get_python_exe(self.current_env))
        cmd = [get_uv_path(), "pip", "install", "--upgrade", package_name, "--python", python_exe]
        self._add_mirror_sources(cmd)
        self.logEdit.append(f"> {self.current_env} :: update {package_name}\n")
        self._start_process(cmd[0], cmd[1:])

    def on_uninstall_package_clicked(self, package_name):
        if not self.current_env:
            InfoBar.error("错误", "请选择环境", parent=self)
            return
        python_exe = str(self.mgr.get_python_exe(self.current_env))
        cmd = [get_uv_path(), "pip", "uninstall", package_name, "--python", python_exe]
        self.logEdit.append(f"> {self.current_env} :: uninstall {package_name}\n")
        self._start_process(cmd[0], cmd[1:])

    def delete_env(self):
        if not self.current_env:
            InfoBar.error("错误", "请选择要删除的环境", parent=self)
            return

        env_name = self.current_env
        msg_box = MessageBox("确认删除", f"确定要删除环境 {env_name} 吗？此操作不可恢复！", self)
        if msg_box.exec_():
            try:
                state_tooltip = StateToolTip("正在删除环境", "请稍候...", self)
                state_tooltip.move(self.home.width() - state_tooltip.width() - 40, 20)
                state_tooltip.show()
                self.mgr.remove_env(env_name)
                self.mgr.remove_finished.connect(
                    lambda: (
                        state_tooltip.close(),
                        self.refresh_env_list(),
                        InfoBar.success("成功", f"环境 {env_name} 已删除", parent=self),
                        self.env_changed.emit()
                    )
                )
                if self.envCombo.count() > 0:
                    self.envCombo.setCurrentIndex(0)
                else:
                    self.current_env = None
                    self.packageTable.setRowCount(0)
            except Exception as e:
                InfoBar.error("错误", f"删除环境失败: {str(e)}", parent=self)

    def _start_process(self, program, args):
        if self.process and self.process.state() != QProcess.NotRunning:
            try:
                self.process.kill()
                self.process.waitForFinished(3000)
            except Exception as e:
                print(f"终止进程时出错: {e}")

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_ready_read)
        self.process.readyReadStandardError.connect(self.on_ready_read)
        self.process.finished.connect(self.on_finished)

        if platform.system() == "Windows":
            from PyQt5.QtCore import QProcessEnvironment
            env = QProcessEnvironment.systemEnvironment()
            self.process.setProcessEnvironment(env)

        self.process.start(program, args)

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
        if self.current_env:
            QTimer.singleShot(1000, lambda: self.load_packages(self.current_env))

    def create_env(self, window=None):
        # ✅ 改为通用 Python 版本列表（不再依赖 Miniconda）
        available_versions = Settings.get_instance().python_versions.value

        version_dialog = CustomComboDialog(
            "选择 Python 版本",
            available_versions,
            0,
            window or self
        )

        if version_dialog.exec_():
            version = version_dialog.get_text()
            env_name_dialog = CustomInputDialog(
                f"输入环境名称（默认为 {version}）",
                placeholder="请输入环境名称",
                currenttext=version,
                parent=window or self
            )

            if env_name_dialog.exec_():
                env_name = env_name_dialog.get_text().strip() or version
                try:
                    self.mgr.create_env(version, env_name, log_callback=self.logEdit.append)
                    state_tooltip = StateToolTip("正在创建环境", "请稍候...", window or self)
                    state_tooltip.move(self.home.width() - state_tooltip.width() - 40, 20)
                    state_tooltip.show()
                    self.mgr.install_finished.connect(
                        lambda result: (
                            state_tooltip.close(),
                            self.refresh_env_list(),
                            InfoBar.success("成功", f"环境 {env_name} 已创建", parent=window or self)
                            if "失败" not in result and "错误" not in result else
                            InfoBar.error("错误", result, parent=window or self),
                            self.envCombo.setCurrentText(env_name)
                            if "失败" not in result and "错误" not in result else None,
                            self.env_changed.emit()
                        )
                    )
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())
                    InfoBar.error("错误", str(e), parent=window or self)

    def clone_env(self):
        envs = self.mgr.list_envs()
        if not envs:
            InfoBar.warning("警告", "没有可用的环境可供克隆", parent=self)
            return

        source_env_dialog = CustomComboDialog("选择要克隆的源环境", envs, 0, self)
        if source_env_dialog.exec_():
            source_env = source_env_dialog.get_text()

            target_env_dialog = CustomInputDialog(
                f"输入新环境名称（基于 {source_env}）",
                placeholder="请输入环境名称",
                currenttext=f"{source_env}_clone",
                parent=self
            )

            if target_env_dialog.exec_():
                target_env = target_env_dialog.get_text().strip()
                if not target_env:
                    InfoBar.warning("警告", "请输入环境名称", parent=self)
                    return

                try:
                    self.mgr.clone_env(source_env, target_env, log_callback=self.logEdit.append)
                    state_tooltip = StateToolTip("正在克隆环境", "请稍候...", self)
                    state_tooltip.move(self.home.width() - state_tooltip.width() - 30, 20)
                    state_tooltip.show()
                    self.mgr.install_finished.connect(
                        lambda result: (
                            state_tooltip.close(),
                            self.refresh_env_list(),
                            InfoBar.success("成功", f"环境 {target_env} 已克隆", parent=self)
                            if "失败" not in result and "错误" not in result else
                            InfoBar.error("错误", result, parent=self),
                            self.envCombo.setCurrentText(target_env)
                            if "失败" not in result and "错误" not in result else None,
                            self.env_changed.emit()
                        )
                    )
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())
                    InfoBar.error("错误", str(e), parent=self)