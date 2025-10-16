# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from Qt import QtWidgets, QtCore
from qfluentwidgets import MessageBoxBase, SubtitleLabel, TextEdit, PushButton, FluentIcon, ToolButton, LineEdit


class LongTextEditorDialog(MessageBoxBase):
    def __init__(self, content: str = "", parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("编辑长文本")
        self.text_edit = TextEdit()
        self.text_edit.setPlainText(content)
        self.text_edit.setMinimumSize(700, 500)  # 足够大的编辑区域

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.text_edit)

        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")


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
        dialog = LongTextEditorDialog(self._text, self.parent)
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