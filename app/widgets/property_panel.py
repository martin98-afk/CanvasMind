# -*- coding: utf-8 -*-
import json
import os

import pandas as pd
from loguru import logger
from NodeGraphQt import BackdropNode
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QFrame, QFileDialog, QListWidgetItem, QWidget, \
    QStackedWidget, QHBoxLayout
from qfluentwidgets import CardWidget, BodyLabel, PushButton, ListWidget, SmoothScrollArea, SegmentedWidget

from app.components.base import ArgumentType
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

    def update_properties(self, node):
        if node is None or node.type_.startswith("control_flow"):
            return
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
                    elif hasattr(widget, 'currentTextChanged') and widget.receivers(widget.currentTextChanged) > 0:
                        widget.currentTextChanged.disconnect()
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
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        self.vbox.addWidget(title)

        # 2. 节点描述
        description = self.get_node_description(node)
        if description and description.strip():
            desc_label = BodyLabel(f"📝 {description}")
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #888888; font-size: 12px;")
            self.vbox.addWidget(desc_label)

        self._add_seperator()

        # 创建导航栏和堆叠窗口
        self.segmented_widget = SegmentedWidget()

        # 添加导航项 - 使用正确的参数
        self.segmented_widget.addItem('input', '输入端口')
        self.segmented_widget.addItem('output', '输出端口')

        self.stacked_widget = QStackedWidget()

        # 添加输入端口页面
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        # 输入端口内容
        input_layout.addWidget(BodyLabel("📥 输入端口:"))
        input_ports_info = self.get_node_input_ports_info(node)

        if input_ports_info:
            for input_port, port_def in zip(node.input_ports(), node.component_class.inputs):
                port_display = f"{port_def.label} ({port_def.name})"
                input_layout.addWidget(BodyLabel(f"  • {port_display}"))

                # 获取原始上游数据（用于列选择）
                connected = input_port.connected_ports()
                original_upstream_data = None
                if len(connected) == 1:
                    upstream_out = connected[0]
                    upstream_node = upstream_out.node()
                    original_upstream_data = upstream_node.get_output_value(upstream_out.name())
                else:
                    original_upstream_data = [
                        upstream.node().get_output_value(upstream.name()) for upstream in connected
                    ]
                port_type = getattr(port_def, 'type', ArgumentType.TEXT)

                # 根据端口类型添加不同的控件
                if port_type == ArgumentType.CSV:
                    # CSV类型：显示列选择控件
                    self._add_column_selector_widget_to_layout(node, port_def.name, original_upstream_data,
                                                               original_upstream_data, input_layout)
                    # 显示当前选中的数据（用于执行）
                    current_selected_data = self._get_current_input_value(node, port_def.name, original_upstream_data)
                    self._add_text_edit_to_layout(
                        current_selected_data, port_type=port_type, port_name=port_def.name, layout=input_layout
                    )
                else:
                    # 普通数据：直接显示上游数据或当前输入值
                    if connected:
                        display_data = original_upstream_data
                    else:
                        display_data = node._input_values.get(port_def.name, "暂无数据")
                    try:
                        if not isinstance(display_data, str) or display_data != "暂无数据":
                            display_data = port_type.serialize(display_data) if len(connected) <= 1 else \
                                [port_type.serialize(data) for data in original_upstream_data]
                        self._add_text_edit_to_layout(
                            display_data, port_type=port_type, port_name=port_def.name, layout=input_layout
                        )
                    except:
                        import traceback
                        traceback.print_exc()
                        logger.error(f"无法解析输入数据：{display_data}")
                        display_data = "暂无数据"

        else:
            input_layout.addWidget(BodyLabel("  无输入端口"))

        input_layout.addStretch(1)

        # 添加输出端口页面
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)

        # 输出端口内容
        output_layout.addWidget(BodyLabel("📤 输出端口:"))
        output_ports = node.component_class.outputs
        if output_ports:
            result = node._output_values
            for port_def in output_ports:
                port_name = port_def.name
                port_label = port_def.label
                output_layout.addWidget(BodyLabel(f"  • {port_label} ({port_name})"))

                display_data = result.get(port_name) if result and port_name in result else "暂无数据"
                port_type = getattr(port_def, 'type', ArgumentType.TEXT)

                # 根据端口类型添加不同的控件
                if port_type == ArgumentType.UPLOAD:
                    self._add_upload_widget_to_layout(node, port_def.name, output_layout)
                try:
                    if isinstance(display_data, str) and display_data != "暂无数据":
                        display_data = port_type.serialize(display_data)
                except:
                    import traceback
                    traceback.print_exc()
                    logger.error(f"无法解析输出数据：{display_data}")
                    display_data = "暂无数据"

                self._add_text_edit_to_layout(display_data, port_name=port_def.name, layout=output_layout)
        else:
            output_layout.addWidget(BodyLabel("  无输出端口"))

        output_layout.addStretch(1)

        # 添加页面到堆叠窗口
        self.stacked_widget.addWidget(input_widget)
        self.stacked_widget.addWidget(output_widget)

        # 连接导航栏信号
        self.segmented_widget.currentItemChanged.connect(self._on_segmented_changed)

        # 添加导航栏和堆叠窗口到主布局
        self.vbox.addWidget(self.segmented_widget)
        self.vbox.addWidget(self.stacked_widget)

        # 默认显示输入端口
        self.segmented_widget.setCurrentItem('input')

    def _add_seperator(self):
        # 添加分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        self.vbox.addWidget(separator)

    def _on_segmented_changed(self, item_key):
        """导航栏切换事件"""
        if item_key == 'input':
            self.stacked_widget.setCurrentIndex(0)
        elif item_key == 'output':
            self.stacked_widget.setCurrentIndex(1)

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

    def _add_column_selector_widget_to_layout(self, node, port_name, data, original_data, layout):
        """优化：使用 CardWidget 分组 + 全选/清空按钮 + 更清晰的视觉层次"""
        if not isinstance(data, pd.DataFrame) or data.empty:
            return

        columns = list(data.columns)
        if not columns:
            return

        # === 创建列选择卡片 ===
        column_card = CardWidget(self)
        column_card.setFixedHeight(220)  # 留出按钮空间
        card_layout = QVBoxLayout(column_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.setSpacing(8)

        # 标题
        title_label = BodyLabel("列选择:")
        card_layout.addWidget(title_label)

        # 列表
        list_widget = ListWidget(self)
        list_widget.setSelectionMode(ListWidget.NoSelection)
        list_widget.setFixedHeight(140)

        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            list_widget.addItem(item)

        # 恢复选中状态
        selected_columns = node.column_select.get(port_name, [])
        if not selected_columns and columns:
            # 默认全选（更符合用户预期）
            selected_columns = columns.copy()
            node.column_select[port_name] = selected_columns

        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setCheckState(Qt.Checked if item.text() in selected_columns else Qt.Unchecked)

        card_layout.addWidget(list_widget)

        # 操作按钮
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
            # 更新下方数据预览
            self._update_text_edit_for_port(port_name, data[current_selected])

        select_all_btn.clicked.connect(select_all)
        clear_btn.clicked.connect(clear_all)
        list_widget.itemChanged.connect(_on_selection_changed)

        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(clear_btn)
        card_layout.addLayout(btn_layout)

        layout.addWidget(column_card)
        self._column_list_widgets[port_name] = list_widget

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

    def _add_text_edit_to_layout(self, text, port_type=None, port_name=None, layout=None):
        """添加文本编辑控件到指定布局"""
        info_card = CardWidget(self)
        card_layout = QVBoxLayout(info_card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        # 标题
        title_label = BodyLabel("数据信息:")
        card_layout.addWidget(title_label)

        tree_widget = VariableTreeWidget(text, port_type, parent=self.main_window)
        card_layout.addWidget(tree_widget)
        if layout is None:
            layout = self.vbox
        layout.addWidget(info_card)
        if port_name is not None:
            self._text_edit_widgets[port_name] = tree_widget
        return tree_widget

    def _add_text_edit(self, text, port_name=None):
        """兼容旧方法"""
        return self._add_text_edit_to_layout(text, port_name)

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

    def _add_upload_widget_to_layout(self, node, port_name, layout):
        """添加上传文件控件到指定布局"""
        upload_widget = QWidget()
        upload_layout = QVBoxLayout(upload_widget)
        upload_layout.setSpacing(4)
        upload_layout.setContentsMargins(0, 0, 0, 0)

        upload_button = PushButton("📁 上传文件", self)
        upload_button.clicked.connect(lambda _, p=port_name, n=node: self._select_upload_file(p, n))
        upload_layout.addWidget(upload_button)

        layout.addWidget(upload_widget)

    def _select_upload_file(self, port_name, node):
        """选择上传文件"""
        current_path = node._output_values.get(port_name, "")
        directory = os.path.dirname(current_path) if current_path else ""

        file_path, _ = QFileDialog.getOpenFileName(
            self, "上传文件", directory, "All Files (*)"
        )
        if file_path:
            node._output_values[port_name] = file_path

        self.update_properties(node)

    def _add_file_widget_to_layout(self, node, port_name, layout):
        """添加文件选择控件到指定布局（用于输出端口）"""
        select_file_button = PushButton("📁 选择文件", self)
        select_file_button.clicked.connect(lambda _, p=port_name, n=node: self._select_output_file(p, n))
        layout.addWidget(select_file_button)

    def _select_output_file(self, port_name, node):
        """选择输出文件（用于UPLOAD类型输出端口）"""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "All Files (*)")
        if file_path:
            self._update_output_file(node, port_name, file_path)

    def _update_output_file(self, node, port_name, file_path):
        node._output_values[port_name] = file_path
        # 更新显示
        if port_name in self._text_edit_widgets:
            self._text_edit_widgets[port_name].set_data(file_path)

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