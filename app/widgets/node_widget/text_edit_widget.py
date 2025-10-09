# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from Qt import QtWidgets, QtCore
from qfluentwidgets import LineEdit


class TextWidget(QtWidgets.QWidget):
    """节点内显示：摘要 + 编辑按钮"""
    valueChanged = QtCore.Signal(str)

    def __init__(self, parent=None, default_text=""):
        super().__init__()
        self.parent = parent
        self._text = default_text

        self.summary_label = LineEdit()

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary_label)

    def get_value(self):
        return self._text

    def set_value(self, text):
        self._text = text or ""
        self.summary_label.setText(self._text)

    def currentText(self):
        return self._text


class TextWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", default="", window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        widget = TextWidget(default_text=default, parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)