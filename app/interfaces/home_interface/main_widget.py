# -*- coding: utf-8 -*-
from pathlib import Path
from typing import List, Dict

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QGraphicsOpacityEffect,
                             QOpenGLWidget)
from qfluentwidgets import (
    ScrollArea, setTheme, Theme
)

from app.interfaces.home_interface.widgets.environment_car_view import EnvironmentCardView
from app.interfaces.home_interface.widgets.quick_start_card_view import QuickStartCardView
from app.interfaces.home_interface.widgets.resource_link_card_view import ResourceLinkCardView
from app.interfaces.home_interface.widgets.sample_model_card_view import SampleModelCardView
from app.interfaces.home_interface.widgets.welecome_banner import WelcomeBannerWidget


class HomeInterface(ScrollArea):
    """ 主界面 """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.home = parent

        # 强制深色
        setTheme(Theme.DARK)
        self.setViewport(QOpenGLWidget())
        self.workflow_manager = getattr(parent, 'workflow_manager', None)
        self.package_manager = getattr(parent, 'package_manager', None)

        self.setObjectName('homeInterface')
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)

        # 全局背景：深色纯色 #1e1e1e (比卡片 #2b2b2b 略深，形成层次)
        self.setStyleSheet("""
            HomeInterface, #HomeInterface, QScrollArea, QWidget#HomeView {
                background-color: #1e1e1e;
                border: none;
            }
        """)

        self.view = QWidget()
        self.view.setObjectName("HomeView")

        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(40, 40, 40, 40)
        self.vBoxLayout.setSpacing(32)  # 模块间距加大

        # 1. 横幅
        self.banner = WelcomeBannerWidget()
        self.banner.newCanvasSignal.connect(self._on_new_canvas_clicked)
        self.banner.openCanvasSignal.connect(self._on_open_canvas_clicked)

        # 2. 容器
        self.cardContainer = QWidget()
        self.cardContainer.setStyleSheet("background-color: transparent;")
        self.cardLayout = QVBoxLayout(self.cardContainer)
        self.cardLayout.setSpacing(24)  # 各个栏目间距
        self.cardLayout.setContentsMargins(0, 0, 0, 0)

        # 初始化模块
        self.environmentCard = EnvironmentCardView(self.package_manager, self.tr("环境管理 >"), parent=self)
        self.environmentCard.manageEnvSignal.connect(lambda: self.home.switchTo(self.package_manager))
        self.environmentCard.addEnvSignal.connect(lambda: self.package_manager.create_env(self))

        self.quickStartCard = QuickStartCardView(self.tr("最近编辑 >"), self)
        self.quickStartCard.openFileSignal.connect(self._on_open_canvas_clicked)

        self.sampleModelCard = SampleModelCardView(self.tr("示例模型 >"), self)
        self.sampleModelCard.openSampleSignal.connect(self._on_open_canvas_clicked)

        self.resourceLinkCard = ResourceLinkCardView(self.tr("资源与支持 >"))

        self._arrange_cards()

        self.vBoxLayout.addWidget(self.banner)
        self.vBoxLayout.addWidget(self.cardContainer)
        self.setWidget(self.view)

        # 信号
        if self.workflow_manager and hasattr(self.workflow_manager, 'scan_finished'):
            self.workflow_manager.scan_finished.connect(self._on_scan_finished)
        if self.package_manager and hasattr(self.package_manager, 'env_changed'):
            self.package_manager.env_changed.connect(self.environmentCard.update_cards_on_env_change)
            self.package_manager.env_changed.connect(self._arrange_cards)

        # 进场动画
        self.opacityEffect = QGraphicsOpacityEffect(self.view)
        self.view.setGraphicsEffect(self.opacityEffect)
        self.opacityAni = QPropertyAnimation(self.opacityEffect, b"opacity", self)
        self.opacityAni.setStartValue(0)
        self.opacityAni.setEndValue(1)
        self.opacityAni.setDuration(500)
        self.opacityAni.setEasingCurve(QEasingCurve.OutCubic)
        self.opacityAni.start()

    def _arrange_cards(self):
        for i in reversed(range(self.cardLayout.count())):
            self.cardLayout.takeAt(i)

        has_env = self.package_manager.envCombo.count() > 0
        if not has_env:
            self.cardLayout.addWidget(self.environmentCard)
            self.cardLayout.addWidget(self.quickStartCard)
            self.cardLayout.addWidget(self.sampleModelCard)
        else:
            self.cardLayout.addWidget(self.quickStartCard)
            self.cardLayout.addWidget(self.sampleModelCard)
            self.cardLayout.addWidget(self.environmentCard)
        self.cardLayout.addWidget(self.resourceLinkCard)

    def _on_new_canvas_clicked(self):
        if self.workflow_manager:
            self.workflow_manager.new_canvas(self)

    def _on_open_canvas_clicked(self, file_path: str):
        if self.workflow_manager:
            self.workflow_manager.open_canvas(Path(file_path))

    def _on_scan_finished(self, workflow_files: List[Path], file_info_map: Dict[str, dict]):
        self.quickStartCard.update_recent_files(workflow_files, file_info_map)