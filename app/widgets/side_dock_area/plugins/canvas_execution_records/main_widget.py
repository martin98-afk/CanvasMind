# -*- coding: utf-8 -*-

from PyQt5.QtCore import QTimer, pyqtSlot
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout
from qfluentwidgets import (
    SingleDirectionScrollArea,
    TransparentToolButton,
    FluentIcon,
    StrongBodyLabel,
)

from app.widgets.side_dock_area.plugins.canvas_execution_records.execution_manager import (
    ExecutionManager,
)
from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.canvas_execution_records.execution_result_card import (
    ExecutionResultCard,
)

# 假设这些是你项目中的工具类引用，如果没有可以替换为标准 PyQt 组件
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class ExecutionHistoryWindow(ToolWindow):
    """
    画布执行历史记录窗口
    """

    name = "任务记录"
    icon = get_icon("任务队列")  # 使用合适的图标
    default_position = DockPosition.BOTTOM
    cards = {}  # {execution_id: ExecutionResultCard}

    def setup_ui(self):
        # 标题栏
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域
        self.scroll_area = SingleDirectionScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")

        self.container = QWidget()
        self.card_layout = QVBoxLayout(self.container)
        self.card_layout.setContentsMargins(10, 0, 10, 10)
        self.card_layout.setSpacing(8)
        self.card_layout.addStretch(1)  # 挤压到底部

        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area)

        # 1. 连接后端信号 (关键优化)
        self.manager = ExecutionManager()
        self.manager.signal.execution_updated.connect(self._on_data_updated)

        # 2. 纯 UI 计时器：只更新 "x秒..." 的文本，不请求后端数据
        self.ui_ticker = QTimer(self)
        self.ui_ticker.setInterval(1000)
        self.ui_ticker.timeout.connect(self._update_running_timers)
        self.ui_ticker.start()

    def _setup_title_bar(self):
        title_bar = self.get_title_bar()
        title_bar.set_title("任务记录")

        self.clear_btn = TransparentToolButton(FluentIcon.DELETE, self)
        self.clear_btn.setToolTip(self.tr("清空记录"))
        self.clear_btn.clicked.connect(self._clear_all)
        title_bar.add_button(self.clear_btn)

    @property
    def execution_manager(self):
        return self.manager

    def create_record(self, **kwargs):
        self.manager.create_record(**kwargs)

    def update_record(self, exec_id, status, **kwargs):
        self.manager.update_record(exec_id, status, **kwargs)

    def showEvent(self, event):
        # 首次显示时同步一次数据
        self._sync_data()
        super().showEvent(event)

    @pyqtSlot()
    def _on_data_updated(self):
        """当后端发来信号时调用"""
        self._sync_data()

    def _sync_data(self):
        """全量同步逻辑 (只在有变化时触发)"""
        all_records = self.manager.get_all_records()
        seen_ids = set()

        for record in all_records:
            eid = record.execution_id
            seen_ids.add(eid)

            if eid in self.cards:
                # 更新已有卡片 (状态、输出等)
                self.cards[eid].update_data(record)
            else:
                # 创建新卡片
                self._add_card(record)

        # 移除已删除的卡片
        current_ui_ids = list(self.cards.keys())
        for eid in current_ui_ids:
            if eid not in seen_ids:
                self._remove_card(eid)

    def _update_running_timers(self):
        """UI Ticker: 仅刷新正在运行卡片的时间文本，不涉及任何数据同步"""
        if not self.isVisible():
            return

        for card in self.cards.values():
            if card.record.status == "running":
                card.refresh_duration()

    def _add_card(self, record):
        card = ExecutionResultCard(record, self.container)
        self.cards[record.execution_id] = card
        # 插入到列表底部 (stretch 之前)
        self.card_layout.insertWidget(self.card_layout.count() - 1, card)
        # 自动滚动到底部
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _remove_card(self, eid):
        if eid in self.cards:
            card = self.cards.pop(eid)
            card.deleteLater()

    def _clear_all(self):
        self.manager.clear_records()
        self._sync_data()

    def _scroll_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
