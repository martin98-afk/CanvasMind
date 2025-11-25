# -*- coding: utf-8 -*-
from enum import Enum
from PyQt5.QtWidgets import QWidget


class DockPosition(Enum):
    TOP = "top"
    BOTTOM = "bottom"
    HIDDEN = "hidden"  # 不自动注册到 dock


class ToolWindow(QWidget):
    name: str = "Unnamed"
    icon = None
    singleton = True
    default_position: DockPosition = DockPosition.HIDDEN  # 默认不自动显示

    def __init__(self, canvas_page):
        super().__init__()
        self.canvas_page = canvas_page
        self.setup_ui()

    def setup_ui(self):
        raise NotImplementedError