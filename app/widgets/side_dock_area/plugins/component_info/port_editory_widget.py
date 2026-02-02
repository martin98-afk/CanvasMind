# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSizePolicy, QTableWidgetItem
from qfluentwidgets import ComboBox, TransparentToolButton, FluentIcon

from app.components.base import ArgumentType, ConnectionType
from app.widgets.side_dock_area.plugins.component_info.config_table import ConfigTableSpace


class PortEditorWidget(ConfigTableSpace):
    def __init__(self, port_type="input", parent=None):
        self.port_type = port_type
        self.port_description = {}
        labels = ["端口名称", "端口标签", "端口类型", "连接方式"] if port_type == "input" else ["端口名称", "端口标签", "端口类型"]
        super().__init__(column_labels=labels, parent=parent)

    def _generate_unique_key(self, base: str = "key") -> str:
        base = "input" if self.port_type == "input" else "output"
        existing = self._get_existing_keys()
        if f"{base}{1}" not in existing:
            return f"{base}{1}"
        i = 2
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"

    def _fill_row_content(self, row: int):
        # 构造 UI，但不连接信号（避免中间 emit）
        label = f"输入{row + 1}" if self.port_type == "input" else f"输出{row + 1}"
        label_item = QTableWidgetItem(label)
        label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 1, label_item)

        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none; background: transparent; color: white;")
        type_combo.setFixedHeight(28)
        for item in ArgumentType:
            type_combo.addItem(item.value, userData=item)
        type_combo.setCurrentText(ArgumentType.TEXT.value)
        self.table.setCellWidget(row, 2, type_combo)

        if self.port_type == "input":
            conn_combo = ComboBox()
            conn_combo.setStyleSheet("border: none; background: transparent; color: white;")
            conn_combo.setFixedHeight(28)
            conn_combo.addItems([ConnectionType.SINGLE.value, ConnectionType.MULTIPLE.value])
            conn_combo.setProperty("raw_values", [ConnectionType.SINGLE, ConnectionType.MULTIPLE])
            conn_combo.setCurrentIndex(0)
            self.table.setCellWidget(row, 3, conn_combo)

        # 构造完成后再连接信号
        type_combo.currentTextChanged.connect(self.dataChanged.emit)
        if self.port_type == "input":
            conn_combo.currentIndexChanged.connect(self.dataChanged.emit)

    def _add_row_with_data(self, row_data):
        # 手动构造行（不走 _add_row）
        row = self.table.rowCount()
        self.table.insertRow(row)

        name = row_data.get("name", self._generate_unique_key())
        name_item = QTableWidgetItem(name)
        name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 0, name_item)

        label = row_data.get("label", "")
        label_item = QTableWidgetItem(label)
        label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 1, label_item)

        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none; background: transparent; color: white;")
        type_combo.setFixedHeight(28)
        for item in ArgumentType:
            type_combo.addItem(item.value, userData=item)
        port_type = row_data.get("type", ArgumentType.TEXT)
        type_val = port_type.value if hasattr(port_type, 'value') else port_type
        type_combo.setCurrentText(type_val)
        self.table.setCellWidget(row, 2, type_combo)
        description = row_data.get("description", "")
        if description:
            self.port_description[name] = description
        if self.port_type == "input":
            conn_combo = ComboBox()
            conn_combo.setStyleSheet("border: none; background: transparent; color: white;")
            conn_combo.setFixedHeight(28)
            conn_combo.addItems([ConnectionType.SINGLE.value, ConnectionType.MULTIPLE.value])
            conn_combo.setProperty("raw_values", [ConnectionType.SINGLE, ConnectionType.MULTIPLE])
            connection = row_data.get("connection", ConnectionType.SINGLE)
            idx = 0 if connection == ConnectionType.SINGLE else 1
            conn_combo.setCurrentIndex(idx)
            self.table.setCellWidget(row, 3, conn_combo)

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("删除此端口")
        delete_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        delete_btn.clicked.connect(self._on_delete_button_clicked)
        self.table.setCellWidget(row, self.table.columnCount() - 1, delete_btn)

        # 连接信号（只 connect 一次）
        type_combo.currentTextChanged.connect(self.dataChanged.emit)
        if self.port_type == "input":
            conn_combo.currentIndexChanged.connect(self.dataChanged.emit)

        # 手动触发一次完整变更
        self.dataChanged.emit()

    def _get_cell_value(self, row: int, col: int):
        widget = self.table.cellWidget(row, col)
        if widget is None:
            item = self.table.item(row, col)
            return item.text() if item else ""
        if isinstance(widget, ComboBox):
            if col == 2:  # 类型列
                data = widget.currentData()
                if data is not None:
                    return data
                # fallback: 通过文本反查枚举
                text = widget.currentText()
                for item in ArgumentType:
                    if item.value == text:
                        return item
                return ArgumentType.TEXT
            elif col == 3 and self.port_type == "input":
                raw_vals = widget.property("raw_values")
                if raw_vals:
                    return raw_vals[widget.currentIndex()]
                return ConnectionType.SINGLE
        return ""

    def get_ports(self, serialize=False):
        ports = []
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
            label = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            port_type = self._get_cell_value(row, 2)
            connection = self._get_cell_value(row, 3) if self.port_type == "input" else ConnectionType.SINGLE

            if serialize:
                # 确保 serialize 时是字符串
                port_type = port_type.value if hasattr(port_type, 'value') else port_type
                connection = connection.value if hasattr(connection, 'value') else connection
            port_info = {
                "name": name,
                "label": label,
                "type": port_type,
                "connection": connection,
            }
            if label in self.port_description:
                port_info["description"] = self.port_description[label]
            ports.append(port_info)
        return ports

    def set_ports(self, ports):
        self.port_description.clear()
        self.table.setRowCount(0)
        for port in ports:
            self._add_row_with_data(port)

    @property
    def ports_changed(self):
        return self.dataChanged

    def add_port(self):
        self._add_row()