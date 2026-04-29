# -*- coding: utf-8 -*-
"""
通用设置卡片基类 - 统一的设计语言
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
)
from qfluentwidgets import CardWidget, StrongBodyLabel
from app.utils.utils import get_unified_font


class BaseSettingsCard(CardWidget):
    """通用设置卡片基类"""

    closed = pyqtSignal()

    def __init__(self, title: str, icon: str = "⚙️", parent=None):
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._setup_base_ui()

    def _setup_base_ui(self):
        self.setSizePolicy(1, 0)  # 水平方向可扩展
        self.setFixedHeight(180)  # 固定高度，超出滚动
        self.setStyleSheet("""
            CardWidget {
                background-color: rgba(33, 33, 38, 250);
                border: 1px solid #3d3d3d;
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(4)

        # 头部
        header = QHBoxLayout()
        header.setSpacing(8)

        self.icon_label = QLabel(self._icon, self)
        self.icon_label.setFont(get_unified_font(12))

        self.title_label = StrongBodyLabel(self._title, self)
        self.title_label.setFont(get_unified_font(11, True))
        self.title_label.setStyleSheet("color: #f59e0b;")

        header.addWidget(self.icon_label)
        header.addWidget(self.title_label)
        header.addStretch()

        # 关闭按钮
        self.close_btn = QLabel("✕", self)
        self.close_btn.setFont(get_unified_font(11))
        self.close_btn.setStyleSheet("color: #888888; cursor: pointer; padding: 4px;")
        self.close_btn.mousePressEvent = lambda e: self._on_close()
        header.addWidget(self.close_btn)

        main_layout.addLayout(header)

        # 内容区域 - 使用 ScrollArea
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 2px 2px 2px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 4, 0, 4)
        self.content_layout.setSpacing(6)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area, 1)

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def show(self):
        self.setVisible(True)
        self.raise_()

    def hide(self):
        self.setVisible(False)
