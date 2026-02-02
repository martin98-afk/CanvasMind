# -*- coding: utf-8 -*-
from Qt import QtWidgets, QtCore, QtGui
from qfluentwidgets import FluentIcon, TransparentPushButton, TransparentToolButton, LineEdit, SwitchButton
from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.node_widget.base import CustomNodeBaseWidget
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET


class TreeContainer(QtWidgets.QWidget):
    """
    专门用于包裹子节点的容器，负责绘制左侧的层级引导线
    """

    def __init__(self, parent=None):
        super(TreeContainer, self).__init__(parent)

    def paintEvent(self, event):
        if not self.isVisible():
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 设置线条颜色（半透明白色或深灰色，根据你的主题调整）
        color = QtGui.QColor(255, 255, 255, 40)  # 40 是透明度
        pen = QtGui.QPen(color, 1)
        pen.setStyle(QtCore.Qt.SolidLine)  # 也可以用 DashLine
        painter.setPen(pen)

        # 线条绘制在左侧 10px 处（对应父级 20px 缩进的一半）
        # 顶部预留一点距离，看起来更自然
        x = 10
        painter.drawLine(x, 0, x, self.height())


class JsonTreeNode(QtWidgets.QWidget):
    removed = QtCore.Signal(object)
    changed = QtCore.Signal()
    sizeChanged = QtCore.Signal()

    TYPES = ["String", "Number", "Boolean", "Object", "Array"]

    def __init__(self, parent=None, level=0, is_array_item=False):
        super(JsonTreeNode, self).__init__(parent)
        self.level = level
        self.is_array_item = is_array_item
        self.child_nodes = []
        self.is_expanded = True
        self._init_ui()

    def _init_ui(self):
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- 节点控制行 ---
        self.row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(self.row_widget)
        row_layout.setContentsMargins(2, 2, 2, 2)
        row_layout.setSpacing(6)

        # 1. 展开/收起按钮
        self.btn_expand = TransparentToolButton(FluentIcon.CHEVRON_DOWN_MED, self)
        self.btn_expand.setFixedSize(20, 20)
        self.btn_expand.setVisible(False)
        self.btn_expand.clicked.connect(self.toggle_expand)
        row_layout.addWidget(self.btn_expand)

        # 2. Key 编辑框
        if self.is_array_item:
            self.key_label = QtWidgets.QLabel("Item:")
            self.key_label.setStyleSheet("color: #aaaaaa; font-family: Consolas; font-size: 11px;")
            row_layout.addWidget(self.key_label)
            self.key_edit = None
        else:
            self.key_edit = LineEdit(self)
            self.key_edit.setPlaceholderText("Key")
            self.key_edit.setMinimumWidth(100)
            self.key_edit.setMaximumWidth(200)
            self.key_edit.textChanged.connect(lambda: self.changed.emit())
            row_layout.addWidget(self.key_edit)

        # 3. 类型切换
        self.type_combo = CustomComboBox(self)
        self.type_combo.addItems(self.TYPES)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        row_layout.addWidget(self.type_combo)

        # 4. Value 编辑区域
        self.value_stack = QtWidgets.QStackedWidget()
        self.value_stack.setFixedHeight(32)

        self.val_edit = LineEdit()
        self.val_edit.setMinimumWidth(150)
        self.val_edit.setPlaceholderText("Value")
        self.val_edit.textChanged.connect(lambda: self.changed.emit())
        self.value_stack.addWidget(self.val_edit)

        self.bool_switch = SwitchButton()
        self.bool_switch.checkedChanged.connect(lambda: self.changed.emit())
        bool_container = QtWidgets.QWidget()
        bool_l = QtWidgets.QHBoxLayout(bool_container)
        bool_l.setContentsMargins(5, 0, 0, 0)
        bool_l.addWidget(self.bool_switch)
        bool_l.addStretch()
        self.value_stack.addWidget(bool_container)

        self.btn_add_child = TransparentToolButton(FluentIcon.ADD, self)
        self.btn_add_child.setFixedSize(28, 28)
        self.btn_add_child.clicked.connect(lambda: self.add_child())
        self.value_stack.addWidget(self.btn_add_child)

        row_layout.addWidget(self.value_stack, 1)

        self.btn_remove = TransparentToolButton(FluentIcon.DELETE, self)
        self.btn_remove.setFixedSize(24, 24)
        self.btn_remove.clicked.connect(lambda: self.removed.emit(self))
        row_layout.addWidget(self.btn_remove)

        self.main_layout.addWidget(self.row_widget)

        # --- 修改点：使用自定义的 TreeContainer ---
        self.child_container = TreeContainer(self)
        self.child_layout = QtWidgets.QVBoxLayout(self.child_container)
        self.child_layout.setContentsMargins(20, 0, 0, 0)  # 20px 缩进
        self.child_layout.setSpacing(2)
        self.main_layout.addWidget(self.child_container)
        self.child_container.hide()

    def _on_type_changed(self, type_str):
        if type_str in ["Object", "Array"]:
            self.value_stack.setCurrentIndex(2)
            self.btn_expand.setVisible(True)
            self.child_container.show()
        else:
            self.clear_all_children()
            self.btn_expand.setVisible(False)
            self.child_container.hide()
            if type_str == "Boolean":
                self.value_stack.setCurrentIndex(1)
            else:
                self.value_stack.setCurrentIndex(0)

        self.changed.emit()
        self.sizeChanged.emit()

    def clear_all_children(self):
        for child in self.child_nodes[:]:
            self.remove_child(child)
        self.child_nodes = []

    def toggle_expand(self):
        self.is_expanded = not self.is_expanded
        self.child_container.setVisible(self.is_expanded)
        icon = FluentIcon.CHEVRON_DOWN_MED if self.is_expanded else FluentIcon.CHEVRON_RIGHT_MED
        self.btn_expand.setIcon(icon)
        self.updateGeometry()
        self.sizeChanged.emit()

    def add_child(self, key="", value=None):
        is_parent_array = self.type_combo.currentText() == "Array"
        child = JsonTreeNode(parent=self, level=self.level + 1, is_array_item=is_parent_array)

        if key and not is_parent_array:
            child.key_edit.setText(str(key))

        child.removed.connect(self.remove_child)
        child.changed.connect(self.changed)
        child.sizeChanged.connect(self.sizeChanged)

        self.child_nodes.append(child)
        self.child_layout.addWidget(child)

        if value is not None:
            child.set_value(value)

        if not self.is_expanded:
            self.toggle_expand()

        self.changed.emit()
        self.sizeChanged.emit()
        return child

    def remove_child(self, child):
        if child in self.child_nodes:
            self.child_nodes.remove(child)
            self.child_layout.removeWidget(child)
            child.hide()
            child.deleteLater()
            self.changed.emit()
            self.sizeChanged.emit()

    def get_value(self):
        t = self.type_combo.currentText()
        if t == "String": return self.val_edit.text()
        if t == "Number":
            val = self.val_edit.text()
            try:
                return float(val) if '.' in val else int(val)
            except:
                return 0
        if t == "Boolean": return self.bool_switch.isChecked()
        if t == "Object":
            return {c.key_edit.text(): c.get_value() for c in self.child_nodes if c.key_edit}
        if t == "Array":
            return [c.get_value() for c in self.child_nodes]

    def set_value(self, value):
        self.blockSignals(True)
        self.clear_all_children()

        if isinstance(value, bool):
            self.type_combo.setCurrentText("Boolean")
            self.bool_switch.setChecked(value)
            self.value_stack.setCurrentIndex(1)
        elif isinstance(value, (int, float)):
            self.type_combo.setCurrentText("Number")
            self.val_edit.setText(str(value))
            self.value_stack.setCurrentIndex(0)
        elif isinstance(value, dict):
            self.type_combo.setCurrentText("Object")
            self.value_stack.setCurrentIndex(2)
            self.child_container.show()
            self.btn_expand.setVisible(True)
            for k, v in value.items():
                self.add_child(k, v)
        elif isinstance(value, list):
            self.type_combo.setCurrentText("Array")
            self.value_stack.setCurrentIndex(2)
            self.child_container.show()
            self.btn_expand.setVisible(True)
            for item in value:
                self.add_child("", item)
        else:
            self.type_combo.setCurrentText("String")
            self.val_edit.setText(str(value))
            self.value_stack.setCurrentIndex(0)

        self.blockSignals(False)


class JsonTreeWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()
    fixed_height = True

    def __init__(self, parent=None):
        super(JsonTreeWidget, self).__init__(parent)
        self.main_window = parent
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(2, 2, 2, 2)
        self.main_layout.setSpacing(4)

        self.btn_add_root = TransparentPushButton(FluentIcon.ADD, "添加根节点", self)
        self.btn_add_root.clicked.connect(lambda: self.add_root())
        self.main_layout.addWidget(self.btn_add_root)

        # 根容器不需要画线，所以直接用普通的 QWidget
        self.container_widget = QtWidgets.QWidget()
        self.container_layout = QtWidgets.QVBoxLayout(self.container_widget)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(2)
        self.main_layout.addWidget(self.container_widget)

        self.main_layout.addStretch(1)
        self.root_nodes = []

    def add_root(self, key="", value=None):
        node = JsonTreeNode(level=0)
        if key: node.key_edit.setText(key)
        if value is not None: node.set_value(value)

        node.removed.connect(self.remove_root)
        node.changed.connect(self._on_changed)
        node.sizeChanged.connect(self._on_size_changed)

        self.root_nodes.append(node)
        self.container_layout.addWidget(node)
        self._on_changed()

    def remove_root(self, node):
        if node in self.root_nodes:
            self.root_nodes.remove(node)
            node.hide()
            node.deleteLater()
            self._on_changed()

    def _on_changed(self):
        self.valueChanged.emit(self.get_value())
        self._on_size_changed()

    def _on_size_changed(self):
        self.container_layout.activate()
        self.main_layout.activate()
        self.updateGeometry()
        self.sizeHintChanged.emit()

    def get_value(self):
        res = {}
        for n in self.root_nodes:
            if n.key_edit:
                res[n.key_edit.text()] = n.get_value()
        return res

    def set_value(self, data):
        if not isinstance(data, dict): return
        if data == self.get_value(): return

        # 批量操作防止多次重绘
        self.blockSignals(True)
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.root_nodes = []

        for k, v in data.items():
            self.add_root(k, v)
        self.blockSignals(False)
        self._on_size_changed()

    def sizeHint(self):
        h = self.btn_add_root.height() + self.container_layout.sizeHint().height() + 20
        return QtCore.QSize(350, h)


class DynamicTreeWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", window=None, z_value=1):
        super(DynamicTreeWidgetWrapper, self).__init__(parent, name, label)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_label(f"{label}({name})")
        self.tree_widget = JsonTreeWidget(window)
        self.set_custom_widget(self.tree_widget)

        self.tree_widget.sizeHintChanged.connect(self._sync_node_geometry)
        self.tree_widget.valueChanged.connect(self.on_value_changed)

    def _sync_node_geometry(self):
        """同步 Proxy 尺寸到 Node 视图"""
        # 关键修复：延迟一帧同步，确保 Qt 已经完成了所有的布局刷新计算
        QtCore.QTimer.singleShot(10, self._do_sync)

    def _do_sync(self):
        if not self.node or not self.node.view:
            return

        # 重新设置 geometry 会触发 ProxyWidget 重新查询 sizeHint
        self.setGeometry(self.boundingRect())

        view = self.node.view
        view.prepareGeometryChange()
        # 强制 NodeGraph 重绘背景板
        if hasattr(view, 'draw_node'):
            view.draw_node()
        view.update()

    def get_value(self):
        return self.tree_widget.get_value()

    def set_value(self, value):
        self.tree_widget.set_value(value)
        # 加载数据后同步一次高度
        self._sync_node_geometry()