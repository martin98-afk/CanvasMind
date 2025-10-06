# dynamic_node_demo.py
import sys
from Qt import QtWidgets, QtCore, QtGui
from NodeGraphQt import NodeGraph, BaseNode, NodeBaseWidget


class DynamicFieldWidget(QtWidgets.QWidget):
    removed = QtCore.Signal(object)

    def __init__(self, parent=None, field_id=None):
        super(DynamicFieldWidget, self).__init__(parent)
        self.field_id = field_id or id(self)

        self.setStyleSheet("""
            QLineEdit {
                background: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555;
                padding: 2px;
                border-radius: 3px;
            }
            QComboBox {
                background: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555;
                padding: 2px;
                border-radius: 3px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: #2d2d2d;
                color: #ffffff;
                selection-background-color: #3a3a3a;
            }
        """)

        self.line_edit = QtWidgets.QLineEdit()
        self.line_edit.setPlaceholderText("Field name")
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems(['text', 'number', 'boolean'])
        self.btn_remove = QtWidgets.QPushButton('×')
        self.btn_remove.setFixedSize(20, 20)
        self.btn_remove.setStyleSheet("""
            QPushButton {
                background: #ff6b6b;
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background: #ff5252; }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.combo)
        layout.addWidget(self.btn_remove)

        self.btn_remove.clicked.connect(lambda: self.removed.emit(self))

    def get_data(self):
        return {
            'id': self.field_id,
            'name': self.line_edit.text(),
            'type': self.combo.currentText()
        }

    def set_data(self, data):
        self.field_id = data.get('id', self.field_id)
        self.line_edit.setText(data.get('name', ''))
        idx = self.combo.findText(data.get('type', 'text'), QtCore.Qt.MatchExactly)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)


class MyCustomWidget(QtWidgets.QWidget):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super(MyCustomWidget, self).__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.MinimumExpanding)
        self.fields = []

        self.btn_add = QtWidgets.QPushButton('➕ Add Field')
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: #4a4a4a;
                color: #e0e0e0;
                border: 1px solid #666;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background: #5a5a5a; }
        """)
        self.field_layout = QtWidgets.QVBoxLayout()
        self.field_layout.setSpacing(6)
        self.field_layout.setContentsMargins(0, 6, 0, 0)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)
        main_layout.addWidget(self.btn_add)
        main_layout.addLayout(self.field_layout)

        self.btn_add.clicked.connect(self.add_field)

    def add_field(self, data=None):
        field_widget = DynamicFieldWidget(field_id=data['id'] if data else None)
        if  data:  # 修复：判断 data 是否存在
            field_widget.set_data(data)
        field_widget.removed.connect(self.remove_field)
        self.fields.append(field_widget)
        self.field_layout.addWidget(field_widget)
        self.sizeHintChanged.emit()

    def remove_field(self, field_widget):
        if field_widget in self.fields:
            self.fields.remove(field_widget)
            self.field_layout.removeWidget(field_widget)
            field_widget.setParent(None)
            field_widget.deleteLater()
            self.sizeHintChanged.emit()

    # ✅ 关键：这两个方法必须存在！
    def get_all_data(self):
        return [f.get_data() for f in self.fields]

    def set_all_data(self, data_list):
        for f in self.fields[:]:
            self.remove_field(f)
        for data in data_list or []:
            self.add_field(data)
        self.sizeHintChanged.emit()


class NodeWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None):
        super(NodeWidgetWrapper, self).__init__(parent)
        self.set_name('dynamic_fields')
        self.set_label('Dynamic Fields')
        custom_widget = MyCustomWidget()
        self.set_custom_widget(custom_widget)
        custom_widget.sizeHintChanged.connect(self._on_size_changed)

    def _on_size_changed(self):
        if self.node and self.node.view:
            QtCore.QTimer.singleShot(0, self._do_update)

    def _do_update(self):
        if self.node and self.node.view:
            self.node.view.update()
            self.node.view.draw_node()

    def get_value(self):
        return self.get_custom_widget().get_all_data()

    def set_value(self, value):
        self.get_custom_widget().set_all_data(value)
        self._on_size_changed()


class MyNode(BaseNode):
    __identifier__ = 'com.example'
    NODE_NAME = 'Dynamic Form Node'

    def __init__(self):
        super(MyNode, self).__init__()
        self.add_input('in', color=(180, 80, 180))
        self.add_output('out', color=(80, 180, 80))
        widget = NodeWidgetWrapper(self.view)
        self.add_custom_widget(widget, tab='Custom')


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    app.setStyle("Fusion")
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.Window, QtGui.QColor(53, 53, 53))
    dark_palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(35, 35, 35))
    dark_palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(53, 53, 53))
    dark_palette.setColor(QtGui.QPalette.ToolTipBase, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.ToolTipText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Button, QtGui.QColor(53, 53, 53))
    dark_palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    dark_palette.setColor(QtGui.QPalette.Link, QtGui.QColor(42, 130, 218))
    dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(42, 130, 218))
    dark_palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.black)
    app.setPalette(dark_palette)

    graph = NodeGraph()
    graph.register_node(MyNode)

    node = graph.create_node('com.example.MyNode')

    viewer = graph.viewer()
    viewer.resize(1100, 800)
    viewer.show()

    def print_graph_data():
        data = graph.serialize_session()
        print("\n" + "="*50)
        print("Serialized Graph Data:")
        print("="*50)
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))

    btn = QtWidgets.QPushButton("🖨️ Print Graph Data")
    btn.setStyleSheet("background: #4a4a4a; color: #e0e0e0; border: 1px solid #666; padding: 4px 8px; border-radius: 4px;")
    btn.clicked.connect(print_graph_data)
    btn.setParent(viewer)
    btn.move(20, 20)
    btn.show()

    sys.exit(app.exec_())