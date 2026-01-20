# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel)
from qfluentwidgets import (
    FluentIcon, CardWidget, IconWidget
)
from qfluentwidgets.common.icon import FluentIconBase

from app.utils.utils import get_icon


class StylishCard(CardWidget):
    """
    【核心修改】重写的高级卡片
    强制定义样式，不依赖默认主题，保证深色模式下绝对好看
    """

    def __init__(self, icon, title, content, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)  # 固定高度，整齐划一
        self.setCursor(Qt.PointingHandCursor)  # 鼠标变手型

        # 1. 布局容器
        self.hLayout = QHBoxLayout(self)
        self.hLayout.setContentsMargins(16, 16, 16, 16)
        self.hLayout.setSpacing(16)

        # 2. 图标 (左侧)
        # 兼容 FluentIcon 和 QIcon/String
        if isinstance(icon, (FluentIcon, FluentIconBase)):
            self.iconWidget = IconWidget(icon)
        else:
            self.iconWidget = IconWidget(get_icon(icon) if isinstance(icon, str) else icon)

        self.iconWidget.setFixedSize(32, 32)
        self.hLayout.addWidget(self.iconWidget)

        # 3. 文字区域 (右侧)
        self.textContainer = QWidget()
        self.textLayout = QVBoxLayout(self.textContainer)
        self.textLayout.setContentsMargins(0, 0, 0, 0)
        self.textLayout.setSpacing(4)  # 标题和内容的间距

        # 标题：强制白色，加粗，16px
        self.titleLabel = QLabel(title)
        self.titleLabel.setObjectName("CardTitle")

        # 内容：强制灰色，常规，12px
        self.contentLabel = QLabel(content)
        self.contentLabel.setObjectName("CardContent")
        self.contentLabel.setWordWrap(False)  # 不换行，超长截断

        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.contentLabel)
        self.textLayout.addStretch(1)  # 顶对齐

        self.hLayout.addWidget(self.textContainer)
        self.hLayout.addStretch(1)

        # 4. 【关键】强制样式表 (QSS)
        # 这里的颜色是精心调配的深色模式配色
        self.setStyleSheet("""
            StylishCard {
                background-color: #2b2b2b;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
            }
            StylishCard:hover {
                background-color: #3a3a3a;
                border: 1px solid #505050;
            }
            QLabel#CardTitle {
                color: #ffffff;
                font-family: "Microsoft YaHei UI", "Segoe UI";
                font-size: 16px;
                font-weight: bold;
                background-color: transparent;
            }
            QLabel#CardContent {
                color: #bbbbbb;
                font-family: "Microsoft YaHei UI", "Segoe UI";
                font-size: 12px;
                background-color: transparent;
            }
        """)