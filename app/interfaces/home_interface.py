# -*- coding: utf-8 -*-
# coding:utf-8
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from PyQt5.QtCore import Qt, QSize, QRectF
from PyQt5.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QBrush, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout

from qfluentwidgets import ScrollArea, FluentIcon, isDarkTheme, Theme, qconfig

from app.utils.utils import get_icon
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.card_widget.home_card import HomeCardView
from app.widgets.card_widget.link_card import LinkCardView
from app.widgets.card_widget.workflow_card import WorkflowCard


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
            "https://martin98-afk.github.io/CanvasMind/    "
        )

        self.linkCardView.addCard(
            FluentIcon.GITHUB,
            self.tr('GitHub repo'),
            self.tr(
                'The latest fluent design controls and styles for your applications.'),
            "https://github.com/martin98-afk/CanvasMind    "
        )

        self.linkCardView.addCard(
            FluentIcon.CODE,
            self.tr('Code samples'),
            self.tr(
                'Find samples that demonstrate specific tasks, features and APIs.'),
            "https://github.com/martin98-afk/CanvasMind/tree/master/workflows    "
        )

        self.linkCardView.addCard(
            FluentIcon.FEEDBACK,
            self.tr('Send feedback'),
            self.tr('Help us improve Canvas Mind by providing feedback.'),
            "https://github.com/martin98-afk/CanvasMind/issues/new    "
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


class HorizontalCardContainerWidget(ScrollArea):
    def __init__(self, gallery_page_instance, parent=None):
        """
        Args:
            gallery_page_instance: WorkflowCanvasGalleryPage 的实例，用于获取画布列表和调用方法
            parent: 父窗口
        """
        super().__init__(parent)
        self.parent = parent
        self.gallery_page = gallery_page_instance # 保存 gallery_page 实例引用

        # 设置横向滚动区域
        self.setWidgetResizable(False) # 关键：不要让内部 widget 自适应高度
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 创建内容 Widget
        self.view = QWidget(self)
        self.hBoxLayout = QHBoxLayout(self.view)
        self.hBoxLayout.setContentsMargins(24, 24, 24, 24)  # 左、上、右、下边距
        self.hBoxLayout.setSpacing(24)  # 卡片之间的间距

        # --- 创建三个卡片并添加到水平布局 ---
        # 1. 快速开始区域 (Quick Start Area) - 使用独立布局
        self.quickStartCardContainer = QWidget(self.view)
        quick_start_layout = QVBoxLayout(self.quickStartCardContainer)

        # 添加标题
        title_label = QLabel("Quick Start >")
        title_label.setStyleSheet("""color: white; font: 14px 'Segoe UI', 'Microsoft YaHei', 'PingFang SC'; font-weight: bold;""")
        quick_start_layout.addWidget(title_label)

        # 添加“新建”按钮
        self.recent_canvas_container = QWidget(self.quickStartCardContainer)
        self.recent_canvas_layout = QHBoxLayout(self.recent_canvas_container)
        self.recent_canvas_layout.setContentsMargins(20, 20, 20, 20)
        self.recent_canvas_layout.setSpacing(5)  # 按钮间距
        self.recent_canvas_layout.addWidget(WorkflowCard(parent=self.gallery_page, type="create"))
        # 创建一个专门用于放置最近画布卡片的容器
        quick_start_layout.addWidget(self.recent_canvas_container)

        # 2. 样例模型展示卡片 (Sample Models Card)
        self.sampleModelCard = HomeCardView(
            self.tr("Sample Models >"), self.view)
        self.sampleModelCard.setFixedWidth(350)

        # 添加样例模型功能卡片
        self.sampleModelCard.addSampleCard(
            icon=FluentIcon.APPLICATION,
            title=self.tr("Basic Workflow"),
            action=lambda: print("Load Basic Workflow clicked") # 替换为实际功能
        )
        self.sampleModelCard.addSampleCard(
            icon=FluentIcon.CODE,
            title=self.tr("ML Pipeline"),
            action=lambda: print("Load ML Pipeline clicked") # 替换为实际功能
        )
        # 3. 环境编辑卡片 (Environment Edit Card)
        self.envEditCard = HomeCardView(
            self.tr("Environment >"), self.view)
        self.envEditCard.setFixedWidth(350)

        # 添加环境编辑功能卡片
        self.envEditCard.addSampleCard(
            icon=FluentIcon.SETTING,
            title=self.tr("Manage Environments"),
            action=lambda: print("Manage Environments clicked") # 替换为实际功能
        )
        self.envEditCard.addSampleCard(
            icon=FluentIcon.ADD,
            title=self.tr("Create New Environment"),
            action=lambda: print("Create New Environment clicked") # 替换为实际功能
        )
        # 将三个卡片添加到水平布局
        self.hBoxLayout.addWidget(self.quickStartCardContainer)
        self.hBoxLayout.addWidget(self.sampleModelCard)
        self.hBoxLayout.addWidget(self.envEditCard)

        self.gallery_page.scan_finished.connect(self._on_scan_finished)

    def _add_loading_placeholder(self):
        """添加一个加载中的占位符"""
        placeholder_label = QLabel(self.tr("Loading Recent..."))
        placeholder_label.setAlignment(Qt.AlignCenter)
        placeholder_label.setStyleSheet("color: gray; font-style: italic;")
        self.recent_canvas_layout.addWidget(placeholder_label)

    def _on_new_canvas_clicked(self):
        """处理“新建画布”点击事件"""
        if self.gallery_page and hasattr(self.gallery_page, 'new_canvas'):
            self.gallery_page.new_canvas(self.parent)
        else:
            print("Gallery page instance not available or 'new_canvas' method not found.")

    def _on_scan_finished(self, workflow_files: List[Path], file_info_map: Dict[str, dict]):
        """处理扫描完成信号"""
        print(f"[DEBUG] HomeInterface received scan_finished signal. Found {len(workflow_files)} files.")

        if not workflow_files or not self.gallery_page:
            # 如果列表为空或 gallery_page 不存在，添加一个提示
            hint_label = QLabel(self.tr("No Recent Canvas"))
            hint_label.setAlignment(Qt.AlignCenter)
            hint_label.setStyleSheet("color: gray; font-style: italic;")
            self.recent_canvas_layout.addWidget(hint_label)
            return

        sorted_paths = sorted(
            workflow_files,
            key=lambda p: file_info_map.get(str(p), {}).get('mtime_ts', 0),
            reverse=True
        )

        # 取最近的 3 个
        recent_paths = sorted_paths[:3]

        # 从 gallery_page 的 _card_map 中获取对应的卡片
        for wf_path in recent_paths:
            card = self.gallery_page._card_map.get(wf_path)
            self.recent_canvas_layout.addWidget(card)

        # 如果没有找到任何最近画布
        if not recent_paths:
             hint_label = QLabel(self.tr("No Recent Canvas"))
             hint_label.setAlignment(Qt.AlignCenter)
             hint_label.setStyleSheet("color: gray; font-style: italic;")
             self.recent_canvas_layout.addWidget(hint_label)

    def _on_open_canvas_clicked(self, path: Path):
        """处理打开画布事件"""
        if self.gallery_page and hasattr(self.gallery_page, 'open_canvas'):
            self.gallery_page.open_canvas(path)
        else:
            print(f"Gallery page instance not available or 'open_canvas' method not found. Path: {path}")


class HomeInterface(ScrollArea):
    """ Home interface """

    def __init__(self, parent=None, gallery_page_instance=None):
        super().__init__(parent=parent)
        self.banner = BannerWidget(self)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        self.__initWidget(gallery_page_instance) # 传递 gallery_page_instance

    def __initWidget(self, gallery_page_instance):
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

        # 创建 HorizontalCardContainerWidget 并传递 gallery_page_instance
        self.card_container = HorizontalCardContainerWidget(gallery_page_instance, self)
        self.vBoxLayout.addWidget(self.card_container)
