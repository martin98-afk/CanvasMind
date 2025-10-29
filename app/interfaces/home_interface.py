# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import requests
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QBrush, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from qfluentwidgets import ScrollArea, FluentIcon, isDarkTheme, FlowLayout

from app.utils.utils import get_icon, resource_path
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.card_widget.home_card import HomeCardView, HomeCard
from app.widgets.card_widget.link_card import LinkCardView


EXAMPLES = {
    "自动组件生成": "https://raw.githubusercontent.com/martin98-afk/CanvasMind/refs/heads/master/workflows/%E8%87%AA%E5%8A%A8%E7%BB%84%E4%BB%B6%E7%94%9F%E6%88%90.workflow.json",
    "循环、迭代样例模型": "https://raw.githubusercontent.com/martin98-afk/CanvasMind/refs/heads/master/workflows/%E5%BE%AA%E7%8E%AF%E3%80%81%E8%BF%AD%E4%BB%A3%E6%A0%B7%E4%BE%8B%E6%A8%A1%E5%9E%8B.workflow.json",
    "机器学习算法样例模型": "https://raw.githubusercontent.com/martin98-afk/CanvasMind/refs/heads/master/workflows/workflow.workflow.json",
    "react工具调用智能体": "https://raw.githubusercontent.com/martin98-afk/CanvasMind/refs/heads/master/workflows/react%E6%99%BA%E8%83%BD%E4%BD%93.workflow.json"
}

