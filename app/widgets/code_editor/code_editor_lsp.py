# -*- coding: utf-8 -*-
import re
import sys
from typing import List, Dict

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QApplication
from intervaltree import IntervalTree
from loguru import logger
from qfluentwidgets import TransparentToolButton
from spyder.plugins.editor.panels.utils import FoldingRegion
from spyder.plugins.editor.utils.editor import BlockUserData
from spyder.plugins.editor.widgets.codeeditor import CodeEditor
from spyder.plugins.editor.widgets.completion import CompletionWidget
from spyder.widgets.findreplace import FindReplace

from app.server_manager.lsp_server.lsp_stdio_client import LspClientManager
from app.utils.utils import get_icon


class LSPCodeEditor(CodeEditor):
    lsp_signal = pyqtSignal(str)
    CODE_PREFIX = """from app.components import BaseComponent, ArgumentType, PropertyType, PortDefinition, PropertyDefinition, ConnectionType\n\n\n"""

    def __init__(self, parent=None, code_parent=None, python_exe_path=None, dialog=None):
        super().__init__()
        self.python_exe_path = python_exe_path
        self.parent_widget = parent
        self.code_parent = code_parent
        self._lsp_ready = False
        self._completing = False
        self._request_hover_clicked = False
        self._show_hint = True
        self._lsp_document_opened = False
        self._last_lsp_content = ""

        # 极限优化：缓存增量变更，不再使用全文 Diff
        self._pending_changes = []
        self._prefix_line_count = self.CODE_PREFIX.count('\n')
        self._prefix_char_count = len(self.CODE_PREFIX)
        # 初始化定时器
        self._init_timers()
        # LSP 集成
        self.lsp_session = LspClientManager(python_path=self.python_exe_path)
        self._connect_lsp_signals()

        # CompletionWidget
        self.completion_widget = CompletionWidget(parent=self, ancestor=self.code_parent)
        self.completion_widget.sig_completion_hint.connect(self.show_hint_for_completion)
        self.completion_widget.setStyleSheet("background-color: #1E1E1E;")
        self.completion_widget.setMinimumWidth(350)
        self.completion_widget.setMinimumHeight(120)

        # 编辑器设置
        self.setup_editor(
            language='python',
            color_scheme='spyder/dark',
            font=QFont('Consolas', 13),
            folding=True,
            automatic_completions=True,
            completions_hint=True,
            hover_hints=True,
            underline_errors=True,
            highlight_current_line=True,
            markers=True,
            automatic_completions_after_chars=1,
            completions_hint_after_ms=500,
            code_snippets=True,
            intelligent_backspace=True,
        )

        # 按钮
        btn_text = "缩小" if dialog else "放大"
        self.fullscreen_button = TransparentToolButton(get_icon(btn_text), parent=self)
        self.fullscreen_button.setFixedSize(28, 28)
        self._update_button_position()

        # --- 关键：监听内容变更 ---
        self.document().contentsChange.connect(self._on_document_contents_change)

    def _init_timers(self):
        self._completion_timer = QTimer()
        self._completion_timer.setSingleShot(True)
        self._completion_timer.timeout.connect(self._trigger_completion)
        self._signature_timer = QTimer()
        self._signature_timer.setSingleShot(True)
        self._signature_timer.timeout.connect(self._trigger_signature_help)
        self._hover_timer = QTimer()
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._trigger_hover)
        self._folding_timer = QTimer()
        self._folding_timer.setSingleShot(True)
        self._folding_timer.timeout.connect(self._request_folding)
        self._lsp_sync_timer = QTimer()
        self._lsp_sync_timer.setSingleShot(True)
        self._lsp_sync_timer.timeout.connect(self._sync_to_lsp)

    def _connect_lsp_signals(self):
        self.lsp_session.initialized.connect(self._on_lsp_initialized)
        self.lsp_session.completion_ready.connect(self._on_lsp_completions_ready)
        self.lsp_session.diagnostics_ready.connect(self._on_lsp_diagnostics_ready)
        self.lsp_session.folding_ready.connect(self._on_lsp_folding_ready)
        self.lsp_session.hover_ready.connect(self._on_hover_response)
        self.lsp_session.definition_ready.connect(self._on_definition_response)
        self.lsp_session.formatting_ready.connect(self._apply_formatting_edits)
        self.lsp_session.completion_resolved.connect(self._on_completion_resolved)
        self.lsp_session.signature_help_ready.connect(self._on_signature_help_response)
        self.lsp_session.error.connect(lambda e: self.lsp_signal.emit("error"))

    def set_completion_environment(self, python_exe: str = None):
        self._lsp_document_opened = False
        if python_exe is None or python_exe == self.python_exe_path:
            self.lsp_signal.emit("restarting...")
        else:
            self.python_exe_path = python_exe
            self.lsp_signal.emit("starting")
        if hasattr(self, 'lsp_session') and self.lsp_session:
            self.lsp_session.shutdown()
        self.lsp_session.set_python_path(self.python_exe_path)

        QTimer.singleShot(2000, self.lsp_session.start)

    # ========== 核心优化：0-Diff 增量同步 ==========

    def _on_document_contents_change(self, position, chars_removed, chars_added):
        """不再对比全文字符串，直接捕获物理变更 (O(1) 复杂度)"""
        if not self._lsp_ready: return
        self._pending_changes.append((position, chars_removed, chars_added))
        self._lsp_sync_timer.start(30)

    def _sync_to_lsp(self):
        if not self._lsp_ready: return
        if not self._lsp_document_opened:
            self.lsp_session.open_document(self._get_code_with_prefix())
            self._lsp_document_opened = True
            self._pending_changes.clear()
        elif self._pending_changes:
            full_text = self._get_code_with_prefix()
            changes = []
            for pos, removed, added in self._pending_changes:
                # 坐标平移（加上前缀长度）
                actual_pos = pos + self._prefix_char_count
                # 高效计算 LSP 坐标
                line = full_text.count('\n', 0, actual_pos)
                last_nl = full_text.rfind('\n', 0, actual_pos)
                col = actual_pos - (last_nl + 1) if last_nl != -1 else actual_pos

                # 这里为了极致简化且安全，我们发送此时刻该位置的文本
                changes.append({
                    "range": {"start": {"line": line, "character": col},
                              "end": {"line": line, "character": col + removed}},
                    "text": full_text[actual_pos: actual_pos + added]
                })
            self.lsp_session.change_document_delta(changes)
            self._pending_changes.clear()
        self._folding_timer.start(800)

    def _on_lsp_initialized(self):
        self._lsp_ready = True;
        self.lsp_signal.emit("ready")
        if self.toPlainText().strip(): self._sync_to_lsp()

    def _on_text_changed_for_lsp(self):
        pass  # 已被 contentsChange 替代，保留定义

    def _get_code_with_prefix(self) -> str:
        code = self.toPlainText()
        return code if code.startswith(self.CODE_PREFIX[:10]) else self.CODE_PREFIX + code

    def _compute_text_changes(self, old_text: str, new_text: str) -> List[Dict]:
        """保留原有函数定义，但实际同步已优化为 contentsChange 驱动"""
        return []

    def _pos_to_line_col(self, text: str, pos: int) -> tuple[int, int]:
        if pos <= 0: return (0, 0)
        lines = text.splitlines(keepends=True)
        curr = 0
        for i, l in enumerate(lines):
            if curr + len(l) >= pos: return (i, pos - curr)
            curr += len(l)
        return (len(lines), 0)

    def _request_folding(self):
        if self._lsp_ready: self.lsp_session.request_folding_ranges()

    def _on_lsp_folding_ready(self, folding_ranges: List[Dict]):
        if not hasattr(self, 'folding_panel') or not self.folding_panel: return
        tree = IntervalTree();
        regions = {};
        status = {}
        for fr in folding_ranges:
            start = fr['startLine'] + 1 - self._prefix_line_count
            end = fr['endLine'] + 1 - self._prefix_line_count
            if end > start:
                regions[start] = end;
                status[start] = False;
                tree[start:end + 1] = (start, end)
        self.folding_panel.update_folding((tree, FoldingRegion(None, None), regions, {}, {}, status))
        self.folding_panel.folding_regions = regions;
        self.folding_panel.folding_status = status

    def format_document(self):
        if self._lsp_ready:
            self.lsp_session.request_formatting()

    def format_selection(self):
        if not self._lsp_ready: return
        cursor = self.textCursor()
        if cursor.hasSelection():
            self.lsp_session.request_range_formatting(
                self.document().findBlock(cursor.selectionStart()).blockNumber(), 0,
                self.document().findBlock(cursor.selectionEnd()).blockNumber(), 0
            )

    def _apply_formatting_edits(self, text_edits: List[Dict]):
        if not text_edits:
            return
        self.set_text(text_edits[0]['newText'][self._prefix_char_count:])
        self.reopen_document()

    def reopen_document(self):
        """强制重置 LSP 服务器端的文档状态，解决全量替换导致的乱序问题"""
        if not self._lsp_ready:
            return

        # 1. 停止增量同步计时器
        self._lsp_sync_timer.stop()
        self._pending_changes.clear()

        # 2. 构造带前缀的新内容
        full_code = self._get_code_with_prefix()

        # 3. 先关闭再打开（这是 LSP 协议中最稳健的硬重置方式）
        # 即使服务器没打开过这个文档，发 close 也是安全的
        try:
            self.lsp_session.close_document()
        except:
            pass

        # 4. 发送 didOpen
        self.lsp_session.open_document(full_code)

        # 5. 更新本地状态，确保后续的 contentsChange 从这个新起点计算
        self._lsp_document_opened = True

        # 6. 顺便请求一次新的折叠范围，保持 UI 同步
        self._folding_timer.start(500)

    def request_hover(self, line, col, offset, show_hint=True, clicked=True):
        self._show_hint = show_hint
        self._request_hover_clicked = clicked
        self.lsp_session.request_hover(line + self._prefix_line_count, col)

    def _on_hover_response(self, result):
        if result.get("contents"):
            val = result["contents"].get("value", "") \
                if isinstance(result["contents"], dict) else str(result["contents"])
            self.handle_hover_response({"params": val})

    def go_to_definition_from_cursor(self, cursor=None):
        if not self.go_to_definition_enabled or self.in_comment_or_string():
            return
        if cursor is None:
            cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        if cursor.selectedText():
            self.lsp_session.request_definition(cursor.blockNumber() + self._prefix_line_count, cursor.columnNumber())

    def _on_definition_response(self, result):
        self.handle_go_to_definition({"params": result})

    def do_completion(self, automatic=True):
        if self._lsp_ready:
            self._completion_timer.start(10)

    def _trigger_completion(self):
        self.lsp_session.request_completion(
            self.textCursor().blockNumber() + self._prefix_line_count, self.textCursor().columnNumber()
        )

    def _trigger_signature_help(self):
        self.lsp_session.request_signature_help(
            self.textCursor().blockNumber() + self._prefix_line_count, self.textCursor().columnNumber()
        )

    def _trigger_hover(self):
        self.lsp_session.request_hover(
            self.textCursor().blockNumber() + self._prefix_line_count, self.textCursor().columnNumber()
        )

    def _get_completion_prefix(self) -> str:
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        start = pos
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] == '_'):
            start -= 1
        return text[start:pos]

    def _on_lsp_completions_ready(self, completion_items: List[Dict]):
        """处理补全结果"""
        pos = self.textCursor().position()
        clean_items = []

        for item in completion_items:
            # 1. 获取基础信息
            label = item.get('label', '')
            insert_text = item.get('insertText', label)

            # 2. 解决 "plt.plot(args...)" 问题：剥离括号及参数
            # 如果 insertText 等于 label 且包含括号，这通常是 Jedi 的默认行为，我们需要手动清洗
            if insert_text == label and '(' in insert_text:
                insert_text = insert_text.split('(')[0]

            # 构造 Spyder 需要的格式
            item_data = item.copy()
            item_data.update({
                'label': label,
                'filterText': item.get('filterText', label),  # 用于模糊匹配
                'insertText': insert_text,
                'kind': item.get('kind', 1),
                'documentation': item.get('documentation', ''),
                'detail': item.get('detail', ''),
                'point': pos,
                'resolve': True  # 允许后续解析文档
            })
            clean_items.append(item_data)

        self.completion_args = (pos, True)
        self.process_completion({"params": clean_items})

    def resolve_completion_item(self, item):
        self.lsp_session.request_completion_resolve(
            {
                k: v for k, v in item.items()
                if k in {'label', 'kind', 'detail', 'documentation', 'insertText',
                         'filterText', 'textEdit', 'additionalTextEdits', 'command',
                         'data', 'tags', 'insertTextFormat', 'commitCharacters',
                         'preselect'}
            }
        )

    def _on_completion_resolved(self, resolved_item):
        cw = self.completion_widget
        if cw.isVisible() and getattr(cw, 'current_selected_item_label', '') == resolved_item.get('label'):
            doc = resolved_item.get('documentation', '')
            resolved_item['documentation'] = doc.get('value', '') if isinstance(doc, dict) else doc
            cw.augment_completion_info(resolved_item)

    def _on_signature_help_response(self, result):
        if not result or not result.get('signatures'): return
        active_sig = result.get('activeSignature', 0)
        sig = result['signatures'][active_sig if active_sig < len(result['signatures']) else 0]
        doc = sig.get('documentation', '')
        self.process_signatures(
            {
                "params":
                    {
                        "signatures":
                            {
                                "label": sig['label'],
                                "documentation": doc.get('value', '') if isinstance(doc, dict) else doc,
                                "parameters": sig.get('parameters', [])
                            },
                        "activeParameter": result.get('activeParameter', 0)
                    }
            }
        )

    def _on_lsp_diagnostics_ready(self, diagnostics: List[Dict]):
        self.clear_extra_selections('lsp_underline')
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if data and hasattr(data, 'code_analysis'):
                data.code_analysis = [x for x in data.code_analysis if x[0] != 'lsp']
                if not data.code_analysis:
                    data.color = None
            block = block.next()
        has_error = False
        for diag in diagnostics:
            try:
                line = diag['range']['start']['line'] - len(self.CODE_PREFIX.splitlines())
                severity = diag.get('severity', 1)
                message = diag.get('message', '').strip()
                if not message:
                    continue
                block = self.document().findBlockByNumber(line)
                if not block.isValid():
                    continue
                data = block.userData()
                if not data:
                    data = BlockUserData(self)
                block.setUserData(data)
                data.code_analysis.append(('lsp', '', severity, message))
                data.color = self.error_color if severity == 1 else self.warning_color
                has_error = True
                start_char = diag['range']['start']['character']
                end_char = diag['range']['end']['character']
                start_pos = block.position() + start_char
                end_pos = block.position() + end_char
                cursor = QTextCursor(self.document())
                cursor.setPosition(start_pos)
                cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                self.highlight_selection(
                    'lsp_underline',
                    cursor,
                    underline_color=QColor(data.color),
                    underline_style=QTextCharFormat.WaveUnderline
                )
            except Exception as e:
                logger.exception(f"[LSP] Error processing diagnostic: {e}")
        if has_error:
            self.sig_flags_changed.emit()
            if hasattr(self, 'linenumberarea'):
                self.linenumberarea.update()

    def _smart_newline(self):
        """
        shift + enter 智能换行
        """
        cursor = self.textCursor()
        line = cursor.block().text()
        indent = ' ' * (len(line) - len(line.lstrip()))
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText('\n' + indent)
        self.setTextCursor(cursor)

    def _toggle_comment(self):
        cursor = self.textCursor()
        doc = self.document()
        c = QTextCursor(doc)
        c.setPosition(cursor.selectionStart())
        c.movePosition(QTextCursor.StartOfLine)
        start_pos = c.position()
        c.setPosition(cursor.selectionEnd())
        c.movePosition(QTextCursor.EndOfLine)
        c.setPosition(start_pos, QTextCursor.KeepAnchor)
        lines = c.selectedText().split('\u2029')
        all_commented = all(not t.strip() or t.strip().startswith('#') for t in lines)
        new_lines = []
        for t in lines:
            if all_commented:
                new_lines.append(re.sub(r'^(\s*)#\s?', r'\1', t))
            else:
                pattern = r'^(\s*)'
                new_lines.append(
                    f"{re.match(pattern, t).group(1)}# {t.lstrip()}"
                ) if t.strip() else new_lines.append(t)
        cursor.beginEditBlock()
        c.insertText('\n'.join(new_lines))
        cursor.endEditBlock()

    def _copy_with_folding(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            line = cursor.blockNumber() + 1
            if getattr(self, 'folding_panel', None) and self.folding_panel.folding_status.get(line):
                end_line = self.folding_panel.folding_regions[line]
                c = QTextCursor(self.document())
                c.setPosition(self.document().findBlockByNumber(line - 1).position())
                c.setPosition(
                    self.document().findBlockByNumber(end_line - 1).position() + self.document().findBlockByNumber(
                        end_line - 1).length() - 1, QTextCursor.KeepAnchor)
                QApplication.clipboard().setText(c.selectedText())
                return
        super().copy()

    def keyPressEvent(self, event):
        key = event.key()
        txt = event.text()

        # 快捷键逻辑保留
        if key in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers():
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            cursor_pos = cursor.positionInBlock()
            line_before_cursor = text[:cursor_pos]
            line_after_cursor = text[cursor_pos:]
            open_count = line_before_cursor.count('[') + line_before_cursor.count('(') + line_before_cursor.count('{')
            close_count = line_before_cursor.count(']') + line_before_cursor.count(')') + line_before_cursor.count('}')
            if open_count > close_count:
                leading_spaces = len(text) - len(text.lstrip())
                new_indent = ' ' * (leading_spaces + 4)
                cursor.insertText('\n' + new_indent)
                if line_after_cursor.strip().startswith(']') or line_after_cursor.strip().startswith(
                        ')') or line_after_cursor.strip().startswith('}'):
                    cursor.insertText('\n' + ' ' * leading_spaces)
                    cursor.movePosition(QTextCursor.PreviousBlock)
                    cursor.movePosition(QTextCursor.EndOfBlock)
                    self.setTextCursor(cursor)
                event.accept()
                return

        if event.modifiers() == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            self._smart_newline()
            return
        elif event.modifiers() == Qt.ControlModifier and key == Qt.Key_Slash:
            self._toggle_comment()
            return
        elif event.modifiers() == Qt.ControlModifier and key == Qt.Key_I:
            self.format_document()
            return

        if txt in ('(', ',') and self._lsp_ready: self._signature_timer.start(50)
        if txt and self._lsp_ready: self._hover_timer.start(300)

        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_button_position()

    def _update_button_position(self):
        if hasattr(self, 'fullscreen_button'):
            self.fullscreen_button.move(self.width() - 58, 6)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jedi Frontend + LSP Backend with CompletionWidget")
        self.setStyleSheet("background-color: #333; color: white;")
        self.resize(800, 600)
        self.find_replace = FindReplace(self, True)
        self.editor = LSPCodeEditor(python_exe_path=r"D:\work\CanvasMind\.venv\Scripts\python.exe")
        example_code = """import numpy as np
a = np.array([1, 2, 3])
# Try: a. then Backspace
def hello(x, y):
    z = x + y
    return z
result = hello(1, 2)"""
        self.editor.set_text(example_code)
        self.find_replace.set_editor(self.editor)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.find_replace)
        layout.addWidget(self.editor)
        self.setCentralWidget(central)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    win.editor.setFocus()
    sys.exit(app.exec_())