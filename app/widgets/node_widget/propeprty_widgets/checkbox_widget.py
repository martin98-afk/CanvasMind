from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtGui import QFont
from Qt import QtWidgets, QtCore
from qfluentwidgets import CheckBox, SwitchButton, BodyLabel  # 使用 Fluent Design 风格的 CheckBox

from app.utils.config import Settings
from app.utils.utils import str_to_bool
from app.widgets.node_widget.base import CustomNodeBaseWidget


class CheckBoxWidget(QtWidgets.QWidget):
    """节点内显示：复选框"""
    valueChanged = QtCore.Signal(bool)
    fixed_height = True

    def __init__(self, text="", state=False, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self._value = state if isinstance(state, bool) else state in ("true", 1, "True", "1")
        self.checkbox = SwitchButton("")
        self.checkbox.setFixedHeight(32)
        self.checkbox._offText = self.checkbox.tr("")
        self.checkbox._onText = self.checkbox.tr("")
        self.checkbox.setChecked(self._value)
        self.checkbox.checkedChanged.connect(self._on_state_changed)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.checkbox)

    def _on_state_changed(self, state):
        # Qt 的 state 是 int（0/2），但我们转为 bool
        if state != self._value:
            self._value = state
            self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        value = str_to_bool(value)
        if value != self._value:
            self._value = value
            self.checkbox.setChecked(value)


class CheckBoxWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", text="", state=False, window=None, z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(f"{text}({name})")
        widget = CheckBoxWidget(text=f"{text}({name})", state=state, parent=window)
        self.set_custom_widget(widget, add_on_label=True)
        widget.valueChanged.connect(self.on_value_changed)

    def _get_local_value(self):
        return self.get_custom_widget().get_value()

    def _set_local_value(self, value):
        self.get_custom_widget().set_value(value)


