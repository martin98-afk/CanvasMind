# -*- coding: utf-8 -*-
import base64
import re
import urllib
import time
import json
import uuid
from datetime import datetime
from html import escape

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl, QPoint
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
from qfluentwidgets.components.widgets.card_widget import CardSeparator, SimpleCardWidget

# 可选：如果你的项目有 ContextRegistry，保留；否则注释
try:
    from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextRegistry
except ImportError:
    ContextRegistry = None

# ======== Markdown 实例 ========
_md_instance = None
ACTION_COLOR_MAP = {
    "jump": "#FFA500",  # 橙色
    "create": "#9370DB",  # 皇家蓝
    "generate": "#32CD32",  # 石灰绿
    "ask": "#FF6347",  # 番茄红
    "view": "#4169E1",  # 中紫色
}
DEFAULT_COLOR = "#888888"  # 未知类型兜底色


def get_markdown_instance():
    global _md_instance
    if _md_instance is None:
        _md_instance = Markdown(
            extensions=['fenced_code', 'nl2br', 'tables'],
            output_format='html5',
            safe=False
        )
    return _md_instance


def _unwrap_code_blocks_with_context_links(md_text: str) -> str:
    def replacer(match):
        lang_part = match.group(1) or ""
        code_content = match.group(2)
        if re.search(r'\[[^\[\]]+\]\([^)\s]+\)', code_content) and lang_part not in ("python"):
            return code_content
        else:
            if lang_part:
                return f'```{lang_part}\n{code_content}```'
            else:
                return f'```\n{code_content}```'

    pattern = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
    return pattern.sub(replacer, md_text)


# ======== Web 专用：代码块增强 ========
def _wrap_code_blocks_with_copy_button_web(html: str) -> str:
    def replacer(match):
        lang = (match.group(1) or "").replace("language-", "").strip().lower()
        code_content_raw = match.group(2) or ""

        # --- Echarts ---
        if lang == 'echarts':
            chart_id = f"chart_{uuid.uuid4().hex}"
            try:
                json_content = code_content_raw.strip()
            except:
                json_content = "{}"
            # 注意：流式输出时，如果 JSON 不完整，echarts 会报错，我们让 JS 在渲染时吞掉错误
            return f'''
            <div class="echarts-wrapper" style="width: 100%; height: 300px; margin: 12px 0; border: 1px solid #3A3F47; border-radius: 8px; padding: 4px;">
                <div id="{chart_id}" class="echarts-div" style="width: 100%; height: 100%;" data-option="{escape(json_content)}"></div>
            </div>
            '''

        # --- Mermaid ---
        if lang == 'mermaid':
            return f'''
            <div class="mermaid" style="background: transparent; margin: 12px 0; overflow-x: auto;">
                {code_content_raw}
            </div>
            '''

        # --- 常规代码块 ---
        try:
            copy_text = code_content_raw.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace(
                "&#39;", "'").replace("&quot;", '"')
        except:
            copy_text = code_content_raw

        b64_copy = base64.b64encode(copy_text.encode('utf-8')).decode('ascii')

        # 简单处理：流式输出过程中，如果调用 Pygments 太慢可以考虑只用 HTML escape
        # 这里为了效果保留 Pygments，但要注意性能
        try:
            from pygments import highlight
            from pygments.lexers import get_lexer_by_name, TextLexer
            from pygments.formatters import HtmlFormatter
            lexer = get_lexer_by_name(lang, stripall=False) if lang else TextLexer()
            formatter = HtmlFormatter(style='dracula', linenos=False, noclasses=True, nowrap=True)
            # 预处理每一行
            lines = copy_text.splitlines() or [""]
            code_lines_html_list = []
            for line in lines:
                if not line:
                    code_lines_html_list.append("&nbsp;")
                else:
                    code_lines_html_list.append(highlight(line, lexer, formatter))
        except:
            lines = copy_text.splitlines() or [""]
            code_lines_html_list = [escape(line) or "&nbsp;" for line in lines]

        max_line = len(str(len(lines)))

        # 构建表格行
        rows = []
        for i, html_line in enumerate(code_lines_html_list):
            rows.append(
                f'<tr><td class="lineno" data-line="{i + 1}">{str(i + 1).rjust(max_line)}</td><td class="code-line">{html_line}</td></tr>')

        table_html = f'<table class="code-table"><tbody>{"".join(rows)}</tbody></table>'

        return f'''
        <div class="code-wrapper">
            <div class="code-header">
                <div style="display:flex; align-items:center; gap:8px;">
                     <span style="color: #9CDCFE; font-size: 12px; font-weight: bold;">{lang}</span>
                </div>
                <div style="display: flex; gap: 6px;">
                    <button type="button" data-action="insert" data-copy="{b64_copy}" class="code-btn" data-tooltip="插入"><img src="qrc:/icons/插入.svg" width="16"/></button>
                    <button type="button" data-action="create" data-copy="{b64_copy}" class="code-btn" data-tooltip="新建"><img src="qrc:/icons/新建.svg" width="16"/></button>
                    <button type="button" data-action="copy" data-copy="{b64_copy}" class="code-btn" data-tooltip="复制"><img src="qrc:/icons/复制.svg" width="16"/></button>
                </div>
            </div>
            <div style="overflow-x: auto;">{table_html}</div>
        </div>
        '''

    pattern = r'<pre><code(?:\s+class="([^"]*)")?>(.*?)</code></pre>'
    return re.sub(pattern, replacer, html, flags=re.DOTALL)


