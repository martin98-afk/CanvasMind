from Qt import QtWidgets, QtCore


class DataTableWidget(QtWidgets.QTableWidget):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 200)

    def set_value(self, data_list):
        """期望输入: [{"name": "A", "val": 1}, {"name": "B", "val": 2}]"""
        self.clear()
        if not data_list or not isinstance(data_list, list):
            self.setFixedSize(200, 150)
            return

        # 提取表头
        headers = list(data_list[0].keys()) if isinstance(data_list[0], dict) else []
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(data_list))

        for r, row_data in enumerate(data_list):
            for c, header in enumerate(headers):
                val = row_data.get(header, "")
                self.setItem(r, c, QtWidgets.QTableWidgetItem(str(val)))
        
        self.setFixedSize(500, 300)
        self.sizeHintChanged.emit()

    def sizeHint(self):
        return self.size()