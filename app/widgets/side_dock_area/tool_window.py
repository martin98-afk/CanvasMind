# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QWidget

class ToolWindow(QWidget):
    name: str = "Unnamed"
    icon = None  # FluentIcon or QIcon
    singleton = True  # 是否单例

    def __init__(self, canvas_page):
        super().__init__()
        self.canvas_page = canvas_page
        self.setup_ui()

    def setup_ui(self):
        raise NotImplementedError