# -*- coding: utf-8 -*-
from typing import Type, Optional, Dict
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize, QTimer, QRectF, QEvent, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QStackedWidget,
    QHBoxLayout,
    QDialog,
    QVBoxLayout,
    QLabel,
)
from PyQt5.QtGui import QPainter, QColor
from qfluentwidgets import isDarkTheme, ToolButton, IconWidget, FluentIcon as FIF

from .button_bar import RightToolPanel
from .registry import SideDockRegistry
from .tool_window import DockPosition, ToolWindow
from ..basic_widget.splitter import ModernSplitter
from ...utils.utils import get_icon


class AdaptiveStackedWidget(QStackedWidget):
    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.sizeHint() if current else QSize(0, 0)

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.minimumSizeHint() if current else QSize(0, 0)


class ToolPopupDialog(QDialog):
    popupClosed = pyqtSignal()

    def __init__(self, tool_instance: ToolWindow, parent=None):
        super().__init__(parent)
        self.tool_instance = tool_instance
        self._drag_pos = None
        self._is_maximized = False
        self._restore_tool_name = None
        self._restore_was_in_top = False
        self.setWindowTitle(tool_instance.name)
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(500, 400)
        self.setSizeGripEnabled(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._create_title_bar()
        main_layout.addWidget(self._title_bar)
        main_layout.addWidget(tool_instance, 1)

        self.destroyed.connect(self._on_destroyed)

    def setRestoreInfo(self, tool_name, was_in_top):
        self._restore_tool_name = tool_name
        self._restore_was_in_top = was_in_top

    def closeEvent(self, event):
        self.popupClosed.emit()
        super().closeEvent(event)

    def _create_title_bar(self):
        self._title_bar = QWidget(self)
        self._title_bar.setFixedHeight(36)

        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(10, 0, 5, 0)
        title_layout.setSpacing(8)

        self._icon_widget = IconWidget(self.tool_instance.icon, self._title_bar)
        self._icon_widget.setFixedSize(18, 18)

        self._title_label = QLabel(self.tool_instance.name, self._title_bar)
        self._title_label.setObjectName("titleLabel")

        title_layout.addWidget(self._icon_widget)
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()

        self._min_btn = ToolButton(FIF.MINIMIZE, self._title_bar)
        self._min_btn.setFixedSize(30, 30)
        self._min_btn.clicked.connect(self.showMinimized)

        self._max_btn = ToolButton(get_icon("放大"), self._title_bar)
        self._max_btn.setFixedSize(30, 30)
        self._max_btn.setToolTip("最大化")
        self._max_btn.clicked.connect(self._toggle_maximize)

        self._close_btn = ToolButton(FIF.CLOSE, self._title_bar)
        self._close_btn.setFixedSize(30, 30)
        self._close_btn.clicked.connect(self.close)

        self._close_btn.installEventFilter(self)

        title_layout.addWidget(self._min_btn)
        title_layout.addWidget(self._max_btn)
        title_layout.addWidget(self._close_btn)

        if isDarkTheme():
            bg = "#2d2d2d"
            border = "#404040"
            title_color = "#e0e0e0"
        else:
            bg = "#f5f5f5"
            border = "#d0d0d0"
            title_color = "#333333"
        self._title_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-bottom: 1px solid {border};
            }}
            QLabel {{
                color: {title_color};
                font-size: 13px;
                font-weight: bold;
            }}
            ToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }}
            ToolButton:hover {{
                background-color: rgba(128, 128, 128, 30);
            }}
        """)

        bg = "#383838" if isDarkTheme() else "#f0f0f0"
        border = "#454545" if isDarkTheme() else "#e0e0e0"
        title_color = "#ffffff" if isDarkTheme() else "#333333"
        self._title_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-bottom: 1px solid {border};
            }}
            QLabel {{
                color: {title_color};
            }}
            ToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }}
            ToolButton:hover {{
                background-color: rgba(255, 255, 255, 15);
            }}
        """)

    def _toggle_maximize(self):
        if self._is_maximized:
            self.showNormal()
            self._is_maximized = False
        else:
            self.showMaximized()
            self._is_maximized = True

    def eventFilter(self, obj, event):
        if obj == self._close_btn and event.type() == QEvent.Enter:
            self._close_btn.setStyleSheet(
                "background-color: #e81123; border-radius: 4px;"
            )
        elif obj == self._close_btn and event.type() == QEvent.Leave:
            self._close_btn.setStyleSheet("")
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.tool_instance.show()
        self.adjustSize()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if isDarkTheme():
            bg_color = QColor(38, 38, 38)
            border_color = QColor(55, 55, 55)
            shadow_color = QColor(0, 0, 0, 120)
        else:
            bg_color = QColor(245, 245, 245)
            border_color = QColor(200, 200, 200)
            shadow_color = QColor(0, 0, 0, 50)

        painter.setBrush(shadow_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, self.width() - 4, self.height() - 4, 10, 10)

        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(0, 0, self.width() - 4, self.height() - 4, 10, 10)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.y() < self._title_bar.height():
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _on_destroyed(self):
        if hasattr(self.tool_instance, "set_allowed_update"):
            self.tool_instance.set_allowed_update(False)