# ======== 辅助函数 ========
def _sanitize_incomplete_markdown(md_text: str) -> str:
    if not md_text: return ""
    if md_text.count('```') % 2 == 1: md_text += '\n```'
    # 处理不完整的 HTML 标签（流式常见问题）
    if md_text.endswith('<'): md_text = md_text[:-1]
    return md_text


def _render_think_block(content: str, completed: bool = True) -> str:
    status_text = "💡 思考过程" if completed else "🧠 正在思考..."
    open_attr = ' open' if not completed else ''
    return f'<details{open_attr} class="think-block"><summary>{status_text}</summary><div class="think-content">{content}</div></details>'


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


def _inject_context_links(md_text: str) -> str:
    def replacer(match):
        content, action = match.group(1), match.group(2)
        import urllib.parse
        encoded_c = urllib.parse.quote(content, safe='')
        encoded_a = urllib.parse.quote(action, safe='')
        return f'<span class="context-tag" data-type="{action}" data-content="{encoded_c}" data-action="{encoded_a}">{escape(content)}</span>'

    return re.sub(r'`*\[([^\[\]]+?)\]\(([^)\s]+)\)`*', replacer, md_text)


# ======== Page & Viewer (核心优化) ========
class ConsoleMonitorPage(QWebEnginePage):
    codeActionRequested = pyqtSignal(str, str)
    contextActionRequested = pyqtSignal(str, str)
    heightReported = pyqtSignal(int)
    contentReady = pyqtSignal()  # 新增：标志JS环境已就绪

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        msg = message.strip()
        if msg == "pywebview_ready":
            self.contentReady.emit()
        elif msg.startswith("pywebview_height:"):
            try:
                self.heightReported.emit(int(float(msg.split(":")[1])))
            except:
                pass
        elif msg.startswith("pywebview_action:"):
            if "context|||" in msg:
                try:
                    parts = msg.split("|||")
                    self.contextActionRequested.emit(urllib.parse.unquote(parts[1]), urllib.parse.unquote(parts[2]))
                except:
                    pass
            else:
                try:
                    p = msg.split(":")
                    self.codeActionRequested.emit(base64.b64decode(p[2]).decode('utf-8'), p[1])
                except:
                    pass


