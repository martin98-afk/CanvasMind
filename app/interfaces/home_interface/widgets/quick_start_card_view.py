# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtWidgets import (QVBoxLayout, QLabel)
from qfluentwidgets import (
    FlowLayout, SimpleCardWidget
)

from app.interfaces.home_interface.widgets.stylish_card import StylishCard
from app.utils.utils import get_icon


class QuickStartCardView(SimpleCardWidget):
    """ 快速开始区域 (自适应布局) """
    openFileSignal = pyqtSignal(str)

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("SimpleCardWidget { background-color: transparent; border: none; }")

        display_title = title if title else self.tr("最近编辑 >")

        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(20, 10, 20, 10)

        # 标题栏样式
        self.titleLabel = QLabel(display_title)
        self.titleLabel.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold; margin-bottom: 8px;")

        self.contentLayout = FlowLayout()
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setHorizontalSpacing(16)
        self.contentLayout.setVerticalSpacing(16)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addLayout(self.contentLayout)

        self.all_cards: List[StylishCard] = []
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self._perform_layout)

    def update_recent_files(self, workflow_files: List[Path], file_info_map: Dict[str, dict]):
        # 清空
        for card in self.all_cards:
            self.contentLayout.removeWidget(card)
            card.deleteLater()
        self.all_cards.clear()

        if not workflow_files:
            return

        sorted_paths = sorted(
            workflow_files,
            key=lambda p: file_info_map.get(str(p), {}).get('mtime_ts', 0),
            reverse=True
        )

        for wf_path in sorted_paths[:30]:
            card_info = file_info_map.get(str(wf_path), {})
            card_title = card_info.get('title', wf_path.stem.split(".")[0])
            time_str = datetime.fromtimestamp(card_info.get('mtime_ts', 0)).strftime('%m-%d %H:%M')
            card_content = f"{self.tr('修改于')}: {time_str}"

            # 使用 StylishCard
            card = StylishCard(
                icon=get_icon("画布"),
                title=card_title,
                content=card_content,
                parent=self
            )
            card.clicked.connect(lambda p=wf_path: self.openFileSignal.emit(str(p)))

            card.setVisible(False)
            self.contentLayout.addWidget(card)
            self.all_cards.append(card)

        self._perform_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_timer.start(50)

    def _perform_layout(self):
        if not self.all_cards: return

        container_width = self.contentsRect().width() - self.vLayout.contentsMargins().left() - self.vLayout.contentsMargins().right()
        # StylishCard 宽度是自适应的，但我们需要给个参考值来算一行放几个
        # 假设最小宽度 260
        min_width = 260
        spacing = self.contentLayout.horizontalSpacing()

        cards_per_row = max(1, (container_width + spacing) // (min_width + spacing))

        # 显示2行
        visible_count = cards_per_row * 2

        for i, card in enumerate(self.all_cards):
            is_visible = i < visible_count
            card.setVisible(is_visible)
            # 强制每个卡片根据行数平分宽度，保证整齐
            if is_visible:
                # 计算精确宽度
                target_width = (container_width - (cards_per_row - 1) * spacing) // cards_per_row
                card.setFixedWidth(target_width)