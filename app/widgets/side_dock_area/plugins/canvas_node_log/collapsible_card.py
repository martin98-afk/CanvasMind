# collapsible_log_card.py （优化版）
import re

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QElapsedTimer, QSize
from PyQt5.QtGui import QTextCharFormat, QColor, QTextCursor, QTextBlockFormat, QTextOption
from PyQt5.QtWidgets import *
from qfluentwidgets import CardWidget, BodyLabel, TextEdit, TransparentToolButton, StrongBodyLabel

from app.utils.utils import get_icon
from app.widgets.basic_widget.roating_status_button import RotatingStatusButton


class CollapsibleLogCard(CardWidget):
    doubleClicked = pyqtSignal(str)

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
        "collapsed": get_icon("折叠"),
        "expanded": get_icon("展开")
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

        self.toggle_button = TransparentToolButton(self.ARROW_ICONS["expanded"], self)
        self.toggle_button.setFixedSize(16, 16)
        self.toggle_button.clicked.connect(self.toggle)
        title_layout.addWidget(self.toggle_button)

        self.title_label = StrongBodyLabel(run_id.split("@")[0])
        self.title_label.setStyleSheet(title_color + " background: transparent; border: none;")
        title_layout.addWidget(self.title_label)

        parts = run_id.split("@")
        if len(parts) == 3:
            separator = BodyLabel("│")
            separator.setStyleSheet("color: #555; background: transparent;")
            title_layout.addWidget(separator)
            loop_label = BodyLabel(parts[1])
            loop_label.setWordWrap(True)
            loop_label.setStyleSheet("color: #808080; background: transparent; border: none;")
            title_layout.addWidget(loop_label, 1)

        title_layout.addStretch()

        time_label = BodyLabel(parts[-1])
        time_label.setStyleSheet("color: #808080; background: transparent; border: none;")
        title_layout.addWidget(time_label)

        title_layout.addWidget(self.timer_label)

        # 使用自定义的旋转按钮
        self.status_button = RotatingStatusButton(
            self.STATUS_ICONS["default"],
            animation_duration=2000,
            parent=self
        )
        self.status_button.setFixedSize(20, 20)
        self.status_button.setIconSize(QSize(16, 16))
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
        self.log_text.setFixedHeight(20)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addLayout(title_layout)
        layout.addWidget(self.log_text)

        self.expand()

    # --- 核心逻辑修改：启动动画 ---
    def set_current_running(self, is_running: bool):
        if self.is_current_running == is_running:
            return
        self.is_current_running = is_running

        if is_running:
            self.set_status("running")
            self.status_button.start_rotation()  # 开启旋转
            self._elapsed_timer.restart()
            self._update_timer.start()
            self.timer_label.show()
            self.expand()
        else:
            self._update_timer.stop()
            self.status_button.stop_rotation()  # 停止旋转
        self._update_style()

    def set_status(self, status: str):
        self.status = status
        icon = self.STATUS_ICONS.get(status, self.STATUS_ICONS["default"])
        self.status_button.setIcon(icon)

        # 如果从运行切换到其他状态，确保动画停止
        if status != "running":
            self.status_button.stop_rotation()
        self._update_style()

    # 其余代码保持原样...
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
        if not text: return
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        lines = text.splitlines()
        if text.endswith('\n'): lines.append("")
        for i, line in enumerate(lines):
            color_hex = "#ffffff"
            clean_line = line.rstrip('\r\n\t ')
            for level, col in self.LEVEL_COLORS.items():
                if re.search(rf'\b{level}\b', clean_line, re.IGNORECASE):
                    color_hex = col
                    break
            char_format = QTextCharFormat()
            char_format.setForeground(QColor(color_hex))
            char_format.setFontFamily("Consolas")
            char_format.setFontPointSize(10)
            cursor.insertText(line, char_format)
            if i < len(lines) - 1: cursor.insertBlock()
        self.log_text.setTextCursor(cursor)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self._adjust_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()