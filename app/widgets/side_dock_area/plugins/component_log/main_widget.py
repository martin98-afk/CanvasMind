# log_tool_window.py
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QLabel, QHBoxLayout
from qfluentwidgets import BodyLabel, SingleDirectionScrollArea, SubtitleLabel, TransparentToolButton, FluentIcon, \
    StrongBodyLabel

from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.component_log.collapsible_card import CollapsibleLogCard
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class LogToolWindow(ToolWindow):
    name = "模型日志"
    icon = get_icon("运行记录")
    default_position = DockPosition.BOTTOM
    MAX_RUNS = 50

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title_container = QWidget(self)
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(3, 3, 3, 3)
        self.title_label = StrongBodyLabel("节点运行日志:")
        title_layout.addWidget(self.title_label)
        # 清空按钮
        self.clear_button = TransparentToolButton(FluentIcon.DELETE, self)
        self.clear_button.setToolTip("清空记录")
        self.clear_button.clicked.connect(self.clear_logs)
        title_layout.addStretch()
        title_layout.addWidget(self.clear_button)
        layout.addWidget(title_container)
        # 日志滚动区域
        self.chat_scroll_area = SingleDirectionScrollArea(self)
        self.chat_scroll_area.setMinimumWidth(400)
        self.chat_scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setViewportMargins(0, 0, 10, 0)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(5, 5, 5, 5)
        self.chat_layout.setSpacing(5)
        self.chat_layout.addStretch()  # ← 关键：顶部 stretch
        self.chat_layout.setAlignment(Qt.AlignBottom)
        self.chat_scroll_area.setWidget(self.chat_container)

        layout.addWidget(self.chat_scroll_area, 1)
        # 状态
        self.run_cards = {}  # {run_id: card}
        self.current_run_id = None

    def start_run(self, run_id: str):
        if run_id == self.current_run_id:
            return

        # 折叠上一个
        if self.current_run_id and self.current_run_id in self.run_cards:
            self.run_cards[self.current_run_id].set_current_running(False)
            self.current_run_id = None

        # 创建新卡片
        if run_id not in self.run_cards:
            card = CollapsibleLogCard(run_id, parent=self.chat_container)
            self.run_cards[run_id] = card
            self.chat_layout.addWidget(card)  # ← 直接加到 chat_layout
            QTimer.singleShot(10, self._scroll_to_bottom)
            self._enforce_max_runs()

        self.run_cards[run_id].set_current_running(True)
        self.current_run_id = run_id

    def push_log(self, run_id: str, line: str):
        if run_id not in self.run_cards:
            # 容错：自动创建（但最好先 start_run）
            card = CollapsibleLogCard(run_id, parent=self.chat_container)
            self.run_cards[run_id] = card
            self.chat_layout.addWidget(card)
            self._enforce_max_runs()

        self.run_cards[run_id].append_colored_log(line)
        QTimer.singleShot(10, self._scroll_to_bottom)

    def _enforce_max_runs(self):
        while len(self.run_cards) > self.MAX_RUNS:
            old_id, old_card = next(iter(self.run_cards.items()))
            del self.run_cards[old_id]
            old_card.deleteLater()

    def _scroll_to_bottom(self):
        QTimer.singleShot(10, lambda: self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()
        ))

    def clear_logs(self):
        for run_id, card in self.run_cards.items():
            card.deleteLater()
        self.run_cards.clear()
        self.chat_layout.addStretch()
        self.current_run_id = None