# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt, QTimer, QPoint, QSize
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
from app.interfaces.exported_project_interface import ExportedProjectsPage
from app.interfaces.package_manager_interface import EnvManagerUI
# --- 核心服务 ---
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
        self.setWindowIcon(get_icon("大模型"))
        self.setWindowTitle(self.tr("LLM Chatter"))

        screen_rect = QDesktopWidget().screenGeometry()
        screen_width, screen_height = screen_rect.width(), screen_rect.height()
        self.window_width = int(0.8 * screen_width)
        self.window_height = int(0.85 * screen_height)
        desktop = QApplication.desktop().availableGeometry()
        self.desktop_w, self.desktop_h = desktop.width(), desktop.height()
        self.move(
            self.desktop_w // 2 - self.width() // 2,
            self.desktop_h // 2 - self.height() // 2,
        )
        self.navigationInterface.setExpandWidth(175)

    def _setup_splash_and_startup(self):
        self.splashScreen = SplashScreen(get_icon("大模型"), self)
        self.splashScreen.titleBar.hide()
        self.splashScreen.setIconSize(QSize(400, 400))
        self.splashScreen.setFixedSize(500, 500)
        self.show()

    # endregion

    # region [2. 核心服务初始化]
    def _init_services(self):
        self._setup_log_viewer()
        self.config = Settings.get_instance()
        setFontFamilies([self.config.canvas_font_selected.value])

    # endregion

    # region [3. 页面实例化]
    def _init_pages(self):
        self.package_manager = EnvManagerUI(self)
        self.project_manager = ExportedProjectsPage(self)

    # endregion

    # region [4. 导航栏配置]
    def _setup_navigation(self):
        project_item = self.addSubInterface(
            self.project_manager, get_icon("项目"), self.tr("项目管理")
        )
        project_item.clicked.connect(self.project_manager.load_projects)

        pkg_item = self.addSubInterface(
            self.package_manager, get_icon("工具包"), self.tr("环境管理")
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

    # region [5. 导航点击回调]
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

    # region [6. 日志系统]
    def _setup_log_viewer(self):
        self.log_popup = LogPopupWidget(self)
        self.settings_popup = SettingDialog(self)

    # endregion

    # region [7. 设置弹窗]
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
        self.move(
            self.desktop_w // 2 - self.width() // 2,
            self.desktop_h // 2 - self.height() // 2,
        )

    # endregion

    # region [9. 系统托盘]
    def _init_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_icon("大模型"))

        tray_menu = QMenu()

        show_action = QAction("显示主界面", self)
        show_action.triggered.connect(self.show_window)

        # 添加：打开 LLM Chatter 弹窗
        llm_chat_action = QAction("LLM Chatter", self)
        llm_chat_action.triggered.connect(self._open_llm_chatter_popup)
        tray_menu.addAction(llm_chat_action)

        tray_menu.addSeparator()

        quit_action = QAction("退出程序", self)
        quit_action.triggered.connect(self.quit_app)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)
        self.tray_icon.show()

    def _open_llm_chatter_popup(self):
        """打开 LLM Chatter 独立弹窗"""
        from app.widgets.side_dock_area.plugins.llm_chatter.standalone_app import (
            LLMChatterWindow,
        )
        
        if not hasattr(self, '_llm_chatter_window') or not self._llm_chatter_window:
            self._llm_chatter_window = LLMChatterWindow()
        
        self._llm_chatter_window.show()
        self._llm_chatter_window.activateWindow()

    def _on_tray_message_clicked(self):
        self.show_window()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                if self.isMinimized():
                    self.showNormal()
                self.activateWindow()
            else:
                self.show_window()

    def show_window(self):
        self.showNormal()
        self.activateWindow()

    def quit_app(self):
        self.tray_icon.setVisible(False)
        qApp.quit()

    def _hide_all_webviews(self):
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
                        if hasattr(widget, "viewer"):
                            viewer = widget.viewer
                            if hasattr(viewer, "hide"):
                                viewer.hide()
                        if hasattr(widget, "hide"):
                            widget.hide()
        except Exception:
            pass

    def _show_all_webviews(self):
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
        except Exception:
            pass

    def closeEvent(self, event):
        self.log_popup.hidePopup()
        self.settings_popup.hidePopup()
        self._hide_all_webviews()

        w = MessageBox("关闭提示", "您希望将程序最小化到系统托盘，还是彻底退出？", self)
        w.yesButton.setText("最小化")
        w.cancelButton.setText("退出程序")

        if w.exec():
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

    # endregion