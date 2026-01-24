# gui/setting_interface.py
import os
from pathlib import Path
from PyQt5 import QtGui
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QFileDialog
from qfluentwidgets import (
    ScrollArea, SettingCardGroup, PushSettingCard, SwitchSettingCard,
    LineEdit, FluentIcon as FIF, InfoBar, MessageBox, TextEdit,
    OptionsSettingCard, FolderListSettingCard, OptionsValidator, Theme, setTheme, themeColor, PrimaryPushSettingCard,
    FluentIcon, RangeSettingCard
)

from app.utils.config import Settings
from app.utils.utils import resource_path, get_icon
from app.widgets.card_widget.list_setting_card import PackageListSettingCard


class SettingInterface(ScrollArea):
    """设置界面"""
    configChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        # ========== 2. 初始化防抖计时器 ==========
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)  # 单次触发
        self._save_timer.setInterval(500)  # 延迟 500ms 保存 (可根据需求调整)
        self._save_timer.timeout.connect(self._perform_save_to_disk)  # 绑定真实保存函数
        # 初始化配置实例
        self.cfg = Settings.get_instance()
        self.setStyleSheet("border: none; background-color: transparent;")
        self.view = QWidget(self)
        self.view.setStyleSheet("border: none; background-color: transparent;")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("settingInterface")

        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(40, 40, 40, 40)
        self.vBoxLayout.setSpacing(20)

        # ========== 配置设置项 ==========
        self.setup_version_info()
        self.setup_workflow_paths_settings()
        self.setup_project_paths_settings()  # 本地项目路径
        self.setup_runtime_env_settings()  # 运行环境管理
        self.setup_canvas_run_settings()
        self.setup_canvas_io_settings()
        self.setup_canvas_display_settings()  # 画布详细设置

        self.vBoxLayout.addStretch(1)

    def setup_version_info(self):
        self.versionGroup = SettingCardGroup(self.tr("版本信息"), self.view)

        copyright_text = self.tr("© 版权所有 2025 martin-afk. 当前版本：{}").format(self.cfg.current_version)

        self.info_card = PrimaryPushSettingCard(
            text=self.tr("检查更新"),
            icon=FluentIcon.INFO,
            title=self.tr("关于"),
            content=copyright_text,
            parent=self.versionGroup
        )
        self.info_card.clicked.connect(self.parent.updater.check_update)

        self.userNameCard = PushSettingCard(
            self.cfg.user_name.value,
            get_icon("用户名"),
            self.tr("当前用户名"),
            self.tr("用户名用于云端组件管理"),
            parent=self.versionGroup
        )
        self.userNameCard.clicked.connect(lambda: self.onUserNameClicked(self.userNameCard.button))

        self.autoUpdateCard = SwitchSettingCard(
            get_icon("更新"),
            self.tr("自动更新"),
            self.tr("是否开启自动版本更新检查"),
            configItem=self.cfg.auto_check_update,
            parent=self.versionGroup
        )
        # 连接配置变化信号，自动保存
        self.cfg.auto_check_update.valueChanged.connect(self.onConfigChanged)

        self.versionGroup.addSettingCard(self.info_card)
        self.versionGroup.addSettingCard(self.userNameCard)
        self.versionGroup.addSettingCard(self.autoUpdateCard)
        self.vBoxLayout.addWidget(self.versionGroup)

    def setup_export_settings(self):
        """导出设置"""
        self.exportGroup = SettingCardGroup(self.tr("导出设置"), self.view)

        self.exportDirCard = PushSettingCard(
            self.tr("修改"),
            FIF.FOLDER,
            self.tr("导出目录"),
            self.cfg.export_dir.value,
            parent=self.exportGroup
        )
        self.exportDirCard.clicked.connect(self.onExportDirClicked)

        self.exportGroup.addSettingCard(self.exportDirCard)
        self.vBoxLayout.addWidget(self.exportGroup)

    def setup_runtime_env_settings(self):
        """运行环境管理"""
        self.runtimeEnvGroup = SettingCardGroup(self.tr("运行环境管理"), self.view)

        # Python 版本管理
        self.pythonVersionsCard = PackageListSettingCard(
            icon=get_icon("python"),
            configItem=self.cfg.python_versions,
            title=self.tr("Python 版本"),
            content=self.tr("选择支持的 Python 版本"),
            parent=self.runtimeEnvGroup,
            home=self
        )
        self.cfg.python_versions.valueChanged.connect(self.onConfigChanged)

        # Python 镜像源管理
        self.mirrorsCard = PackageListSettingCard(
            icon=get_icon("镜像源"),
            configItem=self.cfg.mirrors,
            title=self.tr("镜像源管理"),
            content=self.tr("选择合适的镜像源连接"),
            parent=self.runtimeEnvGroup,
            home=self
        )
        self.cfg.mirrors.valueChanged.connect(self.onConfigChanged)

        # Miniconda 版本
        self.minicondaVersionCard = PushSettingCard(
            self.cfg.miniconda_version.value,
            get_icon("Miniconda"),
            self.tr("Miniconda 版本"),
            self.tr("用于修改 Miniconda 安装的版本"),
            parent=self.runtimeEnvGroup
        )
        self.minicondaVersionCard.clicked.connect(
            lambda: self.onMinicondaVersionClicked(self.minicondaVersionCard.button))

        # 默认包列表
        self.defaultPackagesCard = PackageListSettingCard(
            icon=get_icon("安装包"),
            configItem=self.cfg.default_packages,
            title=self.tr("默认安装包"),
            content=self.tr("管理默认安装的 Python 包"),
            parent=self.runtimeEnvGroup,
            home=self
        )
        self.cfg.default_packages.valueChanged.connect(self.onConfigChanged)

        self.runtimeEnvGroup.addSettingCard(self.pythonVersionsCard)
        self.runtimeEnvGroup.addSettingCard(self.mirrorsCard)
        self.runtimeEnvGroup.addSettingCard(self.minicondaVersionCard)
        self.runtimeEnvGroup.addSettingCard(self.defaultPackagesCard)
        self.vBoxLayout.addWidget(self.runtimeEnvGroup)

    def setup_workflow_paths_settings(self):
        """本地画布路径管理"""
        self.workflowPathsGroup = SettingCardGroup(self.tr("画布管理"), self.view)

        self.workflowPathsCard = FolderListSettingCard(
            configItem=self.cfg.workflow_paths,
            title=self.tr("本地画布路径"),
            content=self.tr("管理多个画布工作目录"),
            directory="./",
            parent=self.workflowPathsGroup
        )
        self.cfg.workflow_paths.valueChanged.connect(self.onConfigChanged)

        self.workflowPathsGroup.addSettingCard(self.workflowPathsCard)
        self.vBoxLayout.addWidget(self.workflowPathsGroup)

    def setup_project_paths_settings(self):
        """本地项目路径管理"""
        self.projectPathsGroup = SettingCardGroup(self.tr("项目管理"), self.view)

        self.projectPathsCard = FolderListSettingCard(
            configItem=self.cfg.project_paths,
            title=self.tr("本地项目路径"),
            content=self.tr("管理多个项目工作目录"),
            directory="./",
            parent=self.projectPathsGroup
        )
        self.cfg.project_paths.valueChanged.connect(self.onConfigChanged)

        self.projectPathsGroup.addSettingCard(self.projectPathsCard)
        self.vBoxLayout.addWidget(self.projectPathsGroup)

    def setup_canvas_run_settings(self):
        """画布运行设置"""
        self.canvasGroup = SettingCardGroup(self.tr("画布运行设置"), self.view)

        self.timeoutToggleCard = SwitchSettingCard(
            get_icon("运行模式"),
            self.tr("是否启用节点超时"),
            self.tr("如果启用，节点在超时时间以后会自动中止"),
            configItem=self.cfg.node_run_timeout_toggle,
            parent=self.canvasGroup
        )
        self.timeoutToggleCard.checkedChanged.connect(self.onConfigChanged)

        self.nodeTimeoutCard = RangeSettingCard(
            self.cfg.node_run_timeout,
            get_icon("运行模式"),
            self.tr("节点运行超时时间"),
            self.tr("决定节点最长运行时间（秒），如果超过则会直接中止运行"),
            parent=self.canvasGroup
        )
        self.nodeTimeoutCard.valueChanged.connect(self.onConfigChanged)

        self.runParallelCard = SwitchSettingCard(
            get_icon("运行模式"),
            self.tr("是否并行运行"),
            self.tr("是否并行运行画布节点（拓扑排序中同时入度为0的节点在此模式下会同时运行）"),
            configItem=self.cfg.run_parallel,
            parent=self.canvasGroup
        )
        self.runParallelCard.checkedChanged.connect(self.onConfigChanged)

        self.parallelNumCard = RangeSettingCard(
            self.cfg.run_parallel_max_workers,
            get_icon("运行模式"),
            self.tr("运行并行度"),
            self.tr("最大并行度控制，同时最多多少个节点同时运行"),
            parent=self.canvasGroup
        )
        self.parallelNumCard.valueChanged.connect(self.onConfigChanged)

        self.canvasGroup.addSettingCard(self.timeoutToggleCard)
        self.canvasGroup.addSettingCard(self.nodeTimeoutCard)
        self.canvasGroup.addSettingCard(self.runParallelCard)
        self.canvasGroup.addSettingCard(self.parallelNumCard)

        self.vBoxLayout.addWidget(self.canvasGroup)

    def setup_canvas_io_settings(self):
        """画布保存设置"""
        self.canvasGroup = SettingCardGroup(self.tr("画布保存设置"), self.view)
        self.autoSaveCard = SwitchSettingCard(
            get_icon("自动保存"),
            self.tr("自动保存"),
            self.tr("每隔一段时间自动保存当前项目"),
            configItem=self.cfg.canvas_auto_save,
            parent=self.canvasGroup
        )
        self.autoSaveCard.checkedChanged.connect(self.onConfigChanged)

        self.autoSaveIntervalCard = RangeSettingCard(
            self.cfg.canvas_auto_save_interval,
            get_icon("自动保存"),
            self.tr("修改"),
            self.tr("自动保存间隔 (秒)"),
            parent=self.canvasGroup
        )
        self.autoSaveIntervalCard.valueChanged.connect(self.onConfigChanged)
        self.canvasGroup.addSettingCard(self.autoSaveCard)
        self.canvasGroup.addSettingCard(self.autoSaveIntervalCard)

        self.vBoxLayout.addWidget(self.canvasGroup)

    def setup_canvas_display_settings(self):
        """画布显示设置"""
        self.canvasGroup = SettingCardGroup(self.tr("画布显示设置"), self.view)

        self.nodeResizeMemoryCard = SwitchSettingCard(
            get_icon("画布"),
            self.tr("节点缩放记忆"),
            self.tr("用于控制画布加载时是否还原上一次保存时的节点缩放情况"),
            configItem=self.cfg.canvas_resize_memory,
            parent=self.canvasGroup
        )
        self.nodeResizeMemoryCard.checkedChanged.connect(self.onConfigChanged)

        self.showGridCard = OptionsSettingCard(
            self.cfg.canvas_grid_mode,
            get_icon("画布"),
            self.tr("显示网格"),
            self.tr("在画布上显示辅助网格"),
            texts=[self.tr("线网格"), self.tr("点网格"), self.tr("无网格")],
            parent=self.canvasGroup
        )
        self.showGridCard.optionChanged.connect(self.onConfigChanged)

        self.NodeProxyCard = RangeSettingCard(
            self.cfg.node_proxy_size,
            get_icon("画布"),
            self.tr("节点细节绘制距离"),
            self.tr("设置节点中控件最小绘制距离，如果超过距离会隐藏控件以提升画布性能"),
            parent=self.canvasGroup
        )
        self.NodeProxyCard.valueChanged.connect(self.onConfigChanged)

        self.pipelayoutCard = OptionsSettingCard(
            self.cfg.canvas_pipelayout,
            get_icon("画布"),
            self.tr("流程图连线类型"),
            "",
            texts=[self.tr("直线"), self.tr("曲线"), self.tr("折线")],
            parent=self.canvasGroup
        )
        self.pipelayoutCard.optionChanged.connect(self.onConfigChanged)

        self.canvasFontCard = OptionsSettingCard(
            self.cfg.canvas_font_type,
            get_icon("画布"),
            self.tr("画布显示字体设置"),
            "",
            texts=self.cfg.canvas_font_type.options,
            parent=self.canvasGroup
        )
        self.canvasFontCard.optionChanged.connect(self.onConfigChanged)

        self.canvasGroup.addSettingCard(self.nodeResizeMemoryCard)
        self.canvasGroup.addSettingCard(self.canvasFontCard)
        self.canvasGroup.addSettingCard(self.showGridCard)
        self.canvasGroup.addSettingCard(self.NodeProxyCard)
        self.canvasGroup.addSettingCard(self.pipelayoutCard)

        self.vBoxLayout.addWidget(self.canvasGroup)

    # ==================== 信号处理方法 ====================
    def onUserNameClicked(self, button):
        self.showLineEditDialog(
            self.tr("输入当前用户名"),
            self.cfg.user_name.value,
            lambda x: (
                self.cfg.set(self.cfg.user_name, x),
                button.setText(x),
                self.cfg.save_config(),
                self.configChanged.emit()
            ),
            placeholder=self.tr("例如: martin98-afk")
        )

    def onMinicondaVersionClicked(self, button):
        self.showLineEditDialog(
            self.tr("Miniconda 版本"),
            self.cfg.miniconda_version.value,
            lambda x: (
                self.cfg.set(self.cfg.miniconda_version, x),
                button.setText(x),
                self.cfg.save_config(),
                self.configChanged.emit()
            ),
            placeholder=self.tr("例如: 23.11.0")
        )

    def onExportDirClicked(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择导出目录"),
            self.cfg.export_dir.value
        )
        if folder:
            self.cfg.set(self.cfg.export_dir, folder)
            self.exportDirCard.setContent(folder)
            Path(folder).mkdir(parents=True, exist_ok=True)
            self.cfg.save_config()
            self.configChanged.emit()
            InfoBar.success(
                self.tr("设置已保存"),
                self.tr("导出目录已更新为 {}").format(folder),
                parent=self
            )

    def onGridSizeClicked(self):
        self.showNumberEditDialog(
            self.tr("网格大小"),
            self.cfg.canvas_grid_size.value,
            lambda x: (
                self.cfg.set(self.cfg.canvas_grid_size, x),
                self.cfg.save_config(),
                self.configChanged.emit()
            ),
            min_val=5,
            max_val=100
        )

    def onConfigChanged(self):
        """
        配置改变时的槽函数（轻量级）。
        只触发内存更新信号和重置保存计时器，不进行磁盘 IO。
        """
        # 1. 立即通知其他 UI 组件（如果有需要实时响应的）
        self.configChanged.emit()

        # 2. 启动/重置 防抖计时器
        self._save_timer.start()

    def _perform_save_to_disk(self):
        """
        【内部方法】真正执行磁盘写入操作。
        由计时器触发，避免 IO 阻塞 UI。
        """
        try:
            self.cfg.save_config()
            # 可选：如果你想在控制台看保存时机，取消下面注释
            # print("✅ 配置已写入硬盘")
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
            # 如果保存失败，可以弹个窗提示
            InfoBar.error(
                title=self.tr("保存失败"),
                content=str(e),
                parent=self,
                duration=3000
            )

    # ==================== 通用对话框 ====================

    def showLineEditDialog(self, title: str, current_value: str, callback, placeholder=""):
        w = MessageBox(title, "", self)
        w.contentLabel.hide()

        lineEdit = LineEdit(w)
        lineEdit.setText(current_value)
        lineEdit.setFixedWidth(300)
        if placeholder:
            lineEdit.setPlaceholderText(placeholder)

        w.vBoxLayout.insertWidget(1, lineEdit, 0, Qt.AlignCenter)
        w.yesButton.setText(self.tr("保存"))
        w.cancelButton.setText(self.tr("取消"))

        if w.exec():
            new_value = lineEdit.text().strip()
            if new_value:
                callback(new_value)
                InfoBar.success(self.tr("设置已保存"), self.tr("{} 已更新").format(title), parent=self)
            else:
                InfoBar.warning(self.tr("输入无效"), self.tr("{} 不能为空").format(title), parent=self)

    def showNumberEditDialog(self, title: str, current_value: int, callback, min_val=0, max_val=100):
        # 使用 format 保持翻译文件清洁
        hint = self.tr("请输入 {} ~ {} 之间的整数").format(min_val, max_val)
        w = MessageBox(title, hint, self)

        lineEdit = LineEdit(w)
        lineEdit.setText(str(current_value))
        lineEdit.setFixedWidth(200)
        lineEdit.setValidator(QtGui.QIntValidator(min_val, max_val))

        w.vBoxLayout.insertWidget(1, lineEdit, 0, Qt.AlignCenter)
        w.yesButton.setText(self.tr("保存"))
        w.cancelButton.setText(self.tr("取消"))

        if w.exec():
            try:
                value = int(lineEdit.text())
                if min_val <= value <= max_val:
                    callback(value)
                    InfoBar.success(self.tr("设置已保存"), self.tr("{} 已更新为 {}").format(title, value), parent=self)
                else:
                    InfoBar.warning(self.tr("输入无效"), hint, parent=self)
            except ValueError:
                InfoBar.error(self.tr("格式错误"), self.tr("请输入有效整数"), parent=self)

    def deleteLater(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._perform_save_to_disk()
        super().deleteLater()