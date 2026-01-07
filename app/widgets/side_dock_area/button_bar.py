# -*- coding: utf-8 -*-
from PyQt5.QtCore import (Qt, pyqtSignal, QRect, QRectF, QPoint, QTimer, QMimeData)
from PyQt5.QtGui import (QColor, QPainter, QCursor, QDrag, QPixmap)
from PyQt5.QtWidgets import QFrame, QVBoxLayout
from qfluentwidgets import NavigationToolButton, FluentIcon as FIF, isDarkTheme, drawIcon, InfoBadge, InfoBadgePosition
from qfluentwidgets.common.color import autoFallbackThemeColor


class ToggleNavigationButton(NavigationToolButton):
    def __init__(self, icon, tool_name, parent=None):
        super().__init__(icon, parent)
        self._checked = False
        self.tool_name = tool_name

        # 长按逻辑计时器
        self.long_press_timer = QTimer(self)
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._start_drag)
        self.press_pos = QPoint()

    def setChecked(self, checked: bool):
        if self._checked == checked:
            return
        self._checked = checked
        self.update()

    def set_badge(self, badge_text, badge_position=InfoBadgePosition.TOP_RIGHT):
        if badge_text:
            self.info_badge = InfoBadge(badge_text, badge_position)
            self.info_badge.setParent(self)
            self.info_badge.move(self.width() - 20, 5)
        else:
            if self.info_badge:
                self.info_badge.deleteLater()
                self.info_badge = None

    def isChecked(self):
        return self._checked

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press_pos = e.pos()
            self.long_press_timer.start(500)  # 600ms 判定为长按拖拽
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        # 如果按下后移动距离过大，则取消长按计时（防止误触发）
        if (e.pos() - self.press_pos).manhattanLength() > 10:
            self.long_press_timer.stop()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self.long_press_timer.stop()
        if e.button() == Qt.LeftButton:
            # 只有在没有进行拖拽的情况下才触发切换逻辑
            if (e.pos() - self.press_pos).manhattanLength() < 10:
                self.setChecked(not self._checked)
        super().mouseReleaseEvent(e)

    def _start_drag(self):
        """执行拖拽启动逻辑"""
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.tool_name)  # 传递工具名称用于识别
        drag.setMimeData(mime)

        # 设置拖拽时的图标预览
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        drag.exec_(Qt.MoveAction)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing |
                               QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        painter.setPen(Qt.NoPen)

        base_opacity = 1.0
        if self.isPressed:
            base_opacity = 0.7
        elif not self.isEnabled():
            base_opacity = 0.4
        painter.setOpacity(base_opacity)

        c = 255 if isDarkTheme() else 0
        m = self._margins()
        pl, pr = m.left(), m.right()
        globalRect = QRect(self.mapToGlobal(QPoint()), self.size())

        if self._canDrawIndicator():
            painter.setBrush(QColor(c, c, c, 6 if self.isEnter else 10))
            painter.drawRoundedRect(self.rect(), 5, 5)
            painter.setBrush(autoFallbackThemeColor(self.lightIndicatorColor, self.darkIndicatorColor))
            painter.drawRoundedRect(pl, 10, 3, 16, 1.5, 1.5)
        elif self.isEnter and self.isEnabled() and globalRect.contains(QCursor.pos()):
            painter.setBrush(QColor(c, c, c, 10))
            painter.drawRoundedRect(self.rect(), 5, 5)

        icon_size = 20
        icon_y = (self.height() - icon_size) / 2
        icon_x = 10 + pl
        drawIcon(self._icon, painter, QRectF(icon_x, icon_y, icon_size, icon_size))

        if not self.isCompacted:
            painter.setFont(self.font())
            painter.setPen(self.textColor())
            left = 44 + pl if not self.icon().isNull() else pl + 16
            painter.drawText(
                QRectF(left, 0, self.width() - 13 - left - pr, self.height()),
                Qt.AlignVCenter, self.text()
            )

        if self._checked:
            painter.setOpacity(1.0)
            line_width = 3
            blue_color = QColor("#0078d4")
            painter.setBrush(blue_color)
            painter.drawRect(0, 0, line_width, self.height())
            overlay_alpha = 20 if not isDarkTheme() else 30
            overlay_color = QColor(0, 120, 212, overlay_alpha)
            painter.setBrush(overlay_color)
            painter.drawRect(0, 0, self.width(), self.height())


