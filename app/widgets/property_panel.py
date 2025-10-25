# -*- coding: utf-8 -*-
import json
import os
import re

import pandas as pd
from NodeGraphQt import BaseNode
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QVBoxLayout, QFrame, QFileDialog, QListWidgetItem, QWidget, \
    QStackedWidget, QHBoxLayout, QApplication
from qfluentwidgets import CardWidget, BodyLabel, PushButton, ListWidget, SmoothScrollArea, SegmentedWidget, \
    ProgressBar, FluentIcon, InfoBar, InfoBarPosition, TransparentToolButton, RoundMenu, Action, TransparentPushButton, \
    TransparentDropDownToolButton

from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.utils.utils import serialize_for_json, get_icon
from app.widgets.dialog_widget.custom_messagebox import CustomTwoInputDialog
from app.widgets.tree_widget.variable_tree import VariableTreeWidget


class PropertyPanel(CardWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setFixedWidth(280)

        # === 全局变量缓存 ===
        self._custom_var_cards = {}
        self._node_var_cards = {}
        self._env_var_cards = {}
        self._global_panel_built = False

        # === 顶层堆叠：两个独立的 ScrollArea ===
        self.main_stacked = QStackedWidget(self)

        # --- 节点面板（带独立 ScrollArea）---
        node_scroll = SmoothScrollArea(self)
        node_scroll.viewport().setStyleSheet("background-color: transparent;")
        node_scroll.setWidgetResizable(True)
        node_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.node_container = QWidget()
        self.node_vbox = QVBoxLayout(self.node_container)
        self.node_vbox.setContentsMargins(10, 10, 10, 10)
        self.node_vbox.setSpacing(8)
        node_scroll.setWidget(self.node_container)
        self.main_stacked.addWidget(node_scroll)  # index 0

        # --- 全局变量面板（带独立 ScrollArea）---
        global_scroll = SmoothScrollArea(self)
        global_scroll.viewport().setStyleSheet("background-color: transparent;")
        global_scroll.setWidgetResizable(True)
        global_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.global_container = QWidget()
        self.global_vbox = QVBoxLayout(self.global_container)
        self.global_vbox.setContentsMargins(10, 10, 10, 10)
        self.global_vbox.setSpacing(8)
        global_scroll.setWidget(self.global_container)
        self.main_stacked.addWidget(global_scroll)  # index 1

        # --- 主布局 ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_stacked)

        self.current_node = None
        self._column_list_widgets = {}
        self._text_edit_widgets = {}
        self.segmented_widget = None
        self.stacked_widget = None
        self._current_global_tab = 'custom'

        self.main_window.global_variables_changed.connect(self._on_global_variables_changed)

    # ========================
    # 全局变量信号响应（增量更新）
    # ========================
    def _on_global_variables_changed(self, var_type: str, var_name: str, action: str):
        if not self._global_panel_built:
            return
        if var_type == "node_vars":
            if action == "add" or action == "update":
                if var_name not in self._node_var_cards:
                    global_vars = self.main_window.global_variables
                    if hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
                        card = self._create_variable_card(var_name, global_vars.node_vars[var_name])
                        self.node_vars_layout.addWidget(card)
                        self._node_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._node_var_cards:
                    card = self._node_var_cards.pop(var_name)
                    card.deleteLater()
        elif var_type == "custom":
            if action == "add" or action == "update":
                if var_name not in self._custom_var_cards:
                    global_vars = self.main_window.global_variables
                    if hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                        card = self._create_dict_row(var_name, global_vars.custom[var_name].value)
                        self.custom_vars_layout.addWidget(card)
                        self._custom_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._custom_var_cards:
                    card = self._custom_var_cards.pop(var_name)
                    card.deleteLater()
        elif var_type == "env":
            if action == "add" or action == "update":
                if var_name not in self._env_var_cards:
                    global_vars = self.main_window.global_variables
                    if hasattr(global_vars, 'env'):
                        value = getattr(global_vars.env, var_name, None)
                        if value is not None:
                            card = self._create_env_var_row(var_name, value)
                            self.env_vars_layout.addWidget(card)
                            self._env_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._env_var_cards:
                    card = self._env_var_cards.pop(var_name)
                    card.deleteLater()

    # ========================
    # 节点面板相关
    # ========================
    def _clear_node_layout(self):
        self._column_list_widgets.clear()
        self._text_edit_widgets.clear()
        while self.node_vbox.count():
            child = self.node_vbox.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def get_port_info(self, node, is_input=True):
        ports = node.input_ports() if is_input else node.output_ports()
        if hasattr(node, 'component_class'):
            comp_ports = getattr(node.component_class, 'inputs' if is_input else 'outputs', [])
            port_dict = {p.name(): p for p in ports}
            result = []
            for comp_def in comp_ports:
                port_name = comp_def.name
                if port_name in port_dict:
                    result.append((port_name, comp_def.label, comp_def.type))
                else:
                    result.append((port_name, port_name, ArgumentType.TEXT))
            for port in ports:
                if port.name() not in [r[0] for r in result]:
                    result.append((port.name(), port.name(), ArgumentType.TEXT))
            return result
        elif node.has_property(f"{'input' if is_input else 'output'}_ports"):
            ports = node.input_ports() if is_input else node.output_ports()
            port_defs = node.get_property(f"{'input' if is_input else 'output'}_ports")
            type_dict = {item.value: item for item in ArgumentType}

            return [(p.name(), p.name(), type_dict[pd["type"]]) for p, pd in zip(ports, port_defs)]
        else:
            return [(p.name(), p.name(), ArgumentType.TEXT) for p in ports]

    def update_properties(self, node):
        is_same_node = (
                node is not None
                and node is self.current_node
                and not isinstance(node, ControlFlowBackdrop)
        )
        if is_same_node:
            self._update_existing_node_data(node)
            return

        current_segment = None
        if self.segmented_widget:
            current_segment = self.segmented_widget.currentRouteKey()
        if hasattr(self, 'global_segmented'):
            self._current_global_tab = self.global_segmented.currentRouteKey()

        self.current_node = node
        if not node:
            self._show_global_variables_panel()
            self.main_stacked.setCurrentIndex(1)
        else:
            # 清理并构建节点面板
            self._clear_node_layout()
            if isinstance(node, ControlFlowBackdrop):
                self._update_control_flow_properties(node, current_segment)
            elif isinstance(node, BaseNode):
                self._build_node_ui(node, current_segment)
            self.main_stacked.setCurrentIndex(0)

    def _build_node_ui(self, node, current_segment=None):
        if not hasattr(node, '_input_values'):
            node._input_values = {}
        if not hasattr(node, 'column_select'):
            node.column_select = {}

        title = BodyLabel(f"📌 {node.name()}")
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.node_vbox.addWidget(title)

        description = self.get_node_description(node)
        if description and description.strip():
            desc_label = BodyLabel(f"📝 {description}")
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #888888; font-size: 16px;")
            self.node_vbox.addWidget(desc_label)
        self._add_seperator(self.node_vbox)

        self.segmented_widget = SegmentedWidget()
        self.stacked_widget = QStackedWidget()
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)

        if len(node.input_ports()) > 0:
            self.segmented_widget.addItem('input', '输入端口')
            self._populate_input_ports(node, input_layout)
            input_layout.addStretch(1)
            self.stacked_widget.addWidget(input_widget)
        if len(node.output_ports()) > 0:
            self.segmented_widget.addItem('output', '输出端口')
            self._populate_output_ports(node, output_layout)
            output_layout.addStretch(1)
            self.stacked_widget.addWidget(output_widget)

        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)
        self.node_vbox.addWidget(self.segmented_widget)
        self.node_vbox.addWidget(self.stacked_widget)

        if current_segment in ['input', 'output']:
            self.segmented_widget.setCurrentItem(current_segment)
        else:
            self.segmented_widget.setCurrentItem('input')

    def _update_existing_node_data(self, node):
        for port_name, _, port_type in self.get_port_info(node, is_input=True):
            input_port = node.get_input(port_name)
            connected = input_port.connected_ports() if input_port else []
            if len(connected) == 1:
                upstream = connected[0]
                original_data = upstream.node().get_output_value(upstream.name())
            elif connected:
                original_data = [up.node().get_output_value(up.name()) for up in connected]
            else:
                original_data = node._input_values.get(port_name, "暂无数据")

            if port_name in self._column_list_widgets:
                list_widget = self._column_list_widgets[port_name]
                if isinstance(original_data, pd.DataFrame) and not original_data.empty:
                    current_columns = list(original_data.columns)
                    existing_items = [list_widget.item(i).text() for i in range(list_widget.count())]
                    if set(current_columns) != set(existing_items):
                        self.update_properties(node)
                        return
                    selected_columns = node.column_select.get(port_name, [])
                    for i in range(list_widget.count()):
                        item = list_widget.item(i)
                        item.setCheckState(Qt.Checked if item.text() in selected_columns else Qt.Unchecked)
            current_selected_data = self._get_current_input_value(node, port_name, original_data)
            self._update_text_edit_for_port(port_name, current_selected_data)

        for port_name, _, port_type in self.get_port_info(node, is_input=False):
            display_data = node.get_output_value(port_name)
            if display_data is None:
                display_data = "暂无数据"
            self._update_text_edit_for_port(port_name, display_data)

    def _populate_input_ports(self, node, layout):
        port_infos = self.get_port_info(node, is_input=True)
        if not port_infos:
            layout.addWidget(BodyLabel("  无输入端口"))
            return
        for port_name, port_label, port_type in port_infos:
            layout.addWidget(BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}"))
            input_port = node.get_input(port_name)
            connected = input_port.connected_ports() if input_port else []
            if len(connected) == 1:
                upstream = connected[0]
                original_data = upstream.node().get_output_value(upstream.name())
            elif connected:
                original_data = [up.node().get_output_value(up.name()) for up in connected]
            else:
                original_data = node._input_values.get(port_name, "暂无数据")

            if port_type == ArgumentType.CSV and isinstance(original_data, pd.DataFrame) and not original_data.empty:
                self._add_column_selector_widget_to_layout(node, port_name, original_data, original_data, layout)
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
        port_infos = self.get_port_info(node, is_input=False)
        if not port_infos:
            layout.addWidget(BodyLabel("  无输出端口"))
            return
        for port_name, port_label, port_type in port_infos:
            layout.addWidget(BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}"))
            if getattr(node, "_output_values") is None:
                continue
            display_data = getattr(node, "_output_values", {}).get(port_name)
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

    def _add_column_selector_widget_to_layout(self, node, port_name, data, original_data, layout):
        if not isinstance(data, pd.DataFrame) or data.empty:
            return
        columns = list(data.columns)
        if not columns:
            return
        column_card = CardWidget(self)
        column_card.setMaximumHeight(280)
        card_layout = QVBoxLayout(column_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(8)
        title_label = BodyLabel("列选择:")
        card_layout.addWidget(title_label)
        list_widget = ListWidget(self)
        list_widget.setSelectionMode(ListWidget.NoSelection)
        list_widget.setFixedHeight(140)
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
        select_all_btn = PushButton("全选", self)
        clear_btn = PushButton("清空", self)
        def select_all():
            for i in range(list_widget.count()):
                list_widget.item(i).setCheckState(Qt.Checked)
            _on_selection_changed()
        def clear_all():
            for i in range(list_widget.count()):
                list_widget.item(i).setCheckState(Qt.Unchecked)
            _on_selection_changed()
        def _on_selection_changed():
            current_selected = [
                list_widget.item(i).text()
                for i in range(list_widget.count())
                if list_widget.item(i).checkState() == Qt.Checked
            ]
            node.column_select[port_name] = current_selected
            self._update_text_edit_for_port(port_name, data[current_selected])
        select_all_btn.clicked.connect(select_all)
        clear_btn.clicked.connect(clear_all)
        list_widget.itemChanged.connect(_on_selection_changed)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(clear_btn)
        card_layout.addLayout(btn_layout)
        layout.addWidget(column_card)
        self._column_list_widgets[port_name] = list_widget

    def _add_text_edit_to_layout(self, text, port_type=None, port_name=None, layout=None, node=None, is_output=False):
        tree_widget = VariableTreeWidget(text, port_type, parent=self.main_window)
        info_card = CardWidget(self)
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
            add_global_btn = TransparentPushButton(text="全局变量", icon=FluentIcon.ADD, parent=self)
            add_global_btn.clicked.connect(
                lambda _, n=node, p=port_name: self._add_output_to_global_variable(n, p)
            )
            title_layout.addWidget(add_global_btn)
        browse_btn = TransparentToolButton(icon=get_icon("放大"), parent=self)
        browse_btn.clicked.connect(tree_widget.show_detail)
        title_layout.addWidget(browse_btn)
        card_layout.addLayout(title_layout)

        card_layout.addWidget(tree_widget)
        if layout is None:
            layout = self.node_vbox
        layout.addWidget(info_card)

        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(
                Action("复制为表达式",
                       triggered=lambda: self._copy_as_expression("node_vars", f"{node.name()}_{port_name}"))
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
        upload_button = PushButton("📁 上传文件", self)
        upload_button.clicked.connect(lambda _, p=port_name, n=node: self._select_upload_file(p, n))
        upload_layout.addWidget(upload_button)
        layout.addWidget(upload_widget)

    def _select_upload_file(self, port_name, node):
        current_path = node._output_values.get(port_name, "")
        directory = os.path.dirname(current_path) if current_path else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "上传文件", directory, "All Files (*)"
        )
        if file_path:
            node._output_values[port_name] = file_path
        self.update_properties(node)

    def get_node_description(self, node):
        if hasattr(node, 'component_class'):
            return getattr(node.component_class, 'description', '')
        try:
            return node.model.get_property('description')
        except KeyError:
            return ''

    # ========================
    # ControlFlowBackdrop 相关
    # ========================
    def _update_control_flow_properties(self, node, current_segment=None):
        title = BodyLabel(f"🔁 {node.NODE_NAME}")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.node_vbox.addWidget(title)
        flow_type = getattr(node, 'TYPE', 'unknown')
        current = node.model.get_property('current_index')
        if flow_type == "loop":
            loop_mode = node.model.get_property("loop_mode")
            if loop_mode == 'count':
                total = node.model.get_property("loop_nums")
            else:
                total = node.model.get_property("max_iterations")
        elif flow_type == "iterate":
            input_data = []
            for input_port in node.input_ports():
                connected = input_port.connected_ports()
                if connected:
                    if len(connected) == 1:
                        upstream = connected[0]
                        value = upstream.node()._output_values.get(upstream.name())
                        input_data = value
                    else:
                        input_data.extend(
                            [upstream.node()._output_values.get(upstream.name()) for upstream in connected]
                        )
            if not isinstance(input_data, (list, tuple, dict)):
                input_data = [input_data]
            total = len(input_data)
            node.model.set_property("loop_nums", total)
        else:
            total = 0
        progress_label = BodyLabel(f"进度: {current}/{total}")
        progress_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        progress_bar = ProgressBar(self, useAni=False)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(int(current / max(1, total) * 100) if total > 0 else 0)
        self.node_vbox.addWidget(progress_label)
        self.node_vbox.addWidget(progress_bar)
        if flow_type == "loop":
            self._add_seperator(self.node_vbox)
            self._add_loop_config_section(node)
        self._add_seperator(self.node_vbox)
        self._add_internal_nodes_section(node)
        self.node_vbox.addStretch()

        self.segmented_widget = SegmentedWidget()
        self.segmented_widget.addItem('input', '输入端口')
        self.segmented_widget.addItem('output', '输出端口')
        self.stacked_widget = QStackedWidget()

        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        self._populate_input_ports(node, input_layout)
        input_layout.addStretch(1)
        self.stacked_widget.addWidget(input_widget)

        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        self._populate_output_ports(node, output_layout)
        output_layout.addStretch(1)
        self.stacked_widget.addWidget(output_widget)

        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)
        self.node_vbox.addWidget(self.segmented_widget)
        self.node_vbox.addWidget(self.stacked_widget)
        self.node_vbox.addStretch(1)

        if current_segment in ['input', 'output']:
            self.segmented_widget.setCurrentItem(current_segment)
        else:
            self.segmented_widget.setCurrentItem('input')

    def _add_loop_config_section(self, node):
        config_card = CardWidget(self)
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(10, 10, 10, 10)
        from qfluentwidgets import ComboBox, SpinBox, LineEdit
        mode_combo = ComboBox(self)
        mode_combo.addItems(['固定次数', '条件循环', 'While循环'])
        mode_combo.setCurrentText({
                                      'count': '固定次数',
                                      'condition': '条件循环',
                                      'while': 'While循环'
                                  }.get(node.model.get_property("loop_mode"), '固定次数'))
        def on_mode_changed(text):
            mode_map = {'固定次数': 'count', '条件循环': 'condition', 'While循环': 'while'}
            node.model.set_property("loop_mode", mode_map.get(text, "count"))
            self.update_properties(node)
        mode_combo.currentTextChanged.connect(on_mode_changed)
        config_layout.addWidget(BodyLabel("循环模式:"))
        config_layout.addWidget(mode_combo)
        current_mode = node.model.get_property("loop_mode")
        if current_mode == 'count':
            max_iter_spin = SpinBox(self)
            max_iter_spin.setRange(1, 10000)
            current_max = node.model.get_property("loop_nums")
            max_iter_spin.setValue(current_max)
            def on_max_iter_changed(value):
                node.model.set_property('loop_nums', value)
            max_iter_spin.valueChanged.connect(on_max_iter_changed)
            config_layout.addWidget(BodyLabel("循环次数:"))
            config_layout.addWidget(max_iter_spin)
        else:
            condition_edit = LineEdit(self)
            condition_edit.setPlaceholderText("请输入条件表达式")
            current_condition = node.model.get_property("loop_condition")
            condition_edit.setText(current_condition)
            def on_condition_changed(text):
                node.model.set_property('loop_condition', text)
            condition_edit.textChanged.connect(on_condition_changed)
            config_layout.addWidget(BodyLabel("条件表达式:"))
            config_layout.addWidget(condition_edit)
            max_iter_spin = SpinBox(self)
            max_iter_spin.setRange(1, 10000)
            current_max_iter = node.model.get_property("max_iterations")
            max_iter_spin.setValue(current_max_iter)
            def on_max_iterations_changed(value):
                node.model.set_property('max_iterations', value)
            max_iter_spin.valueChanged.connect(on_max_iterations_changed)
            config_layout.addWidget(BodyLabel("最大迭代次数:"))
            config_layout.addWidget(max_iter_spin)
        self.node_vbox.addWidget(config_card)

    def _add_internal_nodes_section(self, node):
        nodes_card = CardWidget(self)
        nodes_layout = QVBoxLayout(nodes_card)
        nodes_layout.setContentsMargins(10, 10, 10, 10)
        title = BodyLabel("内部节点")
        nodes_layout.addWidget(title)
        _, _, internal_nodes = node.get_nodes()
        if not internal_nodes:
            nodes_layout.addWidget(BodyLabel("暂无内部节点"))
        else:
            nodes_list = ListWidget(self)
            for n in internal_nodes:
                status = self.main_window.get_node_status(n)
                status_text = {
                    "running": "🟡 运行中",
                    "success": "🟢 成功",
                    "failed": "🔴 失败",
                    "unrun": "⚪ 未运行",
                    "pending": "🔵 待运行"
                }.get(status, status)
                item_text = f"{status_text} - {n.name()}"
                item = QListWidgetItem(item_text)
                nodes_list.addItem(item)
            nodes_layout.addWidget(nodes_list)
        self.node_vbox.addWidget(nodes_card)

    def _add_output_to_global_variable(self, node, port_name: str):
        value = node._output_values.get(port_name)
        if value is None:
            InfoBar.warning(
                title="警告",
                content=f"端口 {port_name} 当前无有效输出值",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT
            )
            return
        safe_node_name = re.sub(r'\s+', '_', node.name())
        var_name = f"{safe_node_name}_{port_name}"
        self.main_window.global_variables.set_output(
            node_id=safe_node_name, output_name=port_name, output_value=serialize_for_json(value)
        )
        self.main_window.global_variables_changed.emit("node_vars", var_name, "add")
        InfoBar.success(
            title="成功",
            content=f"已添加全局变量：{var_name}",
            parent=self.main_window,
            position=InfoBarPosition.TOP_RIGHT
        )

    # ========================
    # 全局变量面板（只构建一次）
    # ========================
    def _show_global_variables_panel(self):
        if self._global_panel_built:
            return

        title = BodyLabel("🌍 全局变量")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.global_vbox.addWidget(title)

        self.global_segmented = SegmentedWidget(self)
        self.global_segmented.addItem('env', '环境变量')
        self.global_segmented.addItem('node', '节点变量')
        self.global_segmented.addItem('custom', '自定义变量')
        self.global_segmented.setCurrentItem('node')

        self.global_stacked = QStackedWidget(self)
        self.env_page = self._create_env_page()
        self.node_page = self._create_node_vars_page()
        self.custom_page = self._create_custom_vars_page()
        self.global_stacked.addWidget(self.env_page)
        self.global_stacked.addWidget(self.node_page)
        self.global_stacked.addWidget(self.custom_page)
        self.global_stacked.setCurrentIndex(1)

        self.global_segmented.currentItemChanged.connect(self._on_global_tab_changed)
        self.global_vbox.addWidget(self.global_segmented)
        self.global_vbox.addWidget(self.global_stacked)

        self._global_panel_built = True

    def _on_global_tab_changed(self, key):
        if key == 'env':
            index = 0
        elif key == 'node':
            index = 1
        else:
            index = 2
        self.global_stacked.setCurrentIndex(index)

    def _create_custom_vars_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = TransparentPushButton(text="自定义变量 (custom)", icon=get_icon("自定义变量"), parent=self)
        layout.addWidget(title)
        add_custom_btn = TransparentPushButton(text="新增自定义变量", parent=self, icon=FluentIcon.ADD)
        add_custom_btn.clicked.connect(self._add_new_custom_variable)
        layout.addWidget(add_custom_btn)
        self.custom_vars_container = QWidget()
        self.custom_vars_layout = QVBoxLayout(self.custom_vars_container)
        self.custom_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_vars_layout.setSpacing(6)
        layout.addWidget(self.custom_vars_container)

        layout.addStretch()
        self._refresh_custom_vars_page()
        return widget

    def _create_node_vars_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        title = TransparentPushButton(text="节点输出变量 (node_vars)", icon=get_icon("节点变量"), parent=self)
        layout.addWidget(title)
        self.node_vars_container = QWidget()
        self.node_vars_layout = QVBoxLayout(self.node_vars_container)
        self.node_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.node_vars_layout.setSpacing(8)
        layout.addWidget(self.node_vars_container)
        layout.addStretch(1)
        self._refresh_node_vars_page()
        return widget

    def _create_env_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = TransparentPushButton(text="环境变量 (env)", icon=get_icon("环境变量"), parent=self)
        layout.addWidget(title)
        add_env_btn = TransparentPushButton(text="新增环境变量", parent=self, icon=FluentIcon.ADD)
        add_env_btn.clicked.connect(self._add_new_env_variable)
        layout.addWidget(add_env_btn)
        self.env_vars_container = QWidget()
        self.env_vars_layout = QVBoxLayout(self.env_vars_container)
        self.env_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.env_vars_layout.setSpacing(6)
        layout.addWidget(self.env_vars_container)
        self._refresh_env_page()
        layout.addStretch()
        return widget

    # ========================
    # 全局变量 UI 构建（增量更新）
    # ========================
    def _refresh_custom_vars_page(self):
        # custom
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        current_custom = set(global_vars.custom.keys()) if hasattr(global_vars, 'custom') else set()
        existing_custom = set(self._custom_var_cards.keys())
        for name in current_custom - existing_custom:
            var_obj = global_vars.custom[name]
            card = self._create_dict_row(name, var_obj.value)
            self.custom_vars_layout.addWidget(card)
            self._custom_var_cards[name] = card
        for name in existing_custom - current_custom:
            card = self._custom_var_cards.pop(name)
            card.deleteLater()
        for name in current_custom & existing_custom:
            var_obj = global_vars.custom[name]
            card = self._custom_var_cards[name]
            if card.layout().count() >= 2:
                value_label = card.layout().itemAt(1).widget()
                if isinstance(value_label, BodyLabel):
                    try:
                        preview = json.dumps(var_obj.value, ensure_ascii=False, default=str)[:40] + "..." if isinstance(var_obj.value, (dict, list)) else str(var_obj.value)[:40]
                    except:
                        preview = "<无法预览>"
                    value_label.setText(preview)

    def _refresh_node_vars_page(self):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        # node_vars
        current_node_vars = set(global_vars.node_vars.keys()) if hasattr(global_vars, 'node_vars') else set()
        existing_node_vars = set(self._node_var_cards.keys())
        for name in current_node_vars - existing_node_vars:
            node_var_obj = global_vars.node_vars[name]
            card = self._create_variable_card(name, node_var_obj)
            self.node_vars_layout.addWidget(card)
            self._node_var_cards[name] = card
        for name in existing_node_vars - current_node_vars:
            card = self._node_var_cards.pop(name)
            card.deleteLater()
        for name in current_node_vars & existing_node_vars:
            node_var_obj = global_vars.node_vars[name]
            card = self._node_var_cards[name]
            if hasattr(card, 'strategy_combo'):
                combo = card.strategy_combo
                if combo.property("policy") != node_var_obj.update_policy:
                    combo.blockSignals(True)
                    combo.setCurrentText(node_var_obj.update_policy)
                    combo.blockSignals(False)
            if hasattr(card, 'tree_widget'):
                card.tree_widget.set_data(node_var_obj.value)

    def _refresh_env_page(self):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars or not hasattr(global_vars, 'env'):
            return
        all_env_vars = global_vars.env.get_all_env_vars()
        current_env = {k: v for k, v in all_env_vars.items() if k != 'start_time'}
        existing_env = set(self._env_var_cards.keys())
        for key in current_env.keys() - existing_env:
            card = self._create_env_var_row(key, current_env[key])
            self.env_vars_layout.addWidget(card)
            self._env_var_cards[key] = card
        for key in existing_env - current_env.keys():
            card = self._env_var_cards.pop(key)
            card.deleteLater()
        for key in current_env.keys() & existing_env:
            card = self._env_var_cards[key]
            value = current_env[key]
            if card.layout().count() >= 2:
                value_label = card.layout().itemAt(1).widget()
                if isinstance(value_label, BodyLabel):
                    try:
                        preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." if isinstance(value, (dict, list)) else str(value)[:40]
                    except:
                        preview = "<无法预览>"
                    value_label.setText(preview)
        if not current_env and self.env_vars_layout.count() == 0:
            self.env_vars_layout.addWidget(BodyLabel("暂无环境变量"))

    def _create_dict_row(self, name: str, value):
        card = CardWidget(self)
        card.setMaximumWidth(250)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        name_label = BodyLabel(f"{name}:")
        try:
            preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." if isinstance(value, (dict, list)) else str(value)[:40]
        except:
            preview = "<无法预览>"
        value_label = BodyLabel(preview)
        value_label.setStyleSheet("color: #888888;")
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(16, 16)
        del_btn.clicked.connect(lambda _, n=name: self._delete_custom_variable(n, 'custom'))
        layout.addWidget(name_label)
        layout.addWidget(value_label)
        layout.addStretch()
        layout.addWidget(del_btn)

        def show_context_menu(pos):
            current_val = self.main_window.global_variables.custom.get(name)
            current_val = current_val.value if current_val is not None else "<已删除>"
            menu = RoundMenu(parent=self)
            menu.addAction(Action("复制为表达式", triggered=lambda: self._copy_as_expression("custom", name)))
            menu.addAction(Action("编辑变量", triggered=lambda: self._edit_custom_variable(name, current_val)))
            menu.exec_(card.mapToGlobal(pos))
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    def _create_variable_card(self, name: str, node_var_obj):
        card = CardWidget(self)
        card.setMaximumWidth(250)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)
        title_layout = QHBoxLayout()
        title = BodyLabel(name)
        title_layout.addWidget(title)
        strategy_combo = TransparentDropDownToolButton(icon=get_icon(node_var_obj.update_policy), parent=self)
        strategy_combo.setProperty("policy", node_var_obj.update_policy)
        strategy_combo.setProperty("node_var_name", name)
        menu = RoundMenu(parent=strategy_combo)
        menu.addAction(
            Action(get_icon("固定"), '固定',
                   triggered=lambda checked=False, btn=strategy_combo: self._on_node_var_strategy_changed("固定", btn))
        )
        menu.addAction(
            Action(get_icon("更新"), '更新',
                   triggered=lambda checked=False, btn=strategy_combo: self._on_node_var_strategy_changed("更新", btn))
        )
        menu.addAction(
            Action(get_icon("追加"), '追加',
                   triggered=lambda checked=False, btn=strategy_combo: self._on_node_var_strategy_changed("追加", btn))
        )
        strategy_combo.setMenu(menu)
        title_layout.addStretch()
        title_layout.addWidget(strategy_combo)
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(16, 16)
        del_btn.clicked.connect(lambda _, n=name: self._delete_custom_variable(n, 'node_vars'))
        title_layout.addWidget(del_btn)
        layout.addLayout(title_layout)
        tree = VariableTreeWidget(node_var_obj.value, parent=self.main_window)
        tree.setMinimumHeight(80)
        tree.setMaximumHeight(120)
        layout.addWidget(tree)

        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(Action("复制为表达式", triggered=lambda: self._copy_as_expression("node_vars", name)))
            menu.exec_(card.mapToGlobal(pos))
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        card.strategy_combo = strategy_combo
        card.tree_widget = tree
        card.node_var_name = name
        return card

    def _create_env_var_row(self, key: str, value):
        card = CardWidget(self)
        card.setMaximumWidth(250)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        name_label = BodyLabel(f"{key} : ")
        try:
            preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." if isinstance(value, (dict, list)) else str(value)[:40]
        except:
            preview = "<无法预览>"
        value_label = BodyLabel(preview)
        value_label.setStyleSheet("color: #888888;")
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(16, 16)
        del_btn.clicked.connect(lambda _, k=key: self._delete_env_variable(k))
        layout.addWidget(name_label)
        layout.addWidget(value_label)
        layout.addStretch()
        layout.addWidget(del_btn)

        def show_context_menu(pos):
            current_val = getattr(self.main_window.global_variables.env, key, None)
            menu = RoundMenu(parent=self)
            menu.addAction(Action("复制为表达式", triggered=lambda: self._copy_as_expression("env", key)))
            menu.addAction(Action("编辑变量", triggered=lambda: self._edit_env_variable(key, current_val)))
            menu.exec_(card.mapToGlobal(pos))
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    # ========================
    # 全局变量操作
    # ========================
    def _delete_custom_variable(self, var_name: str, var_type: str):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        try:
            if var_type == 'custom' and hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                del global_vars.custom[var_name]
            elif var_type == 'node_vars' and hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
                del global_vars.node_vars[var_name]
            self._refresh_custom_vars_page()
            self.main_window.global_variables_changed.emit(var_type, var_name, "delete")
            InfoBar.success("已删除", f"变量 '{var_name}' 已移除", parent=self.main_window, duration=1500)
        except Exception as e:
            InfoBar.error("删除失败", str(e), parent=self.main_window)

    def _on_node_var_strategy_changed(self, text: str, button: TransparentDropDownToolButton):
        button.setIcon(get_icon(text))
        var_name = button.property('node_var_name')
        if not var_name:
            return
        button.setProperty("policy", text)
        global_vars = getattr(self.main_window, 'global_variables', None)
        if global_vars and hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
            global_vars.node_vars[var_name].update_policy = text

    def _add_new_custom_variable(self):
        dialog = CustomTwoInputDialog(
            title1="变量名",
            title2="变量值",
            placeholder1="变量名（如 threshold）",
            placeholder2="变量值（如 0.5）",
            parent=self.main_window
        )
        if dialog.exec():
            name, value_str = dialog.get_text()
            if not name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            try:
                if value_str.lower() in ('true', 'false'):
                    value = value_str.lower() == 'true'
                elif '.' in value_str:
                    value = float(value_str)
                else:
                    value = int(value_str)
            except ValueError:
                value = value_str
            global_vars = getattr(self.main_window, 'global_variables', None)
            if global_vars:
                global_vars.set(name, value)
                self._refresh_custom_vars_page()
                self.main_window.global_variables_changed.emit("custom", name, "add")
                InfoBar.success("已添加", f"自定义变量 {name}", parent=self.main_window)

    def _add_new_env_variable(self):
        dialog = CustomTwoInputDialog(
            title1="环境变量名",
            title2="环境变量值",
            placeholder1="变量名（如 API_KEY）",
            placeholder2="变量值",
            parent=self.main_window
        )
        if dialog.exec():
            name, value = dialog.get_text()
            if not name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            global_vars = getattr(self.main_window, 'global_variables', None)
            if global_vars:
                global_vars.env.set_env_var(name, value)
                self._refresh_env_page()
                self.main_window.global_variables_changed.emit("env", name, "add")
                InfoBar.success("已添加", f"环境变量 {name}", parent=self.main_window)

    def _delete_env_variable(self, key: str):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        global_vars.env.delete_env_var(key)
        self._refresh_env_page()
        self.main_window.global_variables_changed.emit("env", key, "delete")
        InfoBar.success("已删除", f"环境变量 {key}", parent=self.main_window, duration=1500)

    def _copy_as_expression(self, prefix: str, var_name: str):
        var_name = re.sub(r'\s+', '_', var_name)
        expr = f"${prefix}.{var_name}$"
        clipboard = QApplication.clipboard()
        clipboard.setText(expr)
        InfoBar.success(
            title="已复制",
            content=f"表达式已复制：{expr}",
            parent=self.main_window,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500
        )

    def _edit_custom_variable(self, var_name: str, current_value):
        dialog = CustomTwoInputDialog(
            title1="变量名",
            title2="变量值",
            placeholder1="变量名（如 threshold）",
            placeholder2="变量值（如 0.5）",
            text1=var_name,
            text2=str(current_value),
            parent=self.main_window
        )
        if dialog.exec():
            new_name, new_value_str = dialog.get_text()
            if not new_name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            if new_name == var_name and new_value_str == str(current_value):
                return
            try:
                if new_value_str.lower() in ('true', 'false'):
                    new_value = new_value_str.lower() == 'true'
                elif '.' in new_value_str:
                    new_value = float(new_value_str)
                else:
                    new_value = int(new_value_str)
            except ValueError:
                new_value = new_value_str
            global_vars = getattr(self.main_window, 'global_variables', None)
            if not global_vars:
                return
            if new_name != var_name and var_name in global_vars.custom:
                del global_vars.custom[var_name]
                self.main_window.global_variables_changed.emit("custom", var_name, "delete")
                self.main_window.global_variables_changed.emit("custom", new_name, "add")
            global_vars.set(new_name, new_value)
            self._refresh_custom_vars_page()
            InfoBar.success("已更新", f"变量 {new_name}", parent=self.main_window)

    def _edit_env_variable(self, key: str, current_value):
        dialog = CustomTwoInputDialog(
            title1="环境变量名",
            title2="环境变量值",
            placeholder1="变量名（如 API_KEY）",
            placeholder2="变量值",
            text1=key,
            text2=str(current_value) if current_value is not None else "",
            parent=self.main_window
        )
        if dialog.exec():
            new_key, new_value = dialog.get_text()
            if not new_key:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            if new_key == key and new_value == current_value:
                return
            global_vars = getattr(self.main_window, 'global_variables', None)
            if not global_vars:
                return
            if new_key != key:
                global_vars.env.delete_env_var(key)
                self.main_window.global_variables_changed.emit("env", key, "delete")
                self.main_window.global_variables_changed.emit("env", new_key, "add")
            try:
                global_vars.env.set_env_var(new_key, new_value)
            except Exception as e:
                InfoBar.error("设置环境变量失败", f"错误信息：{e.__str__()}", parent=self.main_window)
                return
            self._refresh_env_page()
            InfoBar.success("已更新", f"环境变量 {new_key}", parent=self.main_window)