# -*- coding: utf-8 -*-
import functools
import json
import platform
import re
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal, QProcess, Qt, QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidgetItem, QSplitter, QHeaderView, QSizePolicy, QFileDialog, QCheckBox
)
from qfluentwidgets import (
    ComboBox, PrimaryPushButton, LineEdit, TableWidget,
    FluentIcon, InfoBar, SearchLineEdit, TextEdit, PushButton, MessageBox, BodyLabel
)

from app.utils.env_operation import EnvironmentManager
from app.widgets.dialog_widget.custom_messagebox import CustomComboDialog, CustomInputDialog


class PackageListThread(QThread):
    packages_loaded = pyqtSignal(str)      # 成功时发送 stdout
    error_occurred = pyqtSignal(Exception) # 失败时发送异常

    def __init__(self, python_exe, parent=None):
        super().__init__(parent)
        self.python_exe = python_exe

    def run(self):

        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,  # 可适当延长
                **kwargs
            )
            self.packages_loaded.emit(result.stdout.strip())
        except Exception as e:
            self.error_occurred.emit(e)


class EnvManagerUI(QWidget):
    env_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("EnvManagerUI")
        self.resize(1000, 600)
        self.setStyleSheet("""
                QSplitter {
                    background-color: #2D2D2D;
                    border: 1px solid #444444;
                }

                QSplitter::handle {
                    background-color: #444444;
                    border: 1px solid #555555;
                }

                QSplitter::handle:hover {
                    background-color: #555555;
                }

                QSplitter::handle:horizontal {
                    width: 4px;
                    background-image: url(:/qss_icons/rc/toolbar_separator_vertical.png);
                }

                QSplitter::handle:vertical {
                    height: 4px;
                    background-image: url(:/qss_icons/rc/toolbar_separator_horizontal.png);
                }
            """)

        self.mgr = EnvironmentManager()
        self.process = None
        self.current_env = None
        self.pkgs_data = []  # 保存完整包列表数据

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
        # --- 修改：使用两个联动的下拉框 ---
        self.sourceCombo = ComboBox(self)
        self.sourceCombo.addItems(["在线", "本地"])
        self.sourceCombo.currentIndexChanged.connect(self._update_action_combo) # 连接信号

        self.actionCombo = ComboBox(self)

        self.packageEdit = LineEdit(self)
        self.packageEdit.setPlaceholderText("输入包名或本地文件路径...")

        self.execBtn = PrimaryPushButton("执行", self, icon=FluentIcon.PLAY)
        self.execBtn.clicked.connect(self.run_pip_command)

        self._update_action_combo()  # 初始化 actionCombo 的内容
        # ------------------------------

        actionLayout = QHBoxLayout()
        actionLayout.addWidget(self.sourceCombo)
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
        packageLayout.addLayout(actionLayout) # 包含了 sourceCombo, actionCombo, packageEdit, execBtn
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
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        # ---------- 总布局 ----------
        mainLayout = QVBoxLayout(self)
        mainLayout.addWidget(splitter, stretch=1)  # 中间占满
        self.setLayout(mainLayout)

        if self.envCombo.count() > 0:
            self.on_env_changed()
        else:
            self.logEdit.append("⚠️ 没有检测到任何环境，请点击\"新建环境\"创建。")

    def _update_action_combo(self):
        """根据 sourceCombo 的选择更新 actionCombo 的内容"""
        current_source = self.sourceCombo.currentText()
        self.actionCombo.clear()
        if current_source == "在线":
            self.actionCombo.addItems(["安装", "强制重装", "更新", "卸载"])
            # 清空 packageEdit 提示，因为它用于输入包名
            self.packageEdit.setPlaceholderText("输入包名，例如 numpy 或 numpy==1.24.0")
        elif current_source == "本地":
            self.actionCombo.addItems(["离线", "联网"]) # 可根据需要调整选项
            # 清空 packageEdit 提示，因为它将用于显示本地文件路径（或用户手动输入）
            self.packageEdit.setPlaceholderText("选择本地包文件或输入路径...")

    def get_current_python_exe(self):
        """获取当前环境 Python 的路径"""
        return self.mgr.get_python_exe(self.current_env)

    def refresh_env_list(self):
        self.envCombo.clear()
        envs = self.mgr.list_envs()
        self.envCombo.addItems(envs)

    def on_env_changed(self):
        # 取消所有正在运行的摘要获取线程
        self.current_env = self.envCombo.currentText()
        if self.current_env:
            self.load_packages(self.current_env)

    def load_packages(self, env_name):
        """启动线程获取包列表"""
        self.packageTable.setRowCount(0)
        self.logEdit.append(f"[信息] 正在加载环境 {env_name} 的包列表...")

        try:
            python_exe = str(self.mgr.get_python_exe(env_name))
        except Exception as e:
            self.logEdit.append(f"[错误] 获取 Python 路径失败: {e}")
            return

        # 如果已有线程在运行，先终止（可选）
        if hasattr(self, '_pkg_thread') and self._pkg_thread.isRunning():
            self._pkg_thread.quit()
            self._pkg_thread.wait()

        # 创建并启动新线程
        self._pkg_thread = PackageListThread(python_exe)
        self._pkg_thread.packages_loaded.connect(self.on_load_packages)
        self._pkg_thread.error_occurred.connect(self.on_load_packages_error)
        self._pkg_thread.start()

    def on_load_packages(self, package_list):
        # 提取 JSON 部分（第一个 [ 到最后一个 ]）
        match = re.search(r"\[.*\]", package_list, re.S)
        if match:
            pkgs = json.loads(match.group(0))
        else:
            pkgs = []

        # 保存完整数据，供搜索使用
        self.pkgs_data = pkgs
        self._repopulate_table(pkgs)

    def on_load_packages_error(self, e):
        error_msg = str(e)
        if hasattr(e, 'stderr') and e.stderr:
            error_msg = e.stderr.strip() or error_msg
        self.logEdit.append(f"[错误] 获取包列表失败: {error_msg}")

    def _repopulate_table(self, pkgs):
        """根据传入 pkgs 列表刷新表格（内部使用）"""
        # 取消所有正在运行的摘要获取线程
        self.packageTable.setRowCount(0)
        # 设置Python解释器路径
        if self.current_env:
            python_exe = str(self.mgr.get_python_exe(self.current_env))
        for row, pkg in enumerate(pkgs):
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            self.packageTable.insertRow(row)
            self.packageTable.setItem(row, 0, QTableWidgetItem(name))
            self.packageTable.setItem(row, 1, QTableWidgetItem(version))

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

    def on_search_text_changed(self, text):
        """按搜索文本过滤已安装包"""
        text = text.strip().lower()
        if not text:
            filtered = self.pkgs_data
        else:
            filtered = [p for p in self.pkgs_data if text in p.get("name", "").lower()]
        self._repopulate_table(filtered)

    def run_pip_command(self):
        """根据 sourceCombo 和 actionCombo 执行对应的 pip 命令"""
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

        source = self.sourceCombo.currentText()
        action = self.actionCombo.currentText()
        package_input = self.packageEdit.text().strip()

        if source == "在线":
            # --- 在线安装逻辑 ---
            if not package_input:
                InfoBar.error("错误", "请输入包名", parent=self)
                return

            if action == "安装":
                cmd = ["-m", "pip", "install", package_input]
            elif action == "强制重装":
                cmd = ["-m", "pip", "install", "--force-reinstall", package_input]
            elif action == "更新":
                cmd = ["-m", "pip", "install", "-U", package_input]
            elif action == "卸载":
                cmd = ["-m", "pip", "uninstall", "-y", package_input]
            else:
                return # 不应该发生

        elif source == "本地":
            # --- 本地安装逻辑 ---
            # 如果 packageEdit 为空，弹出文件选择对话框
            file_paths = []
            if not package_input:
                file_paths, _ = QFileDialog.getOpenFileNames(
                    self,
                    "选择本地 WHL 包",
                    "", # 初始目录，可以设置为特定路径
                    "Python Wheels (*.whl);;All Files (*)"
                )
                if not file_paths:
                    # 用户取消了选择
                    return
            else:
                # 如果 packageEdit 有内容，尝试解析为路径
                # 这里可以扩展逻辑，例如支持多个路径（用分隔符分隔）
                # 简单起见，假设它是一个路径
                file_paths = [package_input]

            if file_paths:
                # 验证文件后缀
                valid_whl_paths = [path for path in file_paths if path.lower().endswith('.whl')]
                invalid_paths = [path for path in file_paths if not path.lower().endswith('.whl')]

                if invalid_paths:
                    InfoBar.warning("警告", f"跳过非 .whl 文件: {', '.join(invalid_paths)}", parent=self)

                if not valid_whl_paths:
                    InfoBar.error("错误", "没有选择有效的 .whl 文件", parent=self)
                    return

                # 构建 pip install 命令
                cmd = ["-m", "pip", "install"]
                if "no-index" in action.lower(): # 检查 action 是否包含 "no-index"
                    cmd.append("--no-index")
                cmd.extend(valid_whl_paths)

        else:
            return # 不应该发生

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
                    lambda: (
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

    def _start_process(self, python_exe, cmd):
        """启动 QProcess（封装）"""
        # 若已有进程正在运行，先终止它
        if self.process and self.process.state() != QProcess.NotRunning:
            try:
                self.process.kill()
                self.process.waitForFinished(3000) # 等待最多3秒让进程结束
            except Exception as e:
                print(f"终止进程时出错: {e}") # 可选：记录错误

        # 确保旧进程引用被清理
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        # 连接实时输出
        self.process.readyReadStandardOutput.connect(self.on_ready_read)
        self.process.readyReadStandardError.connect(self.on_ready_read)
        self.process.finished.connect(self.on_finished)
        # 设置进程属性以避免弹出窗口（Windows下）
        import platform
        if platform.system() == "Windows":
            # 在Windows下隐藏窗口
            self.process.setProcessEnvironment(self._get_hidden_window_environment())
        # start with executable and args
        self.process.start(python_exe, cmd)

    def _get_hidden_window_environment(self):
        """获取隐藏窗口的环境变量（Windows）"""
        from PyQt5.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        # 在Windows下，设置一些环境变量来减少窗口显示
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
        # 操作结束后刷新包列表
        if self.current_env:
            # 添加一个小延迟，确保pip操作完全完成
            QTimer.singleShot(1000, lambda: self.load_packages(self.current_env))

    def create_env(self):
        """新建环境：选择版本和环境名"""
        # 创建选择Python版本的对话框
        version_dialog = CustomComboDialog(
            "选择 Python 版本",
            list(self.mgr.MINICONDA_URLS.keys()),
            0,
            self
        )

        if version_dialog.exec_():
            version = version_dialog.get_text()

            # 创建输入环境名称的对话框
            env_name_dialog = CustomInputDialog(
                f"输入环境名称（默认为 {version}）",
                placeholder="请输入环境名称",
                currenttext=version,
                parent=self
            )

            if env_name_dialog.exec_():
                env_name = env_name_dialog.get_text().strip()

                # 如果用户没有输入环境名，使用默认版本号
                if not env_name.strip():
                    env_name = version

                try:
                    self.mgr.download_and_install(version, env_name=env_name, log_callback=self.logEdit.append)
                    self.mgr.install_finished.connect(
                        lambda: (
                            self.refresh_env_list(),
                            InfoBar.success("成功", f"环境 {env_name} 已创建", parent=self),
                            self.envCombo.setCurrentText(env_name),
                            self.env_changed.emit()
                        )
                    )
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())
                    InfoBar.error("错误", str(e), parent=self)

    def clone_env(self):
        # 克隆环境
        envs = self.mgr.list_envs()
        if not envs:
            InfoBar.warning("警告", "没有可用的环境可供克隆", parent=self)
            return

        # 创建选择源环境的对话框
        source_env_dialog = CustomComboDialog("选择要克隆的源环境", envs, 0, self)
        if source_env_dialog.exec_():
            source_env = source_env_dialog.get_text()

            # 创建输入目标环境名的对话框
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
                    self.mgr.install_finished.connect(
                        lambda: (
                            self.refresh_env_list(),
                            InfoBar.success("成功", f"环境 {target_env} 已克隆", parent=self),
                            self.envCombo.setCurrentText(target_env),
                            self.env_changed.emit()
                        )
                    )
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())
                    InfoBar.error("错误", str(e), parent=self)
