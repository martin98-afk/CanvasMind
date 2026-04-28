# -*- coding: utf-8 -*-
"""
LLM Chatter 独立应用入口
支持以弹窗模式直接启动，复用 ToolPopupDialog 的核心功能
"""
import sys
import os
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSystemTrayIcon, QMenu, QAction, QDesktopWidget
from PyQt5.QtGui import QPainter, QColor
from qfluentwidgets import TransparentToolButton

from app.utils.config import Settings

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def setup_logging():
    """设置日志"""
    from loguru import logger
    import os as _os
    
    log_dir = os.path.join(project_root, "logs")
    _os.makedirs(log_dir, exist_ok=True)
    logger.add(
        os.path.join(log_dir, "llm_chatter_app.log"),
        rotation="10 MB",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )


class OpacitySlider(QWidget):
    """透明度滑块控件"""
    opacityChanged = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._opacity = 100
        self.setFixedWidth(36)
        self.setFixedHeight(200)
        self._is_dragging = False
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._knob_height = 12
        self._track_padding = 10
        from qfluentwidgets import isDarkTheme
        self._is_dark = isDarkTheme()
    
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        
        bg_color = QColor(38, 38, 38, 230) if self._is_dark else QColor(245, 245, 245, 230)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(self.rect(), 8, 8)
        
        track_height = self.height() - 2 * self._track_padding
        track_width = 4
        track_x = (self.width() - track_width) // 2
        track_y = self._track_padding
        
        track_bg = QColor(100, 100, 100, 150) if self._is_dark else QColor(180, 180, 180, 150)
        painter.setBrush(track_bg)
        painter.drawRoundedRect(track_x, track_y, track_width, track_height, 2, 2)
        
        fill_height = int(track_height * self._opacity / 100)
        fill_color = QColor("#0078d4")
        painter.setBrush(fill_color)
        painter.drawRoundedRect(track_x, track_y + track_height - fill_height, track_width, fill_height, 2, 2)
        
        knob_y = track_y + track_height - fill_height - self._knob_height // 2
        knob_color = QColor(255, 255, 255) if self._is_dark else QColor(80, 80, 80)
        painter.setBrush(knob_color)
        painter.drawEllipse(QPoint(self.width() // 2, knob_y + self._knob_height // 2), 7, 7)
        
        painter.setPen(QColor(200, 200, 200) if self._is_dark else QColor(80, 80, 80))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignBottom | Qt.AlignHCenter, f"{self._opacity}%")
    
    def setOpacity(self, value: int):
        self._opacity = max(0, min(100, value))
        self.update()
        self.opacityChanged.emit(self._opacity)
    
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._is_dragging = True
            self._update_from_mouse(e.pos())
            self.update()
    
    def mouseMoveEvent(self, e):
        if self._is_dragging:
            self._update_from_mouse(e.pos())
            self.update()
    
    def mouseReleaseEvent(self, e):
        self._is_dragging = False
    
    def _update_from_mouse(self, pos: QPoint):
        track_height = self.height() - 2 * self._track_padding
        rel_y = pos.y() - self._track_padding
        value = int((1 - rel_y / track_height) * 100)
        self.setOpacity(value)


def create_window():
    """创建 LLM Chatter 窗口类"""
    from PyQt5.QtCore import Qt, QSize, QPoint, pyqtSignal
    from PyQt5.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QSizeGrip,
    )
    from PyQt5.QtGui import QPainter, QColor
    from qfluentwidgets import (
        Theme,
        setTheme,
        TransparentPushButton,
        StrongBodyLabel,
        FluentIcon,
        isDarkTheme,
    )
    from app.utils.config import Settings
    from app.utils.utils import get_icon, get_unified_font
    from loguru import logger
    
    class LLMChatterWindow(QDialog):
        """LLM Chatter 独立窗口 - 轻量化弹窗模式"""
        
        def __init__(self):
            super().__init__(None)
            
            self.cfg = Settings.get_instance()
            self._drag_pos = None
            self._is_maximized = False
            self._normal_geometry = None
            self._opacity_slider = None
            self._hide_timer = QTimer(self)
            self._hide_timer.setSingleShot(True)
            self._hide_timer.setInterval(200)
            self._hide_timer.timeout.connect(self._check_hide_slider)
            self._geometry_save_timer = QTimer(self)
            self._geometry_save_timer.setSingleShot(True)
            self._geometry_save_timer.setInterval(160)
            self._geometry_save_timer.timeout.connect(self._save_geometry)
            
            self._init_window()
            self._create_ui()
            self._init_chat_component()
            self._setup_tray()
            
            logger.info("LLM Chatter 独立模式启动成功")
        
        def _init_window(self):
            # 使用 FramelessWindowHint 但保留大小调整能力
            self.setWindowFlags(
                Qt.Dialog 
                | Qt.FramelessWindowHint 
                | Qt.WindowStaysOnTopHint
                | Qt.WindowMinimizeButtonHint
                | Qt.WindowMaximizeButtonHint
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setMinimumSize(400, 300)
            self.setSizeGripEnabled(True)
            self.setWindowTitle("LLM Chatter")
            self.setWindowIcon(get_icon("大模型"))
            
            setTheme(Theme.DARK)
            
            screen = QDesktopWidget().screenGeometry()
            self.resize(int(screen.width() * 0.45), int(screen.height() * 0.75))
            self._center_on_screen()
        
        def _center_on_screen(self):
            screen = QDesktopWidget().screenGeometry()
            self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        
        def _create_ui(self):
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)
            
            # 标题栏
            title_bar = self._create_title_bar()
            main_layout.addWidget(title_bar)
            
            # 聊天区域
            self.chat_container = QWidget()
            self.chat_container.setObjectName("chatContainer")
            self.chat_container.setStyleSheet("#chatContainer { background-color: #2b2b2b; }")
            main_layout.addWidget(self.chat_container, 1)
            
            # 大小调整区域
            size_grip = QSizeGrip(self)
            size_grip.setStyleSheet("QSizeGrip { background-color: transparent; width: 16px; height: 16px; }")
        
        def _create_title_bar(self):
            title_bar = QWidget()
            title_bar.setFixedHeight(32)
            title_bar.setObjectName("titleBar")
            title_bar.setStyleSheet("""
                #titleBar {
                    background-color: #1e1e1e;
                    border-bottom: 1px solid #3d3d3d;
                }
            """)
            
            layout = QHBoxLayout(title_bar)
            layout.setContentsMargins(12, 0, 8, 0)
            layout.setSpacing(8)
            
            # 拖动区域标签
            drag_label = QLabel()
            drag_label.setPixmap(get_icon("大模型").pixmap(16, 16))
            drag_label.setStyleSheet("background: transparent;")
            layout.addWidget(drag_label)
            
            title_label = StrongBodyLabel("LLM Chatter")
            title_label.setFont(get_unified_font(13, True))
            title_label.setStyleSheet("color: #ffffff; background: transparent;")
            layout.addWidget(title_label)
            layout.addStretch()
            
            # 最小化
            min_btn = TransparentToolButton(get_icon("最小化"), self)
            min_btn.setFixedSize(28, 28)
            min_btn.setToolTip("最小化")
            min_btn.clicked.connect(self.showMinimized)
            layout.addWidget(min_btn)
            
            # 最大化/还原
            self._max_btn = TransparentToolButton(get_icon("最大化"), self)
            self._max_btn.setFixedSize(28, 28)
            self._max_btn.setToolTip("最大化")
            self._max_btn.clicked.connect(self._toggle_maximize)
            layout.addWidget(self._max_btn)
            
            # 关闭
            close_btn = TransparentToolButton(FluentIcon.CLOSE, self)
            close_btn.setFixedSize(28, 28)
            close_btn.clicked.connect(self._on_close)
            close_btn.setToolTip("最大化")
            close_btn.installEventFilter(self)
            layout.addWidget(close_btn)
            
            return title_bar
        
        def _init_chat_component(self):
            from app.widgets.side_dock_area.plugins.llm_chatter.main_widget import OpenAIChatToolWindow
            
            fake_page = FakePage()
            self.chat_window = OpenAIChatToolWindow(fake_page, None)
            
            # 确保标题栏按钮被初始化（复制窗口、API文档等）
            if hasattr(self.chat_window, '_setup_title_bar'):
                self.chat_window._setup_title_bar()
            
            # 隐藏内置标题栏，因为我们有自己的标题栏
            title_bar = self.chat_window.get_title_bar()
            if title_bar:
                title_bar.hide()
            
            layout = QVBoxLayout(self.chat_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.chat_window)
        
        def _toggle_maximize(self):
            if self._is_maximized:
                self.showNormal()
                self._is_maximized = False
                if self._normal_geometry:
                    self.restoreGeometry(self._normal_geometry)
            else:
                self._normal_geometry = self.saveGeometry()
                self.showMaximized()
                self._is_maximized = True
        
        def _on_close(self):
            self.hide()
            if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    "LLM Chatter",
                    "程序已在后台运行，点击托盘图标可恢复",
                    QSystemTrayIcon.Information,
                    2000
                )
        
        def _setup_tray(self):
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(get_icon("大模型"))
            
            menu = QMenu()
            
            show_action = QAction("显示窗口", self)
            show_action.triggered.connect(self._toggle_visibility)
            menu.addAction(show_action)
            
            menu.addSeparator()
            
            quit_action = QAction("退出", self)
            quit_action.triggered.connect(lambda: sys.exit(0))
            menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()
        
        def _toggle_visibility(self):
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()
        
        def _on_tray_activated(self, reason):
            if reason == QSystemTrayIcon.Trigger:
                self._toggle_visibility()
        
        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                title_bar = self.findChild(QWidget, "titleBar")
                if title_bar and event.y() <= title_bar.height():
                    self._hide_opacity_slider()
                    self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                    event.accept()
        
        def mouseMoveEvent(self, event):
            if event.buttons() == Qt.LeftButton and self._drag_pos:
                self.move(event.globalPos() - self._drag_pos)
                event.accept()
            else:
                self._show_opacity_slider()
                self._hide_timer_start()
        
        def mouseReleaseEvent(self, event):
            self._drag_pos = None
            if event.button() == Qt.LeftButton:
                self._save_geometry()
        
        def mouseDoubleClickEvent(self, event):
            if event.button() == Qt.LeftButton:
                title_bar = self.findChild(QWidget, "titleBar")
                if title_bar and event.y() < title_bar.height():
                    self._toggle_maximize()
                    event.accept()
        
        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._geometry_save_timer.start()
        
        def moveEvent(self, event):
            super().moveEvent(event)
            if self._is_maximized:
                return
            self._geometry_save_timer.start()
        
        def _show_opacity_slider(self):
            if self._opacity_slider is None:
                self._opacity_slider = OpacitySlider(self)
                self._opacity_slider.opacityChanged.connect(self._on_opacity_changed)
            self._opacity_slider.setOpacity(int(self.windowOpacity() * 100))
            pos = self.mapToGlobal(QPoint(self.width() + 5, 10))
            self._opacity_slider.move(pos)
            self._opacity_slider.show()
            self._opacity_slider.raise_()
        
        def _hide_opacity_slider(self):
            if self._opacity_slider:
                self._opacity_slider.hide()
        
        def _hide_timer_start(self):
            self._hide_timer.start()
        
        def _on_opacity_changed(self, value: int):
            self.setWindowOpacity(value / 100)
        
        def _check_hide_slider(self):
            if not self._opacity_slider or self._opacity_slider._is_dragging:
                return
            slider_pos = self._opacity_slider.mapFromGlobal(self.cursor().pos())
            if self._opacity_slider.rect().contains(slider_pos):
                return
            dialog_pos = self.mapFromGlobal(self.cursor().pos())
            if not self.rect().contains(dialog_pos):
                self._hide_opacity_slider()
        
        def _save_geometry(self):
            from PyQt5.QtCore import QSettings
            settings = QSettings("WorkFlowGUI", "LLMChatterWindow")
            settings.setValue("geometry", self.saveGeometry())
        
        def _restore_geometry(self):
            from PyQt5.QtCore import QSettings
            settings = QSettings("WorkFlowGUI", "LLMChatterWindow")
            geometry = settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        
        def showEvent(self, event):
            super().showEvent(event)
            self._restore_geometry()
        
        def enterEvent(self, e):
            super().enterEvent(e)
            self._show_opacity_slider()
            self._hide_timer.stop()
        
        def leaveEvent(self, e):
            super().leaveEvent(e)
            self._hide_timer_start()
        
        def eventFilter(self, obj, event):
            # 简化 eventFilter
            return super().eventFilter(obj, event)
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            is_dark = isDarkTheme()
            bg_color = QColor(45, 45, 45) if is_dark else QColor(245, 245, 245)
            border_color = QColor(55, 55, 55) if is_dark else QColor(200, 200, 200)
            
            painter.setBrush(bg_color)
            painter.setPen(border_color)
            painter.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)
    
    return LLMChatterWindow


class FakePage(QWidget):
    """模拟的 Page 对象，提供 ToolWindow 所需的接口"""
    
    def __init__(self, parent_window=None):
        super().__init__(parent_window)
        self._parent_window = parent_window
        self.cfg = Settings.get_instance()
        self._event_filters = []
    
    def installEventFilter(self, obj):
        self._event_filters.append(obj)
    
    def removeEventFilter(self, obj):
        if obj in self._event_filters:
            self._event_filters.remove(obj)
    
    def isActiveWindow(self):
        if self._parent_window:
            return self._parent_window.isActiveWindow()
        return True
    
    @property
    def workflow_name(self):
        return "standalone_llm_chatter"
    
    @property
    def global_variables_changed(self):
        class FakeSignal:
            def connect(self, *args, **kwargs):
                pass
        return FakeSignal()
    
    def setUpdatesEnabled(self, enabled):
        pass
    
    def update(self):
        pass
    
    def show_splitter(self):
        pass
    
    def hide_splitter(self):
        pass


def main():
    """独立应用主入口"""
    setup_logging()
    
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    app = QApplication(sys.argv)
    app.setApplicationName("LLM Chatter")
    app.setApplicationDisplayName("LLM Chatter")
    
    window = create_window()()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()