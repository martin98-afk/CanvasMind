# log_tool_window.py
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout, QScrollArea
from qfluentwidgets import (
    SingleDirectionScrollArea,
    TransparentToolButton,
    FluentIcon,
    StrongBodyLabel,
)

from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.canvas_node_log.collapsible_card import (
    CollapsibleLogCard,
)
from app.widgets.side_dock_area.tool_window import (
    ToolWindow,
    DockPosition,
    DockCategory,
)


class LogToolWindow(ToolWindow):
    """画布节点运行日志工具窗口 (包含画布系统日志)"""

    name = "模型日志"
    icon = get_icon("运行记录")
    default_position = DockPosition.BOTTOM
    CATEGORIES = [DockCategory.CANVAS]
    display_order = 90
    MAX_RUNS = 50
    cardDoubleClicked = pyqtSignal(str)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 日志滚动区域
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setMinimumWidth(400)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;")
        self.scroll_area.setStyleSheet("""
                QScrollArea { background-color: transparent; border: none; }
                QScrollBar:vertical { background: transparent; width: 6px; margin-right: 2px; }
                QScrollBar::handle:vertical { background: rgba(120, 120, 120, 150); border-radius: 4px; }
                QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
                """)
        self.scroll_area.setViewportMargins(0, 0, 10, 0)

        self.container = QWidget()
        self.log_layout = QVBoxLayout(self.container)
        self.log_layout.setContentsMargins(5, 5, 5, 5)
        self.log_layout.setSpacing(5)
        self.log_layout.addStretch(1)  # ← 关键：顶部 stretch
        self.log_layout.setAlignment(Qt.AlignBottom)
        self.scroll_area.setWidget(self.container)

        layout.addWidget(self.scroll_area, 1)
        # 状态
        self.run_cards = {}  # {run_id: card}
        self.current_run_id = None

    def _setup_title_bar(self):
        title_bar = self.get_title_bar()
        title_bar.set_title("模型日志")

        self.expand_button = TransparentToolButton(get_icon("expand_all"), self)
        self.expand_button.setToolTip(self.tr("展开所有日志"))
        self.expand_button.clicked.connect(self._expand_all)
        title_bar.add_button(self.expand_button)

        self.collapse_button = TransparentToolButton(get_icon("collapse_all"), self)
        self.collapse_button.setToolTip(self.tr("折叠所有日志"))
        self.collapse_button.clicked.connect(self._collapse_all)
        title_bar.add_button(self.collapse_button)

        self.clear_button = TransparentToolButton(FluentIcon.DELETE, self)
        self.clear_button.setToolTip(self.tr("清空记录"))
        self.clear_button.clicked.connect(self._clear_logs)
        title_bar.add_button(self.clear_button)

    def showEvent(self, event):
        self._collapse_all()
        QTimer.singleShot(10, self._expand_all)
        super().showEvent(event)

    def start_run(self, run_id: str):
        if run_id == self.current_run_id:
            return

        if self.current_run_id and self.current_run_id in self.run_cards:
            self.current_run_id = None

        # 创建新卡片
        if run_id not in self.run_cards:
            card = CollapsibleLogCard(run_id, parent=self.container)
            card.doubleClicked.connect(
                lambda id=run_id: self.cardDoubleClicked.emit(id.split("@")[0].strip())
            )
            self.run_cards[run_id] = card
            self.log_layout.addWidget(card)  # ← 直接加到 layout
            QTimer.singleShot(10, self._scroll_to_bottom)
            self._enforce_max_runs()

        self.run_cards[run_id].set_current_running(True)
        self.current_run_id = run_id

    def push_log(self, run_id: str, line: str):
        if run_id not in self.run_cards:
            # 容错：自动创建（但最好先 start_run）系统日志，标题淡蓝色
            card = CollapsibleLogCard(
                run_id, title_color="color: #4A90E2;", parent=self.container
            )
            card.doubleClicked.connect(
                lambda id=run_id: self.cardDoubleClicked.emit(id.split("@")[0].strip())
            )
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
        QTimer.singleShot(
            10,
            lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ),
        )

    def _expand_all(self):
        for run_id, card in self.run_cards.items():
            card.expand()
        self._scroll_to_bottom()

    def _collapse_all(self):
        for run_id, card in self.run_cards.items():
            card.collapse()

    def _clear_logs(self):
        # 先清除 run_cards 字典（避免后续访问已删除对象）
        self.run_cards.clear()
        self.current_run_id = None

        # 安全清空 layout 中的所有 widget
        while self.log_layout.count():
            item = self.log_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        # 重新添加 stretch（保持底部对齐）
        self.log_layout.addStretch(1)
