# -*- coding: utf-8 -*-
import os

from PyQt5 import QtCore
from PyQt5.QtCore import QSize, Qt, QTimer, QPoint
from PyQt5.QtWidgets import (
    QApplication,
    QDesktopWidget,
    QSystemTrayIcon,
    QMenu,
    QAction,
    qApp,
)
from qfluentwidgets import (
    FluentWindow,
    Theme,
    setTheme,
    NavigationItemPosition,
    SplashScreen,
    FluentIcon,
    setFontFamilies,
    MessageBox,
)

# --- 页面模块 ---
from app.interfaces.component_developer import ComponentDeveloperPage
from app.interfaces.component_market_interface import PluginManagerCenter
from app.interfaces.exported_project_interface import ExportedProjectsPage
from app.interfaces.home_interface import HomeInterface
from app.interfaces.package_manager_interface import EnvManagerUI
from app.interfaces.update_checker import UpdateChecker
from app.interfaces.workflow_manager_interface.main_widget import (
    WorkflowCanvasGalleryPage,
)
from app.plugins.constants import PluginType
from app.plugins.plugin_manager import UnifiedPluginManager

# --- 核心服务 ---
from app.scan_components import ComponentUsageTracker, ComponentScanner
from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.dialog_widget.logger_dialog import LogPopupWidget
from app.widgets.dialog_widget.setting_popup import SettingDialog


class LowCodeWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self._init_window()
        self._setup_splash_and_startup()
        self._init_system_tray()
        self._init_services()
        self._init_pages()
        self._setup_navigation()
        QTimer.singleShot(400, self.finish_splash_screen)

    # region [1. 窗口基础设置]
    def _init_window(self):
        self.setAttribute(Qt.WA_TranslucentBackground)
        setTheme(Theme.DARK)
        self.setWindowIcon(get_icon("logoico"))

        # 使用 self.tr 进行国际化
        self.setWindowTitle(self.tr("Canvas Mind"))

        # 窗口尺寸
        screen_rect = QDesktopWidget().screenGeometry()
        screen_width, screen_height = screen_rect.width(), screen_rect.height()
        self.window_width = int(0.8 * screen_width)
        self.window_height = int(0.85 * screen_height)
        desktop = QApplication.desktop().availableGeometry()
        self.desktop_w, self.desktop_h = desktop.width(), desktop.height()
        # 初始化位置
        self.move(
            self.desktop_w // 2 - self.width() // 2,
            self.desktop_h // 2 - self.height() // 2,
        )
        self.navigationInterface.setExpandWidth(175)

    def _setup_splash_and_startup(self):
        self.splashScreen = SplashScreen(get_icon("logo"), self)
        self.splashScreen.titleBar.hide()
        self.splashScreen.setIconSize(QSize(400, 400))
        self.splashScreen.setFixedSize(500, 500)
        self.show()

    # endregion

    # region [2. 核心服务初始化]
    def _init_services(self):
        # ------------初始化日志系统
        self._setup_log_viewer()
        # ------------启动监听器
        ComponentUsageTracker()  # 日志使用情况监督
        ComponentScanner()  # 日志实时监控服务

        # ------------插件预加载
        plugin_manager = UnifiedPluginManager.get_instance()

        # ------------插件预加载（节点）
        node_plugin_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "plugins", "node_plugins")
        )
        plugin_manager.load_plugins(node_plugin_dir, plugin_type=PluginType.NODE)

        # ------------加载触发器插件
        trigger_plugin_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "plugins", "trigger_plugins")
        )
        plugin_manager.load_plugins(trigger_plugin_dir, plugin_type=PluginType.TRIGGER)
        # ------------加载配置
        self.config = Settings.get_instance()
        setFontFamilies([self.config.canvas_font_selected.value])

    # endregion

    # region [3. 页面实例化]
    def _init_pages(self):
        self.updater = UpdateChecker(self)
        # 页面按需创建
        self.workflow_manager = WorkflowCanvasGalleryPage(self)
        self.package_manager = EnvManagerUI(self)
        self.home_interface = HomeInterface(self)
        self.develop_page = ComponentDeveloperPage(self)
        self.market_page = PluginManagerCenter(self)
        self.project_manager = ExportedProjectsPage(self)

        # 信号连接
        self.workflow_manager.component_code_changed.connect(
            self.develop_page.save_component_by_full_path
        )
        self.workflow_manager.node_request_edit.connect(
            lambda uuid: (
                self.switchTo(self.develop_page),
                self.develop_page.load_component(uuid=uuid),
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
        """所有导航栏的 text 参数都使用了 self.tr()"""

        # 主功能区
        self.addSubInterface(self.home_interface, FluentIcon.HOME, self.tr("首页"))

        workflow_item = self.addSubInterface(
            self.workflow_manager, get_icon("画布管理"), self.tr("画布管理")
        )
        workflow_item.clicked.connect(self._on_workflow_clicked)

        self.addSubInterface(self.develop_page, get_icon("组件"), self.tr("组件管理"))

        self.addSubInterface(
            self.market_page, get_icon("插件市场"), self.tr("插件市场")
        )

        project_item = self.addSubInterface(
            self.project_manager, get_icon("项目"), self.tr("项目管理")
        )
        project_item.clicked.connect(self.project_manager.load_projects)

        pkg_item = self.addSubInterface(
            self.package_manager, get_icon("工具包"), self.tr("环境管理")
        )

        # 底部功能区
        self.navigationInterface.addItem(
            routeKey="update",
            icon=FluentIcon.SYNC,
            text=self.tr("检查更新"),
            onClick=self.updater.check_update,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.addItem(
            routeKey="log",
            icon=get_icon("系统运行日志"),
            text=self.tr("执行日志"),
            onClick=self._on_log_clicked,
            selectable=True,
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text=self.tr("系统设置"),
            onClick=self._on_settings_clicked,
            selectable=True,
            position=NavigationItemPosition.BOTTOM,
        )

    # endregion

    # region [6. 导航点击回调]
    def _on_workflow_clicked(self):
        self.workflow_manager._schedule_refresh()
        self.workflow_manager.build_recommendation_engine()

    def _on_log_clicked(self):
        if self.log_popup.isVisible():
            self.log_popup.hidePopup()
        else:
            log_item = self.navigationInterface.widget("log")
            if log_item:
                log_button_rect = log_item.rect()
                log_button_top_right = log_item.mapToGlobal(
                    QPoint(log_button_rect.right(), log_button_rect.top())
                )
                self.log_popup.show_at_left(self, log_button_top_right)
                self.log_popup.scroll_to_bottom()
                self.log_popup.activateWindow()
                self.log_popup._follow_window = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if (
            hasattr(self, "log_popup")
            and self.log_popup.isVisible()
            and getattr(self.log_popup, "_follow_window", False)
        ):
            self.log_popup._update_position(self)
        if (
            hasattr(self, "settings_popup")
            and self.settings_popup.isVisible()
            and getattr(self.settings_popup, "_follow_window", False)
        ):
            self.settings_popup._update_position(self)

    def moveEvent(self, event):
        super().moveEvent(event)
        if (
            hasattr(self, "log_popup")
            and self.log_popup.isVisible()
            and getattr(self.log_popup, "_follow_window", False)
        ):
            self.log_popup._update_position(self)
        if (
            hasattr(self, "settings_popup")
            and self.settings_popup.isVisible()
            and getattr(self.settings_popup, "_follow_window", False)
        ):
            self.settings_popup._update_position(self)

    # endregion

    # region [7. 日志系统]
    def _setup_log_viewer(self):
        self.log_popup = LogPopupWidget(self)
        self.settings_popup = SettingDialog(self)

    # endregion

    # region [8. 设置弹窗]
    def _on_settings_clicked(self):
        if self.settings_popup.isVisible():
            self.settings_popup.hidePopup()
        else:
            settings_item = self.navigationInterface.widget("settings")
            if settings_item:
                settings_button_rect = settings_item.rect()
                settings_button_top_right = settings_item.mapToGlobal(
                    QPoint(settings_button_rect.right(), settings_button_rect.top())
                )
                self.settings_popup.show_at_left(self, settings_button_top_right)
                self.settings_popup.activateWindow()
                self.settings_popup._follow_window = True

    # endregion

    # region [8. 闪屏结束]
    def finish_splash_screen(self):
        self.splashScreen.finish()
        self.resize(self.window_width, self.window_height)
        desktop = QApplication.desktop().availableGeometry()
        self.desktop_w, self.desktop_h = desktop.width(), desktop.height()
        # 初始化位置
        self.move(
            self.desktop_w // 2 - self.width() // 2,
            self.desktop_h // 2 - self.height() // 2,
        )
        if self.config.auto_check_update.value:
            QtCore.QTimer.singleShot(500, self.updater.check_update)

    # endregion
    # --- 新增区域：系统托盘与关闭逻辑 ---

    def _init_system_tray(self):
        """初始化系统托盘图标"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_icon("logoico"))  # 使用您现有的图标获取方法

        # 创建托盘菜单
        tray_menu = QMenu()

        # 动作：显示主界面
        show_action = QAction("显示主界面", self)
        show_action.triggered.connect(self.show_window)

        # 动作：退出程序
        quit_action = QAction("退出程序", self)
        quit_action.triggered.connect(self.quit_app)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)

        # 点击托盘图标的事件（左键点击恢复窗口）
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)

        self.tray_icon.show()

    def _on_tray_message_clicked(self):
        """点击托盘消息时触发"""
        self.show_window()

    def on_tray_icon_activated(self, reason):
        """点击托盘图标时的响应"""
        if reason == QSystemTrayIcon.Trigger:  # 单击
            if self.isVisible():
                if self.isMinimized():
                    self.showNormal()
                self.activateWindow()
            else:
                self.show_window()

    def show_window(self):
        """恢复并显示窗口"""
        self.showNormal()
        self.activateWindow()

    def quit_app(self):
        """彻底退出程序"""
        self.tray_icon.setVisible(False)  # 隐藏图标，防止残留
        qApp.quit()

    def _hide_all_webviews(self):
        """隐藏所有聊天卡片的WebView，防止遮挡弹窗"""
        try:
            from app.widgets.side_dock_area.plugins.llm_chatter.main_widget import (
                OpenAIChatToolWindow,
            )

            chat_window = self.findChild(OpenAIChatToolWindow)
            if chat_window and hasattr(chat_window, "chat_layout"):
                for i in range(chat_window.chat_layout.count()):
                    item = chat_window.chat_layout.itemAt(i)
                    if item and item.widget():
                        widget = item.widget()
                        # 找到 MessageCard 中的 viewer
                        if hasattr(widget, "viewer"):
                            viewer = widget.viewer
                            if hasattr(viewer, "hide"):
                                viewer.hide()
                        # 也隐藏 MessageCard 本身
                        if hasattr(widget, "hide"):
                            widget.hide()
        except Exception as e:
            pass

    def _show_all_webviews(self):
        """显示所有聊天卡片的WebView"""
        try:
            from app.widgets.side_dock_area.plugins.llm_chatter.main_widget import (
                OpenAIChatToolWindow,
            )

            chat_window = self.findChild(OpenAIChatToolWindow)
            if chat_window and hasattr(chat_window, "chat_layout"):
                for i in range(chat_window.chat_layout.count()):
                    item = chat_window.chat_layout.itemAt(i)
                    if item and item.widget():
                        widget = item.widget()
                        if hasattr(widget, "show"):
                            widget.show()
        except Exception as e:
            pass

    def closeEvent(self, event):
        """
        重写关闭事件：弹出对话框询问用户
        """
        self.log_popup.hidePopup()
        self.settings_popup.hidePopup()

        # 隐藏WebView防止遮挡弹窗
        self._hide_all_webviews()

        w = MessageBox("关闭提示", "您希望将程序最小化到系统托盘，还是彻底退出？", self)
        w.yesButton.setText("最小化")
        w.cancelButton.setText("退出程序")

        if w.exec():
            # 恢复WebView显示
            self._show_all_webviews()
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Canvas Mind",
                "程序已在后台运行，点击托盘图标可恢复。",
                QSystemTrayIcon.Information,
                2000,
            )
        else:
            event.accept()
            self.tray_icon.setVisible(False)
            self.config.save()
            qApp.quit()
