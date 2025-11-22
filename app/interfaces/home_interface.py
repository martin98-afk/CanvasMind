# -*- coding: utf-8 -*-
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import json
from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QBrush, QPixmap, QFont, QFontMetrics
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
from qfluentwidgets import (
    ScrollArea, FluentIcon, isDarkTheme, FlowLayout, MessageBox,
    PrimaryPushButton, PushButton, ComboBox, LineEdit, CardWidget,
    ToolButton, TitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel, ElevatedCardWidget, SimpleCardWidget
)
from qfluentwidgets.common.icon import FluentIconBase

from app.utils.utils import get_icon, resource_path
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.card_widget.home_card import HomeCardView, HomeCard
from app.widgets.card_widget.link_card import LinkCardView


class WelcomeBannerWidget(QWidget):
    """ 改进的欢迎横幅，包含标题、副标题和主要操作按钮，带有背景图片和渐变 """

    newCanvasSignal = pyqtSignal()
    openCanvasSignal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(350)
        # 加载背景图片
        self.bannerPixmap = QPixmap(resource_path('./icons/banner.png'))

        # 主布局
        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(40, 0, 40, 0)
        self.vLayout.setSpacing(20)

        # 标题区域
        self.titleLabel = TitleLabel("Welcome to CanvasMind")
        self.titleLabel.setAlignment(Qt.AlignCenter)

        self.subtitleLabel = BodyLabel("A modern low-code visual programming platform")
        self.subtitleLabel.setAlignment(Qt.AlignCenter)

        # 主要操作按钮区域
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addStretch(1)  # 左侧弹性空间
        self.newButton = PrimaryPushButton(FluentIcon.ADD, "新建画布")
        self.newButton.setFixedWidth(150)
        self.newButton.clicked.connect(self.newCanvasSignal.emit)

        self.openButton = PushButton(FluentIcon.FOLDER, "打开画布")
        self.openButton.setFixedWidth(150)
        self.openButton.clicked.connect(self._on_open_clicked)

        self.buttonLayout.addWidget(self.newButton)
        self.buttonLayout.addSpacing(10)
        self.buttonLayout.addWidget(self.openButton)
        self.buttonLayout.addStretch(1)  # 右侧弹性空间

        self.vLayout.addStretch(1)  # 上方弹性空间
        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addWidget(self.subtitleLabel)
        self.vLayout.addLayout(self.buttonLayout)
        self.vLayout.addStretch(1)  # 下方弹性空间

    def paintEvent(self, e):
        """绘制背景图片和渐变"""
        super().paintEvent(e)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        w, h = self.width(), self.height()
        path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        # 添加一些圆角矩形的变形，模拟你原设计中的效果
        path.addRect(QRectF(0, h - 50, 50, 50))
        path.addRect(QRectF(w - 50, 0, 50, 50))
        path.addRect(QRectF(w - 50, h - 50, 50, 50))
        path = path.simplified()

        # 初始化线性渐变效果
        gradient = QLinearGradient(0, 0, 0, h)

        # 绘制背景色渐变
        if not isDarkTheme():
            # 浅色主题渐变
            gradient.setColorAt(0, QColor(207, 216, 228, 255))
            gradient.setColorAt(1, QColor(207, 216, 228, 0))
        else:
            # 深色主题渐变 - 使用更深、更暗的色调
            # 可以尝试调整这些颜色值来达到你最喜欢的深色效果
            gradient.setColorAt(0, QColor(30, 30, 30, 255))  # 顶部颜色，更深
            gradient.setColorAt(1, QColor(20, 20, 20, 0))  # 底部颜色，几乎透明的黑

        painter.fillPath(path, QBrush(gradient))

        # 绘制背景图片
        if not self.bannerPixmap.isNull():
            # 缩放图片以适应控件大小
            scaledPixmap = self.bannerPixmap.scaled(
                self.size(),
                transformMode=Qt.SmoothTransformation
            )
            # 使用绘制的路径作为遮罩来填充图片，使其形状与渐变一致
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(self.rect(), scaledPixmap)
            painter.restore()

    def _on_open_clicked(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开工作流文件",
            "./",
            "CanvasMind Files (*.workflow.json);;All Files (*)"
        )
        if file_path:
            self.openCanvasSignal.emit(file_path)


