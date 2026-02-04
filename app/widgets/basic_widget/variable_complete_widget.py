# -*- coding: utf-8 -*-
import re

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QColor, QPalette, QCursor, QTextCursor, QFont
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QFontMetrics
from PyQt5.QtWidgets import (QTextEdit, QLineEdit, QListWidget, QAbstractItemView)
from pypinyin import lazy_pinyin, Style


# --- 样式配置 ---
class ModernStyles:
    # 颜色面板
    BG_COLOR = "#2D2D2D"  # 编辑器背景
    WINDOW_BG = "#2D2D2D"  # 窗口背景
    INPUT_BG = "#2D2D2D"  # 输入框背景（比背景深，增加凹陷感）
    POPUP_BG = "#2d2d2d"  # 弹窗背景
    TEXT_COLOR = "#E0E0E0"  # 普通文字
    TEXT_MAIN = "#E0E0E0"  # 主文字颜色
    TEXT_DIM = "#858585"  # 次要文字颜色

    # 凹陷边框色组合
    BORDER_SUNKEN_TOP = "#0a0a0a"  # 顶部边缘（最深，模拟阴影）
    BORDER_SUNKEN_BOTTOM = "#3c3c3c"  # 底部边缘（较亮，模拟反光）

    ACCENT_COLOR = "#007acc"  # 蓝调高亮
    SELECTION_BG = "#264f78"  # 选中背景

    @staticmethod
    def get_editor_style():
        return f"""
            QTextEdit, QLineEdit {{
                background-color: {ModernStyles.INPUT_BG};
                color: {ModernStyles.TEXT_MAIN};

                /* 模拟凹陷感：上深下浅的边框 */
                border-top: 2px solid {ModernStyles.BORDER_SUNKEN_TOP};
                border-left: 2px solid {ModernStyles.BORDER_SUNKEN_TOP};
                border-bottom: 1px solid {ModernStyles.BORDER_SUNKEN_BOTTOM};
                border-right: 1px solid {ModernStyles.BORDER_SUNKEN_BOTTOM};

                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', 'Microsoft YaHei';
                font-size: 13px;
                selection-background-color: {ModernStyles.SELECTION_BG};
            }}

            QTextEdit:focus, QLineEdit:focus {{
                /* 聚焦时取消凹陷感，改为发光感 */
                border: 1px solid {ModernStyles.ACCENT_COLOR};
                background-color: #2D2D2D; /* 聚焦时更深一点 */
            }}
        """

    @staticmethod
    def get_popup_style():
        return f"""
                QListWidget {{
                    background-color: {ModernStyles.POPUP_BG};
                    color: {ModernStyles.TEXT_MAIN};
                    border: 1px solid #454545;
                    border-radius: 6px;
                    outline: 0;
                    padding: 5px;
                }}
                QListWidget::item {{
                    padding: 8px 12px;
                    border-radius: 4px;
                    margin: 1px 2px;
                }}
                QListWidget::item:hover {{
                    background-color: #3e3e42;
                }}
                QListWidget::item:selected {{
                    background-color: {ModernStyles.SELECTION_BG};
                    color: white;
                }}
                /* 滚动条现代化 */
                QScrollBar:vertical {{
                    border: none;
                    background: transparent;
                    width: 8px;
                }}
                QScrollBar::handle:vertical {{
                    background: #4f4f4f;
                    border-radius: 4px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: #686868;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            """

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
        self.setStyleSheet(ModernStyles.get_popup_style())

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

    def init_completion(self, get_var_func):
        self.get_variable_list_func = get_var_func
        self._completing = False
        self._input_timer = QTimer()
        self._input_timer.setSingleShot(True)
        self._input_timer.timeout.connect(self._trigger_completion)

    def _get_context_info(self):
        """
        获取上下文信息
        返回: (dollar_start_position, prefix_string)
        如果不需要补全，返回 None, 0
        """
        # 兼容 TextEdit 和 LineEdit 获取光标和文本的方式
        if hasattr(self, 'textCursor'):
            cursor = self.textCursor()
            pos = cursor.position()
            text = self.toPlainText()
        else:
            pos = self.cursorPosition()
            text = self.text()

        # 1. 获取当前行光标之前的内容
        line_start = text.rfind('\n', 0, pos) + 1
        current_line_prefix = text[line_start:pos]

        # 2. 关键修复：判断 $ 符号的奇偶性
        # 如果光标前的 $ 数量是偶数，说明变量已经闭合，或者没有开始，此时不应补全
        dollar_count = current_line_prefix.count('$')
        if dollar_count % 2 == 0:
            return None, 0

        # 3. 寻找最后一个 $ (作为本次补全的起点)
        dollar_pos = current_line_prefix.rfind('$')
        if dollar_pos == -1:
            return None, 0

        # 4. 计算绝对位置和前缀
        abs_dollar_pos = line_start + dollar_pos
        prefix = text[abs_dollar_pos + 1: pos]

        # 额外安全检查：如果前缀里有非法字符（比如空格），通常也意味着不是变量
        # 这一步是可选的，根据你的变量命名规则决定
        if ' ' in prefix or '\t' in prefix:
            return None, 0

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
        # 获取上下文，如果 _get_context_info 返回 None，说明处于闭合状态，隐藏弹窗
        context = self._get_context_info()
        if not context or context[0] is None:
            self.popup.hide()
            return

        dollar_pos, prefix = context

        filtered = self._filter_variables(prefix)
        if not filtered:
            self.popup.hide()
            return

        self.popup.clear()
        self.popup.addItems(filtered)
        self.popup.setCurrentRow(0)
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

        # 如果输入了 $，延时触发检查
        # 此时如果是第二个 $，_get_context_info 会检测到偶数个 $，从而自动隐藏弹窗
        if event.text() == '$':
            QTimer.singleShot(10, self._trigger_completion)
        elif event.text() or event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            self._input_timer.start(100)
        return False


