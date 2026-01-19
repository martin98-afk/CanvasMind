# -*- coding: utf-8 -*-
from NodeGraphQt import NodeBaseWidget
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import QSize
from Qt import QtWidgets, QtCore, QtGui
from qfluentwidgets import FluentIcon, TransparentPushButton, TransparentToolButton

from app.components.base import PropertyType
from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionLineEdit
from app.widgets.node_widget.base import CustomNodeBaseWidget
from app.widgets.node_widget.checkbox_widget import CheckBoxWidget
from app.widgets.node_widget.longtext_dialog import LongTextWidget
from app.widgets.node_widget.range_widget import RangeWidget
from app.widgets.node_widget.variable_combo_widget import VarComboBoxWidget


class FormFieldWidget(QtWidgets.QWidget):
    """
    表单单行字段组件。
    优化了销毁逻辑，防止在场景中留下幽灵残影。
    """
    removed = QtCore.Signal(object)
    changed = QtCore.Signal()

    def __init__(self, schema, home=None, parent=None, get_port_func=lambda: [], index=1):
        super(FormFieldWidget, self).__init__(parent)
        self.schema = schema
        self.home = home
        self.fields = {}

        self._init_ui(get_port_func, index)

    def _init_ui(self, get_port_func, index):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        for key, defn in self.schema.items():
            field_type = defn["type"]
            label = defn.get("label", "")
            name = defn.get("name", "")
            default = defn.get("default", "")

            if isinstance(default, str) and "{{id}}" in default:
                default = default.replace("{{id}}", str(index))

            # 构建垂直布局：标题 + 输入框
            sub_layout = QtWidgets.QVBoxLayout()
            sub_layout.setContentsMargins(0, 0, 0, 0)
            sub_layout.setSpacing(2)

            # 标签
            label_widget = QtWidgets.QLabel(f"{label} ({name}):" if name else f"{label}:")
            label_widget.setStyleSheet("QLabel { font-weight: bold; color: white; font-size: 11px; }")
            sub_layout.addWidget(label_widget)

            # 输入框容器
            input_row = QtWidgets.QHBoxLayout()
            input_row.setContentsMargins(0, 0, 0, 0)

            # 根据类型创建控件
            if field_type == PropertyType.LONGTEXT.name:
                widget = LongTextWidget(parent=self.home, default_text=default, get_port_func=get_port_func)
                widget.summary_label.setFixedWidth(180)
                widget.valueChanged.connect(self.changed)
                widget.set_value(default)
                self.fields[key] = widget
                input_row.addWidget(widget)

            elif field_type == PropertyType.CHOICE.name:
                widget = CustomComboBox(parent=self.home)
                widget.addItems(defn.get("choices", []))
                widget.setCurrentText(str(default) if default else defn.get("choices", [""])[0])
                widget.currentTextChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            elif field_type == PropertyType.VARIABLE.name:
                widget = VarComboBoxWidget(main_window=self.home, type=default, parent=self)
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            elif field_type == PropertyType.RANGE.name:
                widget = RangeWidget(
                    min_val=defn.get("min", 0), max_val=defn.get("max", 100),
                    step=defn.get("step", 1), default=default, parent=self
                )
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            elif field_type == PropertyType.BOOL.name:
                widget = CheckBoxWidget(text=label, state=bool(default), parent=self)
                widget.valueChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            else:
                gv = getattr(self.home, 'global_variables', None)
                widget = VariableCompletionLineEdit(
                    get_variable_list_func=lambda func=get_port_func: gv.get_vars(func()) if gv else [],
                    use_qcursor=True, parent=self.home
                )
                widget.setFixedWidth(180)
                widget.setPlaceholderText(label)
                widget.setText(str(default))
                widget.textChanged.connect(self.changed)
                self.fields[key] = widget
                input_row.addWidget(widget)

            sub_layout.addLayout(input_row)
            layout.addLayout(sub_layout)

        # 移除按钮
        btn_remove = TransparentToolButton(FluentIcon.DELETE, parent=self)
        btn_remove.setFixedSize(24, 32)
        btn_remove.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(btn_remove, 0, QtCore.Qt.AlignBottom)

    def get_data(self):
        data = {}
        for k, v in self.fields.items():
            if hasattr(v, 'get_value'):
                data[k] = v.get_value()
            elif hasattr(v, 'text'):
                data[k] = v.text()
            elif hasattr(v, 'currentText'):
                data[k] = v.currentText()
            else:
                data[k] = ""
        return data

    def set_data(self, data):
        """仅在数据有差异时更新，防止触发死循环刷新"""
        for k, v in data.items():
            if k in self.fields:
                widget = self.fields[k]
                widget.blockSignals(True)
                if hasattr(widget, 'set_value'):
                    widget.set_value(str(v))
                elif hasattr(widget, 'setText'):
                    widget.setText(str(v))
                elif hasattr(widget, 'setCurrentText'):
                    widget.setCurrentText(str(v))
                widget.blockSignals(False)


