# -*- coding: utf-8 -*-
import ast
import keyword
import builtins

from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QRect, QSize, QPoint
from PyQt5.QtGui import QFont, QTextCursor, QTextOption, QColor, QPainter, QTextFormat, QPalette, QTextCharFormat, QTextBlockUserData
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QTextEdit, QCompleter, QShortcut, QToolTip, QHBoxLayout, QLineEdit, QPushButton, QCheckBox, QLabel, QInputDialog

import os
import re
import subprocess
import sys
import tempfile

try:
    import jedi  # type: ignore
except Exception:
    jedi = None

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
        self.setMouseTracking(True)

        # 行号区宽度调整
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.update_extra_selections)

        self.update_line_number_area_width(0)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._show_hover_tooltip)
        self._last_hover_pos = None

    def setParentWidget(self, widget):
        self._parent_widget = widget

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            # 获取当前字体
            font = self.font()
            size = font.pointSize()
            # 滚轮向上：放大；向下：缩小
            if event.angleDelta().y() > 0:
                new_size = min(size + 1, 32)  # 限制最大字号
            else:
                new_size = max(size - 1, 8)  # 限制最小字号
            if new_size != size:
                font.setPointSize(new_size)
                self.setFont(font)
                # 可选：同步更新 tab 宽度（保持 4 个空格对齐）
                self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseMoveEvent(self, event):
        self._last_hover_pos = event.pos()
        # Delay hover tooltip to avoid flicker
        self._hover_timer.start(400)
        super().mouseMoveEvent(event)

    def _show_hover_tooltip(self):
        if not self._parent_widget:
            return
        if not self._last_hover_pos:
            return
        self._parent_widget._maybe_show_hover_doc(self._last_hover_pos)

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        # ========== 1. Shift+Enter: 简单换行 ==========
        if modifiers == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            self._parent_widget._handle_shift_enter(cursor)
            return

        # ========== 2. 智能回车缩进（普通回车）==========
        if key in (Qt.Key_Return, Qt.Key_Enter) and modifiers == Qt.NoModifier:
            cursor = self.textCursor()
            self._parent_widget._handle_newline(cursor)
            return

        # ========== 3. Tab 补全 ==========
        if (key in (Qt.Key_Return, Qt.Key_Tab)
                and modifiers == Qt.NoModifier
                and self._parent_widget
                and self._parent_widget.completer.popup().isVisible()):
            self._parent_widget.completer.popup().hide()
            self._parent_widget._insert_completion(
                self._parent_widget.completer.currentCompletion()
            )
            return  # 阻止默认行为

        # ========== 4. 其他按键交给 eventFilter 处理（包括 Tab、Backspace、符号等）==========
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
        text = block.text()
        stripped = text.strip()
        if not stripped:
            return False

        # 1. 传统控制结构
        if stripped.startswith(('class ', 'def ', 'if ', 'elif ', 'for ', 'while ', 'try:', 'with ')):
            # 检查是否真的有子块（排除单行语句）
            return not stripped.endswith(': pass') and not stripped.endswith(': ...')

        # 2. 赋值语句中的容器：inputs = [ 或 properties = {
        if '=' in stripped:
            # 找到 = 后的内容
            parts = stripped.split('=', 1)
            rhs = parts[1].strip()
            # 检查是否以 [ 或 { 开头，且未在同一行闭合
            if (rhs.startswith('[') and not rhs.rstrip().endswith(']')) or \
                    (rhs.startswith('{') and not rhs.rstrip().endswith('}')):
                return True

        # 3. 独立的容器开始（如直接写 [ 或 {）
        if stripped.startswith(('[', '{')) and not stripped.rstrip().endswith((']', '}')):
            return True

        return False

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

        # 计算当前块的缩进（考虑非空行）
        current_line = block.text()
        base_indent = len(current_line) - len(current_line.lstrip())

        # 查找折叠结束位置
        next_block = block.next()
        end_block = block  # 默认只折叠自己（安全）

        while next_block.isValid():
            next_line = next_block.text()
            # 跳过空行和纯注释行
            if not next_line.strip() or next_line.strip().startswith('#'):
                next_block = next_block.next()
                continue

            next_indent = len(next_line) - len(next_line.lstrip())
            # 如果缩进 <= base_indent，说明回到同级或上级，停止
            if next_indent <= base_indent:
                break

            end_block = next_block
            next_block = next_block.next()

        # 隐藏/显示从 block.next() 到 end_block 的所有块
        current = block.next()
        while current.isValid() and current != end_block.next():
            current.setVisible(not data.folded)
            current = current.next()

        # 通知文档更新
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
        # Initialize linting BEFORE UI connects textChanged (to avoid race on first setPlainText)
        # self._setup_linting()
        self._setup_ui()
        self._setup_syntax_highlighting()
        self._setup_shortcuts()
        self._suspend_sync_depth = 0


    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.code_editor = CodeEditor()
        self.code_editor.setParentWidget(self)  # 新增：让 editor 知道 widget
        font = QFont("Consolas", 13)
        self.code_editor.setFont(font)
        self._setup_completer()
        self.code_editor.setTabStopDistance(4 * self.code_editor.fontMetrics().horizontalAdvance(' '))
        self.code_editor.setWordWrapMode(QTextOption.NoWrap)

        self.code_editor.textChanged.connect(self._on_text_changed)
        self.code_editor.installEventFilter(self)

        self._replace_all_text(DEFAULT_CODE_TEMPLATE)

        # Find/Replace panel
        self.find_panel = self._create_find_replace_panel()
        self.find_panel.setVisible(False)

        layout.addWidget(self.find_panel)
        layout.addWidget(self.code_editor)

        # status line: line:col
        self.status_label = QLabel("Ln 1, Col 1", self)
        self.status_label.setStyleSheet("color:#9aa0a6; padding:3px 6px; background:#202124;")
        layout.addWidget(self.status_label)
        self.code_editor.cursorPositionChanged.connect(self._update_status_label)

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
        self._extra_completions = set()

    def _setup_shortcuts(self):
        # Ctrl+Space: Jedi completion
        QShortcut(Qt.CTRL + Qt.Key_Space, self.code_editor, activated=self._trigger_jedi_completion)
        # Ctrl+Shift+Space: Signature help
        QShortcut(Qt.CTRL + Qt.SHIFT + Qt.Key_Space, self.code_editor, activated=self._show_signature_help)
        # Ctrl+B: Go to definition
        QShortcut(Qt.CTRL + Qt.Key_B, self.code_editor, activated=self._go_to_definition)
        # Ctrl+F: Toggle find panel
        QShortcut(Qt.CTRL + Qt.Key_F, self.code_editor, activated=self._toggle_find_panel)
        # F3 Shift+F3: next/prev
        QShortcut(Qt.Key_F3, self.code_editor, activated=lambda: self._find_next(backward=False))
        QShortcut(Qt.SHIFT + Qt.Key_F3, self.code_editor, activated=lambda: self._find_next(backward=True))
        # Ctrl+H: replace focus
        QShortcut(Qt.CTRL + Qt.Key_H, self.code_editor, activated=lambda: self._toggle_find_panel(focus_replace=True))
        # Ctrl+Shift+F: Black format
        # QShortcut(Qt.CTRL + Qt.SHIFT + Qt.Key_F, self.code_editor, activated=self._format_with_black)
        # Ctrl+G: go to line
        QShortcut(Qt.CTRL + Qt.Key_G, self.code_editor, activated=self._goto_line)

    def _setup_linting(self):
        self._lint_timer = QTimer(self)
        self._lint_timer.setSingleShot(True)
        self._lint_timer.timeout.connect(self._run_linter)
        self._lint_results = []

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

    def _insert_completion(self, completion):
        cursor = self.code_editor.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        cursor.insertText(completion)
        self.code_editor.setTextCursor(cursor)
        self.completer.popup().hide()

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
            cursor = self.code_editor.textCursor()
            doc = self.code_editor.document()

            # ========== 【关键】先关闭补全弹窗（避免干扰成对符号） ==========
            if self.completer.popup().isVisible():
                if key in (Qt.Key_Space, Qt.Key_Tab, Qt.Key_Period, Qt.Key_Escape,
                           Qt.Key_ParenRight, Qt.Key_BraceRight, Qt.Key_BracketRight,
                           Qt.Key_QuoteDbl, Qt.Key_Apostrophe):
                    self.completer.popup().hide()
                    if key == Qt.Key_Escape:
                        return True  # 只有 Escape 需要提前返回

            # ========== 跳过闭合符（修复引号跳过问题） ==========
            if self._handle_skip_closer(cursor, text, doc):
                return True

            # ========== 自动成对括号/引号 ==========
            if self._handle_auto_pairs(cursor, text, doc):
                return True

            # ========== 删除成对符号 ==========
            if key == Qt.Key_Backspace and self._handle_backspace(cursor, doc):
                return True

            # ========== Tab: 补全确认 或 缩进（核心修改） ==========
            if key == Qt.Key_Tab:
                if self.completer.popup().isVisible():
                    # 用 Tab 确认补全
                    self._insert_completion(self.completer.currentCompletion())
                    return True
                else:
                    # 普通缩进
                    if cursor.selection().isEmpty():
                        cursor.insertText("    ")
                    else:
                        self._indent_selection()
                    return True

            # ========== Backtab: 反向缩进 ==========
            elif key == Qt.Key_Backtab:
                self._unindent_selection()
                return True

            # ========== 快捷键 ==========
            if event.modifiers() == Qt.ControlModifier:
                if key == Qt.Key_Slash:
                    self._toggle_comment()
                    return True
                if key == Qt.Key_D:
                    self._duplicate_line()
                    return True
                if key == Qt.Key_F:
                    self._toggle_find_panel()
                    return True

            # ========== 触发补全（非标识符字符不触发） ==========
            if not self.completer.popup().isVisible():
                if text.isalnum() or text == '_':
                    QTimer.singleShot(0, self._update_completer_prefix)
            else:
                QTimer.singleShot(0, self._update_completer_prefix)

            # 其他按键交给父类
            return super().eventFilter(obj, event)

        return super().eventFilter(obj, event)

    # ===== Jedi integration =====
    def _trigger_jedi_completion(self):
        if jedi is None:
            return
        source = self.get_code()
        tc = self.code_editor.textCursor()
        line = tc.blockNumber() + 1
        col = tc.positionInBlock()
        try:
            script = jedi.Script(source=source)
            comps = script.complete(line=line, column=col)
            if not comps:
                words = sorted(self._buffer_symbols_union())
            else:
                words = sorted({c.name for c in comps} | self._buffer_symbols_union())
            self.completer.model().setStringList(words)
            # set prefix to current word
            prefix = self._text_under_cursor()
            self.completer.setCompletionPrefix(prefix)
            self._show_completer_popup()
        except Exception:
            pass

    def set_extra_completions(self, words):
        try:
            for w in words or []:
                if isinstance(w, str) and w:
                    self._extra_completions.add(w)
        except Exception:
            pass

    def _buffer_symbols_union(self):
        symbols = set()
        try:
            code = self.get_code()
            for m in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", code):
                symbols.add(m.group(0))
            for m in re.finditer(r"\b(inputs|outputs|properties)\s*=\s*(\[|\{)", code):
                symbols.add(m.group(1))
        except Exception:
            pass
        return symbols | self._extra_completions

    def _show_completer_popup(self):
        popup = self.completer.popup()
        model = self.completer.completionModel()
        if model.rowCount() == 0:
            popup.hide()
            return
        max_rows = 10
        row_height = popup.sizeHintForRow(0) or 20
        popup_height = min(model.rowCount(), max_rows) * row_height + 4
        popup_width = max(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width(), 180)
        cursor_rect = self.code_editor.cursorRect()
        point = self.code_editor.mapToGlobal(cursor_rect.bottomLeft())
        popup.setGeometry(point.x(), point.y(), popup_width, popup_height)
        popup.show()

    def _show_signature_help(self):
        if jedi is None:
            return
        source = self.get_code()
        tc = self.code_editor.textCursor()
        line = tc.blockNumber() + 1
        col = tc.positionInBlock()
        try:
            script = jedi.Script(source=source)
            sigs = script.get_signatures(line=line, column=col)
            if not sigs:
                return
            sig = sigs[0]
            label = sig.to_string()
            QToolTip.showText(self.code_editor.mapToGlobal(self.code_editor.cursorRect().bottomRight()), label, self.code_editor)
        except Exception:
            pass

    def _go_to_definition(self):
        if jedi is None:
            return
        source = self.get_code()
        tc = self.code_editor.textCursor()
        line = tc.blockNumber() + 1
        col = tc.positionInBlock()
        try:
            script = jedi.Script(source=source)
            defs = script.goto(line=line, column=col, follow_imports=True, follow_builtin_imports=True)
            if not defs:
                return
            d = defs[0]
            if d.line is None or d.column is None:
                return
            self._jump_to(d.line, d.column)
        except Exception:
            pass

    def _jump_to(self, line, column):
        cursor = self.code_editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        if line > 1:
            cursor.movePosition(QTextCursor.Down, n=line - 1)
        cursor.movePosition(QTextCursor.Right, n=column)
        self.code_editor.setTextCursor(cursor)
        self.code_editor.setFocus()

    # ===== Hover docs =====
    def _maybe_show_hover_doc(self, pos: QPoint):
        if jedi is None:
            return
        cursor = self.code_editor.cursorForPosition(pos)
        if not cursor or cursor.atBlockEnd():
            return
        cursor.select(QTextCursor.WordUnderCursor)
        if not cursor.selectedText():
            return
        tc = self.code_editor.textCursor()
        self.code_editor.setTextCursor(cursor)
        try:
            source = self.get_code()
            line = cursor.blockNumber() + 1
            col = cursor.positionInBlock()
            script = jedi.Script(source=source)
            helps = script.help(line=line, column=col)
            doc = None
            if helps:
                doc = helps[0].docstring()
            if not doc:
                self.code_editor.setTextCursor(tc)
                return
            global_pos = self.code_editor.mapToGlobal(self.code_editor.cursorRect(cursor).bottomRight())
            QToolTip.showText(global_pos, doc, self.code_editor)
        except Exception:
            pass
        finally:
            self.code_editor.setTextCursor(tc)

    # ===== Find/Replace =====
    def _toggle_find_panel(self, focus_replace=False):
        self.find_panel.setVisible(not self.find_panel.isVisible())
        if self.find_panel.isVisible():
            sel = self.code_editor.textCursor().selectedText().replace('\u2029', '\n')
            if sel and '\n' not in sel:
                self.find_input.setText(sel)
            (self.replace_input if focus_replace else self.find_input).setFocus()

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
                # wrap search
                m = pat.search(doc_text, 0)
                if not m:
                    return
        start, end = m.start(), m.end()
        self._set_selection(start, end)
        self._update_hits_count(pat, doc_text)

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
        # lightweight: only update count for now
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
            self._replace_all_text(new_text)
            self.lbl_hits.setText(f"{n} replaced")

    # ===== Black formatting =====
    def _format_with_black(self):
        code = self.get_code()
        cursor_pos = self.code_editor.textCursor().position()
        try:
            # Try using python -m black via subprocess for reliability
            with tempfile.TemporaryDirectory() as td:
                tmp_file = os.path.join(td, "tmp.py")
                with open(tmp_file, "w", encoding="utf-8") as f:
                    f.write(code)
                # Use --quiet to minimize output
                cmd = [sys.executable, "-m", "black", "--quiet", "--line-length", "88", tmp_file]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc.returncode != 0:
                    return
                with open(tmp_file, "r", encoding="utf-8") as f:
                    formatted = f.read()
        except Exception:
            # Fallback: do nothing on failure
            return
        if formatted and formatted != code:
            self._replace_all_text(formatted)
            c = self.code_editor.textCursor()
            c.setPosition(min(cursor_pos, len(formatted)))
            self.code_editor.setTextCursor(c)

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

    def _handle_auto_pairs(self, cursor, text, doc):
        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        pos = cursor.position()
        if text in pairs:
            if cursor.hasSelection():
                cursor.insertText(text + cursor.selectedText() + pairs[text])
            elif not doc.characterAt(pos) == text:
                cursor.insertText(text + pairs[text])
                cursor.movePosition(QTextCursor.Left)
                self.code_editor.setTextCursor(cursor)
            return True
        return False

    def _handle_skip_closer(self, cursor, text, doc):
        if text in [')', ']', '}', '"', "'"]:
            pos = cursor.position()
            if pos < doc.characterCount() and doc.characterAt(pos) == text:
                # 对引号：仅当光标前一个字符也是相同引号时才跳过（即处于 "" 或 '' 中间）
                if text in ('"', "'"):
                    if pos > 0:
                        cursor.movePosition(QTextCursor.Right)
                        self.code_editor.setTextCursor(cursor)
                        return True
                    else:
                        return False
                else:
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
        # Guard: lint timer may not exist if setup failed in environment
        if hasattr(self, '_lint_timer') and self._lint_timer is not None:
            self._lint_timer.start(1200)

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
        # after AST parse, also render lints if any
        # self._apply_lint_decorations()

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

    def _apply_lint_decorations(self):
        if not self._lint_results:
            return
        extras = list(self.code_editor.extraSelections())
        for (ln, col, msg) in self._lint_results:
            try:
                cur = self.code_editor.textCursor()
                cur.movePosition(QTextCursor.Start)
                if ln > 1:
                    cur.movePosition(QTextCursor.Down, n=ln - 1)
                cur.movePosition(QTextCursor.Right, n=max(0, col))
                cur.movePosition(QTextCursor.NextWord, QTextCursor.KeepAnchor)
                ex = QTextEdit.ExtraSelection()
                fmt = QTextCharFormat()
                fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
                fmt.setUnderlineColor(QColor('#cc7832'))
                ex.format = fmt
                ex.cursor = cur
                extras.append(ex)
            except Exception:
                continue
        self.code_editor.setExtraSelections(extras)

    def _run_linter(self):
        code = self.get_code()
        if not code.strip():
            self._lint_results = []
            return
        # Try ruff first, then flake8
        self._lint_results = []
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = os.path.join(td, 'lint.py')
                with open(tmp, 'w', encoding='utf-8') as f:
                    f.write(code)
                # ruff json
                cmd = [sys.executable, '-m', 'ruff', 'check', '--quiet', '--format', 'json', tmp]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if proc.returncode in (0, 1) and proc.stdout:
                    import json as _json
                    try:
                        items = _json.loads(proc.stdout)
                        for it in items:
                            loc = it.get('location', {})
                            ln = loc.get('row', 1)
                            col = loc.get('column', 0)
                            msg = it.get('message', '')
                            self._lint_results.append((ln, col, msg))
                    except Exception:
                        pass
                elif proc.returncode == 2:
                    pass
        except Exception:
            # fallback to flake8
            try:
                with tempfile.TemporaryDirectory() as td:
                    tmp = os.path.join(td, 'lint.py')
                    with open(tmp, 'w', encoding='utf-8') as f:
                        f.write(code)
                    cmd = [sys.executable, '-m', 'flake8', tmp, '--format=%(row)d:%(col)d:%(code)s %(text)s']
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                    if proc.stdout:
                        for line in proc.stdout.splitlines():
                            try:
                                parts = line.strip().split(':', 3)
                                if len(parts) == 4:
                                    ln = int(parts[0])
                                    col = int(parts[1])
                                    msg = parts[3]
                                    self._lint_results.append((ln, col, msg))
                            except Exception:
                                continue
            except Exception:
                self._lint_results = []
        self._apply_lint_decorations()

    # ===== Status line and navigation =====
    def _update_status_label(self):
        cur = self.code_editor.textCursor()
        ln = cur.blockNumber() + 1
        col = cur.positionInBlock() + 1
        self.status_label.setText(f"Ln {ln}, Col {col}")

    def _goto_line(self):
        cur = self.code_editor.textCursor()
        ln = cur.blockNumber() + 1
        num, ok = QInputDialog.getInt(self, "Go to Line", "Line number:", ln, 1, 10**9, 1)
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

    # ---- Safe update helpers ----
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
        # restore selection
        c = self.code_editor.textCursor()
        if sel_start != sel_end:
            c.setPosition(max(0, min(sel_start, len(new_text))))
            c.setPosition(max(0, min(sel_end, len(new_text))), QTextCursor.KeepAnchor)
        else:
            c.setPosition(max(0, min(cursor.position(), len(new_text))))
        self.code_editor.setTextCursor(c)
        scrollbar.setValue(scroll_pos)