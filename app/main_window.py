# -*- coding: utf-8 -*-

from PyQt5 import QtCore
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QPlainTextEdit, QApplication, QDesktopWidget
from loguru import logger
from qfluentwidgets import (
    FluentWindow, Theme, setTheme, NavigationItemPosition,
    SplashScreen, FluentIcon
)

# --- 页面模块 ---
from app.interfaces.component_developer import ComponentDeveloperPage
from app.interfaces.exported_project_interface import ExportedProjectsPage
from app.interfaces.home_interface import HomeInterface
from app.interfaces.package_manager_interface import EnvManagerUI
from app.interfaces.settings_interface import SettingInterface
from app.interfaces.update_checker import UpdateChecker
from app.interfaces.workflow_manager import WorkflowCanvasGalleryPage
# --- 核心服务 ---
from app.scan_components import ComponentUsageTracker, ComponentScanner
from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.dialog_widget.logger_dialog import QTextEditLogger


class LowCodeWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self._init_window()
        self._setup_splash_and_startup()
        self._init_services()
        self._init_pages()
        self._setup_navigation()
        QtCore.QTimer.singleShot(500, self.finish_splash_screen)

    # region [1. 窗口基础设置]
    def _init_window(self):
        self.setAttribute(Qt.WA_TranslucentBackground)
        setTheme(Theme.DARK)
        self.setWindowIcon(get_icon("logo3"))
        self.setWindowTitle("Canvas Mind")

        # 窗口尺寸
        screen_rect = QDesktopWidget().screenGeometry()
        screen_width, screen_height = screen_rect.width(), screen_rect.height()
        self.window_width = int(0.8 * screen_width)
        self.window_height = int(0.85 * screen_height)
        desktop = QApplication.desktop().availableGeometry()
        self.desktop_w, self.desktop_h = desktop.width(), desktop.height()
        self.window_width = int(0.8 * self.desktop_w)
        self.window_height = int(0.85 * self.desktop_h)

        # 初始化位置（稍后 resize 后居中）
        self.move(self.desktop_w // 2 - self.width() // 2, self.desktop_h // 2 - self.height() // 2)
        self.navigationInterface.setExpandWidth(175)

    def _setup_splash_and_startup(self):
        self.splashScreen = SplashScreen(get_icon("logo"), self)
        self.splashScreen.titleBar.hide()
        self.splashScreen.setIconSize(QSize(400, 400))
        self.splashScreen.setFixedSize(500, 500)
        self.show()

        # 延迟初始化 heavy 操作（避免阻塞 UI）
        QtCore.QTimer.singleShot(100, self._post_init_tasks)
    # endregion

    # region [2. 核心服务初始化]
    def _init_services(self):
        # 初始化日志系统
        self._setup_log_viewer()
        # 启动监听器
        ComponentUsageTracker()
        ComponentScanner()
        # 加载配置
        self.config = Settings.get_instance()
        self.config.save()  # 确保默认配置落盘
    # endregion

    # region [3. 页面实例化（延迟创建，避免阻塞）]
    def _init_pages(self):
        self.updater = UpdateChecker(self)
        # 页面按需创建（此时不触发 heavy logic）
        self.workflow_manager = WorkflowCanvasGalleryPage(self)
        self.package_manager = EnvManagerUI(self)
        self.home_interface = HomeInterface(self)
        self.develop_page = ComponentDeveloperPage(self)
        self.project_manager = ExportedProjectsPage(self)
        self.setting_card = SettingInterface(self)
        # 信号连接
        self.workflow_manager.component_code_changed.connect(
            self.develop_page.save_component_by_full_path
        )
        self.workflow_manager.node_request_edit.connect(
            lambda full_path: (
                self.switchTo(self.develop_page),
                self.develop_page._load_component(full_path)
            )
        )
        self.project_manager.exported_projects_changed.connect(
            self.workflow_manager.exported_projects_changed.emit
        )
        self.project_manager.running_projects_changed.connect(
            self.workflow_manager.running_projects_changed.emit
        )
    # endregion

    # region [4. 导航栏配置]
    def _setup_navigation(self):
        # 主功能区
        self.addSubInterface(self.home_interface, FluentIcon.HOME, '首页')

        workflow_item = self.addSubInterface(
            self.workflow_manager, get_icon("画布管理"), '画布管理'
        )
        workflow_item.clicked.connect(self._on_workflow_clicked)

        self.addSubInterface(
            self.develop_page, get_icon("组件"), '组件管理'
        )

        project_item = self.addSubInterface(
            self.project_manager, get_icon("项目"), '项目管理'
        )
        project_item.clicked.connect(self.project_manager.load_projects)

        pkg_item = self.addSubInterface(
            self.package_manager, get_icon("工具包"), '环境管理'
        )
        pkg_item.clicked.connect(self.package_manager.on_env_changed)

        # 底部功能区
        self.navigationInterface.addItem(
            routeKey='update',
            icon=FluentIcon.SYNC,
            text='检查更新',
            onClick=self.updater.check_update,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        log_item = self.addSubInterface(
            self.log_viewer, get_icon("系统运行日志"), '执行日志',
            position=NavigationItemPosition.BOTTOM
        )
        log_item.clicked.connect(self._on_log_clicked)

        self.addSubInterface(
            self.setting_card, FluentIcon.SETTING, '系统设置',
            position=NavigationItemPosition.BOTTOM
        )
    # endregion

    # region [5. 启动流程与闪屏]
    def _post_init_tasks(self):
        """启动后异步任务"""
        # 自动安装 miniconda（非阻塞）
        self.package_manager.mgr.install_miniconda()
    # endregion

    # region [6. 导航点击回调（解耦逻辑）]
    def _on_workflow_clicked(self):
        self.workflow_manager._schedule_refresh()
        self.workflow_manager.build_recommendation_engine()

    def _on_log_clicked(self):
        self.text_logger._clean_trailing_empty_lines()
        self.text_logger.scroll_to_bottom(force=True)
    # endregion

    # region [7. 日志系统]
    def _setup_log_viewer(self):
        self.log_viewer = QPlainTextEdit()
        self.log_viewer.document().setDocumentMargin(0)
        self.log_viewer.setObjectName('运行日志')
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setFont(QFont("Consolas", 11))
        self.log_viewer.setStyleSheet(self._get_log_viewer_style())

        self.text_logger = QTextEditLogger(self.log_viewer, max_lines=1000)
        logger.remove()
        logger.add(
            self.text_logger,
            format="{time:HH:mm:ss} | {level} | {file}:{line} {message}",
            level="DEBUG"
        )

    def _get_log_viewer_style(self) -> str:
        return """
            QPlainTextEdit {
                background-color: #0e1117;
                color: white;
                border: 1px solid #2c2f36;
                font-family: Consolas, monospace;
                font-size: 18px;
                padding: 10px;
            }
            /* 垂直滚动条 */
            QPlainTextEdit QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QPlainTextEdit QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 4px;
                min-height: 20px;
            }
            QPlainTextEdit QScrollBar::handle:vertical:hover {
                background: #888888;
            }
            QPlainTextEdit QScrollBar::add-line:vertical,
            QPlainTextEdit QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
                border: none;
            }
            QPlainTextEdit QScrollBar::add-page:vertical,
            QPlainTextEdit QScrollBar::sub-page:vertical {
                background: none;
            }

            /* 水平滚动条 */
            QPlainTextEdit QScrollBar:horizontal {
                background: transparent;
                height: 8px;
                margin: 0px;
            }
            QPlainTextEdit QScrollBar::handle:horizontal {
                background: #555555;
                border-radius: 4px;
                min-width: 20px;
            }
            QPlainTextEdit QScrollBar::handle:horizontal:hover {
                background: #888888;
            }
            QPlainTextEdit QScrollBar::add-line:horizontal,
            QPlainTextEdit QScrollBar::sub-line:horizontal {
                width: 0px;
                background: none;
                border: none;
            }
            QPlainTextEdit QScrollBar::add-page:horizontal,
            QPlainTextEdit QScrollBar::sub-page:horizontal {
                background: none;
            }
        """
    # endregion

    # region [8. 闪屏结束]
    def finish_splash_screen(self):
        self.splashScreen.finish()
        self.resize(self.window_width, self.window_height)
        self.move(
            self.desktop_w // 2 - self.width() // 2,
            self.desktop_h // 2 - self.height() // 2
        )
        if self.config.auto_check_update.value:
            QtCore.QTimer.singleShot(500, self.updater.check_update)
    # endregion