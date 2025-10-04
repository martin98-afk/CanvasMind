# -*- coding: utf-8 -*-
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QPlainTextEdit, QApplication, QDesktopWidget
from loguru import logger
from qfluentwidgets import FluentWindow, Theme, setTheme, NavigationItemPosition, SplashScreen

from app.interfaces.canvas_interface import CanvasPage
from app.interfaces.component_developer import ComponentDeveloperWidget
from app.interfaces.exported_project_interface import ExportedProjectsPage
from app.interfaces.package_manager_interface import EnvManagerUI
from app.interfaces.workflow_manager import WorkflowManager
from app.utils.utils import get_icon
from app.widgets.logger_dialog import QTextEditLogger


class LowCodeWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        # 初始化日志查看器
        self.setup_log_viwer()
        setTheme(Theme.DARK)
        # 自动最大化窗口
        screen_rect = QDesktopWidget().screenGeometry()
        screen_width, screen_height = screen_rect.width(), screen_rect.height()
        self.window_width = int(screen_width * 0.75)
        self.window_height = int(screen_height * 0.75)
        self.resize(self.window_width, self.window_height)
        desktop = QApplication.desktop().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)
        # 生成启动界面
        # 1. 创建启动页面
        self.setWindowIcon(get_icon("logo3"))
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(400, 400))
        self.show()
        # 创建主界面页面
        self.package_manager = EnvManagerUI()
        self.package_manager.mgr.install_miniconda()
        self.canvas_page = CanvasPage(self)
        self.develop_page = ComponentDeveloperWidget(self)
        self.project_manager = ExportedProjectsPage(self)
        # 添加主界面页面
        self.addSubInterface(self.develop_page, get_icon("组件"), '组件开发')
        canvas_interface = self.addSubInterface(self.canvas_page, get_icon("模型"), '工作流画布')
        canvas_interface.clicked.connect(
            lambda: (
                self.canvas_page.nav_view.refresh_components(),
                self.canvas_page.register_components()
            )
        )
        project_interface = self.addSubInterface(self.project_manager, get_icon("模型"), '导出项目管理')
        self.addSubInterface(self.package_manager, get_icon("工具包"), '工具包管理')
        # 添加日志页面
        log_interface = self.addSubInterface(
            self.log_viewer, get_icon("系统运行日志"), '执行日志', NavigationItemPosition.BOTTOM)
        log_interface.clicked.connect(
            lambda: (
                self.text_logger._clean_trailing_empty_lines(),
                self.text_logger.scroll_to_bottom(force=True)
            )
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