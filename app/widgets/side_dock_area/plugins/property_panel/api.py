# -*- coding: utf-8 -*-
# /app/widgets/side_dock/plugins/property_tool.py
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import FluentIcon
from app.widgets.side_dock_area.tool_window import ToolWindow
from app.widgets.property_panel import PropertyPanel  # ← 复用你现有的 PropertyPanel

class PropertyToolWindow(ToolWindow):
    name = "属性"
    icon = FluentIcon.PROPERTY

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 直接嵌入你现有的 PropertyPanel！
        self.property_panel = PropertyPanel(self.canvas_page, self)
        layout.addWidget(self.property_panel)