# collapsible_log_card.py （优化版）
import re

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QElapsedTimer
from PyQt5.QtGui import QTextCharFormat, QColor, QTextCursor, QTextBlockFormat, QTextOption
from PyQt5.QtWidgets import *
from qfluentwidgets import CardWidget, BodyLabel, TextEdit, TransparentToolButton, StrongBodyLabel

from app.utils.utils import get_icon


class CollapsibleLogCard(CardWidget):
    doubleClicked = pyqtSignal(str)  # 传出 run_id

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

    STATUS_ICONS = {
        "running": get_icon("运行中"),
        "success": get_icon("成功"),
        "error": get_icon("失败"),
        "default": get_icon("系统通知")
    }

    ARROW_ICONS = {
        "collapsed": get_icon("折叠"),   # ▶
        "expanded": get_icon("展开")    # ▼
    }

    def __init__(self, run_id: str, title_color="color: #FFA500;", parent=None):
        super().__init__(parent)
        self.run_id = run_id
        self.is_collapsed = False
        self.is_current_running = False
        self.status = "default"

        self.setStyleSheet("background-color: #2b2b2b; border: 1px solid #444; border-radius: 6px;")

        # === 计时器 ===
        self._elapsed_timer = QElapsedTimer()
        self.timer_label = BodyLabel("0.00 s")
        self.timer_label.setStyleSheet("""
            color: #FFA500; font-size: 13px;
            background: transparent; border: none;
            margin-left: 4px; margin-right: 4px;
        """)
        self.timer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.timer_label.hide()

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_timer_display)
        self._update_timer.setInterval(100)

        # === 标题布局 ===
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(6, 4, 6, 4)
        title_layout.setSpacing(6)

        # 折叠按钮
        self.toggle_button = TransparentToolButton(self.ARROW_ICONS["expanded"], self)
        self.toggle_button.setFixedSize(16, 16)
        self.toggle_button.setStyleSheet("background: transparent; border: none;")
        self.toggle_button.clicked.connect(self.toggle)
        title_layout.addWidget(self.toggle_button)

        # 主标题（节点名）
        self.title_label = StrongBodyLabel(run_id.split("@")[0])
        self.title_label.setWordWrap(False)
        self.title_label.setStyleSheet(title_color + " background: transparent; border: none;")
        title_layout.addWidget(self.title_label)

        # 循环信息（如有）
        parts = run_id.split("@")
        if len(parts) == 3:
            separator = BodyLabel("│")
            separator.setStyleSheet("color: #555; background: transparent;")
            title_layout.addWidget(separator)

            loop_label = BodyLabel(parts[1])
            loop_label.setWordWrap(True)
            loop_label.setStyleSheet("color: #808080; background: transparent; border: none;")
            title_layout.addWidget(loop_label, 1)

        title_layout.addStretch()  # 推动右侧元素靠右
        # 时间戳
        time_label = BodyLabel(parts[-1])
        time_label.setStyleSheet("color: #808080; background: transparent; border: none;")
        title_layout.addWidget(time_label)

        # 计时器 & 状态
        title_layout.addWidget(self.timer_label)
        self.status_button = TransparentToolButton(self.STATUS_ICONS["default"], self)
        self.status_button.setFixedSize(20, 20)
        title_layout.addWidget(self.status_button)

        # === 日志文本区域 ===
        self.log_text = TextEdit(self)
        font = self.log_text.font()
        font.setFamily("Consolas")
        font.setPointSize(10)
        self.log_text.setFont(font)
        self.log_text.setStyleSheet("background: transparent; border: none; color: white;")
        self.log_text.setReadOnly(True)
        self.log_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # 初始高度
        self.log_text.setFixedHeight(20)

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addLayout(title_layout)
        layout.addWidget(self.log_text)

        self.expand()  # 默认展开

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.run_id)
        super().mouseDoubleClickEvent(event)

    def _adjust_height(self):
        doc = self.log_text.document()
        margin = self.log_text.contentsMargins()
        height = doc.size().height() + margin.top() + margin.bottom()
        self.log_text.setFixedHeight(max(int(height), 20))

    def expand(self):
        self.is_collapsed = False
        self.log_text.setVisible(True)
        self.toggle_button.setIcon(self.ARROW_ICONS["expanded"])

    def collapse(self):
        self.is_collapsed = True
        self.log_text.setVisible(False)
        self.toggle_button.setIcon(self.ARROW_ICONS["collapsed"])

    def toggle(self):
        if self.is_collapsed:
            self.expand()
        else:
            self.collapse()

    def set_current_running(self, is_running: bool):
        if self.is_current_running == is_running:
            return
        self.is_current_running = is_running

        if is_running:
            self.set_status("running")
            self._elapsed_timer.restart()
            self._update_timer.start()
            self.timer_label.show()
            self.expand()
        else:
            self._update_timer.stop()
        self._update_style()

    def set_status(self, status: str):
        if self.status == status:
            return
        self.status = status
        icon = self.STATUS_ICONS.get(status, self.STATUS_ICONS["default"])
        self.status_button.setIcon(icon)
        self._update_style()

    def mark_as_error(self):
        self.set_status("error")
        self.expand()

    def mark_as_success(self):
        self.set_status("success")
        self.expand()

    def _update_style(self):
        if self.is_current_running:
            border = "2px solid #FFA500"
        elif self.status == "error":
            border = "2px solid #f44747"
        else:
            border = "1px solid #444"

        self.setStyleSheet(f"""
            CollapsibleLogCard {{
                background-color: #2b2b2b;
                border: {border};
                border-radius: 6px;
            }}
        """)

    def _update_timer_display(self):
        elapsed_sec = self._elapsed_timer.elapsed() / 1000.0
        self.timer_label.setText(f"{elapsed_sec:.2f} s")

    def append_colored_log(self, text: str):
        if not text:
            return

        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)

        # 使用 splitlines(keepends=False) 是安全的，但我们要保留空行语义
        lines = text.splitlines()

        # 如果原文以 \n 结尾，splitlines() 会丢掉最后一个空行，可选保留：
        if text.endswith('\n'):
            lines.append("")

        block_format = QTextBlockFormat()
        block_format.setLineHeight(110, QTextBlockFormat.ProportionalHeight)

        for i, line in enumerate(lines):
            # 检测日志级别
            color_hex = "#ffffff"
            clean_line = line.rstrip('\r\n\t ')  # 仅用于检测，不修改原 line
            for level, col in self.LEVEL_COLORS.items():
                if re.search(rf'\b{level}\b', clean_line, re.IGNORECASE):
                    color_hex = col
                    break

            char_format = QTextCharFormat()
            char_format.setForeground(QColor(color_hex))
            char_format.setFontFamily("Consolas")
            char_format.setFontPointSize(10)

            # 关键：即使 line 是空字符串，也要插入一个 block
            cursor.setBlockFormat(block_format)
            cursor.insertText(line, char_format)  # 保留原始 line（包括末尾空格）
            if i < len(lines) - 1:
                cursor.insertBlock()  # 每行后换 block

        # 滚动到底
        self.log_text.setTextCursor(cursor)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        self._adjust_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()