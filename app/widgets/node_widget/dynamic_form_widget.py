# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from PyQt5.QtWidgets import QComboBox
from Qt import QtWidgets, QtCore
from qfluentwidgets import LineEdit, PushButton, FluentIcon, ToolButton

from app.components.base import PropertyType
from app.widgets.node_widget.longtext_dialog import LongTextWidget


class FormFieldWidget(QtWidgets.QWidget):
    removed = QtCore.Signal(object)
    changed = QtCore.Signal()

    def __init__(self, schema, parent=None):
        super().__init__(parent)
        self.schema = schema
        self.fields = {}

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for key, defn in schema.items():
            if defn["type"] == PropertyType.LONGTEXT.name:
                widget = LongTextWidget(parent)
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                layout.addWidget(widget)
            elif defn["type"] == PropertyType.CHOICE.name:
                widget = QComboBox(parent)
                widget.addItems(defn.get("choices", []))
                widget.currentIndexChanged.connect(self.changed)
                self.fields[key] = widget
                layout.addWidget(widget)
            else:
                widget = LineEdit()
                widget.setFixedWidth(150)
                widget.setText(defn.get("default", ""))
                widget.setPlaceholderText(defn.get("label", ""))
                widget.textChanged.connect(self.changed)
                self.fields[key] = widget
                layout.addWidget(widget)

        btn_remove = ToolButton(FluentIcon.CLOSE)
        btn_remove.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(btn_remove)

    def get_data(self):
        return {k: v.text() if hasattr(v, 'text') else v.currentText() for k, v in self.fields.items()}

    def set_data(self, data):
        for k, v in data.items():
            if k in self.fields:
                widget = self.fields[k]
                if hasattr(widget, 'setText'):
                    widget.setText(str(v))
                elif hasattr(widget, 'setCurrentText'):
                    widget.setCurrentText(str(v))


class DynamicFormWidget(QtWidgets.QWidget):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, schema, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.schema = schema
        self.field_widgets = []

        self.btn_add = PushButton("Add", icon=FluentIcon.ADD)
        self.container = QtWidgets.QVBoxLayout()
        self.container.setSpacing(4)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.btn_add)
        layout.addLayout(self.container)

        self.btn_add.clicked.connect(self.add_field)

    def add_field(self, data=None):
        field = FormFieldWidget(self.schema, parent=self.parent)
        if data:
            field.set_data(data)
        field.removed.connect(self.remove_field)
        field.changed.connect(self.sizeHintChanged)
        self.field_widgets.append(field)
        self.container.addWidget(field)
        self.sizeHintChanged.emit()

    def remove_field(self, field):
        if field in self.field_widgets:
            self.field_widgets.remove(field)
            self.container.removeWidget(field)
            field.setParent(None)
            field.deleteLater()
            # ✅ 关键：延迟触发 sizeHintChanged，确保 deleteLater 生效
            QtCore.QTimer.singleShot(50, self.sizeHintChanged.emit)

    def get_data(self):
        return [f.get_data() for f in self.field_widgets]

    def set_data(self, data_list):
        for f in self.field_widgets[:]:
            self.remove_field(f)
        for item in data_list or []:
            self.add_field(item)
        self.sizeHintChanged.emit()


class DynamicFormWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", schema=None, window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        widget = DynamicFormWidget(schema or {}, parent=window)
        self.set_custom_widget(widget)
        widget.sizeHintChanged.connect(self._update_node)

    def _update_node(self):
        if self.node and self.node.view:
            # ✅ 三重保障：先 adjustSize，再强制更新
            self.get_custom_widget().adjustSize()
            self.node.view.update()
            # 使用稍长延迟确保布局完成
            QtCore.QTimer.singleShot(30, lambda: self.node.view.draw_node())

    def get_value(self):
        return self.get_custom_widget().get_data()

    def set_value(self, value):
        self.get_custom_widget().set_data(value)
        self._update_node()
