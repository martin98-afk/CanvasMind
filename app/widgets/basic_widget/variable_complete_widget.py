# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QFont, QSyntaxHighlighter, QTextCharFormat, QColor
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QListWidget
from qfluentwidgets import TextEdit


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

        # 找到所有 $ 符号的位置
        dollar_positions = []
        for i, char in enumerate(text):
            if char == '$':
                dollar_positions.append(i)

        # 配对 $ 符号
        i = 0
        while i < len(dollar_positions) - 1:
            start_pos = dollar_positions[i]
            # 寻找下一个非重叠的 $ 作为结束符
            j = i + 1
            # 确保中间没有换行符，且不跨越其他已配对的 $ 符号
            while j < len(dollar_positions):
                end_pos = dollar_positions[j]
                # 检查 start_pos 和 end_pos 之间是否还有其他 $ 符号
                # 如果有奇数个，则继续找下一个，因为可能有多重嵌套或连续变量
                # 我们只处理最内层的配对
                inner_dollars = text[start_pos + 1:end_pos].count('$')
                if inner_dollars % 2 == 0:  # 如果内部 $ 是偶数个，则 start 和 end 可能是配对
                    # 检查是否有其他配对冲突，这里简化处理，直接配对相邻的
                    # 更精确的逻辑是找第一个能形成有效配对的
                    # 例如 $a$ $b$ -> a 和 b 各自配对
                    # 例如 $a$b$ -> a 开始，b 结束，无效
                    # 例如 $a$b$c$ -> a 开始，c 结束，内部 $b$ 是无效的开始
                    # 我们用平衡计数法
                    balance = 0
                    valid_start = start_pos
                    found_end = -1
                    for k in range(start_pos, len(text)):
                        if text[k] == '$':
                            if balance == 0:
                                # 可能是开始
                                if k == start_pos:  # 确认是我们找到的开始
                                    balance = 1
                                else:
                                    break  # 找到了另一个开始，中断
                            else:
                                balance -= 1
                                if balance == 0:  # 找到匹配的结束
                                    found_end = k
                                    break
                        elif text[k] == '\n':
                            break  # 换行符中断
                    if found_end != -1 and found_end > valid_start:
                        # 高亮从 valid_start 到 found_end
                        self.setFormat(valid_start, found_end - valid_start + 1, self.variable_format)
                        i = j + 1  # 移动到结束符之后
                        break
                    else:
                        i += 1
                else:
                    # 内部有奇数个$，说明这个start可能不是真正的开始，或者end不是真正的结束
                    # 我们继续寻找
                    i += 1
                    break
            else:
                # 没有找到匹配的结束符
                i += 1

        # 为了更精确地处理，我们使用更简单的平衡方法
        # 重置格式
        self.setFormat(0, len(text), QTextCharFormat())
        balance = 0
        start_pos = -1
        for i, char in enumerate(text):
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


# -----------------------
# 轻量级变量补全弹窗
# -----------------------
class VariableCompletionPopup(QListWidget):
    itemSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
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
        cursor_rect = editor.cursorRect()
        global_pos = editor.mapToGlobal(cursor_rect.bottomLeft())
        self.move(global_pos)
        self.show()
        self.setFocus()


# -----------------------
# 支持变量补全和高亮的 TextEdit
# -----------------------
class VariableCompletionTextEdit(TextEdit):
    def __init__(self, get_variable_list_func, parent=None):
        super().__init__(parent)
        self.get_variable_list_func = get_variable_list_func
        self.popup = VariableCompletionPopup()
        self.popup.itemSelected.connect(self._apply_completion)
        self._completing = False
        self._input_timer = QTimer()
        self._input_timer.setSingleShot(True)
        self._input_timer.timeout.connect(self._trigger_completion)

        # 创建并应用高亮器
        self.highlighter = VariableHighlighter(self.document())

    def keyPressEvent(self, event: QKeyEvent):
        # 处理 $ 触发补全
        if event.text() == '$' and not self._completing:
            super().keyPressEvent(event)
            self._input_timer.start(50)  # 短延迟确保 $ 已插入
            return

        # 处理退格或删除时可能需要更新补全
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            super().keyPressEvent(event)
            if self._is_in_variable_context():
                self._input_timer.start(50)
            else:
                self.popup.hide()
            # 高亮器会自动更新
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

        # 检查当前位置前是否处于变量内
        temp_balance = 0
        start_pos = -1
        for i in range(pos - 1, -1, -1):
            if text[i] == '$':
                if temp_balance == 0:
                    # 这是一个潜在的开始
                    start_pos = i
                    # 检查这个开始之后到pos之间是否有结束
                    inner_balance = 0
                    has_end = False
                    for j in range(start_pos + 1, pos):
                        if text[j] == '$':
                            if inner_balance == 0:
                                # 这是结束
                                has_end = True
                                break
                            else:
                                inner_balance -= 1
                        elif text[j] == '\n':
                            break
                    if not has_end:
                        return True
                    else:
                        return False
                else:
                    temp_balance -= 1
            elif text[i] == '\n':
                break

        return False

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
            text = self.toPlainText()

            # 找到最近的未闭合的 $
            temp_balance = 0
            start_dollar = -1
            for i in range(pos - 1, -1, -1):
                if text[i] == '$':
                    if temp_balance == 0:
                        start_dollar = i
                        # 检查是否已闭合
                        has_end = False
                        for j in range(start_dollar + 1, pos):
                            if text[j] == '$':
                                has_end = True
                                break
                        if not has_end:
                            break
                        else:
                            continue
                    else:
                        temp_balance -= 1
                elif text[i] == '\n':
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
