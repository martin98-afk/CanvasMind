# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QTimer, QEvent, QSize
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QApplication,
    QScrollArea,
    QHBoxLayout,
    QSizePolicy,
    QFrame,
    QDialog,
    QStackedWidget,
    QPushButton,
)
from qfluentwidgets import (
    StrongBodyLabel,
    TransparentPushButton,
    BodyLabel,
    PrimaryPushSettingCard,
    SwitchSettingCard,
    FluentIcon,
)

from app.widgets.card_widget.list_setting_card import FontListSettingCard
from app.utils.config import Settings
from app.utils.utils import get_icon, get_unified_font


class SettingDialog(QDialog):
    configChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_widget = None
        self._resizing = False
        self._start_pos = None
        self._start_width = None
        self._min_width = 750
        self._max_width = 1200
        self._base_x = 0
        self._resize_zone_width = 5
        self._follow_window = False
        self.cfg = Settings.get_instance()
        self._last_parent_pos = None
        self._event_filter_installed = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._perform_save_to_disk)

        self.setup_ui()

    def setup_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(
            """
            SettingDialog {
                background-color: transparent;
            }
        """
        )
        self.setObjectName("settingPopup")
        self.setContentsMargins(10, 10, 10, 10)

        container = QFrame(self)
        container.setObjectName("container")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setStyleSheet(
            """
            QFrame#container {
                background-color: #2b2b2b;
                border-radius: 12px;
                border: 1px solid #3d3d3d;
            }
        """
        )
        container.setAutoFillBackground(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(container)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(40)
        header.setStyleSheet(
            "background-color: #2b2b2b; border-bottom: 1px solid #3d3d3d; border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 12, 0)
        header_layout.setSpacing(8)

        title_label = StrongBodyLabel(self.tr("系统设置"))
        title_label.setFont(get_unified_font(14, True))
        title_label.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.close_btn = TransparentPushButton("✕")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setStyleSheet("""
            TransparentPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            TransparentPushButton:hover {
                background-color: #ff5f56;
                color: #ffffff;
            }
        """)
        self.close_btn.clicked.connect(self.hidePopup)
        header_layout.addWidget(self.close_btn)

        container_layout.addWidget(header)

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #2b2b2b;")
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.nav_widget = QWidget()
        self.nav_widget.setFixedWidth(180)
        self.nav_widget.setStyleSheet("background-color: #252525;")
        nav_layout = QVBoxLayout(self.nav_widget)
        nav_layout.setContentsMargins(8, 16, 8, 8)
        nav_layout.setSpacing(4)

        self.nav_items = {}
        self.nav_buttons = {}
        categories = [
            ("version", self.tr("通用"), "配置"),
            ("llm", self.tr("大模型"), "大模型"),
            ("workflow", self.tr("画布管理"), "画布管理"),
            ("project", self.tr("项目管理"), "项目"),
            ("runtime", self.tr("运行环境"), "运行环境"),
            ("canvas_run", self.tr("画布运行"), "运行模式"),
            ("canvas_io", self.tr("画布保存"), "自动保存"),
            ("canvas_display", self.tr("画布显示"), "画布"),
        ]
        for key, label, icon_name in categories:
            btn = self._create_nav_button(key, label, icon_name)
            self.nav_buttons[key] = btn
            nav_layout.addWidget(btn)
        nav_layout.addStretch()

        nav_footer = QWidget()
        nav_footer.setStyleSheet("background-color: transparent;")
        footer_layout = QVBoxLayout(nav_footer)
        footer_layout.setContentsMargins(12, 0, 0, 0)
        footer_layout.setSpacing(2)

        app_name = StrongBodyLabel("CanvasMind")
        app_name.setFont(get_unified_font(12, True))
        app_name.setStyleSheet("color: #888888; background: transparent;")
        footer_layout.addWidget(app_name)

        version_text = self.tr("{}").format(self.cfg.current_version)
        version_label = BodyLabel(version_text)
        version_label.setFont(get_unified_font(11))
        version_label.setStyleSheet("color: #666666; background: transparent;")
        footer_layout.addWidget(version_label)

        nav_layout.addWidget(nav_footer)

        for btn in self.nav_buttons.values():
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #aaaaaa;
                    border: none;
                    border-radius: 6px;
                    text-align: left;
                    padding-left: 12px;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                    color: #ffffff;
                }
            """)

        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_stack.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #2b2b2b;
            }
            QScrollBar:vertical {
                border: none;
                background: #2b2b2b;
                width: 10px;
                margin: 4px 2px 4px 2px;
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
        """)

        self.content_widgets = {}
        self._create_content_pages()

        self._select_nav("version")

        content_layout.addWidget(self.nav_widget)
        content_layout.addWidget(self.content_stack, 1)

        container_layout.addWidget(content_widget, 1)

        self.resize(1000, 600)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_content_width()

    def _update_content_width(self):
        nav_width = 180
        scrollbar_width = 20
        margin = 32
        available = self.width() - nav_width - scrollbar_width - margin
        for key, scroll in self.content_widgets.items():
            if scroll.widget():
                scroll.widget().setMaximumWidth(max(available, 500))

    def _create_nav_button(self, key, text, icon_name=None):
        btn = QPushButton()
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)

        if icon_name:
            icon = get_icon(icon_name)
            btn.setIcon(icon)
            btn.setIconSize(QSize(18, 18))

        btn.setText("  " + text)
        btn.setFont(get_unified_font(13, True))
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #aaaaaa;
                border: none;
                border-radius: 6px;
                text-align: left;
                padding-left: 12px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
                color: #ffffff;
            }
        """)
        btn._nav_key = key
        btn.clicked.connect(lambda: self._select_nav(btn._nav_key))
        return btn

    def _select_nav(self, key):
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #0078d4;
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        text-align: left;
                        padding-left: 12px;
                    }
                    QPushButton:hover {
                        background-color: #1a8cd4;
                        color: #ffffff;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #aaaaaa;
                        border: none;
                        border-radius: 6px;
                        text-align: left;
                        padding-left: 12px;
                    }
                    QPushButton:hover {
                        background-color: #3d3d3d;
                        color: #ffffff;
                    }
                """)
        if key in self.content_widgets:
            self.content_stack.setCurrentWidget(self.content_widgets[key])

    def _create_content_pages(self):
        keys = [
            "version",
            "llm",
            "workflow",
            "project",
            "runtime",
            "canvas_run",
            "canvas_io",
            "canvas_display",
        ]
        for key in keys:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            content = QWidget()
            content.setStyleSheet("background-color: #2b2b2b; border: none;")
            content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            layout = QVBoxLayout(content)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(16)

            if key == "version":
                self._setup_version_info(layout)
            elif key == "llm":
                self._setup_llm_settings(layout)
            elif key == "workflow":
                self._setup_workflow_paths_settings(layout)
            elif key == "project":
                self._setup_project_paths_settings(layout)
            elif key == "runtime":
                self._setup_runtime_env_settings(layout)
            elif key == "canvas_run":
                self._setup_canvas_run_settings(layout)
            elif key == "canvas_io":
                self._setup_canvas_io_settings(layout)
            elif key == "canvas_display":
                self._setup_canvas_display_settings(layout)

            layout.addStretch(1)
            scroll.setWidget(content)
            self.content_widgets[key] = scroll
            self.content_stack.addWidget(scroll)

    def _setup_version_info(self, layout):
        self.versionGroup = QWidget()
        self.versionGroup.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        versionGroupLayout = QVBoxLayout(self.versionGroup)
        versionGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("通用设置"))
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
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

        self.canvasFontCard = FontListSettingCard(
            icon=get_icon("字体"),
            fontListItem=self.cfg.canvas_font_list,
            fontSelectedItem=self.cfg.canvas_font_selected,
            title=self.tr("画布显示字体设置"),
            content=self.tr("管理字体列表和选择当前字体"),
            parent=self.versionGroup,
            home=self,
        )
        self.canvasFontCard.fontChanged.connect(self.onConfigChanged)
        self.canvasFontCard.fontSelectedChanged.connect(self.onConfigChanged)

        versionGroupLayout.addWidget(self.info_card)
        versionGroupLayout.addWidget(self.userNameCard)
        versionGroupLayout.addWidget(self.autoUpdateCard)
        versionGroupLayout.addWidget(self.canvasFontCard)
        layout.addWidget(self.versionGroup)

    def _setup_llm_settings(self, layout):
        from qfluentwidgets import (
            PrimaryPushSettingCard,
            SwitchSettingCard,
            RangeSettingCard,
            OptionsSettingCard,
        )
        from app.widgets.card_widget.provider_setting_card import (
            ProviderListSettingCard,
        )

        self.llmGroup = QWidget()
        self.llmGroup.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        llmGroupLayout = QVBoxLayout(self.llmGroup)
        llmGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("大模型服务商"))
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
        llmGroupLayout.addWidget(group_label)

        self.llmProviderCard = ProviderListSettingCard(
            icon=get_icon("大模型"),
            configItem=self.cfg.llm_saved_providers,
            defaultProviderItem=self.cfg.llm_selected_model,
            title=self.tr("已保存的服务商"),
            content=self.tr("管理已配置的大模型服务商，可选择默认使用哪个"),
            parent=self.llmGroup,
            home=self,
        )
        self.cfg.llm_saved_providers.valueChanged.connect(self.onConfigChanged)
        self.cfg.llm_selected_model.valueChanged.connect(self.onConfigChanged)

        self.llmThinkingCard = SwitchSettingCard(
            get_icon("智能体"),
            self.tr("启用思考过程"),
            self.tr("是否让大模型输出思考过程"),
            configItem=self.cfg.llm_enable_thinking,
            parent=self.llmGroup,
        )
        self.cfg.llm_enable_thinking.valueChanged.connect(self.onConfigChanged)

        llmGroupLayout.addWidget(self.llmProviderCard)
        llmGroupLayout.addWidget(self.llmThinkingCard)
        layout.addWidget(self.llmGroup)

    def _setup_workflow_paths_settings(self, layout):
        from qfluentwidgets import FolderListSettingCard

        self.workflowPathsGroup = QWidget()
        self.workflowPathsGroup.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Preferred
        )
        workflowGroupLayout = QVBoxLayout(self.workflowPathsGroup)
        workflowGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("画布管理"))
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
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
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
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
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
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
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
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
            self.tr("节点运行超时时间（秒）"),
            self.tr("超时节点自动中止"),
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
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
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

        self.canvasDisplayGroup = QWidget()
        self.canvasDisplayGroup.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Preferred
        )
        canvasDisplayGroupLayout = QVBoxLayout(self.canvasDisplayGroup)
        canvasDisplayGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("画布显示设置"))
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
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

        canvasDisplayGroupLayout.addWidget(self.nodeResizeMemoryCard)
        canvasDisplayGroupLayout.addWidget(self.PipeWidthCard)
        canvasDisplayGroupLayout.addWidget(self.NodeProxyCard)
        canvasDisplayGroupLayout.addWidget(self.nodeAnimationCard)
        canvasDisplayGroupLayout.addWidget(self.autoCollapseCard)
        canvasDisplayGroupLayout.addWidget(self.showGridCard)
        canvasDisplayGroupLayout.addWidget(self.pipelayoutCard)
        layout.addWidget(self.canvasDisplayGroup)

    def _on_check_update(self):
        if self._parent_widget and hasattr(self._parent_widget, "updater"):
            self._parent_widget.updater.check_update()

    def _on_user_name_clicked(self, button):
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

    def enterEvent(self, event):
        super().enterEvent(event)
        self._remove_event_filter()

    def leaveEvent(self, event):
        self._install_event_filter()
        super().leaveEvent(event)

    def _install_event_filter(self):
        if not self._event_filter_installed:
            QApplication.instance().installEventFilter(self)
            self._event_filter_installed = True

    def _remove_event_filter(self):
        if self._event_filter_installed:
            QApplication.instance().removeEventFilter(self)
            self._event_filter_installed = False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if not self.geometry().contains(event.globalPos()):
                self.hidePopup()
                return False
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._install_event_filter()

    def hideEvent(self, event):
        self._remove_event_filter()
        super().hideEvent(event)

    def show_at_left(self, parent_widget, button_top_right):
        self._parent_widget = parent_widget
        self._follow_window = False

        self.resize(850, 600)
        self.move(
            (QApplication.desktop().screenGeometry().width() - self.width()) // 2,
            (QApplication.desktop().screenGeometry().height() - self.height()) // 2,
        )
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
        self._remove_event_filter()
        self.hide()

    def deleteLater(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._perform_save_to_disk()
        self._remove_event_filter()
        super().deleteLater()
