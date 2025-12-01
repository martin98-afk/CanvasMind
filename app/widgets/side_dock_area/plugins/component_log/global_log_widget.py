# global_log_widget.py （更新版）
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from collections import OrderedDict

from qfluentwidgets import SingleDirectionScrollArea, BodyLabel

from app.widgets.side_dock_area.plugins.component_log.collapsible_card import CollapsibleLogCard


class GlobalLogWidget(QWidget):
    MAX_RUNS = 50

    def __init__(self, parent=None):
        super().__init__(parent)
        self.run_cards = OrderedDict()  # {run_id: CollapsibleLogCard}
        self.current_run_id: str = None
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(BodyLabel("运行日志测试"))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.scroll_area = SingleDirectionScrollArea(self)
        self.scroll_area.setMinimumWidth(400)
        # 透明背景
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setViewportMargins(0, 0, 0, 0)

        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        # self.layout.setAlignment(Qt.AlignBottom)  # 关键：防止垂直拉伸
        self.scroll_area.setWidget(self.container)

        layout.addWidget(self.scroll_area, 1)

    def start_run(self, run_id: str):
        """节点开始运行：创建卡片并设为当前运行"""
        print("插入执行日志")
        self.layout.addWidget(BodyLabel(f"运行日志：{run_id}"))
        if run_id == self.current_run_id:
            return

        # 结束上一个运行
        if self.current_run_id and self.current_run_id in self.run_cards:
            self.run_cards[self.current_run_id].set_current_running(False)

        # 创建或获取新卡片
        if run_id not in self.run_cards:
            card = CollapsibleLogCard(run_id, parent=self)
            self.run_cards[run_id] = card
            # 添加说明label
            print("插入卡片")
            self.layout.addWidget(BodyLabel(f"运行日志：{run_id}"))
            self.layout.addWidget(card)
            self._enforce_max_runs()

        # 设置为当前运行
        self.run_cards[run_id].set_current_running(True)
        self.current_run_id = run_id

    def push_log(self, run_id: str, line: str):
        """推送日志（即使不是当前运行也能追加，但不滚动）"""
        if run_id not in self.run_cards:
            # 如果还没 start_run，先创建（容错）
            card = CollapsibleLogCard(run_id, parent=self)
            self.run_cards[run_id] = card
            self.layout.addWidget(card)
            self._enforce_max_runs()

        self.run_cards[run_id].append_colored_log(line)

    def finish_run(self, run_id: str):
        """节点运行结束：自动折叠（如果是当前运行）"""
        if run_id == self.current_run_id:
            if run_id in self.run_cards:
                self.run_cards[run_id].set_current_running(False)
            self.current_run_id = None

    def _enforce_max_runs(self):
        while len(self.run_cards) > self.MAX_RUNS:
            old_id, old_card = self.run_cards.popitem(last=False)
            old_card.deleteLater()

