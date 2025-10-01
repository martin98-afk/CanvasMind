# -*- coding: utf-8 -*-
import ast

from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont, QTextCursor, QTextOption
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import TextEdit as FluentTextEdit

from app.utils.python_syntax_highlighter import PythonSyntaxHighlighter


DEFAULT_CODE_TEMPLATE = '''class Component(BaseComponent):
    name = ""
    category = ""
    description = ""
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


class CodeEditorWidget(QWidget):
    """代码编辑器 - 支持Python语法高亮、自动缩进、智能括号、同步UI"""

    code_changed = pyqtSignal()
    parsed_component = pyqtSignal(dict)   # 新增：解析后的组件信息（name/category/description）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_auto_sync()
        self._setup_ui()
        self._setup_syntax_highlighting()

    # ---------------- UI 相关 ----------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.code_editor = FluentTextEdit()
        font = QFont("Consolas", 10)
        self.code_editor.setFont(font)

        # === 关键：符合Python编码习惯的设置 ===
        self.code_editor.setTabStopDistance(4 * self.code_editor.fontMetrics().horizontalAdvance(' '))  # Tab 显示为4空格宽
        self.code_editor.setTabChangesFocus(False)  # Tab 不切换焦点，用于缩进
        self.code_editor.setWordWrapMode(QTextOption.WrapMode.NoWrap)  # 不自动换行（代码编辑器通常如此）
        self.code_editor.setLineWrapMode(FluentTextEdit.LineWrapMode.NoWrap)

        # 事件绑定
        self.code_editor.textChanged.connect(self._on_text_changed)
        self.code_editor.installEventFilter(self)  # 用于拦截 Tab/Enter 键

        # 设置默认模板
        self.code_editor.setPlainText(DEFAULT_CODE_TEMPLATE)
        layout.addWidget(self.code_editor)

    def _setup_syntax_highlighting(self):
        self.highlighter = PythonSyntaxHighlighter(self.code_editor.document())

    def _setup_auto_sync(self):
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._parse_and_sync)

    # ---------------- 编辑增强 ----------------
    def eventFilter(self, obj, event):
        """拦截键盘事件，支持自动括号、缩进、换行等"""
        if obj == self.code_editor and event.type() == event.KeyPress:
            key = event.key()
            text = event.text()
            cursor = self.code_editor.textCursor()
            doc = self.code_editor.document()

            # 1. 自动成对括号/引号
            if self._handle_auto_pairs(cursor, text):
                return True

            # 2. 智能跳过闭合符
            if self._handle_skip_closer(cursor, text, doc):
                return True

            # 3. 删除空括号对
            if key == Qt.Key_Backspace and self._handle_backspace(cursor, doc):
                return True

            # 4. 缩进逻辑
            if key == Qt.Key_Tab:
                if cursor.selection().isEmpty():
                    cursor.insertText("    ")
                else:
                    self._indent_selection()
                return True
            elif key == Qt.Key_Backtab:
                self._unindent_selection()
                return True

            # 5. 智能换行
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._handle_newline(cursor)
                return True

            # 6. 常用快捷键（Ctrl+/ 注释、Ctrl+D 复制行）
            if event.modifiers() == Qt.ControlModifier and key == Qt.Key_Slash:
                self._toggle_comment()
                return True
            if event.modifiers() == Qt.ControlModifier and key == Qt.Key_D:
                self._duplicate_line()
                return True

        return super().eventFilter(obj, event)

    def _handle_auto_pairs(self, cursor, text):
        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        if text in pairs:
            if cursor.hasSelection():
                cursor.insertText(text + cursor.selectedText() + pairs[text])
            else:
                cursor.insertText(text + pairs[text])
                cursor.movePosition(QTextCursor.Left)
                self.code_editor.setTextCursor(cursor)
            return True
        return False

    def _handle_skip_closer(self, cursor, text, doc):
        if text in [')', ']', '}', '"', "'"]:
            pos = cursor.position()
            if pos < doc.characterCount() - 1 and doc.characterAt(pos) == text:
                cursor.movePosition(QTextCursor.Right)
                self.code_editor.setTextCursor(cursor)
                return True
        return False

    def _handle_backspace(self, cursor, doc):
        pos = cursor.position()
        if pos > 0 and pos < doc.characterCount():
            prev_char = doc.characterAt(pos - 1)
            next_char = doc.characterAt(pos)
            if (prev_char, next_char) in [('(', ')'), ('[', ']'), ('{', '}'), ('"', '"'), ("'", "'")]:
                cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, 2)
                cursor.removeSelectedText()
                return True
        return False

    def _handle_newline(self, cursor):
        current_line = cursor.block().text()
        leading_spaces = len(current_line) - len(current_line.lstrip(' '))
        indent = ' ' * leading_spaces
        if current_line.rstrip().endswith(':'):
            indent += '    '
        cursor.insertText('\n' + indent)

    def _toggle_comment(self):
        cursor = self.code_editor.textCursor()
        cursor.select(QTextCursor.LineUnderCursor)
        line = cursor.selectedText().replace('\u2029', '')  # Qt 的换行符
        if line.strip().startswith("#"):
            cursor.insertText(line.lstrip('# '))
        else:
            cursor.insertText("# " + line)

    def _duplicate_line(self):
        cursor = self.code_editor.textCursor()
        cursor.select(QTextCursor.LineUnderCursor)
        line = cursor.selectedText().replace('\u2029', '')
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText('\n' + line)

    def _indent_selection(self):
        cursor = self.code_editor.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        text = cursor.selectedText()
        indented = '\n'.join('    ' + line if line else line for line in text.split('\u2029'))
        cursor.insertText(indented)

    def _unindent_selection(self):
        cursor = self.code_editor.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)

        lines = []
        for line in cursor.selectedText().split('\u2029'):
            if line.startswith('    '):
                lines.append(line[4:])
            elif line.startswith('\t'):
                lines.append(line[1:])
            else:
                lines.append(line)
        cursor.insertText('\n'.join(lines))

    # ---------------- AST 解析 ----------------
    def _on_text_changed(self):
        self.code_changed.emit()
        self._sync_timer.start(800)  # 延迟 0.8s，避免频繁解析

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
            # TODO: 可以在此高亮错误行
            pass
        except Exception as e:
            print(f"解析代码失败: {e}")

    def _parse_component_class(self, class_node, code):
        """简单解析 Component 类的基础属性"""
        component_info = {"name": "", "category": "", "description": ""}
        for stmt in class_node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Str):
                    if target.id in component_info:
                        component_info[target.id] = stmt.value.s
        self.parsed_component.emit(component_info)

    # ---------------- 工具方法 ----------------
    def get_code(self):
        return self.code_editor.toPlainText().replace('\r\n', '\n').replace('\r', '\n')

    def set_code(self, code):
        normalized = code.replace('\r\n', '\n').replace('\r', '\n')
        self.code_editor.setPlainText(normalized)
        self._parse_and_sync()
