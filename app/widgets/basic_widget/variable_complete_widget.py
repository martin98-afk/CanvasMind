# -*- coding: utf-8 -*-
import re

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QPalette, QCursor
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QListWidget, QDesktopWidget  # 添加 QDesktopWidget
from qfluentwidgets import TextEdit, LineEdit

from app.widgets.basic_widget.style_sheet import StyleSheet


# -----------------------
# 高亮器类：用于高亮 $$ 变量表达式
# -----------------------
class VariableHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.variable_format = QTextCharFormat()
        self.variable_format.setForeground(QColor("#FFD700"))  # 金色
        self.variable_format.setBackground(QColor("#2C2C2C"))  # 深灰色背景
        self.variable_format.setFontWeight(QFont.Bold)

    def highlightBlock(self, text):
        # 清除之前的所有格式
        self.setFormat(0, len(text), QTextCharFormat())

        # 使用平衡计数法准确判断开始和结束的 $ 符号
        balance = 0
        start_pos = -1
        i = 0
        while i < len(text):
            char = text[i]
            if char == '$':
                if balance == 0:
                    # 开始
                    start_pos = i
                    balance = 1
                else:
                    # 结束
                    balance -= 1
                    if balance == 0 and start_pos != -1:
                        # 高亮整个 $...$ 段
                        self.setFormat(start_pos, i - start_pos + 1, self.variable_format)
                        start_pos = -1
            elif char == '\n':
                # 换行符重置状态
                balance = 0
                start_pos = -1
            i += 1


