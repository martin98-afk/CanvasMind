# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSizePolicy, QTableWidgetItem
from qfluentwidgets import ComboBox, TransparentToolButton, FluentIcon

from app.components.base import ArgumentType, ConnectionType
from app.scan_components import ComponentScanner
from app.widgets.basic_widget.searchable_editable_combobox import SearchableEditableComboBox
from app.widgets.side_dock_area.plugins.component_info.config_table import ConfigTableSpace


class PortEditorWidget(ConfigTableSpace):
    def __init__(self, port_type="input", parent=None):
        self.port_type = port_type
        self.port_description = {}

        # 定义表头
        if port_type == "input":
            # 列索引: 0:Name, 1:Label, 2:Type, 3:Sub-Type, 4:Connection, 5:Delete
            labels = ["端口名称", "端口标签", "端口类型", "类型标识", "连接方式"]
        else:
            # 列索引: 0:Name, 1:Label, 2:Type, 3:Sub-Type, 4:Delete
            labels = ["端口名称", "端口标签", "端口类型", "类型标识"]

        super().__init__(column_labels=labels, parent=parent)
        # 1. 注册监听：当 ComponentScanner 发现代码变更导致类型增删时，触发刷新
        ComponentScanner.register_on_change(self._on_scanner_updated)
        # 初始化时先检查一次列的可见性（默认隐藏，因为初始为空）
        self._update_column_visibility()

    def closeEvent(self, event):
        """
        界面关闭/销毁时，务必取消注册，防止 ComponentScanner 调用已销毁对象的在方法
        """
        ComponentScanner.unregister_on_change(self._on_scanner_updated)
        super().closeEvent(event)

    def _on_scanner_updated(self):
        """
        回调函数：当 Scanner 数据更新时调用。
        遍历当前表格所有行，更新 SearchableEditableComboBox 的下拉选项，但不清空当前已输入的文本。
        """
        all_types = ComponentScanner()._cached_subtype_list
        for row in range(self.table.rowCount()):
            # 获取第 3 列的子类型控件
            combo = self.table.cellWidget(row, 3)
            if isinstance(combo, SearchableEditableComboBox):
                # 1. 保存当前用户已经输入或选择的内容
                current_text = combo.text()

                # 2. 清空并重新填充选项
                combo.clear()
                combo.addItems(all_types)

                # 3. 恢复之前的文本
                # SearchableEditableComboBox 的特性是 setText 如果不在 items 里也会显示
                combo.setText(current_text)

    def _generate_unique_key(self, base: str = "key") -> str:
        base = "input" if self.port_type == "input" else "output"
        existing = self._get_existing_keys()
        if f"{base}{1}" not in existing:
            return f"{base}{1}"
        i = 2
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"

    def _update_row_widget_visibility(self, row, type_val):
        """
        行级控制：控制单个单元格内控件的显隐
        """
        sub_type_widget = self.table.cellWidget(row, 3)
        if not sub_type_widget:
            return

        is_object = (type_val == ArgumentType.OBJECT)

        # 如果当前行不是对象，隐藏控件并清空内容
        sub_type_widget.setVisible(is_object)
        if not is_object:
            sub_type_widget.setText("")

        # 每次行级变更后，触发一次表级检查
        self._update_column_visibility()

    def _update_column_visibility(self):
        """
        表级控制：如果所有行都不是Object，则隐藏整列
        """
        has_object = False
        row_count = self.table.rowCount()

        for r in range(row_count):
            type_combo = self.table.cellWidget(r, 2)
            if type_combo:
                current_type = type_combo.currentData()
                if current_type == ArgumentType.OBJECT:
                    has_object = True
                    break

        # 3 是 "子类型" 列的索引
        # 如果有 Object -> not has_object = False -> setColumnHidden(False) -> 显示
        # 如果无 Object -> not has_object = True  -> setColumnHidden(True)  -> 隐藏
        self.table.setColumnHidden(3, not has_object)

    def _on_type_combo_changed(self):
        """类型下拉框变化时的槽函数"""
        combo = self.sender()
        if not combo:
            return

        index = self.table.indexAt(combo.pos())
        if not index.isValid():
            return

        row = index.row()
        val = combo.currentData()

        # 更新该行的控件可见性（这会自动触发列的可见性更新）
        self._update_row_widget_visibility(row, val)

        self.dataChanged.emit()

    def _on_delete_button_clicked(self):
        """重写删除事件，因为删除行可能导致Object消失，需要刷新列可见性"""
        sender = self.sender()
        if not sender:
            return

        index = self.table.indexAt(sender.pos())
        if not index.isValid():
            return

        row = index.row()
        name_item = self.table.item(row, 0)
        if name_item:
            name = name_item.text()
            if name in self.port_description:
                del self.port_description[name]

        self.table.removeRow(row)

        # 关键：删除后重新检查列可见性
        self._update_column_visibility()
        self.dataChanged.emit()

    def _create_row_widgets(self, row, row_data=None):
        if row_data is None:
            row_data = {}

        # --- 2. 类型 ComboBox ---
        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none; background: transparent; color: white;")
        type_combo.setFixedHeight(28)
        for item in ArgumentType:
            type_combo.addItem(item.value, userData=item)

        # 设置选中值
        port_type = row_data.get("type", ArgumentType.TEXT)
        current_data = port_type
        if hasattr(port_type, 'value'):
            current_val_str = port_type.value
        else:
            current_val_str = str(port_type)
            for item in ArgumentType:
                if item.value == current_val_str:
                    current_data = item
                    break
        type_combo.setCurrentText(current_val_str)
        self.table.setCellWidget(row, 2, type_combo)

        # --- 3. 子类型 SearchableEditableComboBox ---
        sub_type_combo = SearchableEditableComboBox()
        sub_type_combo.setStyleSheet("border: none; background: transparent; color: white;")
        sub_type_combo.setFixedHeight(28)
        sub_type_combo.setPlaceholderText("选择或输入类名")
        sub_type_combo.addItems(ComponentScanner()._cached_subtype_list)
        current_sub_type = row_data.get("sub_type", "")
        sub_type_combo.setText(current_sub_type)
        self.table.setCellWidget(row, 3, sub_type_combo)

        # --- 4. 连接方式 ComboBox (仅 Input) ---
        if self.port_type == "input":
            conn_combo = ComboBox()
            conn_combo.setStyleSheet("border: none; background: transparent; color: white;")
            conn_combo.setFixedHeight(28)
            conn_combo.addItems([ConnectionType.SINGLE.value, ConnectionType.MULTIPLE.value])
            conn_combo.setProperty("raw_values", [ConnectionType.SINGLE, ConnectionType.MULTIPLE])

            connection = row_data.get("connection", ConnectionType.SINGLE)
            idx = 0 if connection == ConnectionType.SINGLE else 1
            conn_combo.setCurrentIndex(idx)
            self.table.setCellWidget(row, 4, conn_combo)
            conn_combo.currentIndexChanged.connect(self.dataChanged.emit)

        # --- 删除按钮 ---
        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("删除此端口")
        delete_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        delete_btn.clicked.connect(self._on_delete_button_clicked)  # 连接到重写的删除方法
        self.table.setCellWidget(row, self.table.columnCount() - 1, delete_btn)

        # --- 信号连接 ---
        type_combo.currentIndexChanged.connect(self._on_type_combo_changed)
        sub_type_combo.textChanged.connect(self.dataChanged.emit)

        # --- 初始状态设置 ---
        # 立即更新该行的控件可见性（同时也会刷新整列的可见性）
        self._update_row_widget_visibility(row, current_data)

    def _fill_row_content(self, row: int):
        label = f"输入{row + 1}" if self.port_type == "input" else f"输出{row + 1}"
        label_item = QTableWidgetItem(label)
        label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 1, label_item)
        self._create_row_widgets(row)

    def _add_row_with_data(self, row_data):
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

        description = row_data.get("description", "")
        if description:
            self.port_description[name] = description

        self._create_row_widgets(row, row_data)
        self.dataChanged.emit()

    def _get_cell_value(self, row: int, col: int):
        widget = self.table.cellWidget(row, col)
        if widget is None:
            item = self.table.item(row, col)
            return item.text() if item else ""

        # 处理 SearchableEditableComboBox
        if isinstance(widget, SearchableEditableComboBox):
            if not widget.isVisible():
                return ""
            return widget.text().strip()

        # 处理 ComboBox
        if isinstance(widget, ComboBox):
            if col == 2:  # 类型列
                data = widget.currentData()
                if data is not None:
                    return data
                text = widget.currentText()
                for item in ArgumentType:
                    if item.value == text:
                        return item
                return ArgumentType.TEXT
            elif col == 4 and self.port_type == "input":
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
            sub_type = self._get_cell_value(row, 3)

            connection = self._get_cell_value(row, 4) if self.port_type == "input" else ConnectionType.SINGLE

            if serialize:
                port_type = port_type.value if hasattr(port_type, 'value') else port_type
                connection = connection.value if hasattr(connection, 'value') else connection

            port_info = {
                "name": name,
                "label": label,
                "type": port_type,
                "connection": connection,
            }

            if sub_type:
                port_info["sub_type"] = sub_type

            if label in self.port_description:
                port_info["description"] = self.port_description[label]
            ports.append(port_info)
        return ports

    def set_ports(self, ports):
        self.port_description.clear()
        self.table.setRowCount(0)
        for port in ports:
            self._add_row_with_data(port)
        # 加载完所有数据后，再强制检查一次列可见性，确保状态正确
        self._update_column_visibility()

    @property
    def ports_changed(self):
        return self.dataChanged

    def add_port(self):
        self._add_row()