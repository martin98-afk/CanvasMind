# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView
)
from qfluentwidgets import (
    BodyLabel, TableWidget, ComboBox, FluentIcon, TransparentToolButton, SimpleCardWidget
)

from app.components.base import ArgumentType, ConnectionType


class PortEditorWidget(SimpleCardWidget):
    """端口编辑器 - 支持动态添加删除"""
    ports_changed = pyqtSignal()

    def __init__(self, port_type="input", parent=None):
        super().__init__(parent)
        self.port_type = port_type
        layout = QVBoxLayout(self)
        # 表格：增加第4列
        self.table = TableWidget(self)
        if port_type == "input":
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["端口名称", "端口标签", "端口类型", "连接方式"])
        else:
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["端口名称", "端口标签", "端口类型"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda item: self.ports_changed.emit())
        button_layout = QHBoxLayout()
        button_layout.addWidget(BodyLabel("输入端口:" if port_type == "input" else "输出端口:"))
        add_btn = TransparentToolButton(FluentIcon.ADD, parent=self)
        add_btn.setToolTip("添加参数")
        add_btn.setFixedSize(25, 25)
        add_btn.clicked.connect(lambda: self._add_port())
        remove_btn = TransparentToolButton(FluentIcon.DELETE, parent=self)
        remove_btn.setToolTip("删除添加参数")
        remove_btn.setFixedSize(25, 25)
        remove_btn.clicked.connect(self._remove_port)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        layout.addWidget(self.table)

    def _add_port(self, port: dict = {}):
        row = self.table.rowCount()
        self.table.insertRow(row)

        name = port.get("name", f"input{row + 1}" if self.port_type == "input" else f"output{row + 1}")
        label = port.get("label", f"输入{row + 1}" if self.port_type == "input" else f"输出{row + 1}")
        port_type = port.get("type", ArgumentType.TEXT)

        # 设置文本项 + 垂直居中
        name_item = QTableWidgetItem(name)
        name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        label_item = QTableWidgetItem(label)
        label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, label_item)

        # 类型下拉框
        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none;background: transparent; color: white;")
        type_combo.setFixedHeight(28)  # ✅ 统一高度
        for item in ArgumentType:
            type_combo.addItem(item.value, userData=item)
        type_combo.setCurrentText(port_type.value)
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(lambda: self.ports_changed.emit())

        if self.port_type == "input":
            connection = port.get("connection", ConnectionType.SINGLE)
            conn_combo = ComboBox()
            conn_combo.setStyleSheet("border: none;background: transparent; color: white;")
            conn_combo.setFixedHeight(28)  # ✅ 统一高度
            conn_combo.addItems([ConnectionType.SINGLE.value, ConnectionType.MULTIPLE.value])
            conn_combo.setProperty("raw_values", [ConnectionType.SINGLE, ConnectionType.MULTIPLE])
            conn_combo.setCurrentIndex(0 if connection == ConnectionType.SINGLE else 1)
            self.table.setCellWidget(row, 3, conn_combo)
            conn_combo.currentIndexChanged.connect(lambda: self.ports_changed.emit())

    def _remove_port(self):
        selected_ranges = self.table.selectedRanges()
        if selected_ranges:
            rows = []
            for range_ in selected_ranges:
                rows.extend(range(range_.topRow(), range_.bottomRow() + 1))
            rows = sorted(set(rows), reverse=True)
            for row in rows:
                self.table.removeRow(row)
            self.ports_changed.emit()

    def get_ports(self, serialize=False):
        ports = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)
            if not (name_item and label_item):
                continue
            type_widget = self.table.cellWidget(row, 2)
            port_type = type_widget.currentData() if type_widget else ArgumentType.TEXT
            conn_widget = self.table.cellWidget(row, 3)
            if conn_widget:
                raw_vals = [ConnectionType.SINGLE, ConnectionType.MULTIPLE]
                connection = raw_vals[conn_widget.currentIndex()]
            else:
                connection = ConnectionType.SINGLE
            if serialize:
                port_type = port_type.value
                connection = connection.value

            ports.append({
                "name": name_item.text(),
                "label": label_item.text(),
                "type": port_type,
                "connection": connection
            })
        return ports

    def set_ports(self, ports):
        self.table.setRowCount(0)
        for port in ports:
            self._add_port(port)