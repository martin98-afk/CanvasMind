# -*- coding: utf-8 -*-
from typing import Type, Optional, Dict
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize, QTimer, QRectF, QEvent, QPoint, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QStackedWidget,
    QHBoxLayout,
    QDialog,
    QVBoxLayout,
    QLabel,
)
from PyQt5.QtGui import QPainter, QColor
from qfluentwidgets import isDarkTheme, ToolButton, IconWidget, FluentIcon as FIF, TransparentToolButton

from .button_bar import RightToolPanel
from .registry import SideDockRegistry
from .tool_window import DockPosition, ToolWindow, ToolWindowTitleBar
from ..basic_widget.splitter import ModernSplitter
from ...utils.utils import get_icon


class OpacitySlider(QWidget):
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

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        bg_color = (
            QColor(38, 38, 38, 230) if isDarkTheme() else QColor(245, 245, 245, 230)
        )
        painter.setBrush(bg_color)
        painter.drawRoundedRect(self.rect(), 8, 8)

        track_height = self.height() - 2 * self._track_padding
        track_width = 4
        track_x = (self.width() - track_width) // 2
        track_y = self._track_padding

        track_bg = (
            QColor(100, 100, 100, 150) if isDarkTheme() else QColor(180, 180, 180, 150)
        )
        painter.setBrush(track_bg)
        painter.drawRoundedRect(track_x, track_y, track_width, track_height, 2, 2)

        fill_height = int(track_height * self._opacity / 100)
        fill_color = QColor("#0078d4")
        painter.setBrush(fill_color)
        painter.drawRoundedRect(
            track_x,
            track_y + track_height - fill_height,
            track_width,
            fill_height,
            2,
            2,
        )

        knob_y = track_y + track_height - fill_height - self._knob_height // 2
        knob_color = QColor(255, 255, 255) if isDarkTheme() else QColor(80, 80, 80)
        painter.setBrush(knob_color)
        painter.drawEllipse(
            QPoint(self.width() // 2, knob_y + self._knob_height // 2), 7, 7
        )

        painter.setPen(QColor(200, 200, 200) if isDarkTheme() else QColor(80, 80, 80))
        painter.setFont(self.font())
        painter.drawText(
            self.rect(), Qt.AlignBottom | Qt.AlignHCenter, f"{self._opacity}%"
        )

    def setOpacity(self, value: int):
        self._opacity = max(0, min(100, value))
        self.update()
        self.opacityChanged.emit(self._opacity)

    def opacity(self) -> int:
        return self._opacity

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

    def enterEvent(self, e):
        super().enterEvent(e)
        if (
            hasattr(self.parent(), "_hide_timer")
            and self.parent()._hide_timer.isActive()
        ):
            self.parent()._hide_timer.stop()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if hasattr(self.parent(), "_hide_timer"):
            self.parent()._hide_timer.start()

    def _update_from_mouse(self, pos: QPoint):
        track_height = self.height() - 2 * self._track_padding
        rel_y = pos.y() - self._track_padding
        value = int((1 - rel_y / track_height) * 100)
        self.setOpacity(value)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        self.setOpacity(self._opacity + (delta // 120) * 5)


class AdaptiveStackedWidget(QStackedWidget):
    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.sizeHint() if current else QSize(0, 0)

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.minimumSizeHint() if current else QSize(0, 0)


class ToolPopupDialog(QDialog):
    popupClosed = pyqtSignal(str, bool, object)

    def __init__(self, tool_instance: ToolWindow, parent=None, border_color: str = "none"):
        super().__init__(parent)
        self.tool_instance = tool_instance
        self._border_color = border_color
        self._drag_pos = None
        self._is_maximized = False
        self._restore_tool_name = None
        self._restore_was_in_top = False
        self._restore_btn = None
        self._normal_geometry = None
        self._is_closing = False
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(160)
        self._geometry_save_timer.timeout.connect(self._save_geometry)
        self.setWindowTitle(tool_instance.name)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.FramelessWindowHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(400, 300)
        self.setSizeGripEnabled(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        title_bar = tool_instance.get_title_bar()
        title_bar.set_compact(False)
        title_bar.show()
        title_bar.clear_popup_buttons()
        title_bar.popupRequested.disconnect()
        title_bar.popupRequested.connect(self.close)
        self._popup_btn = title_bar._popup_btn
        self._popup_btn.setIcon(FIF.CLOSE)
        self._popup_btn.setToolTip("关闭")
        self._switch_btn = title_bar._switch_layout_btn
        self._switch_btn.hide()

        self._min_btn = TransparentToolButton(get_icon("最小化"), self)
        self._min_btn.setFixedSize(24, 24)
        self._min_btn.setToolTip("最小化")
        self._min_btn.clicked.connect(self.showMinimized)
        title_bar.add_popup_button(self._min_btn)

        self._max_btn = TransparentToolButton(get_icon("最大化"), self)
        self._max_btn.setFixedSize(24, 24)
        self._max_btn.setToolTip("最大化")
        self._max_btn.clicked.connect(self._toggle_maximize)
        title_bar.add_popup_button(self._max_btn)

        main_layout.addWidget(title_bar)
        main_layout.addWidget(tool_instance, 1)

        self.destroyed.connect(self._on_destroyed)

        self._opacity_slider = None
        self._original_opacity = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(200)
        self._hide_timer.timeout.connect(self._check_hide_slider)
        self.setMouseTracking(True)

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

    def setRestoreInfo(self, tool_name, was_in_top, btn):
        self._restore_tool_name = tool_name
        self._restore_was_in_top = was_in_top
        self._restore_btn = btn

    def showEvent(self, event):
        super().showEvent(event)
        self._restore_geometry()
        self.tool_instance.show()

    def _restore_geometry(self):
        from PyQt5.QtCore import QSettings

        settings = QSettings("WorkFlowGUI", "ToolPopup")
        key = f"popup_geometry_{self.tool_instance.name}"
        geometry = settings.value(key)
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(600, 450)
            self._center_on_screen()

    def _save_geometry(self):
        from PyQt5.QtCore import QSettings

        if self._is_maximized:
            return
        settings = QSettings("WorkFlowGUI", "ToolPopup")
        key = f"popup_geometry_{self.tool_instance.name}"
        settings.setValue(key, self.saveGeometry())

    def _center_on_screen(self):
        from PyQt5.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            x = (rect.width() - self.width()) // 2 + rect.x()
            y = (rect.height() - self.height()) // 2 + rect.y()
            self.move(x, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._is_closing:
            event.accept()
            return
        self._is_closing = True
        self._save_geometry()
        self._restore_title_bar()
        self.popupClosed.emit(
            self._restore_tool_name, self._restore_was_in_top, self._restore_btn
        )
        self.deleteLater()
        super().closeEvent(event)

    def _restore_title_bar(self):
        title_bar = self.tool_instance.get_title_bar()
        if not title_bar:
            return
        try:
            title_bar.popupRequested.disconnect()
        except:
            pass
        tool_name = self.tool_instance.name
        homepage = self.tool_instance.homepage
        title_bar.popupRequested.connect(lambda: homepage._handle_tool_popup(tool_name))
        self._popup_btn.setIcon(get_icon("弹出窗"))
        self._popup_btn.setToolTip("弹出窗口")
        self._switch_btn.show()
        title_bar.clear_popup_buttons()

    def eventFilter(self, obj, event):
        if obj == self._popup_btn and event.type() == QEvent.Enter:
            self._popup_btn.setStyleSheet(
                "background-color: #e81123; border-radius: 4px;"
            )
        elif obj == self._popup_btn and event.type() == QEvent.Leave:
            self._popup_btn.setStyleSheet("")
        return super().eventFilter(obj, event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            title_bar = self.tool_instance.get_title_bar()
            if title_bar and event.y() < title_bar.height():
                self._toggle_maximize()
                event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        opacity = self.windowOpacity()

        if isDarkTheme():
            bg_color = QColor(38, 38, 38, int(255 * opacity))
            shadow_color = QColor(0, 0, 0, int(120 * opacity))
        else:
            bg_color = QColor(245, 245, 245, int(255 * opacity))
            shadow_color = QColor(0, 0, 0, int(50 * opacity))

        # 根据配置设置边框颜色
        border_color_map = {
            "white": QColor(255, 255, 255, int(255 * opacity)),
            "yellow": QColor(255, 200, 0, int(255 * opacity)),
        }
        if self._border_color == "none":
            if isDarkTheme():
                border_color = QColor(55, 55, 55, int(255 * opacity))
            else:
                border_color = QColor(200, 200, 200, int(255 * opacity))
        else:
            border_color = border_color_map.get(
                self._border_color,
                QColor(55, 55, 55, int(255 * opacity)),
            )

        painter.setBrush(shadow_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, self.width() - 4, self.height() - 4, 10, 10)

        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(0, 0, self.width() - 4, self.height() - 4, 10, 10)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            title_bar = self.tool_instance.get_title_bar()
            if title_bar and event.y() < title_bar.height():
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
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._is_closing:
            self._geometry_save_timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._is_maximized or self._is_closing:
            return
        self._geometry_save_timer.start()

    def _on_destroyed(self):
        if hasattr(self.tool_instance, "set_allowed_update"):
            self.tool_instance.set_allowed_update(False)

    def _show_opacity_slider(self):
        if self._opacity_slider is None:
            self._opacity_slider = OpacitySlider(self)
            self._opacity_slider.opacityChanged.connect(self._on_opacity_changed)
        self._opacity_slider.setOpacity(int(self.windowOpacity() * 100))
        pos = self.mapToGlobal(QPoint(self.width(), 10))
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

    def eventFilter(self, obj, event):
        if obj == self._popup_btn and event.type() == QEvent.Enter:
            self._popup_btn.setStyleSheet(
                "background-color: #e81123; border-radius: 4px;"
            )
        elif obj == self._popup_btn and event.type() == QEvent.Leave:
            self._popup_btn.setStyleSheet("")
        return super().eventFilter(obj, event)

    def enterEvent(self, e):
        super().enterEvent(e)
        self._show_opacity_slider()
        self._hide_timer.stop()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._hide_timer_start()


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
            self._last_splitter_state = None

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

        container = getattr(instance, "_dock_container", None)
        if container:
            self.top_stack.removeWidget(container)
            self.bottom_stack.removeWidget(container)
        else:
            self.top_stack.removeWidget(instance)
            self.bottom_stack.removeWidget(instance)

        instance._dock_container = None

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
            container = getattr(instance, "_dock_container", None)
            if container:
                self.top_stack.removeWidget(container)
                self.bottom_stack.removeWidget(container)
                instance._dock_container = None
            else:
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

        container = getattr(instance, "_dock_container", None)
        if container:
            container.hide()
            if self.top_stack.indexOf(container) >= 0:
                self.top_stack.removeWidget(container)
            if self.bottom_stack.indexOf(container) >= 0:
                self.bottom_stack.removeWidget(container)
            instance._dock_container = None
        else:
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

        btn.setVisible(False)

        # 获取该插件的边框颜色配置
        from app.widgets.side_dock_area.registry import SideDockRegistry
        from app.widgets.side_dock_area.tool_window import DockCategory

        border_color = "none"
        for ctx_id in [c.value for c in DockCategory]:
            bc = SideDockRegistry.get_plugin_border_color(ctx_id, tool_name)
            if bc != "none":
                border_color = bc
                break

        popup = ToolPopupDialog(instance, None, border_color)
        popup.setRestoreInfo(tool_name, was_in_top, btn)
        popup.popupClosed.connect(self._on_popup_closed)
        self._popup_windows[tool_name] = popup
        popup.resize(600, 900)
        popup.show()

    def _on_popup_closed(self, tool_name, was_in_top, btn):
        """弹窗关闭后恢复侧边栏显示"""
        self._popup_windows.pop(tool_name, None)
        btn.setVisible(True)
        btn.setChecked(True)
        if was_in_top:
            self._show_top_tool(tool_name)
        else:
            self._show_bottom_tool(tool_name)

    def switch_to(self, tool_name):
        if tool_name in self._popup_windows:
            popup = self._popup_windows[tool_name]
            popup.show()
            popup.raise_()
            popup.activateWindow()
            return
        view = self.get_tool_instance(tool_name)
        if view is None:
            return
        self.tool_panel.set_checked(tool_name)

    def _show_top_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(True)

        container = self._get_or_create_dock_container(view)
        title_bar = container.title_bar

        try:
            title_bar.popupRequested.disconnect()
        except:
            pass
        title_bar.popupRequested.connect(lambda: self._handle_tool_popup(tool_name))

        if self.top_stack.indexOf(container) == -1:
            self.top_stack.addWidget(container)
        self.top_stack.setCurrentWidget(container)
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

        container = self._get_or_create_dock_container(view)
        title_bar = container.title_bar

        try:
            title_bar.popupRequested.disconnect()
        except:
            pass
        title_bar.popupRequested.connect(lambda: self._handle_tool_popup(tool_name))

        if self.bottom_stack.indexOf(container) == -1:
            self.bottom_stack.addWidget(container)
        self.bottom_stack.setCurrentWidget(container)
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

    def _get_or_create_dock_container(self, view):
        if hasattr(view, "_dock_container") and view._dock_container:
            return view._dock_container

        title_bar = view.get_title_bar()
        if not title_bar:
            view._init_title_bar()
            title_bar = view.get_title_bar()

        title_bar.set_compact(False)
        title_bar.show()

        container = QWidget()
        container.title_bar = title_bar
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(title_bar)
        layout.addWidget(view)

        view._dock_container = container
        container._view = view

        view.switchLayoutRequested.connect(lambda: self._on_tool_switch_layout(view))

        return container

    def _on_tool_switch_layout(self, view):
        tool_name = view.name
        btn = self.tool_panel._button_by_name.get(tool_name)
        if not btn:
            return

        is_in_top = btn in self.tool_panel._top_buttons
        new_pos = "bottom" if is_in_top else "top"
        self._handle_tool_reposition(tool_name, new_pos)

    def _update_splitter(self):
        state = (self._top_visible, self._bottom_visible, self.last_content_visible)
        if state == self._last_splitter_state:
            return
        self._last_splitter_state = state

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
        for name, entry in SideDockRegistry.get_all_entries(context_id).items():
            if not SideDockRegistry.is_plugin_enabled(context_id, name):
                continue
            current_position = SideDockRegistry.get_plugin_position(context_id, name)
            self.tool_panel.create_button(entry.cls)
            pos_str = "top" if current_position == DockPosition.TOP else "bottom"
            self.tool_panel.add_button_to_layout(name, pos_str)

            if current_position == DockPosition.TOP:
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
