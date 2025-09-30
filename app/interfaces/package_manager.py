from PyQt5.QtCore import Qt, pyqtSignal, QRunnable, pyqtSlot, QObject
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFileDialog, QTableWidgetItem, QHeaderView, QWidget
)
from qfluentwidgets import (
    CardWidget, BodyLabel, LineEdit, PrimaryPushButton, PushButton,
    TableWidget, ComboBox, ProgressBar,
    InfoBar, InfoBarPosition, TextEdit, ToolButton, FluentIcon
)

from app.utils.env_manager import env_manager


class PackageManagerWidget(CardWidget):
    """智能包管理器界面 - 优化版（铺满界面 + 操作类型选择）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("package_manager")
        # 移除固定宽度限制，让界面可以铺满
        # self.setFixedWidth(320)  # ❌ 删除这行
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(20, 20, 20, 20)
        self.vbox.setSpacing(12)  # 增加间距

        self.current_env = "system"
        self._setup_ui()
        self._load_environments()

    def _setup_ui(self):
        # 标题
        title = BodyLabel("📦 包管理器")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.vbox.addWidget(title)

        # 环境选择
        env_layout = QHBoxLayout()
        env_layout.addWidget(BodyLabel("环境:"), 0)
        self.env_combo = ComboBox()
        self.env_combo.currentTextChanged.connect(self._on_env_changed)
        env_layout.addWidget(self.env_combo, 1)

        refresh_btn = ToolButton(FluentIcon.SYNC, self)
        refresh_btn.setToolTip("刷新环境列表")
        refresh_btn.clicked.connect(self._refresh_environments)
        env_layout.addWidget(refresh_btn, 0)

        self.vbox.addLayout(env_layout)

        # 操作类型选择 + 包名输入 + 执行按钮
        operation_layout = QHBoxLayout()

        # 操作类型下拉框
        self.operation_combo = ComboBox()
        self.operation_combo.addItems(["安装", "更新", "卸载"])
        self.operation_combo.setCurrentText("安装")
        self.operation_combo.setFixedWidth(80)
        operation_layout.addWidget(self.operation_combo, 0)

        # 包名输入框
        self.package_edit = LineEdit()
        self.package_edit.setPlaceholderText("输入包名，如: pandas>=1.0")
        operation_layout.addWidget(self.package_edit, 1)

        # 执行按钮
        self.execute_btn = PrimaryPushButton(FluentIcon.PLAY, "执行", self)
        self.execute_btn.clicked.connect(self._execute_package_operation)
        self.execute_btn.setFixedWidth(80)
        operation_layout.addWidget(self.execute_btn, 0)

        self.vbox.addLayout(operation_layout)

        # 进度条
        self.progress_bar = ProgressBar()
        self.progress_bar.setVisible(False)
        self.vbox.addWidget(self.progress_bar)

        # 包列表标题和刷新按钮
        packages_header_layout = QHBoxLayout()
        packages_header_layout.addWidget(BodyLabel("已安装的包:"), 1)

        refresh_pkgs_btn = ToolButton(FluentIcon.SYNC, self)
        refresh_pkgs_btn.setToolTip("刷新包列表")
        refresh_pkgs_btn.clicked.connect(self._refresh_packages)
        packages_header_layout.addWidget(refresh_pkgs_btn, 0)

        self.vbox.addLayout(packages_header_layout)

        # 包列表（增加高度）
        self.package_list = TableWidget()
        self.package_list.setColumnCount(3)  # 增加一列显示操作
        self.package_list.setHorizontalHeaderLabels(["包名", "版本", "操作"])
        self.package_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.package_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.package_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.package_list.setRowCount(0)
        self.package_list.setFixedHeight(200)  # 增加固定高度
        self.vbox.addWidget(self.package_list)

        # 导入导出按钮
        io_layout = QHBoxLayout()
        export_btn = PushButton(text="📤 导出 requirements.txt", parent=self)
        export_btn.clicked.connect(self._export_requirements)
        import_btn = PushButton(text="📥 导入 requirements.txt", parent=self)
        import_btn.clicked.connect(self._import_requirements)

        io_layout.addWidget(export_btn)
        io_layout.addWidget(import_btn)
        io_layout.addStretch()
        self.vbox.addLayout(io_layout)

        # 日志输出（占据更多空间）
        self.vbox.addWidget(BodyLabel("📋 安装日志:"))
        self.log_output = TextEdit()
        self.log_output.setReadOnly(True)
        # 让日志区域占据更多垂直空间
        self.log_output.setMinimumHeight(300)  # 增加最小高度
        self.vbox.addWidget(self.log_output, 1)  # 添加 stretch 参数让其自动扩展

    def _load_environments(self):
        """加载环境列表"""
        self.env_combo.clear()
        environments = env_manager.list_environments()
        for env in environments:
            display_name = f"{env['name']} ({env.get('python_version', 'Unknown')})"
            self.env_combo.addItem(display_name, env['name'])
        if environments:
            self.current_env = environments[0]['type']
            self._refresh_packages()

    def _refresh_environments(self):
        """刷新环境列表"""
        try:
            env_manager._auto_discover_environments()  # 重新发现环境
            self._load_environments()
            InfoBar.success(
                title='成功',
                content='环境列表已刷新！',
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
        except Exception as e:
            InfoBar.error(
                title='错误',
                content=f'刷新环境列表失败: {str(e)}',
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )

    def _on_env_changed(self, env_display_name):
        """环境改变时的处理"""
        env_name = self.env_combo.currentData()
        if env_name:
            self.current_env = env_name
            self._refresh_packages()

    def _execute_package_operation(self):
        """执行包操作（安装/更新/卸载）"""
        package = self.package_edit.text().strip()
        operation = self.operation_combo.currentText()

        if not package:
            InfoBar.warning(
                title='警告',
                content='请输入包名！',
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
            return

        # 显示进度条
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 无限循环动画
        self.execute_btn.setEnabled(False)
        self.operation_combo.setEnabled(False)
        self.package_edit.setEnabled(False)

        # 清空之前的日志
        self.log_output.clear()
        self.log_output.append(f"[{self.current_env}] 开始执行 {operation} 操作: {package}")

        # 异步执行
        self._async_execute_package_operation(operation, package)

    def _async_execute_package_operation(self, operation, package):
        """异步执行包操作"""
        worker = PackageOperationWorker(self.current_env, operation, package)
        worker.signals.finished.connect(self._on_operation_finished)
        worker.signals.error.connect(self._on_operation_error)
        worker.signals.progress.connect(self._on_operation_progress)

        from PyQt5.QtCore import QThreadPool
        threadpool = QThreadPool()
        threadpool.start(worker)

    def _on_operation_finished(self, success, message):
        """操作完成回调"""
        # 隐藏进度条
        self.progress_bar.setVisible(False)
        self.execute_btn.setEnabled(True)
        self.operation_combo.setEnabled(True)
        self.package_edit.setEnabled(True)

        if success:
            InfoBar.success(
                title='成功',
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )
            self._refresh_packages()
        else:
            InfoBar.error(
                title='错误',
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )

        self.log_output.append(f"[{self.current_env}] {message}")

    def _on_operation_error(self, error_msg):
        """操作错误回调"""
        self.progress_bar.setVisible(False)
        self.execute_btn.setEnabled(True)
        self.operation_combo.setEnabled(True)
        self.package_edit.setEnabled(True)

        InfoBar.error(
            title='错误',
            content=error_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )
        self.log_output.append(f"[{self.current_env}] ❌ 错误: {error_msg}")

    def _on_operation_progress(self, progress_msg):
        """操作进度回调"""
        self.log_output.append(f"[{self.current_env}] {progress_msg}")
        # 自动滚动到底部
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _refresh_packages(self):
        """刷新包列表"""
        try:
            packages = env_manager.list_packages(self.current_env)
            self.package_list.setRowCount(0)
            for pkg in packages:
                row = self.package_list.rowCount()
                self.package_list.insertRow(row)
                self.package_list.setItem(row, 0, QTableWidgetItem(pkg["name"]))
                self.package_list.setItem(row, 1, QTableWidgetItem(pkg["version"]))

                # 添加操作按钮
                update_btn = PushButton(FluentIcon.SYNC, "更新")
                update_btn.clicked.connect(lambda _, p=pkg["name"]: self._update_package(p))
                uninstall_btn = PushButton(FluentIcon.DELETE, "卸载")
                uninstall_btn.clicked.connect(lambda _, p=pkg["name"]: self._uninstall_package(p))

                # 创建按钮容器
                btn_container = QWidget()
                btn_layout = QHBoxLayout(btn_container)
                btn_layout.setContentsMargins(2, 2, 2, 2)
                btn_layout.setSpacing(2)
                btn_layout.addWidget(update_btn)
                btn_layout.addWidget(uninstall_btn)
                btn_layout.addStretch()
                btn_container.setLayout(btn_layout)

                self.package_list.setCellWidget(row, 2, btn_container)

        except Exception as e:
            self.log_output.append(f"[{self.current_env}] 刷新包列表失败: {str(e)}")

    def _update_package(self, package_name):
        """更新指定包"""
        self.package_edit.setText(package_name)
        self.operation_combo.setCurrentText("更新")
        self._execute_package_operation()

    def _uninstall_package(self, package_name):
        """卸载指定包"""
        self.package_edit.setText(package_name)
        self.operation_combo.setCurrentText("卸载")
        self._execute_package_operation()

    def _export_requirements(self):
        """导出 requirements.txt"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出 requirements.txt", "requirements.txt", "Text Files (*.txt)"
        )
        if file_path:
            try:
                success = env_manager.export_requirements(self.current_env, file_path)
                if success:
                    InfoBar.success(
                        title='成功',
                        content='requirements.txt 导出成功！',
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=2000,
                        parent=self
                    )
                    self.log_output.append(f"[{self.current_env}] ✅ requirements.txt 已导出到: {file_path}")
                else:
                    InfoBar.error(
                        title='错误',
                        content='requirements.txt 导出失败！',
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=3000,
                        parent=self
                    )
            except Exception as e:
                InfoBar.error(
                    title='错误',
                    content=f'导出失败: {str(e)}',
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3000,
                    parent=self
                )

    def _import_requirements(self):
        """导入 requirements.txt"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入 requirements.txt", "", "Text Files (*.txt)"
        )
        if file_path:
            try:
                self.log_output.append(f"[{self.current_env}] 📥 正在导入: {file_path}")
                success = env_manager.import_requirements(self.current_env, file_path)
                if success:
                    InfoBar.success(
                        title='成功',
                        content='requirements.txt 导入成功！',
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=2000,
                        parent=self
                    )
                    self.log_output.append(f"[{self.current_env}] ✅ requirements.txt 导入完成")
                    self._refresh_packages()
                else:
                    InfoBar.error(
                        title='错误',
                        content='requirements.txt 导入失败！',
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=3000,
                        parent=self
                    )
            except Exception as e:
                InfoBar.error(
                    title='错误',
                    content=f'导入失败: {str(e)}',
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3000,
                    parent=self
                )


class PackageOperationSignals(QObject):
    finished = pyqtSignal(bool, str)  # (success, message)
    error = pyqtSignal(str)  # (error_message)
    progress = pyqtSignal(str)  # (progress_message)


class PackageOperationWorker(QRunnable):
    def __init__(self, env_name: str, operation: str, package: str):
        super().__init__()
        self.signals = PackageOperationSignals()
        self.env_name = env_name
        self.operation = operation
        self.package = package

    @pyqtSlot()
    def run(self):
        try:
            self.signals.progress.emit(f"▶ 正在{self.operation}包: {self.package}")

            if self.operation == "安装":
                success = env_manager.install_package(self.env_name, self.package)
                if success:
                    self.signals.finished.emit(True, f"✅ 包 {self.package} 安装成功！")
                else:
                    self.signals.finished.emit(False, f"❌ 包 {self.package} 安装失败！")

            elif self.operation == "更新":
                success = env_manager.update_package(self.env_name, self.package)
                if success:
                    self.signals.finished.emit(True, f"✅ 包 {self.package} 更新成功！")
                else:
                    self.signals.finished.emit(False, f"❌ 包 {self.package} 更新失败！")

            elif self.operation == "卸载":
                success = env_manager.uninstall_package(self.env_name, self.package)
                if success:
                    self.signals.finished.emit(True, f"✅ 包 {self.package} 卸载成功！")
                else:
                    self.signals.finished.emit(False, f"❌ 包 {self.package} 卸载失败！")

            else:
                self.signals.error.emit(f"未知操作: {self.operation}")

        except Exception as e:
            import traceback
            error_msg = f"❌ {self.operation}包 {self.package} 失败: {str(e)}\n{traceback.format_exc()}"
            self.signals.error.emit(error_msg)