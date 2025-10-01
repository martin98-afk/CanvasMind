# -*- coding: utf-8 -*-
import ast

from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QRect, QSize
from PyQt5.QtGui import QFont, QTextCursor, QTextOption, QColor, QPainter, QTextFormat, QPalette
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QTextEdit
from qfluentwidgets import TextEdit

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
            cursor = self.code_editor.textCursor()
            doc = self.code_editor.document()

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
        selection = TextEdit.ExtraSelection()
        lineColor = QColor(Qt.red).lighter(160)
        selection.format.setUnderlineStyle(QTextFormat.SpellCheckUnderline)
        selection.format.setUnderlineColor(Qt.red)

        cursor = self.code_editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        if error.lineno:
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, error.lineno - 1)
        selection.cursor = cursor
        extraSelections.append(selection)
        self.code_editor.setExtraSelections(extraSelections)

    # ---------------- 工具方法 ----------------
    def get_code(self):
        return self.code_editor.toPlainText().replace('\r\n', '\n').replace('\r', '\n')

    def set_code(self, code):
        normalized = code.replace('\r\n', '\n').replace('\r', '\n')
        self.code_editor.setPlainText(normalized)
        self._parse_and_sync()
