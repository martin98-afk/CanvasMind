# -*- coding: utf-8 -*-
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore

from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit, VariableCompletionLineEdit
from app.widgets.node_widget.base import CustomNodeBaseWidget


class TextWidget(QtWidgets.QWidget):
    """节点内显示：摘要 + 编辑按钮"""
    valueChanged = QtCore.Signal(str)

    def __init__(self, parent=None, type=None, default_text="", get_port_func=lambda: []):
        super().__init__(parent)
        self.parent = parent
        self._text = default_text
        global_vars = getattr(self.parent, 'global_variables', None)
        if type.value == "多行文本":
            self.summary_label = VariableCompletionTextEdit(
                get_variable_list_func=lambda func=get_port_func: global_vars.get_vars(func()),
                use_qcursor=True, parent=self
            )
            self.summary_label.setFixedWidth(300)
            self.summary_label.textChanged.connect(lambda: self._on_text_changed(self.summary_label.toPlainText()))
        else:
            self.summary_label = VariableCompletionLineEdit(
                get_variable_list_func=lambda func=get_port_func: global_vars.get_vars(func()),
                use_qcursor=True, parent=self
            )
            self.summary_label.setFixedWidth(200)
            self.summary_label.textChanged.connect(self._on_text_changed)
        self.summary_label.setText(default_text)
        # 修改信号连接方式

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary_label)

    def sizeHint(self):
        """✅ 返回子控件的真实尺寸"""
        return self.summary_label.sizeHint()

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


class TextWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", type=None, default="", window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)
        self.set_label(f"{label}({name})")
        widget = TextWidget(default_text=default, type=type, parent=window, get_port_func=self.get_port_func)
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