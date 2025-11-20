# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from Qt import QtWidgets, QtCore
from qfluentwidgets import FluentIcon, ToolButton, LineEdit, TextEdit, TransparentToolButton
from qfluentwidgets import MessageBoxBase, SubtitleLabel

from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit


# -----------------------
# 改造后的对话框
# -----------------------
class LongTextEditorDialog(MessageBoxBase):
    def __init__(self, content: str = "", parent=None, main_window=None, extra_keys=[], get_port_func=lambda: []):
        super().__init__(parent)
        self.main_window = main_window
        self.titleLabel = SubtitleLabel("编辑长文本")
        if not self.main_window:
            return []
        global_vars = getattr(self.main_window, 'global_variables', None)
        if global_vars is not None and hasattr(global_vars, 'get_vars'):
            self.text_edit = VariableCompletionTextEdit(
                get_variable_list_func=lambda keys=extra_keys, func=get_port_func: global_vars.get_vars(keys + func()), parent=self
            )
        else:
            self.text_edit = TextEdit()
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

    def __init__(self, parent=None, default_text="", get_port_func=lambda: []):
        super().__init__(parent)
        self.parent = parent
        self._text = default_text
        self.get_port_func = get_port_func
        self.summary_label = LineEdit()
        self.summary_label.setFixedWidth(300)
        self.summary_label.setText(self._get_summary())
        self.summary_label.setReadOnly(True)

        self.edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
        self.edit_btn.setFixedSize(20,32)
        self.edit_btn.clicked.connect(self._open_editor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.edit_btn)

    def _get_summary(self):
        text = self._text.replace('\n', ' ').replace('\r', ' ')
        return (text[:30] + "...") if len(text) > 30 else text

    def _open_editor(self):
        dialog = LongTextEditorDialog(self._text, self.parent, self.parent, get_port_func=self.get_port_func)
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
        self.set_label(f"{label} ({name})")
        widget = LongTextWidget(default_text=default, parent=window, get_port_func=self.get_port_func)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_port_func(self):
        vars = [f"input.{port.name()}" for port in self.node.input_ports()]
        for port in self.node.input_ports():
            connected_ports = port.connected_ports()
            for connected_port in connected_ports:
                safe_name = connected_port.node().name().replace(" ", "_")
                vars.append(f"input.{safe_name}_{connected_port.name()}")

        return vars

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)