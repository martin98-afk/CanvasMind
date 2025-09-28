import json
from typing import Union, List

import pandas as pd
from NodeGraphQt import BackdropNode
from PyQt5.QtWidgets import QVBoxLayout, QFrame, QPushButton, QFileDialog, QListWidget, QListWidgetItem, QWidget
from PyQt5.QtCore import Qt
from qfluentwidgets import CardWidget, BodyLabel, TextEdit, PushButton, ListWidget, SmoothScrollArea

from app.components.base import ArgumentType
from app.widgets.variable_tree import VariableTreeWidget


class PropertyPanel(CardWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setFixedWidth(280)
        # ✅ 使用 qfluentwidgets 的 SmoothScrollArea（自动适配深色主题）
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 不需要额外样式，SmoothScrollArea 自带主题

        # 内容容器：也建议用 qfluentwidgets 的组件，或至少设置背景
        self.content_widget = QWidget()
        # ✅ 关键：设置内容区域背景为透明或跟随主题
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

    def update_properties(self, node):
        # 清理旧的控件引用
        self._column_list_widgets.clear()
        self._text_edit_widgets.clear()

        # 清理布局中的所有控件
        while self.vbox.count():
            child = self.vbox.takeAt(0)
            if child.widget():
                widget = child.widget()
                try:
                    if hasattr(widget, 'clicked') and widget.receivers(widget.clicked) > 0:
                        widget.clicked.disconnect()
                    elif hasattr(widget, 'itemChanged') and widget.receivers(widget.itemChanged) > 0:
                        widget.itemChanged.disconnect()
                except (TypeError, RuntimeError):
                    pass
                widget.deleteLater()

        self.current_node = node
        if not node or isinstance(node, BackdropNode):
            label = BodyLabel("请选择一个节点查看详情。")
            self.vbox.addWidget(label)
            return

        # 确保节点有 _input_values 属性
        if not hasattr(node, '_input_values'):
            node._input_values = {}

        # 1. 节点标题
        title = BodyLabel(f"📌 {node.name()}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.vbox.addWidget(title)

        # 2. 节点描述
        description = self.get_node_description(node)
        if description and description.strip():
            desc_label = BodyLabel(f"📝 {description}")
            desc_label.setStyleSheet("color: #888888; font-size: 12px;")
            self.vbox.addWidget(desc_label)

        # 添加分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        self.vbox.addWidget(separator)

        # 4. 输入端口
        self.vbox.addWidget(BodyLabel("📥 输入端口:"))

        input_ports_info = self.get_node_input_ports_info(node)

        if input_ports_info:
            for input_port, port_def in zip(node.input_ports(), node.component_class.inputs):
                port_display = f"{port_def.label} ({port_def.name})"
                self.vbox.addWidget(BodyLabel(f"  • {port_display}"))

                # 获取原始上游数据（用于列选择）
                connected = input_port.connected_ports()
                original_upstream_data = None
                if connected:
                    upstream_out = connected[0]
                    upstream_node = upstream_out.node()
                    original_upstream_data = upstream_node.get_output_value(upstream_out.name())

                port_type = getattr(port_def, 'type', ArgumentType.TEXT)
                # 处理 CSV/DataFrame 列选择
                if isinstance(original_upstream_data, pd.DataFrame):
                    # 显示列选择控件
                    self._add_column_selector_widget(node, port_def.name, original_upstream_data,
                                                     original_upstream_data)

                    # 显示当前选中的数据（用于执行）
                    current_selected_data = self._get_current_input_value(node, port_def.name, original_upstream_data)
                    self._add_text_edit(port_type.to_dict(current_selected_data), port_name=port_def.name)
                else:
                    # 普通数据：直接显示上游数据或当前输入值
                    if connected:
                        display_data = original_upstream_data
                    else:
                        display_data = node._input_values.get(port_def.name, "暂无数据")
                    self._add_text_edit(port_type.to_dict(display_data), port_name=port_def.name)

        else:
            self.vbox.addWidget(BodyLabel("  无输入端口"))

        # 5. 输出端口
        self.vbox.addWidget(BodyLabel("📤 输出端口:"))
        output_ports = node.component_class.outputs
        if output_ports:
            result = node._output_values
            for port_def in output_ports:
                port_name = port_def.name
                port_label = port_def.label
                self.vbox.addWidget(BodyLabel(f"  • {port_label} ({port_name})"))

                output_data = result.get(port_name) if result and port_name in result else "暂无数据"
                port_type = getattr(port_def, 'type', ArgumentType.TEXT)
                if port_type.is_file():
                    self._add_file_widget(node, port_def.name)

                self._add_text_edit(port_type.to_dict(output_data), port_name=port_name)
        else:
            self.vbox.addWidget(BodyLabel("  无输出端口"))

        self.vbox.addStretch(1)

    def _get_current_input_value(self, node, port_name, original_data):
        """获取当前端口的输入值（考虑列选择）"""
        # 检查是否有列选择
        selected_columns = node._input_values.get(f"{port_name}_selected_columns", [])

        if selected_columns and isinstance(original_data, pd.DataFrame):
            try:
                if len(selected_columns) == 1:
                    return original_data[selected_columns[0]]
                else:
                    return original_data[selected_columns]
            except Exception as e:
                return f"列选择错误: {str(e)}"
        else:
            # 没有列选择，返回原始数据
            return original_data

    def _add_column_selector_widget(self, node, port_name, data, original_data):
        """添加多列选择控件 - 关键修复：正确保存和恢复状态"""
        columns = list(data.columns)
        if len(columns) == 0:
            return

        list_widget = ListWidget(self)
        list_widget.setSelectionMode(ListWidget.NoSelection)
        list_widget.setFixedHeight(180)  # ✅ 高度从 120 增至 180

        # 添加所有列作为复选框
        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            list_widget.addItem(item)

        # 关键修复：正确恢复选中状态
        selected_columns = node._input_values.get(f"{port_name}_selected_columns", [])

        # 如果没有选中任何列，不要默认选第一列！
        # 只有在第一次初始化时才默认选第一列
        if not selected_columns:
            # 检查是否是第一次初始化（没有上游数据变化）
            if hasattr(node, '_column_selector_initialized') and node._column_selector_initialized.get(port_name,
                                                                                                       False):
                # 已经初始化过，保持空选择
                selected_columns = []
            else:
                # 第一次初始化，选第一列
                if columns:
                    selected_columns = [columns[0]]
                    # 标记已初始化
                    if not hasattr(node, '_column_selector_initialized'):
                        node._column_selector_initialized = {}
                    node._column_selector_initialized[port_name] = True

        # 设置复选框状态
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.text() in selected_columns:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)

        # 更新节点的列选择状态（确保保存）
        node._input_values[f"{port_name}_selected_columns"] = selected_columns

        # 连接信号
        def on_item_changed(item):
            # 收集所有选中的列
            current_selected = []
            for i in range(list_widget.count()):
                item_i = list_widget.item(i)
                if item_i.checkState() == Qt.Checked:
                    current_selected.append(item_i.text())

            # 更新节点的列选择状态
            node._input_values[f"{port_name}_selected_columns"] = current_selected

            # 更新输入值
            self._update_input_value_for_port(node, port_name, original_data, current_selected)

            # 标记已初始化
            if not hasattr(node, '_column_selector_initialized'):
                node._column_selector_initialized = {}
            node._column_selector_initialized[port_name] = True

            # ✅ 关键优化：只更新文本框，不再调用 update_properties！
            selected_data = node._input_values.get(port_name, "未选择列")
            self._update_text_edit_for_port(port_name, selected_data)

        list_widget.itemChanged.connect(on_item_changed)
        self._column_list_widgets[port_name] = list_widget

        self.vbox.addWidget(BodyLabel("  列选择（可多选）:"))
        self.vbox.addWidget(list_widget)

    def _update_input_value_for_port(self, node, port_name, original_data, selected_columns):
        """更新指定端口的输入值"""
        if selected_columns and isinstance(original_data, pd.DataFrame):
            try:
                if len(selected_columns) == 1:
                    selected_data = original_data[selected_columns[0]]
                else:
                    selected_data = original_data[selected_columns]
            except Exception as e:
                selected_data = f"列选择错误: {str(e)}"
        else:
            selected_data = original_data if selected_columns else "未选择列"

        node._input_values[port_name] = selected_data

    def _add_text_edit(self, text, port_name=None):
        tree_widget = VariableTreeWidget(text)
        # tree_widget.previewRequested.connect(self._handle_preview_request)
        self.vbox.addWidget(tree_widget)
        if port_name is not None:
            self._text_edit_widgets[port_name] = tree_widget
        return tree_widget

    def _update_text_edit_for_port(self, port_name, new_value):
        """更新 VariableTreeWidget 的内容"""
        if port_name not in self._text_edit_widgets:
            return

        widget = self._text_edit_widgets[port_name]
        if isinstance(widget, VariableTreeWidget):
            widget.set_data(new_value)
        else:
            # 兼容旧 TextEdit（理论上不会走到这里）
            self._fallback_update_text_edit(widget, new_value)

    def _fallback_update_text_edit(self, edit, new_value):
        """旧 TextEdit 的 fallback 更新逻辑（保留）"""
        if new_value is None:
            display_text = "None"
        elif isinstance(new_value, str):
            display_text = new_value
        elif hasattr(new_value, '__dict__') and not isinstance(new_value, (list, tuple, dict)):
            try:
                # 修复：这里应该直接显示对象信息
                display_text = f"[{new_value.__class__.__name__}] {str(new_value)}"
            except:
                display_text = str(new_value)
        elif isinstance(new_value, (list, tuple, dict)):
            try:
                display_text = json.dumps(new_value, indent=2, ensure_ascii=False, default=str)
            except:
                display_text = str(new_value)
        else:
            display_text = str(new_value)
        edit.setPlainText(display_text)

    def _add_file_widget(self, node, port_name):
        select_file_button = PushButton("📁 选择文件", self)
        select_file_button.clicked.connect(lambda _, p=port_name, n=node: self._select_upload_file(p, n))
        self.vbox.addWidget(select_file_button)

    def _select_upload_file(self, port_name, node):
        if hasattr(node, 'component_class'):
            output_ports = node.component_class.outputs
            for port_def in output_ports:
                if port_def.name == port_name:
                    port_type = getattr(port_def, 'type', None)
                    if port_type:
                        if port_type == ArgumentType.CSV:
                            file_filter = "CSV Files (*.csv)"
                        elif port_type == ArgumentType.JSON:
                            file_filter = "JSON Files (*.json)"
                        elif port_type == ArgumentType.FOLDER:
                            folder_path = QFileDialog.getExistingDirectory(self, "选择文件夹", "")
                            if folder_path:
                                self._update_output_file(node, port_name, folder_path)
                            return
                        else:
                            file_filter = "All Files (*)"
                    break
            else:
                file_filter = "All Files (*)"
        else:
            file_filter = "All Files (*)"

        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", file_filter)
        if file_path:
            self._update_output_file(node, port_name, file_path)

    def _update_output_file(self, node, port_name, file_path):
        if not hasattr(node, '_input_values'):
            node._input_values = {}
        node._output_values[port_name] = file_path
        # 注意：这里如果需要更新输出显示，也可以局部更新，但通常不需要
        # 如果确实需要，可调用 self._update_text_edit_for_port(port_name, file_path)

    def _add_separator(self):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        self.vbox.addWidget(separator)

    def get_node_description(self, node):
        if hasattr(node, 'component_class'):
            return getattr(node.component_class, 'description', '')
        return ''

    def get_node_input_ports_info(self, node):
        if hasattr(node, 'component_class'):
            return node.component_class.get_inputs()
        ports_info = []
        for input_port in node.input_ports():
            port_name = input_port.name()
            ports_info.append((port_name, port_name))
        return ports_info

    def get_node_output_ports_info(self, node):
        if hasattr(node, 'component_class'):
            return node.component_class.get_outputs()
        ports_info = []
        for output_port in node.output_ports():
            port_name = output_port.name()
            ports_info.append((port_name, port_name))
        return ports_info