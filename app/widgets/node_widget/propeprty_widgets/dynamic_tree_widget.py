# -*- coding: utf-8 -*-
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import QSize
from Qt import QtWidgets, QtCore
from qfluentwidgets import FluentIcon, TransparentPushButton, TransparentToolButton

from app.widgets.basic_widget.variable_complete_widget import VariableCompletionLineEdit
from app.widgets.node_widget.base import CustomNodeBaseWidget


class TreeNodeWidget(QtWidgets.QWidget):
    """
    树节点组件：包含自身字段 + 子节点容器
    """
    removed = QtCore.Signal(object)
    changed = QtCore.Signal()
    sizeChanged = QtCore.Signal()

    def __init__(self, schema, home=None, parent=None, get_port_func=lambda: [], level=0):
        super(TreeNodeWidget, self).__init__(parent)
        self.schema = schema
        self.home = home
        self.level = level
        self.get_port_func = get_port_func
        self.fields = {}
        self.child_widgets = []
        self.is_expanded = True

        self._init_ui()

    def _init_ui(self):
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(2)

        # --- 第一行：当前节点的字段控制区 ---
        self.row_container = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(self.row_container)
        row_layout.setContentsMargins(self.level * 15, 2, 2, 2) # 根据层级缩进
        row_layout.setSpacing(6)

        # 展开/收起按钮
        self.btn_expand = TransparentToolButton(FluentIcon.CHEVRON_DOWN, self)
        self.btn_expand.setFixedSize(20, 20)
        self.btn_expand.clicked.connect(self.toggle_expand)
        row_layout.addWidget(self.btn_expand)

        # 渲染 Schema 字段 (参考你的 FormFieldWidget 逻辑)
        for key, defn in self.schema.items():
            field_type = defn["type"]
            # 这里简化了逻辑，只展示核心 LineEdit 逻辑，你可以根据原代码补齐 Choice/Range 等
            gv = getattr(self.home, 'global_variables', None)
            widget = VariableCompletionLineEdit(
                get_variable_list_func=lambda func=self.get_port_func: gv.get_vars(func()) if gv else [],
                use_qcursor=True, parent=self.home
            )
            widget.setFixedWidth(120)
            widget.setPlaceholderText(defn.get("label", key))
            widget.textChanged.connect(self.changed)
            self.fields[key] = widget
            row_layout.addWidget(widget)

        # 添加子节点按钮
        self.btn_add_child = TransparentToolButton(FluentIcon.ADD, self)
        self.btn_add_child.setFixedSize(24, 24)
        self.btn_add_child.clicked.connect(lambda: self.add_child())
        row_layout.addWidget(self.btn_add_child)

        # 移除当前节点按钮
        self.btn_remove = TransparentToolButton(FluentIcon.DELETE, self)
        self.btn_remove.setFixedSize(24, 24)
        self.btn_remove.clicked.connect(lambda: self.removed.emit(self))
        row_layout.addWidget(self.btn_remove)
        
        self.main_layout.addWidget(self.row_container)

        # --- 第二行：子节点容器 ---
        self.child_container_widget = QtWidgets.QWidget()
        self.child_container_layout = QtWidgets.QVBoxLayout(self.child_container_widget)
        self.child_container_layout.setContentsMargins(0, 0, 0, 0)
        self.child_container_layout.setSpacing(2)
        self.main_layout.addWidget(self.child_container_widget)

    def toggle_expand(self):
        self.is_expanded = not self.is_expanded
        self.child_container_widget.setVisible(self.is_expanded)
        icon = FluentIcon.CHEVRON_DOWN if self.is_expanded else FluentIcon.CHEVRON_RIGHT
        self.btn_expand.setIcon(icon)
        self.sizeChanged.emit()

    def add_child(self, data=None):
        child = TreeNodeWidget(
            self.schema, home=self.home, parent=self,
            get_port_func=self.get_port_func, level=self.level + 1
        )
        if data:
            child.set_data(data)
        
        child.removed.connect(self.remove_child)
        child.changed.connect(self.changed)
        child.sizeChanged.connect(self.sizeChanged)

        self.child_widgets.append(child)
        self.child_container_layout.addWidget(child)
        self.changed.emit()
        self.sizeChanged.emit()
        return child

    def remove_child(self, child):
        if child in self.child_widgets:
            self.child_widgets.remove(child)
            self.child_container_layout.removeWidget(child)
            child.hide()
            child.deleteLater()
            self.changed.emit()
            self.sizeChanged.emit()

    def get_data(self):
        """递归获取数据"""
        data = {"_fields": {}}
        for k, v in self.fields.items():
            data["_fields"][k] = v.text() # 简化处理，实际应参考 get_value()
        
        data["children"] = [child.get_data() for child in self.child_widgets]
        return data

    def set_data(self, data):
        """递归设置数据"""
        self.blockSignals(True)
        # 设置自身字段
        field_values = data.get("_fields", {})
        for k, v in field_values.items():
            if k in self.fields:
                self.fields[k].setText(str(v))
        
        # 构建子节点
        for child_f in self.child_widgets[:]:
            self.remove_child(child_f)
        
        for child_data in data.get("children", []):
            self.add_child(child_data)
            
        self.blockSignals(False)


