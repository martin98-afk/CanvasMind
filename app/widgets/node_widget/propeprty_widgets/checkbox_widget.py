from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore
from qfluentwidgets import CheckBox, SwitchButton, BodyLabel  # 使用 Fluent Design 风格的 CheckBox

from app.widgets.node_widget.base import CustomNodeBaseWidget


class CheckBoxWidget(QtWidgets.QWidget):
    """节点内显示：复选框"""
    valueChanged = QtCore.Signal(bool)

    def __init__(self, text="", state=False, parent=None):
        super().__init__()
        self._value = state if isinstance(state, bool) else state in ("true", 1, "True", "1")
        label = BodyLabel(text)
        label.setStyleSheet("color: rgba(170, 170, 170, 255);")
        self.checkbox = SwitchButton("")
        self.checkbox.setFixedHeight(32)
        self.checkbox._offText = self.checkbox.tr("")
        self.checkbox._onText = self.checkbox.tr("")
        self.checkbox.setChecked(self._value)
        self.checkbox.checkedChanged.connect(self._on_state_changed)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(self.checkbox)

    def _on_state_changed(self, state):
        # Qt 的 state 是 int（0/2），但我们转为 bool
        new_value = state == QtCore.Qt.Checked
        if new_value != self._value:
            self._value = new_value
            self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        value = bool(value)
        if value != self._value:
            self._value = value
            self.checkbox.setChecked(value)


class CheckBoxWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", text="", state=False):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)
        self.set_label(f"{name}")
        widget = CheckBoxWidget(text=f"{text}({name})", state=state, parent=parent)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)
        self.set_label_visible(False)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)


