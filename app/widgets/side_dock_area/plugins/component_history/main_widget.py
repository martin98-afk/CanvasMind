# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QVBoxLayout, QTableWidget, QHeaderView, QTableWidgetItem, QWidget
from qfluentwidgets import (
    FluentIcon, BodyLabel, TableWidget, ComboBox
)

from app.widgets.basic_widget.splitter import ModernSplitter
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
        splitter = ModernSplitter(Qt.Vertical)
        # === 编辑历史 ===
        history_container = QWidget(self)
        history_layout = QVBoxLayout(history_container)
        history_layout.setContentsMargins(0, 0, 0, 0)

        history_label = BodyLabel("组件版本记录:")
        # 替换原来的 history_table 设置
        self._history_table = TableWidget(self)
        self._history_table.setColumnCount(3)
        self._history_table.setHorizontalHeaderLabels(["版本", "保存时间", "说明"])
        self._history_table.verticalHeader().hide()
        # ✅ 允许对“说明”列编辑，其他列只读
        self._history_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self._history_table.setSelectionBehavior(QTableWidget.SelectItems)
        header = self._history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # 说明列自适应
        history_layout.addWidget(history_label)
        history_layout.addWidget(self._history_table)

        # === 组件使用情况 ===
        usage_container = QWidget(self)
        usage_layout = QVBoxLayout(usage_container)
        usage_layout.setContentsMargins(0, 0, 0, 0)
        usage_label = BodyLabel("组件使用情况:")
        self._usage_table = TableWidget(self)
        self._usage_table.setColumnCount(3)  # 画布、节点、版本策略
        self._usage_table.setHorizontalHeaderLabels(["画布", "节点名称", "版本策略"])
        self._usage_table.verticalHeader().hide()
        self._usage_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._usage_table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self._usage_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        usage_layout.addWidget(usage_label)
        usage_layout.addWidget(self._usage_table)

        splitter.addWidget(history_container)
        splitter.addWidget(usage_container)
        splitter.setSizes([300, 400])  # 变量浏览器较小，控制台较大
        layout.addWidget(splitter)

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
        self._current_usage_records = usage_records  # ✅ 保存引用供 combo 回调更新
        self._usage_table.setRowCount(len(usage_records))

        for row, record in enumerate(usage_records):
            self._usage_table.setItem(row, 0, QTableWidgetItem(record.get("canvas_name", "")))
            self._usage_table.setItem(row, 1, QTableWidgetItem(record.get("node_name", "")))
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
        combo.setMinimumWidth(80)
        combo.setFixedHeight(28)
        combo.setStyleSheet("color: white; background: transparent; border: none;")
        all_versions = ["同步"] + self.get_all_versions()
        combo.addItems(all_versions)
        current = record.get("version", "同步")
        combo.setCurrentText(current if current in all_versions else "同步")

        # ✅ 用 row 作为 key，不依赖闭包引用 record
        def on_change(text):
            # 动态从 usage_records 中更新
            usage_records = getattr(self, '_current_usage_records', [])
            if 0 <= row < len(usage_records):
                usage_records[row]["version"] = text  # ✅ 实时更新！

            canvas_path = record["canvas_path"]
            node_name = record["node_name"]
            self.strategy_changed.emit(str(canvas_path), node_name, text)

        combo.currentTextChanged.connect(on_change)
        return combo