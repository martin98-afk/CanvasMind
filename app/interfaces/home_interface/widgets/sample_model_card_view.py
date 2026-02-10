# -*- coding: utf-8 -*-
from pathlib import Path

from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtWidgets import (QVBoxLayout, QLabel)
from qfluentwidgets import (
    FlowLayout, SimpleCardWidget
)

from app.interfaces.home_interface.widgets.stylish_card import StylishCard
from app.utils.utils import get_icon, resource_path


class SampleModelCardView(SimpleCardWidget):
    """ 示例模型 """
    openSampleSignal = pyqtSignal(str)

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("SimpleCardWidget { background-color: transparent; border: none; }")

        display_title = title if title else self.tr("示例模型 >")

        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(20, 10, 20, 10)

        self.titleLabel = QLabel(display_title)
        self.titleLabel.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold; margin-bottom: 8px;")

        self.contentLayout = FlowLayout()
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setHorizontalSpacing(16)
        self.contentLayout.setVerticalSpacing(16)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addLayout(self.contentLayout)

        # 定时器用于调整布局宽度
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self._recalc_width)

        self.examples = [
            {"icon": get_icon("AI音乐"), "title": self.tr("ACE-STEP1.5音乐生成"), "content": self.tr("使用ACE-STEP1.5模型生成AI音乐"),
             "key": "ace-step1.5"},
            {"icon": get_icon("多轮对话"), "title": self.tr("AI辩论赛"), "content": self.tr("大模型+TTS辩论"),
             "key": "AI辩论赛"},
            {"icon": get_icon("AI绘画"), "title": self.tr("AI扩图"), "content": self.tr("SD+超分图像扩充"),
             "key": "图像扩充模型"},
            {"icon": get_icon("智能视频"), "title": self.tr("WAN文图生视频"), "content": self.tr("基于comfyui使用wan模型进行文图生视频"),
             "key": "wan图生视频实例"},
            {"icon": get_icon("更新"), "title": self.tr("循环迭代"), "content": self.tr("循环/迭代节点用法"),
             "key": "循环、迭代样例模型"},
            {"icon": get_icon("逻辑回归A"), "title": self.tr("机器学习"), "content": self.tr("训练与推理流程"),
             "key": "机器学习算法样例模型"},
            {"icon": get_icon("智能体"), "title": self.tr("React Agent"), "content": self.tr("工具调用Agent"),
             "key": "react智能体"},
            {"icon": get_icon("HTTP请求"), "title": self.tr("HTTP请求"), "content": self.tr("http请求样例模型，包含请求体合并操作"),
             "key": "http请求样例模型"},
            {"icon": get_icon("图表"), "title": self.tr("ECharts图表"), "content": self.tr("使用echarts进行数据可视化分析"),
             "key": "echarts样例"},
        ]

        self.cards = []
        for ex in self.examples:
            card = StylishCard(ex["icon"], ex["title"], ex["content"], self)
            card.clicked.connect(lambda k=ex["key"]: self._on_open_sample(k))
            self.contentLayout.addWidget(card)
            self.cards.append(card)

    def _on_open_sample(self, model_name: str):
        target_path = Path(resource_path("examples")) / model_name / f"{model_name}.workflow.json"
        try:
            self.openSampleSignal.emit(str(target_path))
        except Exception as e:
            print(f"Error: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_timer.start(50)

    def _recalc_width(self):
        # 强制所有卡片宽度一致，避免参差不齐
        container_width = self.contentsRect().width() - self.vLayout.contentsMargins().left() - self.vLayout.contentsMargins().right()
        min_width = 260
        spacing = self.contentLayout.horizontalSpacing()
        cards_per_row = max(1, (container_width + spacing) // (min_width + spacing))
        target_width = (container_width - (cards_per_row - 1) * spacing) // cards_per_row

        for card in self.cards:
            card.setFixedWidth(target_width)