# -*- coding: utf-8 -*-
import os
import re
from pathlib import Path

import pandas as pd
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QFrame, QListWidgetItem, QWidget, QFileDialog, QStackedWidget
from loguru import logger
from qfluentwidgets import CardWidget, BodyLabel, PushButton, ListWidget, SegmentedWidget, \
    FluentIcon, InfoBar, TransparentToolButton, RoundMenu, Action, TransparentPushButton, \
    SubtitleLabel

from app.components.base import ArgumentType
from app.utils.utils import get_icon, canvas_file_dump_path
from app.widgets.tree_widget.variable_tree import VariableTreeWidget


class NodePanelWidget:
    """处理普通节点属性UI的子模块"""

    def __init__(self, main_window, parent_panel, parent_layout):
        self.main_window = main_window
        self.parent_panel = parent_panel  # PropertyPanel 的实例
        self.parent_layout = parent_layout # PropertyPanel 中的 node_vbox

        # 存储当前节点的UI元素
        self.current_node = None
        self.segmented_widget = None
        self.stacked_widget = None
        self._column_list_widgets = {}
        self._text_edit_widgets = {}

    def build_ui(self, node, current_segment=None):
        """构建节点UI"""
        self.current_node = node
        self._column_list_widgets.clear()
        self._text_edit_widgets.clear()
        if not hasattr(node, '_input_values'):
            node._input_values = {}
        if not hasattr(node, 'column_select'):
            node.column_select = {}

        # 1. 添加标题和描述
        title = SubtitleLabel(f"📌 {node.name()}")
        title.setWordWrap(True)
        self.parent_layout.addWidget(title)

        description = self.parent_panel.get_node_description(node) # 调用父控件的方法
        if description and description.strip():
            desc_label = BodyLabel(f"📝 {description}")
            desc_label.setWordWrap(True)
            self.parent_layout.addWidget(desc_label)

        self._add_seperator(self.parent_layout)

        # 2. 创建分段控件和堆叠控件
        self.segmented_widget = SegmentedWidget(self.parent_panel)
        self.stacked_widget = QStackedWidget(self.parent_panel)

        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)

        # 3. 判断是否有输入输出端口并构建
        has_input_ports = False
        has_output_ports = False
        if hasattr(node, 'component_class') and node.component_class:
            comp_cls = node.component_class
            has_input_ports = len(getattr(comp_cls, 'inputs', [])) > 0
            has_output_ports = len(getattr(comp_cls, 'outputs', [])) > 0
        else:
            has_input_ports = len(node.input_ports()) > 0
            has_output_ports = len(node.output_ports()) > 0

        if has_input_ports:
            self.segmented_widget.addItem('input', '输入端口')
            self._populate_input_ports(node, input_layout)
            input_layout.addStretch(1)
            self.stacked_widget.addWidget(input_widget)
        if has_output_ports:
            self.segmented_widget.addItem('output', '输出端口')
            self._populate_output_ports(node, output_layout)
            output_layout.addStretch(1)
            self.stacked_widget.addWidget(output_widget)

        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)
        self.parent_layout.addWidget(self.segmented_widget)
        self.parent_layout.addWidget(self.stacked_widget)

        if current_segment in ['input', 'output']:
            self.segmented_widget.setCurrentItem(current_segment)
        else:
            self.segmented_widget.setCurrentItem('input')

    def _add_seperator(self, layout):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        layout.addWidget(separator)

    def _on_segmented_changed(self, item_key):
        if item_key == 'input':
            self.stacked_widget.setCurrentIndex(0)
        elif item_key == 'output':
            self.stacked_widget.setCurrentIndex(1)

    def _populate_input_ports(self, node, layout):
        port_infos = self.parent_panel.get_port_info(node, is_input=True) # 调用父控件方法
        if not port_infos:
            layout.addWidget(BodyLabel("  无输入端口"))
            return
        for port_name, port_label, port_type in port_infos:
            port_label = BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}")
            port_label.setWordWrap(True)
            layout.addWidget(port_label)
            input_port = node.get_input(port_name)
            connected = input_port.connected_ports() if input_port else []
            if len(connected) == 1:
                upstream = connected[0]
                original_data = upstream.node().get_output_value(upstream.name())
            elif connected:
                original_data = [up.node().get_output_value(up.name()) for up in connected]
            else:
                original_data = "暂无数据"
            if port_type == ArgumentType.CSV and isinstance(original_data, pd.DataFrame) and not original_data.empty:
                self._add_column_selector_widget_to_layout(node, port_name, original_data, layout)
                current_selected_data = self._get_current_input_value(node, port_name, original_data)
            elif port_type == ArgumentType.CSV and isinstance(original_data, str) and Path(original_data).is_file():
                sample_data = pd.read_csv(original_data, nrows=5)
                self._add_column_selector_widget_to_layout(node, port_name, sample_data, layout)
                current_selected_data = self._get_current_input_value(node, port_name, original_data)
            else:
                current_selected_data = original_data
            self._add_text_edit_to_layout(
                current_selected_data,
                port_type=port_type,
                port_name=port_name,
                layout=layout,
                node=node
            )

    def _populate_output_ports(self, node, layout):
        port_infos = self.parent_panel.get_port_info(node, is_input=False) # 调用父控件方法
        if not port_infos:
            layout.addWidget(BodyLabel("  无输出端口"))
            return
        for port_name, port_label, port_type in port_infos:
            port_label = BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}")
            port_label.setWordWrap(True)
            layout.addWidget(port_label)
            output_values = getattr(node, '_output_values', None)
            if output_values is None:
                output_values = {}
            display_data = output_values.get(port_name)
            if display_data is None:
                try:
                    display_data = node.model.get_property(port_name)
                except KeyError:
                    display_data = "暂无数据"
            if port_type == ArgumentType.UPLOAD:
                self._add_upload_widget_to_layout(node, port_name, layout)
            self._add_text_edit_to_layout(
                display_data,
                port_type=port_type,
                port_name=port_name,
                layout=layout,
                node=node,
                is_output=True
            )

    def _get_current_input_value(self, node, port_name, original_data):
        selected_columns = node.column_select.get(port_name, [])
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

    def _add_column_selector_widget_to_layout(self, node, port_name, data, layout):
        if not isinstance(data, pd.DataFrame) or data.empty:
            return
        columns = list(data.columns)
        if not columns:
            return

        column_card = CardWidget(self.parent_panel)
        initial_max_height = 200
        column_card.setMaximumHeight(initial_max_height)
        column_card.setMinimumHeight(initial_max_height)

        node_id = node.id
        port_identifier = f"{node_id}_{port_name}"
        if not hasattr(self, '_column_selector_card_expanded'):
            self._column_selector_card_expanded = {}
        self._column_selector_card_expanded[port_identifier] = False

        card_layout = QVBoxLayout(column_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(8)

        title_btn_layout = QHBoxLayout()
        title_label = BodyLabel("列选择:")
        title_btn_layout.addWidget(title_label)
        title_btn_layout.addStretch()
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self.parent_panel)

        def toggle_expand():
            is_expanded = self._column_selector_card_expanded[port_identifier]
            if is_expanded:
                column_card.setMaximumHeight(initial_max_height)
                column_card.setMinimumHeight(initial_max_height)
                expand_btn.setIcon(get_icon("放大"))
                self._column_selector_card_expanded[port_identifier] = False
            else:
                num_items = list_widget.count()
                estimated_height_for_items = num_items * 39
                padding_height = card_layout.contentsMargins().top() + card_layout.contentsMargins().bottom()
                title_height = title_label.sizeHint().height() + card_layout.spacing()
                total_estimated_height = padding_height + title_height + estimated_height_for_items
                column_card.setFixedHeight(total_estimated_height + 40)
                expand_btn.setIcon(get_icon("缩小"))
                self._column_selector_card_expanded[port_identifier] = True
            self.parent_layout.invalidate()

        expand_btn.clicked.connect(toggle_expand)
        title_btn_layout.addWidget(expand_btn)
        card_layout.addLayout(title_btn_layout)

        list_widget = ListWidget(self.parent_panel)
        list_widget.setSelectionMode(ListWidget.NoSelection)
        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            list_widget.addItem(item)

        selected_columns = node.column_select.get(port_name, [])
        if not selected_columns and columns:
            selected_columns = columns.copy()
            node.column_select[port_name] = selected_columns
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setCheckState(Qt.Checked if item.text() in selected_columns else Qt.Unchecked)

        card_layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        select_all_btn = PushButton("全选", self.parent_panel)
        clear_btn = PushButton("清空", self.parent_panel)

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
            node.column_select[port_name] = current_selected
            selected_data_subset = data[current_selected] if current_selected else pd.DataFrame()
            self._update_text_edit_for_port(port_name, selected_data_subset)

        list_widget.itemChanged.connect(_on_selection_changed)
        select_all_btn.clicked.connect(select_all)
        clear_btn.clicked.connect(clear_all)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(clear_btn)
        card_layout.addLayout(btn_layout)
        layout.addWidget(column_card)

        self._column_list_widgets[port_name] = list_widget

    def _add_text_edit_to_layout(self, text, port_type=None, port_name=None, layout=None, node=None, is_output=False):
        tree_widget = VariableTreeWidget(text, port_type, parent=self.main_window)
        info_card = CardWidget(self.parent_panel)
        info_card.setMaximumHeight(300)
        card_layout = QVBoxLayout(info_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_text = "数据信息:"
        title_label = BodyLabel(title_text)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        if is_output and node is not None:
            add_global_btn = TransparentPushButton(text="全局变量", icon=FluentIcon.ADD, parent=self.parent_panel)
            add_global_btn.clicked.connect(
                lambda _, n=node, p=port_name: self.parent_panel._add_output_to_global_variable(n, p) # 调用父控件方法
            )
            title_layout.addWidget(add_global_btn)
        browse_btn = TransparentToolButton(icon=get_icon("放大"), parent=self.parent_panel)
        browse_btn.setFixedSize(QSize(26, 20))
        browse_btn.clicked.connect(tree_widget.show_detail)
        title_layout.addWidget(browse_btn)
        card_layout.addLayout(title_layout)
        card_layout.addWidget(tree_widget)

        if layout is None:
            layout = self.parent_layout
        layout.addWidget(info_card)

        def show_context_menu(pos):
            menu = RoundMenu(parent=self.parent_panel)
            menu.addAction(
                Action(
                    FluentIcon.COPY, "复制为表达式", parent=self.parent_panel,
                    triggered=lambda: self.parent_panel._copy_as_expression("node_vars", f"{node.name()}_{port_name}") # 调用父控件方法
                )
            )
            menu.exec_(info_card.mapToGlobal(pos))

        if is_output:
            info_card.setContextMenuPolicy(Qt.CustomContextMenu)
            info_card.customContextMenuRequested.connect(show_context_menu)

        if port_name is not None:
            self._text_edit_widgets[port_name] = tree_widget
        return tree_widget

    def _update_text_edit_for_port(self, port_name, new_value):
        if port_name not in self._text_edit_widgets:
            return
        widget = self._text_edit_widgets[port_name]
        if isinstance(widget, VariableTreeWidget):
            widget.set_data(new_value)

    def _add_upload_widget_to_layout(self, node, port_name, layout):
        upload_widget = QWidget()
        upload_layout = QVBoxLayout(upload_widget)
        upload_layout.setSpacing(4)
        upload_layout.setContentsMargins(0, 0, 0, 0)
        upload_button = PushButton("📁 上传文件", self.parent_panel)
        upload_button.clicked.connect(lambda _, p=port_name, n=node: self._select_upload_file(p, n))
        upload_layout.addWidget(upload_button)
        layout.addWidget(upload_widget)

    def _select_upload_file(self, port_name, node):
        current_path = node._output_values.get(port_name, "")
        directory = os.path.dirname(current_path) if current_path else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent_panel, "上传文件", directory, "All Files (*)"
        )
        if not file_path:
            return
        src_path = Path(file_path)
        if not src_path.exists():
            InfoBar.error("文件不存在", f"所选文件 {file_path} 不存在", parent=self.parent_panel.parent_window)
            return
        upload_root = canvas_file_dump_path() / "uploads"
        upload_root.mkdir(exist_ok=True, parents=True)
        safe_name = re.sub(r'[^\w\.-]', '_', src_path.stem)
        suffix = src_path.suffix
        unique_name = f"{safe_name}_{node.persistent_id}{suffix}"
        dst_path = upload_root / unique_name
        try:
            import shutil
            shutil.copy2(src_path, dst_path)
            logger.info(f"已上传并复制文件: {src_path} -> {dst_path}")
        except Exception as e:
            logger.error(f"文件复制失败: {e}")
            InfoBar.error("上传失败", f"无法复制文件：{e}", parent=self.parent_panel.parent_window)
            return
        node._output_values[port_name] = str(dst_path)
        self.parent_panel.update_properties(node) # 调用父控件方法刷新UI
        InfoBar.success("上传成功", f"文件已保存至：{dst_path.name}", parent=self.main_window, duration=2000)