class DynamicTreeWidget(QtWidgets.QWidget):
    """
    动态树根容器
    """
    sizeHintChanged = QtCore.Signal()
    valueChanged = QtCore.Signal(object)

    def __init__(self, schema, parent=None, label=None, get_port_func=lambda: []):
        super(DynamicTreeWidget, self).__init__()
        self.parent = parent
        self.schema = schema
        self.label = label or "树项"
        self.get_port_func = get_port_func
        self.root_nodes = []
        self._batch_mode = False

        self._init_ui()

    def _init_ui(self):
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        self.btn_add_root = TransparentPushButton(FluentIcon.ADD, f"添加根{self.label}", self)
        self.btn_add_root.clicked.connect(lambda: self.add_root_node())
        self.layout.addWidget(self.btn_add_root)

        self.container = QtWidgets.QVBoxLayout()
        self.container.setSpacing(2)
        self.layout.addLayout(self.container)
        self.layout.addStretch(1)

    def add_root_node(self, data=None):
        node = TreeNodeWidget(
            self.schema, home=self.parent, parent=self,
            get_port_func=self.get_port_func, level=0
        )
        if data:
            node.set_data(data)

        node.removed.connect(self.remove_root_node)
        node.changed.connect(self._on_changed)
        node.sizeChanged.connect(self._on_size_changed)

        self.root_nodes.append(node)
        self.container.addWidget(node)
        self._on_changed()

    def remove_root_node(self, node):
        if node in self.root_nodes:
            self.root_nodes.remove(node)
            self.container.removeWidget(node)
            node.hide()
            node.deleteLater()
            self._on_changed()

    def _on_changed(self):
        if not self._batch_mode:
            self.valueChanged.emit(self.get_data())

    def _on_size_changed(self):
        self.updateGeometry()
        self.sizeHintChanged.emit()

    def get_data(self):
        return [n.get_data() for n in self.root_nodes]

    def set_data(self, data_list):
        if self.get_data() == data_list:
            return
        
        self._batch_mode = True
        for n in self.root_nodes[:]:
            self.remove_root_node(n)
        
        for data in (data_list or []):
            self.add_root_node(data)
        
        self._batch_mode = False
        self._on_size_changed()
        self.valueChanged.emit(self.get_data())

    def sizeHint(self):
        # 递归计算高度
        h = self.btn_add_root.sizeHint().height() + 20
        for n in self.root_nodes:
            h += n.sizeHint().height() + self.container.spacing()
        return QSize(250, h)


class DynamicTreeWidgetWrapper(CustomNodeBaseWidget):
    """
    树控件的图形代理包装器
    """
    def __init__(self, parent=None, name="", label="", schema=None, window=None, z_value=1):
        super(DynamicTreeWidgetWrapper, self).__init__(parent, name, label)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.window = window

        widget = DynamicTreeWidget(schema or {}, parent=window, label=label, get_port_func=self.get_port_func)
        self.set_custom_widget(widget)

        widget.sizeHintChanged.connect(self._sync_node_geometry)
        widget.valueChanged.connect(self.on_value_changed)

    def _sync_node_geometry(self):
        if not self.node or not self.node.view:
            return
        self.setGeometry(self.boundingRect())
        view = self.node.view
        view.prepareGeometryChange()
        view.draw_node()
        view.update()

    def get_port_func(self):
        if not self.node: return []
        return [f"input.{p.name()}" for p in self.node.input_ports()]

    def get_value(self):
        return self.get_custom_widget().get_data()

    def set_value(self, value):
        widget = self.get_custom_widget()
        if widget:
            widget.set_data(value)
            QtCore.QTimer.singleShot(1, self._sync_node_geometry)