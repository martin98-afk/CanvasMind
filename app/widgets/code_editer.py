import ast

from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont, QTextCursor, QTextOption
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import TextEdit as FluentTextEdit

from app.utils.python_syntax_highlighter import PythonSyntaxHighlighter


class CodeEditorWidget(QWidget):
    """代码编辑器 - 支持Python语法高亮、自动缩进、4空格对齐等PEP8习惯"""
    code_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # 顺序很重要：先初始化定时器，再设置文本（避免 textChanged 时 timer 不存在）
        self._setup_auto_sync()
        self._setup_ui()
        self._setup_syntax_highlighting()

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

        # 设置默认换行符为 \n（Unix风格）
        # PyQt 默认使用系统换行符，但 Python 社区偏好 \n
        # （Qt 不直接支持设置换行符类型，但保存时可统一处理）

        # 连接自定义缩进逻辑
        self.code_editor.textChanged.connect(self._on_text_changed)
        self.code_editor.installEventFilter(self)  # 用于拦截 Tab/Enter 键

        self.code_editor.setPlainText(self._get_default_code_template())
        layout.addWidget(self.code_editor)

    def _setup_syntax_highlighting(self):
        self.highlighter = PythonSyntaxHighlighter(self.code_editor.document())

    def _setup_auto_sync(self):
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._parse_and_sync)

    def eventFilter(self, obj, event):
        """拦截 Tab、Enter、括号、引号等键，实现智能编辑"""
        if obj == self.code_editor and event.type() == event.KeyPress:
            key = event.key()
            text = event.text()

            cursor = self.code_editor.textCursor()
            doc = self.code_editor.document()

            # === 1. 自动成对括号/引号 ===
            pairs = {
                '(': ')',
                '[': ']',
                '{': '}',
                '"': '"',
                "'": "'"
            }

            if text in pairs:
                if cursor.hasSelection():
                    # 选中内容：用括号包裹
                    selected = cursor.selectedText()
                    replacement = text + selected + pairs[text]
                    cursor.insertText(replacement)
                    return True
                else:
                    # 无选中：插入成对，并将光标置于中间
                    cursor.insertText(text + pairs[text])
                    # 移动光标回退一格（到中间）
                    cursor.movePosition(QTextCursor.Left)
                    self.code_editor.setTextCursor(cursor)
                    return True

            # === 2. 智能跳过闭合符 ===
            if text in [')', ']', '}', '"', "'"]:
                pos = cursor.position()
                if pos < doc.characterCount() - 1:  # 不是文档末尾
                    next_char = doc.characterAt(pos)
                    if next_char == text:
                        # 下一个字符就是匹配的闭合符，直接跳过
                        cursor.movePosition(QTextCursor.Right)
                        self.code_editor.setTextCursor(cursor)
                        return True

            # === 3. 删除空括号对 ===
            if key == Qt.Key_Backspace:
                pos = cursor.position()
                if pos > 0 and pos < doc.characterCount():
                    prev_char = doc.characterAt(pos - 1)
                    next_char = doc.characterAt(pos)
                    # 检查是否是空括号对
                    empty_pairs = [('(', ')'), ('[', ']'), ('{', '}'), ('"', '"'), ("'", "'")]
                    if (prev_char, next_char) in empty_pairs:
                        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, 2)
                        cursor.removeSelectedText()
                        return True

            # === 4. 原有 Tab/Enter 逻辑 ===
            if key == Qt.Key_Tab:
                if cursor.selection().isEmpty():
                    cursor.insertText("    ")
                    return True
                else:
                    self._indent_selection()
                    return True
            elif key == Qt.Key_Backtab:
                self._unindent_selection()
                return True
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                current_block = cursor.block()
                current_line = current_block.text()
                leading_spaces = len(current_line) - len(current_line.lstrip(' '))
                indent = ' ' * leading_spaces
                if current_line.rstrip().endswith(':'):
                    indent += '    '
                cursor.insertText('\n' + indent)
                return True

        return super().eventFilter(obj, event)

    def _indent_selection(self):
        """对选中行整体增加缩进（4空格）"""
        cursor = self.code_editor.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)

        text = cursor.selectedText()
        indented = '\n'.join('    ' + line if line else line for line in text.split('\u2029'))  # \u2029 是 Qt 的换行符
        cursor.insertText(indented)

    def _unindent_selection(self):
        """对选中行整体减少缩进（最多移除4空格）"""
        cursor = self.code_editor.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)

        text = cursor.selectedText()
        unindented_lines = []
        for line in text.split('\u2029'):
            if line.startswith('    '):
                unindented_lines.append(line[4:])
            elif line.startswith('\t'):
                unindented_lines.append(line[1:])
            else:
                unindented_lines.append(line)
        unindented = '\n'.join(unindented_lines)
        cursor.insertText(unindented)

    def _on_text_changed(self):
        self.code_changed.emit()
        self._sync_timer.start(1000)

    def _parse_and_sync(self):
        try:
            code = self.code_editor.toPlainText()
            if not code.strip():
                return
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self._parse_component_class(node, code)
                    break
        except SyntaxError:
            pass
        except Exception as e:
            print(f"解析代码失败: {e}")

    def _parse_component_class(self, class_node, code):
        pass

    def _get_default_code_template(self):
        return '''import importlib.util
import pathlib
base_path = pathlib.Path(__file__).parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType


class Component(BaseComponent):
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

    def get_code(self):
        # 可选：统一换行符为 \n（避免 Windows \r\n）
        return self.code_editor.toPlainText().replace('\r\n', '\n').replace('\r', '\n')

    def set_code(self, code):
        # 统一换行符并设置
        normalized_code = code.replace('\r\n', '\n').replace('\r', '\n')
        self.code_editor.setPlainText(normalized_code)
        self._parse_and_sync()