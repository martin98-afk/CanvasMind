# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import FluentIcon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.widgets.property_panel import PropertyPanel  # ← 复用你现有的 PropertyPanel


class PropertyToolWindow(ToolWindow):
    name = "属性面板"
    icon = FluentIcon.SAVE
    default_position = DockPosition.TOP  # ← 默认放在顶部

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 直接嵌入你现有的 PropertyPanel！
        self.property_panel = PropertyPanel(self.canvas_page, self.canvas_page)
        layout.addWidget(self.property_panel)

    # --- 工具对外暴露的方法 ---
    def update_properties(self, node, node_changed=False):
        self.property_panel.update_properties(node, node_changed)

    def set_allowed_update(self, allowed):
        self.property_panel.set_allowed_update(allowed)

    def get_current_execution_order(self):
        return self.property_panel.get_current_execution_order()

    def reset_current_components(self):
        self.property_panel.reset_current_components()

    def update_node_list_content(self):
        self.property_panel.node_list_panel_widget.update_node_list_content()

    def refresh_node_vars_page(self):
        self.property_panel._refresh_node_vars_page()