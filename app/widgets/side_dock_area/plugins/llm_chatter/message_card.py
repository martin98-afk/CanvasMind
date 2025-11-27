# -*- coding: utf-8 -*-
from datetime import datetime
import re
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from markdown import Markdown
from qfluentwidgets import (
    FluentIcon, ToolTipFilter, TransparentToolButton, CardWidget, CaptionLabel
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextRegistry

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
    """简化容错：仅处理代码块和换行"""
    if not md_text.strip():
        return md_text
    if md_text.count('```') % 2 == 1:
        md_text += '\n```'
    if not md_text.endswith('\n'):
        md_text += '\n'
    return md_text


def _inject_think_cards(md_text: str) -> str:
    """支持闭合和未闭合的 <think> 标签"""
    # 先处理已闭合的
    parts = []
    i = 0
    pattern_start = "<think>"
    pattern_end = "</think>"
    while i < len(md_text):
        start_idx = md_text.find(pattern_start, i)
        if start_idx == -1:
            parts.append(md_text[i:])
            break

        parts.append(md_text[i:start_idx])
        end_idx = md_text.find(pattern_end, start_idx + len(pattern_start))
        if end_idx != -1:
            # 已闭合
            content = md_text[start_idx + len(pattern_start):end_idx]
            parts.append(_render_think_block(content, completed=True))
            i = end_idx + len(pattern_end)
        else:
            # 未闭合：从 start_idx 到末尾都是思考内容
            content = md_text[start_idx + len(pattern_start):]
            parts.append(_render_think_block(content, completed=False))
            i = len(md_text)  # 结束
    return ''.join(parts)


def _render_think_block(content: str, completed: bool = True) -> str:
    # 转义 HTML
    content = (content.replace("&", "&amp;")
                      .replace("<", "<")
                      .replace(">", ">")
                      .replace('"', "&quot;"))
    status_text = "💡 思考过程" if completed else "🧠 正在思考..."
    end_tag = f"""<summary style="
    cursor: pointer;
    color: #FFA500;
    font-weight: bold;
    list-style: none;
    outline: none;
">{status_text}</summary>""" if completed else ""
    return f'''
<details style="
    margin: 10px 0;
    background: #252D38;
    border: 1px solid #3A3F47;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
    color: #CCCCCC;
">
    <summary style="
        cursor: pointer;
        color: #FFA500;
        font-weight: bold;
        list-style: none;
        outline: none;
    ">{status_text}</summary>
    <div style="margin-top: 6px; white-space: pre-wrap;">{content}</div>
    <div>
    {end_tag}
</details>
'''

class StreamingTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAcceptRichText(True)
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
            /* 支持 <details> 折叠样式 */
            details {
                margin: 10px 0;
                background: #252D38;
                border: 1px solid #3A3F47;
                border-radius: 6px;
                padding: 10px;
            }
            summary {
                color: #FFA500;
                font-weight: bold;
                cursor: pointer;
                outline: none;
            }
            summary::-webkit-details-marker {
                display: none;
            }
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumHeight(20)
        self._width_locked = False
        self._pending_update = False
        self._markdown_text = ""
        self._streaming = True
        self._html_timer = None

    def setFixedWidth(self, w):
        if w <= 1:
            return
        super().setFixedWidth(w)
        self._width_locked = True
        if not self._streaming:
            self._schedule_height_update()

    def append_chunk(self, text: str):
        if not text:
            return
        self._markdown_text += text
        if self._streaming:
            # 粗略扩容，避免频繁重算
            self.setMinimumHeight(max(self.height() + len(text) * 2, 20))
        self._schedule_html_update()

    def finish_streaming(self):
        """必须在流结束时调用"""
        self._streaming = False
        self._update_html()
        if self._width_locked:
            self._update_height()

    def _schedule_html_update(self):
        if self._html_timer is None:
            self._html_timer = QTimer()
            self._html_timer.setSingleShot(True)
            self._html_timer.timeout.connect(self._update_html)
        if not self._html_timer.isActive():
            self._html_timer.start(80)  # 防抖 80ms

    def _update_html(self):
        if not self._markdown_text.strip():
            self.document().setHtml("")
            return

        safe_md = _sanitize_incomplete_markdown(self._markdown_text)
        processed_md = _inject_think_cards(safe_md)

        try:
            md = get_markdown_instance()
            md.reset()
            html = md.convert(processed_md)
        except Exception:
            html = self._markdown_text.replace('&', '&amp;').replace('<', '<').replace('>', '>').replace('\n', '<br>')

        v_scroll = self.verticalScrollBar().value()
        self.document().setHtml(html)
        self.verticalScrollBar().setValue(v_scroll)

        if not self._streaming and self._width_locked:
            self._update_height()

    def get_plain_text(self) -> str:
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
        if self._width_locked:
            self._schedule_height_update()


class TagWidget(CardWidget):
    closed = pyqtSignal(str)      # 发出 key
    doubleClicked = pyqtSignal(str)  # 新增：双击信号

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)  # 提示可交互

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        self.label = CaptionLabel(text, self)

        layout.addWidget(self.label)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.key)
        super().mouseDoubleClickEvent(event)


