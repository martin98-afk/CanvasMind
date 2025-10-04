# -*- coding: utf-8 -*-
import ast

from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QRect, QSize
from PyQt5.QtGui import QFont, QTextCursor, QTextOption, QColor, QPainter, QTextFormat, QPalette, QTextCharFormat
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QTextEdit

from app.utils.python_syntax_highlighter import PythonSyntaxHighlighter

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


# ---------------- 行号区 ----------------
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.codeEditor.lineNumberAreaPaintEvent(event)


class CodeEditor(QPlainTextEdit):
    """带行号和当前行高亮的代码编辑器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.set_dark_theme()
        # 行号区宽度调整
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def set_dark_theme(self):
        # 设置整体调色板
        palette = self.palette()
        palette.setColor(QPalette.Base, QColor("#1e1e1e"))  # 编辑区背景
        palette.setColor(QPalette.Text, QColor("#dcdcdc"))  # 普通文本
        palette.setColor(QPalette.Highlight, QColor("#264f78"))  # 选中区域背景
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.setPalette(palette)

        # 设置字体
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #dcdcdc;
                font-family: Consolas, "Courier New", monospace;
                font-size: 13px;
            }
        """)

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 3 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(),
                                              self.line_number_area_width(), cr.height()))

    def update_line_number_area(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(),
                                       self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def highlight_current_line(self):
        extraSelections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()

            # 深色主题下的当前行背景色
            lineColor = QColor("#2a2d2e")

            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)

        self.setExtraSelections(extraSelections)

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor("#252526"))  # 行号区背景

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        # 行号颜色
        painter.setPen(QColor("#858585"))

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.drawText(0, top, self.lineNumberArea.width(), self.fontMetrics().height(),
                                 Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1


# ---------------- 主部件 ----------------
class CodeEditorWidget(QWidget):
    """代码编辑器 - 支持Python语法高亮、自动缩进、智能括号、同步UI、行号、错误提示"""

    code_changed = pyqtSignal()
    parsed_component = pyqtSignal(dict)  # 新增：解析后的组件信息（name/category/description）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_auto_sync()
        self._setup_ui()
        self._setup_syntax_highlighting()

    # ---------------- UI 相关 ----------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.code_editor = CodeEditor()
        font = QFont("Consolas", 11)
        self.code_editor.setFont(font)

        # IDE 常见设置
        self.code_editor.setTabStopDistance(4 * self.code_editor.fontMetrics().horizontalAdvance(' '))
        self.code_editor.setWordWrapMode(QTextOption.NoWrap)

        # 事件绑定
        self.code_editor.textChanged.connect(self._on_text_changed)
        self.code_editor.installEventFilter(self)

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
        if obj == self.code_editor and event.type() == event.KeyPress:
            key = event.key()
            text = event.text()
            modifiers = event.modifiers()
            cursor = self.code_editor.textCursor()
            doc = self.code_editor.document()

            # Shift+Enter 换行（在当前行末尾换行，不改变当前行内容）
            if modifiers == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
                self._handle_shift_enter(cursor)
                return True

            # 自动成对括号/引号
            if self._handle_auto_pairs(cursor, text):
                return True

            # 跳过闭合符
            if self._handle_skip_closer(cursor, text, doc):
                return True

            # 删除成对符号
            if key == Qt.Key_Backspace and self._handle_backspace(cursor, doc):
                return True

            # Tab 缩进
            if key == Qt.Key_Tab:
                if cursor.selection().isEmpty():
                    cursor.insertText("    ")
                else:
                    self._indent_selection()
                return True
            elif key == Qt.Key_Backtab:
                self._unindent_selection()
                return True

            # 智能换行
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._handle_newline(cursor)
                return True

            # 快捷键
            if modifiers == Qt.ControlModifier and key == Qt.Key_Slash:
                self._toggle_comment()
                return True
            if modifiers == Qt.ControlModifier and key == Qt.Key_D:
                self._duplicate_line()
                return True

        return super().eventFilter(obj, event)

    def _handle_shift_enter(self, cursor):
        """处理 Shift+Enter 换行 - 在当前行末尾换行，不改变当前行内容，光标移到下一行"""
        # 移动到行末
        cursor.movePosition(QTextCursor.EndOfLine)
        # 获取当前行的缩进
        current_line = cursor.block().text()
        leading_spaces = len(current_line) - len(current_line.lstrip(' '))
        indent = ' ' * leading_spaces
        # 在行末插入换行和缩进
        cursor.insertText('\n' + indent)
        # 确保光标在正确位置
        self.code_editor.setTextCursor(cursor)

    def _get_indent_from_brackets(self, line_text, cursor_pos):
        """根据括号嵌套计算缩进"""
        open_brackets = ['(', '[', '{']
        close_brackets = [')', ']', '}']

        indent_level = 0
        in_string = False
        string_char = None
        escaped = False

        for i, char in enumerate(line_text):
            if i >= cursor_pos:
                break
            if char == '\\' and not escaped:
                escaped = True
                continue
            if not escaped and char in ['"', "'"]:
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
            elif not in_string:
                if char in open_brackets:
                    indent_level += 1
                elif char in close_brackets:
                    indent_level = max(0, indent_level - 1)
            escaped = False

        return indent_level

    def _is_empty_bracket_pair(self, line_text, cursor_pos):
        """检查是否在空括号对中"""
        open_brackets = ['(', '[', '{']
        close_brackets = [')', ']', '}']

        # 检查当前位置前后是否是空括号对
        if cursor_pos > 0 and cursor_pos < len(line_text):
            prev_char = line_text[cursor_pos - 1]
            next_char = line_text[cursor_pos]
            if (prev_char in open_brackets and next_char in close_brackets and
                    open_brackets.index(prev_char) == close_brackets.index(next_char)):
                return True
        return False

    def _handle_newline(self, cursor):
        """处理回车换行，支持括号自动缩进"""
        current_line = cursor.block().text()
        current_pos = cursor.positionInBlock()

        # 检查是否在空括号对中
        if self._is_empty_bracket_pair(current_line, current_pos):
            # 在空括号对中换行，格式化为：
            # {
            #     |
            # }
            base_indent = len(current_line) - len(current_line.lstrip(' '))
            bracket_indent = self._get_indent_from_brackets(current_line, current_pos - 1)
            outer_indent = ' ' * (base_indent + bracket_indent * 4)
            inner_indent = ' ' * (base_indent + (bracket_indent + 1) * 4)

            # 获取当前光标位置的字符
            cursor_pos = cursor.position()

            # 保存当前光标位置
            current_pos = cursor.position()

            # 移动到左括号后，插入换行和缩进内容
            # 首先将光标移到左括号的位置（即当前位置-1）
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 1)
            # 获取左括号位置
            left_bracket_pos = cursor.position()

            # 移动到右括号位置（即原始光标位置）
            cursor.setPosition(current_pos)
            # 选中左右括号之间的内容（即空的括号对）
            cursor.setPosition(left_bracket_pos, QTextCursor.KeepAnchor)

            # 重新设置光标到原始位置的左括号处
            cursor.setPosition(left_bracket_pos)

            # 现在在左括号后插入换行和内容
            cursor.movePosition(QTextCursor.Right)  # 移动到左括号后
            cursor.insertText('\n' + inner_indent + '\n' + outer_indent)

            # 将光标移动到中间行（新插入的缩进行）
            cursor.movePosition(QTextCursor.Up)  # 上移一行到中间行
            cursor.movePosition(QTextCursor.EndOfLine)  # 移动到行末

            # 设置光标到正确位置
            self.code_editor.setTextCursor(cursor)
        else:
            # 计算括号缩进
            bracket_indent = self._calculate_bracket_indent(current_line, current_pos)

            # 计算基础缩进
            leading_spaces = len(current_line) - len(current_line.lstrip(' '))
            indent = ' ' * leading_spaces

            # 如果当前行以冒号结尾，增加额外缩进
            if current_line.rstrip().endswith(':'):
                indent += '    '

            # 选择更合适的缩进（括号缩进优先）
            final_indent = max(bracket_indent, indent, key=len)

            cursor.insertText('\n' + final_indent)

    def _calculate_bracket_indent(self, current_line, cursor_pos):
        """计算括号缩进"""
        indent_level = self._get_indent_from_brackets(current_line, cursor_pos)
        base_indent = len(current_line) - len(current_line.lstrip(' '))
        bracket_indent = base_indent + (indent_level * 4)  # 每层4个空格
        return ' ' * bracket_indent

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

    def _toggle_comment(self):
        cursor = self.code_editor.textCursor()
        cursor.select(QTextCursor.LineUnderCursor)
        line = cursor.selectedText().replace('\u2029', '')
        if line.strip().startswith("#"):
            cursor.insertText(line.lstrip('# ').lstrip())
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
        except SyntaxError as e:
            self._mark_syntax_error(e)
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

    # ---------------- 错误高亮 ----------------
    def _mark_syntax_error(self, error: SyntaxError):
        extraSelections = []
        selection = QTextEdit.ExtraSelection()
        lineColor = QColor(Qt.red).lighter(160)
        # 修正：使用正确的 UnderlineStyle 常量
        selection.format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
        selection.format.setUnderlineColor(Qt.red)

        cursor = self.code_editor.textCursor()
        cursor.movePosition(QTextCursor.Start)

        if error.lineno:
            # 移动到错误行的开始
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, error.lineno - 1)
            # 选中整行
            cursor.select(QTextCursor.LineUnderCursor)  # 关键修改：选中整行

        # 将选中范围设置给 selection.cursor
        selection.cursor = cursor
        extraSelections.append(selection)
        self.code_editor.setExtraSelections(extraSelections)

    # ---------------- 工具方法 ----------------
    def get_code(self):
        return self.code_editor.toPlainText().replace('\r\n', '\n').replace('\r', '\n')

    def set_code(self, code):
        # 保存当前滚动位置
        scrollbar = self.code_editor.verticalScrollBar()
        current_scroll_pos = scrollbar.value()
        current_cursor_pos = self.code_editor.textCursor().position()

        normalized = code.replace('\r\n', '\n').replace('\r', '\n')
        self.code_editor.setPlainText(normalized)

        # 恢复滚动位置和光标位置
        scrollbar.setValue(current_scroll_pos)
        cursor = self.code_editor.textCursor()
        cursor.setPosition(current_cursor_pos)
        self.code_editor.setTextCursor(cursor)