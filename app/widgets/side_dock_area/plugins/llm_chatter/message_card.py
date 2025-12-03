# -*- coding: utf-8 -*-
import base64
import re
from datetime import datetime
from html import escape

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QApplication
)
from markdown import Markdown
from qfluentwidgets import (
    FluentIcon, ToolTipFilter, TransparentToolButton,
    CardWidget, CaptionLabel, InfoBar, InfoBarPosition
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

# 可选：如果你的项目有 ContextRegistry，保留；否则注释
try:
    from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextRegistry
except ImportError:
    ContextRegistry = None

# ======== Markdown 实例 ========
_md_instance = None


def get_markdown_instance():
    global _md_instance
    if _md_instance is None:
        _md_instance = Markdown(
            extensions=['fenced_code', 'nl2br', 'tables'],
            output_format='html5'
        )
    return _md_instance


# ======== Web 专用：代码块增强（使用 Pygments + 完整 CSS）========
def _wrap_code_blocks_with_copy_button_web(html: str) -> str:
    def replacer(match):
        lang = (match.group(1) or "").replace("language-", "").strip()
        code_content_raw = match.group(2) or ""

        try:
            copy_text = code_content_raw.replace("&lt;", "<") \
                .replace("&gt;", ">") \
                .replace("&amp;", "&") \
                .replace("&#39;", "'") \
                .replace("&quot;", '"')
        except:
            copy_text = code_content_raw

        b64_copy = base64.b64encode(copy_text.encode('utf-8')).decode('ascii')

        # —————— 关键：我们自己生成表格，不依赖 Pygments 行号 ——————
        try:
            from pygments import highlight
            from pygments.lexers import get_lexer_by_name, TextLexer
            from pygments.formatters import HtmlFormatter

            lexer = get_lexer_by_name(lang, stripall=False) if lang else TextLexer()
            # 注意：这里禁用 linenos！我们自己加
            formatter = HtmlFormatter(
                style='dracula',
                linenos=False,  # ← 关键：关闭 Pygments 行号
                noclasses=True,
                cssclass='code-block',
                prestyles='margin:0; padding:0; background:transparent; font-family: Consolas, monospace; font-size:13px; color:#D4D4D4;'
            )
            highlighted_code = highlight(copy_text, lexer, formatter)
        except Exception:
            # fallback：直接 escape
            highlighted_code = f'<pre style="margin:0; padding:0; background:transparent; font-family: Consolas, monospace; font-size:13px; color:#D4D4D4;">{escape(copy_text)}</pre>'

        # —————— 手动构造带行号的表格 ——————
        lines = copy_text.splitlines() or [""]
        # 生成行号列
        max_line = len(str(len(lines)))
        line_numbers_html = "\n".join(
            f'<td class="lineno" data-line="{i + 1}">{str(i + 1).rjust(max_line)}</td>'
            for i in range(len(lines))
        )
        # 代码列（从 highlighted_code 中提取内容）
        # Pygments 输出如：<div class="code-block"><pre>...</pre></div>
        # 我们提取 <pre> 内容，并按行拆分
        try:
            # 尝试从 Pygments 结果提取代码行
            import re as preg
            pre_match = preg.search(r'<pre[^>]*>(.*?)</pre>', highlighted_code, preg.DOTALL)
            if pre_match:
                inner_html = pre_match.group(1)
                code_lines = inner_html.split('\n')
                # 确保行数一致
                if len(code_lines) < len(lines):
                    code_lines.extend([''] * (len(lines) - len(code_lines)))
            else:
                code_lines = [escape(line) for line in lines]
        except:
            code_lines = [escape(line) for line in lines]

        code_lines_html = "\n".join(
            f'<td class="code-line">{line}</td>' for line in code_lines
        )

        # 构造表格
        table_rows = "\n".join(
            f'<tr>{line_numbers_html.splitlines()[i]}{code_lines_html.splitlines()[i]}</tr>'
            for i in range(len(lines))
        )

        table_html = f'''
        <table class="code-table">
            <tbody>
                {table_rows}
            </tbody>
        </table>
        '''

        # —————— 外层容器 ——————
        code_container_padding = "10px" if not lang else "28px 10px 10px 10px"

        return f'''
    <div style="
        position: relative;
        margin: 16px 0;
        background: #1E1E1E;
        border: 1px solid #3A3F47;
        border-radius: 6px;
        overflow-x: auto;   /* 只在这里启用横向滚动 */
        overflow-y: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        font-family: Consolas, monospace;
        font-size: 13px;
    ">
        {f'<div style="position:absolute; top:6px; left:8px; background:#333; color:#FFA500; padding:1px 6px; border-radius:3px; font-size:11px; z-index:10; pointer-events:none;">{lang}</div>' if lang else ''}

        <button type="button" data-copy="{b64_copy}" style="
            position: absolute;
            top: 6px;
            right: 6px;
            background: rgba(51,51,51,0.9);
            color: #FFA500;
            padding: 1px 5px;
            border-radius: 3px;
            text-decoration: none;
            font-size: 11px;
            cursor: pointer;
            opacity: 0.8;
            border: none;
            outline: none;
            z-index: 10;
        " onmouseenter="this.style.opacity='1'" onmouseleave="this.style.opacity='0.8'">📋</button>

        <div style="padding: {code_container_padding};">
            {table_html}
        </div>
    </div>
    '''
    pattern = r'<pre><code(?:\s+class="([^"]*)")?>(.*?)</code></pre>'
    return re.sub(pattern, replacer, html, flags=re.DOTALL)

# ======== 辅助函数（保持不变）========
def _sanitize_incomplete_markdown(md_text: str) -> str:
    if not md_text.strip():
        return md_text
    if md_text.count('```') % 2 == 1:
        md_text += '\n```'
    if not md_text.endswith('\n'):
        md_text += '\n'
    return md_text


def _render_think_block(content: str, completed: bool = True) -> str:
    content = (content.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace('"', "&quot;"))
    status_text = "💡 思考过程" if completed else "🧠 正在思考..."

    open_attr = ' open' if not completed else ''

    return f'''
<details{open_attr} class="think-block" style="
    margin: 12px 0;
    background: #252D38;
    border: 1px solid #3A3F47;
    border-radius: 8px;
    padding: 12px;
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
    <div style="margin-top: 8px; white-space: pre-wrap;">{content}</div>
</details>
'''


def _inject_think_cards(md_text: str, completed: bool = True) -> str:
    parts = []
    i = 0
    while i < len(md_text):
        start_idx = md_text.find("<think>", i)
        if start_idx == -1:
            parts.append(md_text[i:])
            break
        parts.append(md_text[i:start_idx])
        end_idx = md_text.find("</think>", start_idx + len("<think>"))
        if end_idx != -1:
            content = md_text[start_idx + len("<think>"):end_idx]
            parts.append(_render_think_block(content, completed=True))
            i = end_idx + len("</think>")
        else:
            content = md_text[start_idx + len("<think>"):]
            parts.append(_render_think_block(content, completed=False))
            i = len(md_text)
    return ''.join(parts)


def _inject_context_links(md_text: str, allowed_keys) -> str:
    def replacer(match):
        display_name = match.group(1)
        tool_key = match.group(2)
        if tool_key in allowed_keys:
            return f'<a href="context://{tool_key}" class="context-link">[{display_name}]({tool_key})</a>'
        else:
            return match.group(0)

    return re.sub(r'\[([^\[\]]+?)\]\(([^)\s]+)\)', replacer, md_text)


# ======== 自定义 WebEnginePage：监听 console.log ========
class ConsoleMonitorPage(QWebEnginePage):
    copyRequested = pyqtSignal(str)
    heightReported = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        msg = message.strip()
        if msg.startswith("pywebview_copy_b64:"):
            b64_str = msg[len("pywebview_copy_b64:"):]
            try:
                text = base64.b64decode(b64_str).decode('utf-8')
                self.copyRequested.emit(text)
            except Exception:
                pass  # 安静失败
        elif msg.startswith("pywebview_height:"):
            try:
                h = int(msg[len("pywebview_height:"):])
                self.heightReported.emit(h)
            except ValueError:
                pass
        # else: 静默其他日志


# ======== 核心：CodeWebViewer（基于 QWebEngineView）========
class CodeWebViewer(QWebEngineView):
    contextLinkClicked = pyqtSignal(str)
    contentHeightChanged = pyqtSignal(int)
    copyRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._markdown_text = ""
        self._streaming = True
        self._allowed_keys = set()
        self._html_timer = None
        self._completed = False

        # 使用自定义 Page 以捕获 console.log
        self._page = ConsoleMonitorPage(self)
        self.setPage(self._page)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.page().setBackgroundColor(Qt.transparent)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumHeight(1)

        # 连接信号
        self._page.copyRequested.connect(self.copyRequested)
        self._page.heightReported.connect(self._on_js_height_reported)

        self.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok: bool):
        if ok:
            QTimer.singleShot(100, self._request_content_height)

    def _on_js_height_reported(self, height: int):
        self.contentHeightChanged.emit(height)

    def set_allowed_context_keys(self, keys):
        self._allowed_keys = set(keys or [])

    def _render(self):
        if not self._markdown_text.strip():
            html_body = ""
        else:
            safe_md = _sanitize_incomplete_markdown(self._markdown_text)
            safe_md = _inject_context_links(safe_md, self._allowed_keys)
            processed_md = _inject_think_cards(safe_md, completed=self._completed)

            try:
                md = get_markdown_instance()
                md.reset()
                html_body = md.convert(processed_md)
                html_body = _wrap_code_blocks_with_copy_button_web(html_body)
            except Exception:
                html_body = (self._markdown_text
                             .replace('&', '&amp;')
                             .replace('<', '&lt;')
                             .replace('>', '&gt;')
                             .replace('\n', '<br>'))

        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                html, body {{
                    background: transparent !important;
                    color: white;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                    font-size: 14px;
                    line-height: 1.5;
                    margin: 0;
                    padding: 4px 0;
                    overflow: hidden;
                    height: auto;
                    min-height: 1px;
                }}
                body > * {{
                    max-width: 100%;
                    overflow-wrap: break-word;
                }}
                a.context-link {{
                    color: #FFA500;
                    text-decoration: underline;
                    cursor: pointer;
                }}
                pre, code {{
                    white-space: pre-wrap;
                    word-break: break-all;
                }}
                details {{
                    margin: 12px 0;
                    background: #252D38;
                    border: 1px solid #3A3F47;
                    border-radius: 8px;
                    padding: 12px;
                    font-size: 13px;
                    color: #CCCCCC;
                }}
                summary {{
                    color: #FFA500;
                    font-weight: bold;
                    cursor: pointer;
                    outline: none;
                    list-style: none;
                }}
                button[data-copy] {{
                    z-index: 10;
                }}
                .code-table {{
                    border-collapse: collapse;
                    width: auto;
                    min-width: 100%;
                    white-space: nowrap;
                    margin: 0;
                    font-family: Consolas, monospace;
                    font-size: 13px;
                    color: #D4D4D4;
                }}
                .code-table td {{
                    padding: 0;
                    vertical-align: top;
                    border: none;
                }}
                .code-table .lineno {{
                    user-select: none;
                    width: 35px !important;          /* ← 固定宽度 */
                    -webkit-user-select: none;
                    color: #666 !important;
                    padding-right: 4px !important;
                    border-right: 1px solid #444444 !important;
                    text-align: right;
                    white-space: nowrap;
                    min-width: 2.2em;
                }}
                .code-table .code-line {{
                    white-space: pre;
                    padding-left: 8px;
                    background: transparent !important;
                }}
                .highlight {{
                    display: block !important;
                    overflow-x: auto !important;
                    overflow-y: hidden !important;
                    white-space: nowrap !important;  /* 作用于整个 table */
                }}
                .highlight .code {{
                    padding-left: 8px !important;
                }}
                .highlight {{
                    overflow-x: auto;
                    scrollbar-width: thin; /* Firefox */
                    scrollbar-color: #555 #2a2a2a; /* thumb / track */
                }}
                .highlight::-webkit-scrollbar {{
                    height: 8px;
                }}
                .highlight::-webkit-scrollbar-thumb {{
                    background: #555;
                    border-radius: 4px;
                }}
                .highlight::-webkit-scrollbar-track {{
                    background: #2a2a2a;
                }}
            </style>
        </head>
        <body>
            {html_body}
            <script>
                document.addEventListener('click', function(e) {{
                    if (e.target.matches('button[data-copy]')) {{
                        e.preventDefault();
                        const b64 = e.target.getAttribute('data-copy');
                        const text = atob(b64);
                        // 优先尝试标准 API
                        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {{
                            navigator.clipboard.writeText(text).catch(() => {{
                                console.log('pywebview_copy_b64:' + b64);
                            }});
                        }} else {{
                            console.log('pywebview_copy_b64:' + b64);
                        }}
                    }}
                }});

                function reportHeight() {{
                    const h = document.body.scrollHeight;
                    console.log('pywebview_height:' + h);
                }}

                document.addEventListener('DOMContentLoaded', function() {{
                    setTimeout(reportHeight, 100);

                    document.querySelectorAll('details.think-block').forEach(el => {{
                        el.addEventListener('toggle', () => setTimeout(reportHeight, 20));
                    }});
                }});

                // 暴露接口（备用）
                window.pywebview = {{
                    reportHeight: reportHeight
                }};
            </script>
        </body>
        </html>
        """
        self.setHtml(full_html, QUrl(""))
        QTimer.singleShot(100, self._request_content_height)

    def _request_content_height(self):
        self.page().runJavaScript("reportHeight();")

    def append_chunk(self, text: str):
        if not text:
            return
        self._markdown_text += text
        self._schedule_render()

    def finish_streaming(self):
        self._streaming = False
        self._completed = True
        self._render()

    def _schedule_render(self):
        if self._html_timer is None:
            self._html_timer = QTimer()
            self._html_timer.setSingleShot(True)
            self._html_timer.timeout.connect(self._render)
        if not self._html_timer.isActive():
            self._html_timer.start(80)

    def get_plain_text(self) -> str:
        return self._markdown_text

    def _handle_navigation(self, url: QUrl, _type, _is_main_frame):
        scheme = url.scheme()
        if scheme == "context":
            self.contextLinkClicked.emit(url.host())
            return False
        return True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 宽度变化时，重新计算高度
        QTimer.singleShot(100, self._request_content_height)

    def wheelEvent(self, event: QWheelEvent):
        # 获取滚动条（向上找 QScrollArea）
        scroll_area = self.parent().parent.chat_scroll_area
        if scroll_area:
            vbar = scroll_area.verticalScrollBar()
            if vbar and vbar.minimum() != vbar.maximum():
                # 让外部 ScrollArea 滚动
                delta = event.angleDelta().y()
                vbar.setValue(vbar.value() - delta // 2)
                event.accept()  # 标记事件已处理
                return

        super().wheelEvent(event)


# ======== MessageCard（适配 WebViewer）========
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
        main_layout.setSizeConstraint(QVBoxLayout.SetMinAndMaxSize)  # 关键！

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

        if self.role == "user" and self.context_tags:
            tags_container = QWidget(self)
            tags_container.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
            tags_layout = QHBoxLayout(tags_container)
            tags_layout.setContentsMargins(0, 0, 0, 0)
            tags_layout.setSpacing(4)

            for key, (name, content, callback_params) in self.context_tags.items():
                tag = TagWidget(key, name)
                if self.parent and hasattr(self.parent, 'homepage'):
                    tag.doubleClicked.connect(
                        lambda k=key, cp=callback_params: self.parent.homepage.context_register.get_executor(k)(cp)
                    )
                tags_layout.addWidget(tag)
            tags_layout.addStretch()
            main_layout.addWidget(tags_container)
            main_layout.addWidget(CardSeparator(self))

        self.content_widget = CodeWebViewer(self)
        allowed_keys = list(self.context_tags.keys())
        self.content_widget.set_allowed_context_keys(allowed_keys)
        self.content_widget.contextLinkClicked.connect(self._on_context_link_clicked)
        self.content_widget.contentHeightChanged.connect(self._on_content_height_changed)
        self.content_widget.copyRequested.connect(self._on_internal_copy)
        main_layout.addWidget(self.content_widget)
        main_layout.addWidget(CardSeparator(self))

        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {bg_color};
                border: 1px solid {'#4A5568' if self.role == 'user' else '#334155'};
                border-radius: 8px;
            }}
        """)

    def _on_internal_copy(self, text: str):
        QApplication.clipboard().setText(text)
        InfoBar.success(
            title='已复制',
            content='代码已复制到剪贴板',
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.parent
        )

    def _on_context_link_clicked(self, tool_key: str):
        if tool_key in self.context_tags:
            name, content, callback_params = self.context_tags[tool_key]
            if self.parent and hasattr(self.parent, 'homepage'):
                executor = self.parent.homepage.context_register.get_executor(tool_key)
                if executor:
                    executor(callback_params)

    def _on_content_height_changed(self, height):
        # 强制更新自身尺寸
        self.content_widget.setMinimumHeight(max(1, height))
        self.updateGeometry()
        QTimer.singleShot(20, lambda: self.parentWidget().updateGeometry() if self.parentWidget() else None)

    def update_content(self, new_content: str):
        self.content_widget.append_chunk(new_content)

    def finish_streaming(self):
        self.content_widget.finish_streaming()

    def wheelEvent(self, event: QWheelEvent):
        # 获取滚动条（向上找 QScrollArea）
        scroll_area = self.parent.chat_scroll_area
        if scroll_area:
            vbar = scroll_area.verticalScrollBar()
            if vbar and vbar.minimum() != vbar.maximum():
                # 让外部 ScrollArea 滚动
                delta = event.angleDelta().y()
                vbar.setValue(vbar.value() - delta // 2)
                event.accept()  # 标记事件已处理
                return

        super().wheelEvent(event)


def create_welcome_card(parent=None) -> MessageCard:
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

    card = MessageCard(role="welcome", timestamp="就绪", parent=parent)
    card.update_content(welcome_md)
    card.finish_streaming()
    return card