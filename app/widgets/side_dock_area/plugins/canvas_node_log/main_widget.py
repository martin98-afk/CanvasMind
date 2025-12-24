# log_tool_window.py
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout
from qfluentwidgets import SingleDirectionScrollArea, TransparentToolButton, FluentIcon, \
    StrongBodyLabel

from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.canvas_node_log.collapsible_card import CollapsibleLogCard
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class LogToolWindow(ToolWindow):
    """画布节点运行日志工具窗口 (包含画布系统日志)"""
    name = "模型日志"
    icon = get_icon("运行记录")
    default_position = DockPosition.BOTTOM
    MAX_RUNS = 50
    cardDoubleClicked = pyqtSignal(str)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title_container = QWidget(self)
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(3, 3, 3, 3)
        title_layout.setSpacing(3)
        self.title_label = StrongBodyLabel("运行日志:")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        # 折叠展开按钮
        self.expand_button = TransparentToolButton(get_icon("expand_all"), self)
        self.expand_button.setFixedSize(28, 28)
        self.expand_button.setToolTip("展开所有日志")
        self.expand_button.clicked.connect(self._expand_all)
        title_layout.addWidget(self.expand_button)
        self.collapse_button = TransparentToolButton(get_icon("collapse_all"), self)
        self.collapse_button.setFixedSize(28, 28)
        self.collapse_button.setToolTip("折叠所有日志")
        self.collapse_button.clicked.connect(self._collapse_all)
        title_layout.addWidget(self.collapse_button)
        # 清空按钮
        self.clear_button = TransparentToolButton(FluentIcon.DELETE, self)
        self.clear_button.setFixedSize(28, 28)
        self.clear_button.setToolTip("清空记录")
        self.clear_button.clicked.connect(self._clear_logs)

        title_layout.addWidget(self.clear_button)
        layout.addWidget(title_container)
        # 日志滚动区域
        self.scroll_area = SingleDirectionScrollArea(self)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setMinimumWidth(400)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setViewportMargins(0, 0, 10, 0)

        self.container = QWidget()
        self.log_layout = QVBoxLayout(self.container)
        self.log_layout.setContentsMargins(5, 5, 5, 5)
        self.log_layout.setSpacing(5)
        self.log_layout.addStretch()  # ← 关键：顶部 stretch
        self.log_layout.setAlignment(Qt.AlignBottom)
        self.scroll_area.setWidget(self.container)

        layout.addWidget(self.scroll_area, 1)
        # 状态
        self.run_cards = {}  # {run_id: card}
        self.current_run_id = None

    def start_run(self, run_id: str):
        if run_id == self.current_run_id:
            return

        # 折叠上一个
        if self.current_run_id and self.current_run_id in self.run_cards:
            self.current_run_id = None

        # 创建新卡片
        if run_id not in self.run_cards:
            card = CollapsibleLogCard(run_id, parent=self.container)
            card.doubleClicked.connect(lambda id=run_id: self.cardDoubleClicked.emit(id.split("@")[0].strip()))
            self.run_cards[run_id] = card
            self.log_layout.addWidget(card)  # ← 直接加到 layout
            QTimer.singleShot(10, self._scroll_to_bottom)
            self._enforce_max_runs()

        self.run_cards[run_id].set_current_running(True)
        self.current_run_id = run_id

    def push_log(self, run_id: str, line: str):
        if run_id not in self.run_cards:
            # 容错：自动创建（但最好先 start_run）系统日志，标题淡蓝色
            card = CollapsibleLogCard(run_id, title_color="color: #4A90E2;", parent=self.container)
            card.doubleClicked.connect(lambda id=run_id: self.cardDoubleClicked.emit(id.split("@")[0].strip()))
            self.run_cards[run_id] = card
            self.log_layout.addWidget(card)
            self._enforce_max_runs()

        self.run_cards[run_id].append_colored_log(line)
        QTimer.singleShot(10, self._scroll_to_bottom)

    def on_finished(self, run_id: str):
        if run_id in self.run_cards:
            self.run_cards[run_id].set_current_running(False)
            self.run_cards[run_id].mark_as_success()

    def on_error(self, run_id: str):
        if run_id in self.run_cards:
            self.run_cards[run_id].set_current_running(False)
            self.run_cards[run_id].mark_as_error()

    def _enforce_max_runs(self):
        while len(self.run_cards) > self.MAX_RUNS:
            old_id, old_card = next(iter(self.run_cards.items()))
            del self.run_cards[old_id]
            old_card.deleteLater()

    def _scroll_to_bottom(self):
        QTimer.singleShot(10, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _expand_all(self):
        for run_id, card in self.run_cards.items():
            card.expand()

    def _collapse_all(self):
        for run_id, card in self.run_cards.items():
            card.collapse()

    def _clear_logs(self):
        for run_id, card in self.run_cards.items():
            card.deleteLater()
        while self.log_layout.count():
            if self.log_layout.takeAt(0) is None:
                break
            self.log_layout.takeAt(0).widget().deleteLater()
        self.run_cards.clear()
        self.log_layout.addStretch()
        self.current_run_id = None