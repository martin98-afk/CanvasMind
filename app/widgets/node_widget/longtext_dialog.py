# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from Qt import QtWidgets, QtCore
from qfluentwidgets import FluentIcon, ToolButton, LineEdit
from qfluentwidgets import MessageBoxBase, SubtitleLabel

from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit


# -----------------------
# 改造后的对话框
# -----------------------
class LongTextEditorDialog(MessageBoxBase):
    def __init__(self, content: str = "", parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window
        self.titleLabel = SubtitleLabel("编辑长文本")
        if not self.main_window:
            return []
        global_vars = getattr(self.main_window, 'global_variables', None)

        self.text_edit = VariableCompletionTextEdit(get_variable_list_func=global_vars.get_vars)
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