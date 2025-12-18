# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import QSize
from Qt import QtWidgets, QtCore
from qfluentwidgets import FluentIcon, TransparentPushButton, TransparentToolButton

from app.components.base import PropertyType
from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionLineEdit
from app.widgets.node_widget.base import CustomNodeBaseWidget
from app.widgets.node_widget.checkbox_widget import CheckBoxWidget
from app.widgets.node_widget.longtext_dialog import LongTextWidget
from app.widgets.node_widget.range_widget import RangeWidget
from app.widgets.node_widget.variable_combo_widget import GlobalVarComboBoxWidget


class FormFieldWidget(QtWidgets.QWidget):
    removed = QtCore.Signal(object)
    changed = QtCore.Signal()

    def __init__(self, schema, home=None, parent=None, get_port_func=lambda: [], index=1):
        super().__init__(parent)  # parent 是 DynamicFormWidget（正确！）
        self.schema = schema
        self.home = home  # 用于弹窗的主窗口
        self.fields = {}

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)
        for key, defn in schema.items():
            field_type = defn["type"]
            label = defn.get("label", "")
            name = defn.get("name", "")
            default = defn.get("default", "")

            if isinstance(default, str) and "{{id}}" in default:
                default = default.replace("{{id}}", str(index))

            # 为这种布局创建一个包含标签和输入框的子布局
            sub_layout = QtWidgets.QVBoxLayout()
            sub_layout.setContentsMargins(0, 0, 0, 0)
            sub_layout.setSpacing(2)

            # 标签行
            label_row = QtWidgets.QHBoxLayout()
            label_row.setContentsMargins(0, 0, 0, 0)
            label_row.setSpacing(6)

            label_widget = QtWidgets.QLabel(f"{label} ({name}):" if name else label + ":")
            label_widget.setStyleSheet("QLabel { font-weight: bold; color: white; font-size: 12px; }")
            label_row.addWidget(label_widget)

            # 添加占位符
            label_row.addStretch()
            sub_layout.addLayout(label_row)

            # 输入框行
            input_row = QtWidgets.QHBoxLayout()
            input_row.setContentsMargins(0, 0, 0, 0)

            if field_type == PropertyType.LONGTEXT.name:
                widget = LongTextWidget(parent=home, default_text=default, get_port_func=get_port_func)
                widget.summary_label.setFixedWidth(180)
                widget.summary_label.setPlaceholderText(label)
                widget.valueChanged.connect(self.changed)
                widget.set_value(default)
                self.fields[key] = widget
                input_row.addWidget(widget)

            elif field_type == PropertyType.CHOICE.name:
                # CHOICE 类型：下拉框没有 placeholder，直接显示标签在前面
                widget = CustomComboBox(parent=self)
                widget.addItems(defn.get("choices", []))
                widget.setCurrentText(default or defn.get("choices", [])[0])
                widget.currentTextChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            elif field_type == PropertyType.VARIABLE.name:
                # VARIABLE 类型：检查是否支持 placeholder
                widget = GlobalVarComboBoxWidget(main_window=home, parent=self)
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            elif field_type == PropertyType.RANGE.name:
                # VARIABLE 类型：检查是否支持 placeholder
                widget = RangeWidget(
                    min_val=defn.get("min", 0), max_val=defn.get("max", 100), step=defn.get("step", 1), default=default,
                    parent=self
                )
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            elif field_type == PropertyType.BOOL.name:
                # VARIABLE 类型：检查是否支持 placeholder
                widget = CheckBoxWidget(text=label, state=default, parent=self)
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            else:
                # 其他类型使用 LineEdit
                global_vars = getattr(self.home, 'global_variables', None)
                widget = VariableCompletionLineEdit(
                    get_variable_list_func=lambda func=get_port_func: global_vars.get_vars(func()),
                    use_qcursor=True, parent=self
                )
                widget.setFixedWidth(180)
                widget.setPlaceholderText(label)
                widget.textChanged.connect(self.changed)
                widget.setText(default)
                self.fields[key] = widget
                input_row.addWidget(widget)

            sub_layout.addLayout(input_row)
            layout.addLayout(sub_layout)

        sub_layout = QtWidgets.QVBoxLayout()
        sub_layout.setContentsMargins(0, 0, 0, 0)
        sub_layout.setSpacing(2)

        # 标签行
        label_row = QtWidgets.QHBoxLayout()
        label_row.setContentsMargins(0, 0, 0, 0)
        label_row.setSpacing(6)

        label_widget = QtWidgets.QLabel("")
        label_widget.setStyleSheet("QLabel { font-weight: bold; color: white; font-size: 12px; }")
        label_row.addWidget(label_widget)

        # 添加占位符
        label_row.addStretch()
        sub_layout.addLayout(label_row)

        # 输入框行
        input_row = QtWidgets.QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        # 删除按钮
        btn_remove = TransparentToolButton(FluentIcon.CLOSE, parent=self)
        btn_remove.setFixedSize(20, 32)
        btn_remove.setIconSize(QSize(16,16))
        btn_remove.clicked.connect(lambda: self.removed.emit(self))
        input_row.addWidget(btn_remove)
        sub_layout.addLayout(input_row)

        layout.addLayout(sub_layout)

    def get_data(self):
        data = {}
        for k, v in self.fields.items():
            if hasattr(v, 'text'):
                data[k] = v.text()
            elif hasattr(v, 'currentText'):
                data[k] = v.currentText()
            elif hasattr(v, 'get_value'):
                data[k] = v.get_value()
            elif hasattr(v, 'summary_label'):
                data[k] = v.summary_label.text()
            else:
                data[k] = getattr(v, 'value', lambda: '')()
        return data

    def set_data(self, data):
        for k, v in data.items():
            if k in self.fields:
                widget = self.fields[k]
                if hasattr(widget, 'setText'):
                    widget.setText(str(v))
                elif hasattr(widget, 'setCurrentText'):
                    widget.setCurrentText(str(v))
                elif hasattr(widget, 'set_value'):
                    widget.set_value(str(v))
                elif hasattr(widget, 'summary_label'):
                    widget.summary_label.setText(str(v))
                elif hasattr(widget, 'setData'):
                    widget.setData(str(v))


