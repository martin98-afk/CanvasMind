# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QGraphicsDropShadowEffect,
)
from PyQt5.QtGui import QColor, QIcon
from qfluentwidgets import FluentIcon as FIF


class SearchBarWithHistory(QWidget):
    search_signal = pyqtSignal(str)
    history_changed = pyqtSignal()

    def __init__(self, max_history=10, parent=None):
        super().__init__(parent)
        self._max_history = max_history
        self._history = []
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_search)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._search_container = QWidget()
        self._search_container.setObjectName("SearchContainer")
        self._search_container.setStyleSheet("""
            #SearchContainer {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 8px;
            }
            #SearchContainer:focus-within {
                border-color: #3b82f6;
            }
        """)
        search_layout = QHBoxLayout(self._search_container)
        search_layout.setContentsMargins(8, 4, 8, 4)
        search_layout.setSpacing(8)

        self._search_icon = QLabel()
        self._search_icon.setText(
            f'<img src="{FIF.SEARCH.path}" width="16" height="16"/>'
        )
        search_layout.addWidget(self._search_icon)

        self._line_edit = QLineEdit()
        self._line_edit.setObjectName("SearchLineEdit")
        self._line_edit.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #f0f6fc;
                font-size: 14px;
            }
            QLineEdit::placeholder {
                color: #6b7280;
            }
        """)
        self._line_edit.setPlaceholderText("搜索插件...")
        self._line_edit.textChanged.connect(self._on_text_changed)
        self._line_edit.returnPressed.connect(self._on_return_pressed)
        search_layout.addWidget(self._line_edit, 1)

        self._clear_btn = QPushButton("×")
        self._clear_btn.setFixedSize(20, 20)
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6b7280;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #f0f6fc;
            }
        """)
        self._clear_btn.hide()
        self._clear_btn.clicked.connect(self._on_clear)
        search_layout.addWidget(self._clear_btn)

        self._history_popup = QListWidget(self._search_container)
        self._history_popup.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self._history_popup.setAttribute(Qt.WA_TranslucentBackground)
        self._history_popup.setStyleSheet("""
            QListWidget {
                background: #1a1a1a;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item {
                color: #f0f6fc;
                padding: 8px 12px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: #21262d;
            }
            QListWidget::item:selected {
                background: #3b82f6;
            }
        """)
        self._history_popup.itemClicked.connect(self._on_history_item_clicked)
        self._history_popup.hide()

        shadow = QGraphicsDropShadowEffect(self._history_popup)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self._history_popup.setGraphicsEffect(shadow)

        layout.addWidget(self._search_container)

        self._line_edit.installEventFilter(self)

    def _on_text_changed(self, text):
        self._clear_btn.setVisible(bool(text))
        self._debounce_timer.start(300)

    def _emit_search(self):
        text = self._line_edit.text().strip()
        if text:
            self.search_signal.emit(text)

    def _on_return_pressed(self):
        self._debounce_timer.stop()
        text = self._line_edit.text().strip()
        if text:
            self._add_to_history(text)
            self._hide_history()
            self.search_signal.emit(text)

    def _on_clear(self):
        self._line_edit.clear()
        self._line_edit.setFocus()
        self._hide_history()

    def _show_history(self):
        if not self._history:
            return
        self._history_popup.clear()
        for item_text in self._history[: self._max_history]:
            item = QListWidgetItem(item_text)
            self._history_popup.addItem(item)
        self._history_popup.show()
        self._resize_history_popup()

    def _hide_history(self):
        self._history_popup.hide()

    def _resize_history_popup(self):
        width = self._search_container.width()
        self._history_popup.setFixedWidth(width)
        count = min(len(self._history), self._max_history)
        height = count * 40 + 8
        pos = self._search_container.mapToGlobal(
            self._search_container.rect().bottomLeft()
        )
        self._history_popup.move(pos)
        self._history_popup.setFixedHeight(height)

    def eventFilter(self, obj, event):
        if obj == self._line_edit and event.type() == 9:
            if self._line_edit.text() == "":
                self._show_history()
        return super().eventFilter(obj, event)

    def _on_history_item_clicked(self, item):
        text = item.text()
        self._line_edit.setText(text)
        self._hide_history()
        self._add_to_history(text)
        self.search_signal.emit(text)

    def _add_to_history(self, text):
        if text in self._history:
            self._history.remove(text)
        self._history.insert(0, text)
        self._history = self._history[: self._max_history]
        self.history_changed.emit()

    def set_history(self, history):
        self._history = list(history)

    def get_history(self):
        return list(self._history)

    def clear_history(self):
        self._history = []
        self.history_changed.emit()

    def text(self):
        return self._line_edit.text()

    def setText(self, text):
        self._line_edit.setText(text)
