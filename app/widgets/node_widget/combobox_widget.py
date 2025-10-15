from NodeGraphQt import NodeBaseWidget
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore

from app.widgets.basic_widget.combo_widget import CustomComboBox


class ComboBoxWidget(QtWidgets.QWidget):
    """节点内选择框（在 QGraphicsProxyWidget 中可靠弹出）"""
    valueChanged = QtCore.Signal(str)

    def __init__(self, items=[], parent=None):
        super().__init__()
        self.items = list(items) if items else []
        self._value = self.items[0] if self.items else ""
        self.combobox = CustomComboBox(self)
        self.combobox.setMaxVisibleItems(12)
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


class ComboBoxWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", items=[], z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(label)
        widget = ComboBoxWidget(items=items, parent=parent)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)