class EnvironmentCardView(SimpleCardWidget):
    """ 环境管理区域，显示环境状态和操作按钮 """

    manageEnvSignal = pyqtSignal()
    addEnvSignal = pyqtSignal()

    def __init__(self, package_manager, title="环境管理 >", parent=None):
        super().__init__(parent)
        self.setBorderRadius(8)
        self.package_manager = package_manager
        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(16, 16, 16, 16)

        self.titleLabel = StrongBodyLabel(title)
        self.titleLabel.setObjectName("EnvironmentTitle")

        self.contentLayout = FlowLayout()
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setHorizontalSpacing(12)
        self.contentLayout.setVerticalSpacing(12)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addLayout(self.contentLayout)
        StyleSheet.SAMPLE_CARD.apply(self)
        # 初始更新环境卡片
        self._update_env_cards()

    def _update_env_cards(self):
        """根据环境数量更新卡片内容"""
        # 清除现有内容
        for i in reversed(range(self.contentLayout.count())):
            item = self.contentLayout.itemAt(i)
            if item.widget():
                widget_to_remove = item.widget()
                self.contentLayout.removeWidget(widget_to_remove)
                widget_to_remove.setParent(None)
                widget_to_remove.deleteLater()

        # 根据环境数量添加卡片
        if self.package_manager.envCombo.count() == 0:
            add_card = HomeCard(
                icon=get_icon("惊叹号"),  # 使用惊叹号图标
                title="新建环境",
                content="当前没有任何运行环境，请先新建运行环境",
                routeKey="env_add",
                index=0,
                triggered=self.addEnvSignal.emit,
                parent=self
            )
            self.contentLayout.addWidget(add_card)
        else:
            add_card = HomeCard(
                icon=FluentIcon.ADD,  # 使用加号图标
                title="新建环境",
                content="创建新的画布运行环境",
                routeKey="env_add",
                index=0,
                triggered=self.addEnvSignal.emit,
                parent=self
            )
            self.contentLayout.addWidget(add_card)

        manage_card = HomeCard(
            icon=FluentIcon.SETTING,
            title="环境管理",
            content="管理已有的画布运行环境",
            routeKey="env_manage",
            index=1,
            triggered=self.manageEnvSignal.emit,
            parent=self
        )
        self.contentLayout.addWidget(manage_card)

    def update_cards_on_env_change(self):
        """响应环境变化信号，更新卡片"""
        self._update_env_cards()


