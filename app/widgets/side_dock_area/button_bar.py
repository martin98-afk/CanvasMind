# -*- coding: utf-8 -*-
from PyQt5.QtCore import (Qt, pyqtSignal, QRectF, QPoint, QTimer, QMimeData)
from PyQt5.QtGui import (QColor, QPainter, QDrag, QPen)
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import NavigationToolButton, FluentIcon as FIF, isDarkTheme, drawIcon, InfoBadge, InfoBadgePosition


class ToggleNavigationButton(NavigationToolButton):
    def __init__(self, icon, tool_name, parent=None):
        super().__init__(icon, parent)
        self._checked = False
        self.tool_name = tool_name
        self.setFixedSize(40, 40)  # 建议固定一下大小确保对齐

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
            if hasattr(self, 'info_badge') and self.info_badge:
                self.info_badge.deleteLater()
                self.info_badge = None

    def isChecked(self):
        return self._checked

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press_pos = e.pos()
            self.long_press_timer.start(500)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if (e.pos() - self.press_pos).manhattanLength() > 10:
            self.long_press_timer.stop()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self.long_press_timer.stop()
        if e.button() == Qt.LeftButton:
            if (e.pos() - self.press_pos).manhattanLength() < 10:
                self.setChecked(not self._checked)
        super().mouseReleaseEvent(e)

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.tool_name)
        drag.setMimeData(mime)
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

        # 简化绘制逻辑，确保图标居中
        if self._checked:
            # 选中状态背景
            painter.setBrush(QColor(c, c, c, 15))
            painter.drawRoundedRect(self.rect(), 5, 5)

            # 选中状态左侧指示条
            line_width = 3
            blue_color = QColor("#0078d4")
            painter.setBrush(blue_color)
            painter.drawRoundedRect(0, 8, line_width, self.height() - 16, 1.5, 1.5)
        elif self.isEnter:
            painter.setBrush(QColor(c, c, c, 10))
            painter.drawRoundedRect(self.rect(), 5, 5)

        icon_size = 18
        icon_y = (self.height() - icon_size) / 2
        # 简单的居中计算
        icon_x = (self.width() - icon_size) / 2
        drawIcon(self._icon, painter, QRectF(icon_x, icon_y, icon_size, icon_size))