class BannerWidget(QWidget):
    """ Banner widget """

    def __init__(self, parent=None):
        super().__init__(parent=parent) # 必须首先调用父类构造函数
        self.setFixedHeight(336)

        self.vBoxLayout = QVBoxLayout(self)
        self.galleryLabel = QLabel('Canvas Mind', self)
        self.banner = QPixmap(resource_path('./icons/banner.png'))
        self.linkCardView = LinkCardView(self)

        self.galleryLabel.setObjectName('galleryLabel')

        self.vBoxLayout.setSpacing(20)
        self.vBoxLayout.setContentsMargins(0, 20, 0, 0)
        self.vBoxLayout.addWidget(self.galleryLabel)
        self.vBoxLayout.addWidget(self.linkCardView, Qt.AlignCenter)
        self.vBoxLayout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.linkCardView.addCard(
            get_icon("logo3"),
            self.tr('Getting started'),
            self.tr('An overview of app development options and samples.'),
            "https://martin98-afk.github.io/CanvasMind"
        )

        self.linkCardView.addCard(
            FluentIcon.GITHUB,
            self.tr('GitHub repo'),
            self.tr(
                'The latest fluent design controls and styles for your applications.'),
            "https://github.com/martin98-afk/CanvasMind"
        )

        self.linkCardView.addCard(
            FluentIcon.CODE,
            self.tr('Code samples'),
            self.tr(
                'Find samples that demonstrate specific tasks, features and APIs.'),
            "https://github.com/martin98-afk/CanvasMind/tree/master/workflows"
        )

        self.linkCardView.addCard(
            FluentIcon.FEEDBACK,
            self.tr('Send feedback'),
            self.tr('Help us improve Canvas Mind by providing feedback.'),
            "https://github.com/martin98-afk/CanvasMind/issues/new"
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
    def __init__(self, gallery_page_instance, package_page, parent=None, home=None):
        super().__init__(parent)  # 首先调用父类 ScrollArea 构造函数
        self.parent_ref = parent
        self.home = home
        self.gallery_page = gallery_page_instance
        self.package_page = package_page
        # --- 保存卡片引用以便后续更新 ---
        self.envAddCard = None
        # 设置滚动区域
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # --- 创建内容 Widget 和 FlowLayout ---
        self.view = QWidget(self)
        self.flowLayout = FlowLayout(self.view)
        self.setStyleSheet("background-color: transparent; border: none;")
        self.flowLayout.setContentsMargins(24, 24, 24, 24)
        self.flowLayout.setHorizontalSpacing(24)
        self.flowLayout.setVerticalSpacing(24)

        # --- 创建三个卡片并添加到 FlowLayout ---
        self.quickStartCard = HomeCardView(self.tr("快速开始 >"), self.view)

        self.quickStartCard.addSampleCard(
            icon=FluentIcon.ADD,
            title=self.tr("新建画布"),
            content=self.tr("快速新建一个工作流画布"),
            routeKey="new_canvas",
            index=0,
            triggered=self._on_new_canvas_clicked
        )

        self.sampleModelCard = HomeCardView(self.tr("样例模型 >"), self.view)

        self.sampleModelCard.addSampleCard(
            icon=get_icon("大模型"),
            title=self.tr("自动组件生成"),
            content=self.tr("使用智能体和大模型自动生成画布组件"),
            routeKey="component_generate",
            index=0,
            triggered=lambda: self._on_open_sample_canvas_clicked("自动组件生成")
        )
        self.sampleModelCard.addSampleCard(
            icon=get_icon("更新"),
            title=self.tr("循环、迭代样例模型"),
            content=self.tr("循环、迭代节点使用方法样例模型"),
            routeKey="loop_example",
            index=1,
            triggered=lambda: self._on_open_sample_canvas_clicked("循环、迭代样例模型")
        )
        self.sampleModelCard.addSampleCard(
            icon=get_icon("逻辑回归A"),
            title=self.tr("机器学习算法样例模型"),
            content=self.tr("常见机器学习流程画布样例模型"),
            routeKey="machine_learning",
            index=1,
            triggered=lambda: self._on_open_sample_canvas_clicked("机器学习算法样例模型")
        )
        self.sampleModelCard.addSampleCard(
            icon=get_icon("智能体"),
            title=self.tr("react工具调用智能体"),
            content=self.tr("使用导出的项目作为工具的大模型智能体样例模型"),
            routeKey="react_agent",
            index=1,
            triggered=lambda: self._on_open_sample_canvas_clicked("react工具调用智能体")
        )

        # --- 初始化环境卡片 ---
        self.envEditCard = HomeCardView(self.tr("环境管理 >"), self.view)
        self._update_env_card()  # 调用更新方法

        self.flowLayout.addWidget(self.quickStartCard)
        self.flowLayout.addWidget(self.sampleModelCard)
        self.flowLayout.addWidget(self.envEditCard)

        self.setWidget(self.view)

    def _update_env_card(self):
        """根据当前环境列表状态更新环境卡片内容"""
        # 移除旧的“新建环境”卡片（如果存在）
        for i in reversed(range(self.envEditCard.flowLayout.count())):
            item = self.envEditCard.flowLayout.itemAt(i)
            if item.widget():
                widget_to_remove = item.widget()
                self.envEditCard.flowLayout.removeWidget(widget_to_remove)
                widget_to_remove.setParent(None)  # 从父控件中移除，使其被销毁
        # 根据当前环境数量创建新的卡片
        if self.package_page.envCombo.count() == 0:
            self.envAddCard = self.envEditCard.addSampleCard(
                icon=get_icon("惊叹号"),  # 使用惊叹号图标
                title=self.tr("新建环境"),
                content=self.tr("当前没有任何运行环境，请先新建运行环境"),
                routeKey="env_edit",
                index=0,
                triggered=self._on_env_add_clicked
            )
        else:
            self.envAddCard = self.envEditCard.addSampleCard(
                icon=FluentIcon.ADD,  # 使用加号图标
                title=self.tr("新建环境"),
                content=self.tr("创建画布运行环境"),  # 更新描述文字
                routeKey="env_edit",
                index=0,
                triggered=self._on_env_add_clicked
            )

        # 重新添加“环境管理”卡片
        self.envManageCard = self.envEditCard.addSampleCard(
            icon=FluentIcon.SETTING,
            title=self.tr("环境管理"),
            content=self.tr("管理画布运行环境"),
            routeKey="env_manage",  # 修改 routeKey 以便区分
            index=1,  # index 也需要区分
            triggered=lambda: self.home.switchTo(self.package_page)
        )

    def _on_scan_finished(self, workflow_files: List[Path], file_info_map: Dict[str, dict]):
        """处理扫描完成信号，添加最近的画布卡片到快速开始区域"""

        if not workflow_files:
            return

        # --- 关键：清除之前添加的“最近项目”卡片 ---
        # 假设我们给动态添加的卡片设置一个特定的 objectName
        for i in reversed(range(self.quickStartCard.flowLayout.count())):
            item = self.quickStartCard.flowLayout.itemAt(i)
            if item.widget() and item.widget().objectName() == "recent_workflow_card":
                widget_to_remove = item.widget()
                self.quickStartCard.flowLayout.removeWidget(widget_to_remove)
                widget_to_remove.setParent(None)  # 从父控件中移除，使其被销毁

        # 按修改时间排序，获取最近的 3 个
        sorted_paths = sorted(
            workflow_files,
            key=lambda p: file_info_map.get(str(p), {}).get('mtime_ts', 0),
            reverse=True
        )
        recent_paths = sorted_paths[:3]

        for wf_path in recent_paths:
            card_info = file_info_map.get(str(wf_path), {})
            card_title = card_info.get('title', wf_path.stem.split(".")[0])
            card_content = f"最后修改时间: {datetime.fromtimestamp(card_info.get('mtime_ts', 0)).strftime('%Y-%m-%d %H:%M:%S')}"

            # 创建新的 HomeCard 实例，绑定打开对应文件的事件
            new_card = HomeCard(
                icon=get_icon("画布"),  # 或者根据 wf_path 获取的类型设置图标
                title=card_title,
                content=card_content,
                routeKey="open_recent",
                index=hash(str(wf_path)) % 1000000,
                triggered=lambda p=wf_path: self._on_open_canvas_clicked(p),
                parent=self.quickStartCard  # 设置父控件为 HomeCardView
            )
            # --- 关键：设置 objectName 以便后续识别和清除 ---
            new_card.setObjectName("recent_workflow_card")
            self.quickStartCard.flowLayout.addWidget(new_card)

    def _on_new_canvas_clicked(self):
        """处理“新建画布”点击事件"""
        if self.gallery_page and hasattr(self.gallery_page, 'new_canvas'):
            self.gallery_page.new_canvas(self.parent_ref)

    def _on_env_add_clicked(self):
        """处理“环境管理”点击事件"""
        if hasattr(self.package_page, 'create_env'):
            self.package_page.create_env(self.parent_ref)

    def _on_open_canvas_clicked(self, model_name: str):
        """处理打开画布事件"""
        if self.gallery_page and hasattr(self.gallery_page, 'open_canvas'):
            self.gallery_page.open_canvas(Path(model_name))

    def _on_open_sample_canvas_clicked(self, model_name: str):
        """处理打开画布事件"""
        try:
            output_path = f"./workflows/{model_name}.workflow.json"
            response = requests.get(EXAMPLES.get(model_name))
            response.raise_for_status()  # 如果响应状态码不是 200，将抛出 HTTPError
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"✅ 文件已成功下载到 {output_path}")
        except requests.exceptions.RequestException as e:
            print(f"❌ 下载失败: {e}")
        if self.gallery_page and hasattr(self.gallery_page, 'open_canvas'):
            self.gallery_page.open_canvas(Path(output_path))


class HomeInterface(ScrollArea):
    """ Home interface """

    def __init__(self, parent=None):
        super().__init__(parent=parent) # 必须首先调用父类构造函数
        self.home = parent
        self.banner = BannerWidget(self)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        self.workflow_manager = parent.workflow_manager
        self.package_manager = parent.package_manager
        self.__initWidget() # 传递 gallery_page_instance

    def __initWidget(self):
        self.view.setObjectName('view')
        self.setObjectName('homeInterface')
        StyleSheet.HOME_INTERFACE.apply(self)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(self.view)
        self.setWidgetResizable(True)

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.banner)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

        # 创建 HorizontalCardContainerWidget 并传递 gallery_page_instance
        self.card_container = HorizontalCardContainerWidget(self.workflow_manager, self.package_manager, self, self.home)
        self.vBoxLayout.addWidget(self.card_container)

        # 确保 gallery_page_instance 有 scan_finished 信号，并且参数匹配
        if self.workflow_manager and hasattr(self.workflow_manager, 'scan_finished'):
            self.workflow_manager.scan_finished.connect(self.card_container._on_scan_finished)
        if hasattr(self.package_manager, 'env_changed'):
            self.package_manager.env_changed.connect(self.card_container._update_env_card)