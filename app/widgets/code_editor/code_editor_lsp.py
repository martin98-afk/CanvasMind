# -*- coding: utf-8 -*-
import re
import sys
from typing import List, Dict
from urllib.parse import quote

from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
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
    CODE_PREFIX = """from app.components import BaseComponent, ArgumentType, PropertyType, PortDefinition, PropertyDefinition, ConnectionType


"""

    def __init__(self, parent=None, code_parent=None, python_exe_path=None, dialog=None):
        super().__init__()
        self.python_exe_path = python_exe_path
        self.parent_widget = parent
        self.code_parent = code_parent
        self._lsp_ready = False
        self._completing = False
        self._request_hover_clicked = False
        self._show_hint = True
        self._document_version = 0
        self._lsp_document_opened = False
        self._last_lsp_content = ""  # ← 新增：记录上次发给 LSP 的内容

        # --- 自定义补全词 ---
        self.custom_completions = {
            'True', 'False', 'None', 'Exception', 'OSError', 'ValueError', 'TypeError',
            'print', 'input', 'open', 'range', 'enumerate', 'len', 'str', 'int', 'float',
            'list', 'dict', 'set', 'tuple', '__init__', '__name__', '__file__',
        }
        # --- LSP 集成 ---
        self.lsp_session = LspClientManager(python_path=self.python_exe_path)
        self.lsp_session.initialized.connect(self._on_lsp_initialized)
        self.lsp_session.completion_ready.connect(self._on_lsp_completions_ready)
        self.lsp_session.diagnostics_ready.connect(self._on_lsp_diagnostics_ready)
        self.lsp_session.folding_ready.connect(self._on_lsp_folding_ready)
        self.lsp_session.hover_ready.connect(self._on_hover_response)
        self.lsp_session.definition_ready.connect(self._on_definition_response)
        self.lsp_session.formatting_ready.connect(self._apply_formatting_edits)
        self.lsp_session.completion_resolved.connect(self._on_completion_resolved)
        self.lsp_session.signature_help_ready.connect(self._on_signature_help_response)  # ← 新增
        self.lsp_session.error.connect(lambda e: self.lsp_signal.emit(str(e)))

        # === ✅ CompletionWidget 配置 ===
        self.completion_widget = CompletionWidget(parent=self, ancestor=self.code_parent)
        self.completion_widget.sig_completion_hint.connect(self.show_hint_for_completion)
        self.completion_widget.setStyleSheet("background-color: #1E1E1E;")
        self.completion_widget.setMinimumWidth(350)
        self.completion_widget.setMinimumHeight(120)

        # --- 编辑器设置 ---
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
            automatic_completions=True,
            automatic_completions_after_chars=1,
            completions_hint=True,
            completions_hint_after_ms=500,
            hover_hints=True,
            code_snippets=True,
            intelligent_backspace=True,
            underline_errors=True,
            highlight_current_line=True,
        )
        self.auto_completion_characters = ["."]

        # --- 按钮 ---
        btn_text = "缩小" if dialog else "放大"
        self.fullscreen_button = TransparentToolButton(get_icon(btn_text), parent=self)
        self.fullscreen_button.setIconSize(QSize(28, 28))
        self.fullscreen_button.setFixedSize(28, 28)
        self.fullscreen_button.setToolTip("放大编辑器")
        self._update_button_position()

        # --- LSP 同步（增量更新 + 防抖）---
        self._lsp_sync_timer = QTimer()
        self._lsp_sync_timer.setSingleShot(True)
        self._lsp_sync_timer.timeout.connect(self._sync_to_lsp)

        # --- 高频请求防抖 ---
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
        # --- 连接信号 ---
        self.textChanged.connect(self._on_text_changed_for_lsp)

        if hasattr(self, 'folding_panel') and self.folding_panel:
            self.folding_panel.folding_status = {}

    def set_completion_environment(self, python_exe: str = None):
        self._lsp_document_opened = False
        if python_exe is None:
            self.lsp_signal.emit("restarting...")
        else:
            self.python_exe_path = python_exe
            self.lsp_signal.emit("starting")
        if hasattr(self, 'lsp_session') and self.lsp_session:
            self.lsp_session.stop()

        self.lsp_session.set_python_path(self.python_exe_path)
        self.lsp_session.start()

    # ========== LSP 集成 ==========

    def _on_lsp_initialized(self):
        self._lsp_ready = True
        self.lsp_signal.emit("ready")
        code = self.toPlainText()
        if code.strip():
            self._sync_to_lsp()

    def _on_text_changed_for_lsp(self):
        if self._lsp_ready:
            self._lsp_sync_timer.start(30)  # ← 防抖 30ms

    def _get_code_with_prefix(self) -> str:
        original_code = self.toPlainText()
        if original_code.startswith(self.CODE_PREFIX):
            return original_code
        return self.CODE_PREFIX + original_code

    # === 增量更新核心 ===
    def _compute_text_changes(self, old_text: str, new_text: str) -> List[Dict]:
        """使用 Spyder 内置 differ 生成字符级增量变更"""
        if old_text == new_text:
            return []
        if not old_text:
            return [{"text": new_text}]
        if not new_text:
            # 删除全文
            lines = old_text.splitlines(keepends=True)
            last_line = len(lines) - 1
            last_char = len(lines[-1]) if lines else 0
            return [{
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": last_line, "character": last_char}
                },
                "text": ""
            }]

        # 使用 Spyder 内置 differ
        diffs = self.differ.diff_main(old_text, new_text, checklines=True)

        changes = []

        old_pos = 0  # 字符位置（用于计算 range）
        new_pos = 0

        i = 0
        while i < len(diffs):
            op, text = diffs[i]
            if op == self.differ.DIFF_EQUAL:
                old_pos += len(text)
                new_pos += len(text)
                i += 1
            else:
                # 找到一段连续的 DELETE/INSERT
                start_old = old_pos
                delete_text = ""
                insert_text = ""

                # 合并连续的非 EQUAL 操作
                while i < len(diffs) and diffs[i][0] != self.differ.DIFF_EQUAL:
                    op, txt = diffs[i]
                    if op == self.differ.DIFF_DELETE:
                        delete_text += txt
                        old_pos += len(txt)
                    elif op == self.differ.DIFF_INSERT:
                        insert_text += txt
                        new_pos += len(txt)
                    i += 1

                # 计算 range（基于 old_text）
                start_line, start_char = self._pos_to_line_col(old_text, start_old)
                end_line, end_char = self._pos_to_line_col(old_text, start_old + len(delete_text))

                changes.append({
                    "range": {
                        "start": {"line": start_line, "character": start_char},
                        "end": {"line": end_line, "character": end_char}
                    },
                    "text": insert_text
                })

        return changes

    def _pos_to_line_col(self, text: str, pos: int) -> tuple[int, int]:
        """将字符位置转换为 (line, character)（LSP 行号从 0 开始）"""
        if pos <= 0:
            return (0, 0)
        lines = text.splitlines(keepends=True)
        current_pos = 0
        for line_idx, line in enumerate(lines):
            if current_pos + len(line) >= pos:
                return (line_idx, pos - current_pos)
            current_pos += len(line)
        # 超出范围，返回末尾
        return (len(lines), 0)

    def _sync_to_lsp(self):
        if not self._lsp_ready:
            return
        code_for_lsp = self._get_code_with_prefix()

        if not self._lsp_document_opened:
            self.lsp_session.open_document(code_for_lsp)
            self._lsp_document_opened = True
            self._last_lsp_content = code_for_lsp
        else:
            changes = self._compute_text_changes(self._last_lsp_content, code_for_lsp)
            if changes:
                self.lsp_session.change_document_delta(changes)
                self._last_lsp_content = code_for_lsp

        self._folding_timer.start(800)

    def _request_folding(self):
        if self._lsp_ready:
            self.lsp_session.request_folding_ranges()

    def _on_lsp_folding_ready(self, folding_ranges: List[Dict]):
        if not hasattr(self, 'folding_panel') or not self.folding_panel:
            return
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
        if not self._lsp_ready:
            return
        self.lsp_session.request_formatting()

    def format_selection(self):
        if not self._lsp_ready:
            return
        cursor = self.textCursor()
        if cursor.hasSelection():
            start_block = self.document().findBlock(cursor.selectionStart())
            end_block = self.document().findBlock(cursor.selectionEnd())
            start_line = start_block.blockNumber()
            start_col = 0
            end_line = end_block.blockNumber()
            end_col = end_block.length() - 1
            self.lsp_session.request_range_formatting(start_line, start_col, end_line, end_col)

    def _apply_formatting_edits(self, text_edits: List[Dict]):
        if not text_edits:
            return
        if len(text_edits) == 1:
            edit = text_edits[0]
            start = edit['range']['start']
            end = edit['range']['end']
            if start['line'] == 0 and start['character'] == 0:
                doc_lines = self.toPlainText().splitlines()
                last_line = len(doc_lines) - 1
                if end['line'] >= last_line and end['character'] == 0:
                    new_text = edit['newText'].replace('\r\n', '\n').replace('\r', '\n')
                    prefix_lines = len(self.CODE_PREFIX.splitlines())
                    actual_lines = new_text.splitlines()
                    displayed_text = '\n'.join(actual_lines[prefix_lines:]) if len(actual_lines) > prefix_lines else new_text
                    cursor = self.textCursor()
                    cursor.beginEditBlock()
                    try:
                        cursor.select(QTextCursor.Document)
                        cursor.insertText(displayed_text)
                    finally:
                        cursor.endEditBlock()
                    return
            self.reopen_document()

    def reopen_document(self):
        code_for_lsp = self._get_code_with_prefix()
        # 重置 LSP 文档：先关闭再打开（最可靠）
        self.lsp_session.close_document()
        self.lsp_session.open_document(code_for_lsp)  # ← 使用全量替换
        # 更新本地记录，确保下次增量更新正确
        self._last_lsp_content = code_for_lsp
        self._lsp_document_opened = True
        self._sync_to_lsp()

    def request_hover(self, line, col, offset, show_hint=True, clicked=True):
        self._show_hint = show_hint
        self._request_hover_clicked = clicked
        self.lsp_session.request_hover(line + len(self.CODE_PREFIX.splitlines()), col)

    def _on_hover_response(self, result):
        if result.get("contents"):
            contents = result["contents"]
            if isinstance(contents, dict):
                value = contents.get("value", "")
            else:
                value = str(contents)
            self.handle_hover_response({"params": value})

    def go_to_definition_from_cursor(self, cursor=None):
        if not self.go_to_definition_enabled or self.in_comment_or_string():
            return
        if cursor is None:
            cursor = self.textCursor()
        text = str(cursor.selectedText())
        if len(text) == 0:
            cursor.select(QTextCursor.WordUnderCursor)
            text = str(cursor.selectedText())
        if text:
            line, column = self.get_cursor_line_column()
            self.lsp_session.request_definition(line, column)

    def _on_definition_response(self, result):
        self.handle_go_to_definition({"params": result})

    # ========== 补全 & Hint ==========

    def do_completion(self, automatic=True):
        if not self._lsp_ready:
            return
        self._completion_timer.start(80)  # ← 防抖

    def _trigger_completion(self):
        cursor = self.textCursor()
        line = cursor.blockNumber() + len(self.CODE_PREFIX.splitlines())
        col = cursor.columnNumber()
        self.lsp_session.request_completion(line, col)

    def _trigger_signature_hint_if_needed(self, event):
        if event.text() in ('(', ',') and self._lsp_ready:
            self._signature_timer.start(50)
            return True
        return False

    def _trigger_signature_help(self):
        cursor = self.textCursor()
        line = cursor.blockNumber() + len(self.CODE_PREFIX.splitlines())
        col = cursor.columnNumber()
        self.lsp_session.request_signature_help(line, col)

    def _trigger_hover(self):
        cursor = self.textCursor()
        line = cursor.blockNumber() + len(self.CODE_PREFIX.splitlines())
        col = cursor.columnNumber()
        self.lsp_session.request_hover(line, col)

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
        cursor = self.textCursor()
        cursor_position = cursor.position()
        for item in completion_items:
            item.setdefault('filterText', item.get('label', ''))
            item.setdefault('insertText', item.get('label', ''))
            item.setdefault('kind', 0)
            item.setdefault('detail', '')
            item.setdefault('documentation', '')
            item['point'] = cursor_position
            item['resolve'] = True
        self.completion_args = (cursor_position, True)
        params = {"params": completion_items}
        self.process_completion(params)

    def resolve_completion_item(self, item):
        # 移除非标准字段
        clean_item = {k: v for k, v in item.items() if k in {
            'label', 'kind', 'detail', 'documentation', 'insertText', 'filterText',
            'textEdit', 'additionalTextEdits', 'command', 'data', 'tags',
            'insertTextFormat', 'commitCharacters', 'preselect'
        }}
        self.lsp_session.request_completion_resolve(clean_item)

    def _on_completion_resolved(self, resolved_item):
        # ← 关键：触发 tooltip 显示
        cw = self.completion_widget
        if cw.isVisible() and hasattr(cw, 'current_selected_item_label'):
            if cw.current_selected_item_label == resolved_item.get('label'):
                if isinstance(resolved_item.get('documentation'), dict):
                    resolved_item['documentation'] = resolved_item['documentation'].get('value', '')
                cw.augment_completion_info(resolved_item)

    def _on_signature_help_response(self, result):
        if not result or not result.get('signatures'):
            return

            # Spyder 只支持单个签名，取 activeSignature（默认为 0）
        active_sig_index = result.get('activeSignature', 0)
        signatures_list = result['signatures']

        if not signatures_list:
            return

        # 确保索引安全
        if active_sig_index >= len(signatures_list):
            active_sig_index = 0

        signature_data = signatures_list[active_sig_index]  # ← 取单个 dict

        # 提取 documentation
        doc = signature_data.get('documentation', '')
        if isinstance(doc, dict):
            doc = doc.get('value', '')

        # 提取 active parameter label
        parameter = None
        active_param_idx = result.get('activeParameter', 0)
        parameters = signature_data.get('parameters', [])
        if parameters and active_param_idx < len(parameters):
            param_data = parameters[active_param_idx]
            # 参数 label 可能是字符串或 [start, end]
            param_label = param_data.get('label', '')
            if isinstance(param_label, list) and len(param_label) == 2:
                # 如果是 [start, end]，需要从 signature label 中截取
                # 但 Spyder 的 show_calltip 期望字符串，这里简化处理
                param_label = str(param_label)
            parameter = param_label

        # 构造 Spyder 兼容的格式
        spyder_params = {
            "params": {
                "signatures": {
                    "label": signature_data['label'],
                    "documentation": doc,
                    "parameters": parameters  # 虽然 Spyder 可能不用，但保留
                },
                "activeParameter": active_param_idx
            }
        }
        self.process_signatures(spyder_params)

    # ========== 错误处理 & 其他 ==========

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
                logger.error(f"[LSP] Error processing diagnostic: {e}")
        if has_error:
            self.sig_flags_changed.emit()
            if hasattr(self, 'linenumberarea'):
                self.linenumberarea.update()

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

        # === 你的原有智能回车逻辑（完全保留）===
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

        # === 你的原有快捷键（完全保留）===
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

        # === 新增：触发 signature hint（只在输入 ( 或 , 时）===
        if event.text() in ('(', ',') and self._lsp_ready:
            self._signature_timer.start(50)  # 防抖 50ms

        # === 新增：触发 hover（任意文本输入后）===
        if event.text() and self._lsp_ready:
            self._hover_timer.start(300)  # 防抖 300ms

        # === 最后调用父类（确保所有默认行为正常）===
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_button_position()

    def _update_button_position(self):
        if not hasattr(self, 'fullscreen_button'):
            return
        button_width = 28
        x = self.width() - button_width - 30
        y_top = 6
        self.fullscreen_button.move(x, y_top)


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