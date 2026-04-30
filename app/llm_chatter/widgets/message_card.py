# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import math
import re
import urllib
from datetime import datetime
from html import escape
from typing import List, Dict, Any, Optional

from app.utils.utils import get_icon
from app.llm_chatter.widgets.render_helpers import (
    render_tool_block,
)
from app.llm_chatter.utils.message_content import (
    append_text_block,
    append_tool_result_block,
    content_to_markdown,
    content_to_text,
    ensure_content_blocks,
)

from PyQt5.QtCore import (
    Qt,
    QTimer,
    QTimerEvent,
    pyqtSignal,
    QUrl,
    QVariantAnimation,
    QEasingCurve,
)
from PyQt5.QtGui import (
    QWheelEvent,
    QPainter,
    QPen,
    QColor,
    QBrush,
    QLinearGradient,
    QPainterPath,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
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

from app.llm_chatter.widgets.context_selector import (
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


def _strip_code_blocks(text: str) -> str:
    """移除 markdown 代码块标记，仅保留纯文本内容"""
    # 处理 ```lang\ncode\n``` 格式
    text = re.sub(r"```[\w]*\n", "", text)
    # 处理 ```code\n``` 格式
    text = re.sub(r"```\n", "", text)
    # 处理 ``` 结尾
    text = re.sub(r"```", "", text)
    return text


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
                    <button type="button" data-action="save_file" data-lang="{lang}" data-copy="{b64_copy}" class="code-btn" data-tooltip="保存本地文件" style="width: 30px; height: 30px; background: transparent; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0; border-radius: 6px;">
                        <img src="qrc:/icons/导入.svg" style="width:22px; height:22px; pointer-events: none;" />
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
    expanded = not completed

    max_preview = 40
    content_preview = content.strip().replace("\n", " ")[:max_preview]
    if len(content.strip().replace("\n", " ")) > max_preview:
        content_preview += "..."

    block_seed = f"{content}|{completed}"
    block_key = "think-" + hashlib.sha1(block_seed.encode("utf-8")).hexdigest()[:12]
    expanded_attr = "true" if expanded else "false"
    body_style = ' style="height:auto; opacity:1;"' if expanded else ""

    # 思考内容不需要渲染代码编辑框，移除代码块标记
    content = _strip_code_blocks(content)
    content = escape(content)

    return f"""<div class="cm-collapsible think-block" data-block-key="{block_key}" data-expanded="{expanded_attr}">
    <button type="button" class="cm-collapsible__summary think-block__summary" aria-expanded="{expanded_attr}">
        <span class="cm-collapsible__chevron" aria-hidden="true"></span>
        <span style="white-space: nowrap;">{status_text}</span>
        <span style="color: #666; font-size: 11px; font-weight: normal; margin-left: auto;">{escape(content_preview)}</span>
    </button>
    <div class="cm-collapsible__body"{body_style}>
        <div class="think-content" style="white-space: pre-wrap; word-break: break-word;">{content}</div>
    </div>
</div>"""


def _render_tool_block(
    tool_name: str, tool_args: dict, result: str, success: bool = True
) -> str:
    """渲染工具执行折叠框（默认折叠）"""
    import re

    result = re.sub(r"```[\w]*\n", "", result)
    result = re.sub(r"```", "", result)

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


def _render_tool_block_content(content: str) -> str:
    """渲染工具块内容为HTML"""
    lines = content.strip().split("\n")
    tool_name = ""
    tool_args = ""
    tool_result = ""
    tool_success = True
    tool_call_id = None

    for line in lines:
        if line.startswith("name: "):
            tool_name = line[6:].strip()
        elif line.startswith("args: "):
            tool_args = line[6:].strip()
        elif line.startswith("success: "):
            tool_success = line[9:].strip().lower() == "true"
        elif line.startswith("tool_call_id: "):
            tool_call_id = line[14:].strip()

    result_match = content.find("result: ")
    if result_match != -1:
        result_start = result_match + len("result: ")
        # 查找 success 或 tool_call_id 的位置来确定 result 的结束
        success_match = content.find("\nsuccess: ", result_start)
        tool_call_match = content.find("\ntool_call_id: ", result_start)
        
        # 取最近的标记位置
        end_markers = []
        if success_match != -1:
            end_markers.append(success_match)
        if tool_call_match != -1:
            end_markers.append(tool_call_match)
        
        if end_markers:
            end_pos = min(end_markers)
            tool_result = content[result_start:end_pos].strip()
        else:
            tool_result = content[result_start:].strip()

    try:
        args_dict = json.loads(tool_args) if tool_args else {}
    except:
        args_dict = {}

    return render_tool_block(
        tool_name, args_dict, tool_result, tool_success, collapsed=True,
        tool_call_id=tool_call_id
    )


def _inject_tool_blocks(md_text: str, completed: bool = True) -> str:
    """注入工具块HTML，类似think块"""
    if not md_text:
        return md_text

    parts = []
    i = 0
    while i < len(md_text):
        start_idx = md_text.find("<tool>", i)
        if start_idx == -1:
            parts.append(md_text[i:])
            break
        parts.append(md_text[i:start_idx])
        end_idx = md_text.find("</tool>", start_idx + len("<tool>"))
        if end_idx != -1:
            content = md_text[start_idx + len("<tool>") : end_idx]
            parts.append(_render_tool_block_content(content))
            i = end_idx + len("</tool>")
        else:
            # 工具块未完成（</tool>未出现），保留原始标记，不渲染
            # 避免流式输出时部分内容被错误渲染到折叠框外
            parts.append(md_text[start_idx:])
            break
    return "".join(parts)


def _inject_context_links(md_text: str) -> str:
    def replacer(match):
        content, action = match.group(1), match.group(2)
        if action.startswith("http://") or action.startswith("https://"):
            return match.group(0)
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
    toolDiffRequested = pyqtSignal(str)  # tool_call_id
    saveFileRequested = pyqtSignal(str, str)  # code, lang

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
            elif "context_lost" in msg:
                self._handle_context_lost()
            elif "open_url:" in msg:
                try:
                    url_str = msg.split("open_url:", 1)[1]
                    from PyQt5.QtGui import QDesktopServices
                    from PyQt5.QtCore import QUrl

                    QDesktopServices.openUrl(QUrl(url_str))
                except:
                    pass
            elif "tool_diff:" in msg:
                # 处理工具差异对比请求
                try:
                    tool_call_id = msg.split("tool_diff:", 1)[1]
                    self.toolDiffRequested.emit(tool_call_id)
                except Exception:
                    pass
            elif "save_file:" in msg:
                # 处理保存文件请求
                try:
                    parts = msg.split("save_file:", 1)[1]
                    # 格式: b64_code:lang
                    sub_parts = parts.rsplit(":", 1)
                    if len(sub_parts) == 2:
                        b64_code, lang = sub_parts
                        code = base64.b64decode(b64_code).decode("utf-8")
                        self.saveFileRequested.emit(code, lang)
                except Exception:
                    pass
            else:
                try:
                    p = msg.split(":")
                    self.codeActionRequested.emit(
                        base64.b64decode(p[2]).decode("utf-8"), p[1]
                    )
                except:
                    pass

    def _handle_context_lost(self):
        self.contentReady.emit()


class CodeWebViewer(QWebEngineView):
    contentHeightChanged = pyqtSignal(int)
    codeActionRequested = pyqtSignal(str, str)
    contextActionRequested = pyqtSignal(str, str)
    toolDiffRequested = pyqtSignal(str)  # tool_call_id
    saveFileRequested = pyqtSignal(str, str)  # code, lang
    # WebEngine 上下文丢失信号
    contextLost = pyqtSignal()
    contextRestored = pyqtSignal()

    # WebEngine 最大尺寸限制，防止 GPU 内存溢出
    MAX_WIDTH = 1600
    MAX_HEIGHT = 2000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._markdown_text = ""
        self._streaming = True
        self._is_js_ready = False
        self._last_rendered_html = ""
        self._last_rendered_markdown = ""
        self._reasoning_content = ""  # DeepSeek thinking mode
        self._min_render_interval = 50
        self._height_report_pending = False
        self._context_lost = False  # 上下文丢失标志
        self._context_lost_count = 0  # 上下文丢失次数统计
        self._resize_debounce_timer = QTimer(self)
        self._resize_debounce_timer.setSingleShot(True)
        self._resize_debounce_timer.setInterval(100)
        self._resize_debounce_timer.timeout.connect(self._do_resize_check)
        # 性能优化：resize 锁，防止 resize 期间频繁报告高度
        self._resize_locked = False
        self._resize_unlock_timer = QTimer(self)
        self._resize_unlock_timer.setSingleShot(True)
        self._resize_unlock_timer.setInterval(150)  # resize 结束后 150ms 再报告高度
        self._resize_unlock_timer.timeout.connect(self._on_resize_unlock)

        # 1. 渲染定时器
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._perform_update)

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
        self._page.toolDiffRequested.connect(self.toolDiffRequested.emit)
        self._page.saveFileRequested.connect(self.saveFileRequested.emit)

        self._load_skeleton()

    def _handle_context_lost(self):
        """JavaScript 报告上下文丢失"""
        if not self._context_lost:
            self._context_lost = True
            self._context_lost_count += 1
            self.contextLost.emit()
            # 尝试恢复上下文
            self._schedule_context_restore()

    def _schedule_context_restore(self):
        """延迟恢复 WebEngine 上下文"""
        QTimer.singleShot(500, self._try_restore_context)

    def _try_restore_context(self):
        """尝试恢复 WebEngine 上下文"""
        try:
            # 重新加载骨架 HTML
            self._is_js_ready = False
            self._load_skeleton()
            self._context_lost = False
            self.contextRestored.emit()
            # 重新渲染内容
            if self._markdown_text:
                self._schedule_render(immediate=True)
        except Exception as e:
            print(f"Context restore failed: {e}")

    def event(self, event):
        """拦截 WebEngine 事件"""
        # 处理上下文丢失
        if event.type() == QTimerEvent and hasattr(self, '_context_lost_timer'):
            pass
        return super().event(event)

    def setFixedSize(self, *args, **kwargs):
        """限制最大尺寸，防止 GPU 内存溢出"""
        # 计算安全尺寸
        w = args[0] if len(args) > 0 else kwargs.get('width', self.MAX_WIDTH)
        h = args[1] if len(args) > 1 else kwargs.get('height', self.MAX_HEIGHT)
        
        # 限制最大尺寸
        safe_w = min(w, self.MAX_WIDTH) if isinstance(w, int) else w
        safe_h = min(h, self.MAX_HEIGHT) if isinstance(h, int) else h
        
        super().setFixedSize(safe_w, safe_h)

    def resize(self, *args, **kwargs):
        """限制 resize 尺寸，防止过大导致 GPU 内存溢出"""
        w = args[0] if len(args) > 0 else kwargs.get('width', self.MAX_WIDTH)
        h = args[1] if len(args) > 1 else kwargs.get('height', self.MAX_HEIGHT)
        
        # 限制最大尺寸
        safe_w = min(w, self.MAX_WIDTH) if isinstance(w, int) else w
        safe_h = min(h, self.MAX_HEIGHT) if isinstance(h, int) else h
        
        super().resize(safe_w, safe_h)

    def _install_dialog_filter(self):
        """安装事件过滤器，监听对话框显示"""
        from PyQt5.QtWidgets import QApplication

        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        # 监听对话框显示/激活事件
        event_type = event.type()
        if event_type == 24 or event_type == 9:  # QEvent.Show = 24, QEvent.FocusIn = 9
            obj_class = obj.__class__.__name__
            popup_keywords = [
                "Dialog",
                "Popup",
                "Flyout",
                "InfoBar",
                "Toast",
                "ComboBox",
                "Menu",
                "ToolTip",
            ]
            if any(kw in obj_class for kw in popup_keywords):
                # 降低当前WebView及其父组件的层级
                self.lower()
                parent = self.parent()
                while parent:
                    parent.lower()
                    # 找到 MessageCard 或聊天容器为止
                    if (
                        hasattr(parent, "chat_layout")
                        or parent.__class__.__name__ == "MessageCard"
                    ):
                        break
                    parent = parent.parent()
                # 同时将弹窗提升到最顶层
                if hasattr(obj, "raise_"):
                    obj.raise_()
        return super().eventFilter(obj, event)

    def lower_for_popup(self):
        """降低控件层级，让弹出窗口可以显示在前面"""
        self.lower()
        # 降低父级
        parent_card = self.parent()
        if parent_card:
            parent_card.lower()

    # 安全的高度上报函数
    def _safe_report_height(self):
        try:
            # 再次检查 page 是否存在，避免 C++ 对象已删除错误
            if self.page():
                self._height_report_pending = False
                self.page().runJavaScript("reportHeight();")
        except RuntimeError:
            # 捕获可能的 "wrapped C/C++ object has been deleted"
            pass

    def _do_resize_check(self):
        # 如果处于 resize 锁定状态，跳过 height 报告
        if self._resize_locked:
            return
        try:
            if self.page():
                self.page().runJavaScript("reportHeight();")
        except RuntimeError:
            pass
    
    def _on_resize_unlock(self):
        """resize 结束后触发高度报告"""
        self._resize_locked = False
        self._do_resize_check()

    def _on_height_reported(self, h):
        self._height_report_pending = False
        final_h = h + 2
        if abs(self.height() - final_h) > 2:
            self.contentHeightChanged.emit(final_h)

    def _on_js_ready(self):
        self._is_js_ready = True
        if self._markdown_text:
            self._schedule_render(immediate=True)

    def _load_skeleton(self):
        # 获取系统字体
        font_family = "Segoe UI, sans-serif"
        try:
            from app.utils.config import Settings

            font_family = Settings.get_instance().llm_font_family.value
            if not font_family:
                font_family = "Segoe UI, sans-serif"
        except Exception:
            try:
                from app.utils.config import Settings
                font_family = Settings.get_instance().canvas_font_selected.value
                if not font_family:
                    font_family = "Segoe UI, sans-serif"
            except Exception:
                pass

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
                :root {{
                    --bg: transparent;
                    --panel: #121722;
                    --panel-elevated: #171d2a;
                    --panel-soft: #1d2533;
                    --border: #253044;
                    --border-strong: #32425e;
                    --text: #e8edf7;
                    --text-secondary: #b2bfd6;
                    --text-muted: #7f8ca3;
                    --accent: #66c6ff;
                    --accent-warm: #ffb65c;
                    --code-bg: #0f141d;
                    --code-toolbar: #131a25;
                    --code-border: #2a3447;
                    --success: #5fd18c;
                    --danger: #ff7b7b;
                }}
                html {{ overflow: hidden; }}
                body {{
                    background: var(--bg) !important;
                    color: var(--text);
                    font-family: "{font_family}", "Segoe UI", sans-serif; font-size: 14px; line-height: 1.5;
                    margin: 0; 
                    padding: 6px 14px; 
                    overflow: hidden;
                }}
                {scrollbar_css}

                #content-placeholder {{ color: var(--text); }}
                #content-placeholder * {{ color: inherit; }}
                h1, h2, h3, h4, h5, h6 {{ color: #FFFFFF !important; font-weight: 700; letter-spacing: 0.01em; }}
                h1 {{ font-size: 1.45em; margin: 12px 0 8px; }}
                h2 {{ font-size: 1.25em; margin: 10px 0 6px; }}
                h3 {{ font-size: 1.1em; margin: 8px 0 4px; }}
                p {{ margin: 8px 0; color: var(--text-secondary); }}
                a {{ color: var(--accent) !important; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                ul, ol {{ margin: 8px 0; padding-left: 24px; }}
                li {{ margin: 4px 0; color: var(--text-secondary); }}
                strong {{ color: #FFFFFF !important; font-weight: 600; }}
                em {{ color: #c4cedd !important; font-style: italic; }}
                code:not(.code-content *):not(pre code) {{ 
                    background: rgba(102, 198, 255, 0.12) !important; 
                    color: #9bddff !important;
                    padding: 2px 6px; 
                    border-radius: 5px; 
                    font-family: Consolas, monospace;
                }}
                hr {{ border: none; border-top: 1px solid var(--border); margin: 14px 0; }}
                
                /* 优化：移除首尾元素的边距，彻底消除多余空白 */
                #content-placeholder > :first-child {{ margin-top: 0 !important; }}
                #content-placeholder > :last-child {{ margin-bottom: 0 !important; }}

                /* 优化：紧凑的段落间距 */
                p {{ margin: 8px 0; }}

                table:not(.code-table) {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 10px 0;
                    background: rgba(18, 23, 34, 0.92);
                    border-radius: 10px;
                    overflow: hidden;
                    border: 1px solid var(--border);
                }}
                table:not(.code-table) th {{
                    background: rgba(50, 66, 94, 0.55);
                    padding: 8px 12px;
                    text-align: left;
                    font-weight: 600;
                    color: #fff !important;
                    border-bottom: 1px solid var(--border-strong);
                }}
                table:not(.code-table) td {{
                    padding: 8px 12px;
                    border-bottom: 1px solid rgba(37, 48, 68, 0.8);
                    color: var(--text-secondary) !important;
                }}
                table:not(.code-table) tr:nth-child(even) {{ background: rgba(29, 37, 51, 0.72); }}
                table:not(.code-table) tr:hover {{ background: rgba(38, 50, 69, 0.9); }}

                .context-tag {{
                    display: inline-block;
                    padding: 2px 8px;
                    margin: 0 2px;
                    border: 1px solid transparent;
                    border-radius: 999px;
                    font-size: 12px;
                    font-weight: 700;
                    cursor: pointer;
                    transition: 0.18s ease;
                    vertical-align: middle;
                }}
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
                    background: var(--code-bg);
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
                    color: #5b6578;
                    border-right: 1px solid var(--code-border);
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
                .code-line {{ padding-left: 12px !important; white-space: pre; font-family: Consolas, monospace; }}

                .code-btn:hover {{ background: rgba(255,255,255,0.08) !important; }}

                .cm-collapsible {{
                    overflow: hidden;
                    transform: translateZ(0);
                    backface-visibility: hidden;
                }}
                .cm-collapsible__summary {{
                    width: 100%;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    background: transparent;
                    border: none;
                    text-align: left;
                    cursor: pointer;
                    outline: none;
                    -webkit-tap-highlight-color: transparent;
                }}
                .cm-collapsible__summary:focus-visible {{
                    box-shadow: inset 0 0 0 1px rgba(102, 198, 255, 0.28);
                }}
                .cm-collapsible__chevron {{
                    flex: 0 0 auto;
                    width: 8px;
                    height: 8px;
                    border-right: 1.5px solid currentColor;
                    border-bottom: 1.5px solid currentColor;
                    transform: rotate(45deg);
                    transform-origin: center;
                    transition: transform 180ms ease;
                    margin-left: 2px;
                    opacity: 0.85;
                }}
                .cm-collapsible[data-expanded="true"] .cm-collapsible__chevron {{
                    transform: rotate(225deg);
                }}
                .cm-collapsible__body {{
                    height: 0;
                    opacity: 0;
                    overflow: hidden;
                    will-change: height, opacity;
                    transition: height 220ms cubic-bezier(0.22, 1, 0.36, 1), opacity 160ms ease;
                }}
                .cm-collapsible[data-expanded="true"] .cm-collapsible__body {{
                    opacity: 1;
                }}

                .think-block {{
                    margin: 8px 0;
                    background: linear-gradient(180deg, rgba(19,26,37,0.92), rgba(16,22,31,0.95));
                    border: 1px solid var(--border);
                    border-radius: 10px;
                }}
                .think-block__summary {{
                    padding: 8px 12px;
                    color: var(--text-secondary);
                    font-weight: 600;
                }}
                .think-content {{
                    padding: 10px 12px;
                    border-top: 1px solid var(--border);
                    color: var(--text-muted) !important;
                    font-style: italic;
                }}

                .tool-block {{
                    margin: 8px 0;
                    background: linear-gradient(180deg, rgba(18,24,35,0.96), rgba(15,20,29,0.98));
                    border: 1px solid var(--border);
                    border-radius: 10px;
                    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
                }}
                .tool-block__summary {{
                    padding: 8px 12px;
                    color: var(--accent);
                    font-weight: 600;
                    font-size: 13px;
                    white-space: normal;
                }}
                .tool-content {{
                    padding: 10px 12px;
                    border-top: 1px solid var(--border);
                    background: rgba(18, 24, 35, 0.84);
                }}
                .tool-content pre {{
                    margin: 0;
                    color: #d8b68d;
                    font-size: 12px;
                    font-family: Consolas, monospace;
                    white-space: pre-wrap;
                    word-break: break-word;
                }}

                blockquote {{
                    border-left: 3px solid var(--accent-warm);
                    background: rgba(255,182,92,0.08);
                    margin: 10px 0;
                    padding: 8px 12px;
                    border-radius: 0 10px 10px 0;
                    color: var(--text-secondary) !important;
                }}
            </style>
        </head>
        <body>
            <div id="content-placeholder"></div>
            <script>
                const collapsibleState = new Map();

                function syncExpandedAttrs(block, expanded) {{
                    block.dataset.expanded = expanded ? 'true' : 'false';
                    const summary = block.querySelector('.cm-collapsible__summary');
                    if (summary) summary.setAttribute('aria-expanded', expanded ? 'true' : 'false');
                    const key = block.dataset.blockKey;
                    if (key) collapsibleState.set(key, expanded);
                }}

                function animateCollapsible(block, expand) {{
                    const body = block.querySelector('.cm-collapsible__body');
                    if (!body) return;

                    body.style.transition = 'none';
                    const startHeight = body.getBoundingClientRect().height;
                    body.style.height = startHeight + 'px';
                    body.offsetHeight;
                    body.style.transition = '';

                    if (expand) {{
                        syncExpandedAttrs(block, true);
                        body.style.opacity = '1';
                        body.style.height = body.scrollHeight + 'px';
                    }} else {{
                        body.style.height = body.scrollHeight + 'px';
                        body.offsetHeight;
                        syncExpandedAttrs(block, false);
                        body.style.opacity = '0';
                        body.style.height = '0px';
                    }}

                    const cleanup = () => {{
                        if (block.dataset.expanded === 'true') {{
                            body.style.height = 'auto';
                            body.style.opacity = '1';
                        }} else {{
                            body.style.height = '0px';
                            body.style.opacity = '0';
                        }}
                        reportHeight();
                    }};

                    body.addEventListener('transitionend', cleanup, {{ once: true }});
                    requestAnimationFrame(reportHeight);
                }}

                function restoreCollapsibleStates(root) {{
                    root.querySelectorAll('.cm-collapsible').forEach(block => {{
                        const key = block.dataset.blockKey;
                        const expanded = key && collapsibleState.has(key)
                            ? collapsibleState.get(key)
                            : block.dataset.expanded === 'true';
                        const body = block.querySelector('.cm-collapsible__body');
                        syncExpandedAttrs(block, !!expanded);
                        if (body) {{
                            body.style.transition = 'none';
                            if (expanded) {{
                                body.style.height = 'auto';
                                body.style.opacity = '1';
                            }} else {{
                                body.style.height = '0px';
                                body.style.opacity = '0';
                            }}
                            body.offsetHeight;
                            body.style.transition = '';
                        }}
                    }});
                }}

                function updateContent(newHtml) {{
                    const container = document.getElementById('content-placeholder');
                    if (container.innerHTML !== newHtml) {{
                        container.innerHTML = newHtml;
                        restoreCollapsibleStates(container);
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
                        const lang = btn.getAttribute('data-lang') || '';
                        if (act === 'copy' && navigator.clipboard) navigator.clipboard.writeText(atob(b64));
                        console.log('pywebview_action:' + act + ':' + b64 + ':' + lang);
                        return;
                    }}
                    const summary = e.target.closest('.cm-collapsible__summary');
                    if (summary) {{
                        const block = summary.closest('.cm-collapsible');
                        if (block) {{
                            animateCollapsible(block, block.dataset.expanded !== 'true');
                        }}
                        return;
                    }}
                    const tag = e.target.closest('.context-tag');
                    if (tag) console.log('pywebview_action:context|||' + tag.getAttribute('data-content') + '|||' + tag.getAttribute('data-action'));
                    const link = e.target.closest('a');
                    if (link) {{
                        console.log('pywebview_action:link_found:' + link.href);
                    }}
                    if (link && link.href) {{
                        e.preventDefault();
                        console.log('pywebview_action:open_url:' + link.href);
                    }}
                }});
                document.addEventListener('DOMContentLoaded', () => {{
                    console.log('pywebview_ready');
                    reportHeight();
                    new ResizeObserver(() => requestAnimationFrame(reportHeight)).observe(document.body);
                }});
                window.addEventListener('load', () => {{
                    reportHeight();
                }});
                window.addEventListener('webglcontextlost', (e) => {{
                    e.preventDefault();
                    console.log('pywebview_action:context_lost');
                }}, false);
                window.addEventListener('webglcontextrestored', () => {{
                    console.log('pywebview_ready');
                    reportHeight();
                }}, false);
                window.pywebview = {{ reportHeight: reportHeight }};
                
                // 工具差异对比请求函数
                window._requestToolDiff = function(toolCallId) {{
                    console.log('pywebview_action:tool_diff:' + toolCallId);
                }};
            </script>
        </body>
        </html>
        """
        self.setHtml(html, QUrl(""))

    def append_chunk(self, text: str):
        if not text:
            return

        self._markdown_text += text

        if not self._is_js_ready:
            return
        if self._streaming and len(text) > 3:
            self._schedule_render(immediate=True)
        else:
            self._schedule_render()

    def _render_markdown_to_html(self, raw_md: str) -> str:
        # DeepSeek thinking mode: 注入 reasoning_content 作为思考块
        reasoning = getattr(self, '_reasoning_content', '') or ''
        if reasoning:
            think_html = _render_think_block(reasoning, completed=True)
            raw_md = think_html + raw_md
        
        safe_md = _sanitize_incomplete_markdown(raw_md)
        safe_md = _unwrap_code_blocks_with_context_links(safe_md)
        safe_md = _inject_context_links(safe_md)
        processed_md = _inject_think_cards(safe_md, self._streaming is False)
        processed_md = _inject_tool_blocks(processed_md, self._streaming is False)

        try:
            md = get_markdown_instance()
            md.reset()
            html_content = md.convert(processed_md)
            return _wrap_code_blocks_with_copy_button_web(html_content)
        except Exception:
            return f"<pre>{escape(raw_md)}</pre>"

    def _schedule_render(self, immediate: bool = False):
        if not self._is_js_ready:
            return
        if immediate:
            if self._render_timer.isActive():
                self._render_timer.stop()
            self._perform_update()
            return
        interval = self._min_render_interval if self._streaming else 40
        if self._render_timer.isActive():
            return
        self._render_timer.start(interval)

    def _perform_update(self):
        try:
            if not self.page():
                return
            if self._markdown_text == self._last_rendered_markdown:
                if not self._height_report_pending:
                    self._height_report_pending = True
                    self._resize_timer.start()
                return

            html_content = self._render_markdown_to_html(self._markdown_text)
            self._last_rendered_markdown = self._markdown_text
            if html_content == self._last_rendered_html:
                if not self._height_report_pending:
                    self._height_report_pending = True
                    self._resize_timer.start()
                return

            self._last_rendered_html = html_content
            self._height_report_pending = True
            js_code = f"updateContent({json.dumps(html_content, ensure_ascii=False)});"
            self.page().runJavaScript(js_code)
        except RuntimeError:
            pass

    def finish_streaming(self):
        self._streaming = False
        self._schedule_render(immediate=True)

    def get_plain_text(self) -> str:
        return self._markdown_text

    def get_html(self) -> str:
        return self._markdown_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._streaming:
            return
        
        # 性能优化：使用 resize 锁，阻止 resize 期间频繁报告高度
        if not self._resize_locked:
            self._resize_locked = True
            self._resize_unlock_timer.stop()
            self._resize_unlock_timer.start()

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
        if self._render_timer.isActive():
            self._render_timer.stop()
        if self._resize_timer.isActive():
            self._resize_timer.stop()
        if self._resize_debounce_timer.isActive():
            self._resize_debounce_timer.stop()
        if self._resize_unlock_timer.isActive():
            self._resize_unlock_timer.stop()
        if self.page():
            self.page().deleteLater()
        super().deleteLater()


class PlainTextViewer(QWidget):
    contentHeightChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)

        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text_edit.setFrameShape(QTextEdit.NoFrame)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                color: #F5F7FB;
                font-size: 14px;
                line-height: 1.5;
                selection-background-color: rgba(102, 198, 255, 0.28);
            }
        """)
        layout.addWidget(self.text_edit)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(40)

    def append_chunk(self, text: str):
        self._text += text
        self.text_edit.setPlainText(self._text)
        QTimer.singleShot(0, self._update_height)

    def finish_streaming(self):
        QTimer.singleShot(0, self._update_height)

    def get_plain_text(self) -> str:
        return self._text

    def set_text(self, text: str):
        self._text = text
        self.text_edit.setPlainText(text)
        QTimer.singleShot(0, self._update_height)

    def _update_height(self):
        """避免初始时 document().size() 返回虚高值的问题"""
        doc = self.text_edit.document()
        doc_height = int(doc.size().height())
        
        # 获取视口宽度，用于判断是否已布局完成
        viewport_width = self.text_edit.viewport().width()
        
        # 如果视口宽度为0，说明布局未完成，使用保守高度
        if viewport_width < 10:
            h = 40  # 最小高度，等resize时再更新
        else:
            # 布局完成后，使用文档实际高度 + padding
            h = max(40, doc_height + 16)
        
        if abs(self.height() - h) > 2:
            self.setFixedHeight(h)
            self.contentHeightChanged.emit(h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_height()


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
    undoRequested = pyqtSignal()
    actionRequested = pyqtSignal(str, str)
    contextActionRequested = pyqtSignal(str, str)
    optionSelected = pyqtSignal(dict)
    interventionRequested = pyqtSignal(dict)
    toolDiffRequested = pyqtSignal(str)  # tool_call_id
    cardDiffRequested = pyqtSignal(int)  # round_index
    saveFileRequested = pyqtSignal(str, str)  # code, lang

    def __init__(
        self,
        role: str,
        timestamp: str = None,
        parent=None,
        tag_params: dict = None,
        error: bool = False,
        reasoning_content: str = "",
    ):
        super().__init__(parent)
        self.parent = parent
        self.role = role
        self.context_tags = tag_params or {}
        self.timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
        self.error = error
        self._interactive_options: List[dict] = []
        self._content_data: Any = [] if role == "assistant" else ""
        self._streaming = False
        self._round_index: Optional[int] = None  # 用于卡片差异功能
        self._reasoning_content = reasoning_content
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_anim)
        self._pulse_phase = 0.0
        self._height_anim = QVariantAnimation(self)
        self._height_anim.setDuration(180)
        self._height_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._height_anim.valueChanged.connect(self._apply_viewer_height)
        self._target_viewer_height = 40
        self._last_applied_viewer_height = 40
        self._theme = self._build_theme(role, error)
        self._base_bg = self._theme["bg"]
        self._base_border = self._theme["border"]
        # 性能优化：缓存上次宽度值，避免不必要的更新
        self._last_synced_width = 0
        self._resize_anim_locked = False  # resize 动画锁，防止频繁触发
        # WebEngine 上下文恢复标志
        self._webengine_needs_restore = False
        self._setup_ui()

    def _build_theme(self, role: str, error: bool = False) -> Dict[str, str]:
        themes = {
            "assistant": {
                "avatar": "AI",
                "title": "Drifox",
                "subtitle": "Assistant",
                "bg": "rgba(45, 30, 20, 150)",
                "border": "none",
                "accent": "#D35400",
                "text": "#FFD4B8",
                "muted": "#8FA4C2",
                "side": "left",
            },
            "welcome": {
                "avatar": "DX",
                "title": "Drifox",
                "subtitle": "AI Copilot",
                "bg": "rgba(45, 30, 20, 150)",
                "border": "none",
                "accent": "#D35400",
                "text": "#FFD4B8",
                "muted": "#95A4BC",
                "side": "left",
            },
            "user": {
                "avatar": "你",
                "title": "你",
                "subtitle": "Prompt",
                "bg": "rgba(27,42,67,150)",
                "border": "none",
                "accent": "#9FC3FF",
                "text": "#F4F7FD",
                "muted": "#B4C2D9",
                "side": "right",
            },
        }
        theme = dict(themes.get(role, themes["assistant"]))
        if error:
            theme["bg"] = "#2A1F1F"
            theme["border"] = "#A94444"
            theme["accent"] = "#FF7B7B"
        return theme

    def _setup_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(10)

        av = QLabel(self)
        if self.role in ("welcome", "assistant"):
            # 品牌图标头像
            av_icon = get_icon("drifox")
            pixmap = av_icon.pixmap(28, 28)
            av.setPixmap(pixmap)
            av.setFixedSize(30, 30)
            av.setAlignment(Qt.AlignCenter)
        else:
            # user 和其他：圆形文字头像
            av.setText(self._theme["avatar"])
            av.setStyleSheet(
                f"""
                QLabel {{
                    font-size: 12px;
                    color: #FFFFFF;
                    font-weight: 700;
                    background: {self._theme["accent"]};
                    border: 1px solid rgba(255,255,255,0.12);
                    border-radius: 15px;
                }}
                """
            )
            av.setFixedSize(30, 30)
            av.setAlignment(Qt.AlignCenter)

        title_wrap = QWidget(self)
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)

        nm_l = QLabel(self._theme["title"], self)
        nm_l.setStyleSheet(
            f"font-size:14px;color:{self._theme['text']};font-weight:700;"
        )
        sub_l = QLabel(self._theme["subtitle"], self)
        sub_l.setStyleSheet(
            f"font-size:11px;color:{self._theme['muted']};font-weight:500;letter-spacing:0.02em;"
        )
        title_layout.addWidget(nm_l)
        title_layout.addWidget(sub_l)

        top.addWidget(av)
        top.addWidget(title_wrap)
        if self.role != "user":
            ts = QLabel(self.timestamp, self)
            ts.setStyleSheet(
                f"""
                QLabel {{
                    font-size: 11px;
                    color: {self._theme["muted"]};
                    background: rgba(255,255,255,0.03);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-radius: 9px;
                    padding: 2px 8px;
                }}
                """
            )
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
                    get_icon("差异对比"),
                    "文档差异对比",
                    lambda: self._emit_card_diff_requested(),
                ),
                (
                    get_icon("复制"),
                    "复制",
                    lambda: self.actionRequested.emit(self.get_plain_text(), "copy"),
                ),
            ]
        elif self.role == "user":
            specs = [
                (
                    get_icon("复制"),
                    "复制",
                    lambda: self.actionRequested.emit(self.get_plain_text(), "copy"),
                ),
                (get_icon("撤销"), "撤销到这里", self.undoRequested.emit),
                (FluentIcon.DELETE, "删除", self.deleteRequested.emit),
            ]
        for ic, tp, cb in specs:
            b = TransparentToolButton(ic, self)
            b.setToolTip(tp)
            b.clicked.connect(cb)
            b.setFixedSize(32, 32)
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

        if self.role == "user":
            self.viewer = PlainTextViewer(self)
            self.viewer.contentHeightChanged.connect(self._update_height)
        else:
            self.viewer = CodeWebViewer(self)
            self.viewer.codeActionRequested.connect(self.actionRequested.emit)
            self.viewer.contextActionRequested.connect(self.contextActionRequested.emit)
            self.viewer.contentHeightChanged.connect(self._update_height)
            self.viewer.toolDiffRequested.connect(self.toolDiffRequested.emit)
            self.viewer.saveFileRequested.connect(self.saveFileRequested.emit)
            # WebEngine 上下文丢失处理
            self.viewer.contextLost.connect(self._on_webengine_context_lost)
            self.viewer.contextRestored.connect(self._on_webengine_context_restored)
        main.addWidget(self.viewer)

        self.options_widget = QWidget(self)
        self.options_layout = QVBoxLayout(self.options_widget)
        self.options_layout.setContentsMargins(0, 8, 0, 0)
        self.options_layout.setSpacing(8)
        self.options_widget.setVisible(False)
        main.addWidget(self.options_widget)

        main.addWidget(CardSeparator(self))
        self.setStyleSheet(
            f"""
            CardWidget {{
                background-color: {self._theme["bg"]};
                border: 1px solid {self._theme["border"]};
                border-radius: 16px;
            }}
            """
        )

    def start_streaming_anim(self):
        if self._streaming:
            return
        self._streaming = True
        self._pulse_phase = 0.0
        try:
            self._anim_timer.start(80)
        except RuntimeError:
            return
        self.update()

    def _update_anim(self):
        self._pulse_phase = (self._pulse_phase + 0.25) % (math.pi * 2)
        self.update()

    def _apply_card_style(self, border: str = None, bg: str = None):
        self.setStyleSheet(
            f"""
            CardWidget {{
                background-color: {bg or self._base_bg};
                border: 1px solid {border or self._base_border};
                border-radius: 16px;
            }}
            """
        )

    def stop_streaming_anim(self):
        self._streaming = False
        try:
            self._anim_timer.stop()
        except RuntimeError:
            return
        self._apply_card_style()
        self.update()

    def _on_webengine_context_lost(self):
        """WebEngine 上下文丢失时显示恢复提示"""
        # 设置卡片为错误状态样式
        self._apply_card_style(border="#A94444")
        # 标记需要恢复
        self._webengine_needs_restore = True

    def _on_webengine_context_restored(self):
        """WebEngine 上下文恢复后恢复正常样式"""
        self._apply_card_style()
        self._webengine_needs_restore = False
        # 重新同步宽度
        self.sync_width(force=True)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        radius = 16

        accent = QColor(self._theme["accent"])
        accent.setAlpha(95 if self.role == "user" else 75)
        stripe_width = 4
        stripe_x = w - stripe_width - 2 if self._theme.get("side") == "right" else 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(stripe_x, 10, stripe_width, max(18, h - 20), 3, 3)

        if not self._streaming:
            return

        path = QPainterPath()
        path.addRoundedRect(1, 1, w - 2, h - 2, radius, radius)
        painter.setClipPath(path)

        gradient = QLinearGradient(0, 0, w, h)
        if self.role == "assistant":
            rainbow = [
                QColor("#63D8FF"),
                QColor("#7FA8FF"),
                QColor("#A98BFF"),
                QColor("#FF92C2"),
                QColor("#FFB86B"),
                QColor("#7BE3A1"),
            ]
            shift = int((self._pulse_phase / (math.pi * 2)) * len(rainbow))
            rainbow = rainbow[shift:] + rainbow[:shift]
            positions = [0.0, 0.2, 0.4, 0.62, 0.82, 1.0]
            for pos, color in zip(positions, rainbow):
                c = QColor(color)
                c.setAlpha(175)
                gradient.setColorAt(pos, c)
        else:
            pulse = QColor(self._theme["accent"])
            glow_alpha = 90 + int(45 * (math.sin(self._pulse_phase) + 1) / 2)
            pulse.setAlpha(glow_alpha)
            gradient.setColorAt(0.0, pulse.lighter(120))
            gradient.setColorAt(0.5, pulse)
            gradient.setColorAt(1.0, pulse.darker(130))

        pen = QPen(gradient, 3)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.NoBrush))
        painter.drawRoundedRect(1, 1, w - 2, h - 2, radius, radius)

        highlight = QColor(self._theme["accent"])
        highlight.setAlpha(24)
        painter.fillRect(0, 0, w, 4, highlight)

    def set_error_state(self, is_error: bool):
        self.error = is_error
        if is_error:
            bd, bg = "#ff4d4d", "#2a1f1f"
        else:
            bd, bg = self._base_border, self._base_bg
        self._apply_card_style(border=bd, bg=bg)

    def _on_link_click(self, k, t):
        if ContextRegistry and k in self.context_tags:
            try:
                exe = self.parent.homepage.context_register.get_executor(k)
                if exe:
                    exe(self.context_tags[k][2], t)
            except:
                pass

    def _emit_card_diff_requested(self):
        """发射卡片差异请求信号"""
        if self._round_index is not None:
            self.cardDiffRequested.emit(self._round_index)

    def _update_height(self, h):
        target_height = max(40, h)
        current_height = self.viewer.height() or self.viewer.minimumHeight() or 40
        self._target_viewer_height = target_height

        if self._streaming or abs(target_height - current_height) < 10:
            if self._height_anim.state() == QVariantAnimation.Running:
                self._height_anim.stop()
            self._apply_viewer_height(target_height)
            return

        self._height_anim.stop()
        self._height_anim.setStartValue(current_height)
        self._height_anim.setEndValue(target_height)
        self._height_anim.start()

    def _apply_viewer_height(self, value):
        height = max(40, int(value))
        if height == self._last_applied_viewer_height:
            return
        self._last_applied_viewer_height = height
        self.viewer.setFixedHeight(height)
        self.updateGeometry()
        parent = self.parentWidget()
        if parent:
            parent.updateGeometry()

    def sync_width(self, force: bool = False):
        """同步卡片宽度
        
        Args:
            force: 是否强制更新，即使宽度没变化
        """
        parent = self.parentWidget()
        if not parent:
            return
        parent_width = parent.width()
        if self.role == "welcome":
            horizontal_margin = 20
        elif self.role == "user":
            horizontal_margin = 120
        else:
            horizontal_margin = 72

        target_width = max(320, parent_width - horizontal_margin)
        
        # 性能优化：只有宽度真正变化时才更新
        if not force and target_width == self._last_synced_width:
            return
        
        self._last_synced_width = target_width
        if self.minimumWidth() != target_width or self.maximumWidth() != target_width:
            self.blockSignals(True)
            self.setMinimumWidth(target_width)
            self.setMaximumWidth(target_width)
            self.blockSignals(False)

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
        if self.role == "assistant" and not self._streaming:
            self.start_streaming_anim()
        if isinstance(txt, list):
            self.set_content(txt)
            return
        self.append_text(txt)

    def set_content(self, content: Any):
        if self.role == "assistant":
            self._content_data = ensure_content_blocks(content)
            rendered = content_to_markdown(self._content_data)
        else:
            self._content_data = str(content or "")
            rendered = self._content_data

        if hasattr(self.viewer, "_markdown_text"):
            self.viewer._markdown_text = rendered
            self.viewer._schedule_render(immediate=True)
        elif hasattr(self.viewer, "set_text"):
            self.viewer.set_text(rendered)

    def append_text(self, text: str):
        if self.role == "assistant":
            self._content_data = append_text_block(self._content_data, text)
            rendered = content_to_markdown(self._content_data)
            self.viewer._markdown_text = rendered
            self.viewer._schedule_render(immediate=False)
            return

        self._content_data = str(self._content_data or "") + str(text or "")
        self.viewer.append_chunk(str(text or ""))

    def append_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any] = None,
        result: Any = None,
        success: bool = True,
        tool_call_id: str = None,
    ):
        self._content_data = append_tool_result_block(
            self._content_data,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            tool_call_id=tool_call_id,
        )
        self.viewer._markdown_text = content_to_markdown(self._content_data)
        self.viewer._schedule_render(immediate=True)

    def get_plain_text(self) -> str:
        if self.role == "assistant":
            return content_to_text(self._content_data, include_tool_results=True)
        return str(self._content_data or "")

    def run_js(self, js_code: str):
        """运行 JavaScript 代码"""
        try:
            if self.viewer and hasattr(self.viewer, "page"):
                self.viewer.page().runJavaScript(js_code)
        except RuntimeError:
            pass

    def set_reasoning_content(self, content: str):
        """设置思考内容（用于 DeepSeek 思考模式）"""
        self._reasoning_content = content
        if content and hasattr(self.viewer, "_markdown_text"):
            # 刷新渲染以显示思考内容
            self.viewer._schedule_render(immediate=True)

    def set_html_direct(self, html: str):
        """直接设置 HTML，绕过打字机效果"""
        try:
            if self.viewer:
                self.viewer._markdown_text = html
                self.viewer._streaming = False
                self.viewer._perform_update()
        except RuntimeError:
            pass

    def append_reasoning(self, text: str):
        """追加思考内容（流式模式）"""
        if not hasattr(self.viewer, '_reasoning_content'):
            return
        self._reasoning_content = (self._reasoning_content or '') + text
        self.viewer._reasoning_content = self._reasoning_content
        # 触发渲染更新
        self.viewer._schedule_render(immediate=True)

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
        try:
            self.viewer.finish_streaming()
        except RuntimeError:
            pass
        self.stop_streaming_anim()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 性能优化：使用节流，避免每次 resize 都触发 sync_width
        if not self._resize_anim_locked:
            self._resize_anim_locked = True
            QTimer.singleShot(50, self._unlock_resize_and_sync)
    
    def _unlock_resize_and_sync(self):
        self._resize_anim_locked = False
        self.sync_width(force=True)

    def closeEvent(self, e):
        try:
            self._anim_timer.stop()
        except RuntimeError:
            pass
        try:
            self._height_anim.stop()
        except RuntimeError:
            pass
        if hasattr(self.viewer, "deleteLater"):
            try:
                self.viewer.deleteLater()
            except RuntimeError:
                pass
        super().closeEvent(e)


def create_welcome_card(
    parent=None, agent_name: str = "", agent_description: str = ""
) -> MessageCard:
    agent_tendency = ""
    if agent_name:
        agent_tendency = f"""
---

### 🤖 当前智能体：{agent_name}

{agent_description}

"""

    welcome_md = f"""\
### 👋 你好！我是 Drifox 飘狐

---
*如需切换智能体，请在输入框右下角下拉菜单中选择。*

{agent_tendency}
"""

    card = MessageCard(role="welcome", timestamp="就绪", parent=parent)
    card.update_content(welcome_md)
    card.finish_streaming()
    return card
