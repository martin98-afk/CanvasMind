# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import FluentIcon, SimpleCardWidget

from app.interfaces.home_interface.widgets.stylish_card import StylishCard
from app.utils.utils import get_icon, get_unified_font


class EnvironmentCardView(SimpleCardWidget):
    """环境管理"""

    manageEnvSignal = pyqtSignal()
    addEnvSignal = pyqtSignal()

    def __init__(self, package_manager, title=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "SimpleCardWidget { background-color: transparent; border: none; }"
        )

        display_title = title if title else self.tr("环境管理 >")
        self.package_manager = package_manager

        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(20, 10, 20, 10)

        self.titleLabel = QLabel(display_title)
        self.titleLabel.setFont(get_unified_font(18, True))
        self.titleLabel.setStyleSheet("color: #FFFFFF; margin-bottom: 8px;")

        self.contentLayout = (
            QHBoxLayout()
        )  # 环境卡片少，用HBox或者Flow都行，这里用HBox固定显示
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setSpacing(16)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addLayout(self.contentLayout)
        self._update_env_cards()

    def _update_env_cards(self):
        while self.contentLayout.count():
            item = self.contentLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 新建卡片
        if self.package_manager.envCombo.count() == 0:
            add_card = StylishCard(
                get_icon("惊叹号"),
                self.tr("新建环境"),
                self.tr("无运行环境，请新建"),
                self,
            )
        else:
            add_card = StylishCard(
                FluentIcon.ADD, self.tr("新建环境"), self.tr("创建新环境"), self
            )
        add_card.clicked.connect(self.addEnvSignal.emit)

        # 管理卡片
        manage_card = StylishCard(
            FluentIcon.SETTING, self.tr("环境管理"), self.tr("管理已有环境"), self
        )
        manage_card.clicked.connect(self.manageEnvSignal.emit)

        self.contentLayout.addWidget(add_card)
        self.contentLayout.addWidget(manage_card)

    def update_cards_on_env_change(self):
        self._update_env_cards()
