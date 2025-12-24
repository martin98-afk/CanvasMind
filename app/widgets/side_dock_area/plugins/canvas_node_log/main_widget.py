# log_tool_window.py
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QElapsedTimer
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout
from qfluentwidgets import SingleDirectionScrollArea, TransparentToolButton, FluentIcon, StrongBodyLabel

from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.canvas_node_log.collapsible_card import CollapsibleLogCard
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class LogToolWindow(ToolWindow):
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

        self.clear_button = TransparentToolButton(FluentIcon.DELETE, self)
        self.clear_button.setFixedSize(28, 28)
        self.clear_button.setToolTip("清空记录")
        self.clear_button.clicked.connect(self._clear_logs)
        title_layout.addWidget(self.clear_button)

        layout.addWidget(title_container)

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
        self.log_layout.addStretch()
        self.log_layout.setAlignment(Qt.AlignBottom)
        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area, 1)

        # === 状态管理 ===
        self.round_cards = {}        # {round_key: card}
        self.node_card_map = {}      # {full_run_id: node_card}
        self.round_node_count = {}   # {round_key: total_nodes}
        self.round_finished_count = {}  # {round_key: finished_nodes}
        self.round_start_time = {}   # {round_key: QElapsedTimer}

        self.current_run_id = None

    def _parse_run_id(self, run_id: str):
        if '@' not in run_id or ':' not in run_id:
            return None, None, run_id
        parts = run_id.split('@')
        if len(parts) < 3:
            return None, None, run_id
        node_name = parts[0]
        loop_with_count = '@'.join(parts[2:])
        if loop_with_count.count(':') != 1:
            return None, None, run_id
        group_name, count = loop_with_count.rsplit(':', 1)
        round_key = f"{group_name}:{count}"
        return round_key, node_name, run_id

    def get_node_name(self, run_id):
        if "@" in run_id:
            return run_id.split("@")[0].strip()
        elif ":" in run_id:
            return run_id.split(":")[0]
        else:
            return run_id

    def start_run(self, run_id: str):
        round_key, node_name, full_id = self._parse_run_id(run_id)

        if round_key is None:
            # 普通日志
            if full_id not in self.node_card_map:
                card = CollapsibleLogCard(full_id, title_color="color: #4A90E2;", parent=self.container)
                card.doubleClicked.connect(lambda run_id: self.cardDoubleClicked.emit(self.get_node_name(run_id)))
                self.node_card_map[full_id] = card
                self.log_layout.insertWidget(self.log_layout.count() - 1, card)
                self._enforce_max_runs()
            self.node_card_map[full_id].set_current_running(True)
            self.current_run_id = full_id
            QTimer.singleShot(10, self._scroll_to_bottom)
            return

        # === 新一轮循环 ===
        if round_key not in self.round_cards:
            round_card = CollapsibleLogCard(round_key, title_color="color: #32cd32;", parent=self.container)
            round_card.doubleClicked.connect(
                lambda run_id: self.cardDoubleClicked.emit(self.get_node_name(run_id))
            )
            self.round_cards[round_key] = round_card
            self.log_layout.insertWidget(self.log_layout.count() - 1, round_card)
            self._enforce_max_runs()
            # 初始化轮次状态
            self.round_node_count[round_key] = 0
            self.round_finished_count[round_key] = 0
            self.round_start_time[round_key] = None

        round_card = self.round_cards[round_key]

        # === 添加节点 ===
        if full_id not in self.node_card_map:
            node_card = round_card.add_nested_card(node_name)
            node_card.doubleClicked.connect(
                lambda run_id: self.cardDoubleClicked.emit(self.get_node_name(run_id))
            )
            self.node_card_map[full_id] = node_card
            self.round_node_count[round_key] += 1

            # 启动轮次计时器（第一次节点 start 时）
            if self.round_start_time[round_key] is None:
                self.round_start_time[round_key] = QElapsedTimer()
                self.round_start_time[round_key].start()
                round_card._elapsed_timer = self.round_start_time[round_key]
                round_card._update_timer.start()

        self.node_card_map[full_id].set_current_running(True)
        self.current_run_id = full_id
        QTimer.singleShot(10, self._scroll_to_bottom)

    def push_log(self, run_id: str, line: str):
        round_key, node_name, full_id = self._parse_run_id(run_id)

        if round_key is None:
            if full_id not in self.node_card_map:
                card = CollapsibleLogCard(full_id, title_color="color: #4A90E2;", parent=self.container)
                card.doubleClicked.connect(lambda run_id: self.cardDoubleClicked.emit(self.get_node_name(run_id)))
                self.node_card_map[full_id] = card
                self.log_layout.insertWidget(self.log_layout.count() - 1, card)
                self._enforce_max_runs()
            self.node_card_map[full_id].append_colored_log(line)
        else:
            if full_id not in self.node_card_map:
                self.start_run(run_id)
            if full_id in self.node_card_map:
                self.node_card_map[full_id].append_colored_log(line)

        QTimer.singleShot(10, self._scroll_to_bottom)

    def _finish_round_if_needed(self, round_key):
        total = self.round_node_count.get(round_key, 0)
        finished = self.round_finished_count.get(round_key, 0)
        if total > 0 and finished >= total:
            # 所有节点完成，停止轮次计时器
            round_card = self.round_cards[round_key]
            round_card._update_timer.stop()
            # 保留最终时间
            if round_key in self.round_start_time and self.round_start_time[round_key]:
                elapsed = self.round_start_time[round_key].elapsed() / 1000.0
                round_card.timer_label.setText(f"{elapsed:.2f} s")

    def on_finished(self, run_id: str):
        round_key, _, full_id = self._parse_run_id(run_id)
        if round_key is None:
            if full_id in self.node_card_map:
                self.node_card_map[full_id].set_current_running(False)
                self.node_card_map[full_id].mark_as_success()
            return

        if full_id in self.node_card_map:
            self.node_card_map[full_id].set_current_running(False)
            self.node_card_map[full_id].mark_as_success()

            # 更新轮次完成计数
            self.round_finished_count[round_key] = self.round_finished_count.get(round_key, 0) + 1
            self._finish_round_if_needed(round_key)

    def on_error(self, run_id: str):
        round_key, _, full_id = self._parse_run_id(run_id)
        if round_key is None:
            if full_id in self.node_card_map:
                self.node_card_map[full_id].set_current_running(False)
                self.node_card_map[full_id].mark_as_error()
            return

        if full_id in self.node_card_map:
            self.node_card_map[full_id].set_current_running(False)
            self.node_card_map[full_id].mark_as_error()

            self.round_finished_count[round_key] = self.round_finished_count.get(round_key, 0) + 1
            self._finish_round_if_needed(round_key)

    def _enforce_max_runs(self):
        while len(self.round_cards) > self.MAX_RUNS:
            old_key, old_card = next(iter(self.round_cards.items()))
            del self.round_cards[old_key]
            old_card.deleteLater()
            to_remove = [k for k, card in self.node_card_map.items() if hasattr(card, 'parent_card') and card.parent_card == old_card]
            for k in to_remove:
                del self.node_card_map[k]
            self.round_node_count.pop(old_key, None)
            self.round_finished_count.pop(old_key, None)
            self.round_start_time.pop(old_key, None)

    def _scroll_to_bottom(self):
        QTimer.singleShot(10, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _expand_all(self):
        for card in self.round_cards.values():
            card.expand()
        for card in self.node_card_map.values():
            card.expand()

    def _collapse_all(self):
        for card in self.round_cards.values():
            card.collapse()
        for card in self.node_card_map.values():
            card.collapse()

    def _clear_logs(self):
        for card in list(self.round_cards.values()):
            card.deleteLater()
        for card in list(self.node_card_map.values()):
            if not card.parent() or card.parent().isWindow():
                card.deleteLater()

        self.round_cards.clear()
        self.node_card_map.clear()
        self.round_node_count.clear()
        self.round_finished_count.clear()
        self.round_start_time.clear()
        self.current_run_id = None

        while self.log_layout.count() > 1:
            item = self.log_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()