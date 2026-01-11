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
    CODE_PREFIX = """from app.components.base import BaseComponent, ArgumentType, PropertyType, PortDefinition, PropertyDefinition, ConnectionType\n\n\n"""

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

        # 缓存变更
        self._pending_changes = []
        # 修正行数统计：确保与 LSP 内部计算逻辑一致
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
        self._font_family = 'Consolas'
        self._current_font_size = 13
        # 编辑器设置
        self.setup_editor(
            language='python',
            color_scheme='spyder/dark',
            font=QFont('Consolas', 13),
            show_blanks=False,
            edge_line=True,
            auto_unindent=True,
            close_quotes=True,
            indent_guides=True,
            folding=True,
            markers=True,
            automatic_completions=True,
            automatic_completions_after_chars=2,
            completions_hint=True,
            completions_hint_after_ms=500,
            hover_hints=True,
            code_snippets=True,
            intelligent_backspace=True,
            underline_errors=True,
            highlight_current_line=True,
        )
        self.auto_completion_characters = ["."]
        # 按钮
        btn_text = "缩小" if dialog else "放大"
        self.fullscreen_button = TransparentToolButton(get_icon(btn_text), parent=self)
        self.fullscreen_button.setFixedSize(28, 28)
        self._update_button_position()

        # --- 关键：监听内容变更 ---
        self.cursorPositionChanged.connect(self._on_cursor_position_changed)
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

    # ========== 核心修复：稳健同步逻辑 ==========

    def _on_document_contents_change(self, position, chars_removed, chars_added):
        if not self._lsp_ready: return
        self._pending_changes.append((position, chars_removed, chars_added))
        # 缩短同步时间间隔，提高响应感
        self._lsp_sync_timer.start(50)

    def _sync_to_lsp(self):
        """
        优化：改用全量同步 didChange。
        在存在 CODE_PREFIX 的情况下，手动计算增量偏移极其容易出错（莫名红线的根源）。
        对于普通脚本大小，发送全量文本的开销微乎其微，但能保证服务器与编辑器绝对同步。
        """
        if not self._lsp_ready: return

        full_text = self._get_code_with_prefix()

        if not self._lsp_document_opened:
            self.lsp_session.open_document(full_text)
            self._lsp_document_opened = True
        else:
            try:
                # 这里我们清空暂存区，直接同步全文
                self.lsp_session.change_document_delta([{"text": full_text}])
            except Exception as e:
                logger.error(f"Sync failed: {e}")
                self.reopen_document()

        self._pending_changes.clear()
        self._folding_timer.start(800)

    def _on_lsp_initialized(self):
        self._lsp_ready = True
        self.lsp_signal.emit("ready")
        if self.toPlainText().strip(): self._sync_to_lsp()

    def _on_text_changed_for_lsp(self):
        pass

    def _get_code_with_prefix(self) -> str:
        code = self.toPlainText()
        # 优化判断：防止重复添加前缀
        if code.startswith(self.CODE_PREFIX[:20]):
            return code
        return self.CODE_PREFIX + code

    def _compute_text_changes(self, old_text: str, new_text: str) -> List[Dict]:
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
        tree = IntervalTree()
        regions = {}
        status = {}
        for fr in folding_ranges:
            start = fr['startLine'] + 1 - self._prefix_line_count
            end = fr['endLine'] + 1 - self._prefix_line_count
            if end > start:
                regions[start] = end
                status[start] = False
                tree[start:end + 1] = (start, end)
        self.folding_panel.update_folding((tree, FoldingRegion(None, None), regions, {}, {}, status))
        self.folding_panel.folding_regions = regions
        self.folding_panel.folding_status = status

    def format_document(self):
        if self._lsp_ready:
            self.lsp_session.request_formatting()

    def format_selection(self):
        if not self._lsp_ready: return
        cursor = self.textCursor()
        if cursor.hasSelection():
            self.lsp_session.request_range_formatting(
                self.document().findBlock(cursor.selectionStart()).blockNumber() + self._prefix_line_count, 0,
                self.document().findBlock(cursor.selectionEnd()).blockNumber() + self._prefix_line_count, 0
            )

    def _apply_formatting_edits(self, text_edits: List[Dict]):
        if not text_edits:
            return
        # 格式化通常返回全文，去除前缀
        new_text = text_edits[0]['newText']
        if new_text.startswith(self.CODE_PREFIX):
            new_text = new_text[self._prefix_char_count:]
        self.set_text(new_text)
        self.reopen_document()

    def reopen_document(self):
        if not self._lsp_ready: return
        self._lsp_sync_timer.stop()
        self._pending_changes.clear()
        full_code = self._get_code_with_prefix()
        try:
            self.lsp_session.close_document()
        except:
            pass
        self.lsp_session.open_document(full_code)
        self._lsp_document_opened = True
        self._folding_timer.start(500)

    def request_hover(self, line, col, offset, show_hint=True, clicked=True):
        self._show_hint = show_hint
        self._request_hover_clicked = clicked
        self.lsp_session.request_hover(line + self._prefix_line_count, col)

    def _on_hover_response(self, result):
        if result and result.get("contents"):
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
        cursor = self.textCursor()
        self.lsp_session.request_completion(
            cursor.blockNumber() + self._prefix_line_count, cursor.columnNumber()
        )

    def _trigger_signature_help(self):
        cursor = self.textCursor()
        self.lsp_session.request_signature_help(
            cursor.blockNumber() + self._prefix_line_count, cursor.columnNumber()
        )

    def _trigger_hover(self):
        cursor = self.textCursor()
        self.lsp_session.request_hover(
            cursor.blockNumber() + self._prefix_line_count, cursor.columnNumber()
        )

    def _get_completion_prefix(self) -> str:
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        start = pos
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] == '_'):
            start -= 1
        return text[start:pos]

    # ========== 核心修复：解决补全吞点逻辑 ==========

    def _on_lsp_completions_ready(self, completion_items: List[Dict]):
        """
        处理补全结果：极致防吞点逻辑
        """
        cursor = self.textCursor()
        current_pos = cursor.position()
        text = self.toPlainText()

        # 1. 基础起始位置计算
        start_pos = current_pos
        while start_pos > 0 and (text[start_pos - 1].isalnum() or text[start_pos - 1] == '_'):
            start_pos -= 1

        # 2. 核心修复：点号守卫
        # 如果光标就在点号后面，强制将 start_pos 设为当前位置
        # 这样替换范围的长度就是 0，不会触碰点号
        is_dot_trigger = False
        if current_pos > 0 and text[current_pos - 1] == '.':
            start_pos = current_pos
            is_dot_trigger = True

        clean_items = []
        for item in completion_items:
            label = item.get('label', '')
            kind = item.get('kind', 1)

            # 获取插入文本
            insert_text = item.get('insertText', label)

            # 3. 如果是点号触发，且 insertText 开头有句点，则去掉它
            # 防止出现 np..array 或替换逻辑误判
            if is_dot_trigger and insert_text.startswith('.'):
                insert_text = insert_text[1:]

            # 处理括号逻辑
            insert_format = 1
            if kind in (2, 3):  # Method, Function
                base_text = insert_text
                if '(' in base_text:
                    base_text = base_text.split('(')[0]

                # 检查是否需要参数
                has_args = False
                detail = item.get('detail', '')
                if '(' in detail and '()' not in detail:
                    has_args = True

                if has_args:
                    insert_text = f"{base_text}($1)"
                    insert_format = 2
                else:
                    insert_text = f"{base_text}()"

            # 构造 Spyder 格式
            item_data = {
                'label': label,
                'insertText': insert_text,
                'insertTextFormat': insert_format,
                'filterText': item.get('filterText', label),
                'sortText': item.get('sortText', label),
                'kind': kind,
                'documentation': item.get('documentation', ''),
                'detail': item.get('detail', ''),
                'point': start_pos,  # 统一使用修正后的锚点
                'resolve': True
            }

            if 'data' in item:
                item_data['data'] = item['data']

            clean_items.append(item_data)

        # 4. 这里的锚点必须与 item 里的 point 完全一致
        self.completion_args = (start_pos, True)

        try:
            # 检查是否有有效项
            if clean_items:
                self.process_completion({"params": clean_items})
            else:
                if self.completion_widget:
                    self.completion_widget.hide()
        except Exception as e:
            logger.error(f"Error processing completions: {e}")

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
                line = diag['range']['start']['line'] - self._prefix_line_count
                if line < 0: continue  # 过滤前缀部分的错误

                severity = diag.get('severity', 1)
                message = diag.get('message', '').strip()
                if not message: continue

                block = self.document().findBlockByNumber(line)
                if not block.isValid(): continue

                data = block.userData()
                if not data: data = BlockUserData(self)
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
                logger.error(f"[LSP] Diagnostic Error: {e}")

        if has_error:
            self.sig_flags_changed.emit()
            if hasattr(self, 'linenumberarea'):
                self.linenumberarea.update()

    def _smart_newline(self):
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

    def wheelEvent(self, event):
        """处理鼠标滚轮事件以缩放字体"""
        if event.modifiers() == Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._increase_font_size()
            else:
                self._decrease_font_size()
            event.accept()
        else:
            super().wheelEvent(event)

    def _increase_font_size(self):
        """增加字体大小"""
        if self._current_font_size < 30:
            self._current_font_size += 1
            self._apply_font()

    def _decrease_font_size(self):
        """减少字体大小"""
        if self._current_font_size > 8:
            self._current_font_size -= 1
            self._apply_font()

    def _apply_font(self):
        """应用当前字体设置"""
        font = QFont(self._font_family, self._current_font_size)
        self.set_font(font)

    def _on_cursor_position_changed(self):
        if not self._lsp_ready:
            return

        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()

        # 逻辑：如果光标左侧紧挨着 '(' 或者 ','，就说明可能需要签名提示
        if pos > 0:
            prev_char = text[pos - 1]
            if prev_char in ('(', ','):
                # 使用定时器防抖，避免光标快速移动时频繁请求
                self._signature_timer.start(100)

    def keyPressEvent(self, event):
        key = event.key()
        txt = event.text()
        # 在字符已经进入文档后，再判断
        if self._lsp_ready:
            # 如果刚才输入的是左括号或逗号
            if txt in ('(', ','):
                self._signature_timer.start(50)
            # 或者是回车（有时在函数参数里换行也需要提示）
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                self._signature_timer.start(50)
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
        self.editor = LSPCodeEditor(python_exe_path=r"python.exe")
        example_code = """import numpy as np
a = np.array([1, 2, 3])

# Try typing: a.
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