class MessageCard(CardWidget):
    deleteRequested = pyqtSignal()
    copyRequested = pyqtSignal(str)
    regenerateRequested = pyqtSignal()

    def __init__(self, role: str, timestamp: str = None, parent=None, tag_params: dict = None):
        super().__init__(parent)
        self.parent = parent
        self.role = role
        self.context_tags = tag_params
        self.timestamp = timestamp or datetime.now().strftime('%H:%M')
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(2)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(6)

        # Avatar 和名称颜色区分
        if self.role == "user":
            avatar_text = "👤"
            avatar_color = "#63B3ED"
            name = "用户"
            name_color = "#63B3ED"
            bg_color = "#2A2A2A"
        else:
            avatar_text = "🤖"
            avatar_color = "#FFA500"
            name = "大模型助手"
            name_color = "#FFA500"
            bg_color = "#1E293B"

        avatar_label = QLabel(avatar_text, self)
        avatar_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {avatar_color};")
        avatar_label.setFixedSize(28, 28)
        avatar_label.setAlignment(Qt.AlignCenter)

        name_label = QLabel(name, self)
        name_label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {name_color};")

        top_layout.addWidget(avatar_label)
        top_layout.addWidget(name_label)

        if self.role == "assistant":
            time_label = QLabel(self.timestamp, self)
            time_label.setStyleSheet("font-size: 12px; color: #B0B0B0;")
            top_layout.addWidget(time_label)

        top_layout.addStretch()

        # 按钮容器
        button_container = QWidget(self)
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)

        if self.role == "assistant":
            btn_specs = [
                (FluentIcon.COPY, "复制", lambda: self.copyRequested.emit(self.content_widget.get_plain_text())),
                (FluentIcon.SYNC, "重新生成", self.regenerateRequested.emit)
            ]
        else:
            btn_specs = [
                (FluentIcon.COPY, "复制", lambda: self.copyRequested.emit(self.content_widget.get_plain_text())),
                (FluentIcon.DELETE, "删除", self.deleteRequested.emit),
            ]

        for icon, tooltip, slot in btn_specs:
            btn = TransparentToolButton(icon, self)
            btn.setToolTip(tooltip)
            btn.clicked.connect(slot)
            btn.setFixedSize(24, 24)
            btn.installEventFilter(ToolTipFilter(btn))
            button_layout.addWidget(btn)

        top_layout.addWidget(button_container)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(CardSeparator(self))
        if self.role == "user" and self.context_tags:

            tags_container = QWidget(self)
            tags_container.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
            tags_layout = QHBoxLayout(tags_container)
            tags_layout.setContentsMargins(0, 0, 0, 0)
            tags_layout.setSpacing(4)

            for key, (name, content, callback_params) in self.context_tags.items():
                tag = TagWidget(key, name)
                tag.doubleClicked.connect(
                    lambda k=key, cp=callback_params: ContextRegistry.get_executor(k)(cp)
                )

                tags_layout.addWidget(tag)
            tags_layout.addStretch()
            tags_container.setVisible(True)
            tags_container.adjustSize()

            main_layout.addWidget(tags_container)
            main_layout.addWidget(CardSeparator(self))

        self.content_widget = StreamingTextEdit(self)
        main_layout.addWidget(self.content_widget)

        # 设置卡片背景（高对比度）
        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {bg_color};
                border: 1px solid {'#4A5568' if self.role == 'user' else '#334155'};
                border-radius: 8px;
            }}
        """)
        self._update_content_width()

    def _update_content_width(self):
        margin = 80  # 与 setContentsMargins(5,5,5,5) 对应（左右共 10，保守取 24）
        content_width = max(100, self.parent.width() - margin)
        self.content_widget.setFixedWidth(content_width)

    def update_content(self, new_content: str):
        self.content_widget.append_chunk(new_content)

    def finish_streaming(self):
        """暴露给外部调用，结束流式更新"""
        self.content_widget.finish_streaming()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_content_width()