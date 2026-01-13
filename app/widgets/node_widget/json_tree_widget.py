# -*- coding: utf-8 -*-
from Qt import QtWidgets, QtCore


class JsonTreeWidget(QtWidgets.QTreeWidget):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Key", "Value"])
        self.setColumnCount(2)
        self.setFixedSize(300, 200) # 默认大小

    def set_value(self, data):
        self.clear()
        if data is None:
            self.setFixedSize(200, 150)
            return
            
        if isinstance(data, (dict, list)):
            self._populate_tree(data, self.invisibleRootItem())
            self.expandAll()
            self.setFixedSize(400, 300) # 有数据时撑大一点
        self.sizeHintChanged.emit()

    def _populate_tree(self, data, parent_item):
        if isinstance(data, dict):
            for key, value in data.items():
                item = QtWidgets.QTreeWidgetItem([str(key)])
                parent_item.addChild(item)
                self._populate_tree(value, item)
        elif isinstance(data, list):
            for i, value in enumerate(data):
                item = QtWidgets.QTreeWidgetItem([f"[{i}]"])
                parent_item.addChild(item)
                self._populate_tree(value, item)
        else:
            parent_item.setText(1, str(data))

    def sizeHint(self):
        return self.size()