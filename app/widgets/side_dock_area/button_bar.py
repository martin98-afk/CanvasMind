# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from qfluentwidgets import TransparentToolButton

from app.widgets.side_dock_area.registry import SideDockRegistry


class DraggableTabWidget(QTabWidget):
    def __init__(self, dock_area, position="top"):
        super().__init__()
        self.dock_area = dock_area
        self.position = position
        self.setMovable(True)
        self.setTabsClosable(False)

    def tabRemoved(self, index):
        if self.count() == 0 and self.position == "bottom":
            self.dock_area.hide_bottom()


class SideDockButtonBar(QWidget):
    def __init__(self, dock_area):
        super().__init__(dock_area)
        self.dock_area = dock_area
        self.setFixedWidth(36)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(4)
        self.layout.setContentsMargins(4, 8, 4, 8)
        self.buttons = []
        self._create_buttons()

    def _create_buttons(self):
        registry = SideDockRegistry.get_all()
        for name, cls in registry.items():
            btn = TransparentToolButton(cls.icon, self)
            btn.setToolTip(cls.name)
            btn.clicked.connect(lambda _, n=name: self._activate_tab(n))
            self.layout.addWidget(btn)
            self.buttons.append(btn)
        self.layout.addStretch()

    def _activate_tab(self, name):
        # 切换到对应 tab（需在 tab widget 中实现）
        pass