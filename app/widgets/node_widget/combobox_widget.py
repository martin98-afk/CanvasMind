from NodeGraphQt import NodeBaseWidget
from PyQt5.QtWidgets import QComboBox
from Qt import QtWidgets, QtCore
from qfluentwidgets import CheckBox, ComboBox  # 使用 Fluent Design 风格的 CheckBox


class ComboBoxWidget(QtWidgets.QWidget):
    """节点内显示：复选框"""
    valueChanged = QtCore.Signal(bool)

    def __init__(self, items=[]):
        super().__init__()
        self.items = items
        self._value = items[0]
        self.combobox = QComboBox()
        self.combobox.setStyleSheet("""
        QComboBox {
            border: 1px solid #d0d0d0;
            border-radius: 5px;
            padding: 4px 8px;
            background: transparent;
            color: white;
        }
        QComboBox::drop-down {
            width: 30px;
            border: none;
            background: transparent;
            color: white;
        }
        QComboBox QAbstractItemView {
            border: 1px solid #d0d0d0;
            selection-background-color: #e0e0e0;
        }
        """)
        self.combobox.setCurrentText(self._value)
        self.combobox.addItems(items)
        self.combobox.currentIndexChanged.connect(self.combobox.setCurrentIndex)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combobox)

    def _on_index_changed(self, index):
        self._value = self.combobox.currentText()
        self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        self.combobox.setCurrentText(value)


class ComboBoxWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", items=[]):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        widget = ComboBoxWidget(items=items)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)


