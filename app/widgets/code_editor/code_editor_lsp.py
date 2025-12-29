# -*- coding: utf-8 -*-
import re
import sys
from typing import List, Dict
from urllib.parse import quote

from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QCursor
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QApplication
from loguru import logger
from qfluentwidgets import TransparentToolButton
from spyder.plugins.editor.widgets.codeeditor import CodeEditor
from spyder.plugins.editor.widgets.completion import CompletionWidget
from spyder.widgets.findreplace import FindReplace
from spyder_kernels.utils.dochelpers import getobj

from app.server_manager.lsp_server.lsp_manager_stdio import LspClientManager
from app.utils.utils import get_icon


class LSPCodeEditor(CodeEditor):
    lsp_signal = pyqtSignal(str)
    CODE_PREFIX = """from app.components import BaseComponent, ArgumentType, PropertyType, PortDefinition, PropertyDefinition, ConnectionType


"""

    def __init__(self, parent=None, code_parent=None, python_exe_path=None, dialog=None):
        super().__init__()
        self.python_exe_path = python_exe_path or sys.executable
        self.parent_widget = parent
        self.code_parent = code_parent
        self._lsp_ready = False
        self._completing = False
        self._document_version = 0
        self._lsp_document_opened = False
        # --- 自定义补全词（CompletionWidget 会自动合并）---
        self.custom_completions = {
            'True', 'False', 'None', 'Exception', 'OSError', 'ValueError', 'TypeError',
            'print', 'input', 'open', 'range', 'enumerate', 'len', 'str', 'int', 'float',
            'list', 'dict', 'set', 'tuple', '__init__', '__name__', '__file__',
        }
        # === ✅ 使用 Spyder 的 CompletionWidget ===
        self.completion_widget = CompletionWidget(parent=self, ancestor=self.code_parent)
        # 深色背景
        self.completion_widget.setStyleSheet("background-color: #1E1E1E;")
        self.completion_widget.setMinimumWidth(350)
        self.completion_widget.setMinimumHeight(120)
        # --- 编辑器设置（必须启用 underline_errors 才能显示 ScrollFlagArea 图标）---
        font = QFont('Consolas', 13)
        self.setup_editor(
            language='python',
            color_scheme='spyder/dark',
            font=font,
            show_blanks=False,
            edge_line=True,
            auto_unindent=True,
            close_quotes=True,
            indent_guides=True,
            folding=True,
            markers=True,
            hover_hints=True,
            automatic_completions=True,  # ✅ 关键！
            automatic_completions_after_chars=1,
            intelligent_backspace=True,
            completions_hint=True,
            underline_errors=True,  # ✅ 必须为 True 才能显示行号前错误图标
            highlight_current_line=True,
        )
        self.auto_completion_characters = ["."]
        # --- 按钮 ---
        btn_text = "缩小" if dialog else "放大"
        self.fullscreen_button = TransparentToolButton(get_icon(btn_text), parent=self)
        self.fullscreen_button.setIconSize(QSize(28, 28))
        self.fullscreen_button.setFixedSize(28, 28)
        self.fullscreen_button.setToolTip("放大编辑器")
        self.spyder_button = TransparentToolButton(get_icon("spyder"), parent=self)
        self.spyder_button.setIconSize(QSize(28, 28))
        self.spyder_button.setFixedSize(28, 28)
        self.spyder_button.setToolTip("在 Spyder 中打开当前代码")
        self.spyder_button.clicked.connect(self._open_in_spyder)
        self._update_button_position()

        # --- LSP 同步 ---
        self._lsp_sync_timer = QTimer()
        self._lsp_sync_timer.setSingleShot(True)
        self._lsp_sync_timer.timeout.connect(self._sync_to_lsp)
        self.textChanged.connect(self._on_text_changed_for_lsp)

        # --- LSP 折叠 ---
        self._folding_timer = QTimer()
        self._folding_timer.setSingleShot(True)
        self._folding_timer.timeout.connect(self._request_folding)
        self.textChanged.connect(self._on_text_changed_for_folding)

        # --- Parso 语法检查（可选）---
        self._parso_timer = QTimer()
        self._parso_timer.setSingleShot(True)
        self._parso_timer.timeout.connect(self._run_parso_analysis)
        self.textChanged.connect(self._on_text_changed_for_parso)

        if hasattr(self, 'folding_panel') and self.folding_panel:
            self.folding_panel.folding_status = {}

    def set_completion_environment(self, python_exe: str = None):
        if python_exe is None:
            self.lsp_signal.emit("restarting...")
        else:
            self.lsp_signal.emit("starting")
        if hasattr(self, 'lsp_manager') and self.lsp_manager:
            self.lsp_manager.shutdown()

        self.lsp_manager = LspClientManager(python_path=python_exe or self.python_exe_path)
        self.lsp_manager.initialized.connect(self._on_lsp_initialized)
        self.lsp_manager.completion_ready.connect(self._on_lsp_completions_ready)
        self.lsp_manager.diagnostics_ready.connect(self._on_lsp_diagnostics_ready)
        self.lsp_manager.folding_ready.connect(self._on_lsp_folding_ready)
        self.lsp_manager.hover_ready.connect(self._on_hover_response)
        self.lsp_manager.definition_ready.connect(self._on_definition_response)
        self.lsp_manager.formatting_ready.connect(self._apply_formatting_edits)
        self.lsp_manager.error.connect(lambda e: self.lsp_signal.emit(str(e)))
        self.lsp_manager.start()

    # ========== LSP 集成 ==========
    def _document_uri(self) -> str:
        return "file://" + quote("/tmp/editor.py")

    def _on_lsp_initialized(self):
        self._lsp_ready = True
        self.lsp_signal.emit("ready")
        self.start_completion_services()  # ← LSPMixin 方法！
        code = self.toPlainText()
        if code.strip():
            self._sync_to_lsp()

    def _on_text_changed_for_lsp(self):
        if self._lsp_ready:
            self._lsp_sync_timer.start(10)

    def _on_text_changed_for_folding(self):
        if self._lsp_ready:
            self._folding_timer.start(800)

    def _get_code_with_prefix(self) -> str:
        """返回用于 LSP 分析的代码（含虚拟导入前缀）"""

        original_code = self.toPlainText()
        if original_code.startswith(self.CODE_PREFIX):
            # 防止重复添加（虽然一般不会）
            return original_code
        return self.CODE_PREFIX + original_code

    def _sync_to_lsp(self):
        if not self._lsp_ready:
            return
        code_for_lsp = self._get_code_with_prefix()  # ✅ 关键修改
        self._document_version += 1

        if not self._lsp_document_opened:
            self.lsp_manager.open_document(code_for_lsp)
            self._lsp_document_opened = True
        else:
            self.lsp_manager.change_document(code_for_lsp)
        self._request_folding()

    def _request_folding(self):
        if self._lsp_ready:
            self.lsp_manager.request_folding_ranges()

    def _on_lsp_folding_ready(self, folding_ranges: List[Dict]):
        if not hasattr(self, 'folding_panel') or not self.folding_panel:
            return
        from intervaltree import IntervalTree
        from spyder.plugins.editor.panels.utils import FoldingRegion
        current_tree = IntervalTree()
        folding_regions = {}
        folding_nesting = {}
        folding_levels = {}
        folding_status = {}
        for fr in folding_ranges:
            start = fr['startLine'] + 1 - len(self.CODE_PREFIX.splitlines())
            end = fr['endLine'] + 1 - len(self.CODE_PREFIX.splitlines())
            if end > start:
                folding_regions[start] = end
                folding_status[start] = False
                current_tree[start:end + 1] = (start, end)
                folding_levels[start] = 1
                folding_nesting[start] = []
        root = FoldingRegion(None, None)
        self.folding_panel.update_folding(
            (current_tree, root, folding_regions, folding_nesting, folding_levels, folding_status)
        )
        self.folding_panel.folding_regions = folding_regions
        self.folding_panel.folding_status = folding_status

    def format_document(self):
        """格式化整个文档"""
        if not self._lsp_ready:
            return
        self.lsp_manager.request_formatting()

    def format_selection(self):
        """格式化选中区域"""
        if not self._lsp_ready:
            return
        cursor = self.textCursor()
        if cursor.hasSelection():
            start_block = self.document().findBlock(cursor.selectionStart())
            end_block = self.document().findBlock(cursor.selectionEnd())
            # 注意：LSP 行号是 0-based
            start_line = start_block.blockNumber()
            start_col = 0
            end_line = end_block.blockNumber()
            end_col = end_block.length() - 1  # 包含换行符
            self.lsp_manager.request_range_formatting(start_line, start_col, end_line, end_col)

    def _apply_formatting_edits(self, text_edits: List[Dict]):
        """Apply LSP TextEdits to the document"""
        if not text_edits:
            return

        # 如果只有一个 edit 且覆盖全文（常见于 formatting），直接替换
        if len(text_edits) == 1:
            edit = text_edits[0]
            start = edit['range']['start']
            end = edit['range']['end']
            # 检查是否覆盖全文（从 0,0 开始，到最后一行）
            if start['line'] == 0 and start['character'] == 0:
                doc_lines = self.toPlainText().splitlines()
                last_line = len(doc_lines) - 1
                if end['line'] >= last_line and end['character'] == 0:
                    # 是全文替换！
                    new_text = edit['newText']
                    # 修复换行符
                    new_text = new_text.replace('\r\n', '\n').replace('\r', '\n')
                    # 但要移除 CODE_PREFIX（因为编辑器不显示它）
                    prefix_lines = len(self.CODE_PREFIX.splitlines())
                    actual_lines = new_text.splitlines()
                    if len(actual_lines) > prefix_lines:
                        # 剔除前缀部分
                        displayed_text = '\n'.join(actual_lines[prefix_lines:])
                    else:
                        displayed_text = new_text  # 安全兜底

                    cursor = self.textCursor()
                    cursor.beginEditBlock()
                    try:
                        cursor.select(QTextCursor.Document)  # 全选
                        cursor.insertText(displayed_text)
                    finally:
                        cursor.endEditBlock()
                    return

    def request_symbols(self):
        self.lsp_manager.request_symbols()

    def request_hover(self, line, col, offset, show_hint=True, clicked=True):
        self._show_hint = show_hint
        self._request_hover_clicked = clicked
        self.lsp_manager.request_hover(line + len(self.CODE_PREFIX.splitlines()), col)

    def _on_hover_response(self, result):
        if result["contents"]:
            self.handle_hover_response({"params": result["contents"]["value"]})

    def go_to_definition_from_cursor(self, cursor=None):
        if not self.go_to_definition_enabled or self.in_comment_or_string():
            return

        if cursor is None:
            cursor = self.textCursor()

        text = str(cursor.selectedText())

        if len(text) == 0:
            cursor.select(QTextCursor.WordUnderCursor)
            text = str(cursor.selectedText())

        if text is not None:
            line, column = self.get_cursor_line_column()
        self.lsp_manager.request_definition(line, column)

    def _on_definition_response(self, result):
        self.handle_go_to_definition({"params": result})

    def do_completion(self, automatic=True):
        """触发 LSP 补全请求（Spyder 风格）"""
        if not self._lsp_ready:
            return
        cursor = self.textCursor()
        line = cursor.blockNumber() + len(self.CODE_PREFIX.splitlines())  # 0-based
        col = cursor.columnNumber()  # 0-based
        self.lsp_manager.request_completion(line, col)

    # ========== 补全核心（使用 CompletionWidget）==========
    def _get_completion_prefix(self) -> str:
        cursor = self.textCursor()
        pos = cursor.position()
        if pos <= 0:
            return ""
        text = self.toPlainText()
        start = pos
        while start > 0:
            ch = text[start - 1]
            if ch.isalnum() or ch == '_':
                start -= 1
            else:
                break
        return text[start:pos]

    def _on_lsp_completions_ready(self, completion_items: List[Dict]):
        # ✅ 补全缺失的 filterText（用 label 代替）
        for item in completion_items:
            if 'filterText' not in item:
                item['filterText'] = item.get('label', '')
            if 'insertText' not in item:
                item['insertText'] = item.get('label', '')
            if 'kind' not in item:
                item['kind'] = 0  # 'unknown'
            if 'detail' not in item:
                item['detail'] = ''
            if 'documentation' not in item:
                item['documentation'] = ''
        self.completion_args = (self.textCursor().position(), True)
        params = {"params": completion_items}
        self.process_completion(params)

    # ========== 错误下划线 + 行号前图标 ==========
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
                    from spyder.plugins.editor.utils.editor import BlockUserData
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
                logger.error(f"[LSP] Error processing diagnostic: {e}")
        if has_error:
            self.sig_flags_changed.emit()  # ✅ 触发行号前错误图标
            if hasattr(self, 'linenumberarea'):
                self.linenumberarea.update()

    # ========== 其他功能（注释、折叠复制等）==========
    def _smart_newline(self):
        cursor = self.textCursor()
        current_line = cursor.block().text()
        leading_spaces = len(current_line) - len(current_line.lstrip(' '))
        indent = ' ' * leading_spaces
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText('\n' + indent)
        self.setTextCursor(cursor)

    def _toggle_comment(self):
        cursor = self.textCursor()
        doc = self.document()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        c1 = QTextCursor(doc)
        c1.setPosition(start)
        c1.movePosition(QTextCursor.StartOfLine)
        start_line_pos = c1.position()
        c2 = QTextCursor(doc)
        c2.setPosition(end)
        if c2.atBlockStart() and end > start:
            c2.movePosition(QTextCursor.Left)
            c2.movePosition(QTextCursor.EndOfLine)
        end_line_pos = c2.position()
        c1.setPosition(start_line_pos)
        c1.setPosition(end_line_pos, QTextCursor.KeepAnchor)
        lines = c1.selectedText().split('\u2029')
        def is_commented(s):
            return s.strip().startswith('#')
        all_commented = all(not t.strip() or is_commented(t) for t in lines)
        new_lines = []
        if all_commented:
            for t in lines:
                if not t.strip():
                    new_lines.append(t)
                else:
                    new_lines.append(re.sub(r'^(\s*)#\s?', r'\1', t))
        else:
            for t in lines:
                if not t.strip():
                    new_lines.append(t)
                else:
                    m = re.match(r'^(\s*)', t)
                    indent = m.group(1) if m else ''
                    new_lines.append(f"{indent}# {t[len(indent):]}")
        cursor.beginEditBlock()
        c1.insertText('\n'.join(new_lines))
        cursor.endEditBlock()

    def _copy_with_folding(self):
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        if start == end:
            block = cursor.block()
            line_number = block.blockNumber() + 1
            if (hasattr(self, 'folding_status') and
                line_number in self.folding_panel.folding_status and
                self.folding_panel.folding_status[line_number]):
                if (hasattr(self, 'folding_regions') and
                    line_number in self.folding_panel.folding_regions):
                    end_line = self.folding_panel.folding_regions[line_number]
                    start_pos = self.document().findBlockByNumber(line_number - 1).position()
                    end_block = self.document().findBlockByNumber(end_line - 1)
                    end_pos = end_block.position() + end_block.length() - 1
                    copy_cursor = QTextCursor(self.document())
                    copy_cursor.setPosition(start_pos)
                    copy_cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                    clipboard = QApplication.clipboard()
                    clipboard.setText(copy_cursor.selectedText())
                    return
        super().copy()

    def keyPressEvent(self, event):
        """Reimplement Qt method."""
        key = event.key()

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

        # 自定义快捷键
        if event.modifiers() == Qt.ShiftModifier and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._smart_newline()
            event.accept()
            return
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Slash:
            self._toggle_comment()
            event.accept()
            return
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_I:
            self.format_document()
            event.accept()
            return

        super().keyPressEvent(event)

    def _open_in_spyder(self):
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_button_position()

    def _update_button_position(self):
        if not hasattr(self, 'fullscreen_button'):
            return
        button_width = 28
        button_spacing = 8
        x = self.width() - button_width - 30
        y_top = 6
        y_bottom = y_top + button_width + button_spacing
        self.fullscreen_button.move(x, y_top)
        self.spyder_button.move(x, y_bottom)

    def _on_text_changed_for_parso(self):
        self._parso_timer.stop()
        self._parso_timer.start(800)

    def _run_parso_analysis(self):
        code = self.toPlainText()
        if not code.strip():
            self._clear_parso_results()
            return
        try:
            import parso
            grammar = parso.load_grammar()
            module = grammar.parse(code, error_recovery=True)
            errors = list(grammar.iter_errors(module))
        except Exception as e:
            logger.error(f"[Parso] Parse error: {e}")
            errors = []
        self._clear_parso_results()
        self.clear_extra_selections('parso_underline')
        error_color = QColor(self.error_color) if self.error_color else QColor("#ff0000")
        warning_color = QColor(self.warning_color) if self.warning_color else QColor("#ffaa00")
        for error in errors:
            try:
                line_number = error.start_pos[0]
                column_number = error.start_pos[1]
                message = error.message
                block = self.document().findBlockByNumber(line_number - 1)
                if not block.isValid():
                    continue
                data = block.userData()
                if not data:
                    from spyder.plugins.editor.utils.editor import BlockUserData
                    data = BlockUserData(self)
                block.setUserData(data)
                data.code_analysis.append(('parso', '', 2, message))
                data.color = error_color
                start_pos = block.position() + column_number
                end_pos = start_pos + 1
                cursor = QTextCursor(self.document())
                cursor.setPosition(start_pos)
                cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                self.highlight_selection(
                    'parso_underline',
                    cursor,
                    underline_color=error_color,
                    underline_style=QTextCharFormat.WaveUnderline
                )
            except Exception as e:
                logger.error(f"[Parso] Highlight error: {e}")
        self.sig_flags_changed.emit()
        if hasattr(self, 'linenumberarea'):
            self.linenumberarea.update()

    def _clear_parso_results(self):
        self.clear_extra_selections('parso_underline')
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if data and hasattr(data, 'code_analysis'):
                data.code_analysis = [x for x in data.code_analysis if x[0] != 'parso']
                if not data.code_analysis:
                    data.color = None
            block = block.next()


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