# -*- coding: utf-8 -*-
import re
import sys
import uuid
from typing import List, Dict
from urllib.parse import quote

from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QCursor
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QApplication
from loguru import logger
from qfluentwidgets import TransparentToolButton
from spyder.plugins.editor.widgets.codeeditor import CodeEditor
from spyder.plugins.editor.widgets.completion import CompletionWidget
from spyder.widgets.findreplace import FindReplace
from spyder_kernels.utils.dochelpers import getobj

from app.server_manager.lsp_server.lsp_manager_stdio import LspClientManager
from app.server_manager.lsp_server.lsp_manager_zmq import LspClientZMQManager
from app.utils.utils import get_icon


class LSPCodeEditor(CodeEditor):
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

        self.set_completion_environment(python_exe_path)

        # === ✅ 使用 Spyder 的 CompletionWidget ===
        self.completion_widget = CompletionWidget(parent=self, ancestor=self.code_parent)
        # 深色背景
        self.completion_widget.setStyleSheet("background-color: #1E1E1E;")
        self.completion_widget.setMinimumWidth(350)
        self.completion_widget.setMinimumHeight(200)
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

    def set_completion_environment(self, python_exe: str):
        if hasattr(self, 'lsp_manager') and self.lsp_manager:
            self.lsp_manager.shutdown()
        self.lsp_manager = LspClientManager(python_path=python_exe)
        self.lsp_manager.initialized.connect(self._on_lsp_initialized)
        self.lsp_manager.completion_ready.connect(self._on_lsp_completions_ready)
        self.lsp_manager.diagnostics_ready.connect(self._on_lsp_diagnostics_ready)
        self.lsp_manager.folding_ready.connect(self._on_lsp_folding_ready)
        self.lsp_manager.start()

    # ========== LSP 集成 ==========
    def _document_uri(self) -> str:
        return "file://" + quote("/tmp/editor.py")

    def _on_lsp_initialized(self):
        self._lsp_ready = True
        code = self.toPlainText()
        if code.strip():
            self._sync_to_lsp()

    def _on_text_changed_for_lsp(self):
        if self._lsp_ready:
            self._lsp_sync_timer.start(300)

    def _on_text_changed_for_folding(self):
        if self._lsp_ready:
            self._folding_timer.start(800)

    def _sync_to_lsp(self):
        if not self._lsp_ready:
            return
        code = self.toPlainText()
        self._document_version += 1

        # 第一次同步时发送 didOpen
        if not self._lsp_document_opened:
            self.lsp_manager.open_document(code)
            self._lsp_document_opened = True
        else:
            self.lsp_manager.change_document(code)
        self._request_folding()

    def _request_folding(self):
        if self._lsp_ready:
            self.lsp_manager.request_folding_ranges(self._document_uri())

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
            start = fr['startLine'] + 1
            end = fr['endLine'] + 1
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

    def do_completion(self, automatic=True):
        """触发 LSP 补全请求（Spyder 风格）"""
        if not self._lsp_ready:
            return
        cursor = self.textCursor()
        line = cursor.blockNumber()  # 0-based
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

        # ✅ 注入自定义补全（可选）
        current_prefix = self._get_completion_prefix().lower()
        for word in self.custom_completions:
            if word.lower().startswith(current_prefix):
                completion_items.append({
                    'label': word,
                    'kind': 6,  # variable
                    'detail': 'builtin',
                    'documentation': '',
                    'filterText': word,
                    'insertText': word
                })

        cursor_pos = self.textCursor().position()
        self.completion_widget.show_list(
            completion_list=completion_items,
            position=cursor_pos,
            automatic=True
        )

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
                line = diag['range']['start']['line']
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
        # 处理 Ctrl+C
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            self._copy_with_folding()
            event.accept()
            return

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

        if self.completions_hint_after_ms > 0:
            self._completions_hint_idle = False
            self._timer_completions_hint.start(self.completions_hint_after_ms)
        else:
            self._set_completions_hint_idle()

        # Only set overwrite mode during key handling to allow correct painting
        # of multiple overwrite cursors. Must unset overwrite before return.
        self.setOverwriteMode(self.overwrite_mode)
        self.start_cursor_blink()  # reset cursor blink by reseting timer
        if self.extra_cursors:
            self.handle_multi_cursor_keypress(event)
            self.setOverwriteMode(False)
            return

        # Send the signal to the editor's extension.
        event.ignore()
        self.sig_key_pressed.emit(event)

        self._last_pressed_key = key = event.key()
        self._last_key_pressed_text = text = str(event.text())
        has_selection = self.has_selected_text()
        ctrl = event.modifiers() & Qt.ControlModifier
        shift = event.modifiers() & Qt.ShiftModifier

        if text:
            self.clear_occurrences()

        if key in {Qt.Key_Up, Qt.Key_Left, Qt.Key_Right, Qt.Key_Down}:
            self.hide_tooltip()

        if key in {Qt.Key_PageUp, Qt.Key_PageDown}:
            self.hide_tooltip()
            self.hide_calltip()

        if event.isAccepted():
            # The event was handled by one of the editor extension.
            self.setOverwriteMode(False)
            return

        if key in [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt,
                   Qt.Key_Meta, Qt.KeypadModifier]:
            self.setOverwriteMode(False)
            # The user pressed only a modifier key.
            if event.modifiers() == self.mouse_shortcuts['goto_definition']:
                pos = self.mapFromGlobal(QCursor.pos())
                pos = self.calculate_real_position_from_global(pos)
                if self._handle_goto_uri_event(pos):
                    event.accept()
                    return

                if self._handle_goto_definition_event(pos):
                    event.accept()
                    return
            return

        # ---- Handle hard coded and builtin actions
        operators = {'+', '-', '*', '**', '/', '//', '%', '@', '<<', '>>',
                     '&', '|', '^', '~', '<', '>', '<=', '>=', '==', '!='}
        delimiters = {',', ':', ';', '@', '=', '->', '+=', '-=', '*=', '/=',
                      '//=', '%=', '@=', '&=', '|=', '^=', '>>=', '<<=', '**='}

        if text not in self.auto_completion_characters:
            if text in operators or text in delimiters:
                self.completion_widget.hide()
        if key in (Qt.Key_Enter, Qt.Key_Return):
            if not shift and not ctrl:
                if (
                    self.add_colons_enabled and
                    self.is_python_like() and
                    self.autoinsert_colons()
                ):
                    self.textCursor().beginEditBlock()
                    self.insert_text(':' + self.get_line_separator())
                    if self.strip_trailing_spaces_on_modify:
                        self.fix_and_strip_indent()
                    else:
                        self.fix_indent()
                    self.textCursor().endEditBlock()
                elif self.is_completion_widget_visible():
                    self.select_completion_list()
                else:
                    self.textCursor().beginEditBlock()
                    cur_indent = self.get_block_indentation(
                        self.textCursor().blockNumber())
                    self._handle_keypress_event(event)
                    # Check if we're in a comment or a string at the
                    # current position
                    cmt_or_str_cursor = self.in_comment_or_string()

                    # Check if the line start with a comment or string
                    cursor = self.textCursor()
                    cursor.setPosition(cursor.block().position(),
                                       QTextCursor.KeepAnchor)
                    cmt_or_str_line_begin = self.in_comment_or_string(
                        cursor=cursor)

                    # Check if we are in a comment or a string
                    cmt_or_str = cmt_or_str_cursor and cmt_or_str_line_begin

                    if self.strip_trailing_spaces_on_modify:
                        self.fix_and_strip_indent(
                            comment_or_string=cmt_or_str,
                            cur_indent=cur_indent)
                    else:
                        self.fix_indent(comment_or_string=cmt_or_str,
                                        cur_indent=cur_indent)
                    self.textCursor().endEditBlock()
        elif key == Qt.Key_Insert and not shift and not ctrl:
            self.overwrite_mode = not self.overwrite_mode
        elif key == Qt.Key_Backspace and not shift and not ctrl:
            if has_selection or not self.intelligent_backspace:
                self._handle_keypress_event(event)
            else:
                leading_text = self.get_text('sol', 'cursor')
                leading_length = len(leading_text)
                trailing_spaces = leading_length - len(leading_text.rstrip())
                trailing_text = self.get_text('cursor', 'eol')
                matches = ('()', '[]', '{}', '\'\'', '""')
                if (
                    not leading_text.strip() and
                    (leading_length > len(self.indent_chars))
                ):
                    if leading_length % len(self.indent_chars) == 0:
                        self.unindent()
                    else:
                        self._handle_keypress_event(event)
                elif trailing_spaces and not trailing_text.strip():
                    self.remove_suffix(leading_text[-trailing_spaces:])
                elif (
                    leading_text and
                    trailing_text and
                    (leading_text[-1] + trailing_text[0] in matches)
                ):
                    cursor = self.textCursor()
                    cursor.movePosition(QTextCursor.PreviousCharacter)
                    cursor.movePosition(QTextCursor.NextCharacter,
                                        QTextCursor.KeepAnchor, 2)
                    cursor.removeSelectedText()
                else:
                    self._handle_keypress_event(event)
        elif key == Qt.Key_Home:
            self.stdkey_home(shift, ctrl)
        elif key == Qt.Key_End:
            # See spyder-ide/spyder#495: on MacOS X, it is necessary to
            # redefine this basic action which should have been implemented
            # natively
            self.stdkey_end(shift, ctrl)
        elif (
            text in self.auto_completion_characters and
            self.automatic_completions
        ):
            self.insert_text(text)
            if text == ".":
                if not self.in_comment_or_string():
                    text = self.get_text('sol', 'cursor')
                    last_obj = getobj(text)
                    prev_char = text[-2] if len(text) > 1 else ''
                    if (
                        prev_char in {')', ']', '}'} or
                        (last_obj and not last_obj.isdigit())
                    ):
                        # Completions should be triggered immediately when
                        # an autocompletion character is introduced.
                        self.do_completion(automatic=True)
            else:
                self.do_completion(automatic=True)
        elif (
            text in self.signature_completion_characters and
            not self.has_selected_text()
        ):
            self.insert_text(text)
            self.request_signature()
        elif (
            key == Qt.Key_Colon and
            not has_selection and
            self.auto_unindent_enabled
        ):
            leading_text = self.get_text('sol', 'cursor')
            if leading_text.lstrip() in ('else', 'finally'):
                ind = lambda txt: len(txt) - len(txt.lstrip())
                prevtxt = str(self.textCursor().block().previous().text())
                if self.language == 'Python':
                    prevtxt = prevtxt.rstrip()
                if ind(leading_text) == ind(prevtxt):
                    self.unindent(force=True)
            self._handle_keypress_event(event)
        elif (
            key == Qt.Key_Space and
            not shift and
            not ctrl and
            not has_selection and
            self.auto_unindent_enabled
        ):
            self.completion_widget.hide()
            leading_text = self.get_text('sol', 'cursor')
            if leading_text.lstrip() in ('elif', 'except'):
                ind = lambda txt: len(txt)-len(txt.lstrip())
                prevtxt = str(self.textCursor().block().previous().text())
                if self.language == 'Python':
                    prevtxt = prevtxt.rstrip()
                if ind(leading_text) == ind(prevtxt):
                    self.unindent(force=True)
            self._handle_keypress_event(event)
        elif key == Qt.Key_Tab and not ctrl:
            # Important note: <TAB> can't be called with a QShortcut because
            # of its singular role with respect to widget focus management
            if not has_selection and not self.tab_mode:
                self.intelligent_tab()
            else:
                # indent the selected text
                self.indent_or_replace()
        elif key == Qt.Key_Backtab and not ctrl:
            # Backtab, i.e. Shift+<TAB>, could be treated as a QShortcut but
            # there is no point since <TAB> can't (see above)
            if not has_selection and not self.tab_mode:
                self.intelligent_backtab()
            else:
                # indent the selected text
                self.unindent()
            event.accept()
        elif not event.isAccepted():
            self._handle_keypress_event(event)

        if not event.modifiers():
            # Accept event to avoid it being handled by the parent.
            # Modifiers should be passed to the parent because they
            # could be shortcuts
            event.accept()

        self.setOverwriteMode(False)

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