class CodeWebViewer(QWebEngineView):
    contentHeightChanged = pyqtSignal(int)
    codeActionRequested = pyqtSignal(str, str)
    contextActionRequested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._markdown_text = ""
        self._streaming = True
        self._is_js_ready = False  # 核心标志位

        # 优化定时器：更短的间隔，因为 runJavaScript 开销很小
        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._perform_update)
        self._min_render_interval = 35  # 35ms ~ 30fps，极度流畅

        self._page = ConsoleMonitorPage(self)
        self.setPage(self._page)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.page().setBackgroundColor(Qt.transparent)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(40)

        self._page.codeActionRequested.connect(self.codeActionRequested.emit)
        self._page.contextActionRequested.connect(self.contextActionRequested.emit)
        self._page.heightReported.connect(self._on_height_reported)
        self._page.contentReady.connect(self._on_js_ready)

        # 初始化加载骨架
        self._load_skeleton()

    def _on_height_reported(self, h):
        final_h = h + 10  # 留一点 buffer
        if abs(self.height() - final_h) > 2:  # 减少微小抖动
            self.contentHeightChanged.emit(final_h)

    def _on_js_ready(self):
        self._is_js_ready = True
        # 如果有积压的内容，立即渲染
        if self._markdown_text:
            self._schedule_render()

    def _generate_css(self):
        # 动态生成颜色CSS
        tag_css = []
        for act, col in ACTION_COLOR_MAP.items():
            tag_css.append(
                f'.context-tag[data-type="{act}"] {{ background: {col}15; border-color: {col}60; color: {col}; }}')
            tag_css.append(f'.context-tag[data-type="{act}"]:hover {{ background: {col}30; border-color: {col}; }}')

        return f"""
            html {{ overflow: hidden; }}
            body {{
                background: transparent !important; color: #E0E0E0;
                font-family: "Segoe UI", sans-serif; font-size: 14px; line-height: 1.6;
                margin: 0; padding: 10px 12px; overflow: hidden;
            }}
            /* 表格 */
            table:not(.code-table) {{ width: 100%; border-collapse: collapse; margin: 10px 0; background: #252526; border-radius: 6px; overflow: hidden; }}
            table:not(.code-table) th {{ background: #333; padding: 8px; text-align: left; font-weight: 600; color: #fff; }}
            table:not(.code-table) td {{ padding: 8px; border-bottom: 1px solid #3A3F47; color: #ccc; }}
            table:not(.code-table) tr:nth-child(even) {{ background: #2A2D31; }}

            /* 标签 */
            .context-tag {{ display: inline-block; padding: 2px 6px; margin: 0 2px; border: 1px solid transparent; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer; transition: 0.2s; }}
            {"".join(tag_css)}

            /* 代码块 */
            .code-wrapper {{ margin: 12px 0; background: #1E1E1E; border: 1px solid #3A3F47; border-radius: 8px; overflow: hidden; font-family: 'JetBrains Mono', Consolas, monospace; }}
            .code-header {{ display: flex; justify-content: space-between; padding: 6px 12px; background: #252526; border-bottom: 1px solid #333; }}
            .code-btn {{ width: 24px; height: 24px; background: transparent; border: none; border-radius: 4px; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
            .code-btn:hover {{ background: rgba(255,255,255,0.1); }}

            .code-table {{ width: 100%; border-collapse: collapse; }}
            .code-table td {{ padding: 0; vertical-align: top; }}
            .lineno {{ width: 32px; text-align: right; padding-right: 8px !important; color: #606060; border-right: 1px solid #404040; user-select: none; font-size: 12px; line-height: 1.5; }}
            .code-line {{ padding-left: 12px !important; color: #d4d4d4; font-size: 13px; line-height: 1.5; white-space: pre; }}

            /* 思考块 */
            details.think-block {{ margin: 8px 0; background: #1a1b1e; border: 1px solid #333; border-radius: 6px; }}
            details.think-block summary {{ padding: 6px 10px; cursor: pointer; color: #aaa; font-weight: 600; }}
            .think-content {{ padding: 10px; border-top: 1px solid #333; color: #888; font-style: italic; }}

            /* 引用 */
            blockquote {{ border-left: 3px solid #FFA500; background: rgba(255,165,0,0.05); margin: 10px 0; padding: 4px 12px; color: #ccc; }}
        """

    def _load_skeleton(self):
        """只加载一次 HTML 骨架"""
        cdn_libs = """
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
        <script>mermaid.initialize({ startOnLoad: false, theme: 'dark' });</script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            {cdn_libs}
            <style>{self._generate_css()}</style>
        </head>
        <body>
            <div id="content-placeholder"></div>
            <script>
                // 核心：增量更新函数
                function updateContent(newHtml) {{
                    const container = document.getElementById('content-placeholder');
                    if (container.innerHTML !== newHtml) {{
                        container.innerHTML = newHtml;

                        // 重新处理 Echarts
                        document.querySelectorAll('.echarts-div').forEach(div => {{
                            if (div.getAttribute('data-processed')) return;
                            try {{
                                const option = JSON.parse(decodeURIComponent(div.getAttribute('data-option')));
                                const chart = echarts.init(div, 'dark', {{renderer: 'canvas', useDirtyRect: false}});
                                option.backgroundColor = 'transparent';
                                chart.setOption(option);
                                new ResizeObserver(() => chart.resize()).observe(div);
                                div.setAttribute('data-processed', 'true');
                            }} catch(e) {{}}
                        }});

                        // 重新处理 Mermaid
                        mermaid.run({{ nodes: document.querySelectorAll('.mermaid') }});

                        // 重新处理 MathJax
                        if (window.MathJax && MathJax.typesetPromise) {{
                            MathJax.typesetPromise();
                        }}

                        reportHeight();
                    }}
                }}

                function reportHeight() {{
                    const h = document.documentElement.getBoundingClientRect().height;
                    console.log('pywebview_height:' + h);
                }}

                // 事件监听
                document.addEventListener('click', e => {{
                    const btn = e.target.closest('button[data-action]');
                    if (btn) {{
                        const act = btn.getAttribute('data-action');
                        const b64 = btn.getAttribute('data-copy');
                        if (act === 'copy' && navigator.clipboard) navigator.clipboard.writeText(atob(b64));
                        console.log('pywebview_action:' + act + ':' + b64);
                    }}
                    const tag = e.target.closest('.context-tag');
                    if (tag) {{
                        console.log('pywebview_action:context|||' + tag.getAttribute('data-content') + '|||' + tag.getAttribute('data-action'));
                    }}
                }});

                // 初始化通知
                window.onload = () => {{
                    console.log('pywebview_ready');
                    new ResizeObserver(() => requestAnimationFrame(reportHeight)).observe(document.body);
                }};
                window.pywebview = {{ reportHeight: reportHeight }};
            </script>
        </body>
        </html>
        """
        self.setHtml(html, QUrl(""))

    def append_chunk(self, text: str):
        if not text: return
        self._markdown_text += text
        self._schedule_render()

    def _schedule_render(self):
        if not self._is_js_ready: return
        if not self._render_timer.isActive():
            self._render_timer.start(self._min_render_interval)

    def _perform_update(self):
        # 转换 Markdown 为 HTML
        raw_md = self._markdown_text
        safe_md = _sanitize_incomplete_markdown(raw_md)
        safe_md = _unwrap_code_blocks_with_context_links(safe_md)
        safe_md = _inject_context_links(safe_md)
        processed_md = _inject_think_cards(safe_md, self._streaming == False)

        try:
            md = get_markdown_instance()
            md.reset()
            html_content = md.convert(processed_md)
            html_content = _wrap_code_blocks_with_copy_button_web(html_content)
        except Exception as e:
            html_content = f"<pre>{escape(raw_md)}</pre>"

        # 核心：使用 runJavaScript 注入 HTML，而不是 setHtml
        # json.dumps 确保字符串被正确转义，避免 JS 语法错误
        js_code = f"updateContent({json.dumps(html_content, ensure_ascii=False)});"
        self.page().runJavaScript(js_code)

    def finish_streaming(self):
        self._streaming = False
        self._perform_update()  # 确保最后一次状态（如思考块关闭）被渲染

    def get_plain_text(self) -> str:
        return self._markdown_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 宽度变化可能导致高度变化，触发重算
        QTimer.singleShot(50, lambda: self.page().runJavaScript("reportHeight();"))

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