class ToolSeparator(QWidget):
    """自定义分割线，类似 CardSeparator，但在侧边栏更紧凑"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)  # 占用高度，方便留白

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 根据主题设置线条颜色
        color = QColor(255, 255, 255, 40) if isDarkTheme() else QColor(0, 0, 0, 20)
        painter.setPen(QPen(color, 3))

        # 绘制中间的横线，左右留边距
        margin = 3
        y = self.height() // 2
        painter.drawLine(margin, y, self.width() - margin, y)


class RightToolPanel(QFrame):
    """PyCharm 风格侧边栏：按钮全部靠上，中间用分割线隔开"""
    topToolChecked = pyqtSignal(str)
    topToolUnchecked = pyqtSignal(str)
    bottomToolChecked = pyqtSignal(str)
    bottomToolUnchecked = pyqtSignal(str)
    toolMoveRequested = pyqtSignal(str, str)

    def __init__(self, canvas_page, parent=None):
        super().__init__(parent)
        self.canvas_page = canvas_page
        self.setFixedWidth(42)
        self.setAcceptDrops(True)

        self._top_buttons = []
        self._bottom_buttons = {}
        self._tool_by_button = {}
        self._button_by_name = {}

        # 布局初始化
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 6, 1, 6)  # 稍微调整边距
        main_layout.setSpacing(2)

        # 1. 顶部工具组布局
        self._top_layout = QVBoxLayout()
        self._top_layout.setSpacing(4)
        self._top_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        main_layout.addLayout(self._top_layout)

        # 2. 分割线 (核心变化)
        self.separator = ToolSeparator(self)
        self.separator.hide()  # 初始没有按钮时隐藏
        main_layout.addWidget(self.separator)

        # 3. 底部工具组布局 (物理位置现在在上方，逻辑上是第二组)
        self._bottom_layout = QVBoxLayout()
        self._bottom_layout.setSpacing(4)
        self._bottom_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)  # 也是靠上对齐
        main_layout.addLayout(self._bottom_layout)

        # 4. 弹簧 (把所有东西顶上去)
        main_layout.addStretch(1)

        self.setObjectName("RightToolPanel")
        self._update_style()

    def _update_style(self):
        bg = "#202020" if isDarkTheme() else "#f3f3f3"
        border = "#3a3a3a" if isDarkTheme() else "#e0e0e0"
        self.setStyleSheet(f"#RightToolPanel {{ background: {bg}; border-left: 1px solid {border}; }}")

    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        tool_name = e.mimeData().text()

        # 优化判定逻辑：不再用屏幕中心，而是用分割线的位置
        # 如果分割线隐藏了（说明有一个列表为空），或者鼠标在分割线下方，则判定为 bottom

        sep_pos = self.separator.mapTo(self, QPoint(0, 0)).y()
        sep_height = self.separator.height()
        mouse_y = e.pos().y()

        # 判定逻辑：
        # 如果鼠标在分割线中心线以下 -> Bottom
        # 如果鼠标在分割线中心线以上 -> Top
        # 注意：如果分割线是隐藏的，我们需要预判一下

        if self.separator.isVisible():
            is_bottom = mouse_y > (sep_pos + sep_height / 2)
        else:
            # 如果分割线不可见，说明可能全在top或者全在bottom
            # 简单粗暴：如果当前top有按钮，且鼠标在最下面，算bottom；
            # 或者为了操作方便，如果在面板下半部分，就算bottom（虽然现在视觉上都在上面，但在空白处松手可以归到底部组）
            # 这里为了符合PyCharm逻辑：拖到现有Top按钮列表下方较远位置算Bottom

            top_layout_height = self._top_layout.sizeHint().height()
            if mouse_y > top_layout_height + 20:
                is_bottom = True
            else:
                is_bottom = False

        new_pos = "bottom" if is_bottom else "top"
        self.toolMoveRequested.emit(tool_name, new_pos)
        e.acceptProposedAction()

    def create_button(self, tool_cls):
        btn = ToggleNavigationButton(tool_cls.icon or FIF.BRUSH, tool_cls.name, self)
        btn.setToolTip(tool_cls.name)
        self._button_by_name[tool_cls.name] = btn
        self._tool_by_button[btn] = tool_cls
        return btn

    def add_button_to_layout(self, tool_name, position_str):
        btn = self._button_by_name.get(tool_name)
        if not btn: return
        tool_cls = self._tool_by_button.get(btn)

        # 清理旧连接
        try:
            btn.clicked.disconnect()
        except:
            pass

        # 移除旧布局归属
        self._top_layout.removeWidget(btn)
        if btn in self._top_buttons: self._top_buttons.remove(btn)

        self._bottom_layout.removeWidget(btn)
        if tool_name in self._bottom_buttons: self._bottom_buttons.pop(tool_name)

        # 添加到新布局
        if position_str == "top":
            btn.clicked.connect(lambda: self._on_top_clicked(btn, tool_cls))
            self._top_layout.addWidget(btn)
            self._top_buttons.append(btn)
        else:
            btn.clicked.connect(lambda: self._on_bottom_clicked(btn, tool_cls))
            self._bottom_layout.addWidget(btn)
            self._bottom_buttons[tool_name] = btn

        btn.show()
        self._update_separator_visibility()

    def _update_separator_visibility(self):
        """只有当上下都有元素时才显示分割线，看起来更整洁"""
        has_top = self._top_layout.count() > 0
        has_bottom = self._bottom_layout.count() > 0
        # 只要有任何一组有元素，且为了体现分栏感，通常建议只要有一组非空，且另一组可能被拖入时...
        # 但为了视觉最佳：如果只有Top，没必要显示线。如果只有Bottom，也没必要。
        # 只有两边都有才显示，或者你想模仿PyCharm即便一边为空也保留分隔占位？
        # 这里采用：两边都有按钮时显示分割线。
        self.separator.setVisible(has_top and has_bottom)

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