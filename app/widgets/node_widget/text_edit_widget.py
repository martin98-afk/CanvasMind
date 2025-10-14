# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from Qt import QtWidgets, QtCore
from qfluentwidgets import LineEdit, TextEdit


class TextWidget(QtWidgets.QWidget):
    """节点内显示：摘要 + 编辑按钮"""
    valueChanged = QtCore.Signal(str)

    def __init__(self, parent=None, type=None, default_text=""):
        super().__init__()
        self.parent = parent
        self._text = default_text
        if type.value == "多行文本":
            self.summary_label = TextEdit()
            self.summary_label.textChanged.connect(lambda: self._on_text_changed(self.summary_label.toPlainText()))
        else:
            self.summary_label = LineEdit()
            self.summary_label.textChanged.connect(self._on_text_changed)
        self.summary_label.setText(default_text)
        # 修改信号连接方式

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary_label)

    def _on_text_changed(self, text):
        """处理文本变化事件"""
        self._text = text
        self.valueChanged.emit(text)

    def get_value(self):
        return self._text

    def set_value(self, text):
        self._text = text or ""
        self.summary_label.setText(self._text)

    def currentText(self):
        return self._text


class TextWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", type=None, default="", window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        widget = TextWidget(default_text=default, type=type, parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)