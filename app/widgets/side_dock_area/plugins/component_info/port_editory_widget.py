# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView, QWidget, QSizePolicy
)
from qfluentwidgets import (
    TableWidget, ComboBox, FluentIcon, TransparentToolButton, SimpleCardWidget
)

from app.components.base import ArgumentType, ConnectionType


class PortEditorWidget(SimpleCardWidget):
    """端口编辑器 - + 按钮作为最后一列表头文字，删除按钮每行一个"""
    ports_changed = pyqtSignal()

    def __init__(self, port_type="input", parent=None):
        super().__init__(parent)
        self.port_type = port_type
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        col_count = 5 if port_type == "input" else 4
        self.table = TableWidget(self)

        self.table.setColumnCount(col_count)

        if port_type == "input":
            self.table.setHorizontalHeaderLabels(["端口名称", "端口标签", "端口类型", "连接方式", "＋"])
        else:
            self.table.setHorizontalHeaderLabels(["端口名称", "端口标签", "端口类型", "＋"])
        font = QFont()
        font.setPointSize(14)  # 或 16，根据需求调整
        font.setBold(True)

        for col in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(col)
            if item and col == self.table.columnCount() - 1:  # 最后一列
                item.setFont(font)
                item.setTextAlignment(Qt.AlignCenter)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(col_count - 1, QHeaderView.ResizeToContents)

        # ← 关键：监听表头点击
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        self.table.itemChanged.connect(lambda item: self.ports_changed.emit())
        layout.addWidget(self.table)

    def _on_header_clicked(self, logical_index):
        """点击最后一列表头时触发添加"""
        if logical_index == self.table.columnCount() - 1:
            self.add_port()

    def _add_port(self, port: dict = {}):
        row = self.table.rowCount()
        self.table.insertRow(row)

        name = port.get("name", f"input{row + 1}" if self.port_type == "input" else f"output{row + 1}")
        label = port.get("label", f"输入{row + 1}" if self.port_type == "input" else f"输出{row + 1}")
        port_type = port.get("type", ArgumentType.TEXT)

        name_item = QTableWidgetItem(name)
        name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        label_item = QTableWidgetItem(label)
        label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, label_item)

        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none; background: transparent; color: white;")
        type_combo.setFixedHeight(28)
        for item in ArgumentType:
            type_combo.addItem(item.value, userData=item)
        type_combo.setCurrentText(port_type.value)
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(lambda: self.ports_changed.emit())

        col_offset = 0
        if self.port_type == "input":
            connection = port.get("connection", ConnectionType.SINGLE)
            conn_combo = ComboBox()
            conn_combo.setStyleSheet("border: none; background: transparent; color: white;")
            conn_combo.setFixedHeight(28)
            conn_combo.addItems([ConnectionType.SINGLE.value, ConnectionType.MULTIPLE.value])
            conn_combo.setProperty("raw_values", [ConnectionType.SINGLE, ConnectionType.MULTIPLE])
            conn_combo.setCurrentIndex(0 if connection == ConnectionType.SINGLE else 1)
            self.table.setCellWidget(row, 3, conn_combo)
            conn_combo.currentIndexChanged.connect(lambda: self.ports_changed.emit())
            col_offset = 1

        # === 删除按钮：直接作为 cell widget，不包裹容器 ===
        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("删除此端口")
        delete_btn.clicked.connect(self._on_delete_button_clicked)

        # 关键：设置按钮的 sizePolicy 为 Fixed，避免被 stretch
        delete_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # 直接设为 cell widget（不再用 btn_container）
        self.table.setCellWidget(row, 3 + col_offset, delete_btn)

    def _on_delete_button_clicked(self):
        """支持直接按钮（无容器）的删除"""
        button = self.sender()
        if not button:
            return
        # 遍历所有行，找到包含该按钮的行
        for row in range(self.table.rowCount()):
            cell_widget = self.table.cellWidget(row, self.table.columnCount() - 1)
            if cell_widget is button:  # 直接比较按钮对象
                self._remove_port_at(row)
                return

    def _remove_port_at(self, row: int):
        if 0 <= row < self.table.rowCount():
            self.table.removeRow(row)
            self.ports_changed.emit()

    def add_port(self):
        self._add_port()

    def get_ports(self, serialize=False):
        ports = []
        col_offset = 1 if self.port_type == "input" else 0
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)
            if not (name_item and label_item):
                continue
            type_widget = self.table.cellWidget(row, 2)
            port_type = type_widget.currentData() if type_widget else ArgumentType.TEXT

            connection = ConnectionType.SINGLE
            if self.port_type == "input":
                conn_widget = self.table.cellWidget(row, 3)
                if conn_widget:
                    raw_vals = [ConnectionType.SINGLE, ConnectionType.MULTIPLE]
                    connection = raw_vals[conn_widget.currentIndex()]

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