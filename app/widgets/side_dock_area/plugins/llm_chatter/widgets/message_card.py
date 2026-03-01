# -*- coding: utf-8 -*-
import base64
import json
import re
import urllib
import uuid
from datetime import datetime
from html import escape
from typing import List, Dict, Any, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QPushButton,
    QButtonGroup,
)
from markdown import Markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, TextLexer
from qfluentwidgets import (
    FluentIcon,
    ToolTipFilter,
    TransparentToolButton,
    CardWidget,
    CaptionLabel,
)
from qfluentwidgets.components.widgets.card_widget import (
    CardSeparator,
    SimpleCardWidget,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.context_selector import (
    ContextRegistry,
)

# ======== Markdown 实例 ========
_md_instance = None
ACTION_COLOR_MAP = {
    "jump": "#FFA500",
    "create": "#9370DB",
    "generate": "#32CD32",
    "ask": "#FF6347",
    "view": "#4169E1",
}
DEFAULT_COLOR = "#888888"


def get_markdown_instance():
    global _md_instance
    if _md_instance is None:
        _md_instance = Markdown(
            extensions=["fenced_code", "nl2br", "tables"],
            output_format="html5",
            safe=False,
        )
    return _md_instance


def _unwrap_code_blocks_with_context_links(md_text: str) -> str:
    def replacer(match):
        lang_part = match.group(1) or ""
        code_content = match.group(2)
        if re.search(r"\[[^\[\]]+\]\([^)\s]+\)", code_content) and lang_part not in (
            "python"
        ):
            return code_content
        else:
            return (
                f"```{lang_part}\n{code_content}```"
                if lang_part
                else f"```\n{code_content}```"
            )

    pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    return pattern.sub(replacer, md_text)


# ======== 核心逻辑：保留你的原始代码块样式 ========
def _wrap_code_blocks_with_copy_button_web(html: str) -> str:
    def replacer(match):
        lang = (match.group(1) or "").replace("language-", "").strip()
        code_content_raw = match.group(2) or ""
        # --- 优化后的代码块逻辑 ---
        try:
            copy_text = (
                code_content_raw.replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&amp;", "&")
                .replace("&#39;", "'")
                .replace("&quot;", '"')
            )
        except:
            copy_text = code_content_raw

        b64_copy = base64.b64encode(copy_text.encode("utf-8")).decode("ascii")

        lines = copy_text.splitlines() or [""]
        line_count = len(lines)

        # 高亮代码（获取 <pre> 内部 HTML）
        try:
            lexer = get_lexer_by_name(lang, stripall=False) if lang else TextLexer()
            formatter = HtmlFormatter(
                style="dracula",
                linenos=False,
                noclasses=True,
                cssclass="code-block",
                prestyles="margin:0; padding:0; background:transparent; font-family: Consolas, monospace; font-size:13px; color:#D4D4D4;",
            )
            highlighted = highlight(copy_text, lexer, formatter)
            # 提取 <pre> 内部内容
            import re as preg

            pre_match = preg.search(r"<pre[^>]*>(.*?)</pre>", highlighted, preg.DOTALL)
            if pre_match:
                inner_code_html = pre_match.group(1)
            else:
                inner_code_html = escape(copy_text)
        except Exception:
            inner_code_html = escape(copy_text)

        # 生成行号（纯文本，每行一个数字）
        line_numbers_text = "\n".join(str(i + 1) for i in range(line_count))

        # 构建新的代码容器（行号固定 + 代码可横向滚动）
        code_block_html = f"""
        <div class="code-container">
            <div class="line-numbers">{escape(line_numbers_text)}</div>
            <div class="code-content">
                <pre>{inner_code_html}</pre>
            </div>
        </div>
        """

        return f'''
        <div style="
            position: relative;
            margin: 12px 0;
            background: #1E1E1E;
            border: 1px solid #3A3F47;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.25), 0 1px 3px rgba(0,0,0,0.3);
            font-family: Consolas, monospace;
            font-size: 13px;
        ">
            <!-- 顶部工具栏区域 -->
            <div style="
                display: flex; justify-content: space-between; align-items: center;
                padding: 6px 10px; height: 30px; background: rgba(28, 28, 28, 0.95);
                border-bottom: 1px solid #2d2d2d; border-radius: 10px 10px 0 0;
            ">
                {f'<span style="color: #FFA500; font-size: 13px; font-weight: bold;">{lang}</span>' if lang else '<span style="color: #888;">Plain Text</span>'}
                <div style="display: flex; gap: 12px; align-items: center; padding-right: 4px;">
                    <button type="button" data-action="insert" data-copy="{b64_copy}" class="code-btn" data-tooltip="插入代码" style="width: 30px; height: 30px; background: transparent; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0; border-radius: 6px;">
                        <img src="qrc:/icons/插入.svg" style="width:22px; height:22px; pointer-events: none;" />
                    </button>
                    <button type="button" data-action="create" data-copy="{b64_copy}" class="code-btn" data-tooltip="新建组件" style="width: 30px; height: 30px; background: transparent; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0; border-radius: 6px;">
                        <img src="qrc:/icons/新建.svg" style="width:22px; height:22px; pointer-events: none;" />
                    </button>
                    <button type="button" data-action="copy" data-copy="{b64_copy}" class="code-btn" data-tooltip="复制代码" style="width: 30px; height: 30px; background: transparent; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0; border-radius: 6px;">
                        <img src="qrc:/icons/复制.svg" style="width:22px; height:22px; pointer-events: none;" />
                    </button>
                </div>
            </div>
            <!-- 可横向滚动的代码区域 -->
            <div style="
                padding: 8px 0 0 0;
                border-radius: 0 0 10px 10px;
            ">
                {code_block_html}
            </div>
        </div>
        '''

    pattern = r'<pre><code(?:\s+class="([^"]*)")?>(.*?)</code></pre>'
    return re.sub(pattern, replacer, html, flags=re.DOTALL)


def _sanitize_incomplete_markdown(md_text: str) -> str:
    if not md_text:
        return ""
    if md_text.count("```") % 2 == 1:
        md_text += "\n```"
    if md_text.endswith("<"):
        md_text = md_text[:-1]
    return md_text


def _render_think_block(content: str, completed: bool = True) -> str:
    status_text = "💡 思考过程" if completed else "🧠 正在思考..."
    open_attr = " open" if not completed else ""
    return f'<details{open_attr} class="think-block"><summary>{status_text}</summary><div class="think-content">{content}</div></details>'


def _render_tool_block(
    tool_name: str, tool_args: dict, result: str, success: bool = True
) -> str:
    """渲染工具执行折叠框（默认折叠）"""
    status_icon = "✅" if success else "❌"
    args_str = json.dumps(tool_args, ensure_ascii=False, indent=2) if tool_args else ""
    header = f"{status_icon} 🔧 工具调用: {tool_name}"
    if args_str:
        header += f"\n📝 参数: {args_str}"

    result_html = result.replace("\n", "<br>")
    return f'<details class="tool-block"><summary>{header}</summary><div class="tool-content"><pre>{result_html}</pre></div></details>'


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
            content = md_text[start_idx + len("<think>") : end_idx]
            parts.append(_render_think_block(content, completed=True))
            i = end_idx + len("</think>")
        else:
            content = md_text[start_idx + len("<think>") :]
            parts.append(_render_think_block(content, completed=False))
            i = len(md_text)
    return "".join(parts)


def _inject_context_links(md_text: str) -> str:
    def replacer(match):
        content, action = match.group(1), match.group(2)
        import urllib.parse

        encoded_c = urllib.parse.quote(content, safe="")
        encoded_a = urllib.parse.quote(action, safe="")
        return f'<span class="context-tag" data-type="{action}" data-content="{encoded_c}" data-action="{encoded_a}">{escape(content)}</span>'

    return re.sub(r"`*\[([^\[\]]+?)\]\(([^)\s]+)\)`*", replacer, md_text)


# ======== WebViewer ========
class ConsoleMonitorPage(QWebEnginePage):
    codeActionRequested = pyqtSignal(str, str)
    contextActionRequested = pyqtSignal(str, str)
    heightReported = pyqtSignal(int)
    contentReady = pyqtSignal()

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
                    self.contextActionRequested.emit(
                        urllib.parse.unquote(parts[1]), urllib.parse.unquote(parts[2])
                    )
                except:
                    pass
            else:
                try:
                    p = msg.split(":")
                    self.codeActionRequested.emit(
                        base64.b64decode(p[2]).decode("utf-8"), p[1]
                    )
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
        self._is_js_ready = False

        # 1. 渲染定时器
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._perform_update)
        self._min_render_interval = 10  # 减少到10ms以获得更流畅的流式输出

        # 2. Resize 定时器 (修复 Crash 的关键：作为成员变量，随 self 销毁)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._safe_report_height)

        self._page = ConsoleMonitorPage(self)
        self.setPage(self._page)
        # 透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.page().setBackgroundColor(Qt.transparent)
        self.setContextMenuPolicy(Qt.NoContextMenu)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(40)

        self._page.codeActionRequested.connect(self.codeActionRequested.emit)
        self._page.contextActionRequested.connect(self.contextActionRequested.emit)
        self._page.heightReported.connect(self._on_height_reported)
        self._page.contentReady.connect(self._on_js_ready)

        self._load_skeleton()

    def _install_dialog_filter(self):
        """安装事件过滤器，监听对话框显示"""
        from PyQt5.QtWidgets import QApplication

        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        # 监听对话框显示事件
        if event.type() == 4:  # QEvent.Show
            obj_class = obj.__class__.__name__
            if (
                "Dialog" in obj_class
                or "Popup" in obj_class
                or "Flyout" in obj_class
                or "InfoBar" in obj_class
            ):
                self.lower()
        return super().eventFilter(obj, event)

    def lower_for_popup(self):
        """降低控件层级，让弹出窗口可以显示在前面"""
        self.lower()

    # 安全的高度上报函数
    def _safe_report_height(self):
        try:
            # 再次检查 page 是否存在，避免 C++ 对象已删除错误
            if self.page():
                self.page().runJavaScript("reportHeight();")
        except RuntimeError:
            # 捕获可能的 "wrapped C/C++ object has been deleted"
            pass

    def _on_height_reported(self, h):
        final_h = h + 2
        if abs(self.height() - final_h) > 2:
            self.contentHeightChanged.emit(final_h)

    def _on_js_ready(self):
        self._is_js_ready = True
        if self._markdown_text:
            self._schedule_render()

    def _load_skeleton(self):
        tag_css = []
        for act, col in ACTION_COLOR_MAP.items():
            tag_css.append(
                f'.context-tag[data-type="{act}"] {{ background: {col}15; border-color: {col}60; color: {col}; }}'
            )
            tag_css.append(
                f'.context-tag[data-type="{act}"]:hover {{ background: {col}30; border-color: {col}; }}'
            )

        cdn_libs = """
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        """

        scrollbar_css = """
            ::-webkit-scrollbar { width: 10px; height: 10px; }
            ::-webkit-scrollbar-track { background: #252526; border-radius: 5px; }
            ::-webkit-scrollbar-thumb { background: #454545; border-radius: 5px; border: 1px solid #3c3c3c; }
            ::-webkit-scrollbar-thumb:hover { background: #5a5a5a; }
        """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            {cdn_libs}
            <style>
                html {{ overflow: hidden; }}
                body {{
                    background: transparent !important; color: #E0E0E0;
                    font-family: "Segoe UI", sans-serif; font-size: 14px; line-height: 1.5;
                    margin: 0; 
                    /* 优化：减小上下内边距 */
                    padding: 4px 12px; 
                    overflow: hidden;
                }}
                {scrollbar_css}

                /* 修复黑色内容问题：显式设置所有元素的颜色 */
                #content-placeholder {{ color: #E0E0E0; }}
                #content-placeholder * {{ color: inherit; }}
                h1, h2, h3, h4, h5, h6 {{ color: #FFFFFF !important; font-weight: 600; }}
                h1 {{ font-size: 1.5em; margin: 12px 0 8px; }}
                h2 {{ font-size: 1.3em; margin: 10px 0 6px; }}
                h3 {{ font-size: 1.1em; margin: 8px 0 4px; }}
                p {{ margin: 6px 0; color: #D0D0D0; }}
                a {{ color: #6BA3FF !important; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                ul, ol {{ margin: 6px 0; padding-left: 24px; }}
                li {{ margin: 2px 0; color: #D0D0D0; }}
                strong {{ color: #FFFFFF !important; font-weight: 600; }}
                em {{ color: #B0B0B0 !important; font-style: italic; }}
                code:not(.code-content *):not(pre code) {{ 
                    background: #2D2D2D !important; 
                    color: #FF7B72 !important;
                    padding: 2px 4px; 
                    border-radius: 3px; 
                    font-family: Consolas, monospace;
                }}
                hr {{ border: none; border-top: 1px solid #3A3F47; margin: 12px 0; }}
                
                /* 优化：移除首尾元素的边距，彻底消除多余空白 */
                #content-placeholder > :first-child {{ margin-top: 0 !important; }}
                #content-placeholder > :last-child {{ margin-bottom: 0 !important; }}

                /* 优化：紧凑的段落间距 */
                p {{ margin: 6px 0; }}

                /* Markdown 表格 */
                table:not(.code-table) {{ width: 100%; border-collapse: collapse; margin: 8px 0; background: #252526; border-radius: 6px; overflow: hidden; border: 1px solid #3A3F47; }}
                table:not(.code-table) th {{ background: #333; padding: 6px 12px; text-align: left; font-weight: 600; color: #fff !important; border-bottom: 2px solid #454545; }}
                table:not(.code-table) td {{ padding: 6px 12px; border-bottom: 1px solid #3A3F47; color: #ccc !important; }}
                table:not(.code-table) tr:nth-child(even) {{ background: #2A2D31; }}
                table:not(.code-table) tr:hover {{ background: #3A3F47; }}

                /* 标签 */
                .context-tag {{ display: inline-block; padding: 1px 5px; margin: 0 2px; border: 1px solid transparent; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer; transition: 0.2s; vertical-align: middle; }}
                {"".join(tag_css)}

                /* 代码块通用样式 */
                .code-table {{ width: 100%; border-collapse: collapse; }}
                .code-table td {{ padding: 0; vertical-align: top; }}
                .lineno {{ width: 32px; text-align: right; padding-right: 8px !important; color: #606060; border-right: 1px solid #404040; user-select: none; font-size: 12px; line-height: 1.5; }}
                /* 优化后的代码块布局：行号固定，代码可横向滚动 */
                .code-container {{
                    display: flex;
                    overflow-x: auto;
                    overflow-y: hidden;
                    background: #1E1E1E;
                    font-family: Consolas, monospace;
                    font-size: 13px;
                    line-height: 1.5;
                    padding: 0 10px 8px 0;
                    margin: 0;
                }}
                .line-numbers {{
                    flex: 0 0 auto;
                    text-align: right;
                    padding-right: 12px;
                    color: #606060;
                    border-right: 1px solid #404040;
                    user-select: none; /* 关键：禁止复制行号 */
                    white-space: pre;
                    min-width: 32px;
                    overflow: hidden;
                }}
                .code-content {{
                    flex: 1;
                    overflow-x: auto;
                    overflow-y: hidden;
                    padding-left: 12px;
                }}
                .code-content pre {{
                    margin: 0 !important;
                    white-space: pre;
                    word-wrap: normal;
                    overflow: visible;
                    background: transparent !important;
                    font-family: Consolas, monospace !important;
                    font-size: 13px !important;
                    line-height: 1.5 !important;
                }}
                /* 关键：修复缩进丢失 */
                .code-line {{ padding-left: 12px !important; white-space: pre; font-family: Consolas, monospace; }}

                .code-btn:hover {{ background: rgba(255,255,255,0.1) !important; }}

                details.think-block {{ margin: 6px 0; background: #1a1b1e; border: 1px solid #333; border-radius: 6px; }}
                details.think-block summary {{ padding: 4px 10px; cursor: pointer; color: #aaa; font-weight: 600; }}
                .think-content {{ padding: 8px; border-top: 1px solid #333; color: #888 !important; font-style: italic; }}
                
                details.tool-block {{ margin: 6px 0; background: #1e1f22; border: 1px solid #4a4d50; border-radius: 6px; }}
                details.tool-block summary {{ padding: 6px 10px; cursor: pointer; color: #9cdcfe; font-weight: 600; font-size: 13px; white-space: pre-wrap; }}
                .tool-content {{ padding: 8px; border-top: 1px solid #4a4d50; background: #25262b; }}
                .tool-content pre {{ margin: 0; color: #ce9178; font-size: 12px; font-family: Consolas, monospace; }}
                
                blockquote {{ border-left: 3px solid #FFA500; background: rgba(255,165,0,0.05); margin: 6px 0; padding: 4px 12px; color: #ccc !important; }}
            </style>
        </head>
        <body>
            <div id="content-placeholder"></div>
            <script>
                function updateContent(newHtml) {{
                    const container = document.getElementById('content-placeholder');
                    if (container.innerHTML !== newHtml) {{
                        container.innerHTML = newHtml;
                        if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise();
                        reportHeight();
                    }}
                }}
                function reportHeight() {{
                    const h = document.documentElement.getBoundingClientRect().height;
                    console.log('pywebview_height:' + h);
                }}
                document.addEventListener('click', e => {{
                    const btn = e.target.closest('button[data-action]');
                    if (btn) {{
                        const act = btn.getAttribute('data-action');
                        const b64 = btn.getAttribute('data-copy');
                        if (act === 'copy' && navigator.clipboard) navigator.clipboard.writeText(atob(b64));
                        console.log('pywebview_action:' + act + ':' + b64);
                    }}
                    const tag = e.target.closest('.context-tag');
                    if (tag) console.log('pywebview_action:context|||' + tag.getAttribute('data-content') + '|||' + tag.getAttribute('data-action'));
                }});
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
        if not text:
            return
        self._markdown_text += text
        # 流式输出时立即渲染，不等待定时器
        if self._streaming and self._is_js_ready:
            from PyQt5.QtCore import QTimer

            QTimer.singleShot(0, self._perform_update)
        else:
            self._schedule_render()

    def _schedule_render(self):
        if not self._is_js_ready:
            return
        if not self._render_timer.isActive():
            self._render_timer.start(self._min_render_interval)

    def _perform_update(self):
        try:
            # 增加检查
            if not self.page():
                return

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
            except Exception:
                html_content = f"<pre>{escape(raw_md)}</pre>"

            js_code = f"updateContent({json.dumps(html_content, ensure_ascii=False)});"
            self.page().runJavaScript(js_code)
        except RuntimeError:
            pass

    def finish_streaming(self):
        self._streaming = False
        self._perform_update()

    def get_plain_text(self) -> str:
        return self._markdown_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 使用成员变量 timer，替代 lambda
        self._resize_timer.start()

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

    def deleteLater(self):
        # 显式停止定时器
        if self._render_timer.isActive():
            self._render_timer.stop()
        if self._resize_timer.isActive():
            self._resize_timer.stop()
        if self.page():
            self.page().deleteLater()
        super().deleteLater()


# ======== MessageCard ========
class TagWidget(CardWidget):
    closed = pyqtSignal(str)
    doubleClicked = pyqtSignal(str)

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        l = QHBoxLayout(self)
        l.setContentsMargins(6, 0, 6, 0)
        l.addWidget(CaptionLabel(text, self))

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.key)
        super().mouseDoubleClickEvent(e)


class MessageCard(SimpleCardWidget):
    deleteRequested = pyqtSignal()
    regenerateRequested = pyqtSignal()
    actionRequested = pyqtSignal(str, str)
    contextActionRequested = pyqtSignal(str, str)
    optionSelected = pyqtSignal(dict)
    interventionRequested = pyqtSignal(dict)

    def __init__(
        self,
        role: str,
        timestamp: str = None,
        parent=None,
        tag_params: dict = None,
        error: bool = False,
    ):
        super().__init__(parent)
        self.parent = parent
        self.role = role
        self.context_tags = tag_params or {}
        self.timestamp = timestamp or datetime.now().strftime("%H:%M")
        self.error = False
        self._interactive_options: List[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(5, 5, 5, 5)
        main.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(6)
        if self.role == "user":
            av_t, av_c, nm, nm_c, bg, bd = (
                "👤",
                "#63B3ED",
                "用户",
                "#63B3ED",
                "#2A2A2A",
                "#4A5568",
            )
        else:
            av_t, av_c, nm, nm_c, bg, bd = (
                "🤖",
                "#FFA500",
                "画布助手",
                "#FFA500",
                "#1E293B",
                "#334155",
            )
        if self.error:
            bd, bg = "#ff4d4d", "#2a1f1f"

        av = QLabel(av_t, self)
        av.setStyleSheet(f"font-size:20px;color:{av_c};font-weight:bold")
        av.setFixedSize(28, 28)
        av.setAlignment(Qt.AlignCenter)
        nm_l = QLabel(nm, self)
        nm_l.setStyleSheet(f"font-size:15px;color:{nm_c};font-weight:bold")
        top.addWidget(av)
        top.addWidget(nm_l)
        if self.role == "assistant":
            ts = QLabel(self.timestamp, self)
            ts.setStyleSheet("font-size:12px;color:#B0B0B0")
            top.addWidget(ts)
        top.addStretch()

        btns = QWidget(self)
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        specs = []
        if self.role == "assistant":
            specs = [
                (
                    FluentIcon.COPY,
                    "复制",
                    lambda: self.actionRequested.emit(
                        self.viewer.get_plain_text(), "copy"
                    ),
                ),
                (FluentIcon.SYNC, "重试", self.regenerateRequested.emit),
            ]
        elif self.role == "user":
            specs = [
                (
                    FluentIcon.COPY,
                    "复制",
                    lambda: self.actionRequested.emit(
                        self.viewer.get_plain_text(), "copy"
                    ),
                ),
                (FluentIcon.DELETE, "删除", self.deleteRequested.emit),
            ]
        for ic, tp, cb in specs:
            b = TransparentToolButton(ic, self)
            b.setToolTip(tp)
            b.clicked.connect(cb)
            b.setFixedSize(24, 24)
            b.installEventFilter(ToolTipFilter(b))
            bl.addWidget(b)
        top.addWidget(btns)
        main.addLayout(top)
        main.addWidget(CardSeparator(self))

        if self.role == "user" and self.context_tags:
            tg_c = QWidget(self)
            tl = QHBoxLayout(tg_c)
            tl.setContentsMargins(0, 0, 0, 0)
            tl.setSpacing(4)
            for k, (n, _, _, _) in self.context_tags.items():
                t = TagWidget(k, n)
                t.doubleClicked.connect(lambda k=k, t=t: self._on_link_click(k, t))
                tl.addWidget(t)
            tl.addStretch()
            main.addWidget(tg_c)
            main.addWidget(CardSeparator(self))

        self.viewer = CodeWebViewer(self)
        self.viewer.codeActionRequested.connect(self.actionRequested.emit)
        self.viewer.contextActionRequested.connect(self.contextActionRequested.emit)
        self.viewer.contentHeightChanged.connect(self._update_height)
        main.addWidget(self.viewer)

        self.options_widget = QWidget(self)
        self.options_layout = QVBoxLayout(self.options_widget)
        self.options_layout.setContentsMargins(0, 8, 0, 0)
        self.options_layout.setSpacing(8)
        self.options_widget.setVisible(False)
        main.addWidget(self.options_widget)

        main.addWidget(CardSeparator(self))
        self.setStyleSheet(
            f"CardWidget{{background-color:{bg};border:1px solid {bd};border-radius:12px;}}"
        )

    def _on_link_click(self, k, t):
        if ContextRegistry and k in self.context_tags:
            try:
                exe = self.parent.homepage.context_register.get_executor(k)
                if exe:
                    exe(self.context_tags[k][2], t)
            except:
                pass

    def _update_height(self, h):
        self.viewer.setFixedHeight(max(40, h))
        self.updateGeometry()
        if self.parentWidget():
            QTimer.singleShot(10, self.parentWidget().updateGeometry)

    def wheelEvent(self, event: QWheelEvent):
        try:
            scroll_area = self.parent.chat_scroll_area
            if scroll_area:
                vbar = scroll_area.verticalScrollBar()
                if (
                    vbar
                    and vbar.minimum() != vbar.maximum()
                    and event.angleDelta().y() != 0
                ):
                    vbar.setValue(vbar.value() - event.angleDelta().y() // 2)
                    event.accept()
                    return
        except:
            pass
        super().wheelEvent(event)

    def update_content(self, txt):
        self.viewer.append_chunk(txt)

    def add_interactive_option(self, option: Dict[str, Any]):
        """添加交互选项"""
        self._interactive_options.append(option)

        option_widget = QWidget(self.options_widget)
        option_layout = QHBoxLayout(option_widget)
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_layout.setSpacing(8)

        label = QLabel(f"• {option.get('label', '选项')}", self)
        label.setStyleSheet("color: #4a9eff; font-size: 13px; cursor: pointer;")
        label.setCursor(Qt.PointingHandCursor)
        label.option_data = option
        label.mousePressEvent = lambda e, opt=option: self._on_option_clicked(opt)

        option_layout.addWidget(label)
        option_layout.addStretch()

        self.options_layout.addWidget(option_widget)
        self.options_widget.setVisible(True)

    def add_interactive_options(self, options: List[Dict[str, Any]]):
        """批量添加交互选项"""
        if not options:
            return

        title_label = QLabel("👉 请选择：", self)
        title_label.setStyleSheet("color: #888; font-size: 12px; margin-top: 8px;")
        self.options_layout.addWidget(title_label)

        for option in options:
            self.add_interactive_option(option)

    def _on_option_clicked(self, option: Dict[str, Any]):
        """选项被点击"""
        self.optionSelected.emit(option)

    def set_intervention_mode(self, enabled: bool):
        """设置人工干预模式"""
        if enabled:
            self.interventionRequested.emit(
                {"card_id": id(self), "message": "请求人工干预"}
            )

    def finish_streaming(self):
        self.viewer.finish_streaming()

    def closeEvent(self, e):
        self.viewer.deleteLater()
        super().closeEvent(e)


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
