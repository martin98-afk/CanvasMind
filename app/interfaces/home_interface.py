# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QRectF, QSize
from PyQt5.QtGui import QPixmap, QPainter, QColor, QBrush, QPainterPath, QLinearGradient
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QScrollArea, QGridLayout, QHBoxLayout

from qfluentwidgets import ScrollArea as QFluentScrollArea, isDarkTheme, FluentIcon, StyleSheetBase, Theme, qconfig, \
    ScrollArea

from app.utils.utils import get_icon
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.card_widget.home_card import HomeCardView
from app.widgets.card_widget.link_card import LinkCardView


class BannerWidget(QWidget):
    """ Banner widget """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFixedHeight(336)

        self.vBoxLayout = QVBoxLayout(self)
        self.galleryLabel = QLabel('Canvas Mind', self)
        self.banner = QPixmap('./icons/banner.png')
        self.linkCardView = LinkCardView(self)

        self.galleryLabel.setObjectName('galleryLabel')

        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setContentsMargins(0, 20, 0, 0)
        self.vBoxLayout.addWidget(self.galleryLabel)
        self.vBoxLayout.addWidget(self.linkCardView, Qt.AlignCenter)
        self.vBoxLayout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.linkCardView.addCard(
            get_icon("logo3"),
            self.tr('Getting started'),
            self.tr('An overview of app development options and samples.'),
            "https://martin98-afk.github.io/CanvasMind/  "
        )

        self.linkCardView.addCard(
            FluentIcon.GITHUB,
            self.tr('GitHub repo'),
            self.tr(
                'The latest fluent design controls and styles for your applications.'),
            "https://github.com/martin98-afk/CanvasMind  "
        )

        self.linkCardView.addCard(
            FluentIcon.CODE,
            self.tr('Code samples'),
            self.tr(
                'Find samples that demonstrate specific tasks, features and APIs.'),
            "https://github.com/martin98-afk/CanvasMind/tree/master/workflows  "
        )

        self.linkCardView.addCard(
            FluentIcon.FEEDBACK,
            self.tr('Send feedback'),
            self.tr('Help us improve Canvas Mind by providing feedback.'),
            "https://github.com/martin98-afk/CanvasMind/issues/new  "
        )

    def paintEvent(self, e):
        super().paintEvent(e)
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.SmoothPixmapTransform | QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        w, h = self.width(), self.height()
        path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        path.addRect(QRectF(0, h - 50, 50, 50))
        path.addRect(QRectF(w - 50, 0, 50, 50))
        path.addRect(QRectF(w - 50, h - 50, 50, 50))
        path = path.simplified()

        # init linear gradient effect
        gradient = QLinearGradient(0, 0, 0, h)

        # draw background color
        if not isDarkTheme():
            gradient.setColorAt(0, QColor(207, 216, 228, 255))
            gradient.setColorAt(1, QColor(207, 216, 228, 0))
        else:
            gradient.setColorAt(0, QColor(0, 0, 0, 255))
            gradient.setColorAt(1, QColor(0, 0, 0, 0))

        painter.fillPath(path, QBrush(gradient))

        # draw banner image
        pixmap = self.banner.scaled(self.size(), transformMode=Qt.SmoothTransformation)
        painter.fillPath(path, QBrush(pixmap))


class HorizontalCardContainerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(24, 24, 24, 24) # 左、上、右、下边距
        self.hBoxLayout.setSpacing(24) # 卡片之间的间距

        # --- 创建三个卡片并添加到水平布局 ---
        # 1. 快速开始卡片 (Quick Start Card)
        self.quickStartCard = HomeCardView(
            self.tr("Quick Start >"), self) # 使用你项目中的 SampleCardView1
        # 设置固定宽度，以便横向滚动
        self.quickStartCard.setFixedWidth(350)

        # 添加具体功能卡片
        self.quickStartCard.addSampleCard(
            icon=FluentIcon.ADD, # 可以是 QIcon 或 图片路径
            title=self.tr("New Canvas"),
            action=lambda: print("New Canvas clicked") # 替换为实际功能
        )
        self.quickStartCard.addSampleCard(
            icon=FluentIcon.HISTORY, # 假设图标合适
            title=self.tr("Recent Canvas 1"), # 这里需要动态获取最近的画布列表
            action=lambda: print("Open Recent Canvas 1 clicked") # 替换为实际功能
        )
        # ... 可以添加更多最近的画布 ...

        # 2. 样例模型展示卡片 (Sample Models Card)
        self.sampleModelCard = HomeCardView(
            self.tr("Sample Models >"), self)
        self.sampleModelCard.setFixedWidth(350)

        # 添加样例模型功能卡片
        self.sampleModelCard.addSampleCard(
            icon=FluentIcon.APPLICATION, # 假设图标合适
            title=self.tr("Basic Workflow"),
            action=lambda: print("Load Basic Workflow clicked") # 替换为实际功能
        )
        self.sampleModelCard.addSampleCard(
            icon=FluentIcon.CODE, # 假设图标合适
            title=self.tr("ML Pipeline"),
            action=lambda: print("Load ML Pipeline clicked") # 替换为实际功能
        )
        # ... 可以添加更多样例 ...

        # 3. 环境编辑卡片 (Environment Edit Card)
        self.envEditCard = HomeCardView(
            self.tr("Environment >"), self)
        self.envEditCard.setFixedWidth(350)

        # 添加环境编辑功能卡片
        self.envEditCard.addSampleCard(
            icon=FluentIcon.SETTING, # 假设图标合适
            title=self.tr("Manage Environments"),
            action=lambda: print("Manage Environments clicked") # 替换为实际功能
        )
        self.envEditCard.addSampleCard(
            icon=FluentIcon.ADD, # 假设图标合适
            title=self.tr("Create New Environment"),
            action=lambda: print("Create New Environment clicked") # 替换为实际功能
        )
        # ... 可以添加更多环境相关功能 ...

        # 将三个卡片添加到水平布局
        self.hBoxLayout.addWidget(self.quickStartCard)
        self.hBoxLayout.addWidget(self.sampleModelCard)
        self.hBoxLayout.addWidget(self.envEditCard)

        # 添加一个弹簧，防止卡片被拉伸，并填充剩余空间
        self.hBoxLayout.addStretch(1)


class HomeInterface(ScrollArea):
    """ Home interface """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.banner = BannerWidget(self)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        self.__initWidget()
        self.load_cards()

    def __initWidget(self):
        self.view.setObjectName('view')
        self.setObjectName('homeInterface')
        StyleSheet.HOME_INTERFACE.apply(self)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(self.view)
        self.setWidgetResizable(True)

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(25)
        self.vBoxLayout.addWidget(self.banner)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

    def load_cards(self):
        self.quickStartCard = HomeCardView(
            self.tr("Quick Start >"), self)  # 使用你项目中的 SampleCardView1
        # 设置固定宽度，以便横向滚动
        self.quickStartCard.setFixedWidth(350)

        # 添加具体功能卡片
        self.quickStartCard.addSampleCard(
            icon=FluentIcon.ADD,  # 可以是 QIcon 或 图片路径
            title=self.tr("New Canvas"),
            action=lambda: print("New Canvas clicked")  # 替换为实际功能
        )
        self.quickStartCard.addSampleCard(
            icon=FluentIcon.HISTORY,  # 假设图标合适
            title=self.tr("Recent Canvas 1"),  # 这里需要动态获取最近的画布列表
            action=lambda: print("Open Recent Canvas 1 clicked")  # 替换为实际功能
        )
        # ... 可以添加更多最近的画布 ...

        # 2. 样例模型展示卡片 (Sample Models Card)
        self.sampleModelCard = HomeCardView(
            self.tr("Sample Models >"), self)
        self.sampleModelCard.setFixedWidth(350)

        # 添加样例模型功能卡片
        self.sampleModelCard.addSampleCard(
            icon=FluentIcon.APPLICATION,  # 假设图标合适
            title=self.tr("Basic Workflow"),
            action=lambda: print("Load Basic Workflow clicked")  # 替换为实际功能
        )
        self.sampleModelCard.addSampleCard(
            icon=FluentIcon.CODE,  # 假设图标合适
            title=self.tr("ML Pipeline"),
            action=lambda: print("Load ML Pipeline clicked")  # 替换为实际功能
        )
        # ... 可以添加更多样例 ...

        # 3. 环境编辑卡片 (Environment Edit Card)
        self.envEditCard = HomeCardView(
            self.tr("Environment >"), self)
        self.envEditCard.setFixedWidth(350)

        # 添加环境编辑功能卡片
        self.envEditCard.addSampleCard(
            icon=FluentIcon.SETTING,  # 假设图标合适
            title=self.tr("Manage Environments"),
            action=lambda: print("Manage Environments clicked")  # 替换为实际功能
        )
        self.envEditCard.addSampleCard(
            icon=FluentIcon.ADD,  # 假设图标合适
            title=self.tr("Create New Environment"),
            action=lambda: print("Create New Environment clicked")  # 替换为实际功能
        )
        self.vBoxLayout.addWidget(self.quickStartCard)
        self.vBoxLayout.addWidget(self.sampleModelCard)
        self.vBoxLayout.addWidget(self.envEditCard)
