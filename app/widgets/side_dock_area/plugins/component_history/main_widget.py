# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QVBoxLayout, QTableWidget, QHeaderView
from qfluentwidgets import FluentIcon, CardWidget, BodyLabel, TableWidget

from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class ComponentHistoryToolWindow(ToolWindow):
    name = "组件历史管理"
    icon = FluentIcon.HISTORY
    singleton = True
    default_position = DockPosition.BOTTOM  # 放在底部
    _history_table = None

    def setup_ui(self):
        history_card_layout = QVBoxLayout(self)
        history_card_layout.setContentsMargins(10, 10, 10, 10)  # 设置内边距
        history_label = BodyLabel("编辑历史:")
        self._history_table = TableWidget(self)
        self._history_table.setColumnCount(2)  # 只显示版本和时间
        self._history_table.setHorizontalHeaderLabels(["版本", "保存时间"])
        self._history_table.verticalHeader().hide()
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.setSelectionBehavior(QTableWidget.SelectItems)
        self._history_table.setSelectionMode(QTableWidget.ContiguousSelection)
        # 设置版本列宽度自适应内容，时间列拉伸填充
        self._history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 版本列
        self._history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)  # 时间列
        history_card_layout.addWidget(history_label)
        history_card_layout.addWidget(self._history_table)

    @property
    def history_table(self):
        return self._history_table