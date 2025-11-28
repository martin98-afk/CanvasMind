# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QSizePolicy
from qfluentwidgets import SmoothScrollArea

from app.utils.utils import get_icon
from app.widgets.property_panel.global_panel import GlobalPanelWidget
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class GlobalVarPanel(ToolWindow):
    name = "全局变量面板"
    icon = get_icon("Global")
    default_position = DockPosition.BOTTOM  # ← 默认放在顶部

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 直接嵌入你现有的 PropertyPanel！
        self.global_panel = GlobalPanelWidget(self.canvas_page, self, layout)
        self.global_panel.build_ui()

    def set_scrollbar(self, widget):
        scroll = SmoothScrollArea(self)
        scroll.setStyleSheet("""
                SmoothScrollArea {
                    background: transparent;
                    border: none;
                }
            """)
        scroll.viewport().setStyleSheet("background-color: transparent; border: none;")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        scroll.setWidget(widget)
        return scroll