class SideDockArea(QWidget):
    def __init__(self, page, context_id):
        super().__init__()
        self.page = page
        self.context_id = context_id
        self._instances: Dict[str, ToolWindow] = {}
        self._popup_windows: Dict[str, ToolPopupDialog] = {}

        self.setUpdatesEnabled(False)

        try:
            main_layout = QHBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # 内容分栏
            self.splitter = ModernSplitter(Qt.Vertical)
            self.top_stack = AdaptiveStackedWidget()
            self.bottom_stack = AdaptiveStackedWidget()
            self.top_stack.hide()
            self.bottom_stack.hide()
            self._top_visible = False
            self._bottom_visible = False
            self.last_content_visible = False

            self.splitter.addWidget(self.top_stack)
            self.splitter.addWidget(self.bottom_stack)

            # 工具按钮栏 (保留变量名 tool_panel)
            self.tool_panel = RightToolPanel(page, self)
            self.tool_panel.topToolChecked.connect(self._show_top_tool)
            self.tool_panel.topToolUnchecked.connect(self._hide_top_tool)
            self.tool_panel.bottomToolChecked.connect(self._show_bottom_tool)
            self.tool_panel.bottomToolUnchecked.connect(self._hide_bottom_tool)
            self.tool_panel.toolMoveRequested.connect(self._handle_tool_reposition)
            self.tool_panel.toolHidden.connect(self._handle_tool_hidden)
            self.tool_panel.toolPopupRequested.connect(self._handle_tool_popup)

            main_layout.addWidget(self.splitter)

            self._load_plugins(context_id)

        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def _handle_tool_reposition(self, tool_name, pos_str):
        """处理拖拽后的位置逻辑切换"""
        instance = self.get_tool_instance(tool_name)
        if not instance:
            return

        new_pos = DockPosition.TOP if pos_str == "top" else DockPosition.BOTTOM
        if hasattr(instance, "position") and instance.position == new_pos:
            return

        was_visible = instance.isVisible()

        self.top_stack.removeWidget(instance)
        self.bottom_stack.removeWidget(instance)

        self.tool_panel.add_button_to_layout(
            tool_name, pos_str, force_checked=was_visible
        )

        instance.position = new_pos

        if not was_visible:
            self._update_splitter()

    def _handle_tool_hidden(self, tool_name):
        """处理工具隐藏"""
        if tool_name in self._popup_windows:
            popup = self._popup_windows.pop(tool_name)
            popup.close()
            popup.deleteLater()

        instance = self.get_tool_instance(tool_name)
        if instance:
            self.top_stack.removeWidget(instance)
            self.bottom_stack.removeWidget(instance)
            if hasattr(instance, "set_allowed_update"):
                instance.set_allowed_update(False)
        self._update_splitter()

    def _handle_tool_popup(self, tool_name):
        """处理工具弹窗显示"""
        if tool_name in self._popup_windows:
            popup = self._popup_windows[tool_name]
            popup.show()
            popup.raise_()
            popup.activateWindow()
            return

        btn = self.tool_panel._button_by_name.get(tool_name)
        if not btn:
            return

        instance = self.get_tool_instance(tool_name)
        if not instance:
            return

        was_checked = btn.isChecked()
        was_in_top = btn in self.tool_panel._top_buttons

        instance.hide()
        if self.top_stack.indexOf(instance) >= 0:
            self.top_stack.removeWidget(instance)
        if self.bottom_stack.indexOf(instance) >= 0:
            self.bottom_stack.removeWidget(instance)
        instance.setParent(None)
        instance.show()

        if was_checked:
            btn.setChecked(False)
            if was_in_top:
                self._top_visible = False
            else:
                self._bottom_visible = False
            self._update_splitter()

        popup = ToolPopupDialog(instance, self)
        popup.setRestoreInfo(tool_name, was_in_top)
        popup.popupClosed.connect(
            lambda tn=tool_name, wt=was_in_top: self._on_popup_closed(tn, wt)
        )
        self._popup_windows[tool_name] = popup
        popup.resize(600, 400)
        popup.show()

    def _on_popup_closed(self, tool_name, was_in_top):
        """弹窗关闭后恢复侧边栏显示"""
        self._popup_windows.pop(tool_name, None)
        btn = self.tool_panel._button_by_name.get(tool_name)
        if btn and not btn.isChecked():
            btn.setChecked(True)
            if was_in_top:
                self._show_top_tool(tool_name)
            else:
                self._show_bottom_tool(tool_name)

    def switch_to(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if view is None:
            return
        self.tool_panel.set_checked(tool_name)

    def _show_top_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(True)
        if self.top_stack.indexOf(view) == -1:
            self.top_stack.addWidget(view)
        self.top_stack.setCurrentWidget(view)
        self.top_stack.show()
        self._top_visible = True
        self._update_splitter()

    def _hide_top_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(False)
        self.top_stack.hide()
        self._top_visible = False
        self._update_splitter()

    def _show_bottom_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(True)
        if self.bottom_stack.indexOf(view) == -1:
            self.bottom_stack.addWidget(view)
        self.bottom_stack.setCurrentWidget(view)
        self.bottom_stack.show()
        self._bottom_visible = True
        self._update_splitter()

    def _hide_bottom_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(False)
        self.bottom_stack.hide()
        self._bottom_visible = False
        self._update_splitter()

    def _update_splitter(self):
        if self.last_content_visible and not (
            self._top_visible or self._bottom_visible
        ):
            self.splitter.setSizes([0, 0])
            self.page.hide_splitter()
            self.last_content_visible = False
            return
        elif not self.last_content_visible and (
            self._top_visible or self._bottom_visible
        ):
            self.last_content_visible = True
            self.page.show_splitter()

        if self._top_visible and self._bottom_visible:
            self.splitter.setSizes([1, 1])
        elif self._top_visible:
            self.splitter.setSizes([1, 0])
        else:
            self.splitter.setSizes([0, 1])

    def _load_plugins(self, context_id):
        top_classes = []
        for name, entry in SideDockRegistry.get_all(context_id).items():
            # 先创建按钮
            self.tool_panel.create_button(entry.cls)
            # 再按初始位置摆放按钮
            pos_str = "top" if entry.position == DockPosition.TOP else "bottom"
            self.tool_panel.add_button_to_layout(name, pos_str)

            if entry.position == DockPosition.TOP:
                top_classes.append(entry.cls)

        if top_classes:
            first_cls = top_classes[0]
            QtCore.QTimer.singleShot(
                100, lambda cls=first_cls: self._show_top_tool(cls.name)
            )
            self.last_content_visible = True
            self.tool_panel._set_top_button_checked(first_cls)

    def _get_or_create_instance(self, cls: Type[ToolWindow]) -> ToolWindow:
        """根据 singleton 策略获取或创建实例，并将 button 注入"""
        self.setUpdatesEnabled(False)
        try:
            name = cls.name
            if cls.singleton and name in self._instances:
                return self._instances[name]

            # 【关键重构】从 tool_panel 获取对应的按钮实例
            btn_instance = self.tool_panel._button_by_name.get(name)

            # 注入 button 到插件类构造函数中
            instance = cls(self.page, button=btn_instance)

            # 初始化位置信息
            entry = SideDockRegistry._registries.get(self.context_id).get(name)
            instance.position = entry.position if entry else DockPosition.TOP

            if cls.singleton:
                self._instances[name] = instance
            return instance
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def get_tool_instance(self, name: str) -> Optional[ToolWindow]:
        entry = SideDockRegistry._registries.get(self.context_id).get(name)
        if entry is None:
            return None
        return self._get_or_create_instance(entry.cls)

    def cleanup(self):
        try:
            self.tool_panel.topToolChecked.disconnect(self._show_top_tool)
            self.tool_panel.topToolUnchecked.disconnect(self._hide_top_tool)
            self.tool_panel.bottomToolChecked.disconnect(self._show_bottom_tool)
            self.tool_panel.bottomToolUnchecked.disconnect(self._hide_bottom_tool)
            self.tool_panel.toolMoveRequested.disconnect(self._handle_tool_reposition)
            self.tool_panel.toolHidden.disconnect(self._handle_tool_hidden)
            self.tool_panel.toolPopupRequested.disconnect(self._handle_tool_popup)
        except:
            pass

        for name, popup in list(self._popup_windows.items()):
            popup.close()
            popup.deleteLater()
        self._popup_windows.clear()

        for name, instance in self._instances.items():
            if hasattr(instance, "cleanup"):
                instance.cleanup()
            instance.setParent(None)
            instance.deleteLater()
        self._instances.clear()

        def clear_stacked(stack: QStackedWidget):
            while stack.count():
                widget = stack.widget(0)
                stack.removeWidget(widget)
                widget.deleteLater()

        clear_stacked(self.top_stack)
        clear_stacked(self.bottom_stack)
        self.splitter.deleteLater()
        self.tool_panel.deleteLater()