# ======== MessageCard (保持不变，确保连接) ========
class TagWidget(CardWidget):
    closed = pyqtSignal(str)
    doubleClicked = pyqtSignal(str)

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(self);
        l.setContentsMargins(6, 0, 6, 0)
        l.addWidget(CaptionLabel(text, self))

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton: self.doubleClicked.emit(self.key)
        super().mouseDoubleClickEvent(e)


class MessageCard(SimpleCardWidget):
    deleteRequested = pyqtSignal()
    regenerateRequested = pyqtSignal()
    actionRequested = pyqtSignal(str, str)
    contextActionRequested = pyqtSignal(str, str)

    def __init__(self, role: str, timestamp: str = None, parent=None, tag_params: dict = None, error: bool = False):
        super().__init__(parent)
        self.parent = parent
        self.role = role
        self.context_tags = tag_params or {}
        self.timestamp = timestamp or datetime.now().strftime('%H:%M')
        self.error = error
        self._setup_ui()

    def _setup_ui(self):
        main = QVBoxLayout(self);
        main.setContentsMargins(5, 5, 5, 5);
        main.setSpacing(2)

        # Header
        top = QHBoxLayout();
        top.setSpacing(6)
        if self.role == "user":
            av_t, av_c, nm, nm_c, bg, bd = "👤", "#63B3ED", "用户", "#63B3ED", "#2A2A2A", "#4A5568"
        else:
            av_t, av_c, nm, nm_c, bg, bd = "🤖", "#FFA500", "画布助手", "#FFA500", "#1E293B", "#334155"
        if self.error: bd, bg = "#ff4d4d", "#2a1f1f"

        av = QLabel(av_t, self);
        av.setStyleSheet(f"font-size:20px;color:{av_c};font-weight:bold")
        av.setFixedSize(28, 28);
        av.setAlignment(Qt.AlignCenter)
        nm_l = QLabel(nm, self);
        nm_l.setStyleSheet(f"font-size:15px;color:{nm_c};font-weight:bold")
        top.addWidget(av);
        top.addWidget(nm_l)

        if self.role == "assistant":
            ts = QLabel(self.timestamp, self);
            ts.setStyleSheet("font-size:12px;color:#B0B0B0")
            top.addWidget(ts)
        top.addStretch()

        # Buttons
        btns = QWidget(self);
        bl = QHBoxLayout(btns);
        bl.setContentsMargins(0, 0, 0, 0);
        bl.setSpacing(4)
        specs = []
        if self.role == "assistant":
            specs = [(FluentIcon.COPY, "复制", lambda: self.actionRequested.emit(self.viewer.get_plain_text(), "copy")),
                     (FluentIcon.SYNC, "重试", self.regenerateRequested.emit)]
        elif self.role == "user":
            specs = [(FluentIcon.COPY, "复制", lambda: self.actionRequested.emit(self.viewer.get_plain_text(), "copy")),
                     (FluentIcon.DELETE, "删除", self.deleteRequested.emit)]

        for ic, tp, cb in specs:
            b = TransparentToolButton(ic, self);
            b.setToolTip(tp);
            b.clicked.connect(cb)
            b.setFixedSize(24, 24);
            b.installEventFilter(ToolTipFilter(b));
            bl.addWidget(b)
        top.addWidget(btns)
        main.addLayout(top);
        main.addWidget(CardSeparator(self))

        # Context Tags
        if self.role == "user" and self.context_tags:
            tg_c = QWidget(self);
            tl = QHBoxLayout(tg_c);
            tl.setContentsMargins(0, 0, 0, 0);
            tl.setSpacing(4)
            for k, (n, _, _, _) in self.context_tags.items():
                t = TagWidget(k, n);
                t.doubleClicked.connect(lambda k=k, t=t: self._on_link_click(k, t))
                tl.addWidget(t)
            tl.addStretch();
            main.addWidget(tg_c);
            main.addWidget(CardSeparator(self))

        # Viewer
        self.viewer = CodeWebViewer(self)
        self.viewer.codeActionRequested.connect(lambda c, a: self._handle_code(c, a))
        self.viewer.contextActionRequested.connect(self.contextActionRequested.emit)
        self.viewer.contentHeightChanged.connect(self._update_height)
        main.addWidget(self.viewer);
        main.addWidget(CardSeparator(self))

        self.setStyleSheet(f"CardWidget{{background-color:{bg};border:1px solid {bd};border-radius:12px;}}")

    def _handle_code(self, c, a):
        if a == "copy":
            QApplication.clipboard().setText(c)
            InfoBar.success('已复制', '代码已复制', duration=1500, parent=self.parent,
                            position=InfoBarPosition.TOP_RIGHT)
        self.actionRequested.emit(c, a)

    def _on_link_click(self, k, t):
        if ContextRegistry and k in self.context_tags:
            try:
                exe = self.parent.homepage.context_register.get_executor(k)
                if exe: exe(self.context_tags[k][2], t)
            except:
                pass

    def _update_height(self, h):
        self.viewer.setFixedHeight(max(40, h))
        self.updateGeometry()
        if self.parentWidget(): QTimer.singleShot(10, self.parentWidget().updateGeometry)

    def update_content(self, txt):
        self.viewer.append_chunk(txt)

    def finish_streaming(self):
        self.viewer.finish_streaming()

    def closeEvent(self, e):
        self.viewer.deleteLater(); super().closeEvent(e)


