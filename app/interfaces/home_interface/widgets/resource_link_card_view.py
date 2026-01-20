# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from PyQt5.QtCore import Qt, QRectF, pyqtSignal, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QBrush, QPixmap
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect,
                             QOpenGLWidget, QFileDialog, QLabel)
from qfluentwidgets import (
    ScrollArea, FluentIcon, FlowLayout, PrimaryPushButton, PushButton,
    SimpleCardWidget, setTheme, Theme
)

from app.interfaces.home_interface.widgets.stylish_card import StylishCard
from app.utils.utils import get_icon, resource_path


class ResourceLinkCardView(SimpleCardWidget):
    """ 资源链接 """

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("SimpleCardWidget { background-color: transparent; border: none; }")

        display_title = title if title else self.tr("资源与支持 >")
        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(20, 10, 20, 10)

        self.titleLabel = QLabel(display_title)
        self.titleLabel.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold; margin-bottom: 8px;")

        # 这里复用了 LinkCardView，但需要确保 LinkCardView 内部也是透明的
        # 简单处理：给 LinkCardView 注入样式，或者如果它是封装好的，我们可能需要类似 StylishCard 的重写
        # 这里为了保持一致性，我们直接手动添加 StylishCard 风格的链接

        self.contentLayout = FlowLayout()
        self.contentLayout.setSpacing(16)
        self.contentLayout.setContentsMargins(0, 0, 0, 0)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addLayout(self.contentLayout)

        links = [
            (FluentIcon.GITHUB, "项目地址", "GitHub 源码", "https://github.com/martin98-afk/CanvasMind"),
            (get_icon("logo3"), "使用指南", "文档与教程",
             "https://canvasmind-sphinx-build.readthedocs.io/zh-cn/latest/"),
            (get_icon("bilibili"), "视频介绍", "B站演示视频", "https://www.bilibili.com/video/BV13Sr6BiEAB/"),
            (FluentIcon.CODE, "流程图样例", "更多官方样例",
             "https://github.com/martin98-afk/CanvasMind/tree/master/examples"),
            (FluentIcon.FEEDBACK, "反馈意见", "提交 Issue", "https://github.com/martin98-afk/CanvasMind/issues/new")
        ]

        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl

        self.link_cards = []
        for icon, title, desc, url in links:
            card = StylishCard(icon, title, desc, self)
            card.clicked.connect(lambda u=url: QDesktopServices.openUrl(QUrl(u)))
            self.contentLayout.addWidget(card)
            self.link_cards.append(card)

        # 同样需要宽度调整逻辑
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self._recalc_width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_timer.start(50)

    def _recalc_width(self):
        container_width = self.contentsRect().width() - self.vLayout.contentsMargins().left() - self.vLayout.contentsMargins().right()
        min_width = 260
        spacing = self.contentLayout.horizontalSpacing()
        cards_per_row = max(1, (container_width + spacing) // (min_width + spacing))
        target_width = (container_width - (cards_per_row - 1) * spacing) // cards_per_row
        for card in self.link_cards:
            card.setFixedWidth(target_width)
