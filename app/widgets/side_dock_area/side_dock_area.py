# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QSplitter, QTabWidget
from PyQt5.QtCore import Qt
from .registry import SideDockRegistry
from .button_bar import SideDockButtonBar

class SideDockArea(QWidget):
    def __init__(self, canvas_page):
        super().__init__()
        self.canvas_page = canvas_page
        self.splitter = QSplitter(Qt.Vertical)
        self.top_tab = DraggableTabWidget(self, "top")
        self.bottom_tab = DraggableTabWidget(self, "bottom")
        self.splitter.addWidget(self.top_tab)
        self.splitter.addWidget(self.bottom_tab)
        self.splitter.setSizes([300, 100])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setHandleWidth(6)

        self.button_bar = SideDockButtonBar(self)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.splitter)

        self._load_plugins()

    def _load_plugins(self):
        registry = SideDockRegistry.get_all()
        for name, cls in registry.items():
            widget = cls(self.canvas_page)
            self.top_tab.add_draggable_tab(widget, name, cls.icon)

        # 初始隐藏底部
        self.bottom_tab.hide()

    def move_tab_to_bottom(self, widget, title, icon):
        self.bottom_tab.show()
        self.bottom_tab.add_draggable_tab(widget, title, icon)

    def move_tab_to_top(self, widget, title, icon):
        self.top_tab.add_draggable_tab(widget, title, icon)
        if self.bottom_tab.count() == 0:
            self.bottom_tab.hide()