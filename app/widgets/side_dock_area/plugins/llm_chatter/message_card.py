# -*- coding: utf-8 -*-
from datetime import datetime
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QTextEdit
)
from PyQt5.QtGui import QTextCursor
from qfluentwidgets import (
    FluentIcon, ToolTipFilter, ToolButton, CardWidget
)


class StreamingTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QTextEdit {
                font-size: 14px;
                color: white;
                background: transparent;
                border: none;
                padding: 4px 0;
                selection-background-color: #4A4A4A;
            }
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumHeight(20)
        self._document = self.document()
        self._width_locked = False
        self._pending_update = False

    def setFixedWidth(self, w):
        # 跳过无效宽度
        if w <= 1:
            return
        super().setFixedWidth(w)
        self._width_locked = True
        self._schedule_height_update()

    def append_chunk(self, text: str):
        if not text:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        # 注意：不调用 setTextCursor，避免选区跳动和潜在重绘

        if self._width_locked:
            self._schedule_height_update()

    def _schedule_height_update(self):
        if not self._pending_update:
            self._pending_update = True
            QTimer.singleShot(0, self._update_height)

    def _update_height(self):
        self._pending_update = False
        if not self._width_locked or self.width() <= 1:
            return

        margins = self.contentsMargins()
        available_width = self.width() - margins.left() - margins.right()
        if available_width <= 0:
            return

        # 关键：强制文档使用当前可用宽度重新布局
        self._document.setTextWidth(available_width)

        # 计算精确高度 + 安全余量（防止末尾行被裁）
        doc_height = int(self._document.size().height())
        total_height = doc_height + margins.top() + margins.bottom() + 8  # +8px 安全边距
        self.setFixedHeight(max(total_height, 20))

    def get_plain_text(self) -> str:
        return self.toPlainText()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._width_locked = True
        self._schedule_height_update()


class MessageCard(CardWidget):
    deleteRequested = pyqtSignal()
    copyRequested = pyqtSignal(str)
    regenerateRequested = pyqtSignal()

    def __init__(self, role: str, content: str, timestamp: str = None, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.role = role
        self.timestamp = timestamp or datetime.now().strftime('%H:%M')
        self.setup_ui(content)

    def setup_ui(self, content: str):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(2)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(0)

        # Avatar
        avatar_label = QLabel(self)
        avatar_text = "👤" if self.role == "user" else "🤖"
        avatar_color = "#FFFFFF" if self.role == "user" else "#4DA6FF"
        avatar_label.setText(avatar_text)
        avatar_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {avatar_color};")
        avatar_label.setFixedSize(28, 28)
        avatar_label.setAlignment(Qt.AlignCenter)

        # Name
        name = "用户" if self.role == "user" else "大模型助手"
        name_label = QLabel(name, self)
        name_label.setStyleSheet("font-size: 15px; font-weight: bold; color: white;")
        top_layout.addWidget(avatar_label)
        top_layout.addWidget(name_label)

        # Timestamp (assistant only)
        if self.role == "assistant":
            time_label = QLabel(self.timestamp, self)
            time_label.setStyleSheet("font-size: 12px; color: #AAAAAA;")
            top_layout.addWidget(time_label)

        top_layout.addStretch()

        # Buttons
        button_container = QWidget(self)
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)

        if self.role == "assistant":
            for icon, tooltip, slot in [
                (FluentIcon.COPY, "复制", lambda: self.copyRequested.emit(self.content_widget.get_plain_text())),
                (FluentIcon.SYNC, "重新生成", self.regenerateRequested.emit),
                (FluentIcon.DELETE, "删除", self.deleteRequested.emit),
            ]:
                btn = ToolButton(icon, self)
                btn.setToolTip(tooltip)
                btn.clicked.connect(slot)
                btn.setFixedSize(24, 24)
                btn.installEventFilter(ToolTipFilter(btn))
                button_layout.addWidget(btn)
        else:
            copy_btn = ToolButton(FluentIcon.COPY, self)
            copy_btn.setToolTip("复制")
            copy_btn.clicked.connect(lambda: self.copyRequested.emit(self.content_widget.get_plain_text()))
            copy_btn.setFixedSize(24, 24)
            copy_btn.installEventFilter(ToolTipFilter(copy_btn))
            button_layout.addWidget(copy_btn)

        top_layout.addWidget(button_container)
        main_layout.addLayout(top_layout)

        # Content widget
        self.content_widget = StreamingTextEdit(self)
        if content:
            self.content_widget.append_chunk(content)

        main_layout.addWidget(self.content_widget, 0)

        # Card background
        bg_color = "#2A2A2A" if self.role == "user" else "#1E1E1E"
        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {bg_color};
                border: 1px solid #444444;
                border-radius: 8px;
            }}
        """)

        # 初始设置宽度（防止首次 append 时宽度为 0）
        self._update_content_width()

    def _update_content_width(self):
        margin = 70  # 与 setContentsMargins(5,5,5,5) 对应（左右共 10，保守取 24）
        content_width = max(100, self.parent.width() - margin)
        self.content_widget.setFixedWidth(content_width)

    def update_content(self, new_content: str):
        self.content_widget.append_chunk(new_content)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_content_width()