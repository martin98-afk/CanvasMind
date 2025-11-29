# -*- coding: utf-8 -*-
from datetime import datetime
import re
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt5.QtGui import QMouseEvent, QTextCursor
from PyQt5.QtWidgets import QTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QTextBrowser
from markdown import Markdown
from qfluentwidgets import (
    FluentIcon, ToolTipFilter, TransparentToolButton, CardWidget, CaptionLabel, TextBrowser
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
            content = md_text[start_idx + len(pattern_start):end_idx]
            parts.append(_render_think_block(content, completed=True))
            i = end_idx + len(pattern_end)
        else:
            content = md_text[start_idx + len(pattern_start):]
            parts.append(_render_think_block(content, completed=False))
            i = len(md_text)
    return ''.join(parts)


def _render_think_block(content: str, completed: bool = True) -> str:
    content = (content.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace('"', "&quot;"))
    status_text = "💡 思考开始" if completed else "🧠 正在思考..."
    end_text = "💡 思考结束" if completed else ""
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
    <summary style="
        cursor: pointer;
        color: #FFA500;
        font-weight: bold;
        list-style: none;
        outline: none;
    ">{end_text}</summary>
    <div>
</details>
'''


def _inject_context_links(md_text: str, allowed_keys) -> str:
    """将 [显示名](key) 转为可点击链接，仅当 key 在 allowed_keys 中"""

    def replacer(match):
        display_name = match.group(1)
        tool_key = match.group(2)
        if tool_key in allowed_keys:
            return f'<a href="context://{tool_key}" class="context-link">[{display_name}]({tool_key})</a>'
        else:
            return match.group(0)

    return re.sub(r'\[([^\[\]]+?)\]\(([^)\s]+)\)', replacer, md_text)


class StreamingTextEdit(QTextBrowser):  # 👈 关键：继承 QTextBrowser
    contextLinkClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
        )

        self.setStyleSheet("""
            QTextBrowser {
                font-size: 14px;
                color: white;
                background: transparent;
                border: none;
                padding: 4px 0;
                selection-background-color: #4A4A4A;
            }
            a.context-link {
                color: #FFA500;
                text-decoration: underline;
                cursor: pointer;
            }
            a.context-link:hover {
                color: #FFD700;
            }
            /* details 样式 ... */
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
        self._allowed_context_keys = set()
        self._current_html = ""  # 缓存 HTML（备用）

        self.anchorClicked.connect(self._on_anchor_clicked)

    # ✅ 关键：拦截 setSource，防止清空
    def setSource(self, url: QUrl):
        if url.toString().startswith("context://"):
            return  # 不加载，不请空
        super().setSource(url)

    def set_allowed_context_keys(self, keys):
        self._allowed_context_keys = set(keys or [])

    def _update_html(self):
        if not self._markdown_text.strip():
            html = ""
        else:
            safe_md = _sanitize_incomplete_markdown(self._markdown_text)
            safe_md = _inject_context_links(safe_md, self._allowed_context_keys)
            processed_md = _inject_think_cards(safe_md)

            try:
                md = get_markdown_instance()
                md.reset()
                html = md.convert(processed_md)
            except Exception:
                html = (self._markdown_text
                        .replace('&', '&amp;')
                        .replace('<', '&lt;')
                        .replace('>', '&gt;')
                        .replace('\n', '<br>'))

        self._current_html = html
        v_scroll = self.verticalScrollBar().value()
        self.setHtml(html)
        self.verticalScrollBar().setValue(v_scroll)

        if not self._streaming and self._width_locked:
            self._update_height()

    def _on_anchor_clicked(self, url: QUrl):
        href = url.toString()
        if href.startswith("context://"):
            tool_key = href[len("context://"):]
            self.contextLinkClicked.emit(tool_key)

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
            self.setMinimumHeight(max(self.height() + len(text) * 2, 20))
        self._schedule_html_update()

    def finish_streaming(self):
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
            self._html_timer.start(80)

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
    closed = pyqtSignal(str)
    doubleClicked = pyqtSignal(str)

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

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
        self.context_tags = tag_params or {}
        self.timestamp = timestamp or datetime.now().strftime('%H:%M')
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(2)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(6)

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

        button_container = QWidget(self)
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)
        # 增加卡片按钮，欢迎卡片没有按钮
        if self.role == "assistant":
            btn_specs = [
                (FluentIcon.COPY, "复制", lambda: self.copyRequested.emit(self.content_widget.get_plain_text())),
                (FluentIcon.SYNC, "重新生成", self.regenerateRequested.emit)
            ]
        elif self.role == "user":
            btn_specs = [
                (FluentIcon.COPY, "复制", lambda: self.copyRequested.emit(self.content_widget.get_plain_text())),
                (FluentIcon.DELETE, "删除", self.deleteRequested.emit),
            ]
        else:
            btn_specs = []

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
        # 增加引用上下文的标签
        if self.role == "user" and self.context_tags:
            tags_container = QWidget(self)
            tags_container.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
            tags_layout = QHBoxLayout(tags_container)
            tags_layout.setContentsMargins(0, 0, 0, 0)
            tags_layout.setSpacing(4)

            for key, (name, content, callback_params) in self.context_tags.items():
                tag = TagWidget(key, name)
                tag.doubleClicked.connect(
                    lambda k=key, cp=callback_params: self.parent.homepage.context_register.get_executor(k)(cp)
                )
                tags_layout.addWidget(tag)
            tags_layout.addStretch()
            main_layout.addWidget(tags_container)
            main_layout.addWidget(CardSeparator(self))

        self.content_widget = StreamingTextEdit(self)
        allowed_keys = list(self.context_tags.keys())
        self.content_widget.set_allowed_context_keys(allowed_keys)
        self.content_widget.contextLinkClicked.connect(self._on_context_link_clicked)
        main_layout.addWidget(self.content_widget)
        main_layout.addWidget(CardSeparator(self))
        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {bg_color};
                border: 1px solid {'#4A5568' if self.role == 'user' else '#334155'};
                border-radius: 8px;
            }}
        """)
        self._update_content_width()

    def _update_content_width(self):
        margin = 80
        content_width = max(100, self.parent.width() - margin) if self.parent else 100
        self.content_widget.setFixedWidth(content_width)

    def update_content(self, new_content: str):
        self.content_widget.append_chunk(new_content)

    def finish_streaming(self):
        self.content_widget.finish_streaming()

    def _on_context_link_clicked(self, tool_key: str):
        """处理 [显示名](tool_key) 的点击事件"""
        print(f"点击了 {tool_key}")
        if tool_key in self.context_tags:
            name, content, callback_params = self.context_tags[tool_key]
            executor = self.parent.homepage.context_register.get_executor(tool_key)
            if executor:
                executor(callback_params)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_content_width()


def create_welcome_card(parent=None) -> MessageCard:
    """生成一个说明当前大模型功能的欢迎卡片"""
    # 欢迎语 Markdown 内容（支持你已实现的 <think>、context 链接、表格、代码块等）
    welcome_md = """\
你好！我是你的大模型助手，当前支持以下功能：

- ✅ **多模态输入**：支持通过 Base64 传递图像，启用视觉识别能力。
- ✅ **流式对话**：逐字生成，响应流畅，类似 ChatGPT 的体验。
- ✅ **上下文增强**：可插入画布节点、组件信息、全局变量等上下文（点击下方 `[...]` 选择）。
- ✅ **结构化输出**：支持 Markdown 表格、代码块、列表等格式。
- ✅ **上下文联动**：点击 `[变量名](key)` 可直接在画布中定位或操作对应节点。
- ✅ **深色主题 & 流畅交互**：界面适配 Fluent Design，支持停止生成、复制、重试等操作。

你可以随时：
- 输入文本开始对话；
- 点击输入框旁的 ➕ 按钮添加上下文；
- 在生成过程中点击“停止”中断响应。

祝你使用愉快！✨
"""

    # 创建助手角色的欢迎卡片
    card = MessageCard(role="system", timestamp="就绪", parent=parent)
    card.update_content(welcome_md)
    card.finish_streaming()  # 立即渲染，不流式
    return card
