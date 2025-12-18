# collapsible_log_card.py （更新版）
import re

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QElapsedTimer
from PyQt5.QtGui import QTextCharFormat, QColor, QTextCursor, QTextBlockFormat, QTextOption
from PyQt5.QtWidgets import *
from qfluentwidgets import CardWidget, BodyLabel, TextEdit, TransparentToolButton, StrongBodyLabel

from app.utils.utils import get_icon


class CollapsibleLogCard(CardWidget):
    # 颜色规则（与你原 LogMessageBox 一致）
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

    def __init__(self, run_id: str, title_color="color: #FFA500;", parent=None):
        super().__init__(parent)
        self.run_id = run_id
        self.is_collapsed = False
        self.is_current_running = False

        self.setStyleSheet("background-color: #2b2b2b; border: 1px solid #444; border-radius: 4px;")

        # === 新增：计时器相关 ===
        self._elapsed_timer = QElapsedTimer()  # 用于高精度计时
        self.timer_label = BodyLabel("0.00 s")
        self.timer_label.setStyleSheet("color: #FFA500; font-size: 13px; background: transparent; border: none;")
        self.timer_label.setFixedWidth(60)  # 宽一点容纳 "99.99 秒"
        self.timer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_timer_display)
        self._update_timer.setInterval(100)  # 每100ms更新一次，足够流畅且性能好

        # 标题
        self.title_label = StrongBodyLabel(run_id)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(title_color+"background:transparent;border:none;")

        self.toggle_button = TransparentToolButton(get_icon("expand_all"), self)
        self.toggle_button.setFixedSize(20, 20)
        self._update_toggle_text()
        self.toggle_button.clicked.connect(self.toggle)

        # === 修改标题布局：加入计时器 ===
        title_layout = QHBoxLayout()
        title_layout.addWidget(self.title_label, 1)
        title_layout.addStretch()
        title_layout.addWidget(self.timer_label)  # <-- 新增：计时器在 toggle 左边
        title_layout.addWidget(self.toggle_button)

        # 日志内容（保持不变）
        self.log_text = TextEdit(self)
        font = self.log_text.font()
        font.setFamily("Consolas")  # 或 "Courier New", "Fira Code", "JetBrains Mono"
        font.setPointSize(10)
        self.log_text.setFont(font)
        self.log_text.setStyleSheet("background: transparent; border: none; color: white;")
        self.log_text.setReadOnly(True)
        self.log_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setSizeAdjustPolicy(TextEdit.AdjustToContents)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.log_text.textChanged.connect(self._adjust_height)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(title_layout)
        layout.addWidget(self.log_text)

        # 默认展开（符合你注释逻辑）
        self.log_text.setVisible(True)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.run_id)
        super().mouseDoubleClickEvent(event)

    def _adjust_height(self):
        """根据内容自动调整高度"""
        doc = self.log_text.document()
        layout = doc.documentLayout()
        height = layout.documentSize().height()
        total_height = int(height)
        QTimer.singleShot(10, lambda: self.log_text.setFixedHeight(max(total_height, 0)))  # 最小高度 40

    def expand(self):
        """外部调用：展开卡片"""
        self.is_collapsed = False
        self.log_text.setVisible(True)
        self.toggle_button.setIcon(get_icon("collapse_all"))

    def collapse(self):
        """外部调用：折叠卡片"""
        self.is_collapsed = True
        self.log_text.setVisible(False)
        self.toggle_button.setIcon(get_icon("expand_all"))

    def _update_toggle_text(self):
        if self.is_collapsed:
            self.toggle_button.setIcon(get_icon("expand_all"))
        else:
            self.toggle_button.setIcon(get_icon("collapse_all"))

    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        self.log_text.setVisible(not self.is_collapsed)
        self._update_toggle_text()

    def set_current_running(self, is_running: bool):
        if self.is_current_running == is_running:
            return

        self.is_current_running = is_running

        if is_running:
            self.setStyleSheet("background-color: #2b2b2b; border: 2px solid #FFA500; border-radius: 4px;")
            self.is_collapsed = False
            self.log_text.setVisible(True)
            self._update_toggle_text()
            # 启动高精度计时
            self._elapsed_timer.start()
            self._update_timer.start()
            self.timer_label.show()
        else:
            self.setStyleSheet("background-color: #2b2b2b; border: 1px solid #444; border-radius: 4px;")
            self.is_collapsed = True
            self.log_text.setVisible(False)
            self._update_toggle_text()
            self._update_timer.stop()

    def _update_timer_display(self):
        elapsed_ms = self._elapsed_timer.elapsed()  # 毫秒
        elapsed_sec = elapsed_ms / 1000.0
        self.timer_label.setText(f"{elapsed_sec:.2f} s")

    def mark_as_error(self):
        self._update_timer.stop()  # 停止刷新
        self.setStyleSheet("background-color: #2b2b2b; border: 2px solid #f44747; border-radius: 4px;")
        self.log_text.setVisible(True)
        self.is_collapsed = False
        self._update_toggle_text()

    def append_colored_log(self, text: str):
        if not text or not text.strip():
            return

        # 先获取当前 HTML 内容（避免覆盖）
        current_html = self.log_text.toHtml()
        if not current_html.startswith('<!DOCTYPE HTML'):
            current_html = ""

        lines = text.splitlines(keepends=True)
        new_html_lines = []

        for line in lines:
            # 检测日志级别
            color_hex = "#ffffff"
            line_for_check = line.replace('&nbsp;', ' ')
            for level, col in self.LEVEL_COLORS.items():
                if re.search(rf'\b{level}\b', line_for_check, re.IGNORECASE):
                    color_hex = col
                    break

            # 转义 HTML 特殊字符（防止 XSS 或解析错误）
            escaped_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # 用 <pre> + color
            html_line = f'<pre style="color:{color_hex}; margin:0; padding:0;">{escaped_line}</pre>'
            new_html_lines.append(html_line)

        # 拼接 HTML
        full_html = current_html + "\n".join(new_html_lines)
        # 禁用自动换行（<pre> 默认不换行，但你可以控制）
        self.log_text.setHtml(full_html)

        # 保持滚动到底（如果正在运行）
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()