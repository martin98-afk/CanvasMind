# -*- coding: utf-8 -*-
import re

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget
from qfluentwidgets import CardWidget, BodyLabel, ProgressBar, TransparentToolButton, SubtitleLabel, StrongBodyLabel

from app.utils.utils import get_icon
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit
from app.widgets.node_widget.longtext_dialog import LongTextEditorDialog
from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList

# --- 导入新的 PortWidget ---
from app.widgets.side_dock_area.plugins.property_panel.port_widget import PortWidget


class FlowControlPanelWidget:
    """处理控制流节点（如循环、迭代）UI的子模块"""

    def __init__(self, main_window, parent_panel, parent_layout):
        self.main_window = main_window
        self.parent_panel = parent_panel  # PropertyPanel 的实例
        self.parent_layout = parent_layout  # PropertyPanel 中的 node_vbox

        # 用于更新现有Backdrop状态的缓存
        self._backdrop_progress_label = None
        self._backdrop_progress_bar = None
        self._backdrop_internal_nodes_list = None
        # --- 新增：用于缓存 PortWidget ---
        self._port_widget = None
        self.current_segment = None

    def build_port(self, node):
        # 创建新的 PortWidget 实例
        self._port_widget = PortWidget(
            main_window=self.main_window,
            parent_panel=self.parent_panel,  # 传递 PropertyPanel 实例
            node=node,
            port_info_func=self.parent_panel.get_port_info,  # 传递获取端口信息的函数
            copy_as_expression_func=self.parent_panel._copy_as_expression,  # 传递复制表达式的函数
            add_func=self.parent_panel._add_output_to_global_variable,  # 传递添加到全局变量的函数
            delete_func=self.parent_panel._delete_output_from_global_variable,
            is_in_func=self.parent_panel._is_output_in_global_variable,
            parent=self.parent_panel  # 传递父控件
        )
        self._port_widget.setMinimumHeight(180)
        self._port_widget.segmented_widget.currentItemChanged.connect(self._on_port_segment_changed)

    def build_ui(self, node, current_segment=None):
        """构建控制流节点UI"""
        # 1. 节点名称
        title = SubtitleLabel(f"🔁 {node.NODE_NAME}")
        self.parent_layout.addWidget(title)

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
        # 2. 控制流进度
        progress_label = StrongBodyLabel(f"进度: {current}/{total}")
        self.parent_layout.addWidget(progress_label)
        self._backdrop_progress_label = progress_label

        progress_bar = ProgressBar(self.parent_panel, useAni=False)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(int(current / max(1, total) * 100) if total > 0 else 0)
        self.parent_layout.addWidget(progress_bar)
        self._backdrop_progress_bar = progress_bar

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        # 3. 循环流配置
        if flow_type == "loop":
            self._add_loop_config_section(node, layout)
        # 4. 内部节点
        self._add_internal_nodes_section(node, layout)
        # 5. 输入输出端口
        self.build_port(node)
        # 根据 current_segment 设置 PortWidget 内部的分段控件状态
        if self.current_segment is not None:
            self._port_widget.segmented_widget.setCurrentItem(self.current_segment)
        elif hasattr(self._port_widget, 'segmented_widget'):
            if current_segment in ['input', 'output']:
                self._port_widget.segmented_widget.setCurrentItem(current_segment)
        layout.addWidget(self._port_widget, 1)
        scroll = self.parent_panel.set_scrollbar(widget)
        self.parent_layout.addWidget(scroll, 1)

    def _on_port_segment_changed(self, segment):
        """处理 PortWidget 的分段切换事件"""
        self.current_segment = segment

    def update_backdrop_data(self, node):
        """尝试更新现有 ControlFlowBackdrop 的状态。"""
        if not self._backdrop_progress_label or not self._backdrop_progress_bar or not self._backdrop_internal_nodes_list:
            return False

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
        else:
            total = 0

        self._backdrop_progress_label.setText(f"进度: {current}/{total}")
        progress_value = int(current / max(1, total) * 100) if total > 0 else 0
        self._backdrop_progress_bar.setValue(progress_value)

        if self._backdrop_internal_nodes_list:
            _, _, internal_nodes = node.get_nodes()
            new_status_list = [self.main_window.get_node_status(n) for n in internal_nodes]
            new_name_list = [n.name() for n in internal_nodes]
            self._backdrop_internal_nodes_list.update_content(new_status_list, new_name_list)

        return True

    def _add_internal_nodes_section(self, node, layout):
        nodes_card = CardWidget(self.parent_panel)
        node_id = node.id
        if not hasattr(self.parent_panel, '_internal_nodes_card_expanded'):
            self.parent_panel._internal_nodes_card_expanded = {}
        self.parent_panel._internal_nodes_card_expanded[node_id] = False

        nodes_layout = QVBoxLayout(nodes_card)
        nodes_layout.setContentsMargins(10, 10, 10, 10)
        title_btn_layout = QHBoxLayout()
        title = BodyLabel("区域内部节点：")
        title_btn_layout.addWidget(title)
        title_btn_layout.addStretch()
        expand_btn = TransparentToolButton(icon=get_icon("放大"), parent=self.parent_panel)
        expand_btn.setFixedSize(QSize(26, 20))

        def toggle_expand():
            is_expanded = self.parent_panel._internal_nodes_card_expanded[node_id]
            if is_expanded:
                nodes_card.setMaximumHeight(initial_max_height)
                nodes_card.setMinimumHeight(initial_max_height)
                expand_btn.setIcon(get_icon("放大"))
                self.parent_panel._internal_nodes_card_expanded[node_id] = False
            else:
                nodes_card.setFixedHeight(total_estimated_height)
                expand_btn.setIcon(get_icon("缩小"))
                self.parent_panel._internal_nodes_card_expanded[node_id] = True
            self.parent_layout.invalidate()

        expand_btn.clicked.connect(toggle_expand)
        title_btn_layout.addWidget(expand_btn)
        nodes_layout.addLayout(title_btn_layout)

        _, _, internal_nodes = node.get_nodes()
        status_list = [self.main_window.get_node_status(n) for n in internal_nodes]
        name_list = [n.name() for n in internal_nodes]
        internal_nodes_list = InternalNodeList(status_list, name_list, self.parent_panel)

        def on_item_double_clicked(item):
            row = internal_nodes_list.row(item)
            if 0 <= row < len(internal_nodes):
                node_to_center = internal_nodes[row]
                self.main_window.canvas_widget.zoom_to_nodes([node_to_center._view])

        internal_nodes_list.itemDoubleClicked.connect(on_item_double_clicked)
        num_items = internal_nodes_list.count()
        estimated_height_for_items = num_items * 40
        padding_height = 25
        title_height = 20
        total_estimated_height = padding_height + title_height + estimated_height_for_items
        initial_max_height = min(total_estimated_height, 200)
        nodes_card.setMaximumHeight(initial_max_height)
        nodes_card.setMinimumHeight(initial_max_height)
        nodes_layout.addWidget(internal_nodes_list)
        layout.addWidget(nodes_card, 1)
        self._backdrop_internal_nodes_list = internal_nodes_list  # 缓存

    def _add_loop_config_section(self, node, layout):
        config_card = CardWidget(self.parent_panel)
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(10, 10, 10, 10)

        from qfluentwidgets import ComboBox, SpinBox
        mode_combo = ComboBox(self.parent_panel)
        mode_combo.addItems(['固定次数', '条件循环', 'While循环'])
        mode_combo.setCurrentText({
                                      'count': '固定次数',
                                      'condition': '条件循环',
                                      'while': 'While循环'
                                  }.get(node.model.get_property("loop_mode"), '固定次数'))

        def on_mode_changed(text):
            mode_map = {'固定次数': 'count', '条件循环': 'condition', 'While循环': 'while'}
            node.model.set_property("loop_mode", mode_map.get(text, "count"))
            self.parent_panel.update_properties(node, node_changed=True)  # 调用父控件方法

        mode_combo.currentTextChanged.connect(on_mode_changed)
        config_layout.addWidget(BodyLabel("循环模式:"))
        config_layout.addWidget(mode_combo)

        current_mode = node.model.get_property("loop_mode")
        if current_mode == 'count':
            max_iter_spin = SpinBox(self.parent_panel)
            max_iter_spin.setRange(1, 10000)
            current_max = node.model.get_property("loop_nums")
            max_iter_spin.setValue(current_max)

            def on_max_iter_changed(value):
                node.model.set_property('loop_nums', value)
                # 尝试更新现有Backdrop数据
                if hasattr(self, '_backdrop_progress_label') and self._backdrop_progress_label:
                    self.update_backdrop_data(node)

            max_iter_spin.valueChanged.connect(on_max_iter_changed)
            config_layout.addWidget(BodyLabel("循环次数:"))
            config_layout.addWidget(max_iter_spin)
        else:
            expr_layout = QHBoxLayout()
            expr_label = BodyLabel("条件表达式:")
            expr_layout.addWidget(expr_label)
            global_vars = getattr(self.main_window, 'global_variables', None)
            extra_keys = ['data', 'result', 'current_index', 'current_iteration', 'iteration_count', 'loop_mode',
                          'max_iterations']
            _, _, internal_nodes = node.get_nodes()
            for n in internal_nodes:
                name = re.sub(r'\s+', '_', n.name())
                for port in n.output_ports():
                    extra_keys.append(f"node_vars.{name}__{port.name()}")
            condition_edit = VariableCompletionTextEdit(
                get_variable_list_func=lambda keys=extra_keys: global_vars.get_vars(keys),
                parent=self.parent_panel
            )
            condition_edit.setMaximumHeight(60)
            condition_edit.setPlaceholderText("请输入条件表达式")
            current_condition = node.model.get_property("loop_condition")
            condition_edit.setText(current_condition)

            def on_condition_changed():
                node.model.set_property('loop_condition', condition_edit.toPlainText())

            condition_edit.cursorPositionChanged.connect(on_condition_changed)
            browse_btn = TransparentToolButton(icon=get_icon("放大"), parent=self.parent_panel)
            browse_btn.setFixedSize(QSize(26, 20))
            browse_btn.clicked.connect(
                lambda _, edit=condition_edit, key=extra_keys: self._open_long_text_editor(edit, key)
            )
            expr_layout.addWidget(browse_btn)
            config_layout.addLayout(expr_layout)
            config_layout.addWidget(condition_edit)

            max_iter_spin = SpinBox(self.parent_panel)
            max_iter_spin.setRange(1, 10000)
            current_max_iter = node.model.get_property("max_iterations")
            max_iter_spin.setValue(current_max_iter)

            def on_max_iterations_changed(value):
                node.model.set_property('max_iterations', value)
                # 尝试更新现有Backdrop数据
                if hasattr(self, '_backdrop_progress_label') and self._backdrop_progress_label:
                    self.update_backdrop_data(node)

            max_iter_spin.valueChanged.connect(on_max_iterations_changed)
            config_layout.addWidget(BodyLabel("最大迭代次数:"))
            config_layout.addWidget(max_iter_spin)

        layout.addWidget(config_card)

    def _open_long_text_editor(self, line_edit, key):
        dialog = LongTextEditorDialog(
            content=line_edit.toPlainText(), extra_keys=key, parent=self.parent_panel.window(),
            main_window=self.main_window
        )
        if dialog.exec():
            new_text = dialog.text_edit.toPlainText().strip()
            line_edit.setText(new_text)
