# collapsible_log_card.py （更新版）
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QTextCharFormat, QColor, QTextCursor
from qfluentwidgets import CardWidget, BodyLabel, TextEdit, ToolButton, TransparentToolButton, StrongBodyLabel

from app.utils.utils import get_icon


class CollapsibleLogCard(CardWidget):
    # 颜色规则（与你原 LogMessageBox 一致）
    LEVEL_COLORS = {
        'DEBUG': '#808080',
        'INFO': '#9cdcfe',
        'WARNING': '#ffcb6b',
        'WARN': '#ffcb6b',
        'ERROR': '#f44747',
        'Error': '#f44747',
        'CRITICAL': '#f44747',
        'SUCCESS': '#32cd32',
    }

    def __init__(self, run_id: str, parent=None):
        super().__init__(parent)
        self.run_id = run_id
        self.is_collapsed = True  # 默认折叠
        self.is_current_running = False  # 是否是当前运行卡片
        self.setStyleSheet("background-color: #2b2b2b; border: 1px solid #444; border-radius: 4px;")
        # 标题
        self.title_label = StrongBodyLabel(run_id)
        self.title_label.setStyleSheet("color: #FFA500;")

        self.toggle_button = TransparentToolButton(get_icon("放大"), self)
        self.toggle_button.setFixedSize(20, 20)
        self._update_toggle_text()

        self.toggle_button.clicked.connect(self.toggle)

        title_layout = QHBoxLayout()
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.toggle_button)

        # 日志内容（使用 QTextEdit 以便格式化）
        self.log_text = TextEdit(self)
        self.log_text.setStyleSheet("background: transparent; border: none;")
        self.log_text.setReadOnly(True)
        self.log_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setSizeAdjustPolicy(TextEdit.AdjustToContents)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.log_text.textChanged.connect(self._adjust_height)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(title_layout)
        layout.addWidget(self.log_text)

        # 默认折叠（但如果是当前运行，会在外部设为展开）
        self.log_text.setVisible(True)  # 你已经写了，很好
        self.is_collapsed = False  # 也设为 False

    def _adjust_height(self):
        """根据内容自动调整高度"""
        document_height = self.log_text.document().size().height()
        margin = self.log_text.contentsMargins()
        total_height = int(document_height + margin.top())
        self.log_text.setFixedHeight(max(total_height, 0))  # 最小高度 40

    def _update_toggle_text(self):
        if self.is_collapsed:
            self.toggle_button.setIcon(get_icon("放大"))
        else:
            self.toggle_button.setIcon(get_icon("缩小"))

    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        self.log_text.setVisible(not self.is_collapsed)
        self._update_toggle_text()

    def set_current_running(self, is_running: bool):
        """外部调用：设置是否为当前运行卡片"""
        self.is_current_running = is_running
        if is_running:
            # 自动展开 + 滚动到底
            self.is_collapsed = False
            self.log_text.setVisible(True)
            self._update_toggle_text()
        else:
            # 自动折叠
            self.is_collapsed = True
            self.log_text.setVisible(False)
            self._update_toggle_text()

    def append_colored_log(self, text: str):
        """处理多行日志文本"""
        if not text or not text.strip():
            return
        lines = text.splitlines(keepends=True)
        for line in lines:
            if not line.strip():
                self._append_single_line("\n")
            else:
                self._append_single_line(line)

    def _append_single_line(self, line: str):
        """处理单行日志"""
        if not line.endswith('\n'):
            line += '\n'

        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)

        char_format = QTextCharFormat()
        line_for_check = line.replace('&nbsp;', ' ')
        detected_level = "INFO"
        for level, color_hex in self.LEVEL_COLORS.items():
            if re.search(rf'\b{level}\b', line_for_check, re.IGNORECASE):
                detected_level = level.upper()
                char_format.setForeground(QColor(color_hex))
                break

        cursor.setCharFormat(char_format)
        cursor.insertText(line)

        if self.is_current_running:
            vsb = self.log_text.verticalScrollBar()
            vsb.setValue(vsb.maximum())