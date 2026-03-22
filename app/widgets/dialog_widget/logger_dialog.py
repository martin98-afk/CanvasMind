# -*- coding: utf-8 -*-
from loguru import logger
from collections import deque

from PyQt5.QtCore import QObject, pyqtSignal, Qt, QPoint
from PyQt5.QtGui import QTextCharFormat, QColor, QTextCursor, QFont, QCursor
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QApplication,
    QTabWidget,
    QScrollArea,
    QHBoxLayout,
)
from qfluentwidgets import StrongBodyLabel

from app.utils.config import Settings


class TabbedLogWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #0e1117;
            }
            QTabWidget::tab-bar {
                alignment: left;
            }
            QTabBar::tab {
                background-color: #1e1e1e;
                color: #888888;
                padding: 6px 12px;
                border: none;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #0e1117;
                color: white;
            }
            QTabBar::tab:hover {
                color: white;
            }
        """)

        self.log_tabs = {}
        self.log_handlers = {}

        tab_configs = [
            ("全部", "all"),
            ("画布", "canvas"),
            ("组件", "component"),
            ("AI对话", "llm"),
            ("系统", "system"),
        ]

        for label, key in tab_configs:
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setStyleSheet("""
                QScrollArea {
                    background-color: #0e1117;
                    border: none;
                }
            """)
            text_edit = QPlainTextEdit()
            text_edit.document().setDocumentMargin(0)
            text_edit.setObjectName(label)
            text_edit.setReadOnly(True)
            text_edit.setFont(QFont(Settings.get_instance().canvas_font_type.value, 11))
            text_edit.setStyleSheet("""
                QPlainTextEdit {
                    background-color: #0e1117;
                    color: white;
                    border: none;
                    font-family: Consolas, monospace;
                    font-size: 13px;
                    padding: 5px;
                }
                QPlainTextEdit QScrollBar:vertical { 
                    background: transparent; 
                    width: 10px; 
                }
                QPlainTextEdit QScrollBar::handle:vertical { 
                    background: #555555; 
                    border-radius: 5px; 
                }
            """)

            scroll_area.setWidget(text_edit)
            self.tab_widget.addTab(scroll_area, label)

            handler = QTextEditLogger(text_edit, max_lines=1000)
            self.log_tabs[key] = text_edit
            self.log_handlers[key] = handler

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tab_widget)

        self._setup_log_handlers()

    def _setup_log_handlers(self):
        logger.remove()

        logger.add(
            self.log_handlers["all"],
            format="{time:HH:mm:ss} | {level} | {file}:{line} {message}",
            level="DEBUG",
            filter=self._filter_all,
        )

        logger.add(
            self.log_handlers["canvas"],
            format="{time:HH:mm:ss} | {level} | {file}:{line} {message}",
            level="DEBUG",
            filter=self._filter_canvas,
        )

        logger.add(
            self.log_handlers["component"],
            format="{time:HH:mm:ss} | {level} | {file}:{line} {message}",
            level="DEBUG",
            filter=self._filter_component,
        )

        logger.add(
            self.log_handlers["llm"],
            format="{time:HH:mm:ss} | {level} | {file}:{line} {message}",
            level="DEBUG",
            filter=self._filter_llm,
        )

        logger.add(
            self.log_handlers["system"],
            format="{time:HH:mm:ss} | {level} | {file}:{line} {message}",
            level="DEBUG",
            filter=self._filter_system,
        )

    def _filter_all(self, record):
        return True

    def _filter_canvas(self, record):
        file_path = record.get("file", "")
        if file_path:
            path_str = str(file_path)
            return "canvas_interaface" in path_str or "canvas_interface" in path_str
        return False

    def _filter_component(self, record):
        file_path = record.get("file", "")
        if file_path:
            return "component_developer" in str(file_path)
        return False

    def _filter_llm(self, record):
        file_path = record.get("file", "")
        if file_path:
            return "llm_chatter" in str(file_path)
        return False

    def _filter_system(self, record):
        file_path = record.get("file", "")
        if file_path:
            path_str = str(file_path)
            if (
                "canvas_interaface" in path_str
                or "canvas_interface" in path_str
                or "component_developer" in path_str
                or "llm_chatter" in path_str
            ):
                return False
            return True
        return False

    def get_current_text_edit(self):
        scroll_area = self.tab_widget.currentWidget()
        if scroll_area:
            return scroll_area.widget()
        return None

    def scroll_to_bottom(self, force=False):
        text_edit = self.get_current_text_edit()
        if text_edit:
            text_edit.verticalScrollBar().setValue(
                text_edit.verticalScrollBar().maximum()
            )


class LogPopupWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._resizing = False
        self._start_pos = None
        self._start_width = None
        self._min_width = 400
        self._max_width = 1000
        self._base_x = 0
        self._resize_zone_width = 8
        self.setup_ui()

    def setup_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1e1e1e;
                border-right: %dpx solid #404040;
            }
        """
            % self._resize_zone_width
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet(
            "background-color: #1e1e1e; border-bottom: 1px solid #3c3c3c;"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(8)

        title_label = StrongBodyLabel("执行日志")
        title_label.setStyleSheet("color: white;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.resize_grip = QWidget()
        self.resize_grip.setFixedSize(20, 16)
        self.resize_grip.setStyleSheet("""
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 transparent, stop:0.5 #666666, stop:1 transparent);
        """)
        header_layout.addWidget(self.resize_grip)

        self.tabbed_log_widget = TabbedLogWidget()

        main_layout.addWidget(header)
        main_layout.addWidget(self.tabbed_log_widget)

        self.resize(550, 600)

    def set_width(self, width):
        width = max(self._min_width, min(width, self._max_width))
        self.resize(width, self.height())

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and event.pos().x() >= self.width() - self._resize_zone_width
        ):
            self._resizing = True
            self._start_pos = event.globalPos()
            self._start_width = self.width()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        is_in_resize_zone = event.pos().x() >= self.width() - self._resize_zone_width

        if is_in_resize_zone:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

        if self._resizing:
            delta = event.globalPos() - self._start_pos
            new_width = self._start_width + delta.x()
            self.set_width(new_width)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        super().mouseReleaseEvent(event)

    def show_at_left(self, parent_widget, log_button_top_right):
        self._parent_widget = parent_widget
        x = log_button_top_right.x() - 5
        self._base_x = x

        parent_global_y = parent_widget.mapToGlobal(QPoint(0, 0)).y()
        y = parent_global_y

        popup_height = parent_widget.height()
        screen = QApplication.desktop().screenGeometry(parent_widget)
        if y + popup_height > screen.bottom():
            popup_height = screen.bottom() - y - 10

        self.move(x, y)
        self.resize(400, popup_height)
        self.show()
        self.activateWindow()

    def _update_position(self, parent_widget):
        if not hasattr(self, "_parent_widget"):
            return

        nav_interface = parent_widget.navigationInterface
        nav_right = nav_interface.rect().right()
        nav_right_global = nav_interface.mapToGlobal(QPoint(nav_right, 0))
        x = nav_right_global.x() - 5

        parent_global_y = parent_widget.mapToGlobal(QPoint(0, 0)).y()
        y = parent_global_y

        popup_height = parent_widget.height()
        screen = QApplication.desktop().screenGeometry(parent_widget)
        if y + popup_height > screen.bottom():
            popup_height = screen.bottom() - y - 10

        self.move(x, y)
        self.resize(self.width(), popup_height)

    def hidePopup(self):
        self.hide()

    def scroll_to_bottom(self, force=False):
        self.tabbed_log_widget.scroll_to_bottom(force=force)

    def _clean_trailing_empty_lines(self):
        pass


class QTextEditLogger(QObject):
    """线程安全的日志记录器，专为Qt应用设计（无空白行版）"""

    log_signal = pyqtSignal(str, str)  # (level, message)

    def __init__(self, text_edit, max_lines=1000):
        super().__init__()
        self.text_edit = text_edit
        self.buffer = deque(maxlen=max_lines)
        self.is_scrolling = True  # 跟踪用户是否手动滚动

        # 级别对应颜色
        self.colors = {
            "DEBUG": QColor("#00BFFF"),
            "INFO": QColor("#00FF7F"),
            "WARNING": QColor("#FFD700"),
            "ERROR": QColor("#FF4500"),
            "CRITICAL": QColor("#FF1493"),
        }

        # 连接信号到安全处理槽
        self.log_signal.connect(self._safe_append_line, Qt.QueuedConnection)

        # 连接滚动条信号
        self.text_edit.verticalScrollBar().valueChanged.connect(
            self._on_scroll_value_changed
        )

    def write(self, message):
        """安全写入日志（可被任何线程调用）"""
        text = message.strip()
        if not text:
            return

        # 提取日志级别
        level = "INFO"
        for lvl in self.colors:
            if f"| {lvl} |" in text:
                level = lvl
                break

        # 缓存到内存
        self.buffer.append((level, text))

        # 通过信号安全传递到主线程
        self.log_signal.emit(level, text)

    def _on_scroll_value_changed(self, value):
        """当用户滚动时更新状态"""
        max_value = self.text_edit.verticalScrollBar().maximum()
        self.is_scrolling = value >= max_value - 2

    def _safe_text_cursor(self) -> QTextCursor:
        """安全获取文本游标"""
        if not self._is_widget_valid():
            return None
        try:
            return self.text_edit.textCursor()
        except RuntimeError:
            return None

    def _safe_append_line(self, level: str, line: str):
        """主线程执行的日志追加（正确处理换行和空白）"""
        # 1. 检查UI对象是否有效
        if not self._is_widget_valid():
            return

        # 2. 检查日志级别有效性
        color = self.colors.get(level, QColor("#FFFFFF"))

        # 3. 创建格式化对象
        fmt = QTextCharFormat()
        fmt.setForeground(color)

        # 4. 安全获取文档
        doc = self.text_edit.document()
        if not doc:
            return

        # 5. 直接操作文档
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)

        # 关键修复：总是添加换行符（确保每条日志独占一行）
        # 注意：QPlainTextEdit需要显式换行符才能分行显示
        cursor.insertText(line + "\n", fmt)

        # 6. 清理底部空白（关键：在滚动前清理）
        self._clean_trailing_empty_lines()

        # 7. 滚动到底部（使用更可靠的方法）
        self._safe_scroll_to_bottom()

    def _clean_trailing_empty_lines(self):
        """清理文档末尾的额外空白行（只清理QPlainTextEdit自动添加的）"""
        if not self._is_widget_valid():
            return

        doc = self.text_edit.document()
        if not doc or doc.blockCount() <= 1:
            return

        # 保存当前滚动位置
        scroll_pos = self.text_edit.verticalScrollBar().value()
        max_scroll = self.text_edit.verticalScrollBar().maximum()

        # 如果当前在底部附近，标记为自动滚动
        at_bottom = scroll_pos >= max_scroll - 2

        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)

        # 检查最后一行是否为空（由QPlainTextEdit自动添加的）
        last_block = doc.lastBlock()
        if last_block.text().endswith("\n\n"):
            # 移除空行
            cursor.setPosition(last_block.position())
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # 删除段落结束符

        # 恢复滚动位置（如果之前在底部）
        if at_bottom:
            self.text_edit.verticalScrollBar().setValue(
                self.text_edit.verticalScrollBar().maximum()
            )

    def _safe_scroll_to_bottom(self):
        """安全滚动到底部（确保保留正常换行）"""
        if not self._is_widget_valid() or not self.is_scrolling:
            return

        try:
            # 方法1：直接滚动到文档末尾（最可靠）
            self.text_edit.verticalScrollBar().setValue(
                self.text_edit.verticalScrollBar().maximum()
            )
        except RuntimeError:
            pass

    def scroll_to_bottom(self, force=False):
        """
        滚动到底部（公共方法）
        :param force: 是否强制滚动（忽略 is_scrolling 状态）
        """
        if not self._is_widget_valid():
            return

        try:
            scroll_bar = self.text_edit.verticalScrollBar()
            if scroll_bar:
                if force:
                    # 强制滚动到底部
                    scroll_bar.setValue(scroll_bar.maximum())
                else:
                    # 只有在自动滚动模式下才滚动
                    if self.is_scrolling:
                        scroll_bar.setValue(scroll_bar.maximum())
        except RuntimeError:
            pass

    def _is_widget_valid(self) -> bool:
        """检查文本编辑控件是否有效"""
        if not hasattr(self, "text_edit") or self.text_edit is None:
            return False
        try:
            self.text_edit.isVisible()
            return True
        except RuntimeError:
            return False

    def flush(self):
        """标准流接口"""
        pass

    def close(self):
        """安全关闭（清理资源）"""
        try:
            self.log_signal.disconnect()
            self.text_edit.verticalScrollBar().valueChanged.disconnect(
                self._on_scroll_value_changed
            )
        except:
            pass
        self.text_edit = None
        self.buffer.clear()
