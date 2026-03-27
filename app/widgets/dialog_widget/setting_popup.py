# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QTimer
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QApplication,
    QScrollArea,
    QHBoxLayout,
    QSizePolicy,
    QFrame,
)
from qfluentwidgets import StrongBodyLabel

from app.utils.config import Settings
from app.utils.utils import resource_path, get_icon


class SettingPopupWidget(QFrame):
    configChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_widget = None
        self._resizing = False
        self._start_pos = None
        self._start_width = None
        self._min_width = 700
        self._max_width = 1200
        self._base_x = 0
        self._resize_zone_width = 5
        self._follow_window = False
        self.cfg = Settings.get_instance()
        self._last_parent_pos = None

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._perform_save_to_disk)

        self.setup_ui()

    def setup_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(
            """
            QFrame {
                border: none;
                background-color: #1e1e1e;
                border-right: %dpx solid #404040;
            }
        """
            % self._resize_zone_width
        )
        self.setObjectName("settingPopup")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet(
            "background-color: #1e1e1e; border-bottom: 1px solid #3c3c3c;"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(8)

        title_label = StrongBodyLabel(self.tr("系统设置"))
        title_label.setStyleSheet("color: white;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.resize_grip = QWidget()
        self.resize_grip.setFixedSize(20, 16)
        self.resize_grip.setStyleSheet("""
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 transparent, stop:0.5 #666666, stop:1 transparent);
        """)
        header_layout.addWidget(self.resize_grip)

        main_layout.addWidget(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1e1e1e;
            }
            QScrollBar:vertical {
                border: none;
                background: #1e1e1e;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                border: none;
                background: transparent;
                height: 0px;
            }
        """)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("contentWidget")
        self.content_widget.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(20, 20, 28, 20)
        self.content_layout.setSpacing(15)
        self.content_layout.setSizeConstraint(QVBoxLayout.SetMaximumSize)

        self._setup_version_info(self.content_layout)
        self._setup_workflow_paths_settings(self.content_layout)
        self._setup_project_paths_settings(self.content_layout)
        self._setup_runtime_env_settings(self.content_layout)
        self._setup_canvas_run_settings(self.content_layout)
        self._setup_canvas_io_settings(self.content_layout)
        self._setup_canvas_display_settings(self.content_layout)

        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area)

        self.resize(750, 500)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        available_width = self.width() - self._resize_zone_width
        if self.content_widget.maximumWidth() != available_width:
            self.content_widget.setMaximumWidth(available_width)

    def _setup_version_info(self, layout):
        from qfluentwidgets import PrimaryPushSettingCard, SwitchSettingCard, FluentIcon

        self.versionGroup = QWidget()
        self.versionGroup.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        versionGroupLayout = QVBoxLayout(self.versionGroup)
        versionGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("版本信息"))
        group_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        versionGroupLayout.addWidget(group_label)

        copyright_text = self.tr("© 版权所有 2025 martin-afk. 当前版本：{}").format(
            self.cfg.current_version
        )
        self.info_card = PrimaryPushSettingCard(
            text=self.tr("检查更新"),
            icon=FluentIcon.INFO,
            title=self.tr("关于"),
            content=copyright_text,
            parent=self.versionGroup,
        )
        self.info_card.clicked.connect(self._on_check_update)

        self.userNameCard = PrimaryPushSettingCard(
            self.cfg.user_name.value,
            get_icon("用户名"),
            self.tr("当前用户名"),
            self.tr("用户名用于云端组件管理"),
            parent=self.versionGroup,
        )
        self.userNameCard.clicked.connect(
            lambda: self._on_user_name_clicked(self.userNameCard.button)
        )

        self.autoUpdateCard = SwitchSettingCard(
            get_icon("更新"),
            self.tr("自动更新"),
            self.tr("是否开启自动版本更新检查"),
            configItem=self.cfg.auto_check_update,
            parent=self.versionGroup,
        )
        self.cfg.auto_check_update.valueChanged.connect(self.onConfigChanged)

        versionGroupLayout.addWidget(self.info_card)
        versionGroupLayout.addWidget(self.userNameCard)
        versionGroupLayout.addWidget(self.autoUpdateCard)
        layout.addWidget(self.versionGroup)

    def _setup_workflow_paths_settings(self, layout):
        from qfluentwidgets import FolderListSettingCard

        self.workflowPathsGroup = QWidget()
        self.workflowPathsGroup.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Preferred
        )
        workflowGroupLayout = QVBoxLayout(self.workflowPathsGroup)
        workflowGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("画布管理"))
        group_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        workflowGroupLayout.addWidget(group_label)

        self.workflowPathsCard = FolderListSettingCard(
            configItem=self.cfg.workflow_paths,
            title=self.tr("本地画布路径"),
            content=self.tr("管理多个画布工作目录"),
            directory="./",
            parent=self.workflowPathsGroup,
        )
        self.cfg.workflow_paths.valueChanged.connect(self.onConfigChanged)
        workflowGroupLayout.addWidget(self.workflowPathsCard)
        layout.addWidget(self.workflowPathsGroup)

    def _setup_project_paths_settings(self, layout):
        from qfluentwidgets import FolderListSettingCard

        self.projectPathsGroup = QWidget()
        self.projectPathsGroup.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Preferred
        )
        projectGroupLayout = QVBoxLayout(self.projectPathsGroup)
        projectGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("项目管理"))
        group_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        projectGroupLayout.addWidget(group_label)

        self.projectPathsCard = FolderListSettingCard(
            configItem=self.cfg.project_paths,
            title=self.tr("本地项目路径"),
            content=self.tr("管理多个项目工作目录"),
            directory="./",
            parent=self.projectPathsGroup,
        )
        self.cfg.project_paths.valueChanged.connect(self.onConfigChanged)
        projectGroupLayout.addWidget(self.projectPathsCard)
        layout.addWidget(self.projectPathsGroup)

    def _setup_runtime_env_settings(self, layout):
        from qfluentwidgets import PrimaryPushSettingCard
        from app.widgets.card_widget.list_setting_card import PackageListSettingCard

        self.runtimeEnvGroup = QWidget()
        self.runtimeEnvGroup.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        runtimeGroupLayout = QVBoxLayout(self.runtimeEnvGroup)
        runtimeGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("运行环境管理"))
        group_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        runtimeGroupLayout.addWidget(group_label)

        self.pythonVersionsCard = PackageListSettingCard(
            icon=get_icon("python"),
            configItem=self.cfg.python_versions,
            title=self.tr("Python 版本"),
            content=self.tr("选择支持的 Python 版本"),
            parent=self.runtimeEnvGroup,
            home=self,
        )
        self.cfg.python_versions.valueChanged.connect(self.onConfigChanged)

        self.mirrorsCard = PackageListSettingCard(
            icon=get_icon("镜像源"),
            configItem=self.cfg.mirrors,
            title=self.tr("镜像源管理"),
            content=self.tr("选择合适的镜像源连接"),
            parent=self.runtimeEnvGroup,
            home=self,
        )
        self.cfg.mirrors.valueChanged.connect(self.onConfigChanged)

        self.minicondaVersionCard = PrimaryPushSettingCard(
            self.cfg.miniconda_version.value,
            get_icon("Miniconda"),
            self.tr("Miniconda 版本"),
            self.tr("用于修改 Miniconda 安装的版本"),
            parent=self.runtimeEnvGroup,
        )
        self.minicondaVersionCard.clicked.connect(
            lambda: self._on_miniconda_version_clicked(self.minicondaVersionCard.button)
        )

        self.defaultPackagesCard = PackageListSettingCard(
            icon=get_icon("安装包"),
            configItem=self.cfg.default_packages,
            title=self.tr("默认安装包"),
            content=self.tr("管理默认安装的 Python 包"),
            parent=self.runtimeEnvGroup,
            home=self,
        )
        self.cfg.default_packages.valueChanged.connect(self.onConfigChanged)

        runtimeGroupLayout.addWidget(self.pythonVersionsCard)
        runtimeGroupLayout.addWidget(self.mirrorsCard)
        runtimeGroupLayout.addWidget(self.minicondaVersionCard)
        runtimeGroupLayout.addWidget(self.defaultPackagesCard)
        layout.addWidget(self.runtimeEnvGroup)

    def _setup_canvas_run_settings(self, layout):
        from qfluentwidgets import (
            SwitchSettingCard,
            RangeSettingCard,
            OptionsSettingCard,
        )

        self.canvasGroup = QWidget()
        self.canvasGroup.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        canvasGroupLayout = QVBoxLayout(self.canvasGroup)
        canvasGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("画布运行设置"))
        group_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        canvasGroupLayout.addWidget(group_label)

        self.timeoutToggleCard = SwitchSettingCard(
            get_icon("运行模式"),
            self.tr("是否启用节点超时"),
            self.tr("如果启用，节点在超时时间以后会自动中止"),
            configItem=self.cfg.node_run_timeout_toggle,
            parent=self.canvasGroup,
        )
        self.timeoutToggleCard.checkedChanged.connect(self.onConfigChanged)

        self.nodeTimeoutCard = RangeSettingCard(
            self.cfg.node_run_timeout,
            get_icon("运行模式"),
            self.tr("节点运行超时时间"),
            self.tr("决定节点最长运行时间（秒），如果超过则会直接中止运行"),
            parent=self.canvasGroup,
        )
        self.nodeTimeoutCard.valueChanged.connect(self.onConfigChanged)

        self.runParallelCard = SwitchSettingCard(
            get_icon("运行模式"),
            self.tr("是否并行运行"),
            self.tr("是否并行运行画布节点"),
            configItem=self.cfg.run_parallel,
            parent=self.canvasGroup,
        )
        self.runParallelCard.checkedChanged.connect(self.onConfigChanged)

        self.parallelNumCard = RangeSettingCard(
            self.cfg.run_parallel_max_workers,
            get_icon("运行模式"),
            self.tr("运行并行度"),
            self.tr("最大并行度控制"),
            parent=self.canvasGroup,
        )
        self.parallelNumCard.valueChanged.connect(self.onConfigChanged)

        self.communicationMethodCard = OptionsSettingCard(
            self.cfg.communication_method,
            get_icon("运行模式"),
            self.tr("节点与UI通信方式"),
            self.tr("ZMQ通信或日志通信"),
            texts=[self.tr("ZMQ通信"), self.tr("日志通信")],
            parent=self.canvasGroup,
        )
        self.communicationMethodCard.optionChanged.connect(self.onConfigChanged)

        canvasGroupLayout.addWidget(self.timeoutToggleCard)
        canvasGroupLayout.addWidget(self.nodeTimeoutCard)
        canvasGroupLayout.addWidget(self.runParallelCard)
        canvasGroupLayout.addWidget(self.parallelNumCard)
        canvasGroupLayout.addWidget(self.communicationMethodCard)
        layout.addWidget(self.canvasGroup)

    def _setup_canvas_io_settings(self, layout):
        from qfluentwidgets import SwitchSettingCard, RangeSettingCard

        self.canvasIOGroup = QWidget()
        self.canvasIOGroup.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        canvasIOGroupLayout = QVBoxLayout(self.canvasIOGroup)
        canvasIOGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("画布保存设置"))
        group_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        canvasIOGroupLayout.addWidget(group_label)

        self.autoSaveCard = SwitchSettingCard(
            get_icon("自动保存"),
            self.tr("自动保存"),
            self.tr("每隔一段时间自动保存当前项目"),
            configItem=self.cfg.canvas_auto_save,
            parent=self.canvasIOGroup,
        )
        self.autoSaveCard.checkedChanged.connect(self.onConfigChanged)

        self.autoSaveIntervalCard = RangeSettingCard(
            self.cfg.canvas_auto_save_interval,
            get_icon("自动保存"),
            self.tr("修改"),
            self.tr("自动保存间隔 (秒)"),
            parent=self.canvasIOGroup,
        )
        self.autoSaveIntervalCard.valueChanged.connect(self.onConfigChanged)

        canvasIOGroupLayout.addWidget(self.autoSaveCard)
        canvasIOGroupLayout.addWidget(self.autoSaveIntervalCard)
        layout.addWidget(self.canvasIOGroup)

    def _setup_canvas_display_settings(self, layout):
        from qfluentwidgets import (
            SwitchSettingCard,
            RangeSettingCard,
            OptionsSettingCard,
        )
        from app.widgets.card_widget.list_setting_card import FontListSettingCard

        self.canvasDisplayGroup = QWidget()
        self.canvasDisplayGroup.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Preferred
        )
        canvasDisplayGroupLayout = QVBoxLayout(self.canvasDisplayGroup)
        canvasDisplayGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("画布显示设置"))
        group_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        canvasDisplayGroupLayout.addWidget(group_label)

        self.nodeAnimationCard = SwitchSettingCard(
            get_icon("画布"),
            self.tr("节点动画"),
            self.tr("开关节点缩放、新建动画"),
            configItem=self.cfg.node_animation,
            parent=self.canvasDisplayGroup,
        )
        self.nodeAnimationCard.checkedChanged.connect(self.onConfigChanged)

        self.nodeResizeMemoryCard = SwitchSettingCard(
            get_icon("画布"),
            self.tr("节点缩放记忆"),
            self.tr("用于控制画布加载时是否还原上一次保存时的节点缩放情况"),
            configItem=self.cfg.canvas_resize_memory,
            parent=self.canvasDisplayGroup,
        )
        self.nodeResizeMemoryCard.checkedChanged.connect(self.onConfigChanged)

        self.autoCollapseCard = SwitchSettingCard(
            get_icon("画布"),
            self.tr("Proxy模式自动收缩"),
            self.tr("当节点处于隐藏控件的proxy模式下是否自动缩小节点为固定大小"),
            configItem=self.cfg.canvas_auto_collapse,
            parent=self.canvasDisplayGroup,
        )
        self.autoCollapseCard.checkedChanged.connect(self.onConfigChanged)

        self.showGridCard = OptionsSettingCard(
            self.cfg.canvas_grid_mode,
            get_icon("画布"),
            self.tr("显示网格"),
            self.tr("在画布上显示辅助网格"),
            texts=[self.tr("线网格"), self.tr("点网格"), self.tr("无网格")],
            parent=self.canvasDisplayGroup,
        )
        self.showGridCard.optionChanged.connect(self.onConfigChanged)

        self.NodeProxyCard = RangeSettingCard(
            self.cfg.node_proxy_size,
            get_icon("画布"),
            self.tr("节点细节绘制距离"),
            self.tr("设置节点中控件最小绘制距离"),
            parent=self.canvasDisplayGroup,
        )
        self.NodeProxyCard.valueChanged.connect(self.onConfigChanged)

        self.PipeWidthCard = RangeSettingCard(
            self.cfg.canvas_pipe_width,
            get_icon("画布"),
            self.tr("画布连线粗细"),
            self.tr("控制画布节点之间连线粗细"),
            parent=self.canvasDisplayGroup,
        )
        self.PipeWidthCard.valueChanged.connect(self.onConfigChanged)

        self.pipelayoutCard = OptionsSettingCard(
            self.cfg.canvas_pipelayout,
            get_icon("画布"),
            self.tr("流程图连线类型"),
            "",
            texts=[self.tr("直线"), self.tr("曲线"), self.tr("折线")],
            parent=self.canvasDisplayGroup,
        )
        self.pipelayoutCard.optionChanged.connect(self.onConfigChanged)

        self.canvasFontCard = FontListSettingCard(
            icon=get_icon("画布"),
            fontListItem=self.cfg.canvas_font_list,
            fontSelectedItem=self.cfg.canvas_font_selected,
            title=self.tr("画布显示字体设置"),
            content=self.tr("管理字体列表和选择当前字体"),
            parent=self.canvasDisplayGroup,
            home=self,
        )
        self.canvasFontCard.fontChanged.connect(self.onConfigChanged)
        self.canvasFontCard.fontSelectedChanged.connect(self.onConfigChanged)

        canvasDisplayGroupLayout.addWidget(self.nodeResizeMemoryCard)
        canvasDisplayGroupLayout.addWidget(self.PipeWidthCard)
        canvasDisplayGroupLayout.addWidget(self.NodeProxyCard)
        canvasDisplayGroupLayout.addWidget(self.nodeAnimationCard)
        canvasDisplayGroupLayout.addWidget(self.autoCollapseCard)
        canvasDisplayGroupLayout.addWidget(self.canvasFontCard)
        canvasDisplayGroupLayout.addWidget(self.showGridCard)
        canvasDisplayGroupLayout.addWidget(self.pipelayoutCard)
        layout.addWidget(self.canvasDisplayGroup)

    def _on_check_update(self):
        if self._parent_widget and hasattr(self._parent_widget, "updater"):
            self._parent_widget.updater.check_update()

    def _on_user_name_clicked(self, button):
        from PyQt5 import QtGui
        from PyQt5.QtCore import Qt
        from qfluentwidgets import LineEdit, MessageBox, InfoBar

        w = MessageBox(self.tr("输入当前用户名"), "", self)
        w.contentLabel.hide()

        lineEdit = LineEdit(w)
        lineEdit.setText(self.cfg.user_name.value)
        lineEdit.setFixedWidth(300)
        lineEdit.setPlaceholderText(self.tr("例如: martin98-afk"))

        w.vBoxLayout.insertWidget(1, lineEdit, 0, Qt.AlignCenter)
        w.yesButton.setText(self.tr("保存"))
        w.cancelButton.setText(self.tr("取消"))

        if w.exec():
            new_value = lineEdit.text().strip()
            if new_value:
                self.cfg.set(self.cfg.user_name, new_value)
                button.setText(new_value)
                self.cfg.save_config()
                self.configChanged.emit()
                InfoBar.success(
                    self.tr("设置已保存"),
                    self.tr("用户名已更新"),
                    parent=self,
                )

    def _on_miniconda_version_clicked(self, button):
        from PyQt5 import QtGui
        from PyQt5.QtCore import Qt
        from qfluentwidgets import LineEdit, MessageBox, InfoBar

        w = MessageBox(self.tr("Miniconda 版本"), "", self)
        w.contentLabel.hide()

        lineEdit = LineEdit(w)
        lineEdit.setText(self.cfg.miniconda_version.value)
        lineEdit.setFixedWidth(300)
        lineEdit.setPlaceholderText(self.tr("例如: 23.11.0"))

        w.vBoxLayout.insertWidget(1, lineEdit, 0, Qt.AlignCenter)
        w.yesButton.setText(self.tr("保存"))
        w.cancelButton.setText(self.tr("取消"))

        if w.exec():
            new_value = lineEdit.text().strip()
            if new_value:
                self.cfg.set(self.cfg.miniconda_version, new_value)
                button.setText(new_value)
                self.cfg.save_config()
                self.configChanged.emit()
                InfoBar.success(
                    self.tr("设置已保存"),
                    self.tr("Miniconda 版本已更新"),
                    parent=self,
                )

    def onConfigChanged(self):
        self.configChanged.emit()
        self._save_timer.start()

    def _perform_save_to_disk(self):
        try:
            self.cfg.save_config()
        except Exception as e:
            print(f"保存配置失败: {e}")

    def set_width(self, width):
        width = max(self._min_width, min(width, self._max_width))
        self.resize(width, self.height())

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and event.pos().x() >= self.width() - self._resize_zone_width
        ):
            self._resizing = True
            self._start_pos = event.globalPos()
            self._start_width = self.width()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        is_in_resize_zone = event.pos().x() >= self.width() - self._resize_zone_width

        if is_in_resize_zone:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

        if self._resizing:
            delta = event.globalPos() - self._start_pos
            new_width = self._start_width + delta.x()
            self.set_width(new_width)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)
        mouse_pos = self.mapFromGlobal(QCursor.pos())
        if mouse_pos.x() >= self.width() - self._resize_zone_width:
            self.setStyleSheet(
                """
                QFrame {
                    border: none;
                    background-color: #1e1e1e;
                    border-right: %dpx solid #0078D4;
                }
            """
                % self._resize_zone_width
            )

    def leaveEvent(self, event):
        if not self._resizing:
            self.setStyleSheet(
                """
                QFrame {
                    border: none;
                    background-color: #1e1e1e;
                    border-right: %dpx solid #404040;
                }
            """
                % self._resize_zone_width
            )
        super().leaveEvent(event)

    def show_at_left(self, parent_widget, button_top_right):
        self._parent_widget = parent_widget
        self._follow_window = True

        nav_interface = parent_widget.navigationInterface
        nav_right = nav_interface.rect().right()
        nav_right_global = nav_interface.mapToGlobal(QPoint(nav_right, 0))
        x = nav_right_global.x() + 5
        self._base_x = x

        parent_global_y = parent_widget.mapToGlobal(QPoint(0, 0)).y()
        y = parent_global_y

        popup_height = parent_widget.height()
        screen = QApplication.desktop().screenGeometry(parent_widget)
        if y + popup_height > screen.bottom():
            popup_height = screen.bottom() - y - 10

        self.move(x, y)
        self.resize(750, popup_height)
        self.show()
        self.activateWindow()

    def _update_position(self, parent_widget):
        if not self._follow_window or not self.isVisible():
            return

        nav_interface = parent_widget.navigationInterface
        nav_right = nav_interface.rect().right()
        nav_right_global = nav_interface.mapToGlobal(QPoint(nav_right, 0))
        x = nav_right_global.x() + 5

        parent_global_y = parent_widget.mapToGlobal(QPoint(0, 0)).y()
        y = parent_global_y

        popup_height = parent_widget.height()
        screen = QApplication.desktop().screenGeometry(parent_widget)
        if y + popup_height > screen.bottom():
            popup_height = screen.bottom() - y - 10

        self.move(x, y)
        self.resize(self.width(), popup_height)

    def hidePopup(self):
        self._follow_window = False
        self.hide()

    def deleteLater(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._perform_save_to_disk()
        super().deleteLater()
