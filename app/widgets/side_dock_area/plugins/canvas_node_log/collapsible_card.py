# collapsible_log_card.py
import re

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QElapsedTimer
from PyQt5.QtWidgets import *
from qfluentwidgets import CardWidget, BodyLabel, TextEdit, TransparentToolButton, StrongBodyLabel

from app.utils.utils import get_icon


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

    def __init__(self, run_id: str, title_color="color: #FFA500;", is_nested=False, parent=None):
        super().__init__(parent)
        self.run_id = run_id
        self.is_nested = is_nested
        self.is_collapsed = False
        self.is_current_running = False
        self.is_nested_mode = False
        self.parent_card = None

        # === 样式：先设初始样式 ===
        self._apply_initial_style(title_color)

        # === 计时器（仅顶层卡使用）===
        self._elapsed_timer = QElapsedTimer()
        self.timer_label = BodyLabel("0.00 s")
        self.timer_label.setStyleSheet("color: #FFA500; font-size: 13px; background: transparent; border: none;")
        self.timer_label.setFixedWidth(60)
        self.timer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_timer_display)
        self._update_timer.setInterval(100)

        # === 按钮 ===
        self.toggle_button = TransparentToolButton(self.ARROW_ICONS["expanded"], self)
        self.toggle_button.setFixedSize(16, 16)
        self.toggle_button.setStyleSheet("background: transparent; border: none;")
        self._update_toggle_text()
        self.toggle_button.clicked.connect(self.toggle)

        self.title_label = StrongBodyLabel(run_id)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(title_color + "background:transparent;border:none;")

        self.status_button = TransparentToolButton(self.STATUS_ICONS["default"], self)
        self.status_button.setFixedSize(20, 20)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.addWidget(self.toggle_button)
        title_layout.addWidget(self.title_label, 1)
        title_layout.addStretch()
        title_layout.addWidget(self.timer_label)
        title_layout.addWidget(self.status_button)

        # === 日志区域 ===
        self.log_text = TextEdit(self)
        font = self.log_text.font()
        font.setFamily("Consolas")
        font.setPointSize(10)
        self.log_text.setFont(font)
        self.log_text.setStyleSheet("background: transparent; border: none; color: white;")
        self.log_text.setReadOnly(True)
        self.log_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setSizeAdjustPolicy(TextEdit.AdjustToContents)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_text.textChanged.connect(self._adjust_height)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.log_text.setMinimumHeight(40)  # 防止高度为0

        # === 嵌套容器 ===
        self.nested_layout = QVBoxLayout()
        self.nested_layout.setContentsMargins(8, 4, 4, 4)
        self.nested_layout.setSpacing(4)
        self.nested_container = QWidget()
        self.nested_container.setLayout(self.nested_layout)
        self.nested_container.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(title_layout)
        layout.addWidget(self.log_text)
        layout.addWidget(self.nested_container)

        self.log_text.setVisible(True)

    def _apply_initial_style(self, title_color):
        border = "1px solid #FFA500" if self.is_nested else "1px solid #444"
        if self.is_nested:
            border = "1px solid #555"
        radius = "6px" if not self.is_nested else "4px"
        bg = "#2b2b2b"
        self.setStyleSheet(f"background-color: {bg}; border: {border}; border-radius: {radius};")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.run_id)
        super().mouseDoubleClickEvent(event)

    def _adjust_height(self):
        if self.is_nested_mode:
            total_height = self.nested_container.sizeHint().height()
            self.log_text.setFixedHeight(0)
            self.nested_container.setFixedHeight(max(total_height, 40))
        else:
            doc = self.log_text.document()
            height = int(doc.documentLayout().documentSize().height())
            self.log_text.setFixedHeight(max(height, 40))
            self.nested_container.setFixedHeight(0)
        self.updateGeometry()

    def expand(self):
        self.is_collapsed = False
        self.log_text.setVisible(not self.is_nested_mode)
        self.nested_container.setVisible(self.is_nested_mode)
        self.toggle_button.setIcon(self.ARROW_ICONS["expanded"])

    def collapse(self):
        self.is_collapsed = True
        self.log_text.setVisible(False)
        self.nested_container.setVisible(False)
        self.toggle_button.setIcon(self.ARROW_ICONS["collapsed"])

    def _update_toggle_text(self):
        icon = self.ARROW_ICONS["collapsed"] if self.is_collapsed else self.ARROW_ICONS["expanded"]
        self.toggle_button.setIcon(icon)

    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        if self.is_collapsed:
            self.collapse()
        else:
            self.expand()

    def set_current_running(self, is_running: bool):
        if self.is_current_running == is_running:
            return
        self.is_current_running = is_running
        if is_running:
            self.set_status("running")
            self._elapsed_timer.start()
            self._update_timer.start()
            self.timer_label.show()
            self.expand()
            if self.parent_card:
                self.parent_card.expand()
        else:
            self._update_timer.stop()
            # 不隐藏计时器
        self._update_style()

    def set_status(self, status: str):
        self.status = status
        icon = self.STATUS_ICONS.get(status, self.STATUS_ICONS["default"])
        self.status_button.setIcon(icon)

    def mark_as_error(self):
        self.set_status("error")
        self._update_timer.stop()
        self._update_style()
        self.expand()

    def mark_as_success(self):
        self.set_status("success")
        self._update_style()
        self.expand()

    def _update_style(self):
        if self.is_nested:
            border = "1px solid #f44747" if self.status == "error" else "1px solid #555"
        else:
            if self.is_current_running:
                border = "2px solid #FFA500"
            elif hasattr(self, 'status') and self.status == "error":
                border = "2px solid #f44747"
            else:
                border = "1px solid #444"
        radius = "6px" if not self.is_nested else "4px"
        bg = "#2b2b2b"
        self.setStyleSheet(f"background-color: {bg}; border: {border}; border-radius: {radius};")

    def _update_timer_display(self):
        elapsed_sec = self._elapsed_timer.elapsed() / 1000.0
        self.timer_label.setText(f"{elapsed_sec:.2f} s")

    def append_colored_log(self, text: str):
        if self.is_nested_mode:
            return
        if not text.strip():
            return
        lines = text.splitlines(keepends=True)
        new_html_lines = []
        for line in lines:
            color_hex = "#ffffff"
            line_for_check = line.replace('&nbsp;', ' ')
            for level, col in self.LEVEL_COLORS.items():
                if re.search(rf'\b{level}\b', line_for_check, re.IGNORECASE):
                    color_hex = col
                    break
            escaped_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_line = f'<pre style="color:{color_hex}; margin:0; padding:0;">{escaped_line}</pre>'
            new_html_lines.append(html_line)
        current_html = self.log_text.toHtml()
        if not current_html.startswith('<!DOCTYPE HTML'):
            current_html = ""
        full_html = current_html + "\n".join(new_html_lines)
        self.log_text.setHtml(full_html)
        vsb = self.log_text.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    def add_nested_card(self, run_id: str) -> 'CollapsibleLogCard':
        if self.is_nested:
            raise RuntimeError("No multi-level nesting")
        child_card = CollapsibleLogCard(run_id, title_color="color: #FFA500;", is_nested=True, parent=self)
        child_card.parent_card = self
        self.nested_layout.addWidget(child_card)
        if not self.is_nested_mode:
            self.is_nested_mode = True
            self.log_text.setVisible(False)
            self.nested_container.setVisible(True)
            self._adjust_height()
        return child_card

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()