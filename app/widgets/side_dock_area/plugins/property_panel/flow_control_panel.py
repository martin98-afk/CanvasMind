# -*- coding: utf-8 -*-
import re
from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QStackedWidget
from qfluentwidgets import (CardWidget, BodyLabel, ProgressBar, TransparentToolButton,
                            SubtitleLabel, StrongBodyLabel, ComboBox, SpinBox, SmoothScrollArea, SimpleCardWidget)

from app.utils.utils import get_icon
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit
from app.widgets.node_widget.longtext_dialog import LongTextEditorDialog
from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList
from app.widgets.side_dock_area.plugins.property_panel.port_widget import PortWidget


class FlowControlPanelWidget(SimpleCardWidget):
    """
    完全修复版：处理控制流节点，修复 VariableCompletionTextEdit 初始化报错。
    """

    def __init__(self, main_window, parent_panel, node):
        super().__init__(parent_panel)
        self.main_window = main_window
        self.parent_panel = parent_panel
        self.current_node = node  # 必须先设置节点，以便初始化时回调可用
        self.current_segment = 'input'

        self._backdrop_internal_nodes_list = None
        self._port_widget = None

        # 1. 初始化 UI 骨架
        self._setup_ui(node)

        # 2. 初始数据填充
        self.update_data(node)

    def _setup_ui(self, node):
        self.setStyleSheet("""background-color: transparent;""")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)

        self.progress_label = StrongBodyLabel()
        self.progress_bar = ProgressBar(self, useAni=False)
        self.main_layout.addWidget(self.progress_label)
        self.main_layout.addWidget(self.progress_bar)

        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)

        # 初始化循环配置
        self._init_loop_config_section()
        # 初始化内部节点卡片
        self._init_internal_nodes_section(node)
        # 初始化端口
        self._init_port_section(node)

        self.scroll_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area, 1)

    def _get_variable_autocomplete_list(self):
        """
        动态获取自动补全列表的回调函数。
        解决 VariableCompletionTextEdit 初始化参数缺失问题。
        """
        if not self.current_node:
            return []

        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return []

        # 基础关键字
        extra_keys = ['data', 'result', 'current_index', 'current_iteration',
                      'iteration_count', 'loop_mode', 'max_iterations']

        # 获取区域内部节点的输出端口变量
        try:
            _, _, internal_nodes = self.current_node.get_nodes()
            for n in internal_nodes:
                name = re.sub(r'\s+', '_', n.name())
                for port in n.output_ports():
                    extra_keys.append(f"node_vars.{name}__{port.name()}")
        except:
            pass

        return global_vars.get_vars(extra_keys)

    def _init_loop_config_section(self):
        self.config_card = CardWidget(self)
        layout = QVBoxLayout(self.config_card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(BodyLabel("循环模式:"))
        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems(['固定次数', '条件循环', 'While循环'])
        self.mode_combo.currentTextChanged.connect(self._on_mode_ui_changed)
        layout.addWidget(self.mode_combo)

        # --- 页面1: 固定次数容器 ---
        self.container_count = QWidget()
        count_lay = QVBoxLayout(self.container_count)
        count_lay.setContentsMargins(0, 5, 0, 0)
        count_lay.addWidget(BodyLabel("循环次数:"))
        self.max_iter_spin = SpinBox(self)
        self.max_iter_spin.setRange(1, 10000)
        self.max_iter_spin.valueChanged.connect(lambda v: self._set_node_prop('loop_nums', v))
        count_lay.addWidget(self.max_iter_spin)
        layout.addWidget(self.container_count)

        # --- 页面2: 条件/While容器 ---
        self.container_condition = QWidget()
        cond_lay = QVBoxLayout(self.container_condition)
        cond_lay.setContentsMargins(0, 5, 0, 0)

        expr_head = QHBoxLayout()
        expr_head.addWidget(BodyLabel("条件表达式:"))
        self.browse_btn = TransparentToolButton(icon=get_icon("放大"))
        self.browse_btn.clicked.connect(self._open_long_text_editor)
        expr_head.addStretch()
        expr_head.addWidget(self.browse_btn)
        cond_lay.addLayout(expr_head)

        self.condition_edit = VariableCompletionTextEdit(
            get_variable_list_func=self._get_variable_autocomplete_list,
            parent=self
        )
        self.condition_edit.setMaximumHeight(60)
        self.condition_edit.textChanged.connect(
            lambda: self._set_node_prop('loop_condition', self.condition_edit.toPlainText())
        )
        cond_lay.addWidget(self.condition_edit)

        cond_lay.addWidget(BodyLabel("最大迭代次数:"))
        self.cond_max_spin = SpinBox(self)
        self.cond_max_spin.setRange(1, 10000)
        self.cond_max_spin.valueChanged.connect(lambda v: self._set_node_prop('max_iterations', v))
        cond_lay.addWidget(self.cond_max_spin)
        layout.addWidget(self.container_condition)

        self.scroll_layout.addWidget(self.config_card)

    def update_data(self, node):
        """增量刷新数据接口"""
        self.current_node = node

        # 标题和进度
        flow_type = getattr(node, 'TYPE', 'unknown')
        current = node.model.get_property('current_index')
        total = self._calculate_total(node, flow_type)

        self.progress_label.setText(f"进度: {current}/{total}")
        self.progress_bar.setValue(int(current / max(1, total) * 100) if total > 0 else 0)

        # 模式显隐
        self.config_card.setVisible(flow_type == "loop")
        if flow_type == "loop":
            self._update_loop_config_ui(node)

        # 内部节点
        _, _, internal_nodes = node.get_nodes()
        status_list = [self.main_window.get_node_status(n) for n in internal_nodes]
        name_list = [n.name() for n in internal_nodes]
        self._backdrop_internal_nodes_list.update_content(status_list, name_list)
        self._current_internal_nodes = internal_nodes

        # 端口
        self._port_widget.refresh(node)

    def _update_loop_config_ui(self, node):
        mode = node.model.get_property("loop_mode")
        mode_text = {'count': '固定次数', 'condition': '条件循环', 'while': 'While循环'}.get(mode, '固定次数')

        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(mode_text)
        self.mode_combo.blockSignals(False)

        # 核心优化：显隐切换实现自动高度收缩
        if mode == 'count':
            self.container_count.setVisible(True)
            self.container_condition.setVisible(False)

            self.max_iter_spin.blockSignals(True)
            self.max_iter_spin.setValue(node.model.get_property("loop_nums"))
            self.max_iter_spin.blockSignals(False)
        else:
            self.container_count.setVisible(False)
            self.container_condition.setVisible(True)

            self.condition_edit.blockSignals(True)
            self.condition_edit.setPlainText(node.model.get_property("loop_condition") or "")
            self.condition_edit.blockSignals(False)

            self.cond_max_spin.blockSignals(True)
            self.cond_max_spin.setValue(node.model.get_property("max_iterations"))
            self.cond_max_spin.blockSignals(False)

        # 强制卡片重新计算高度
        self.config_card.adjustSize()

    def _on_mode_ui_changed(self, text):
        mode_map = {'固定次数': 'count', '条件循环': 'condition', 'While循环': 'while'}
        new_mode = mode_map.get(text, "count")
        if self.current_node:
            self.current_node.model.set_property("loop_mode", new_mode)
            self.update_data(self.current_node)

    def _set_node_prop(self, key, value):
        if self.current_node:
            self.current_node.model.set_property(key, value)
            if key in ['loop_nums', 'max_iterations']:
                # 重新计算进度显示
                self.update_data(self.current_node)

    def _calculate_total(self, node, flow_type):
        if flow_type == "loop":
            mode = node.model.get_property("loop_mode")
            return node.model.get_property("loop_nums") if mode == 'count' else node.model.get_property(
                "max_iterations")
        return node.model.get_property("loop_nums") or 0

    def _init_internal_nodes_section(self, node):
        self.nodes_card = CardWidget(self)
        layout = QVBoxLayout(self.nodes_card)
        title_lay = QHBoxLayout()
        title_lay.addWidget(BodyLabel("区域内部节点："))
        title_lay.addStretch()
        self.expand_btn = TransparentToolButton(icon=get_icon("放大"))
        title_lay.addWidget(self.expand_btn)
        layout.addLayout(title_lay)

        self._backdrop_internal_nodes_list = InternalNodeList([], [], self)
        self._backdrop_internal_nodes_list.itemDoubleClicked.connect(self._on_internal_node_clicked)
        layout.addWidget(self._backdrop_internal_nodes_list)
        self.nodes_card.setFixedHeight(200)
        self.scroll_layout.addWidget(self.nodes_card)
        self.expand_btn.clicked.connect(self._toggle_nodes_expand)

    def _init_port_section(self, node):
        self._port_widget = PortWidget(
            main_window=self.main_window, parent_panel=self.parent_panel, node=node,
            port_info_func=self.parent_panel.get_port_info,
            copy_as_expression_func=self.parent_panel._copy_as_expression,
            add_func=self.parent_panel._add_output_to_global_variable,
            delete_func=self.parent_panel._delete_output_from_global_variable,
            is_in_func=self.parent_panel._is_output_in_global_variable,
            parent=self
        )
        self.scroll_layout.addWidget(self._port_widget)

    def _on_internal_node_clicked(self, item):
        row = self._backdrop_internal_nodes_list.row(item)
        if hasattr(self, '_current_internal_nodes') and 0 <= row < len(self._current_internal_nodes):
            self.main_window.canvas_widget.zoom_to_nodes([self._current_internal_nodes[row]._view])

    def _toggle_nodes_expand(self):
        if self.nodes_card.height() <= 200:
            count = self._backdrop_internal_nodes_list.count()
            self.nodes_card.setFixedHeight(max(200, count * 40 + 60))
            self.expand_btn.setIcon(get_icon("缩小"))
        else:
            self.nodes_card.setFixedHeight(200)
            self.expand_btn.setIcon(get_icon("放大"))

    def _open_long_text_editor(self):
        # 重新生成最新的 key 列表
        global_vars = getattr(self.main_window, 'global_variables', None)
        extra_keys = ['current_index', 'max_iterations', 'loop_mode']
        try:
            _, _, internal_nodes = self.current_node.get_nodes()
            for n in internal_nodes:
                name = re.sub(r'\s+', '_', n.name())
                for port in n.output_ports(): extra_keys.append(f"node_vars.{name}__{port.name()}")
        except:
            pass

        dialog = LongTextEditorDialog(
            content=self.condition_edit.toPlainText(), extra_keys=extra_keys,
            parent=self.window(), main_window=self.main_window
        )
        if dialog.exec():
            self.condition_edit.setPlainText(dialog.text_edit.toPlainText().strip())