class RightToolPanel(QFrame):
    """PyCharm 风格侧边栏，支持拖拽排序和分栏切换"""
    topToolChecked = pyqtSignal(str)
    topToolUnchecked = pyqtSignal(str)
    bottomToolChecked = pyqtSignal(str)
    bottomToolUnchecked = pyqtSignal(str)

    # 拖拽移动信号：(插件名, 目标位置字符串'top'/'bottom')
    toolMoveRequested = pyqtSignal(str, str)

    def __init__(self, canvas_page, parent=None):
        super().__init__(parent)
        self.canvas_page = canvas_page
        self.setFixedWidth(42)
        self.setAcceptDrops(True)  # 开启接收拖拽

        self._top_buttons = []
        self._bottom_buttons = {}  # name -> button
        self._tool_by_button = {}  # button -> tool_cls
        self._button_by_name = {}  # name -> button

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
        self.setStyleSheet(f"#RightToolPanel {{ background: {bg}; border-left: 1px solid {border}; }}")

    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        tool_name = e.mimeData().text()
        # 判定落在上半部分还是下半部分
        is_bottom = e.pos().y() > self.height() / 2
        new_pos = "bottom" if is_bottom else "top"
        self.toolMoveRequested.emit(tool_name, new_pos)
        e.acceptProposedAction()

    def create_button(self, tool_cls):
        """创建并记录按钮实例"""
        btn = ToggleNavigationButton(tool_cls.icon or FIF.BRUSH, tool_cls.name, self)
        btn.setToolTip(tool_cls.name)
        self._button_by_name[tool_cls.name] = btn
        self._tool_by_button[btn] = tool_cls
        return btn

    def add_button_to_layout(self, tool_name, position_str):
        """将已有按钮放入指定布局逻辑"""
        btn = self._button_by_name.get(tool_name)
        tool_cls = self._tool_by_button.get(btn)
        if not btn: return

        # 断开旧连接，防止信号重复触发
        try:
            btn.clicked.disconnect()
        except:
            pass

        # 从旧布局移除
        self._top_layout.removeWidget(btn)
        if btn in self._top_buttons: self._top_buttons.remove(btn)
        self._bottom_layout.removeWidget(btn)
        if tool_name in self._bottom_buttons: self._bottom_buttons.pop(tool_name)

        if position_str == "top":
            btn.clicked.connect(lambda: self._on_top_clicked(btn, tool_cls))
            self._top_layout.addWidget(btn)
            self._top_buttons.append(btn)
        else:
            btn.clicked.connect(lambda: self._on_bottom_clicked(btn, tool_cls))
            self._bottom_layout.addWidget(btn)
            self._bottom_buttons[tool_name] = btn
        btn.show()

    def _on_top_clicked(self, btn, tool_cls):
        if btn.isChecked():
            for b in self._top_buttons:
                if b is not btn: b.setChecked(False)
            self.topToolChecked.emit(tool_cls.name)
        else:
            self.topToolUnchecked.emit(tool_cls.name)

    def _on_bottom_clicked(self, btn, tool_cls):
        if btn.isChecked():
            for k, b in self._bottom_buttons.items():
                if b is not btn: b.setChecked(False)
            self.bottomToolChecked.emit(tool_cls.name)
        else:
            self.bottomToolUnchecked.emit(tool_cls.name)

    def set_checked(self, tool_name: str):
        btn = self._button_by_name.get(tool_name)
        if not btn: return
        if not btn.isChecked():
            btn.setChecked(True)
            tool_cls = self._tool_by_button[btn]
            if btn in self._top_buttons:
                self._on_top_clicked(btn, tool_cls)
            else:
                self._on_bottom_clicked(btn, tool_cls)

    def _set_top_button_checked(self, target_cls):
        btn = self._button_by_name.get(target_cls.name)
        if btn and btn in self._top_buttons:
            btn.setChecked(True)
            for other_btn in self._top_buttons:
                if other_btn is not btn: other_btn.setChecked(False)