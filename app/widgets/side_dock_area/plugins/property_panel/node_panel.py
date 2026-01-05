# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SubtitleLabel, SmoothScrollArea, SimpleCardWidget

# --- 导入优化后的 PortWidget ---
from app.widgets.side_dock_area.plugins.property_panel.port_widget import PortWidget


class NodePanelWidget(SimpleCardWidget):
    """
    优化后的普通节点属性面板。
    不再是工具类，而是一个具有持久状态的 QWidget。
    """

    def __init__(self, main_window, parent_panel, node):
        """
        Args:
            main_window: 主窗口实例
            parent_panel: PropertyPanel 实例
            node: 绑定的初始节点
        """
        super().__init__(parent_panel)
        self.main_window = main_window
        self.parent_panel = parent_panel

        # 内部状态缓存
        self.current_segment = 'input'

        # 初始化 UI 骨架
        self._setup_ui(node)

    def _setup_ui(self, node):
        """仅在面板创建时执行一次，构建 UI 结构"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)

        # 2. 描述 (📝 节点描述)
        self.desc_label = BodyLabel()
        self.desc_label.setWordWrap(True)
        self.main_layout.addWidget(self.desc_label)

        # 3. 分隔线
        self.separator = self._create_separator()
        self.main_layout.addWidget(self.separator)

        # 4. 端口组件 (核心：只创建一次)
        self.port_widget = PortWidget(
            main_window=self.main_window,
            parent_panel=self.parent_panel,
            node=node,
            port_info_func=self.parent_panel.get_port_info,
            copy_as_expression_func=self.parent_panel._copy_as_expression,
            add_func=self.parent_panel._add_output_to_global_variable,
            delete_func=self.parent_panel._delete_output_from_global_variable,
            is_in_func=self.parent_panel._is_output_in_global_variable,
            parent=self
        )
        # 绑定分段切换事件，用于保留用户选中的 Tab 状态
        self.port_widget.segmented_widget.currentItemChanged.connect(self._on_port_segment_changed)

        # 将 PortWidget 添加到主布局
        self.main_layout.addWidget(self.port_widget, 1)

    def update_data(self, node):
        """
        增量更新方法：当 PropertyPanel 切换到此节点时调用。
        不重建任何控件，只修改现有控件的属性。
        """
        # 1. 初始化节点属性缓存（业务逻辑保留）
        if not hasattr(node, '_input_values'):
            node._input_values = {}
        if not hasattr(node, 'column_select'):
            node.column_select = {}

        # 3. 更新描述
        description = self.parent_panel.get_node_description(node)
        if description and description.strip():
            self.desc_label.setText(f"📝 {description}")
            self.desc_label.show()
            self.separator.show()
        else:
            self.desc_label.hide()
            self.separator.hide()

        # 4. 核心：触发 PortWidget 的增量刷新
        # 它会处理内部 Card 的复用、隐藏和数据显示
        self.port_widget.refresh(node)

        # 5. 恢复之前的分段选择状态 (Input/Output)
        self._restore_segment_state()

    def _restore_segment_state(self):
        """恢复分段控件的选中状态"""
        if hasattr(self.port_widget, 'segmented_widget'):
            self.port_widget.segmented_widget.blockSignals(True)
            self.port_widget.segmented_widget.setCurrentItem(self.current_segment)
            self.port_widget.segmented_widget.blockSignals(False)

    def _on_port_segment_changed(self, segment):
        """记录用户的 Tab 选择，以便在下次刷新时保留"""
        self.current_segment = segment

    def _create_separator(self):
        """创建分隔线"""
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("background-color: #444444; max-height: 1px; border: none;")
        return sep