class DynamicFormWidget(QtWidgets.QWidget):
    sizeHintChanged = QtCore.Signal()
    valueChanged = QtCore.Signal(object)

    def __init__(self, schema, parent=None, label=None, get_port_func=lambda: []):
        super().__init__(parent)
        self.parent = parent
        self.schema = schema
        self.label = label or "条件"
        self.field_widgets = []
        self._batch_mode = False
        self.field_width = 0
        self.get_port_func = get_port_func
        # 添加按钮
        self.btn_add = TransparentPushButton(text=f"添加{self.label}", icon=FluentIcon.ADD, parent=self)
        self.container = QtWidgets.QVBoxLayout()
        self.container.setSpacing(6)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.btn_add)
        layout.addLayout(self.container)
        layout.addStretch(1)

        self.btn_add.clicked.connect(self.add_field)

    def add_field(self, data=None):
        index = len(self.field_widgets) + 1  # 序号从 1 开始
        field = FormFieldWidget(
            self.schema,
            home=self.parent,
            parent=self,
            get_port_func=self.get_port_func,
            index=index
        )
        if data:
            field.set_data(data)  # 注意：回填时不替换 {{id}}，因为 data 是用户已保存的值
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
        self.updateGeometry()
        self.sizeHintChanged.emit()
        self.valueChanged.emit(self.get_data())

    def remove_field(self, field):
        if field not in self.field_widgets:
            return

        self.field_widgets.remove(field)
        self.container.removeWidget(field)
        field.setParent(None)
        field.deleteLater()

        # 如果是最后一个字段被删除，重建 container
        if not self.field_widgets:
            # 清空旧 container
            while self.container.count():
                child = self.container.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            # 重新设置 spacing/margins
            self.container.setSpacing(6)

        if not self._batch_mode:
            self._emit_changes()
        else:
            self.updateGeometry()

    def sizeHint(self):
        # 计算最大宽度
        max_width = self.btn_add.sizeHint().width()
        for field in self.field_widgets:
            self.field_width = field.sizeHint().width()
            break

        max_width = max(max_width, self.field_width)

        # 高度计算
        h = self.btn_add.sizeHint().height() + 6  # 按钮高度 + 间距
        for field in self.field_widgets:
            h += field.sizeHint().height() + 4  # 每个字段的高度 + 间距

        return QtCore.QSize(max_width, h)

    def get_data(self):
        return [f.get_data() for f in self.field_widgets]

    def set_data(self, data_list):
        self._batch_mode = True

        # 清空现有字段
        for f in self.field_widgets[:]:
            self.field_widgets.remove(f)
            self.container.removeWidget(f)
            f.setParent(None)
            f.deleteLater()

        # 添加新字段
        for item in data_list or []:
            field = FormFieldWidget(self.schema, home=self.parent, parent=self, get_port_func=self.get_port_func)
            if item:
                field.set_data(item)
            field.removed.connect(self.remove_field)
            field.changed.connect(self._on_field_changed)
            self.field_widgets.append(field)
            self.container.addWidget(field)

        self._batch_mode = False
        self.updateGeometry()
        self._emit_changes()


class DynamicFormWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", schema=None, window=None, z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.window = window
        self.name = name
        self.set_name(name)
        self.set_label(f"{label}({name})")
        widget = DynamicFormWidget(schema or {}, parent=window, label=label, get_port_func=self.get_port_func)
        self.set_custom_widget(widget)
        widget.sizeHintChanged.connect(self._update_node)
        widget.valueChanged.connect(self.on_value_changed)

    def _update_node(self):
        if self.node.graph is not None:
            QtCore.QTimer.singleShot(0, self.node.graph.viewer().force_update)

    def get_port_func(self):
        vars = [f"input.{port.name()}" for port in self.node.input_ports()]
        for port in self.node.input_ports():
            connected_ports = port.connected_ports()
            for connected_port in connected_ports:
                safe_name = connected_port.node().name().replace(" ", "_")
                vars.append(f"input.{safe_name}_{connected_port.name()}")

        return vars

    def get_value(self):
        return self.get_custom_widget().get_data()

    def set_value(self, value):
        # 确保节点已加入 scene
        widget = self.get_custom_widget()
        if widget:
            widget.set_data(value)
            self._update_node()