# -*- coding: utf-8 -*-
from datetime import datetime

import markdown
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)
from markdown import Markdown
from qfluentwidgets import (
    FluentIcon, ToolTipFilter, ToolButton, CardWidget, TransparentToolButton
)
# 可复用的 Markdown 实例
_md_instance = None

def get_markdown_instance():
    global _md_instance
    if _md_instance is None:
        _md_instance = Markdown(
            extensions=['fenced_code', 'nl2br', 'tables'],
            output_format='html5'
        )
    return _md_instance

def _sanitize_incomplete_markdown(md_text: str) -> str:
    """对不完整的 Markdown 做容错处理，临时闭合未闭合结构"""
    if not md_text.strip():
        return md_text

    # 1. 处理行内代码 `
    backtick_count = md_text.count('`')
    if backtick_count % 2 == 1:
        md_text += '`'  # 临时闭合

    # 2. 处理粗体/斜体 ** 和 __
    # 简化处理：只处理 **（更常见），避免复杂状态机
    star_count = md_text.count('**')
    if star_count % 2 == 1:
        md_text += '**'

    underscore_count = md_text.count('__')
    if underscore_count % 2 == 1:
        md_text += '__'

    # 3. 处理 fenced code block ```
    code_block_count = md_text.count('```')
    if code_block_count % 2 == 1:
        md_text += '\n```'  # 闭合代码块

    # 4. 确保末尾有换行（避免最后一行被吞）
    if not md_text.endswith('\n'):
        md_text += '\n'

    return md_text


class StreamingTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAcceptRichText(True)          # ✅ 改为 True
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
        self._width_locked = False
        self._pending_update = False
        self._markdown_text = ""              # 存储原始 Markdown
        self._cursor_position = 0             # 可选：用于保持滚动位置（进阶）

    def setFixedWidth(self, w):
        if w <= 1:
            return
        super().setFixedWidth(w)
        self._width_locked = True
        self._schedule_height_update()

    def append_chunk(self, text: str):
        if not text:
            return
        # 追加到 Markdown 源
        self._markdown_text += text
        # 防抖更新 HTML（避免频繁重绘）
        self._schedule_html_update()

    def _schedule_html_update(self):
        if not hasattr(self, '_html_timer'):
            self._html_timer = QTimer()
            self._html_timer.setSingleShot(True)
            self._html_timer.timeout.connect(self._update_html)
        self._html_timer.start(10)  # 10ms 延迟，平衡流畅性与性能

    def _update_html(self):
        if not self._markdown_text.strip():
            self.setHtml("")
            return

        # ✅ 容错处理：补全不完整语法
        safe_md = _sanitize_incomplete_markdown(self._markdown_text)

        try:
            md = get_markdown_instance()
            md.reset()  # 清理状态（重要！）
            html = md.convert(safe_md)
        except Exception:
            # fallback: 转义后显示（保留换行）
            html = self._markdown_text.replace('&', '&amp;').replace('<', '<').replace('>', '>').replace('\n', '<br>')

        # 恢复滚动
        v_scroll = self.verticalScrollBar().value()
        self.setHtml(html)
        self.verticalScrollBar().setValue(v_scroll)

        if self._width_locked:
            self._schedule_height_update()

    def get_plain_text(self) -> str:
        # 返回原始 Markdown（不是 HTML）
        return self._markdown_text

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

        self.document().setTextWidth(available_width)
        doc_height = int(self.document().size().height())
        total_height = doc_height + margins.top() + margins.bottom() + 8
        self.setFixedHeight(max(total_height, 20))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._width_locked = True
        self._schedule_height_update()


class MessageCard(CardWidget):
    deleteRequested = pyqtSignal()
    copyRequested = pyqtSignal(str)
    regenerateRequested = pyqtSignal()

    def __init__(self, role: str, timestamp: str = None, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.role = role
        self.timestamp = timestamp or datetime.now().strftime('%H:%M')
        self.setup_ui()

    def setup_ui(self):
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
                (FluentIcon.SYNC, "重新生成", self.regenerateRequested.emit)
            ]:
                btn = TransparentToolButton(icon, self)
                btn.setToolTip(tooltip)
                btn.clicked.connect(slot)
                btn.setFixedSize(24, 24)
                btn.installEventFilter(ToolTipFilter(btn))
                button_layout.addWidget(btn)
        else:
            for icon, tooltip, slot in [
                (FluentIcon.COPY, "复制", lambda: self.copyRequested.emit(self.content_widget.get_plain_text())),
                (FluentIcon.DELETE, "删除", self.deleteRequested.emit),
            ]:
                btn = TransparentToolButton(icon, self)
                btn.setToolTip(tooltip)
                btn.clicked.connect(slot)
                btn.setFixedSize(24, 24)
                btn.installEventFilter(ToolTipFilter(btn))
                button_layout.addWidget(btn)

        top_layout.addWidget(button_container)
        main_layout.addLayout(top_layout)

        # Content widget
        self.content_widget = StreamingTextEdit(self)
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