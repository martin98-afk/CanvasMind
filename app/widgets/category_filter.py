# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt, pyqtSignal, QRect
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QApplication
)
from PyQt5.QtGui import QColor
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton,
    SmoothScrollArea, setFont, isDarkTheme, CheckBox, SimpleCardWidget
)


class CategoryFilterDialog(QWidget):
    categories_changed = pyqtSignal(set)

    def __init__(self, categories, parent=None, selected_categories=None, direction="auto", max_visible=8):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.categories = categories
        self.selected_categories = set(selected_categories or categories)
        self.checkboxes = []
        self.max_visible = max_visible
        self._direction = direction

        self._init_ui()
        self._apply_dark_scroll_fix()

    def _init_ui(self):
        self.card = SimpleCardWidget(self)
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(12, 12, 12, 12)
        self.card_layout.setSpacing(10)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        select_all_btn = PrimaryPushButton("全选", self)
        select_all_btn.setMinimumWidth(80)
        select_all_btn.clicked.connect(self._select_all)

        select_none_btn = PushButton("取消全选", self)
        select_none_btn.setMinimumWidth(80)
        select_none_btn.clicked.connect(self._select_none)

        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addStretch(1)

        self.card_layout.addLayout(button_layout)

        # 滚动区域
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 内容容器
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("border: none;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(2, 2, 2, 2)  # 微调内边距
        self.content_layout.setSpacing(6)

        for category in self.categories:
            checkbox = CheckBox(category, self)
            setFont(checkbox, 12)
            checkbox.setChecked(category in self.selected_categories)
            checkbox.stateChanged.connect(
                lambda state, cat=category: self._on_category_toggled(cat, state)
            )
            self.checkboxes.append(checkbox)
            self.content_layout.addWidget(checkbox)

        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content_widget)

        # 动态高度
        item_height = 28
        visible_count = min(len(self.categories), self.max_visible)
        scroll_height = visible_count * (item_height + 6) - 6
        self.scroll_area.setFixedHeight(scroll_height)

        self.card_layout.addWidget(self.scroll_area)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.card)

    def _apply_dark_scroll_fix(self):
        """关键：修复深色模式下滚动区域白色背景和滚动条问题"""
        # 圆角
        self.setStyleSheet(f"background-color: #2D2D2D; border-radius: 4px;")
        self.content_widget.setStyleSheet(f"""
            QWidget {{
                background-color: #2D2D2D;
                border: none;
            }}
        """)

        # 2. 强制滚动区域 viewport 背景
        viewport = self.scroll_area.viewport()
        viewport.setStyleSheet(f"background-color: #2D2D2D; border: none;")

        # 3. （可选）自定义滚动条样式（更保险）
        self.scroll_area.setStyleSheet("""
            SmoothScrollArea QScrollBar:vertical {
                width: 10px;
                background: transparent;
            }
            SmoothScrollArea QScrollBar::handle:vertical {
                border-radius: 5px;
                background: rgba(255, 255, 255, 0.2);
                min-height: 30px;
            }
            SmoothScrollArea QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.3);
            }
            SmoothScrollArea QScrollBar::add-line:vertical,
            SmoothScrollArea QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def _on_category_toggled(self, category, state):
        if state == Qt.Checked:
            self.selected_categories.add(category)
        else:
            self.selected_categories.discard(category)
        self.categories_changed.emit(self.selected_categories)

    def _select_all(self):
        for cb in self.checkboxes:
            cb.setChecked(True)
        self.selected_categories = set(self.categories)
        self.categories_changed.emit(self.selected_categories)

    def _select_none(self):
        for cb in self.checkboxes:
            cb.setChecked(False)
        self.selected_categories.clear()
        self.categories_changed.emit(self.selected_categories)

    def get_selected_categories(self):
        return self.selected_categories.copy()

    def show_at(self, pos):
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        w, h = self.card.width(), self.card.height()
        x = max(screen.left(), min(pos.x(), screen.right() - w))

        if self._direction == "auto":
            space_below = screen.bottom() - pos.y()
            space_above = pos.y() - screen.top()
            y = pos.y() if space_below >= h else (pos.y() - h if space_above >= h else max(screen.top(), pos.y()))
        else:
            y = pos.y() if self._direction == "down" else pos.y() - h
        y = max(screen.top(), min(y, screen.bottom() - h))

        self.move(x, y)
        self.show()
        self.setFocus()