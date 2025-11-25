# -*- coding: utf-8 -*-
from typing import Dict, Type
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QStackedWidget, QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal
from qfluentwidgets import NavigationToolButton, FluentIcon as FIF, isDarkTheme

from app.widgets.side_dock_area.tool_window import ToolWindow


class ToggleNavigationButton(NavigationToolButton):
    def __init__(self, icon, parent=None):
        super().__init__(icon, parent)
        self._checked = False

    def setChecked(self, checked: bool):
        if self._checked == checked:
            return
        self._checked = checked
        self.update()

    def isChecked(self):
        return self._checked

    def mouseReleaseEvent(self, e):
        self.setChecked(not self._checked)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._checked:
            from PyQt5.QtGui import QPainter, QColor
            painter = QPainter(self)
            painter.setRenderHints(painter.Antialiasing)
            painter.setPen(Qt.NoPen)
            color = QColor(255, 255, 255, 80) if isDarkTheme() else QColor(0, 0, 0, 80)
            painter.setBrush(color)
            painter.drawRect(0, self.height() - 2, self.width(), 2)


class RightToolPanel(QFrame):
    """
    PyCharm 风格右侧工具面板，支持插件式 ToolWindow
    """

    def __init__(self, canvas_page, parent=None):
        super().__init__(parent)
        self.canvas_page = canvas_page
        self.setFixedWidth(42)

        # 按钮与视图映射
        self._top_buttons = []
        self._bottom_buttons = {}
        self._tool_by_button = {}  # button -> tool_window

        # 布局
        self._top_layout = QVBoxLayout()
        self._bottom_layout = QVBoxLayout()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._top_layout.setSpacing(0)
        self._bottom_layout.setSpacing(0)
        self._top_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self._bottom_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

        main_layout.addLayout(self._top_layout)
        main_layout.addStretch(1)
        main_layout.addLayout(self._bottom_layout)

        self.setObjectName("RightToolPanel")
        bg = "#202020" if isDarkTheme() else "#ffffff"
        border = "#3a3a3a" if isDarkTheme() else "#e0e0e0"
        self.setStyleSheet(f"""
            #RightToolPanel {{
                background: {bg};
                border-left: 1px solid {border};
            }}
        """)

    def _set_top_button_checked(self, target_cls):
        """手动将某个 top 按钮设为 checked（用于默认选中）"""
        for btn, cls in self._tool_by_button.items():
            if cls == target_cls and btn in self._top_buttons:
                btn.setChecked(True)
                # 取消其他 top 按钮
                for other_btn in self._top_buttons:
                    if other_btn is not btn:
                        other_btn.setChecked(False)
                break

    def add_to_top(self, tool: ToolWindow):
        """注册工具到上组"""
        btn = ToggleNavigationButton(tool.icon or FIF.BRUSH, self)
        btn.setToolTip(tool.name)
        btn.clicked.connect(lambda: self._on_top_clicked(btn, tool))
        self._top_layout.addWidget(btn)
        self._top_buttons.append(btn)
        self._tool_by_button[btn] = tool

    def add_to_bottom(self, tool: ToolWindow):
        """注册工具到下组"""
        btn = ToggleNavigationButton(tool.icon or FIF.BRUSH, self)
        btn.setToolTip(tool.name)
        btn.clicked.connect(lambda: self._on_bottom_clicked(btn, tool))
        self._bottom_layout.addWidget(btn)
        self._bottom_buttons[tool.name] = btn
        self._tool_by_button[btn] = tool

    def _on_top_clicked(self, btn, tool_cls):
        if btn.isChecked():
            for b in self._top_buttons:
                if b is not btn:
                    b.setChecked(False)
            self.topToolChecked.emit(tool_cls.name)
        else:
            self.topToolUnchecked.emit(tool_cls.name)

    def _on_bottom_clicked(self, btn, tool_cls):
        if btn.isChecked():
            for k, b in self._bottom_buttons.items():
                if b is not btn:
                    b.setChecked(False)
            self.bottomToolChecked.emit(tool_cls.name)
        else:
            self.bottomToolUnchecked.emit(tool_cls.name)

    # 信号：传出的是 ToolWindow 类（或你可在内部实例化后传实例）
    topToolChecked = pyqtSignal(str)      # Type[ToolWindow]
    topToolUnchecked = pyqtSignal(str)
    bottomToolChecked = pyqtSignal(str)
    bottomToolUnchecked = pyqtSignal(str)