# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QTableWidget, QHeaderView, QTableWidgetItem
from qfluentwidgets import (
    FluentIcon, BodyLabel, TableWidget, ComboBox
)
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class ComponentHistoryToolWindow(ToolWindow):
    name = "组件历史管理"
    icon = FluentIcon.HISTORY
    singleton = True
    default_position = DockPosition.BOTTOM
    _history_table = None
    _usage_table = None
    strategy_changed = pyqtSignal(str, str, str)  # canvas_path, node_name, new_strategy

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # === 编辑历史 ===
        history_label = BodyLabel("编辑历史:")
        self._history_table = TableWidget(self)
        self._history_table.setColumnCount(2)
        self._history_table.setHorizontalHeaderLabels(["版本", "保存时间"])
        self._history_table.verticalHeader().hide()
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.setSelectionBehavior(QTableWidget.SelectItems)
        self._history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(history_label)
        layout.addWidget(self._history_table)

        # === 组件使用情况 ===
        usage_label = BodyLabel("组件使用情况:")
        self._usage_table = TableWidget(self)
        self._usage_table.setColumnCount(3)  # 画布、节点、版本策略
        self._usage_table.setHorizontalHeaderLabels(["画布", "节点名称", "版本策略"])
        self._usage_table.verticalHeader().hide()
        self._usage_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._usage_table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self._usage_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(usage_label)
        layout.addWidget(self._usage_table)

    @property
    def history_table(self):
        return self._history_table

    @property
    def usage_table(self):
        return self._usage_table

    def get_all_versions(self) -> list:
        """从 history_table 获取所有版本号（如 ["V1", "V2", "V3"]）"""
        versions = []
        for row in range(self._history_table.rowCount()):
            item = self._history_table.item(row, 0)
            if item:
                versions.append(item.text())
        return versions

    def update_usage_table(self, usage_records):
        """
        更新使用情况表格
        :param usage_records: List[dict]，每个含 keys: canvas_name, node_name, version
        """
        self._usage_table.setRowCount(len(usage_records))
        all_versions = self.get_all_versions()
        strategy_options = ["同步"] + all_versions  # 同步 + 所有历史版本

        for row, record in enumerate(usage_records):
            # 画布
            self._usage_table.setItem(row, 0, QTableWidgetItem(record.get("canvas_name", "")))
            # 节点
            self._usage_table.setItem(row, 1, QTableWidgetItem(record.get("node_name", "")))
            # 版本策略下拉框
            combo = self._setup_strategy_combo(row, record)
            self._usage_table.setCellWidget(row, 2, combo)

    def get_strategy_for_row(self, row: int) -> str:
        """获取某行的策略值（如 "同步" 或 "V2"）"""
        widget = self._usage_table.cellWidget(row, 2)
        if isinstance(widget, ComboBox):
            return widget.currentText()
        return "同步"

    def _setup_strategy_combo(self, row, record):
        combo = ComboBox(self)
        all_versions = ["同步"] + self.get_all_versions()
        combo.addItems(all_versions)
        current = record.get("version", "同步")
        combo.setCurrentText(current if current in all_versions else "同步")

        def on_change(text):
            canvas_path = record["canvas_path"]  # 确保 record 中有 canvas_path（Path 对象）
            node_name = record["node_name"]
            self.strategy_changed.emit(str(canvas_path), node_name, text)

        combo.currentTextChanged.connect(on_change)
        return combo