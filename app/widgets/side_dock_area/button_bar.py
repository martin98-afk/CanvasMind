# -*- coding: utf-8 -*-
from PyQt5.QtCore import (Qt, pyqtSignal, QRect, QRectF, QPoint)
from PyQt5.QtWidgets import (
    QFrame
)
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import NavigationToolButton, FluentIcon as FIF, isDarkTheme, drawIcon
from qfluentwidgets.common.color import autoFallbackThemeColor

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
        from PyQt5.QtGui import QColor, QPainter, QCursor
        from PyQt5.QtCore import Qt, QRectF
        from qfluentwidgets.common.icon import drawIcon
        from qfluentwidgets import isDarkTheme

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing |
                               QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        painter.setPen(Qt.NoPen)

        # --- 1. 设置基础透明度（仅用于背景/图标/文本）---
        base_opacity = 1.0
        if self.isPressed:
            base_opacity = 0.7
        elif not self.isEnabled():
            base_opacity = 0.4
        painter.setOpacity(base_opacity)

        # --- 2. 绘制背景和指示器 ---
        c = 255 if isDarkTheme() else 0
        m = self._margins()
        pl, pr = m.left(), m.right()
        globalRect = QRect(self.mapToGlobal(QPoint()), self.size())

        if self._canDrawIndicator():
            painter.setBrush(QColor(c, c, c, 6 if self.isEnter else 10))
            painter.drawRoundedRect(self.rect(), 5, 5)

            # 指示器
            painter.setBrush(autoFallbackThemeColor(self.lightIndicatorColor, self.darkIndicatorColor))
            painter.drawRoundedRect(pl, 10, 3, 16, 1.5, 1.5)
        elif self.isEnter and self.isEnabled() and globalRect.contains(QCursor.pos()):
            painter.setBrush(QColor(c, c, c, 10))
            painter.drawRoundedRect(self.rect(), 5, 5)

        # --- 3. 绘制图标（增大尺寸）---
        icon_size = 20
        icon_y = (self.height() - icon_size) / 2
        icon_x = 10 + pl
        drawIcon(self._icon, painter, QRectF(icon_x, icon_y, icon_size, icon_size))

        # --- 4. 绘制文本 ---
        if not self.isCompacted:
            painter.setFont(self.font())
            painter.setPen(self.textColor())
            left = 44 + pl if not self.icon().isNull() else pl + 16
            painter.drawText(
                QRectF(left, 0, self.width() - 13 - left - pr, self.height()),
                Qt.AlignVCenter,
                self.text()
            )

        # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
        # --- 5. 【关键】绘制选中状态（必须最后，且重置透明度）---
        # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
        if self._checked:
            # 重置透明度为 1.0，确保选中效果不被削弱
            painter.setOpacity(1.0)

            # 蓝色竖线（左侧）
            line_width = 3
            blue_color = QColor("#0078d4")
            painter.setBrush(blue_color)
            painter.drawRect(0, 0, line_width, self.height())

            # 半透明覆盖层
            overlay_alpha = 20 if not isDarkTheme() else 30
            overlay_color = QColor(0, 120, 212, overlay_alpha)
            painter.setBrush(overlay_color)
            painter.drawRect(0, 0, self.width(), self.height())


class RightToolPanel(QFrame):
    """
    PyCharm 风格右侧工具面板，支持插件式 ToolWindow
    """
    # 信号：传出的是 ToolWindow 名
    topToolChecked = pyqtSignal(str)      # Type
    topToolUnchecked = pyqtSignal(str)
    bottomToolChecked = pyqtSignal(str)
    bottomToolUnchecked = pyqtSignal(str)

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

    def set_checked(self, tool_name: str):
        if tool_name in self._bottom_buttons:
            btn = self._bottom_buttons[tool_name]
            if not btn.isChecked():
                btn.setChecked(True)  # 先设为 True
                # 手动触发点击逻辑（避免重复 emit）
                tool = self._tool_by_button[btn]
                self._on_bottom_clicked(btn, tool)
        else:
            for btn, tool in self._tool_by_button.items():
                if btn in self._top_buttons and tool.name == tool_name:
                    if not btn.isChecked():
                        btn.setChecked(True)
                        self._on_top_clicked(btn, tool)
                    break

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