# -*- coding: utf-8 -*-
import re
from pypinyin import lazy_pinyin, Style

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QPalette, QCursor
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QListWidget
from qfluentwidgets import TextEdit, LineEdit


# -----------------------
# 高亮器类：用于高亮 $变量$
# -----------------------
class VariableHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.variable_format = QTextCharFormat()
        self.variable_format.setForeground(QColor("#FFD700"))
        self.variable_format.setBackground(QColor("#2C2C2C"))
        self.variable_format.setFontWeight(QFont.Bold)

    def highlightBlock(self, text):
        # 使用正则匹配 $...$，非贪婪
        pattern = re.compile(r'\$[^$\n]+\$')
        for match in pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.variable_format)


# -----------------------
# 轻量级变量补全弹窗
# -----------------------
class VariableCompletionPopup(QListWidget):
    itemSelected = pyqtSignal(str)

    def __init__(self, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.use_qcursor = use_qcursor
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setFocusPolicy(Qt.NoFocus)  # 建议不抢焦点，让键盘事件留在编辑器
        self.setStyleSheet("""
            QListWidget {
                background-color: #19232D;
                color: #FFFFFF;
                border: 1px solid #32414B;
                outline: 0;
                padding: 4px;
            }
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected {
                background-color: #2A4C66;
                color: #FFFFFF;
                border: 1px solid #50A1C5;
            }
        """)
        self.setFont(QFont('Consolas', 11))
        self.setMinimumWidth(250)
        self.itemClicked.connect(lambda item: self.itemSelected.emit(item.text()))

    def show_at_cursor(self, editor):
        if not self.use_qcursor:
            rect = editor.cursorRect()
            pos = editor.mapToGlobal(rect.bottomLeft())
        else:
            pos = QCursor.pos()
        self.move(pos.x(), pos.y() + 5)
        self.show()


# -----------------------
# 核心逻辑混合类 (Mixin) 用于减少重复代码
# -----------------------
class CompletionMixin:
    def init_completion(self, get_var_func):
        self.get_variable_list_func = get_var_func
        self._completing = False
        self._input_timer = QTimer()
        self._input_timer.setSingleShot(True)
        self._input_timer.timeout.connect(self._trigger_completion)

    def _get_context_info(self):
        """获取当前光标在 $ 表达式中的位置信息"""
        cursor = self.textCursor() if hasattr(self, 'textCursor') else None
        pos = cursor.position() if cursor else self.cursorPosition()
        text = self.toPlainText() if hasattr(self, 'toPlainText') else self.text()

        # 寻找当前行开始
        line_start = text.rfind('\n', 0, pos) + 1
        current_line_prefix = text[line_start:pos]

        # 寻找左侧最近的 $
        dollar_pos = current_line_prefix.rfind('$')
        if dollar_pos == -1:
            return None, 0

        abs_dollar_pos = line_start + dollar_pos
        prefix = text[abs_dollar_pos + 1: pos]
        return abs_dollar_pos, prefix

    def _filter_variables(self, prefix):
        all_vars = self.get_variable_list_func()
        if not prefix:
            return all_vars

        prefix_l = prefix.lower()
        scored_items = []
        for var in all_vars:
            var_l = var.lower()
            # 1. 直接匹配开头 (最高优先级)
            if var_l.startswith(prefix_l):
                score = 0
            # 2. 汉字包含匹配
            elif prefix_l in var_l:
                score = 1
            # 3. 拼音匹配
            else:
                pinyin_list = lazy_pinyin(var, style=Style.NORMAL)
                pinyin_str = "".join(pinyin_list).lower()
                first_letters = "".join([p[0] for p in pinyin_list if p]).lower()

                if pinyin_str.startswith(prefix_l) or first_letters.startswith(prefix_l):
                    score = 2
                elif prefix_l in pinyin_str:
                    score = 3
                else:
                    continue
            scored_items.append((score, var))

        # 按得分排序，得分越低越靠前
        scored_items.sort(key=lambda x: (x[0], x[1]))
        return [item[1] for item in scored_items]

    def _trigger_completion(self):
        dollar_pos, prefix = self._get_context_info()
        if dollar_pos is None:
            self.popup.hide()
            return

        filtered = self._filter_variables(prefix)
        if not filtered:
            self.popup.hide()
            return

        self.popup.clear()
        self.popup.addItems(filtered)
        self.popup.setCurrentRow(0)
        if not self.popup.isVisible():
            self.popup.show_at_cursor(self)

    def handle_key_event(self, event):
        if self.popup.isVisible():
            if event.key() == Qt.Key_Escape:
                self.popup.hide()
                return True
            elif event.key() in (Qt.Key_Return, Qt.Key_Tab, Qt.Key_Enter):
                if self.popup.currentItem():
                    self._apply_completion(self.popup.currentItem().text())
                    return True
            elif event.key() == Qt.Key_Up:
                self.popup.setCurrentRow(max(0, self.popup.currentRow() - 1))
                return True
            elif event.key() == Qt.Key_Down:
                self.popup.setCurrentRow(min(self.popup.count() - 1, self.popup.currentRow() + 1))
                return True

        # 输入 $ 立即触发，其他字符延迟触发
        if event.text() == '$':
            QTimer.singleShot(10, self._trigger_completion)
        elif event.text() or event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            self._input_timer.start(100)

        return False


# -----------------------
# 优化后的 TextEdit
# -----------------------
class VariableCompletionTextEdit(TextEdit, CompletionMixin):
    def __init__(self, get_variable_list_func, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.popup = VariableCompletionPopup(use_qcursor, self.window())
        self.popup.itemSelected.connect(self._apply_completion)
        self.init_completion(get_variable_list_func)
        self.highlighter = VariableHighlighter(self.document())

    def keyPressEvent(self, event):
        if self.handle_key_event(event):
            return
        super().keyPressEvent(event)

    def _apply_completion(self, var_name):
        self._completing = True
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()

        dollar_pos, _ = self._get_context_info()
        if dollar_pos is not None:
            # 检查右侧是否已经有 $
            has_right_dollar = (pos < len(text) and text[pos] == '$')

            # 选中并替换从 $ 之后到当前光标的内容
            cursor.setPosition(dollar_pos + 1)
            cursor.setPosition(pos, QTextCursor.KeepAnchor)

            completion = var_name if has_right_dollar else f"{var_name}$"
            cursor.insertText(completion)
            self.setTextCursor(cursor)

        self.popup.hide()
        self._completing = False

    def focusOutEvent(self, event):
        QTimer.singleShot(200, self.popup.hide)
        super().focusOutEvent(event)


# -----------------------
# 优化后的 LineEdit
# -----------------------
class VariableCompletionLineEdit(LineEdit, CompletionMixin):
    def __init__(self, get_variable_list_func, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.popup = VariableCompletionPopup(use_qcursor, self.window())
        self.popup.itemSelected.connect(self._apply_completion)
        self.init_completion(get_variable_list_func)

    def keyPressEvent(self, event):
        if self.handle_key_event(event):
            return
        super().keyPressEvent(event)

    def _apply_completion(self, var_name):
        self._completing = True
        pos = self.cursorPosition()
        text = self.text()

        dollar_pos, _ = self._get_context_info()
        if dollar_pos is not None:
            has_right_dollar = (pos < len(text) and text[pos] == '$')

            left_part = text[:dollar_pos + 1]
            right_part = text[pos:]

            completion = var_name if has_right_dollar else f"{var_name}$"
            self.setText(left_part + completion + right_part)
            self.setCursorPosition(dollar_pos + 1 + len(completion))

        self.popup.hide()
        self._completing = False

    def focusOutEvent(self, event):
        QTimer.singleShot(200, self.popup.hide)
        super().focusOutEvent(event)