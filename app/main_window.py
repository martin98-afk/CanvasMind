# -*- coding: utf-8 -*-
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QPlainTextEdit, QApplication, QDesktopWidget
from loguru import logger
from qfluentwidgets import FluentWindow, Theme, setTheme, NavigationItemPosition, SplashScreen, FluentIcon

from app.interfaces.component_developer import ComponentDeveloperWidget
from app.interfaces.exported_project_interface import ExportedProjectsPage
from app.interfaces.package_manager_interface import EnvManagerUI
from app.interfaces.settings_interface import SettingInterface
from app.interfaces.update_checker import UpdateChecker
from app.interfaces.workflow_manager import WorkflowCanvasGalleryPage
from app.utils.utils import get_icon
from app.widgets.dialog_widget.logger_dialog import QTextEditLogger


class LowCodeWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        setTheme(Theme.DARK)
        self.setWindowIcon(get_icon("logo3"))
        self.setWindowTitle("Canvas Mind")
        # 初始化日志查看器
        self.setup_log_viwer()
        # 自动最大化窗口
        screen_rect = QDesktopWidget().screenGeometry()
        screen_width, screen_height = screen_rect.width(), screen_rect.height()
        self.window_width = int(screen_width * 0.8)
        self.window_height = int(screen_height * 0.8)
        self.navigationInterface.setExpandWidth(175)
        self.resize(self.window_width, self.window_height)
        desktop = QApplication.desktop().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)
        # 生成启动界面
        # 1. 创建启动页面
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(400, 400))
        self.show()
        # 创建主界面页面
        self.package_manager = EnvManagerUI()
        self.package_manager.mgr.install_miniconda()
        self.develop_page = ComponentDeveloperWidget(self)
        self.project_manager = ExportedProjectsPage(self)
        self.workflow_manager = WorkflowCanvasGalleryPage(self)
        # 添加主界面页面
        workflow_interface = self.addSubInterface(self.workflow_manager, get_icon("工作流"), '画布管理')
        workflow_interface.clicked.connect(self.workflow_manager._schedule_refresh)
        devp_interface = self.addSubInterface(self.develop_page, get_icon("组件"), '组件管理')
        devp_interface.clicked.connect(
            lambda: self.develop_page.code_editor.code_editor.set_jedi_environment(
                self.package_manager.get_current_python_exe()
            )
        )
        project_interface = self.addSubInterface(self.project_manager, get_icon("项目"), '项目管理')
        project_interface.clicked.connect(self.project_manager.load_projects)
        package_interface = self.addSubInterface(self.package_manager, get_icon("工具包"), '环境管理')
        package_interface.clicked.connect(self.package_manager.on_env_changed)
        self.updater = UpdateChecker(self)
        self.updater.check_update()
        self.navigationInterface.addItem(
            routeKey='update',
            icon=FluentIcon.SYNC,
            text='检查更新',
            onClick=self.updater.check_update,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        # 添加日志页面
        log_interface = self.addSubInterface(
            self.log_viewer, get_icon("系统运行日志"), '执行日志', NavigationItemPosition.BOTTOM)
        log_interface.clicked.connect(
            lambda: (
                self.text_logger._clean_trailing_empty_lines(),
                self.text_logger.scroll_to_bottom(force=True)
            )
        )
        # 配置管理界面
        self.setting_card = SettingInterface(self)
        self.addSubInterface(
            self.setting_card, FluentIcon.SETTING, '系统设置', NavigationItemPosition.BOTTOM
        )
        self.splashScreen.finish()

    def setup_log_viwer(self):
        if not hasattr(self, 'log_viewer'):
            self.log_viewer = QPlainTextEdit()
            self.log_viewer.document().setDocumentMargin(0)
            self.log_viewer.setObjectName('运行日志')
            self.log_viewer.setReadOnly(True)
            self.log_viewer.setFont(QFont("Consolas", 11))
            self.log_viewer.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: #0e1117;
                    color: white;
                    border: 1px solid #2c2f36;
                    font-family: Consolas, monospace;
                    font-size: 18px;
                    padding: 10px;
                }}
                /* 纵向滚动条 */
                QTextEdit QScrollBar:vertical {{
                    background: transparent;
                    width: 8px;
                    margin: 0px;
                }}
                QTextEdit QScrollBar::handle:vertical {{
                    background: #555555;
                    border-radius: 4px;
                    min-height: 20px;
                }}
                QTextEdit QScrollBar::handle:vertical:hover {{
                    background: #888888;
                }}
                QTextEdit QScrollBar::add-line:vertical,
                QTextEdit QScrollBar::sub-line:vertical {{
                    height: 0px;
                    background: none;
                    border: none;
                }}
                QTextEdit QScrollBar::add-page:vertical, QTextEdit QScrollBar::sub-page:vertical {{
                    background: none;
                }}

                /* 横向滚动条 */
                QTextEdit QScrollBar:horizontal {{
                    background: transparent;
                    height: 8px;
                    margin: 0px;
                }}
                QTextEdit QScrollBar::handle:horizontal {{
                    background: #555555;
                    border-radius: 4px;
                    min-width: 20px;
                }}
                QTextEdit QScrollBar::handle:horizontal:hover {{
                    background: #888888;
                }}
                QTextEdit QScrollBar::add-line:horizontal,
                QTextEdit QScrollBar::sub-line:horizontal {{
                    width: 0px;
                    background: none;
                    border: none;
                }}
                QTextEdit QScrollBar::add-page:horizontal, QTextEdit QScrollBar::sub-page:horizontal {{
                    background: none;
                }}
            """)

            # 创建 sink
            self.text_logger = QTextEditLogger(self.log_viewer, max_lines=1000)
            logger.remove()
            logger.add(self.text_logger, format="{time:HH:mm:ss} | {level} | {file}:{line} {message}", level="DEBUG")