# -*- coding: utf-8 -*-
from typing import Any

from NodeGraphQt import NodeBaseWidget
from Qt import QtWidgets, QtCore
from qfluentwidgets import SpinBox, DoubleSpinBox


class SpinBoxWidget(QtWidgets.QWidget):
    """节点内显示：摘要 + 编辑按钮"""
    valueChanged = QtCore.Signal(object)

    def __init__(self, parent=None, default=0, type="float"):
        super().__init__(parent)
        self.parent = parent
        self._value = default
        self.spinbox = SpinBox() if type == "int" else DoubleSpinBox()
        self.spinbox.setRange(-1000000, 1000000)
        self.spinbox.setValue(self._value)
        self.spinbox.valueChanged.connect(self.valueChanged.emit)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.spinbox)

    def get_value(self):
        return self._value

    def set_value(self, value):
        self.spinbox.setValue(value)

class NumberWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", default=0, type="float", window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        self.type = type
        widget = SpinBoxWidget(default=default, parent=window, type=type)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(float(value) if self.type == "float" else int(value))