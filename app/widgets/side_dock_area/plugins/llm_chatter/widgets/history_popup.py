# -*- coding: utf-8 -*-
from typing import List, Dict, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from qfluentwidgets import BodyLabel, CaptionLabel, CardWidget, TransparentToolButton, FluentIcon
from qfluentwidgets.components.widgets.card_widget import CardSeparator


class _HistoryItemCard(CardWidget):
    sessionClicked = pyqtSignal(int)
    deleteRequested = pyqtSignal(int)

    def __init__(
        self,
        index: int,
        title: str,
        last_time: str,
        message_count: int,
        is_current: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._index = index
        self.setCursor(Qt.PointingHandCursor)
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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(8)

        text_wrap = QVBoxLayout()
        text_wrap.setContentsMargins(0, 0, 0, 0)
        text_wrap.setSpacing(2)

        title_label = BodyLabel(title[:200], self)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            "color: white; font-weight: bold;" if is_current else "color: white;"
        )
        text_wrap.addWidget(title_label)

        meta_text = f"{last_time} · {message_count} 轮"
        if is_current:
            meta_text += " · 当前"
        meta_label = CaptionLabel(meta_text, self)
        meta_label.setStyleSheet(
            "color: #ffb65c;" if is_current else "color: rgba(255, 255, 255, 0.6);"
        )
        text_wrap.addWidget(meta_label)

        layout.addLayout(text_wrap, 1)

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setToolTip("删除历史")
        delete_btn.setFixedSize(24, 24)
        delete_btn.clicked.connect(lambda: self.deleteRequested.emit(self._index))
        layout.addWidget(delete_btn, 0, Qt.AlignTop)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.sessionClicked.emit(self._index)
        super().mousePressEvent(event)


class HistoryPopup(QWidget):
    sessionSelected = pyqtSignal(int)
    sessionDeleted = pyqtSignal(int)
    MAX_CONTENT_HEIGHT = 420

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("historyPopupFrame")
        self.main_frame.setStyleSheet(
            """
            QFrame#historyPopupFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 10px;
            }
            """
        )
        outer.addWidget(self.main_frame)

        layout = QVBoxLayout(self.main_frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = BodyLabel("历史对话", self.main_frame)
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        layout.addWidget(title)
        layout.addWidget(CardSeparator(self.main_frame))

        self.scroll_area = QScrollArea(self.main_frame)
        self.scroll_area.setObjectName("historyScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFixedHeight(self.MAX_CONTENT_HEIGHT)
        self.scroll_area.setViewportMargins(2, 2, 10, 2)
        self.scroll_area.setStyleSheet(
            """
            QScrollArea#historyScrollArea {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 18px;
            }
            QScrollArea#historyScrollArea > QWidget > QWidget {
                background: transparent;
                border-radius: 14px;
            }
            QScrollBar:vertical {
                width: 10px;
                background: transparent;
                margin: 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(140, 148, 160, 0.45);
                border-radius: 5px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(160, 168, 180, 0.62);
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

        self.content_widget = QWidget(self.scroll_area)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)

        self.setMinimumWidth(360)
        self.setMaximumWidth(420)

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_history(self, history_list: List[Dict], current_index: Optional[int]):
        self._clear_content()

        if not history_list:
            empty_label = QLabel("暂无历史对话记录", self.content_widget)
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: rgba(255, 255, 255, 0.6); padding: 16px;")
            self.content_layout.addWidget(empty_label)
        else:
            for index, session in enumerate(history_list):
                card = _HistoryItemCard(
                    index=index,
                    title=session.get("title", "新对话"),
                    last_time=session.get("last_time", "未知"),
                    message_count=session.get("message_count", 0),
                    is_current=current_index == index,
                    parent=self.content_widget,
                )
                card.sessionClicked.connect(self.sessionSelected.emit)
                card.deleteRequested.connect(self.sessionDeleted.emit)
                self.content_layout.addWidget(card)

        self.content_layout.addStretch(1)
        self.content_layout.invalidate()
        self.content_widget.adjustSize()
        self.scroll_area.verticalScrollBar().setValue(0)
        self.scroll_area.updateGeometry()
        self.content_widget.updateGeometry()
        self.adjustSize()

    def show_at(self, reference_widget: QWidget):
        self.adjustSize()
        btn_rect = reference_widget.rect()
        btn_global_pos = reference_widget.mapToGlobal(btn_rect.topLeft())
        btn_width = btn_rect.width()
        btn_height = btn_rect.height()

        popup_width = self.width()
        popup_height = self.height()

        x = btn_global_pos.x() + btn_width - popup_width
        y = btn_global_pos.y() + btn_height

        screen = reference_widget.screen() if hasattr(reference_widget, "screen") else None
        if screen:
            screen_geom = screen.availableGeometry()
            x = max(x, screen_geom.left())
            if y + popup_height > screen_geom.bottom():
                y = btn_global_pos.y() - popup_height

        self.move(x, y)
        self.show()
        self.raise_()
        self.setFocus()