# -----------------------
# TextEdit 与 LineEdit 类（保持逻辑，仅结构复用）
# -----------------------
class VariableCompletionTextEdit(QTextEdit, CompletionMixin):
    def __init__(self, get_variable_list_func, use_qcursor=False, parent=None):
        super().__init__(parent)
        # 1. 应用现代化编辑器样式
        self.setStyleSheet(ModernStyles.get_editor_style())
        self.setMinimumHeight(100)
        # 2. 设置光标颜色 (深色背景下光标需要是白色的)
        p = self.palette()
        p.setColor(QPalette.Text, QColor(ModernStyles.TEXT_COLOR))
        p.setColor(QPalette.Base, QColor(ModernStyles.BG_COLOR))
        self.setPalette(p)

        self.popup = VariableCompletionPopup(use_qcursor, self.window())
        self.popup.itemClicked.connect(lambda item: self._apply_completion(item.text()))

        self.init_completion(get_variable_list_func)

        # 假设你有这个类，如果没有，注释掉即可
        try:
            self.highlighter = VariableHighlighter(self.document())
        except NameError:
            pass

    def keyPressEvent(self, event):
        # 列表导航逻辑：如果弹窗显示中，接管上下键和回车
        if self.popup.isVisible():
            if event.key() == Qt.Key_Down:
                idx = self.popup.currentRow() + 1
                if idx < self.popup.count():
                    self.popup.setCurrentRow(idx)
                return
            elif event.key() == Qt.Key_Up:
                idx = self.popup.currentRow() - 1
                if idx >= 0:
                    self.popup.setCurrentRow(idx)
                return
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                if self.popup.currentItem():
                    self._apply_completion(self.popup.currentItem().text())
                return
            elif event.key() == Qt.Key_Escape:
                self.popup.hide()
                return

        if self.handle_key_event(event): return
        super().keyPressEvent(event)

    def _apply_completion(self, var_name):
        self._completing = True
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()

        # 安全获取上下文
        context_info = self._get_context_info()  # 假设返回 (dollar_pos, str)
        dollar_pos = context_info[0] if context_info else None

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
        # 这里的逻辑保留，防止点击弹窗滚动条时弹窗消失
        if not self.popup.isActiveWindow():
            QTimer.singleShot(200, self.popup.hide)
        super().focusOutEvent(event)


class VariableCompletionLineEdit(QLineEdit, CompletionMixin):
    def __init__(self, get_variable_list_func, use_qcursor=False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        # 应用样式
        self.setStyleSheet(ModernStyles.get_editor_style())

        self.popup = VariableCompletionPopup(use_qcursor, self.window())
        self.popup.itemClicked.connect(lambda item: self._apply_completion(item.text()))

        self.init_completion(get_variable_list_func)

    def keyPressEvent(self, event):
        # 同样的导航逻辑
        if self.popup.isVisible():
            if event.key() == Qt.Key_Down:
                idx = self.popup.currentRow() + 1
                if idx < self.popup.count():
                    self.popup.setCurrentRow(idx)
                return
            elif event.key() == Qt.Key_Up:
                idx = self.popup.currentRow() - 1
                if idx >= 0:
                    self.popup.setCurrentRow(idx)
                return
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                if self.popup.currentItem():
                    self._apply_completion(self.popup.currentItem().text())
                return
            elif event.key() == Qt.Key_Escape:
                self.popup.hide()
                return

        if self.handle_key_event(event): return
        super().keyPressEvent(event)

    def _apply_completion(self, var_name):
        self._completing = True
        pos = self.cursorPosition()
        text = self.text()

        context_info = self._get_context_info()
        dollar_pos = context_info[0] if context_info else None

        if dollar_pos is not None:
            has_right_dollar = (pos < len(text) and text[pos] == '$')
            left_part = text[:dollar_pos + 1]
            right_part = text[pos:]

            completion = var_name if has_right_dollar else f"{var_name}$"

            new_text = left_part + completion + right_part
            self.setText(new_text)
            self.setCursorPosition(dollar_pos + 1 + len(completion))

        self.popup.hide()
        self._completing = False

    def focusOutEvent(self, event):
        if not self.popup.isActiveWindow():
            QTimer.singleShot(200, self.popup.hide)
        super().focusOutEvent(event)