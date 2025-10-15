# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtWidgets import QComboBox
from Qt import QtWidgets, QtCore
from qfluentwidgets import LineEdit, PushButton, FluentIcon, ToolButton

from app.components.base import PropertyType
from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.node_widget.longtext_dialog import LongTextWidget
from app.widgets.node_widget.variable_combo_widget import GlobalVarComboBoxWidget


class FormFieldWidget(QtWidgets.QWidget):
    removed = QtCore.Signal(object)
    changed = QtCore.Signal()

    def __init__(self, schema, home=None, parent=None):
        super().__init__(parent)  # parent 是 DynamicFormWidget（正确！）
        self.schema = schema
        self.home = home  # 用于弹窗的主窗口
        self.fields = {}

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for key, defn in schema.items():
            field_type = defn["type"]
            if field_type == PropertyType.LONGTEXT.name:
                # ✅ 关键：parent=self，不是 parent
                widget = LongTextWidget(parent=self)
                widget.summary_label.setFixedWidth(150)
                widget.summary_label.setText(defn.get("default", ""))
                widget.summary_label.setPlaceholderText(defn.get("label", ""))
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                layout.addWidget(widget)

            elif field_type == PropertyType.CHOICE.name:
                widget = CustomComboBox(parent=self)  # ✅ parent=self
                widget.addItems(defn.get("choices", []))
                widget.currentIndexChanged.connect(self.changed)
                self.fields[key] = widget
                layout.addWidget(widget)

            elif field_type == PropertyType.VARIABLE.name:
                widget = GlobalVarComboBoxWidget(main_window=self.home, parent=self)  # ✅ parent=self
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                layout.addWidget(widget)

            else:
                widget = LineEdit(parent=self)  # ✅ parent=self
                widget.setFixedWidth(150)
                widget.setText(defn.get("default", ""))
                widget.setPlaceholderText(defn.get("label", ""))
                widget.textChanged.connect(self.changed)
                self.fields[key] = widget
                layout.addWidget(widget)

        # ✅ 按钮 parent=self
        btn_remove = ToolButton(FluentIcon.CLOSE, parent=self)
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
                elif hasattr(widget, 'setData'):
                    widget.setData(str(v))
                elif hasattr(widget, 'set_value'):
                    widget.set_value(str(v))


class DynamicFormWidget(QtWidgets.QWidget):
    sizeHintChanged = QtCore.Signal()
    valueChanged = QtCore.Signal(object)

    def __init__(self, schema, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.schema = schema
        self.field_widgets = []
        self._batch_mode = False  # ← 新增：批量模式标志

        self.btn_add = PushButton(text="Add", icon=FluentIcon.ADD, parent=self)
        self.container = QtWidgets.QVBoxLayout()
        self.container.setSpacing(4)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.btn_add)
        layout.addLayout(self.container)
        layout.addStretch(1)
        self.btn_add.clicked.connect(self.add_field)
        self.setStyleSheet("background: rgba(255, 0, 0, 30); border: 1px solid red;")

    def add_field(self, data=None):
        field = FormFieldWidget(self.schema, home=self.parent, parent=self)
        if data:
            field.set_data(data)
        field.removed.connect(self.remove_field)
        field.changed.connect(self._on_field_changed)
        self.field_widgets.append(field)
        self.container.addWidget(field)
        if not self._batch_mode:
            self._emit_changes()

    def _on_field_changed(self):
        if not self._batch_mode:
            self._emit_changes()

    def _emit_changes(self):
        self.sizeHintChanged.emit()
        self.valueChanged.emit(self.get_data())

    def remove_field(self, field):
        if field in self.field_widgets:
            self.field_widgets.remove(field)
            self.container.removeWidget(field)
            field.setParent(None)
            field.deleteLater()
            if not self._batch_mode:
                self._emit_changes()
            else:
                # 批量模式下只更新 geometry，不 emit
                self.updateGeometry()

    def sizeHint(self):
        h = self.btn_add.sizeHint().height()
        for field in self.field_widgets:
            h += field.sizeHint().height()
        h += self.container.spacing() * len(self.field_widgets)
        return QtCore.QSize(300, h)

    def get_data(self):
        return [f.get_data() for f in self.field_widgets]

    def set_data(self, data_list):
        # 🔒 防闪现：隐藏整个容器
        self.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)

        self._batch_mode = True

        for f in self.field_widgets[:]:
            self.field_widgets.remove(f)
            self.container.removeWidget(f)
            f.setParent(None)
            f.deleteLater()

        for item in data_list or []:
            field = FormFieldWidget(self.schema, home=self.parent, parent=self)
            if item:
                field.set_data(item)
            field.removed.connect(self.remove_field)
            field.changed.connect(self._on_field_changed)
            self.field_widgets.append(field)
            self.container.addWidget(field)

        self._batch_mode = False
        self.updateGeometry()
        self._emit_changes()

        # 🔓 初始化完成，允许显示
        self.setAttribute(QtCore.Qt.WA_DontShowOnScreen, False)
        self.show()


class DynamicFormWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", schema=None, window=None, z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(label)
        widget = DynamicFormWidget(schema or {}, parent=window)
        widget.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Maximum  # ← 不允许拉伸超过 sizeHint
        )
        self.set_custom_widget(widget)
        widget.sizeHintChanged.connect(self._update_node)
        widget.valueChanged.connect(self.on_value_changed)

    def _update_node(self):
        if self.node and self.node.view:
            QtCore.QTimer.singleShot(100, lambda: self.node.view.draw_node())

    def get_value(self):
        return self.get_custom_widget().get_data()

    def set_value(self, value):
        QtCore.QTimer.singleShot(0, lambda: self._delayed_set_value(value))

    def _delayed_set_value(self, value):
        # 确保节点已加入 scene
        if not (self.node and self.node.view and self.node.view.scene()):
            QtCore.QTimer.singleShot(50, lambda: self._delayed_set_value(value))
            return

        widget = self.get_custom_widget()
        if widget:
            widget.set_data(value)
            self._update_node()