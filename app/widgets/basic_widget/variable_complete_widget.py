# -*- coding: utf-8 -*-
import re
from pypinyin import lazy_pinyin, Style

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QPalette, QCursor, QFontMetrics
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QListWidget, QAbstractItemView
from qfluentwidgets import TextEdit, LineEdit


# -----------------------
# 高亮器类：保持不变
# -----------------------
class VariableHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.variable_format = QTextCharFormat()
        self.variable_format.setForeground(QColor("#FFD700"))
        self.variable_format.setBackground(QColor("#2C2C2C"))
        self.variable_format.setFontWeight(QFont.Bold)

    def highlightBlock(self, text):
        pattern = re.compile(r'\$[^$\n]+\$')
        for match in pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.variable_format)


# -----------------------
# 优化后的补全弹窗
# -----------------------
class VariableCompletionPopup(QListWidget):
    itemSelected = pyqtSignal(str)

    def __init__(self, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.use_qcursor = use_qcursor
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setFocusPolicy(Qt.NoFocus)

        # 核心设置
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用横向滚动
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)  # 平滑滚动
        self.setTextElideMode(Qt.ElideNone)  # 确保文字不打省略号

        self.setFont(QFont('Consolas', 11))
        self._setup_style()

        self.itemClicked.connect(lambda item: self.itemSelected.emit(item.text()))

    def _setup_style(self):
        """现代化深色主题 QSS"""
        self.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                color: #D4D4D4;
                border: 1px solid #454545;
                border-radius: 6px;
                outline: 0;
                padding: 4px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-radius: 4px;
                margin-bottom: 1px;
            }
            QListWidget::item:hover {
                background-color: #2A2D2E;
            }
            QListWidget::item:selected {
                background-color: #094771;
                color: #FFFFFF;
            }

            /* 现代滚动条样式 */
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 2px 2px 2px 2px;
            }
            QScrollBar::handle:vertical {
                background: #4F4F4F;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #606060;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

    def update_size(self):
        """根据内容动态计算宽度和高度"""
        fm = QFontMetrics(self.font())
        max_width = 250
        # 遍历所有项，找到最宽的内容
        for i in range(self.count()):
            text_w = fm.width(self.item(i).text()) + 40  # 加上padding和滚动条预留空间
            if text_w > max_width:
                max_width = text_w

        # 限制最大宽度，防止内容过长撑破屏幕
        max_width = min(max_width, 600)

        # 计算高度（最多显示8行）
        item_height = 32  # 大致的单行高度
        display_count = min(self.count(), 8)
        total_height = display_count * item_height + 10

        self.setFixedSize(max_width, total_height)

    def show_at_cursor(self, editor):
        self.update_size()  # 显示前重新计算尺寸
        if not self.use_qcursor:
            rect = editor.cursorRect()
            pos = editor.mapToGlobal(rect.bottomLeft())
        else:
            pos = QCursor.pos()
        self.move(pos.x(), pos.y() + 5)
        self.show()


# -----------------------
# 核心逻辑混合类 (Mixin)
# -----------------------
class CompletionMixin:
    # ... (保持原有的 init_completion, _get_context_info, _filter_variables 内容不变)
    def init_completion(self, get_var_func):
        self.get_variable_list_func = get_var_func
        self._completing = False
        self._input_timer = QTimer()
        self._input_timer.setSingleShot(True)
        self._input_timer.timeout.connect(self._trigger_completion)

    def _get_context_info(self):
        cursor = self.textCursor() if hasattr(self, 'textCursor') else None
        pos = cursor.position() if cursor else self.cursorPosition()
        text = self.toPlainText() if hasattr(self, 'toPlainText') else self.text()
        line_start = text.rfind('\n', 0, pos) + 1
        current_line_prefix = text[line_start:pos]
        dollar_pos = current_line_prefix.rfind('$')
        if dollar_pos == -1: return None, 0
        abs_dollar_pos = line_start + dollar_pos
        prefix = text[abs_dollar_pos + 1: pos]
        return abs_dollar_pos, prefix

    def _filter_variables(self, prefix):
        all_vars = self.get_variable_list_func()
        if not prefix: return all_vars
        prefix_l = prefix.lower()
        scored_items = []
        for var in all_vars:
            var_l = var.lower()
            if var_l.startswith(prefix_l):
                score = 0
            elif prefix_l in var_l:
                score = 1
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
        # 即使已经显示，也要更新位置和大小，因为内容变了
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

        if event.text() == '$':
            QTimer.singleShot(10, self._trigger_completion)
        elif event.text() or event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            self._input_timer.start(100)
        return False


# -----------------------
# TextEdit 与 LineEdit 类（保持逻辑，仅结构复用）
# -----------------------
class VariableCompletionTextEdit(TextEdit, CompletionMixin):
    def __init__(self, get_variable_list_func, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.popup = VariableCompletionPopup(use_qcursor, self.window())
        self.popup.itemSelected.connect(self._apply_completion)
        self.init_completion(get_variable_list_func)
        self.highlighter = VariableHighlighter(self.document())

    def keyPressEvent(self, event):
        if self.handle_key_event(event): return
        super().keyPressEvent(event)

    def _apply_completion(self, var_name):
        self._completing = True
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        dollar_pos, _ = self._get_context_info()
        if dollar_pos is not None:
            has_right_dollar = (pos < len(text) and text[pos] == '$')
            cursor.setPosition(dollar_pos + 1)
            cursor.setPosition(pos, QTextCursor.KeepAnchor)
            completion = var_name if has_right_dollar else f"{var_name}$"
            cursor.insertText(completion)
            self.setTextCursor(cursor)
        self.popup.hide()
        self._completing = False

    def focusOutEvent(self, event):
        # 稍微加长延迟，防止点击滚动条时消失
        QTimer.singleShot(200, self.popup.hide)
        super().focusOutEvent(event)


class VariableCompletionLineEdit(LineEdit, CompletionMixin):
    def __init__(self, get_variable_list_func, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.popup = VariableCompletionPopup(use_qcursor, self.window())
        self.popup.itemSelected.connect(self._apply_completion)
        self.init_completion(get_variable_list_func)

    def keyPressEvent(self, event):
        if self.handle_key_event(event): return
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