# gui/setting_interface.py
import os
from pathlib import Path
from PyQt5 import QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QFileDialog
from qfluentwidgets import (
    ScrollArea, SettingCardGroup, PushSettingCard, SwitchSettingCard,
    LineEdit, FluentIcon as FIF, InfoBar, MessageBox, TextEdit,
    OptionsSettingCard, FolderListSettingCard, OptionsValidator
)

from app.utils.config import Settings
from app.utils.utils import resource_path


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
        self.setup_project_paths_settings()  # 本地项目路径
        self.setup_canvas_settings()        # 画布详细设置

        self.vBoxLayout.addStretch(1)

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

    # ==================== 新增：项目路径管理 ====================

    def setup_project_paths_settings(self):
        """本地项目路径管理"""
        self.projectPathsGroup = SettingCardGroup(" 项目管理", self.view)

        self.projectPathsCard = FolderListSettingCard(
            configItem=self.cfg.project_paths,
            title="本地项目路径",
            content="管理多个项目工作目录",
            directory=resource_path("./projects"),
            parent=self.projectPathsGroup
        )

        self.projectPathsGroup.addSettingCard(self.projectPathsCard)
        self.vBoxLayout.addWidget(self.projectPathsGroup)

    # ==================== 新增：画布详细设置 ====================

    def setup_canvas_settings(self):
        """画布详细设置"""
        self.canvasGroup = SettingCardGroup(" 画布设置", self.view)

        self.showGridCard = SwitchSettingCard(
            FIF.SAVE,
            "显示网格",
            "在画布上显示辅助网格",
            configItem=self.cfg.canvas_show_grid,
            parent=self.canvasGroup
        )

        self.gridSizeCard = PushSettingCard(
            "修改",
            FIF.SAVE,
            "网格大小 (px)",
            str(self.cfg.canvas_grid_size.value),
            parent=self.canvasGroup
        )
        self.gridSizeCard.clicked.connect(self.onGridSizeClicked)

        self.autoSaveCard = SwitchSettingCard(
            FIF.SAVE,
            "自动保存",
            "每隔一段时间自动保存当前项目",
            configItem=self.cfg.canvas_auto_save,
            parent=self.canvasGroup
        )

        self.autoSaveIntervalCard = PushSettingCard(
            "修改",
            FIF.SAVE,
            "自动保存间隔 (秒)",
            str(self.cfg.canvas_auto_save_interval.value),
            parent=self.canvasGroup
        )
        self.autoSaveIntervalCard.clicked.connect(self.onAutoSaveIntervalClicked)

        # self.defaultZoomCard = OptionsSettingCard(
        #     self.cfg.canvas_default_zoom,
        #     FIF.ZOOM,
        #     "默认缩放比例",
        #     "新建画布时的初始缩放",
        #     OptionsValidator(options=["50%", "75%", "100%", "125%", "150%"]),
        #     parent=self.canvasGroup
        # )

        self.canvasGroup.addSettingCard(self.showGridCard)
        self.canvasGroup.addSettingCard(self.gridSizeCard)
        self.canvasGroup.addSettingCard(self.autoSaveCard)
        self.canvasGroup.addSettingCard(self.autoSaveIntervalCard)
        # self.canvasGroup.addSettingCard(self.defaultZoomCard)
        self.vBoxLayout.addWidget(self.canvasGroup)

    # ==================== 信号处理方法 ====================
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
            self.configChanged.emit()
            InfoBar.success("设置已保存", f"导出目录已更新为 {folder}", parent=self)

    def onGridSizeClicked(self):
        self.showNumberEditDialog(
            "网格大小",
            self.cfg.canvas_grid_size.value,
            lambda x: self.cfg.set(self.cfg.canvas_grid_size, x),
            min_val=5,
            max_val=100
        )

    def onAutoSaveIntervalClicked(self):
        self.showNumberEditDialog(
            "自动保存间隔",
            self.cfg.canvas_auto_save_interval.value,
            lambda x: self.cfg.set(self.cfg.canvas_auto_save_interval, x),
            min_val=10,
            max_val=600
        )

    # ==================== 通用对话框 ====================

    def showLineEditDialog(self, title: str, current_value: str, callback):
        w = MessageBox(title, "", self)
        w.contentLabel.hide()

        lineEdit = LineEdit(w)
        lineEdit.setText(current_value)
        lineEdit.setFixedWidth(300)

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