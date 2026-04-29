# -*- coding: utf-8 -*-
"""
历史会话卡片 - 直接使用 BaseSettingsCard 的 scroll_area
"""
import datetime
from typing import List, Dict, Optional
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    TransparentToolButton,
    FluentIcon,
)
from app.utils.utils import get_icon


def format_relative_time(time_str: str) -> str:
    """将时间字符串转换为相对时间显示"""
    if not time_str or time_str == "未知":
        return "更早"
    try:
        session_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()
        diff = now - session_time

        if diff.total_seconds() < 60:
            return "刚刚"
        elif diff.total_seconds() < 3600:
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes}分钟前"
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"{hours}小时前"
        elif diff.days == 1:
            return "昨天"
        elif diff.days < 7:
            return f"{diff.days}天前"
        else:
            return time_str[5:10] if len(time_str) >= 10 else time_str
    except (ValueError, TypeError):
        return time_str[5:10] if time_str and len(time_str) >= 10 else "更早"


def get_message_preview(messages: List[Dict], max_len: int = 50) -> str:
    """从消息列表中提取预览文本"""
    if not messages:
        return ""
    for msg in reversed(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user" and content:
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") if isinstance(c, dict) else str(c)
                    for c in content
                )
            return content[:max_len].strip() + ("..." if len(content) > max_len else "")
    return ""


