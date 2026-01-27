from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore

from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.node_widget.base import CustomNodeBaseWidget


class ComboBoxWidget(QtWidgets.QWidget):
    """节点内选择框（在 QGraphicsProxyWidget 中可靠弹出）"""
    valueChanged = QtCore.Signal(str)
    fixed_height = True

    def __init__(self, items=[], parent=None):
        super().__init__()
        self.main_window = parent
        self.items = list(items) if items else []
        self._value = self.items[0] if self.items else ""
        self.combobox = CustomComboBox(self)
        if self.items:
            self.combobox.addItems(self.items)
            self.combobox.setCurrentText(self._value)
        self.combobox.currentIndexChanged.connect(self._on_index_changed)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combobox)

    def _on_index_changed(self, index):
        self._value = self.combobox.currentText()
        self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        if value not in self.items and value is not None:
            # 动态补充选项，避免无法设置
            self.items.append(value)
            self.combobox.addItem(value)
        self._value = value or ""
        self.combobox.setCurrentText(self._value)


class ComboBoxWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", items=[], z_value=1, window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(f"{label}({name})")
        widget = ComboBoxWidget(items=items, parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)