def create_welcome_card(parent=None) -> MessageCard:
    welcome_md = """\
### 👋 你好！我是你的画布开发智能助手

我已为你准备好以下能力，助你高效构建与调试画布：

- **🔗 上下文增强**  
  可动态插入画布节点、组件信息、全局变量等上下文（点击下方 `+` 选择插入）。

- **⚡ 上下文联动**  
  点击带链接的名称即可触发交互逻辑：
  - **跳转节点**：`[节点名](jump)` → 定位到画布中对应节点  
  - **创建组件**：`[组件名](create)` → 在画布中生成新组件节点  
  - **生成代码**：`[组件名](generate)` → 跳转至组件开发界面并自动生成代码  

---

### 💬 快速开始：点击下方问题直接提问

- [帮我分析当前画布功能是否合理？](ask)  
- [结合组件库，帮我完善当前画布：列出需新增的组件，如有前置节点需说明具体位置，如何连接，参数如何设置；若组件库缺失，也请说明需生成的新组件。](ask)  
- [帮我审查当前组件代码，指出潜在问题并提供优化建议。](ask)
- [帮我的代码生成一句话描述，说明代码具体功能、输入形式、输出形式、参数形式, 纯文本，不要有换行和任何特殊字符。](ask)

"""

    card = MessageCard(role="welcome", timestamp="就绪", parent=parent)
    card.update_content(welcome_md)
    card.finish_streaming()
    return card