# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QFrame
from qfluentwidgets import BodyLabel, SubtitleLabel

# --- 导入新模块 ---
from app.widgets.property_panel.port_widget import PortWidget


class NodePanelWidget:
    """处理普通节点属性UI的子模块"""

    def __init__(self, main_window, parent_panel, parent_layout):
        self.main_window = main_window
        self.parent_panel = parent_panel  # PropertyPanel 的实例
        self.parent_layout = parent_layout # PropertyPanel 中的 node_vbox

        # 存储当前节点的UI元素
        self.current_node = None
        self.port_widget = None # 引用 PortWidget 实例
        self.current_segment = None

    def build_port(self, node):
        # (c) 创建新的 PortWidget 实例
        self.port_widget = PortWidget(
            main_window=self.main_window,
            parent_panel=self.parent_panel,
            node=node,
            port_info_func=self.parent_panel.get_port_info,  # 传递获取端口信息的函数
            copy_as_expression_func=self.parent_panel._copy_as_expression,  # 传递复制表达式的函数
            add_output_to_global_func=self.parent_panel._add_output_to_global_variable,  # 传递添加到全局变量的函数
            parent=self.parent_panel  # 或者传入 self.parent_layout 的父控件
        )

    def build_ui(self, node, current_segment=None):
        """构建节点UI"""
        # 1. 检查是否是当前节点
        is_current_node = (self.current_node is not None and self.current_node.id == node.id)

        # 更新当前节点引用
        self.current_node = node

        # 2. 初始化节点属性
        if not hasattr(node, '_input_values'):
            node._input_values = {}
        if not hasattr(node, 'column_select'):
            node.column_select = {}

        self.build_port(node)

        title = SubtitleLabel(f"📌 {node.name()}")
        title.setWordWrap(True)
        self.parent_layout.addWidget(title)

        description = self.parent_panel.get_node_description(node) # 调用父控件的方法
        if description and description.strip():
            desc_label = BodyLabel(f"📝 {description}")
            desc_label.setWordWrap(True)
            self.parent_layout.addWidget(desc_label)

        self._add_separator(self.parent_layout)
        # 将已存在的 PortWidget 添加回布局
        self.parent_layout.addWidget(self.port_widget)
        # 根据 current_segment 设置 PortWidget 内部的分段控件状态
        if self.current_segment is not None:
             self.port_widget.segmented_widget.setCurrentItem(self.current_segment)
        elif hasattr(self.port_widget, 'segmented_widget'):
             if current_segment in ['input', 'output']:
                 self.port_widget.segmented_widget.setCurrentItem(current_segment)

        self.parent_layout.addWidget(self.port_widget)
        self.parent_layout.addStretch(1) # 添加伸缩项，使内容靠上

    def _add_separator(self, layout):
        """向布局添加分隔线"""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        layout.addWidget(separator)

    # --- 可选：提供方法访问 PortWidget 的内部字典 ---
    def get_port_widget_text_edit_widgets(self):
        """获取 PortWidget 内部的 text_edit_widgets 字典"""
        if self.port_widget:
            return self.port_widget.get_text_edit_widgets()
        return {}

    def get_port_widget_column_list_widgets(self):
        """获取 PortWidget 内部的 column_list_widgets 字典"""
        if self.port_widget:
            return self.port_widget.get_column_list_widgets()
        return {}

    # --- 可选：提供方法更新 PortWidget 内容 ---
    def update_port_data_in_widget(self, port_name, new_value):
        """更新 PortWidget 内部特定端口的数据"""
        if self.port_widget:
            self.port_widget.update_port_data(port_name, new_value)