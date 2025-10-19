# -*- coding: utf-8 -*-
import ast
import keyword
import builtins
from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QRect, QSize, QPoint
from PyQt5.QtGui import QFont, QTextCursor, QTextOption, QColor, QPainter, QTextFormat, QPalette, QTextCharFormat, \
    QTextBlockUserData
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QTextEdit, QShortcut, QToolTip, QHBoxLayout, \
    QLineEdit, QPushButton, QCheckBox, QLabel, QInputDialog
import os
import re
import subprocess
import sys
import tempfile
from qfluentwidgets import PlainTextEdit, TextEdit
from app.utils.python_syntax_highlighter import PythonSyntaxHighlighter
from app.widgets.code_editor_spyder import JediCodeEditor

DEFAULT_CODE_TEMPLATE = '''class Component(BaseComponent):
    name = ""
    category = ""
    description = ""
    requirements = ""
    inputs = [
    ]
    outputs = [
    ]
    properties = {
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        input_data = inputs.get("input_data") if inputs else None
        param1 = params.get("param1", "default_value")
        # 处理逻辑
        result = f"处理结果: {input_data} + {param1}"
        return {
            "output_data": result
        }
'''


# ---------------- 主部件 ----------------
class CodeEditorWidget(QWidget):
    code_changed = pyqtSignal()
    parsed_component = pyqtSignal(dict)

    def __init__(self, parent=None, python_exe=None, popup_offset=0):
        super().__init__()
        self.code_editor = JediCodeEditor(parent, self, python_exe_path=python_exe, popup_offset=popup_offset)
        self.code_editor.textChanged.connect(self.code_changed)
        self._setup_auto_sync()
        self._setup_ui()
        # self._setup_syntax_highlighting()
        self._setup_shortcuts()
        self._suspend_sync_depth = 0

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.code_editor.add_custom_completions(
            [
                'global_variable', 'Exception',  # 内置常量
                'True', 'False', 'None',

                # 内置异常
                'Exception', 'ValueError', 'TypeError', 'RuntimeError',
                'KeyError', 'IndexError', 'AttributeError', 'ImportError',
                'OSError', 'FileNotFoundError', 'PermissionError',

                # 常用内置函数（作为变量名也可能出现）
                'float', 'list', 'dict', 'tuple',
                'print', 'input', 'open', 'range', 'enumerate',
                'sorted', 'reversed','filter', 'enumerate',
                'type', 'isinstance', 'issubclass', 'hasattr', 'getattr', 'setattr', 'delattr', 'vars',
                'locals', 'eval', 'exec',  'repr', 'complex', 'round', 'strip', 'split', 'join', 'replace', 'lower',

                # 常见日志/调试变量
                'logger', 'debug', 'info', 'warning', 'error',

                # 常见 self 属性（提示用户可能想输入的）
                'self',
            ]
        )
        self.replace_text_preserving_view(DEFAULT_CODE_TEMPLATE)
        self.find_panel = self._create_find_replace_panel()
        self.find_panel.setVisible(False)
        layout.addWidget(self.find_panel)
        layout.addWidget(self.code_editor)
        self.status_label = QLabel("Ln 1, Col 1", self)
        self.status_label.setStyleSheet("color:#9aa0a6; padding:3px 6px; background:transparent;")
        layout.addWidget(self.status_label)
        self.code_editor.cursorPositionChanged.connect(self._update_status_label)

    def _setup_auto_sync(self):
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._parse_and_sync)

    def _setup_shortcuts(self):
        QShortcut(Qt.CTRL + Qt.Key_F, self.code_editor, activated=self._toggle_find_panel)
        QShortcut(Qt.Key_F3, self.code_editor, activated=lambda: self._find_next(backward=False))
        QShortcut(Qt.SHIFT + Qt.Key_F3, self.code_editor, activated=lambda: self._find_next(backward=True))
        QShortcut(Qt.CTRL + Qt.Key_H, self.code_editor, activated=lambda: self._toggle_find_panel(focus_replace=True))
        QShortcut(Qt.CTRL + Qt.Key_G, self.code_editor, activated=self._goto_line)
        QShortcut(Qt.CTRL + Qt.Key_Slash, self.code_editor, activated=self._toggle_comment)
        QShortcut(Qt.CTRL + Qt.Key_D, self.code_editor, activated=self._duplicate_line)

    def _create_find_replace_panel(self):
        panel = QWidget(self)
        h = QHBoxLayout(panel)
        h.setContentsMargins(6, 6, 6, 6)
        self.find_input = QLineEdit(panel)
        self.find_input.setPlaceholderText("Find")
        self.chk_regex = QCheckBox("Regex", panel)
        self.chk_case = QCheckBox("Aa", panel)
        btn_prev = QPushButton("Prev", panel)
        btn_next = QPushButton("Next", panel)
        self.replace_input = QLineEdit(panel)
        self.replace_input.setPlaceholderText("Replace")
        btn_replace = QPushButton("Replace", panel)
        btn_replace_all = QPushButton("All", panel)
        self.lbl_hits = QLabel("", panel)
        h.addWidget(self.find_input)
        h.addWidget(self.chk_regex)
        h.addWidget(self.chk_case)
        h.addWidget(btn_prev)
        h.addWidget(btn_next)
        h.addSpacing(12)
        h.addWidget(self.replace_input)
        h.addWidget(btn_replace)
        h.addWidget(btn_replace_all)
        h.addSpacing(12)
        h.addWidget(self.lbl_hits)
        btn_prev.clicked.connect(lambda: self._find_next(backward=True))
        btn_next.clicked.connect(lambda: self._find_next(backward=False))
        btn_replace.clicked.connect(self._replace_once)
        btn_replace_all.clicked.connect(self._replace_all)
        self.find_input.textChanged.connect(self._update_find_highlight)
        self.find_input.returnPressed.connect(lambda: self._find_next(backward=False))
        self.replace_input.returnPressed.connect(self._replace_once)
        panel.setStyleSheet("""
            QWidget { background: #202124; }
            QLineEdit { background:#2b2d30; color:#e8eaed; border:1px solid #3c4043; padding:3px 6px; }
            QLabel { color:#9aa0a6; }
            QCheckBox { color:#c0c4c9; }
            QPushButton { background:#303134; color:#e8eaed; border:1px solid #3c4043; padding:3px 6px; }
            QPushButton:hover { background:#3a3b3e; }
        """)
        return panel

    # ===== Find/Replace =====
    def _toggle_find_panel(self, focus_replace=False):
        self.find_panel.setVisible(not self.find_panel.isVisible())
        if self.find_panel.isVisible():
            sel = self.code_editor.textCursor().selectedText().replace('\u2029', '\n')
            if sel and '\n' not in sel:
                self.find_input.setText(sel)
            (self.replace_input if focus_replace else self.find_input).setFocus()

    def _find_next(self, backward=False):
        pat = self._pattern()
        if not pat:
            return
        doc_text = self.get_code()
        cursor = self.code_editor.textCursor()
        pos = cursor.position()
        self._highlight_all_matches(pat, doc_text)
        if backward:
            hay = doc_text[:pos]
            matches = list(pat.finditer(hay))
            if not matches:
                return
            m = matches[-1]
        else:
            m = pat.search(doc_text, pos)
            if not m:
                m = pat.search(doc_text, 0)
                if not m:
                    return
        start, end = m.start(), m.end()
        self._set_selection(start, end)
        self._update_hits_count(pat, doc_text)

    def _pattern(self):
        text = self.find_input.text()
        if not text:
            return None
        flags = 0 if self.chk_case.isChecked() else re.IGNORECASE
        try:
            if self.chk_regex.isChecked():
                return re.compile(text, flags)
            return re.compile(re.escape(text), flags)
        except re.error:
            return None

    def _replace_all_text(self, new_text):
        scrollbar = self.code_editor.verticalScrollBar()
        scroll_pos = scrollbar.value()
        tc = self.code_editor.textCursor()
        sel_start = tc.selectionStart()
        sel_end = tc.selectionEnd()
        tc.beginEditBlock()
        tc.select(QTextCursor.Document)
        tc.insertText(new_text)
        tc.endEditBlock()
        self.code_editor.setTextCursor(tc)
        if sel_start != sel_end:
            tc.setPosition(max(0, min(sel_start, len(new_text))))
            tc.setPosition(max(0, min(sel_end, len(new_text))), QTextCursor.KeepAnchor)
            self.code_editor.setTextCursor(tc)
        scrollbar.setValue(scroll_pos)

    def _highlight_all_matches(self, pat, text):
        try:
            extras = [e for e in self.code_editor.extraSelections() if getattr(e, 'searchHighlight', False) is False]
        except Exception:
            extras = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('#3949ab'))
        fmt.setForeground(QColor('#ffffff'))
        for m in pat.finditer(text):
            cur = self.code_editor.textCursor()
            cur.setPosition(m.start())
            cur.setPosition(m.end(), QTextCursor.KeepAnchor)
            ex = QTextEdit.ExtraSelection()
            ex.format = fmt
            ex.cursor = cur
            ex.searchHighlight = True
            extras.append(ex)
        self.code_editor.setExtraSelections(extras)

    def _set_selection(self, start, end):
        cursor = self.code_editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.code_editor.setTextCursor(cursor)
        self.code_editor.centerCursor()

    def _update_hits_count(self, pat, text):
        try:
            count = len(list(pat.finditer(text)))
        except Exception:
            count = 0
        self.lbl_hits.setText(f"{count} hits")

    def _update_find_highlight(self):
        pat = self._pattern()
        if not pat:
            self.lbl_hits.setText("")
            return
        self._update_hits_count(pat, self.get_code())

    def _replace_once(self):
        sel = self.code_editor.textCursor().selectedText().replace('\u2029', '\n')
        pat = self._pattern()
        if not pat:
            return
        replacement = self.replace_input.text()
        if sel:
            try:
                new_text = pat.sub(replacement, sel, count=1)
            except Exception:
                return
            self.code_editor.textCursor().insertText(new_text)
            return
        self._find_next(backward=False)

    def _replace_all(self):
        pat = self._pattern()
        if not pat:
            return
        replacement = self.replace_input.text()
        text = self.get_code()
        try:
            new_text, n = pat.subn(replacement, text)
        except Exception:
            return
        if n > 0:
            self.replace_text_preserving_view(new_text)
            self.lbl_hits.setText(f"{n} replaced")

    def _handle_shift_enter(self, cursor):
        cursor.movePosition(QTextCursor.EndOfLine)
        current_line = cursor.block().text()
        leading_spaces = len(current_line) - len(current_line.lstrip(' '))
        indent = ' ' * leading_spaces
        cursor.insertText('\n' + indent)
        self.code_editor.setTextCursor(cursor)

    def _toggle_comment(self):
        cursor = self.code_editor.textCursor()
        doc = self.code_editor.document()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        c = QTextCursor(doc)
        c.setPosition(start)
        c.movePosition(QTextCursor.StartOfLine)
        start_line_pos = c.position()
        c.setPosition(end)
        if c.atBlockStart() and end > start:
            c.movePosition(QTextCursor.Left)
        c.movePosition(QTextCursor.EndOfLine)
        end_line_pos = c.position()
        c.setPosition(start_line_pos)
        c.setPosition(end_line_pos, QTextCursor.KeepAnchor)
        lines = c.selectedText().split('\u2029')

        def is_commented(s):
            return bool(re.match(r"^\s*#", s))

        all_commented = all((t.strip() == '' or is_commented(t)) for t in lines)
        new_lines = []
        if all_commented:
            for t in lines:
                if not t.strip():
                    new_lines.append(t)
                    continue
                new_lines.append(re.sub(r"^(\s*)#\s?", r"\1", t))
        else:
            for t in lines:
                if not t.strip():
                    new_lines.append(t)
                else:
                    m = re.match(r"^(\s*)", t)
                    indent = m.group(1) if m else ''
                    new_lines.append(f"{indent}# " + t[len(indent):])
        cursor.beginEditBlock()
        c.insertText("\n".join(new_lines))
        cursor.endEditBlock()

    def _duplicate_line(self):
        cursor = self.code_editor.textCursor()
        cursor.select(QTextCursor.LineUnderCursor)
        line = cursor.selectedText().replace('\u2029', '')
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText('\n' + line)

    def _on_text_changed(self):
        self.code_changed.emit()
        self._sync_timer.start(800)

    def _parse_and_sync(self):
        try:
            code = self.code_editor.toPlainText()
            if not code.strip():
                return
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "Component":
                    self._parse_component_class(node, code)
                    break
        except SyntaxError:
            pass
        except Exception as e:
            print(f"解析代码失败: {e}")

    def _parse_component_class(self, class_node, code):
        component_info = {"name": "", "category": "", "description": ""}
        for stmt in class_node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Str):
                    if target.id in component_info:
                        component_info[target.id] = stmt.value.s
        self.parsed_component.emit(component_info)

    def _update_status_label(self):
        cur = self.code_editor.textCursor()
        ln = cur.blockNumber() + 1
        col = cur.positionInBlock() + 1
        self.status_label.setText(f"Ln {ln}, Col {col}")

    def _goto_line(self):
        cur = self.code_editor.textCursor()
        ln = cur.blockNumber() + 1
        num, ok = QInputDialog.getInt(self, "Go to Line", "Line number:", ln, 1, 10 ** 9, 1)
        if not ok:
            return
        cursor = self.code_editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        if num > 1:
            cursor.movePosition(QTextCursor.Down, n=num - 1)
        self.code_editor.setTextCursor(cursor)
        self.code_editor.centerCursor()

    def get_code(self):
        return self.code_editor.toPlainText().replace('\r\n', '\n').replace('\r', '\n')

    def set_code(self, code):
        self.replace_text_preserving_view(code)

    def suspend_sync(self):
        self._suspend_sync_depth += 1

    def resume_sync(self):
        if self._suspend_sync_depth > 0:
            self._suspend_sync_depth -= 1

    def replace_text_preserving_view(self, new_text: str):
        doc_text = self.get_code()
        if new_text == doc_text:
            return
        scrollbar = self.code_editor.verticalScrollBar()
        scroll_pos = scrollbar.value()
        cursor = self.code_editor.textCursor()
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        self.code_editor.blockSignals(True)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(new_text.replace('\r\n', '\n').replace('\r', '\n'))
        cursor.endEditBlock()
        self.code_editor.blockSignals(False)
        c = self.code_editor.textCursor()
        if sel_start != sel_end:
            c.setPosition(max(0, min(sel_start, len(new_text))))
            c.setPosition(max(0, min(sel_end, len(new_text))), QTextCursor.KeepAnchor)
        else:
            c.setPosition(max(0, min(cursor.position(), len(new_text))))
        self.code_editor.setTextCursor(c)
        scrollbar.setValue(scroll_pos)
