# -*- coding: utf-8 -*-
import functools
import json
import platform
import re
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal, QProcess, Qt, QTimer, QSize
from PyQt5.QtGui import QTextCursor, QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView, QFileDialog, QFrame, QAbstractItemView
)
from qfluentwidgets import (
    ComboBox, PrimaryPushButton, LineEdit, TableWidget,
    FluentIcon, InfoBar, SearchLineEdit, TextEdit, MessageBox,
    BodyLabel, StateToolTip, StrongBodyLabel, CardWidget, TransparentToolButton,
    IconWidget, CaptionLabel
)

from app.utils.config import Settings
from app.utils.env_operation import EnvironmentManager
from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.dialog_widget.custom_messagebox import CustomComboDialog, CustomInputDialog


class PackageListThread(QThread):
    # 修改信号：第一个参数是 python 版本，第二个是包列表 json
    packages_loaded = pyqtSignal(str, str)
    error_occurred = pyqtSignal(Exception)

    def __init__(self, python_exe, parent=None):
        super().__init__(parent)
        self.python_exe = python_exe

    def run(self):
        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            # 1. 获取 Python 版本信息
            version_res = subprocess.run(
                [self.python_exe, "--version"],
                capture_output=True,
                text=True,
                check=True,
                **kwargs
            )
            py_version = version_res.stdout.strip() # 例如 "Python 3.10.5"

            # 2. 获取 Pip 包列表
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
                **kwargs
            )
            self.packages_loaded.emit(py_version, result.stdout.strip())
        except Exception as e:
            self.error_occurred.emit(e)


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
        self.pkgs_data = []
        self.config = Settings.get_instance()

        # ==========================================================
        #  布局重构：左右分栏 (IDE Style)
        # ==========================================================

        # 主分割器 (左右)
        self.splitter = ModernSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(5)

        # ----------------------------------------------------------
        # 左侧：包列表区域
        # ----------------------------------------------------------
        leftWidget = QWidget()
        leftLayout = QVBoxLayout(leftWidget)
        leftLayout.setContentsMargins(0, 0, 5, 0)
        leftLayout.setSpacing(10)

        # 1. 顶部搜索栏 (整合在左侧上方)
        searchLayout = QHBoxLayout()
        # 这里的 IconWidget 只是为了装饰，表示这是一个列表
        listIcon = IconWidget(FluentIcon.LIBRARY, self)
        listIcon.setFixedSize(24, 24)

        titleLabel = StrongBodyLabel("已安装包列表", self)

        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索包名 (Ctrl+F)")
        self.searchEdit.setFixedWidth(240)
        self.searchEdit.textChanged.connect(self.on_search_text_changed)
        self.searchEdit.searchSignal.connect(self.on_search_text_changed)

        searchLayout.addWidget(listIcon)
        searchLayout.addWidget(titleLabel)
        searchLayout.addStretch(1)
        searchLayout.addWidget(self.searchEdit)

        # 2. 表格
        self.packageTable = TableWidget(self)
        self.packageTable.setColumnCount(3)
        self.packageTable.setHorizontalHeaderLabels(["名称", "版本", "操作"])

        # 优化表格样式
        self.packageTable.verticalHeader().hide()
        self.packageTable.setBorderVisible(True)
        self.packageTable.setBorderRadius(8)
        self.packageTable.setAlternatingRowColors(True)
        self.packageTable.setShowGrid(False)
        self.packageTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.packageTable.setSelectionMode(QAbstractItemView.SingleSelection)
        self.packageTable.setWordWrap(False)

        # 列宽策略
        header = self.packageTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 名称自适应
        header.setSectionResizeMode(1, QHeaderView.Fixed)  # 版本固定
        header.resizeSection(1, 120)
        header.setSectionResizeMode(2, QHeaderView.Fixed)  # 操作固定
        header.resizeSection(2, 90)

        leftLayout.addLayout(searchLayout)
        leftLayout.addWidget(self.packageTable)

        # ----------------------------------------------------------
        # 右侧：控制面板 + 日志 (使用 CardWidget 聚合)
        # ----------------------------------------------------------
        self.rightCard = CardWidget(self)
        rightLayout = QVBoxLayout(self.rightCard)
        rightLayout.setContentsMargins(15, 15, 15, 15)
        rightLayout.setSpacing(15)

        # 3. 环境管理区域 (顶部)
        # --- UI 优化：增加版本显示标签 ---
        envTitleLayout = QHBoxLayout()
        envIcon = IconWidget(get_icon("python"), self)
        envIcon.setFixedSize(20, 20)

        titleVBoxLayout = QVBoxLayout()  # 使用垂直布局包裹标题和版本号
        titleVBoxLayout.setSpacing(0)

        self.titleLabel = StrongBodyLabel("环境管理", self)
        self.pyVersionLabel = CaptionLabel("Python 版本: --", self)  # 用于显示具体版本号

        titleVBoxLayout.addWidget(self.titleLabel)
        titleVBoxLayout.addWidget(self.pyVersionLabel)

        envTitleLayout.addWidget(envIcon)
        envTitleLayout.addLayout(titleVBoxLayout)
        envTitleLayout.addStretch(1)

        # 环境下拉框
        self.envCombo = ComboBox(self)
        self.refresh_env_list()
        self.envCombo.currentIndexChanged.connect(self.on_env_changed)

        # 环境操作按钮组 (一行排列)
        envBtnLayout = QHBoxLayout()
        envBtnLayout.setSpacing(5)

        self.newEnvBtn = TransparentToolButton(FluentIcon.ADD, self)
        self.newEnvBtn.setToolTip("新建环境")
        self.newEnvBtn.clicked.connect(self.create_env)

        self.cloneEnvBtn = TransparentToolButton(FluentIcon.COPY, self)
        self.cloneEnvBtn.setToolTip("克隆环境")
        self.cloneEnvBtn.clicked.connect(self.clone_env)

        self.deleteEnvBtn = TransparentToolButton(FluentIcon.DELETE, self)
        self.deleteEnvBtn.setToolTip("删除环境")
        self.deleteEnvBtn.clicked.connect(self.delete_env)

        envBtnLayout.addWidget(self.envCombo, 1)  # 下拉框占主要
        envBtnLayout.addWidget(self.newEnvBtn)
        envBtnLayout.addWidget(self.cloneEnvBtn)
        envBtnLayout.addWidget(self.deleteEnvBtn)

        # 4. PIP 命令控制台
        pipTitle = StrongBodyLabel("命令控制台", self)

        # 来源与动作 (一行)
        comboLayout = QHBoxLayout()
        self.sourceCombo = ComboBox(self)
        self.sourceCombo.addItems(["在线源", "本地包"])
        self.sourceCombo.currentIndexChanged.connect(self._update_action_combo)

        self.actionCombo = ComboBox(self)

        comboLayout.addWidget(self.sourceCombo, 1)
        comboLayout.addWidget(self.actionCombo, 1)

        # 输入框
        self.packageEdit = LineEdit(self)
        self.packageEdit.setClearButtonEnabled(True)
        self.packageEdit.setPlaceholderText("输入包名...")

        # 执行按钮
        self.execBtn = PrimaryPushButton("执行命令", self, icon=FluentIcon.PLAY)
        self.execBtn.clicked.connect(lambda: self.run_pip_command())

        # 5. 终端日志
        logLabel = BodyLabel("终端输出:", self)
        self.logEdit = TextEdit(self)
        self.logEdit.setReadOnly(True)
        # 仿终端样式
        self.logEdit.setStyleSheet("""
            QTextEdit {
                background-color: #282c34;
                color: #abb2bf;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #3e4451;
                border-radius: 6px;
                padding: 4px;
            }
        """)

        # 分割线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("color: #e5e5e5;")

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #e5e5e5;")

        # 右侧布局组装
        rightLayout.addLayout(envTitleLayout)
        rightLayout.addLayout(envBtnLayout)
        rightLayout.addWidget(line1)

        rightLayout.addWidget(pipTitle)
        rightLayout.addLayout(comboLayout)
        rightLayout.addWidget(self.packageEdit)
        rightLayout.addWidget(self.execBtn)
        rightLayout.addWidget(line2)

        rightLayout.addWidget(logLabel)
        rightLayout.addWidget(self.logEdit, 1)  # 日志占据剩余高度

        self._update_action_combo()  # 初始化 combo

        # ----------------------------------------------------------
        # 总布局
        # ----------------------------------------------------------
        self.splitter.addWidget(leftWidget)
        self.splitter.addWidget(self.rightCard)
        self.splitter.setStretchFactor(0, 3)  # 左 70%
        self.splitter.setStretchFactor(1, 5)  # 右 30%

        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(16, 16, 16, 16)
        mainLayout.addWidget(self.splitter)
        self.setLayout(mainLayout)

        # 初始化逻辑保持不变
        if self.envCombo.count() > 0:
            self.on_env_changed()
        else:
            self.logEdit.append("⚠️ 没有检测到任何环境，请在右侧点击“+”创建。")

    def _update_action_combo(self):
        """根据 sourceCombo 的选择更新 actionCombo 的内容"""
        current_source = self.sourceCombo.currentText()
        self.actionCombo.clear()
        if current_source == "在线源":
            self.actionCombo.addItems(["安装", "强制重装", "更新", "卸载"])
            self.packageEdit.setPlaceholderText("输入包名，例如 numpy")
        elif current_source == "本地包":
            self.actionCombo.addItems(["离线安装", "联网安装"])
            self.packageEdit.setPlaceholderText("选择本地 .whl 文件路径...")

    def get_current_python_exe(self):
        """获取当前环境 Python 的路径"""
        return self.mgr.get_python_exe(self.current_env)

    def change_env(self, env_name):
        envs = self.mgr.list_envs()
        if env_name in envs:
            self.envCombo.setCurrentText(env_name)

    def refresh_env_list(self):
        self.envCombo.clear()
        envs = self.mgr.list_envs()
        self.envCombo.addItems(envs)
        if len(envs) > 0 and self.config.current_env_selected.value in envs:
            self.envCombo.setCurrentText(self.config.current_env_selected.value)

    def on_env_changed(self):
        self.mgr.refresh_env_config()
        self.current_env = self.envCombo.currentText()
        self.config.set(self.config.current_env_selected, self.current_env)
        self.config.save_config()
        if self.current_env:
            self.load_packages(self.current_env)

    def load_packages(self, env_name):
        """启动线程获取包列表"""
        self.pyVersionLabel.setText("正在获取版本...")  # 加载状态提示
        self._log_color(f"> 正在加载环境: {env_name} ...", "#61afef")
        try:
            python_exe = str(self.mgr.get_python_exe(env_name))
        except Exception as e:
            self.logEdit.append(f"[错误] 获取 Python 路径失败: {e}")
            self.pyVersionLabel.setText("获取版本失败")
            return

        if hasattr(self, '_pkg_thread') and self._pkg_thread.isRunning():
            self._pkg_thread.quit()
            self._pkg_thread.wait()

        self._pkg_thread = PackageListThread(python_exe)
        # 注意：这里的槽函数接收两个参数了
        self._pkg_thread.packages_loaded.connect(self.on_load_packages)
        self._pkg_thread.error_occurred.connect(self.on_load_packages_error)
        self._pkg_thread.start()

    def on_load_packages(self, py_version, package_list):
        """成功加载后的回调"""
        self.pyVersionLabel.setText(f"基础环境: {py_version}")  # 更新 UI 上的版本号

        self.packageTable.setRowCount(0)
        try:
            match = re.search(r"\[.*\]", package_list, re.S)
            if match:
                pkgs = json.loads(match.group(0))
            else:
                pkgs = []
        except:
            pkgs = []

        self.pkgs_data = pkgs
        self._repopulate_table(pkgs)
        self._log_color(f"> 加载完成，{py_version} 共 {len(pkgs)} 个包。", "#98c379")

    def on_load_packages_error(self, e):
        self.pyVersionLabel.setText("获取版本失败")
        error_msg = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            error_msg = e.stderr.strip() or error_msg
        self._log_color(f"[错误] 获取包列表失败: {error_msg}", "#e06c75")  # Red

    def _repopulate_table(self, pkgs):
        """根据传入 pkgs 列表刷新表格（内部使用），已美化"""
        self.packageTable.setRowCount(0)
        self.packageTable.setSortingEnabled(False)  # 关闭排序以加速插入

        font = QFont()
        font.setFamily("Segoe UI")
        font.setPointSize(9)

        for row, pkg in enumerate(pkgs):
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            self.packageTable.insertRow(row)

            # 名称
            nameItem = QTableWidgetItem(name)
            nameItem.setFont(font)
            nameItem.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.packageTable.setItem(row, 0, nameItem)

            # 版本 (稍微变灰)
            verItem = QTableWidgetItem(version)
            verItem.setFont(font)
            verItem.setForeground(QColor(150, 150, 150))
            verItem.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.packageTable.setItem(row, 1, verItem)

            # 操作按钮 (使用透明图标按钮，更简洁)
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(4)
            btn_layout.setAlignment(Qt.AlignCenter)

            update_btn = TransparentToolButton(get_icon("更新"), self)
            update_btn.setToolTip(f"更新 {name}")
            update_btn.setFixedSize(26, 26)
            update_btn.setIconSize(QSize(14, 14))
            update_btn.clicked.connect(functools.partial(self.on_update_package_clicked, name))

            uninstall_btn = TransparentToolButton(FluentIcon.DELETE, self)
            uninstall_btn.setToolTip(f"卸载 {name}")
            uninstall_btn.setFixedSize(26, 26)
            uninstall_btn.setIconSize(QSize(14, 14))
            uninstall_btn.clicked.connect(functools.partial(self.on_uninstall_package_clicked, name))

            btn_layout.addWidget(update_btn)
            btn_layout.addWidget(uninstall_btn)

            self.packageTable.setCellWidget(row, 2, btn_widget)

        self.packageTable.setSortingEnabled(True)

    def on_search_text_changed(self, text):
        """按搜索文本过滤已安装包 (优化：隐藏行而不是重新插入)"""
        text = text.strip().lower()

        # 性能优化：直接操作 UI 隐藏行，避免频繁 remove/insert
        for row in range(self.packageTable.rowCount()):
            item = self.packageTable.item(row, 0)
            if not item: continue

            pkg_name = item.text().lower()
            should_hide = text not in pkg_name
            self.packageTable.setRowHidden(row, should_hide)

    def run_pip_command(self, action=None, package_input=None):
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

        source = self.sourceCombo.currentText() if action is None else "在线源"
        action = self.actionCombo.currentText() if action is None else action
        package_input = self.packageEdit.text().strip() if package_input is None else package_input

        self._log_color(f"\n$ pip command: {action} {package_input}", "#c678dd")  # Purple

        if source == "在线源":
            package_input_list = package_input.split(" ")
            if not package_input and action != "卸载":
                InfoBar.error("错误", "请输入包名", parent=self)
                return

            if action == "安装":
                cmd = ["-m", "pip", "install"]
                self._add_mirror_sources(cmd)
                cmd.extend(package_input_list)
            elif action == "强制重装":
                cmd = ["-m", "pip", "install", "--force-reinstall"]
                self._add_mirror_sources(cmd)
                cmd.extend(package_input_list)
            elif action == "更新":
                cmd = ["-m", "pip", "install", "-U"]
                self._add_mirror_sources(cmd)
                cmd.extend(package_input_list)
            elif action == "卸载":
                if not package_input:
                    InfoBar.error("错误", "请输入要卸载的包名", parent=self)
                    return
                cmd = ["-m", "pip", "uninstall", "-y"]
                cmd.extend(package_input_list)
            else:
                return

        elif source == "本地包":
            file_paths = []
            if not package_input:
                file_paths, _ = QFileDialog.getOpenFileNames(
                    self,
                    "选择本地 WHL 包",
                    "",
                    "Python Wheels (*.whl);;All Files (*)"
                )
                if not file_paths:
                    return
            else:
                file_paths = [package_input]

            if file_paths:
                valid_whl_paths = [path for path in file_paths if path.lower().endswith('.whl')]

                if not valid_whl_paths:
                    InfoBar.error("错误", "没有选择有效的 .whl 文件", parent=self)
                    return

                cmd = ["-m", "pip", "install"]
                if "离线" in action:
                    cmd.append("--no-index")
                cmd.extend(valid_whl_paths)
                self._add_mirror_sources(cmd)
        else:
            return

        self._start_process(python_exe, cmd)

    def _add_mirror_sources(self, cmd):
        mirrors = self.mgr.config.mirrors.value
        if mirrors:
            primary_mirror = mirrors[0]
            cmd.extend(["-i", primary_mirror])
            from urllib.parse import urlparse
            parsed = urlparse(primary_mirror)
            cmd.extend(["--trusted-host", parsed.hostname])

            for mirror_url in mirrors[1:]:
                cmd.extend(["--extra-index-url", mirror_url])
                parsed = urlparse(mirror_url)
                cmd.extend(["--trusted-host", parsed.hostname])

    def on_update_package_clicked(self, package_name):
        if not self.current_env:
            InfoBar.error("错误", "请选择环境", parent=self)
            return
        python_exe = str(self.mgr.get_python_exe(self.current_env))

        cmd = ["-m", "pip", "install", "-U", package_name]
        self._add_mirror_sources(cmd)

        self._log_color(f"> 更新包: {package_name}", "#61afef")
        self._start_process(python_exe, cmd)

    def on_uninstall_package_clicked(self, package_name):
        if not self.current_env:
            InfoBar.error("错误", "请选择环境", parent=self)
            return

        msg_box = MessageBox("确认卸载", f"确定要卸载包 {package_name} 吗？", self)
        if msg_box.exec_():
            python_exe = str(self.mgr.get_python_exe(self.current_env))
            cmd = ["-m", "pip", "uninstall", "-y", package_name]
            self._log_color(f"> 卸载包: {package_name}", "#e06c75")
            self._start_process(python_exe, cmd)

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

                # 使用闭包避免修改函数签名
                def on_finish_remove(res):
                    state_tooltip.close()
                    self.refresh_env_list()
                    InfoBar.success("成功", f"环境 {env_name} 已删除", parent=self)
                    self.env_changed.emit()
                    if self.envCombo.count() > 0:
                        self.envCombo.setCurrentIndex(0)
                    else:
                        self.current_env = None
                        self.packageTable.setRowCount(0)
                    try:
                        self.mgr.remove_finished.disconnect()
                    except:
                        pass

                self.mgr.remove_finished.connect(on_finish_remove)

            except Exception as e:
                InfoBar.error("错误", f"删除环境失败: {str(e)}", parent=self)

    def _start_process(self, python_exe, cmd):
        if self.process and self.process.state() != QProcess.NotRunning:
            try:
                self.process.kill()
                self.process.waitForFinished(3000)
            except Exception as e:
                print(f"终止进程时出错: {e}")

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_ready_read)
        self.process.finished.connect(self.on_finished)

        if platform.system() == "Windows":
            self.process.setProcessEnvironment(self._get_hidden_window_environment())

        self.process.start(python_exe, cmd)
        self.execBtn.setEnabled(False)  # 禁用按钮防止重复提交

    def _get_hidden_window_environment(self):
        from PyQt5.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        return env

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
        self.execBtn.setEnabled(True)
        if self.current_env:
            QTimer.singleShot(1000, lambda: self.load_packages(self.current_env))

    def create_env(self, window=None):
        version_dialog = CustomComboDialog(
            "选择 Python 版本",
            list(self.config.python_versions.value),
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
                env_name = env_name_dialog.get_text().strip()
                if not env_name.strip():
                    env_name = version

                try:
                    self.mgr.download_and_install(version, env_name=env_name, log_callback=self.logEdit.append)
                    state_tooltip = StateToolTip("正在安装环境", "请稍候...", window or self)
                    state_tooltip.move(self.home.width() - state_tooltip.width() - 40, 20)
                    state_tooltip.show()

                    def on_finish_install(res):
                        state_tooltip.close()
                        self.refresh_env_list()
                        InfoBar.success("成功", f"环境 {env_name} 已创建", parent=window or self)
                        self.envCombo.setCurrentText(env_name)
                        self.on_env_changed()
                        self.env_changed.emit()
                        try:
                            self.mgr.install_finished.disconnect()
                        except:
                            pass

                    self.mgr.install_finished.connect(on_finish_install)
                except Exception as e:
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
                if not target_env: return

                try:
                    self.mgr.clone_env(source_env, target_env, log_callback=self.logEdit.append)
                    state_tooltip = StateToolTip("正在克隆环境", "请稍候...", self)
                    state_tooltip.show()

                    def on_finish_clone(res):
                        state_tooltip.close()
                        self.refresh_env_list()
                        InfoBar.success("成功", f"环境 {target_env} 已克隆", parent=self)
                        self.envCombo.setCurrentText(target_env)
                        self.env_changed.emit()
                        try:
                            self.mgr.install_finished.disconnect()
                        except:
                            pass

                    self.mgr.install_finished.connect(on_finish_clone)
                except Exception as e:
                    InfoBar.error("错误", str(e), parent=self)

    # 辅助方法：输出带颜色的日志 (新增但只在内部使用，不影响 API)
    def _log_color(self, text, color):
        self.logEdit.append(f'<span style="color:{color};">{text}</span>')
        self.logEdit.moveCursor(QTextCursor.End)