class _HistoryItemCard(CardWidget):
    """历史会话项卡片"""

    sessionClicked = pyqtSignal(int)
    deleteRequested = pyqtSignal(int)
    renameRequested = pyqtSignal(int, str)

    def __init__(
        self,
        index: int,
        title: str,
        last_time: str,
        message_count: int,
        is_current: bool,
        preview: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._index = index
        self._is_current = is_current
        self._is_editing = False
        self.setCursor(Qt.PointingHandCursor)

        if is_current:
            self.setStyleSheet(
                """
                CardWidget {
                    background-color: rgba(102, 198, 255, 0.12);
                    border: 2px solid rgba(102, 198, 255, 0.6);
                    border-radius: 10px;
                }
                CardWidget:hover {
                    background-color: rgba(102, 198, 255, 0.18);
                    border: 2px solid rgba(102, 198, 255, 0.8);
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                CardWidget {
                    background-color: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 10px;
                }
                CardWidget:hover {
                    background-color: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(102, 198, 255, 0.45);
                }
                """
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.title_label = BodyLabel(title[:100], self)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            "color: white; font-weight: bold;" if is_current else "color: white;"
        )
        top_row.addWidget(self.title_label, 1)

        self.title_edit = QLineEdit(title[:100], self)
        self.title_edit.setStyleSheet(
            """
            QLineEdit {
                background-color: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(102, 198, 255, 0.5);
                border-radius: 4px;
                color: white;
                padding: 2px 6px;
            }
            """
        )
        self.title_edit.hide()
        self.title_edit.setMaximumWidth(250)
        self.title_edit.returnPressed.connect(self._finish_edit)
        self.title_edit.editingFinished.connect(self._finish_edit)
        top_row.addWidget(self.title_edit, 1, Qt.AlignLeft)

        self.current_indicator = CaptionLabel("🔥 活跃中", self)
        self.current_indicator.setStyleSheet(
            "color: #fff; font-weight: bold; background-color: rgba(102, 198, 255, 0.35); border-radius: 4px; padding: 2px 8px;"
        )
        self.current_indicator.setVisible(is_current)
        top_row.addWidget(self.current_indicator, 0, Qt.AlignTop)

        btn_container = QHBoxLayout()
        btn_container.setSpacing(2)

        self.edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
        self.edit_btn.setToolTip("重命名")
        self.edit_btn.setFixedSize(24, 24)
        self.edit_btn.clicked.connect(self._start_edit)
        btn_container.addWidget(self.edit_btn)

        self.delete_btn = TransparentToolButton(get_icon("归档"), self)
        self.delete_btn.setToolTip("归档")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.clicked.connect(lambda: self.deleteRequested.emit(self._index))
        btn_container.addWidget(self.delete_btn)

        top_row.addLayout(btn_container, 0)

        layout.addLayout(top_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        rel_time = format_relative_time(last_time)
        meta_text = f"{rel_time} · {message_count} 轮对话"
        self.meta_label = CaptionLabel(meta_text, self)
        self.meta_label.setStyleSheet(
            "color: #ffb65c;" if is_current else "color: rgba(255, 255, 255, 0.5);"
        )
        bottom_row.addWidget(self.meta_label)

        bottom_row.addStretch(1)

        if preview:
            self.preview_label = CaptionLabel(preview, self)
            self.preview_label.setStyleSheet(
                "color: rgba(255, 255, 255, 0.4); font-style: italic;"
            )
            self.preview_label.setWordWrap(True)
            self.preview_label.setMaximumWidth(260)
            bottom_row.addWidget(self.preview_label, 0, Qt.AlignRight)

        layout.addLayout(bottom_row)

    def _start_edit(self):
        self._is_editing = True
        self.title_label.hide()
        self.title_edit.show()
        self.title_edit.setText(self.title_label.text())
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def _finish_edit(self):
        if not self._is_editing:
            return
        new_title = self.title_edit.text().strip()
        if new_title and new_title != self.title_label.text():
            self.renameRequested.emit(self._index, new_title)
        self._is_editing = False
        self.title_edit.hide()
        self.title_label.show()

    def update_title(self, new_title: str):
        self.title_label.setText(new_title[:100])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_editing:
            self.sessionClicked.emit(self._index)
        super().mousePressEvent(event)


class _SectionHeader(QLabel):
    def __init__(self, text: str, count: int = 0, parent=None):
        super().__init__(parent)
        display_text = text if count == 0 else f"{text} ({count})"
        self.setText(display_text)
        self.setStyleSheet(
            """
            color: rgba(255, 255, 255, 0.45);
            font-size: 12px;
            font-weight: bold;
            padding: 4px 2px;
            """
        )


class HistoryCard(QWidget):
    """历史会话卡片内容 - 直接使用 BaseSettingsCard 的 scroll_area"""

    sessionSelected = pyqtSignal(int)
    sessionArchived = pyqtSignal(int)
    sessionRenamed = pyqtSignal(int, str)
    refreshRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_history: List[Dict] = []
        self._current_index: Optional[int] = None
        self._item_cards = []
        self._setup_ui()

    def _setup_ui(self):
        """不需要创建自己的布局，直接使用父控件的 scroll_area"""
        pass

    def get_content_layout(self) -> QVBoxLayout:
        """返回内容布局，供外部使用"""
        # 找到 BaseSettingsCard 的 content_layout
        parent = self.parent()
        while parent:
            if hasattr(parent, 'content_layout'):
                return parent.content_layout
            parent = parent.parent()
        # 如果没找到，返回自己的默认布局
        if self.layout() is None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(6)
        return self.layout()

    def _get_date_category(self, last_time_str: str) -> str:
        if not last_time_str or last_time_str == "未知":
            return "更早"
        try:
            session_date = datetime.datetime.strptime(
                last_time_str[:10], "%Y-%m-%d"
            ).date()
            today = datetime.datetime.now().date()
            yesterday = today - datetime.timedelta(days=1)
            week_start = today - datetime.timedelta(days=today.weekday())
            last_week_start = week_start - datetime.timedelta(days=7)
            month_start = today.replace(day=1)

            if session_date == today:
                return "今天"
            elif session_date == yesterday:
                return "昨天"
            elif week_start <= session_date <= today:
                return "本周"
            elif last_week_start <= session_date < week_start:
                return "上周"
            elif session_date >= month_start:
                return "本月"
            elif session_date.year == today.year:
                month_names = ["一月", "二月", "三月", "四月", "五月", "六月",
                               "七月", "八月", "九月", "十月", "十一月", "十二月"]
                return month_names[session_date.month - 1]
            else:
                return f"{session_date.year}年"
        except (ValueError, TypeError):
            return "更早"

    def _clear_content(self):
        """清理内容区域"""
        layout = self.get_content_layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() and item.widget() != self:
                item.widget().deleteLater()
        self._item_cards.clear()

    def set_history(self, history_list: List[Dict], current_index=None):
        """设置历史会话列表"""
        self._all_history = history_list
        self._current_index = current_index
        self._update_display()

    def _update_display(self):
        """更新显示内容"""
        layout = self.get_content_layout()
        self._clear_content()

        if not self._all_history:
            empty_label = QLabel("暂无历史对话记录")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: rgba(255, 255, 255, 0.6); padding: 16px;")
            layout.addWidget(empty_label)
        else:
            # 先显示当前会话
            current_session_widget = None
            if self._current_index is not None and 0 <= self._current_index < len(self._all_history):
                current_session = self._all_history[self._current_index]
                current_preview = get_message_preview(current_session.get("messages", []))
                current_session_widget = _HistoryItemCard(
                    index=self._current_index,
                    title=current_session.get("title", "当前对话"),
                    last_time=current_session.get("last_time", "未知"),
                    message_count=current_session.get("message_count", 0),
                    is_current=True,
                    preview=current_preview,
                )
                current_session_widget.sessionClicked.connect(self._on_card_clicked)
                current_session_widget.deleteRequested.connect(self._on_card_deleted)
                current_session_widget.renameRequested.connect(self._on_card_renamed)

            # 分离当前会话和其他会话
            other_sessions = [s for i, s in enumerate(self._all_history) if i != self._current_index]
            grouped = {}
            for session in other_sessions:
                category = self._get_date_category(session.get("last_time", ""))
                if category not in grouped:
                    grouped[category] = []
                grouped[category].append(session)

            order = ["今天", "昨天", "本周", "上周", "本月"]
            month_names = ["一月", "二月", "三月", "四月", "五月", "六月",
                           "七月", "八月", "九月", "十月", "十一月", "十二月"]

            extra_sections = []
            for key in grouped.keys():
                if key not in order and key != "更早":
                    extra_sections.append((key, grouped[key]))

            year_groups = {}
            month_groups = []
            for key, sessions in extra_sections:
                if key.endswith("年"):
                    year_groups[key] = sessions
                else:
                    month_groups.append((key, sessions))

            final_order = []
            for section in order:
                if section in grouped:
                    final_order.append((section, grouped[section]))
            for section, sessions in month_groups:
                final_order.append((section, sessions))
            for year in sorted(year_groups.keys(), reverse=True):
                final_order.append((year, year_groups[year]))

            has_items = False

            # 渲染当前会话
            if current_session_widget:
                has_items = True
                current_header = _SectionHeader("当前会话", 0)
                layout.addWidget(current_header)
                layout.addWidget(current_session_widget)
                self._item_cards.append(current_session_widget)

                spacer = QWidget()
                spacer.setFixedHeight(8)
                layout.addWidget(spacer)

            # 渲染其他历史会话
            for section, sessions in final_order:
                if not sessions:
                    continue
                has_items = True

                header = _SectionHeader(section, len(sessions))
                layout.addWidget(header)

                for session in sessions:
                    original_index = self._all_history.index(session)
                    messages = session.get("messages", [])
                    preview = get_message_preview(messages)
                    card = _HistoryItemCard(
                        index=original_index,
                        title=session.get("title", "新对话"),
                        last_time=session.get("last_time", "未知"),
                        message_count=session.get("message_count", 0),
                        is_current=False,
                        preview=preview,
                    )
                    card.sessionClicked.connect(self._on_card_clicked)
                    card.deleteRequested.connect(self._on_card_deleted)
                    card.renameRequested.connect(self._on_card_renamed)
                    layout.addWidget(card)
                    self._item_cards.append(card)

                spacer = QWidget()
                spacer.setFixedHeight(8)
                layout.addWidget(spacer)

            if not has_items:
                empty_label = QLabel("暂无历史对话记录")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("color: rgba(255, 255, 255, 0.6); padding: 16px;")
                layout.addWidget(empty_label)

        layout.addStretch(1)

    def _on_card_clicked(self, index: int):
        self.sessionSelected.emit(index)

    def _on_card_deleted(self, index: int):
        self.sessionArchived.emit(index)

    def _on_card_renamed(self, index: int, new_title: str):
        self.sessionRenamed.emit(index, new_title)
