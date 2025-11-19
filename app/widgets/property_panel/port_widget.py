# -*- coding: utf-8 -*-
"""
Port Widget Module
一个独立的控件，用于显示节点的输入和输出端口及其数据。
"""
import os
import re
from pathlib import Path

import pandas as pd
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QFrame, QListWidgetItem, QWidget, QFileDialog, QStackedWidget, \
    QSpacerItem
from loguru import logger
from qfluentwidgets import CardWidget, BodyLabel, PushButton, ListWidget, SegmentedWidget, \
    FluentIcon, InfoBar, TransparentToolButton, RoundMenu, Action, TransparentPushButton

from app.components.base import ArgumentType
from app.utils.utils import get_icon, canvas_file_dump_path
from app.widgets.tree_widget.variable_tree import VariableTreeWidget


class PortWidget(QWidget):
    """
    一个独立的控件，用于显示节点的输入和输出端口。
    这个控件内部管理分段控件和堆叠控件，以及输入/输出页面的布局。
    """

    def __init__(self, main_window, parent_panel, node, port_info_func, copy_as_expression_func, add_output_to_global_func, parent=None):
        """
        初始化 PortWidget。

        Args:
            main_window: 主窗口对象。
            parent_panel: 调用此函数的父面板对象 (如 PropertyPanel)。
            node: 要显示端口信息的节点对象。
            port_info_func: 一个函数，用于获取端口信息，例如 parent_panel.get_port_info。
            copy_as_expression_func: 一个函数，用于复制表达式，例如 parent_panel._copy_as_expression。
            add_output_to_global_func: 一个函数，用于将输出添加到全局变量，例如 parent_panel._add_output_to_global_variable。
            parent: PyQt父控件。
        """
        super().__init__(parent)
        self.main_window = main_window
        self.parent_panel = parent_panel
        self.node = node
        self.port_info_func = port_info_func
        self.copy_as_expression_func = copy_as_expression_func
        self.add_output_to_global_func = add_output_to_global_func

        # 存储当前节点的UI元素
        self.segmented_widget = None
        self.stacked_widget = None
        self.input_widget = None # 缓存输入页面
        self.output_widget = None # 缓存输出页面
        self._column_list_widgets = {}
        self._text_edit_widgets = {}

        # 初始化UI
        self._setup_ui()

    def _setup_ui(self):
        """设置端口控件的UI布局"""
        # 清理旧的UI元素
        self._column_list_widgets.clear()
        self._text_edit_widgets.clear()
        if not hasattr(self.node, '_input_values'):
            self.node._input_values = {}
        if not hasattr(self.node, 'column_select'):
            self.node.column_select = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(10) # SegmentedWidget 和 StackedWidget 之间可能不需要额外间距

        # 1. 创建分段控件和堆叠控件
        self.segmented_widget = SegmentedWidget(self)
        self.stacked_widget = QStackedWidget(self)

        self.input_widget = QWidget()
        input_layout = QVBoxLayout(self.input_widget)
        input_layout.setContentsMargins(3, 3, 3, 3)
        input_layout.setSpacing(8)

        self.output_widget = QWidget()
        output_layout = QVBoxLayout(self.output_widget)
        output_layout.setContentsMargins(3, 3, 3, 3)
        output_layout.setSpacing(8)

        # 2. 判断是否有输入输出端口并构建
        has_input_ports = False
        has_output_ports = False
        if hasattr(self.node, 'component_class') and self.node.component_class:
            comp_cls = self.node.component_class
            has_input_ports = len(getattr(comp_cls, 'inputs', [])) > 0
            has_output_ports = len(getattr(comp_cls, 'outputs', [])) > 0
        else:
            has_input_ports = len(self.node.input_ports()) > 0
            has_output_ports = len(self.node.output_ports()) > 0

        if has_input_ports:
            self.segmented_widget.addItem('input', '输入端口')
            self._populate_input_ports(input_layout)
            input_layout.addStretch(1)
            self.stacked_widget.addWidget(self.input_widget)
        if has_output_ports:
            self.segmented_widget.addItem('output', '输出端口')
            self._populate_output_ports(output_layout)
            output_layout.addStretch(1)
            self.stacked_widget.addWidget(self.output_widget)

        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)
        layout.addWidget(self.segmented_widget)
        layout.addWidget(self.stacked_widget)

        # 默认选中输入端口
        if has_input_ports:
            self.segmented_widget.setCurrentItem('input')
        elif has_output_ports:
            self.segmented_widget.setCurrentItem('output')

    def _on_segmented_changed(self, item_key):
        """处理分段控件切换"""
        if item_key == 'input':
            self.stacked_widget.setCurrentIndex(0)
        elif item_key == 'output':
            self.stacked_widget.setCurrentIndex(1)

    def _populate_input_ports(self, layout):
        """构建输入端口UI"""
        port_infos = self.port_info_func(self.node, is_input=True)
        if not port_infos:
            layout.addWidget(BodyLabel("  无输入端口"))
            return
        for port_name, port_label, port_type in port_infos:
            port_label = BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}")
            port_label.setWordWrap(True)
            layout.addWidget(port_label)
            input_port = self.node.get_input(port_name)
            connected = input_port.connected_ports() if input_port else []
            if len(connected) == 1:
                upstream = connected[0]
                original_data = upstream.node().get_output_value(upstream.name())
            elif connected:
                original_data = [up.node().get_output_value(up.name()) for up in connected]
            else:
                original_data = "暂无数据"
            if port_type == ArgumentType.CSV and isinstance(original_data, pd.DataFrame) and not original_data.empty:
                self._add_column_selector_widget_to_layout(port_name, original_data, layout)
                current_selected_data = self._get_current_input_value(port_name, original_data)
            elif port_type == ArgumentType.CSV and isinstance(original_data, str) and Path(original_data).is_file():
                sample_data = pd.read_csv(original_data, nrows=5)
                self._add_column_selector_widget_to_layout(port_name, sample_data, layout)
                current_selected_data = self._get_current_input_value(port_name, original_data)
            else:
                current_selected_data = original_data
            self._add_text_edit_to_layout(
                current_selected_data,
                port_type=port_type,
                port_name=port_name,
                layout=layout,
                is_output=False
            )

    def _populate_output_ports(self, layout):
        """构建输出端口UI"""
        port_infos = self.port_info_func(self.node, is_input=False)
        if not port_infos:
            layout.addWidget(BodyLabel("  无输出端口"))
            return
        for port_name, port_label, port_type in port_infos:
            port_label = BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}")
            port_label.setWordWrap(True)
            layout.addWidget(port_label)
            output_values = getattr(self.node, '_output_values', None)
            if output_values is None:
                output_values = {}
            display_data = output_values.get(port_name)
            if display_data is None:
                try:
                    display_data = self.node.model.get_property(port_name)
                except KeyError:
                    display_data = "暂无数据"
            if port_type == ArgumentType.UPLOAD:
                self._add_upload_widget_to_layout(port_name, layout)
            self._add_text_edit_to_layout(
                display_data,
                port_type=port_type,
                port_name=port_name,
                layout=layout,
                is_output=True
            )

    def _get_current_input_value(self, port_name, original_data):
        """获取当前经过列选择过滤的输入值"""
        selected_columns = self.node.column_select.get(port_name, [])
        if selected_columns and isinstance(original_data, pd.DataFrame):
            try:
                if len(selected_columns) == 1:
                    return original_data[selected_columns[0]]
                else:
                    return original_data[selected_columns]
            except Exception as e:
                return f"列选择错误: {str(e)}"
        else:
            return original_data

    def _add_column_selector_widget_to_layout(self, port_name, data, layout):
        """向布局添加列选择控件"""
        if not isinstance(data, pd.DataFrame) or data.empty:
            return
        columns = list(data.columns)
        if not columns:
            return

        column_card = CardWidget(self)
        initial_max_height = 200
        column_card.setMaximumHeight(initial_max_height)
        column_card.setMinimumHeight(initial_max_height)

        node_id = self.node.id
        port_identifier = f"{node_id}_{port_name}"
        if not hasattr(self.parent_panel, '_column_selector_card_expanded'):
            self.parent_panel._column_selector_card_expanded = {}
        self.parent_panel._column_selector_card_expanded[port_identifier] = False

        card_layout = QVBoxLayout(column_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(8)

        title_btn_layout = QHBoxLayout()
        title_label = BodyLabel("列选择:")
        title_btn_layout.addWidget(title_label)
        title_btn_layout.addStretch()
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)

        def toggle_expand():
            is_expanded = self.parent_panel._column_selector_card_expanded[port_identifier]
            if is_expanded:
                column_card.setMaximumHeight(initial_max_height)
                column_card.setMinimumHeight(initial_max_height)
                expand_btn.setIcon(get_icon("放大"))
                self.parent_panel._column_selector_card_expanded[port_identifier] = False
            else:
                num_items = list_widget.count()
                estimated_height_for_items = num_items * 39
                padding_height = card_layout.contentsMargins().top() + card_layout.contentsMargins().bottom()
                title_height = title_label.sizeHint().height() + card_layout.spacing()
                total_estimated_height = padding_height + title_height + estimated_height_for_items
                column_card.setFixedHeight(total_estimated_height + 40)
                expand_btn.setIcon(get_icon("缩小"))
                self.parent_panel._column_selector_card_expanded[port_identifier] = True
            layout.invalidate() # 通知父布局重新计算大小

        expand_btn.clicked.connect(toggle_expand)
        title_btn_layout.addWidget(expand_btn)
        card_layout.addLayout(title_btn_layout)

        list_widget = ListWidget(self)
        list_widget.setSelectionMode(ListWidget.NoSelection)
        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            list_widget.addItem(item)

        selected_columns = self.node.column_select.get(port_name, [])
        if not selected_columns and columns:
            selected_columns = columns.copy()
            self.node.column_select[port_name] = selected_columns
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setCheckState(Qt.Checked if item.text() in selected_columns else Qt.Unchecked)

        card_layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        select_all_btn = PushButton("全选", self)
        clear_btn = PushButton("清空", self)

        def select_all():
            list_widget.blockSignals(True)
            try:
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    item.setCheckState(Qt.Checked)
            finally:
                list_widget.blockSignals(False)
            _on_selection_changed()

        def clear_all():
            list_widget.blockSignals(True)
            try:
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    item.setCheckState(Qt.Unchecked)
            finally:
                list_widget.blockSignals(False)
            _on_selection_changed()

        def _on_selection_changed():
            current_selected = [
                list_widget.item(i).text()
                for i in range(list_widget.count())
                if list_widget.item(i).checkState() == Qt.Checked
            ]
            self.node.column_select[port_name] = current_selected
            selected_data_subset = data[current_selected] if current_selected else pd.DataFrame()
            # 尝试更新关联的 VariableTreeWidget
            if port_name in self._text_edit_widgets:
                widget = self._text_edit_widgets[port_name]
                if isinstance(widget, VariableTreeWidget):
                    widget.set_data(selected_data_subset)

        list_widget.itemChanged.connect(_on_selection_changed)
        select_all_btn.clicked.connect(select_all)
        clear_btn.clicked.connect(clear_all)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(clear_btn)
        card_layout.addLayout(btn_layout)
        layout.addWidget(column_card)

        self._column_list_widgets[port_name] = list_widget

    def _add_text_edit_to_layout(self, text, port_type=None, port_name=None, layout=None, is_output=False):
        """向布局添加 VariableTreeWidget 用于显示数据"""
        tree_widget = VariableTreeWidget(text, port_type, parent=self.main_window)
        info_card = CardWidget(self)
        info_card.setMaximumHeight(300)
        card_layout = QVBoxLayout(info_card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_text = "数据信息:"
        title_label = BodyLabel(title_text)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        if is_output:
            add_global_btn = TransparentPushButton(text="全局变量", icon=FluentIcon.ADD, parent=self)
            add_global_btn.clicked.connect(
                lambda _, n=self.node, p=port_name: self.add_output_to_global_func(n, p)
            )
            title_layout.addWidget(add_global_btn)
        browse_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)
        browse_btn.setFixedSize(QSize(26, 20))
        browse_btn.clicked.connect(tree_widget.show_detail)
        title_layout.addWidget(browse_btn)
        card_layout.addLayout(title_layout)
        card_layout.addWidget(tree_widget)

        if layout is None:
            layout = self.layout() # Fallback
        layout.addWidget(info_card)

        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(
                Action(
                    FluentIcon.COPY, "复制为表达式", parent=self,
                    triggered=lambda: self.copy_as_expression_func("node_vars", f"{self.node.name()}_{port_name}")
                )
            )
            menu.exec_(info_card.mapToGlobal(pos))

        if is_output:
            info_card.setContextMenuPolicy(Qt.CustomContextMenu)
            info_card.customContextMenuRequested.connect(show_context_menu)

        if port_name is not None:
            self._text_edit_widgets[port_name] = tree_widget
        return tree_widget

    def _add_upload_widget_to_layout(self, port_name, layout):
        """向布局添加文件上传控件"""
        upload_widget = QWidget()
        upload_layout = QVBoxLayout(upload_widget)
        upload_layout.setSpacing(4)
        upload_layout.setContentsMargins(0, 0, 0, 0)
        upload_button = PushButton("📁 上传文件", self)
        upload_button.clicked.connect(lambda _, p=port_name: self._select_upload_file(p))
        upload_layout.addWidget(upload_button)
        layout.addWidget(upload_widget)

    def _select_upload_file(self, port_name):
        """处理文件选择和上传逻辑"""
        current_path = self.node._output_values.get(port_name, "")
        directory = os.path.dirname(current_path) if current_path else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "上传文件", directory, "All Files (*)"
        )
        if not file_path:
            return
        src_path = Path(file_path)
        if not src_path.exists():
            InfoBar.error("文件不存在", f"所选文件 {file_path} 不存在", parent=self.parent())
            return
        upload_root = canvas_file_dump_path() / "uploads"
        upload_root.mkdir(exist_ok=True, parents=True)
        safe_name = re.sub(r'[^\w\.-]', '_', src_path.stem)
        suffix = src_path.suffix
        unique_name = f"{safe_name}_{self.node.persistent_id}{suffix}"
        dst_path = upload_root / unique_name
        try:
            import shutil
            shutil.copy2(src_path, dst_path)
            logger.info(f"已上传并复制文件: {src_path} -> {dst_path}")
        except Exception as e:
            logger.error(f"文件复制失败: {e}")
            InfoBar.error("上传失败", f"无法复制文件：{e}", parent=self.parent())
            return
        self.node._output_values[port_name] = str(dst_path)
        InfoBar.success("上传成功", f"文件已保存至：{dst_path.name}", parent=self.main_window, duration=2000)