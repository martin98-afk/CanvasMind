# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QFont, QSyntaxHighlighter, QTextCharFormat, QColor
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QListWidget
from Qt import QtWidgets, QtCore
from qfluentwidgets import FluentIcon, ToolButton, LineEdit
from qfluentwidgets import MessageBoxBase, SubtitleLabel, TextEdit


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
        self.setStyleSheet("""
            QListWidget {
                background-color: #19232D;
                color: #FFFFFF;
                border: 1px solid #32414B;
                outline: 0;
                padding: 4px;
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
# 支持变量补全的 TextEdit
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
        # 寻找最近的未闭合的 $
        # 从当前位置向前找最后一个 $
        last_dollar = -1
        balance = 0
        for i in range(pos - 1, -1, -1):
            if text[i] == '$':
                if balance == 0:
                    last_dollar = i
                    break
                else:
                    balance -= 1
            elif text[i] == '\n':
                break  # 换行则中断（不跨行）
        if last_dollar == -1:
            return False
        # 检查是否已闭合（$xxx$）
        after_dollar = text[last_dollar + 1:pos]
        if '$' in after_dollar:
            return False  # 已闭合
        return True

    def _get_variable_prefix(self) -> str:
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        # 找到最近的 $
        for i in range(pos - 1, -1, -1):
            if text[i] == '$':
                return text[i + 1:pos]
            if text[i] == '\n':
                break
        return ""

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
            # 找到 $ 的位置
            pos = cursor.position()
            text = self.toPlainText()
            start_dollar = -1
            for i in range(pos - 1, -1, -1):
                if text[i] == '$':
                    start_dollar = i
                    break
                if text[i] == '\n':
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


# -----------------------
# 改造后的对话框
# -----------------------
class LongTextEditorDialog(MessageBoxBase):
    def __init__(self, content: str = "", parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window
        self.titleLabel = SubtitleLabel("编辑长文本")

        # 获取变量列表的闭包函数
        def get_vars():
            if not self.main_window:
                return []
            global_vars = getattr(self.main_window, 'global_variables', None)
            if not global_vars:
                return []
            all_vars = []
            env_vars = global_vars.env.get_all_env_vars()
            for key in sorted(env_vars.keys()):
                all_vars.append(f"env.{key}")
            for key in sorted(global_vars.custom.keys()):
                all_vars.append(f"custom.{key}")
            for key in sorted(global_vars.node_vars.keys()):
                all_vars.append(f"node_vars.{key}")
            return all_vars

        self.text_edit = VariableCompletionTextEdit(get_variable_list_func=get_vars)
        self.text_edit.setPlainText(content)
        self.text_edit.setMinimumSize(700, 500)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.text_edit)

        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")

    def get_content(self) -> str:
        return self.text_edit.toPlainText()


class LongTextWidget(QtWidgets.QWidget):
    """节点内显示：摘要 + 编辑按钮"""
    valueChanged = QtCore.Signal(str)

    def __init__(self, parent=None, default_text=""):
        super().__init__(parent)
        self.parent = parent
        self._text = default_text

        self.summary_label = LineEdit()
        self.summary_label.setFixedWidth(300)
        self.summary_label.setText(self._get_summary())
        self.summary_label.setReadOnly(True)

        self.edit_btn = ToolButton(FluentIcon.EDIT)
        self.edit_btn.clicked.connect(self._open_editor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.edit_btn)

    def _get_summary(self):
        text = self._text.replace('\n', ' ').replace('\r', ' ')
        return (text[:30] + "...") if len(text) > 30 else text

    def _open_editor(self):
        dialog = LongTextEditorDialog(self._text, self.parent, self.parent)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_text = dialog.text_edit.toPlainText()
            if new_text != self._text:
                self._text = new_text
                self.summary_label.setText(self._get_summary())
                self.valueChanged.emit(self._text)

    def get_value(self):
        return self._text

    def set_value(self, text):
        self._text = text or ""
        self.summary_label.setText(self._get_summary())

    def setText(self, text):
        self._text = text or ""
        self.summary_label.setText(self._get_summary())

    def currentText(self):
        return self._text


class LongTextWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", default="", window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        widget = LongTextWidget(default_text=default, parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)