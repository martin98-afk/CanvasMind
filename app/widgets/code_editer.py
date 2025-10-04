# -*- coding: utf-8 -*-
import ast
import keyword
import builtins

from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QRect, QSize
from PyQt5.QtGui import QFont, QTextCursor, QTextOption, QColor, QPainter, QTextFormat, QPalette, QTextCharFormat, QTextBlockUserData
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QTextEdit, QCompleter

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

    def mousePressEvent(self, event):
        y = event.y()
        block = self.codeEditor.firstVisibleBlock()
        top = int(self.codeEditor.blockBoundingGeometry(block).translated(self.codeEditor.contentOffset()).top())
        bottom = top + int(self.codeEditor.blockBoundingRect(block).height())

        while block.isValid() and top <= y:
            if y <= bottom and self.codeEditor.is_foldable(block):
                self.codeEditor.toggle_fold(block.blockNumber())
                break
            block = block.next()
            top = bottom
            bottom = top + int(self.codeEditor.blockBoundingRect(block).height())
        super().mousePressEvent(event)


# ---------------- 自定义 Block 数据 ----------------
class CodeBlockData(QTextBlockUserData):
    def __init__(self):
        super().__init__()
        self.folded = False


# ---------------- 代码编辑器 ----------------
class CodeEditor(QPlainTextEdit):
    """带行号、当前行高亮、括号匹配、代码折叠的代码编辑器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.set_dark_theme()

        # 行号区宽度调整
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.update_extra_selections)

        self.update_line_number_area_width(0)

    def setParentWidget(self, widget):
        self._parent_widget = widget

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        # ========== 1. 补全确认 ==========
        if (key in (Qt.Key_Return, Qt.Key_Enter)
                and modifiers == Qt.NoModifier
                and self._parent_widget
                and self._parent_widget.completer.popup().isVisible()):
            self._parent_widget.completer.popup().hide()
            self._parent_widget._insert_completion(
                self._parent_widget.completer.currentCompletion()
            )
            return  # 阻止默认行为

        # ========== 2. Shift+Enter: 简单换行 ==========
        if modifiers == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            self._parent_widget._handle_shift_enter(cursor)
            return

        # ========== 3. 智能回车缩进（普通回车）==========
        if key in (Qt.Key_Return, Qt.Key_Enter) and modifiers == Qt.NoModifier:
            cursor = self.textCursor()
            self._parent_widget._handle_newline(cursor)
            return

        # ========== 4. 其他按键交给父类（Tab/Backspace等由eventFilter处理）==========
        super().keyPressEvent(event)

    def set_dark_theme(self):
        palette = self.palette()
        palette.setColor(QPalette.Base, QColor("#1e1e1e"))
        palette.setColor(QPalette.Text, QColor("#dcdcdc"))
        palette.setColor(QPalette.Highlight, QColor("#264f78"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.setPalette(palette)

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
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space + 12  # 额外空间用于折叠图标

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

    def update_extra_selections(self):
        selections = []

        # 当前行高亮
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor("#2a2d2e")
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selections.append(selection)

        # 括号匹配高亮
        self._add_bracket_match_selections(selections)

        self.setExtraSelections(selections)

    def _add_bracket_match_selections(self, selections):
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()
        if pos == 0 or pos >= doc.characterCount():
            return

        char_before = doc.characterAt(pos - 1)
        char_at = doc.characterAt(pos)

        bracket_map = {'(': ')', '[': ']', '{': '}', ')': '(', ']': '[', '}': '{'}
        if char_before in bracket_map:
            match_pos = self._find_matching_bracket(doc, pos - 1, char_before in "([{", char_before)
            if match_pos != -1:
                for p in [pos - 1, match_pos]:
                    sel = QTextEdit.ExtraSelection()
                    sel.cursor = QTextCursor(doc)
                    sel.cursor.setPosition(p)
                    sel.cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
                    sel.format.setBackground(QColor("#3a3d3e"))
                    sel.format.setForeground(QColor("#d7ba7d"))
                    selections.append(sel)
        elif char_at in bracket_map:
            match_pos = self._find_matching_bracket(doc, pos, char_at in ")]}", char_at)
            if match_pos != -1:
                for p in [pos, match_pos]:
                    sel = QTextEdit.ExtraSelection()
                    sel.cursor = QTextCursor(doc)
                    sel.cursor.setPosition(p)
                    sel.cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
                    sel.format.setBackground(QColor("#3a3d3e"))
                    sel.format.setForeground(QColor("#d7ba7d"))
                    selections.append(sel)

    def _find_matching_bracket(self, doc, pos, is_opening, char):
        target = ')' if char == '(' else \
                 ']' if char == '[' else \
                 '}' if char == '{' else \
                 '(' if char == ')' else \
                 '[' if char == ']' else \
                 '{' if char == '}' else None

        if target is None:
            return -1

        depth = 1
        current_pos = pos + (1 if is_opening else -1)
        text = doc.toPlainText()

        while 0 <= current_pos < len(text):
            c = text[current_pos]
            if c == char:
                depth += 1
            elif c == target:
                depth -= 1
                if depth == 0:
                    return current_pos
            current_pos += 1 if is_opening else -1

        return -1

    def is_foldable(self, block):
        text = block.text().strip()
        return text.startswith(('class ', 'def ', 'if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except ', 'with '))

    def toggle_fold(self, block_number):
        doc = self.document()
        block = doc.findBlockByNumber(block_number)
        if not block.isValid() or not self.is_foldable(block):
            return

        data = block.userData()
        if not data:
            data = CodeBlockData()
            block.setUserData(data)
        data.folded = not data.folded

        # 隐藏/显示后续块
        next_block = block.next()
        indent = len(block.text()) - len(block.text().lstrip())
        while next_block.isValid():
            next_indent = len(next_block.text()) - len(next_block.text().lstrip())
            if next_indent <= indent:
                break
            next_block.setVisible(not data.folded)
            next_block = next_block.next()

        # 重新计算文档布局
        self.document().markContentsDirty(block.position(), doc.characterCount())
        self.update()
        self.lineNumberArea.update()

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor("#252526"))

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        painter.setPen(QColor("#858585"))

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.drawText(0, top, self.lineNumberArea.width() - 12, self.fontMetrics().height(),
                                 Qt.AlignRight, number)

                # 绘制折叠图标
                if self.is_foldable(block):
                    data = block.userData()
                    folded = data.folded if data else False
                    icon_rect = QRect(self.lineNumberArea.width() - 10, top, 10, self.fontMetrics().height())
                    if folded:
                        painter.drawText(icon_rect, Qt.AlignCenter, "▶")
                    else:
                        painter.drawText(icon_rect, Qt.AlignCenter, "▼")

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1


# ---------------- 主部件 ----------------
class CodeEditorWidget(QWidget):
    """代码编辑器 - 支持Python语法高亮、自动缩进、智能括号、同步UI、行号、错误提示、括号匹配、代码折叠、自动补全"""

    code_changed = pyqtSignal()
    parsed_component = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_auto_sync()
        self._setup_ui()
        self._setup_syntax_highlighting()


    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.code_editor = CodeEditor()
        self.code_editor.setParentWidget(self)  # 新增：让 editor 知道 widget
        font = QFont("Consolas", 11)
        self.code_editor.setFont(font)
        self._setup_completer()
        self.code_editor.setTabStopDistance(4 * self.code_editor.fontMetrics().horizontalAdvance(' '))
        self.code_editor.setWordWrapMode(QTextOption.NoWrap)

        self.code_editor.textChanged.connect(self._on_text_changed)
        self.code_editor.installEventFilter(self)

        self.code_editor.setPlainText(DEFAULT_CODE_TEMPLATE)
        layout.addWidget(self.code_editor)

    def _setup_syntax_highlighting(self):
        self.highlighter = PythonSyntaxHighlighter(self.code_editor.document())

    def _setup_auto_sync(self):
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._parse_and_sync)

    def _setup_completer(self):
        PYTHON_KEYWORDS = keyword.kwlist
        BUILTIN_NAMES = [name for name in dir(builtins) if not name.startswith('_')]
        DEFAULT_COMPLETIONS = sorted(set(PYTHON_KEYWORDS + BUILTIN_NAMES + [
            'self', 'params', 'inputs', 'return', 'Component', 'BaseComponent'
        ]))
        self.completer = QCompleter(DEFAULT_COMPLETIONS, self)
        self.completer.setWidget(self.code_editor)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self._insert_completion)

    def _insert_completion(self, completion):
        cursor = self.code_editor.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        cursor.insertText(completion)
        self.code_editor.setTextCursor(cursor)

    def _text_under_cursor(self):
        cursor = self.code_editor.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        word = cursor.selectedText()
        # 如果光标在 '.' 后，WordUnderCursor 可能为空，此时手动向前找
        if not word:
            pos = cursor.position()
            doc = self.code_editor.document()
            text = doc.toPlainText()
            i = pos - 1
            while i >= 0 and (text[i].isalnum() or text[i] == '_'):
                i -= 1
            word = text[i + 1:pos]

        return word

    def _should_hide_completer(self, text_under_cursor):
        """判断是否应隐藏补全窗口"""
        if not self.completer.popup().isVisible():
            return True
        prefix = self.completer.completionPrefix()
        # 如果当前词不是前缀的扩展（比如用户输入了 '.' 或空格），就关闭
        if not text_under_cursor.startswith(prefix):
            return True
        # 如果当前词包含非标识符字符（如 . ( [ 空格），也关闭
        if any(c in text_under_cursor for c in " .([{}):;'\"\\"):
            return True
        return False

    def _update_completer_prefix(self):
        if not self.code_editor.hasFocus():
            return

        prefix = self._text_under_cursor()
        popup = self.completer.popup()

        # 只允许字母、数字、下划线组成前缀
        if len(prefix) < 2 or not prefix.replace('_', '').isalnum():
            popup.hide()
            return

        self.completer.setCompletionPrefix(prefix)
        model = self.completer.completionModel()

        if model.rowCount() == 0:
            popup.hide()
            return

        # 计算高度
        max_rows = 8
        row_height = popup.sizeHintForRow(0) or 20
        popup_height = min(model.rowCount(), max_rows) * row_height + 4
        popup_width = max(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width(), 150)

        cursor_rect = self.code_editor.cursorRect()
        point = self.code_editor.mapToGlobal(cursor_rect.bottomLeft())
        popup.setGeometry(point.x(), point.y(), popup_width, popup_height)
        popup.show()

    def eventFilter(self, obj, event):
        if obj == self.code_editor and event.type() == event.KeyPress:
            key = event.key()
            text = event.text()
            # modifiers = event.modifiers()  # 不再需要判断回车

            # 删除所有关于 Qt.Key_Return / Qt.Key_Enter 的处理！

            # 只保留：自动括号、Tab、Backspace、快捷键、补全触发等
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

            # 快捷键
            if event.modifiers() == Qt.ControlModifier:
                if key == Qt.Key_Slash:
                    self._toggle_comment()
                    return True
                if key == Qt.Key_D:
                    self._duplicate_line()
                    return True

            # 触发补全（非回车键）
            if not self.completer.popup().isVisible():
                if text.isalnum() or text == '_':
                    QTimer.singleShot(0, self._update_completer_prefix)
            else:
                # 更新过滤
                QTimer.singleShot(0, self._update_completer_prefix)

            # 关闭补全的按键
            if self.completer.popup().isVisible():
                if key in (Qt.Key_Space, Qt.Key_Tab, Qt.Key_Period, Qt.Key_Escape,
                           Qt.Key_ParenRight, Qt.Key_BraceRight, Qt.Key_BracketRight):
                    self.completer.popup().hide()
                    if key == Qt.Key_Escape:
                        return True

        return super().eventFilter(obj, event)

    def _handle_shift_enter(self, cursor):
        cursor.movePosition(QTextCursor.EndOfLine)
        current_line = cursor.block().text()
        leading_spaces = len(current_line) - len(current_line.lstrip(' '))
        indent = ' ' * leading_spaces
        cursor.insertText('\n' + indent)
        self.code_editor.setTextCursor(cursor)

    def _get_indent_from_brackets(self, line_text, cursor_pos):
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
        open_brackets = ['(', '[', '{']
        close_brackets = [')', ']', '}']

        if cursor_pos > 0 and cursor_pos < len(line_text):
            prev_char = line_text[cursor_pos - 1]
            next_char = line_text[cursor_pos]
            if (prev_char in open_brackets and next_char in close_brackets and
                    open_brackets.index(prev_char) == close_brackets.index(next_char)):
                return True
        return False

    def _handle_newline(self, cursor):
        current_line = cursor.block().text()
        current_pos = cursor.positionInBlock()

        if self._is_empty_bracket_pair(current_line, current_pos):
            base_indent = len(current_line) - len(current_line.lstrip(' '))
            inner_indent = ' ' * (base_indent + 4)
            outer_indent = ' ' * base_indent

            # 1. 记录右括号字符
            right_char = current_line[current_pos]  # 应该是 ) ] }

            # 2. 删除右括号（光标在 left_bracket + 1 位置）
            #    先选中右括号
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()  # 现在变成 "[|"（无右括号）

            # 3. 插入：\n + inner_indent + \n + outer_indent + right_char
            cursor.insertText('\n' + inner_indent + '\n' + outer_indent + right_char)

            # 4. 光标移到中间行
            cursor.movePosition(QTextCursor.Up)  # 到 inner_indent 行
            cursor.movePosition(QTextCursor.EndOfLine)

            self.code_editor.setTextCursor(cursor)
        else:
            bracket_indent = self._calculate_bracket_indent(current_line, current_pos)
            leading_spaces = len(current_line) - len(current_line.lstrip(' '))
            indent = ' ' * leading_spaces
            if current_line.rstrip().endswith(':'):
                indent += '    '
            final_indent = max(bracket_indent, indent, key=len)
            cursor.insertText('\n' + final_indent)

    def _calculate_bracket_indent(self, current_line, cursor_pos):
        indent_level = self._get_indent_from_brackets(current_line, cursor_pos)
        base_indent = len(current_line) - len(current_line.lstrip(' '))
        bracket_indent = base_indent + (indent_level * 4)
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
            pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
            if prev_char in pairs and next_char == pairs[prev_char]:
                cursor.setPosition(pos - 1)
                cursor.setPosition(pos + 1, QTextCursor.KeepAnchor)
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

    def _on_text_changed(self):
        self.code_changed.emit()
        self._sync_timer.start(800)

        # 自动关闭补全窗口
        current_word = self._text_under_cursor()
        if self._should_hide_completer(current_word):
            self.completer.popup().hide()

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

    def _mark_syntax_error(self, error: SyntaxError):
        extraSelections = []
        selection = QTextEdit.ExtraSelection()
        selection.format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
        selection.format.setUnderlineColor(Qt.red)

        cursor = self.code_editor.textCursor()
        cursor.movePosition(QTextCursor.Start)

        if error.lineno:
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, error.lineno - 1)
            cursor.select(QTextCursor.LineUnderCursor)

        selection.cursor = cursor
        extraSelections.append(selection)
        self.code_editor.setExtraSelections(extraSelections)

    def get_code(self):
        return self.code_editor.toPlainText().replace('\r\n', '\n').replace('\r', '\n')

    def set_code(self, code):
        scrollbar = self.code_editor.verticalScrollBar()
        current_scroll_pos = scrollbar.value()
        current_cursor_pos = self.code_editor.textCursor().position()

        normalized = code.replace('\r\n', '\n').replace('\r', '\n')
        self.code_editor.setPlainText(normalized)

        scrollbar.setValue(current_scroll_pos)
        cursor = self.code_editor.textCursor()
        cursor.setPosition(current_cursor_pos)
        self.code_editor.setTextCursor(cursor)