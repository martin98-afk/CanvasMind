# gui/setting_interface.py
import os
from pathlib import Path
from PyQt5 import QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QFileDialog
from qfluentwidgets import (
    ScrollArea, SettingCardGroup, PushSettingCard, SwitchSettingCard,
    LineEdit, FluentIcon as FIF, InfoBar, MessageBox, TextEdit,
    OptionsSettingCard, FolderListSettingCard, OptionsValidator, Theme, setTheme, themeColor, PrimaryPushSettingCard,
    FluentIcon
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

        # ========== 新增设置 ==========
        self.setup_version_info()
        self.setup_workflow_paths_settings()
        self.setup_project_paths_settings()  # 本地项目路径
        self.setup_runtime_env_settings()  # 运行环境管理
        self.setup_canvas_settings()        # 画布详细设置

        self.vBoxLayout.addStretch(1)

    def setup_version_info(self):
        self.versionGroup = SettingCardGroup(" 版本信息", self.view)
        self.info_card = PrimaryPushSettingCard(
            text="检查更新",
            icon=FluentIcon.INFO,
            title="关于",
            content=f"© 版权所有 2025 martin-afk. 当前版本：{self.cfg.current_version.value}",
            parent=self.versionGroup
        )
        self.info_card.clicked.connect(self.parent.updater.check_update)
        self.autoUpdateCard = SwitchSettingCard(
            get_icon("更新"),
            "自动更新",
            "是否开启自动版本更新检查",
            configItem=self.cfg.auto_check_update,
            parent=self.versionGroup
        )
        # 连接配置变化信号，自动保存
        self.cfg.auto_check_update.valueChanged.connect(self.onConfigChanged)
        self.versionGroup.addSettingCard(self.info_card)
        self.versionGroup.addSettingCard(self.autoUpdateCard)
        self.vBoxLayout.addWidget(self.versionGroup)

    def setup_export_settings(self):
        """导出设置"""
        self.exportGroup = SettingCardGroup(" 导出设置", self.view)

        self.exportDirCard = PushSettingCard(
            "修改",
            FIF.FOLDER,
            "导出目录",
            self.cfg.export_dir.value,
            parent=self.exportGroup
        )
        self.exportDirCard.clicked.connect(self.onExportDirClicked)

        self.exportGroup.addSettingCard(self.exportDirCard)
        self.vBoxLayout.addWidget(self.exportGroup)

    # ==================== 新增：运行环境管理 ====================

    def setup_runtime_env_settings(self):
        """运行环境管理"""
        self.runtimeEnvGroup = SettingCardGroup(" 运行环境管理", self.view)

        # Python 版本管理
        self.pythonVersionsCard = PackageListSettingCard(
            icon=get_icon("python"),
            configItem=self.cfg.python_versions,
            title="Python 版本",
            content="选择支持的 Python 版本",
            parent=self.runtimeEnvGroup,
            home=self
        )
        # 连接配置变化信号，自动保存
        self.cfg.python_versions.valueChanged.connect(self.onConfigChanged)

        # Miniconda 版本
        self.minicondaVersionCard = PushSettingCard(
            "修改",
            get_icon("Miniconda"),
            "Miniconda 版本",
            self.cfg.miniconda_version.value,
            parent=self.runtimeEnvGroup
        )
        self.minicondaVersionCard.clicked.connect(self.onMinicondaVersionClicked)

        # 默认包列表
        self.defaultPackagesCard = PackageListSettingCard(
            icon=get_icon("安装包"),
            configItem=self.cfg.default_packages,
            title="默认安装包",
            content="管理默认安装的 Python 包",
            parent=self.runtimeEnvGroup,
            home=self
        )
        # 连接配置变化信号，自动保存
        self.cfg.default_packages.valueChanged.connect(self.onConfigChanged)

        self.runtimeEnvGroup.addSettingCard(self.pythonVersionsCard)
        self.runtimeEnvGroup.addSettingCard(self.minicondaVersionCard)
        self.runtimeEnvGroup.addSettingCard(self.defaultPackagesCard)
        self.vBoxLayout.addWidget(self.runtimeEnvGroup)

    # ==================== 新增：项目路径管理 ====================

    def setup_workflow_paths_settings(self):
        """本地项目路径管理"""
        self.workflowPathsGroup = SettingCardGroup(" 画布管理", self.view)

        self.workflowPathsCard = FolderListSettingCard(
            configItem=self.cfg.workflow_paths,
            title="本地画布路径",
            content="管理多个画布工作目录",
            directory="./",
            parent=self.workflowPathsGroup
        )
        # 连接配置变化信号，自动保存
        self.cfg.workflow_paths.valueChanged.connect(self.onConfigChanged)

        self.workflowPathsGroup.addSettingCard(self.workflowPathsCard)
        self.vBoxLayout.addWidget(self.workflowPathsGroup)

    # ==================== 新增：项目路径管理 ====================

    def setup_project_paths_settings(self):
        """本地项目路径管理"""
        self.projectPathsGroup = SettingCardGroup(" 项目管理", self.view)

        self.projectPathsCard = FolderListSettingCard(
            configItem=self.cfg.project_paths,
            title="本地项目路径",
            content="管理多个项目工作目录",
            directory="./",
            parent=self.projectPathsGroup
        )
        # 连接配置变化信号，自动保存
        self.cfg.project_paths.valueChanged.connect(self.onConfigChanged)

        self.projectPathsGroup.addSettingCard(self.projectPathsCard)
        self.vBoxLayout.addWidget(self.projectPathsGroup)

    # ==================== 新增：画布详细设置 ====================

    def setup_canvas_settings(self):
        """画布详细设置"""
        self.canvasGroup = SettingCardGroup(" 画布设置", self.view)

        self.showGridCard = OptionsSettingCard(
            self.cfg.canvas_grid_mode,
            get_icon("画布"),
            "显示网格",
            "在画布上显示辅助网格",
            texts=["线网格", "点网格", "无网格"],
            parent=self.canvasGroup
        )
        # 连接配置变化信号，自动保存
        self.cfg.canvas_grid_mode.valueChanged.connect(self.onConfigChanged)

        self.gridSizeCard = PushSettingCard(
            "修改",
            get_icon("画布"),
            "网格大小 (px)",
            str(self.cfg.canvas_grid_size.value),
            parent=self.canvasGroup
        )
        self.gridSizeCard.clicked.connect(self.onGridSizeClicked)

        self.autoSaveCard = SwitchSettingCard(
            get_icon("画布"),
            "自动保存",
            "每隔一段时间自动保存当前项目",
            configItem=self.cfg.canvas_auto_save,
            parent=self.canvasGroup
        )
        # 连接配置变化信号，自动保存
        self.cfg.canvas_auto_save.valueChanged.connect(self.onConfigChanged)

        self.autoSaveIntervalCard = PushSettingCard(
            "修改",
            get_icon("画布"),
            "自动保存间隔 (秒)",
            str(self.cfg.canvas_auto_save_interval.value),
            parent=self.canvasGroup
        )
        self.autoSaveIntervalCard.clicked.connect(self.onAutoSaveIntervalClicked)

        self.pipelayoutCard = OptionsSettingCard(
            self.cfg.canvas_pipelayout,
            get_icon("画布"),
            "流程图连线类型",
            "",
            texts=["直线", "曲线", "折线"],
            parent=self.canvasGroup
        )
        # 连接配置变化信号，自动保存
        self.cfg.canvas_pipelayout.valueChanged.connect(self.onConfigChanged)

        self.pipeDirectionCard = OptionsSettingCard(
            self.cfg.canvas_direction,
            get_icon("画布"),
            "流程图延展方向",
            "",
            texts=["水平", "垂直"],
            parent=self.canvasGroup
        )
        # 连接配置变化信号，自动保存
        self.cfg.canvas_direction.valueChanged.connect(self.onConfigChanged)

        self.canvasGroup.addSettingCard(self.showGridCard)
        self.canvasGroup.addSettingCard(self.gridSizeCard)
        self.canvasGroup.addSettingCard(self.autoSaveCard)
        self.canvasGroup.addSettingCard(self.autoSaveIntervalCard)
        self.canvasGroup.addSettingCard(self.pipelayoutCard)
        self.canvasGroup.addSettingCard(self.pipeDirectionCard)

        self.vBoxLayout.addWidget(self.canvasGroup)

    # ==================== 信号处理方法 ====================

    def onMinicondaVersionClicked(self):
        """修改 Miniconda 版本"""
        self.showLineEditDialog(
            "Miniconda 版本",
            self.cfg.miniconda_version.value,
            lambda x: (
                self.cfg.set(self.cfg.miniconda_version, x),
                # 自动保存
                self.cfg.save_config(),
                self.configChanged.emit()
            ),
            placeholder="例如: 23.11.0"
        )

    def onExportDirClicked(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择导出目录",
            self.cfg.export_dir.value
        )
        if folder:
            self.cfg.set(self.cfg.export_dir, folder)
            self.exportDirCard.setContent(folder)
            Path(folder).mkdir(parents=True, exist_ok=True)
            # 自动保存
            self.cfg.save_config()
            self.configChanged.emit()
            InfoBar.success("设置已保存", f"导出目录已更新为 {folder}", parent=self)

    def onGridSizeClicked(self):
        self.showNumberEditDialog(
            "网格大小",
            self.cfg.canvas_grid_size.value,
            lambda x: (
                self.cfg.set(self.cfg.canvas_grid_size, x),
                # 自动保存
                self.cfg.save_config(),
                self.configChanged.emit()
            ),
            min_val=5,
            max_val=100
        )

    def onAutoSaveIntervalClicked(self):
        self.showNumberEditDialog(
            "自动保存间隔",
            self.cfg.canvas_auto_save_interval.value,
            lambda x: (
                self.cfg.set(self.cfg.canvas_auto_save_interval, x),
                # 自动保存
                self.cfg.save_config(),
                self.configChanged.emit()
            ),
            min_val=10,
            max_val=600
        )

    def onConfigChanged(self):
        """当配置项通过 SettingCard 自动更改时触发"""
        self.cfg.save_config()
        # 可选：发出配置更改信号，通知其他组件
        self.configChanged.emit()

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
        w.yesButton.setText("保存")
        w.cancelButton.setText("取消")

        if w.exec():
            new_value = lineEdit.text().strip()
            if new_value:
                callback(new_value)
                InfoBar.success("设置已保存", f"{title} 已更新", parent=self)
            else:
                InfoBar.warning("输入无效", f"{title} 不能为空", parent=self)

    def showNumberEditDialog(self, title: str, current_value: int, callback, min_val=0, max_val=100):
        w = MessageBox(title, f"请输入 {min_val} ~ {max_val} 之间的整数", self)

        lineEdit = LineEdit(w)
        lineEdit.setText(str(current_value))
        lineEdit.setFixedWidth(200)
        lineEdit.setValidator(QtGui.QIntValidator(min_val, max_val))

        w.vBoxLayout.insertWidget(1, lineEdit, 0, Qt.AlignCenter)
        w.yesButton.setText("保存")
        w.cancelButton.setText("取消")

        if w.exec():
            try:
                value = int(lineEdit.text())
                if min_val <= value <= max_val:
                    callback(value)
                    InfoBar.success("设置已保存", f"{title} 已更新为 {value}", parent=self)
                else:
                    InfoBar.warning("输入无效", f"请输入 {min_val}~{max_val} 之间的值", parent=self)
            except ValueError:
                InfoBar.error("格式错误", "请输入有效整数", parent=self)