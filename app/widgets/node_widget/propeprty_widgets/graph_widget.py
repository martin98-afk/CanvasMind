from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore

from app.widgets.custom_nodegraphqt.custom_nodegraph import CustomNodeGraph, CustomNodeViewer
from app.widgets.node_widget.base import CustomNodeBaseWidget


class SubGraphWidget(QtWidgets.QWidget):
    """节点内显示：复选框"""
    valueChanged = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.graph = CustomNodeGraph(
            viewer=CustomNodeViewer(parent=self.main_window),
            parent=self.main_window
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.graph.widget)

    def get_value(self):
        return self.graph.serialize_session()

    def set_value(self, data):
        self.graph.deserialize_session(data)


class SubGraphWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", text="", window=None, z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(f"{text}({name})")
        widget = SubGraphWidget(parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)