class QuickStartCardView(SimpleCardWidget):
    """ 快速开始区域，展示最近打开的文件，自适应数量 """

    openFileSignal = pyqtSignal(str)

    def __init__(self, title="最近编辑", parent=None):
        super().__init__(parent)
        self.setBorderRadius(8)
        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(16, 16, 16, 16)

        self.titleLabel = StrongBodyLabel(title)
        self.titleLabel.setObjectName("QuickStartTitle")

        self.contentLayout = FlowLayout()
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setHorizontalSpacing(12)
        self.contentLayout.setVerticalSpacing(12)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addLayout(self.contentLayout)
        StyleSheet.SAMPLE_CARD.apply(self)
        # 用于存储最近文件卡片的引用
        self.recent_cards = []

    def update_recent_files(self, workflow_files: List[Path], file_info_map: Dict[str, dict]):
        """更新最近文件列表，自适应数量"""
        # 清除旧的卡片
        for card in self.recent_cards:
            self.contentLayout.removeWidget(card)
            card.deleteLater()
        self.recent_cards.clear()

        if not workflow_files:
            return

        # 按修改时间排序
        sorted_paths = sorted(
            workflow_files,
            key=lambda p: file_info_map.get(str(p), {}).get('mtime_ts', 0),
            reverse=True
        )

        # --- 关键修改：自适应数量 ---
        estimated_card_width = 300 + self.contentLayout.horizontalSpacing() # 卡片宽度 + 右侧间距
        available_width = self.contentLayout.geometry().width() or self.width() - 2 * self.vLayout.contentsMargins().left()
        if available_width <= 0:
             # 如果 geometry.width() 无效，尝试用 parent widget 的宽度估算
             parent_width = self.parent().width() if self.parent() else 800 # 假设默认宽度
             available_width = parent_width - 2 * self.vLayout.contentsMargins().left() - 10 # 减去一些边距

        cards_per_row = max(1, available_width // estimated_card_width)
        # 假设我们最多展示 2 行，可以根据需要调整
        max_cards_to_show = max(cards_per_row * 2, 6)

        # 取需要展示的数量
        paths_to_show = sorted_paths[:max_cards_to_show]
        # --- 结束修改 ---

        for wf_path in paths_to_show:
            card_info = file_info_map.get(str(wf_path), {})
            card_title = card_info.get('title', wf_path.stem.split(".")[0])
            card_content = f"修改于: {datetime.fromtimestamp(card_info.get('mtime_ts', 0)).strftime('%m-%d %H:%M')}"

            card = HomeCard(
                icon=get_icon("画布"),
                title=card_title,
                content=card_content,
                routeKey="open_recent",
                index=hash(str(wf_path)) % 1000000,
                triggered=lambda p=wf_path: self.openFileSignal.emit(str(p)),
                parent=self
            )
            self.contentLayout.addWidget(card)
            self.recent_cards.append(card)


class SampleModelCardView(SimpleCardWidget):
    """ 示例模型区域，展示官方示例 """

    openSampleSignal = pyqtSignal(str)

    def __init__(self, title="示例模型", parent=None):
        super().__init__(parent)
        self.setBorderRadius(8)
        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(16, 16, 16, 16)

        self.titleLabel = StrongBodyLabel(title)
        self.titleLabel.setObjectName("SampleModelTitle")

        self.contentLayout = FlowLayout()
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setHorizontalSpacing(12)
        self.contentLayout.setVerticalSpacing(12)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addLayout(self.contentLayout)
        StyleSheet.SAMPLE_CARD.apply(self)
        # 添加示例卡片
        examples = [
            {"icon": get_icon("大模型"), "title": "自动组件生成", "content": "使用智能体自动生成组件",
             "key": "自动组件生成"},
            {"icon": get_icon("更新"), "title": "循环迭代样例", "content": "循环、迭代节点使用方法",
             "key": "循环、迭代样例模型"},
            {"icon": get_icon("逻辑回归A"), "title": "机器学习样例", "content": "常见机器学习流程",
             "key": "机器学习算法样例模型"},
            {"icon": get_icon("智能体"), "title": "React智能体", "content": "工具调用智能体样例",
             "key": "react智能体"},
        ]

        for i, ex in enumerate(examples):
            card = HomeCard(
                icon=ex["icon"],
                title=ex["title"],
                content=ex["content"],
                routeKey="open_sample",
                index=i,
                triggered=lambda k=ex["key"]: self._on_open_sample(k),
                parent=self
            )
            self.contentLayout.addWidget(card)

    def _on_open_sample(self, model_name: str):
        target_path = Path(resource_path("examples")) / f"{model_name}.workflow.json"
        try:
            self.openSampleSignal.emit(str(target_path))
        except Exception as e:
            print(f"复制示例文件失败: {e}")


class ResourceLinkCardView(CardWidget):
    """ 资源链接区域，提供外部链接 """

    def __init__(self, title="资源与支持", parent=None):
        super().__init__(parent)
        self.setBorderRadius(8)
        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(16, 16, 16, 16)

        self.titleLabel = StrongBodyLabel(title)
        self.titleLabel.setObjectName("ResourceLinkTitle")

        self.linkCardView = LinkCardView(self)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addWidget(self.linkCardView)

        self.linkCardView.addCard(
            FluentIcon.GITHUB,
            "项目地址",
            "获取最新更新及版本信息",
            "https://github.com/martin98-afk/CanvasMind"
        )

        self.linkCardView.addCard(
            get_icon("logo3"),
            "使用指南",
            "功能清单及使用方法演示",
            "https://canvasmind-sphinx-build.readthedocs.io/zh-cn/latest/"
        )

        self.linkCardView.addCard(
            FluentIcon.CODE,
            "流程图样例",
            "获取官方画布样例文件",
            "https://github.com/martin98-afk/CanvasMind/tree/master/examples"
        )

        self.linkCardView.addCard(
            FluentIcon.FEEDBACK,
            "反馈意见",
            "帮助我们改善 Canvas Mind",
            "https://github.com/martin98-afk/CanvasMind/issues/new"
        )


class HomeInterface(ScrollArea):
    """ 改进的主页界面 """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.home = parent
        self.workflow_manager = parent.workflow_manager
        # 注意：这里假设 parent.package_manager 指向的是包含 envCombo 和 env_changed 信号的组件管理页面
        self.package_manager = parent.package_manager

        self.setObjectName('homeInterface')
        # 确保应用样式表
        StyleSheet.HOME_INTERFACE.apply(self)

        # 设置滚动区域
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)

        # 主内容 Widget
        self.view = QWidget()
        # --- 关键修改：设置 view 背景 ---
        # 主内容 view 的背景色也应与深色主题一致
        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(24, 24, 24, 24)
        self.vBoxLayout.setSpacing(0)

        # 设置 view 的背景色
        if isDarkTheme():
            # 如果样式表或主题没有自动应用，可以尝试手动设置
            self.view.setStyleSheet("background-color: transparent;")  # 依赖父级或全局主题
            # 或者设置一个具体的深色
            # self.view.setStyleSheet("background-color: #1E1E1E;") # 示例深色
        # --- 结束修改 ---

        # 1. 横幅
        self.banner = WelcomeBannerWidget()
        self.banner.newCanvasSignal.connect(self._on_new_canvas_clicked)
        self.banner.openCanvasSignal.connect(self._on_open_canvas_clicked)

        # 2. 卡片容器
        self.cardContainer = QWidget()
        self.cardLayout = QVBoxLayout(self.cardContainer)
        self.cardLayout.setSpacing(16)

        # 2.1 环境管理卡片 (新增)
        self.environmentCard = EnvironmentCardView(self.package_manager, title="环境管理 >", parent=self)
        self.environmentCard.manageEnvSignal.connect(lambda: self.home.switchTo(self.package_manager))
        self.environmentCard.addEnvSignal.connect(
            lambda: self.package_manager.create_env(self))  # 假设 create_env 在 package_manager 上

        # 2.2 快速开始卡片
        self.quickStartCard = QuickStartCardView("最近编辑 >", self)
        self.quickStartCard.openFileSignal.connect(self._on_open_canvas_clicked)

        # 2.3 示例模型卡片
        self.sampleModelCard = SampleModelCardView("示例模型 >", self)
        self.sampleModelCard.openSampleSignal.connect(self._on_open_canvas_clicked)

        # 2.4 资源链接卡片
        self.resourceLinkCard = ResourceLinkCardView("资源与支持 >")

        # --- 关键修改：根据环境数量动态调整卡片顺序 ---
        if self.package_manager.envCombo.count() == 0:
            # 没有环境时，环境管理卡片放在第一个
            self.cardLayout.addWidget(self.environmentCard)
            self.cardLayout.addWidget(self.quickStartCard)
            self.cardLayout.addWidget(self.sampleModelCard)
            self.cardLayout.addWidget(self.resourceLinkCard)
        else:
            # 有环境时，环境管理卡片放在示例模型之后，资源支持之前
            self.cardLayout.addWidget(self.quickStartCard)
            self.cardLayout.addWidget(self.sampleModelCard)
            self.cardLayout.addWidget(self.environmentCard)
            self.cardLayout.addWidget(self.resourceLinkCard)
        # --- 结束修改 ---

        # 将组件添加到主布局
        self.vBoxLayout.addWidget(self.banner)
        self.vBoxLayout.addWidget(self.cardContainer)

        self.setWidget(self.view)

        # 连接信号
        if self.workflow_manager and hasattr(self.workflow_manager, 'scan_finished'):
            self.workflow_manager.scan_finished.connect(self._on_scan_finished)
        # 连接环境变化信号
        if self.package_manager and hasattr(self.package_manager, 'env_changed'):
            self.package_manager.env_changed.connect(self.environmentCard.update_cards_on_env_change)

    # --- 关键修改：重写 paintEvent 强制背景 ---
    def paintEvent(self, event):
        """强制绘制深色背景，以防样式表未生效"""
        if isDarkTheme():
            painter = QPainter(self.viewport())  # 在视口上绘制
            painter.fillRect(self.rect(), QColor(30, 30, 30))  # 绘制一个深灰色背景
        super().paintEvent(event)  # 调用父类的 paintEvent

    # --- 结束修改 ---

    def _on_new_canvas_clicked(self):
        """处理“新建画布”点击事件"""
        if self.workflow_manager and hasattr(self.workflow_manager, 'new_canvas'):
            self.workflow_manager.new_canvas(self)

    def _on_open_canvas_clicked(self, file_path: str):
        """处理“打开画布”点击事件"""
        if self.workflow_manager and hasattr(self.workflow_manager, 'open_canvas'):
            self.workflow_manager.open_canvas(Path(file_path))

    def _on_scan_finished(self, workflow_files: List[Path], file_info_map: Dict[str, dict]):
        """处理扫描完成信号，更新最近文件列表"""
        self.quickStartCard.update_recent_files(workflow_files, file_info_map)