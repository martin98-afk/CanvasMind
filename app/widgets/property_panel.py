# -*- coding: utf-8 -*-
import json
import os

import pandas as pd
from NodeGraphQt import BaseNode
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QVBoxLayout, QFrame, QFileDialog, QListWidgetItem, QWidget, \
    QStackedWidget, QHBoxLayout, QApplication
from loguru import logger
from qfluentwidgets import CardWidget, BodyLabel, PushButton, ListWidget, SmoothScrollArea, SegmentedWidget, \
    ProgressBar, FluentIcon, InfoBar, InfoBarPosition, TransparentToolButton, RoundMenu, Action

from app.components.base import ArgumentType
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.utils.utils import serialize_for_json
from app.widgets.dialog_widget.custom_messagebox import CustomTwoInputDialog
from app.widgets.tree_widget.variable_tree import VariableTreeWidget


class PropertyPanel(CardWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setFixedWidth(280)

        # 使用 qfluentwidgets 的 SmoothScrollArea
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 内容容器
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")

        self.vbox = QVBoxLayout(self.content_widget)
        self.vbox.setContentsMargins(20, 20, 20, 20)
        self.vbox.setSpacing(8)

        self.scroll_area.setWidget(self.content_widget)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.scroll_area)

        self.current_node = None
        self._column_list_widgets = {}
        self._text_edit_widgets = {}
        # 添加导航栏和堆叠窗口
        self.segmented_widget = None
        self.stacked_widget = None
        # 缓存全局变量面板的当前 tab
        self._current_global_tab = 'custom'

    def _clear_layout(self, keep_global_segment=False):
        """
        清理布局中的所有控件
        :param keep_global_segment: 是否保留全局变量面板的当前 tab（用于局部刷新）
        """
        if not keep_global_segment:
            self._column_list_widgets.clear()
            self._text_edit_widgets.clear()

        while self.vbox.count():
            child = self.vbox.takeAt(0)
            if child.widget():
                widget = child.widget()
                try:
                    if hasattr(widget, 'clicked') and widget.receivers(widget.clicked) > 0:
                        widget.clicked.disconnect()
                    elif hasattr(widget, 'itemChanged') and widget.receivers(widget.itemChanged) > 0:
                        widget.itemChanged.disconnect()
                    elif hasattr(widget, 'currentTextChanged') and widget.receivers(widget.currentTextChanged) > 0:
                        widget.currentTextChanged.disconnect()
                except (TypeError, RuntimeError):
                    pass
                widget.deleteLater()

        # 清理全局变量相关控件（除非保留）
        if not keep_global_segment:
            if hasattr(self, 'global_segmented'):
                self.global_segmented.deleteLater()
                del self.global_segmented
            if hasattr(self, 'global_stacked'):
                self.global_stacked.deleteLater()
                del self.global_stacked

    def get_port_info(self, node, is_input=True):
        """
        获取端口信息列表，兼容原生节点和 component_class 节点
        返回: [(port_name, port_label, port_type), ...]
        """
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
                    # component_class 定义了但图中无此端口（罕见）
                    result.append((port_name, port_name, ArgumentType.TEXT))
            # 补充 component_class 未覆盖的端口（如动态添加）
            for port in ports:
                if port.name() not in [r[0] for r in result]:
                    result.append((port.name(), port.name(), ArgumentType.TEXT))
            return result
        else:
            # 纯原生节点：只有端口名，类型默认 TEXT
            return [(p.name(), p.name(), ArgumentType.TEXT) for p in ports]

    def update_properties(self, node):
        # === 判断是否为同一个普通节点（非 Backdrop）===
        is_same_node = (
            node is not None
            and node is self.current_node
            and not isinstance(node, ControlFlowBackdrop)
        )

        if is_same_node:
            # ✅ 只更新数据，不重建 UI
            self._update_existing_node_data(node)
            return

        # === 不同节点：重建 UI ===
        current_segment = None
        if self.segmented_widget:
            current_segment = self.segmented_widget.currentRouteKey()

        if hasattr(self, 'global_segmented'):
            self._current_global_tab = self.global_segmented.currentRouteKey()

        self._clear_layout()

        self.current_node = node
        if not node:
            self._show_global_variables_panel()
            return

        elif isinstance(node, ControlFlowBackdrop):
            self._update_control_flow_properties(node)
        elif isinstance(node, BaseNode):
            self._build_node_ui(node, current_segment)

    def _build_node_ui(self, node, current_segment=None):
        # 确保节点有必要的属性
        if not hasattr(node, '_input_values'):
            node._input_values = {}
        if not hasattr(node, 'column_select'):
            node.column_select = {}
        # 1. 节点标题
        title = BodyLabel(f"📌 {node.name()}")
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.vbox.addWidget(title)

        # 2. 节点描述
        description = self.get_node_description(node)
        if description and description.strip():
            desc_label = BodyLabel(f"📝 {description}")
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #888888; font-size: 16px;")
            self.vbox.addWidget(desc_label)

        self._add_seperator()

        # 创建导航栏和堆叠窗口
        self.segmented_widget = SegmentedWidget()
        self.segmented_widget.addItem('input', '输入端口')
        self.segmented_widget.addItem('output', '输出端口')

        self.stacked_widget = QStackedWidget()

        # === 输入端口页面 ===
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        self._populate_input_ports(node, input_layout)
        input_layout.addStretch(1)
        self.stacked_widget.addWidget(input_widget)

        # === 输出端口页面 ===
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        self._populate_output_ports(node, output_layout)
        output_layout.addStretch(1)
        self.stacked_widget.addWidget(output_widget)

        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)
        self.vbox.addWidget(self.segmented_widget)
        self.vbox.addWidget(self.stacked_widget)

        if current_segment in ['input', 'output']:
            self.segmented_widget.setCurrentItem(current_segment)
        else:
            self.segmented_widget.setCurrentItem('input')

    def _update_existing_node_data(self, node):
        """仅更新当前节点的数据内容，不重建 UI"""
        # 更新输入端口
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

            # 更新列选择器
            if port_name in self._column_list_widgets:
                list_widget = self._column_list_widgets[port_name]
                if isinstance(original_data, pd.DataFrame) and not original_data.empty:
                    current_columns = list(original_data.columns)
                    existing_items = [list_widget.item(i).text() for i in range(list_widget.count())]
                    if set(current_columns) != set(existing_items):
                        # 列结构变化，需重建 UI
                        self.update_properties(node)
                        return
                    selected_columns = node.column_select.get(port_name, [])
                    for i in range(list_widget.count()):
                        item = list_widget.item(i)
                        item.setCheckState(Qt.Checked if item.text() in selected_columns else Qt.Unchecked)

            current_selected_data = self._get_current_input_value(node, port_name, original_data)
            self._update_text_edit_for_port(port_name, current_selected_data)

        # 更新输出端口
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

            # === 关键：不要 serialize！直接使用原始数据 ===
            if port_type == ArgumentType.CSV and isinstance(original_data, pd.DataFrame) and not original_data.empty:
                self._add_column_selector_widget_to_layout(node, port_name, original_data, original_data, layout)
                current_selected_data = self._get_current_input_value(node, port_name, original_data)
            else:
                current_selected_data = original_data  # ← 原始数据！

            # 直接传给 VariableTreeWidget
            self._add_text_edit_to_layout(
                current_selected_data,
                port_type=port_type,
                port_name=port_name,
                layout=layout
            )

    def _populate_output_ports(self, node, layout):
        port_infos = self.get_port_info(node, is_input=False)
        if not port_infos:
            layout.addWidget(BodyLabel("  无输出端口"))
            return

        for port_name, port_label, port_type in port_infos:
            layout.addWidget(BodyLabel(f"  • {port_label} ({port_name}): {port_type.value}"))

            # 获取原始数据（不要 serialize！）
            display_data = node._output_values.get(port_name)
            if display_data is None:
                try:
                    display_data = node.model.get_property(port_name)
                except KeyError:
                    display_data = "暂无数据"

            # 特殊控件（如上传）
            if port_type == ArgumentType.UPLOAD:
                self._add_upload_widget_to_layout(node, port_name, layout)

            # ✅ 直接传原始数据 + port_type 给 VariableTreeWidget
            self._add_text_edit_to_layout(
                display_data,
                port_type=port_type,
                port_name=port_name,
                layout=layout,
                node=node,
                is_output=True
            )

    def _add_seperator(self):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        self.vbox.addWidget(separator)

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
        info_card = CardWidget(self)
        info_card.setMaximumHeight(300)
        card_layout = QVBoxLayout(info_card)
        card_layout.setContentsMargins(4, 4, 4, 4)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_text = "数据信息:"
        title_label = BodyLabel(title_text)
        title_layout.addWidget(title_label)

        if is_output and node is not None:
            add_global_btn = PushButton(text="全局变量", icon=FluentIcon.ADD, parent=self)
            add_global_btn.clicked.connect(
                lambda _, n=node, p=port_name: self._add_output_to_global_variable(n, p)
            )
            title_layout.addStretch()
            title_layout.addWidget(add_global_btn)

        card_layout.addLayout(title_layout)

        tree_widget = VariableTreeWidget(text, port_type, parent=self.main_window)
        card_layout.addWidget(tree_widget)

        if layout is None:
            layout = self.vbox
        layout.addWidget(info_card)

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
    # ControlFlowBackdrop 相关（保持不变）
    # ========================
    def _update_control_flow_properties(self, node):
        title = BodyLabel(f"🔁 {node.NODE_NAME}")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.vbox.addWidget(title)

        flow_type = getattr(node, 'TYPE', 'unknown')
        type_label = BodyLabel(f"类型: {'循环' if flow_type == 'loop' else '迭代'}")
        self.vbox.addWidget(type_label)

        current = node.model.get_property('current_index')
        if flow_type == "loop":
            total = node.model.get_property("loop_nums")
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

        progress_label = BodyLabel(f"进度: {current}/{total}")
        progress_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        progress_bar = ProgressBar(self, useAni=False)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(int(current / max(1, total) * 100))
        self.vbox.addWidget(progress_label)
        self.vbox.addWidget(progress_bar)
        if flow_type == "loop":
            self._add_seperator()
            self._add_loop_config_section(node)
        self._add_seperator()
        self._add_internal_nodes_section(node)
        self.vbox.addStretch()

    def _add_loop_config_section(self, node):
        config_card = CardWidget(self)
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(10, 10, 10, 10)

        title = BodyLabel("循环配置")
        config_layout.addWidget(title)

        from qfluentwidgets import SpinBox
        max_iter_spin = SpinBox(self)
        max_iter_spin.setRange(1, node.model.get_property("max_iterations"))
        current_max = node.model.get_property("loop_nums")
        max_iter_spin.setValue(current_max)

        def on_max_iter_changed(value):
            node.model.set_property('loop_nums', value)
            self.update_properties(node)

        max_iter_spin.valueChanged.connect(on_max_iter_changed)

        config_layout.addWidget(BodyLabel("最大迭代次数:"))
        config_layout.addWidget(max_iter_spin)

        self.vbox.addWidget(config_card)

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

        self.vbox.addWidget(nodes_card)

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

        safe_node_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in node.name())
        var_name = f"{safe_node_name}__{port_name}"

        self.main_window.global_variables.set_output(
            node_id=safe_node_name, output_name=port_name, output_value=serialize_for_json(value)
        )
        self.main_window.global_variables_changed.emit()
        InfoBar.success(
            title="成功",
            content=f"已添加全局变量：{var_name}",
            parent=self.main_window,
            position=InfoBarPosition.TOP_RIGHT
        )

    # ========================
    # 全局变量面板（保持不变）
    # ========================

    def _show_global_variables_panel(self):
        self._clear_layout(keep_global_segment=True)

        title = BodyLabel("🌍 全局变量")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.vbox.addWidget(title)

        self.global_segmented = SegmentedWidget(self)
        self.global_segmented.addItem('env', '环境变量')
        self.global_segmented.addItem('custom', '自定义变量')

        self.global_stacked = QStackedWidget(self)
        env_page = self._create_env_page()
        custom_page = self._create_custom_vars_page()
        self.global_stacked.addWidget(env_page)
        self.global_stacked.addWidget(custom_page)

        self.global_segmented.currentItemChanged.connect(self._on_global_tab_changed)
        self.vbox.addWidget(self.global_segmented)
        self.vbox.addWidget(self.global_stacked)

        if self._current_global_tab in ['env', 'custom']:
            self.global_segmented.setCurrentItem(self._current_global_tab)
        else:
            self.global_segmented.setCurrentItem('custom')

    def _save_env_row(self, key_edit, value_edit):
        old_key = key_edit.property("env_key")
        new_key = key_edit.text().strip()
        new_value = value_edit.text().strip() or None

        if not new_key:
            InfoBar.warning("无效键", "键不能为空", parent=self.main_window)
            return

        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return

        env_dict = global_vars.env.model_dump()

        if old_key and old_key != new_key and old_key in env_dict:
            delattr(global_vars.env, old_key)

        setattr(global_vars.env, new_key, new_value)

        key_edit.setProperty("env_key", new_key)
        value_edit.setProperty("env_key", new_key)
        self.main_window.global_variables_changed.emit()
        InfoBar.success("已保存", f"环境变量 {new_key}", parent=self.main_window, duration=1500)

    def _refresh_custom_vars_page(self):
        while self.custom_vars_layout.count():
            child = self.custom_vars_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        while self.node_vars_layout.count():
            child = self.node_vars_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            self.custom_vars_layout.addWidget(BodyLabel("全局变量未初始化"))
            self.node_vars_layout.addWidget(BodyLabel("全局变量未初始化"))
            return

        if hasattr(global_vars, 'custom'):
            custom_vars = global_vars.custom
            if custom_vars:
                for name, var_obj in custom_vars.items():
                    row = self._create_dict_row(name, var_obj.value)
                    self.custom_vars_layout.addWidget(row)
            else:
                self.custom_vars_layout.addWidget(BodyLabel("暂无自定义变量"))
        else:
            self.custom_vars_layout.addWidget(BodyLabel("custom 未定义"))

        if hasattr(global_vars, 'node_vars'):
            node_vars = global_vars.node_vars
            if node_vars:
                for name, value in node_vars.items():
                    card = self._create_variable_card(name, value)
                    self.node_vars_layout.addWidget(card)
                    self.node_vars_layout.addStretch()
            else:
                self.node_vars_layout.addWidget(BodyLabel("暂无节点输出变量"))
        else:
            self.node_vars_layout.addWidget(BodyLabel("node_vars 未定义"))

    def _create_dict_row(self, name: str, value):
        card = CardWidget(self)
        card.setMaximumWidth(250)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        name_label = BodyLabel(f"{name}:")

        try:
            if isinstance(value, (dict, list)):
                preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..."
            else:
                preview = str(value)[:40]
        except:
            preview = "<无法预览>"

        value_label = BodyLabel(preview)
        value_label.setStyleSheet("color: #888888;")

        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.setIconSize(QSize(8, 8))
        del_btn.clicked.connect(lambda _, n=name: self._delete_custom_variable(n, 'custom'))

        layout.addWidget(name_label)
        layout.addWidget(value_label)
        layout.addStretch()
        layout.addWidget(del_btn)

        # === 右键菜单：复制为 $custom.name$ ===
        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(
                Action("复制为表达式", triggered=lambda: self._copy_as_expression("custom", name))
            )
            menu.addAction(Action("编辑变量", triggered=lambda: self._edit_custom_variable(name, value)))
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)

        return card

    def _create_variable_card(self, name: str, value):
        card = CardWidget(self)
        card.setMaximumWidth(250)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title_layout = QHBoxLayout()
        title = BodyLabel(name)
        title_layout.addWidget(title)
        title_layout.addStretch()
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.setIconSize(QSize(8, 8))
        del_btn.clicked.connect(lambda _, n=name: self._delete_custom_variable(n, 'node_vars'))
        title_layout.addWidget(del_btn)
        layout.addLayout(title_layout)

        tree = VariableTreeWidget(value, parent=self.main_window)
        tree.setMinimumHeight(80)
        tree.setMaximumHeight(120)
        layout.addWidget(tree)

        # === 右键菜单：复制为 $node.name$ ===
        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(
                Action("复制为表达式", triggered=lambda: self._copy_as_expression("node_vars", name))
            )
            if menu.actions():
                menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)

        return card

    def _delete_custom_variable(self, var_name: str, var_type: str):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return

        try:
            if var_type == 'custom' and hasattr(global_vars, 'custom'):
                if var_name in global_vars.custom:
                    del global_vars.custom[var_name]
            elif var_type == 'node_vars' and hasattr(global_vars, 'node_vars'):
                if var_name in global_vars.node_vars:
                    del global_vars.node_vars[var_name]

            self._refresh_custom_vars_page()
            self.main_window.global_variables_changed.emit()
            InfoBar.success("已删除", f"变量 '{var_name}' 已移除", parent=self.main_window, duration=1500)
        except Exception as e:
            InfoBar.error("删除失败", str(e), parent=self.main_window)

    def _on_global_tab_changed(self, key):
        index = 0 if key == 'env' else 1
        self.global_stacked.setCurrentIndex(index)

    def _create_custom_vars_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        custom_title = BodyLabel("📝 自定义变量 (custom)")
        layout.addWidget(custom_title)

        add_custom_btn = PushButton(text="新增自定义变量", parent=self, icon=FluentIcon.ADD)
        add_custom_btn.clicked.connect(self._add_new_custom_variable)
        layout.addWidget(add_custom_btn)

        self.custom_vars_container = QWidget()
        self.custom_vars_layout = QVBoxLayout(self.custom_vars_container)
        self.custom_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_vars_layout.setSpacing(6)
        layout.addWidget(self.custom_vars_container)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        layout.addWidget(separator)

        node_title = BodyLabel("📤 节点输出变量 (node_vars)")
        layout.addWidget(node_title)

        self.node_vars_container = QWidget()
        self.node_vars_layout = QVBoxLayout(self.node_vars_container)
        self.node_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.node_vars_layout.setSpacing(8)
        layout.addWidget(self.node_vars_container)

        layout.addStretch()
        self._refresh_custom_vars_page()
        return widget

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
                self.main_window.global_variables_changed.emit()
                InfoBar.success("已添加", f"自定义变量 {name}", parent=self.main_window)

    def _create_env_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        add_env_btn = PushButton(text="新增环境变量", parent=self, icon=FluentIcon.ADD)
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

    def _refresh_env_page(self):
        while self.env_vars_layout.count():
            child = self.env_vars_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars or not hasattr(global_vars, 'env'):
            self.env_vars_layout.addWidget(BodyLabel("环境变量未初始化"))
            return

        all_env_vars = global_vars.env.get_all_env_vars()
        for key, value in all_env_vars.items():
            if key == 'start_time':
                continue
            card = self._create_env_var_row(key, value)
            self.env_vars_layout.addWidget(card)

    def _create_env_var_row(self, key: str, value):
        card = CardWidget(self)
        card.setMaximumWidth(250)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        name_label = BodyLabel(f"{key} : ")
        try:
            if isinstance(value, (dict, list)):
                preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..."
            else:
                preview = str(value)[:40]
        except:
            preview = "<无法预览>"

        value_label = BodyLabel(preview)
        value_label.setStyleSheet("color: #888888;")

        del_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        del_btn.setIconSize(QSize(8, 8))
        del_btn.clicked.connect(lambda _, k=key: self._delete_env_variable(k))

        layout.addWidget(name_label)
        layout.addWidget(value_label)
        layout.addStretch()
        layout.addWidget(del_btn)

        # === 添加右键菜单 ===
        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(
                Action("复制为表达式", triggered=lambda: self._copy_as_expression("env", key))
            )
            menu.addAction(Action("编辑变量", triggered=lambda: self._edit_env_variable(key, value)))
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)

        return card

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
                self.main_window.global_variables_changed.emit()
                InfoBar.success("已添加", f"环境变量 {name}", parent=self.main_window)

    def _delete_env_variable(self, key: str):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        global_vars.env.delete_env_var(key)
        self._refresh_env_page()
        self.main_window.global_variables_changed.emit()
        InfoBar.success("已删除", f"环境变量 {key}", parent=self.main_window, duration=1500)

    def _copy_as_expression(self, prefix: str, var_name: str):
        """将变量名复制为 $prefix.var_name$ 格式"""
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
        """编辑自定义变量"""
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

            # 类型推断（与新增逻辑一致）
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

            # 如果名字变了，先删除旧的
            if new_name != var_name and var_name in global_vars.custom:
                del global_vars.custom[var_name]

            global_vars.set(new_name, new_value)
            self._refresh_custom_vars_page()
            self.main_window.global_variables_changed.emit()
            InfoBar.success("已更新", f"变量 {new_name}", parent=self.main_window)

    def _edit_env_variable(self, key: str, current_value):
        """编辑环境变量"""
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

            global_vars = getattr(self.main_window, 'global_variables', None)
            if not global_vars:
                return

            # 删除旧 key（如果改名）
            if new_key != key:
                global_vars.env.delete_env_var(key)

            global_vars.env.set_env_var(new_key, new_value)
            self._refresh_env_page()
            self.main_window.global_variables_changed.emit()
            InfoBar.success("已更新", f"环境变量 {new_key}", parent=self.main_window)