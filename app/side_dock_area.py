# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QSize, QTimer, QEvent, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import (
    QWidget,
    QStackedWidget,
    QDialog,
    QVBoxLayout,
)
from qfluentwidgets import isDarkTheme, FluentIcon as FIF, TransparentToolButton, FluentIcon

from app.utils.config import Settings
from app.utils.utils import get_icon


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


class ResizeEdge(QWidget):
    """边缘拖拽区域"""
    EDGE_NONE = 0
    EDGE_TOP = 1
    EDGE_BOTTOM = 2
    EDGE_LEFT = 4
    EDGE_RIGHT = 8
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._edge = ResizeEdge.EDGE_NONE
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self._update_cursor()
    
    def set_edge(self, edge):
        self._edge = edge
        self._update_cursor()
    
    def _update_cursor(self):
        if self._edge == ResizeEdge.EDGE_TOP or self._edge == ResizeEdge.EDGE_BOTTOM:
            self.setCursor(Qt.SizeVerCursor)
        elif self._edge == ResizeEdge.EDGE_LEFT or self._edge == ResizeEdge.EDGE_RIGHT:
            self.setCursor(Qt.SizeHorCursor)
        elif self._edge == (ResizeEdge.EDGE_TOP | ResizeEdge.EDGE_LEFT) or \
             self._edge == (ResizeEdge.EDGE_BOTTOM | ResizeEdge.EDGE_RIGHT):
            self.setCursor(Qt.SizeFDiagCursor)
        elif self._edge == (ResizeEdge.EDGE_TOP | ResizeEdge.EDGE_RIGHT) or \
             self._edge == (ResizeEdge.EDGE_BOTTOM | ResizeEdge.EDGE_LEFT):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)


class ToolPopupDialog(QDialog):
    popupClosed = pyqtSignal(str, bool, object)

    def __init__(self, tool_instance, parent=None, border_color: str = "none"):
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
        self._resize_edge = ResizeEdge.EDGE_NONE
        self._resize_start_geometry = None
        self._edge_size = 6  # 边缘检测区域宽度
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

        # 设置按钮已移除（移到主窗口内）

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

    def _show_settings(self):
        """显示设置弹窗 - 已被移除，按钮已移到主窗口"""
        pass

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
        # ESC 不做任何操作，忽略事件
        if event.key() == Qt.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._is_closing:
            event.accept()
            return
        self._is_closing = True
        self._save_geometry()
        self._restore_title_bar()
        Settings.get_instance().save()
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

    def _get_edge_at_pos(self, pos):
        """检测指定位置位于哪个边缘"""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        edge = ResizeEdge.EDGE_NONE
        
        # 检测顶部边缘
        if y < self._edge_size:
            edge |= ResizeEdge.EDGE_TOP
        # 检测底部边缘
        elif y > h - self._edge_size:
            edge |= ResizeEdge.EDGE_BOTTOM
        # 检测左边缘
        if x < self._edge_size:
            edge |= ResizeEdge.EDGE_LEFT
        # 检测右边缘
        elif x > w - self._edge_size:
            edge |= ResizeEdge.EDGE_RIGHT
        
        return edge

    def _perform_resize(self, global_pos):
        """执行边缘缩放"""
        if self._resize_edge == ResizeEdge.EDGE_NONE or not self._resize_start_geometry:
            return
        
        delta = global_pos - self._resize_start_pos
        geom = self._resize_start_geometry
        x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
        min_w, min_h = self.minimumSize().width(), self.minimumSize().height()
        
        edge = self._resize_edge
        
        # 处理左右边缘
        if edge & ResizeEdge.EDGE_LEFT:
            new_x = x + delta.x()
            new_w = w - delta.x()
            if new_w >= min_w:
                x = new_x
                w = new_w
        elif edge & ResizeEdge.EDGE_RIGHT:
            w = max(min_w, w + delta.x())
        
        # 处理上下边缘
        if edge & ResizeEdge.EDGE_TOP:
            new_y = y + delta.y()
            new_h = h - delta.y()
            if new_h >= min_h:
                y = new_y
                h = new_h
        elif edge & ResizeEdge.EDGE_BOTTOM:
            h = max(min_h, h + delta.y())
        
        self.setGeometry(x, y, w, h)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            title_bar = self.tool_instance.get_title_bar()
            if title_bar and event.y() < title_bar.height():
                self._hide_opacity_slider()
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
                return
            
            # 检查是否在边缘区域开始拖拽
            edge = self._get_edge_at_pos(event.pos())
            if edge != ResizeEdge.EDGE_NONE:
                self._resize_edge = edge
                self._resize_start_pos = event.globalPos()
                self._resize_start_geometry = self.geometry()
                self._hide_opacity_slider()
                event.accept()
                return

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            # 正在边缘拖拽缩放
            if self._resize_edge != ResizeEdge.EDGE_NONE:
                self._perform_resize(event.globalPos())
                event.accept()
                return
            
            # 标题栏拖拽移动
            if self._drag_pos:
                self.move(event.globalPos() - self._drag_pos)
                event.accept()
                return
        else:
            # 更新鼠标光标形状（排除标题栏区域）
            title_bar = self.tool_instance.get_title_bar()
            title_height = title_bar.height() if title_bar else 0
            if event.y() > title_height:
                edge = self._get_edge_at_pos(event.pos())
                if edge == ResizeEdge.EDGE_TOP or edge == ResizeEdge.EDGE_BOTTOM:
                    self.setCursor(Qt.SizeVerCursor)
                elif edge == ResizeEdge.EDGE_LEFT or edge == ResizeEdge.EDGE_RIGHT:
                    self.setCursor(Qt.SizeHorCursor)
                elif edge == (ResizeEdge.EDGE_TOP | ResizeEdge.EDGE_LEFT) or \
                     edge == (ResizeEdge.EDGE_BOTTOM | ResizeEdge.EDGE_RIGHT):
                    self.setCursor(Qt.SizeFDiagCursor)
                elif edge == (ResizeEdge.EDGE_TOP | ResizeEdge.EDGE_RIGHT) or \
                     edge == (ResizeEdge.EDGE_BOTTOM | ResizeEdge.EDGE_LEFT):
                    self.setCursor(Qt.SizeBDiagCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            self._show_opacity_slider()
            self._hide_timer_start()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = ResizeEdge.EDGE_NONE
        self._resize_start_geometry = None
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