# -----------------------
# 轻量级变量补全弹窗
# -----------------------
class VariableCompletionPopup(QListWidget):
    itemSelected = pyqtSignal(str)

    def __init__(self, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.use_qcursor = use_qcursor
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setFocusPolicy(Qt.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 改进样式，增加选中项的高亮
        self.setStyleSheet("""
            QListWidget {
                background-color: #19232D;
                color: #FFFFFF;
                border: 1px solid #32414B;
                outline: 0;
                padding: 4px;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #2A4C66; /* 更深的蓝色背景 */
                color: #FFFFFF; /* 确保文字颜色 */
                border: 1px solid #50A1C5; /* 添加边框 */
            }
            QListWidget::item:hover {
                background-color: #253648; /* 悬停背景 */
            }
            QScrollBar:vertical {
                width: 8px;
                background-color: #2A3B4D;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #32414B;
                border-radius: 4px;
                min-height: 20px;
            }
        """)
        font = QFont('Consolas', 12)
        self.setFont(font)
        self.setMaximumWidth(600)
        self.setMinimumWidth(300)
        self.itemClicked.connect(self._on_item_clicked)
        self.hide()

    def _on_item_clicked(self, item):
        self.itemSelected.emit(item.text())
        self.hide()

    def show_at_cursor(self, editor):
        # 获取当前鼠标位置
        if not self.use_qcursor:
            cursor_rect = editor.cursorRect()
            cursor_pos = editor.mapToGlobal(cursor_rect.bottomLeft())
            x = cursor_pos.x()
            y = cursor_pos.y()
        else:
            cursor_pos = QCursor.pos()
            # 计算调整后的 x, y 坐标 - 显示在鼠标位置下方
            x = cursor_pos.x()
            y = cursor_pos.y() + 10  # 在鼠标下方留一点间距

        self.move(int(x), int(y))
        self.show()
        self.setFocus()


# -----------------------
# 支持变量补全和高亮的 TextEdit
# -----------------------
class VariableCompletionTextEdit(TextEdit):
    def __init__(self, get_variable_list_func, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.get_variable_list_func = get_variable_list_func
        self.popup = VariableCompletionPopup(use_qcursor)
        self.popup.itemSelected.connect(self._apply_completion)
        self._completing = False
        self._input_timer = QTimer()
        self._input_timer.setSingleShot(True)
        self._input_timer.timeout.connect(self._trigger_completion)

        # 创建并应用高亮器
        self.highlighter = VariableHighlighter(self.document())

    def focusOutEvent(self, event):
        """当焦点离开编辑框时自动隐藏补全框"""
        self.popup.hide()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        # 处理 $ 触发补全
        if event.text() == '$' and not self._completing:
            super().keyPressEvent(event)
            # --- 优化触发逻辑 ---
            # 检查输入 $ 后，当前位置是否处于未闭合的变量上下文中
            # 获取光标位置（事件已处理，光标已移动）
            cursor = self.textCursor()
            pos_after_input = cursor.position()
            text_after_input = self.toPlainText()

            # 使用平衡计数法判断新输入的 $ 是否是未闭合的
            balance = 0
            in_unmatched_dollar_context = False
            for i in range(pos_after_input):
                if text_after_input[i] == '$':
                    if balance == 0:
                        # 新的开始，或恰好是当前光标前的那个$
                        balance = 1
                        in_unmatched_dollar_context = True
                    else:
                        # 结束一个配对
                        balance -= 1
                        if balance == 0:
                            in_unmatched_dollar_context = False

            # 只有在未闭合的上下文中才触发补全
            if in_unmatched_dollar_context:
                QTimer.singleShot(0, lambda: self._trigger_completion_if_needed())
            # --- 优化结束 ---
            return

        # 处理退格或删除时可能需要更新补全
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            super().keyPressEvent(event)
            if self._is_in_variable_context():
                self._input_timer.start(50)
            else:
                self.popup.hide()
            # 高亮器会自动更新，因为 document() 会感知到变化
            return

        # 处理弹窗导航
        if self.popup.isVisible():
            if event.key() == Qt.Key_Escape:
                self.popup.hide()
                return
            elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Tab:
                if self.popup.currentItem():
                    self._apply_completion(self.popup.currentItem().text())
                    return
            elif event.key() == Qt.Key_Up:
                self.popup.setCurrentRow(max(0, self.popup.currentRow() - 1))
                return
            elif event.key() == Qt.Key_Down:
                self.popup.setCurrentRow(min(self.popup.count() - 1, self.popup.currentRow() + 1))
                return

        # 其他字符：若在变量上下文中，继续补全
        super().keyPressEvent(event)
        if self._is_in_variable_context():
            self._input_timer.start(50)
        elif self.popup.isVisible():
            self.popup.hide()

    def _trigger_completion_if_needed(self):
        """在UI更新后检查是否需要触发补全"""
        if self._is_in_variable_context():
            self._trigger_completion()

    def _is_in_variable_context(self) -> bool:
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        if pos == 0:
            return False

        # 使用平衡计数法判断是否在未闭合的 $ 内
        balance = 0
        in_variable = False
        for i in range(pos):
            if text[i] == '$':
                if balance == 0:
                    # 新的开始
                    balance = 1
                    in_variable = True
                else:
                    # 结束一个配对
                    balance -= 1
                    if balance == 0:
                        in_variable = False
            elif text[i] == '\n':
                # 换行符重置，因为变量不跨行
                balance = 0
                in_variable = False

        return in_variable

    def _get_variable_prefix(self) -> str:
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        # 找到最近的未闭合的 $
        temp_balance = 0
        start_pos = -1
        for i in range(pos - 1, -1, -1):
            if text[i] == '$':
                if temp_balance == 0:
                    start_pos = i
                    # 检查这个$之后到pos之间是否有结束$
                    has_end = False
                    for j in range(start_pos + 1, pos):
                        if text[j] == '$':
                            has_end = True
                            break
                    if not has_end:
                        # 找到了未闭合的开始$
                        break
                    else:
                        # 这个$已经闭合，继续找
                        continue
                else:
                    temp_balance -= 1
            elif text[i] == '\n':
                break

        if start_pos == -1:
            return ""
        return text[start_pos + 1:pos]

    def _trigger_completion(self):
        if not self._is_in_variable_context():
            self.popup.hide()
            return

        prefix = self._get_variable_prefix()
        all_vars = self.get_variable_list_func()
        filtered = [v for v in all_vars if v.lower().startswith(prefix.lower())]

        if not filtered:
            self.popup.hide()
            return

        self.popup.clear()
        for var in filtered:
            self.popup.addItem(var)

        if not self.popup.isVisible():
            self.popup.show_at_cursor(self)
        self.popup.setCurrentRow(0)

    def _apply_completion(self, var_name: str):
        if self._completing:
            return
        self._completing = True
        try:
            cursor = self.textCursor()
            pos = cursor.position()
            text_before = self.toPlainText()  # 获取修改前的文本

            # 找到最近的未闭合的 $
            temp_balance = 0
            start_dollar = -1
            for i in range(pos - 1, -1, -1):
                if text_before[i] == '$':
                    if temp_balance == 0:
                        start_dollar = i
                        # 检查是否已闭合
                        has_end = False
                        for j in range(start_dollar + 1, pos):
                            if text_before[j] == '$':
                                has_end = True
                                break
                        if not has_end:
                            break
                        else:
                            continue
                    else:
                        temp_balance -= 1
                elif text_before[i] == '\n':
                    break
            if start_dollar == -1:
                return

            # 选中从 $ 到光标的内容（包括 $）
            cursor.setPosition(start_dollar)
            cursor.setPosition(pos, QTextCursor.KeepAnchor)
            cursor.insertText(f"${var_name}$")

            # 光标移到 $ 后
            cursor.setPosition(start_dollar + len(var_name) + 2)
            self.setTextCursor(cursor)
        finally:
            self._completing = False
            self.popup.hide()
        # 手动触发 textChanged 信号，因为 setTextCursor 不会触发
        # 高亮器会自动更新，其他连接到 textChanged 的功能也会被触发
        self.textChanged.emit()


class VariableCompletionLineEdit(LineEdit):
    def __init__(self, get_variable_list_func, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.get_variable_list_func = get_variable_list_func
        self.popup = VariableCompletionPopup(use_qcursor)
        self.popup.itemSelected.connect(self._apply_completion)
        self._completing = False
        self._input_timer = QTimer()
        self._input_timer.setSingleShot(True)
        self._input_timer.timeout.connect(self._trigger_completion)

        # 为 LineEdit 使用 QPalette 进行背景高亮
        self._original_palette = self.palette()
        self._highlighted_palette = self._create_highlighted_palette()
        self._last_text = ""
        self.textChanged.connect(self._on_text_changed)

    def _create_highlighted_palette(self):
        palette = self.palette()
        # 设置背景色为深灰色，模拟TextEdit的高亮背景
        palette.setColor(QPalette.Base, QColor("#2C2C2C"))
        # 设置文字颜色为白色或浅色，以匹配TextEdit的高亮文字
        palette.setColor(QPalette.Text, QColor("#FFFFFF"))
        # 因此这里只改变整体背景和文字颜色，提供一种视觉上的区分
        return palette

    def _on_text_changed(self, text):
        # 检测文本中是否包含 $$ 模式，如果包含则应用高亮样式
        if self._has_variable_pattern(text):
            self.setPalette(self._highlighted_palette)
        else:
            self.setPalette(self._original_palette)
        self._last_text = text

    def _has_variable_pattern(self, text):
        match = re.search(r'\$[^\$]*\$', text)
        return match is not None

    def focusOutEvent(self, event):
        """当焦点离开编辑框时自动隐藏补全框"""
        self.popup.hide()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        # 处理 $ 触发补全
        if event.text() == '$' and not self._completing:
            super().keyPressEvent(event)
            # --- 优化触发逻辑 ---
            # 检查输入 $ 后，当前位置是否处于未闭合的变量上下文中
            pos_after_input = self.cursorPosition()
            text_after_input = self.text()

            # 使用平衡计数法判断新输入的 $ 是否是未闭合的
            balance = 0
            in_unmatched_dollar_context = False
            for i in range(pos_after_input):
                if text_after_input[i] == '$':
                    if balance == 0:
                        # 新的开始，或恰好是当前光标前的那个$
                        balance = 1
                        in_unmatched_dollar_context = True
                    else:
                        # 结束一个配对
                        balance -= 1
                        if balance == 0:
                            in_unmatched_dollar_context = False

            # 只有在未闭合的上下文中才触发补全
            if in_unmatched_dollar_context:
                QTimer.singleShot(0, lambda: self._trigger_completion_if_needed())
            # --- 优化结束 ---
            return

        # 处理退格或删除时可能需要更新补全
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            super().keyPressEvent(event)
            if self._is_in_variable_context():
                self._input_timer.start(50)
            else:
                self.popup.hide()
            # textChanged 信号会触发 _on_text_changed，自动更新样式
            return

        # 处理弹窗导航
        if self.popup.isVisible():
            if event.key() == Qt.Key_Escape:
                self.popup.hide()
                return
            elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Tab:
                if self.popup.currentItem():
                    self._apply_completion(self.popup.currentItem().text())
                    return
            elif event.key() == Qt.Key_Up:
                # LineEdit 上下键不移动选择，模拟为上一个/下一个
                current_row = self.popup.currentRow()
                if current_row > 0:
                    self.popup.setCurrentRow(current_row - 1)
                return
            elif event.key() == Qt.Key_Down:
                current_row = self.popup.currentRow()
                if current_row < self.popup.count() - 1:
                    self.popup.setCurrentRow(current_row + 1)
                return

        # 其他字符：若在变量上下文中，继续补全
        super().keyPressEvent(event)
        if self._is_in_variable_context():
            self._input_timer.start(50)
        elif self.popup.isVisible():
            self.popup.hide()

    def _trigger_completion_if_needed(self):
        """在UI更新后检查是否需要触发补全"""
        if self._is_in_variable_context():
            self._trigger_completion()

    def _is_in_variable_context(self) -> bool:
        cursor_pos = self.cursorPosition()
        text = self.text()
        if cursor_pos == 0:
            return False

        # 使用平衡计数法判断是否在未闭合的 $ 内
        # 从头开始计算到当前位置的平衡
        balance = 0
        in_variable_at_pos = False
        for i in range(cursor_pos):
            if text[i] == '$':
                if balance == 0:
                    # 新的开始
                    balance = 1
                    in_variable_at_pos = True
                else:
                    # 结束一个配对
                    balance -= 1
                    if balance == 0:
                        in_variable_at_pos = False
        return in_variable_at_pos

    def _get_variable_prefix(self) -> str:
        cursor_pos = self.cursorPosition()
        text = self.text()
        # 找到最近的未闭合的 $
        # 从当前位置向前找
        balance = 0
        start_pos = -1
        for i in range(cursor_pos - 1, -1, -1):
            if text[i] == '$':
                if balance == 0:
                    # 这是一个未闭合的开始$
                    start_pos = i
                    break
                else:
                    balance -= 1
        if start_pos == -1:
            return ""
        return text[start_pos + 1:cursor_pos]

    def _trigger_completion(self):
        if not self._is_in_variable_context():
            self.popup.hide()
            return

        prefix = self._get_variable_prefix()
        all_vars = self.get_variable_list_func()
        filtered = [v for v in all_vars if v.lower().startswith(prefix.lower())]

        if not filtered:
            self.popup.hide()
            return

        self.popup.clear()
        for var in filtered:
            self.popup.addItem(var)

        if not self.popup.isVisible():
            self.popup.show_at_cursor(self)
        self.popup.setCurrentRow(0)

    def _apply_completion(self, var_name: str):
        if self._completing:
            return
        self._completing = True
        try:
            cursor_pos = self.cursorPosition()
            text_before = self.text()  # 获取修改前的文本

            # 找到最近的未闭合的 $
            balance = 0
            start_dollar = -1
            for i in range(cursor_pos - 1, -1, -1):
                if text_before[i] == '$':
                    if balance == 0:
                        start_dollar = i
                        break
                    else:
                        balance -= 1
            if start_dollar == -1:
                return

            # 替换文本
            new_text = text_before[:start_dollar] + f"${var_name}$" + text_before[cursor_pos:]
            self.setText(new_text)

            # 设置新的光标位置
            new_cursor_pos = start_dollar + len(var_name) + 2
            self.setCursorPosition(new_cursor_pos)
        finally:
            self._completing = False
            self.popup.hide()
        # 手动触发高亮更新，因为 setText 不会触发 textChanged
        self._on_text_changed(self.text())