class DynamicFormWidget(QtWidgets.QWidget):
    """
    动态表单容器部件。
    """
    sizeHintChanged = QtCore.Signal()
    valueChanged = QtCore.Signal(object)

    def __init__(self, schema, parent=None, label=None, get_port_func=lambda: []):
        super(DynamicFormWidget, self).__init__()
        self.parent = parent
        self.schema = schema
        self.label = label or "项"
        self.get_port_func = get_port_func
        self.field_widgets = []
        self._batch_mode = False
        self.field_width = None

        self._init_ui()

    def _init_ui(self):
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        self.btn_add = TransparentPushButton(FluentIcon.ADD, f"添加{self.label}", self)
        self.btn_add.clicked.connect(lambda: self.add_field())
        self.main_layout.addWidget(self.btn_add)

        self.container = QtWidgets.QVBoxLayout()
        self.container.setSpacing(6)
        self.main_layout.addLayout(self.container)
        self.main_layout.addStretch(1)

    def add_field(self, data=None):
        field = FormFieldWidget(
            self.schema, home=self.parent, parent=self,
            get_port_func=self.get_port_func, index=len(self.field_widgets) + 1
        )
        if data:
            field.set_data(data)

        field.removed.connect(self.remove_field)
        field.changed.connect(self._on_field_changed)

        self.field_widgets.append(field)
        self.container.addWidget(field)

        if not self._batch_mode:
            self._notify_update()

    def remove_field(self, field):
        if field not in self.field_widgets:
            return
        self.field_widgets.remove(field)
        self.container.removeWidget(field)
        field.hide()
        field.deleteLater()

        # 强制立即刷新布局树，不要等下一帧
        self.main_layout.activate()
        self.updateGeometry()  # 告诉系统 sizeHint 变了

        if not self._batch_mode:
            # 延迟 10ms 确保控件彻底从底层树移除后再触发同步
            QtCore.QTimer.singleShot(10, self._notify_update)

    def _on_field_changed(self):
        if not self._batch_mode:
            self.valueChanged.emit(self.get_data())

    def _notify_update(self):
        self.updateGeometry()
        self.sizeHintChanged.emit()
        self.valueChanged.emit(self.get_data())

    def get_data(self):
        return [f.get_data() for f in self.field_widgets]

    def set_data(self, data_list):
        """
        核心优化：脏检查逻辑。
        如果新传入的数据与当前数据一致，则不执行重建操作。
        """
        new_data = data_list or []
        if self.get_data() == new_data:
            return

        self._batch_mode = True

        # 物理清空旧部件
        for f in self.field_widgets[:]:
            self.remove_field(f)

        # 重建新部件
        for item in new_data:
            self.add_field(item)

        self._batch_mode = False
        self._notify_update()

    def sizeHint(self):
        h = self.btn_add.sizeHint().height() + 10
        w = self.btn_add.sizeHint().width()
        for f in self.field_widgets:
            f_hint = f.sizeHint()
            h += f_hint.height() + self.container.spacing()
            w = max(w, f_hint.width())
            self.field_width = w
        return QtCore.QSize(self.field_width or w, h)


class DynamicFormWidgetWrapper(CustomNodeBaseWidget):
    """
    表单部件的图形代理包装器。
    解决了加载过程中的几何尺寸同步问题。
    """

    def __init__(self, parent=None, name="", label="", schema=None, window=None, z_value=1):
        super(DynamicFormWidgetWrapper, self).__init__(parent, name, label)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.window = window
        self._name = name

        widget = DynamicFormWidget(schema or {}, parent=window, label=label, get_port_func=self.get_port_func)
        self.set_custom_widget(widget)

        widget.sizeHintChanged.connect(self._sync_node_geometry)
        widget.valueChanged.connect(self.on_value_changed)

    def _sync_node_geometry(self):
        """
        核心修复：强制同步 QGraphicsProxyWidget 的尺寸，防止产生残影。
        """
        if not self.node or not self.node.view:
            return

        # CustomNodeBaseWidget 本身就是 Proxy 对象
        self.setGeometry(self.boundingRect())

        view = self.node.view
        view.set_proxy_mode(False)
        view.prepareGeometryChange()
        view.draw_node()
        view.update()

    def get_port_func(self):
        if not self.node:
            return []
        vars_path = [f"input.{p.name()}" for p in self.node.input_ports()]
        for p in self.node.input_ports():
            for connected in p.connected_ports():
                safe_name = connected.node().name().replace(" ", "_")
                vars_path.append(f"input.{safe_name}__{connected.name()}")
        return vars_path

    def get_value(self):
        return self.get_custom_widget().get_data()

    def set_value(self, value):
        widget = self.get_custom_widget()
        if widget:
            widget.set_data(value)
            # 使用异步队列，确保在加载阶段完成后执行几何刷新
            QtCore.QTimer.singleShot(0, self._sync_node_geometry)

    def _update_node(self):
        """由基类 CustomNodeBaseWidget 继承，此处显式调用重绘"""
        self._sync_node_geometry()