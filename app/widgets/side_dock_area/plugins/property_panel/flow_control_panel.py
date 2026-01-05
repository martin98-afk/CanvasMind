# -*- coding: utf-8 -*-
import re

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QFrame
from qfluentwidgets import (CardWidget, BodyLabel, ProgressBar, TransparentToolButton,
                            StrongBodyLabel, ComboBox, SpinBox, SmoothScrollArea,
                            IconWidget, FluentIcon, CaptionLabel)

from app.utils.utils import get_icon
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit
from app.widgets.node_widget.longtext_dialog import LongTextEditorDialog
from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList
from app.widgets.side_dock_area.plugins.property_panel.port_widget import PortWidget


class FlowControlPanelWidget(QWidget):
    """
    极致舒适版：控制流面板
    特点：状态监控 Dashboard、配置分区化、极简信息密度。
    """

    def __init__(self, main_window, parent_panel, node):
        super().__init__(parent_panel)
        self.main_window = main_window
        self.parent_panel = parent_panel
        self.current_node = node
        self.current_segment = 'input'

        self._backdrop_internal_nodes_list = None
        self._port_widget = None

        # 1. 骨架初始化
        self._setup_ui(node)

        # 2. 填充数据
        self.update_data(node)

    def _setup_ui(self, node):
        self.setObjectName("FlowControlPanel")
        self.setStyleSheet("background-color: transparent;")

        # 主布局：增加内边距和间距
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 12, 16, 12)
        self.main_layout.setSpacing(15)

        # --- [1] 状态控制台 (Dashboard Header) ---
        self._setup_status_dashboard()

        # --- [2] 滚动内容区 ---
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(SmoothScrollArea.NoFrame)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 4, 0)
        self.scroll_layout.setSpacing(16)

        # 初始化：循环配置
        self._init_loop_config_section()
        # 初始化：内部成员监控
        self._init_internal_nodes_section(node)
        # 初始化：端口管理
        self._init_port_section(node)

        self.scroll_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area, 1)

    def _setup_status_dashboard(self):
        """创建一个类似 HUD 的状态显示区域"""
        dash_container = QFrame()
        dash_container.setObjectName("Dashboard")
        dash_container.setStyleSheet("""
            #Dashboard {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
        """)
        dash_layout = QVBoxLayout(dash_container)
        dash_layout.setContentsMargins(12, 10, 12, 10)
        dash_layout.setSpacing(6)

        # 状态行
        status_line = QHBoxLayout()
        status_icon = IconWidget(FluentIcon.PLAY)
        status_icon.setFixedSize(14, 14)

        self.status_title = CaptionLabel("运行状态分析")
        self.status_title.setStyleSheet("color: #888888; text-transform: uppercase;")

        self.progress_label = StrongBodyLabel("0 / 0")
        # 使用等宽字体防止数字变动时宽度抖动
        self.progress_label.setFont(QFont("Consolas", 11, QFont.Bold))
        self.progress_label.setStyleSheet("color: #00a2ff;")

        status_line.addWidget(status_icon)
        status_line.addWidget(self.status_title)
        status_line.addStretch()
        status_line.addWidget(self.progress_label)
        dash_layout.addLayout(status_line)

        # 进度条：更细、更精致
        self.progress_bar = ProgressBar(self, useAni=True)
        self.progress_bar.setFixedHeight(4)
        dash_layout.addWidget(self.progress_bar)

        self.main_layout.addWidget(dash_container)

    def _init_loop_config_section(self):
        """配置区域：带有逻辑感的分组"""
        self.config_card = CardWidget(self)
        self.config_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self.config_card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 头部：带图标的标签
        mode_header = QHBoxLayout()
        mode_icon = IconWidget(FluentIcon.SETTING)
        mode_icon.setFixedSize(16, 16)
        mode_header.addWidget(mode_icon)
        mode_header.addWidget(BodyLabel("逻辑策略配置"))
        mode_header.addStretch()
        layout.addLayout(mode_header)

        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems(['固定次数', '条件循环', 'While循环'])
        self.mode_combo.currentTextChanged.connect(self._on_mode_ui_changed)
        layout.addWidget(self.mode_combo)

        # 分隔符
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: rgba(255, 255, 255, 0.05);")
        layout.addWidget(line)

        # --- 容器1: 固定次数 ---
        self.container_count = QWidget()
        count_lay = QVBoxLayout(self.container_count)
        count_lay.setContentsMargins(0, 0, 0, 0)
        count_lay.addWidget(CaptionLabel("ITERATION COUNT"))
        self.max_iter_spin = SpinBox(self)
        self.max_iter_spin.setRange(1, 10000)
        self.max_iter_spin.setMinimumWidth(150)
        self.max_iter_spin.valueChanged.connect(lambda v: self._set_node_prop('loop_nums', v))
        count_lay.addWidget(self.max_iter_spin)
        layout.addWidget(self.container_count)

        # --- 容器2: 条件表达式 ---
        self.container_condition = QWidget()
        cond_lay = QVBoxLayout(self.container_condition)
        cond_lay.setContentsMargins(0, 0, 0, 0)

        expr_head = QHBoxLayout()
        expr_head.addWidget(CaptionLabel("LOGIC EXPRESSION"))
        expr_head.addStretch()
        self.browse_btn = TransparentToolButton(FluentIcon.FULL_SCREEN)
        self.browse_btn.setFixedSize(24, 24)
        self.browse_btn.clicked.connect(self._open_long_text_editor)
        expr_head.addWidget(self.browse_btn)
        cond_lay.addLayout(expr_head)

        self.condition_edit = VariableCompletionTextEdit(
            get_variable_list_func=self._get_variable_autocomplete_list,
            parent=self
        )
        self.condition_edit.setPlaceholderText("请输入 Python 表达式...")
        self.condition_edit.setMaximumHeight(80)
        self.condition_edit.textChanged.connect(
            lambda: self._set_node_prop('loop_condition', self.condition_edit.toPlainText())
        )
        cond_lay.addWidget(self.condition_edit)

        cond_lay.addSpacing(5)
        cond_lay.addWidget(CaptionLabel("SAFE EXIT THRESHOLD (MAX ITER)"))
        self.cond_max_spin = SpinBox(self)
        self.cond_max_spin.setRange(1, 10000)
        self.cond_max_spin.valueChanged.connect(lambda v: self._set_node_prop('max_iterations', v))
        cond_lay.addWidget(self.cond_max_spin)
        layout.addWidget(self.container_condition)

        self.scroll_layout.addWidget(self.config_card)

    def _init_internal_nodes_section(self, node):
        """内部成员监控：使用 HUD 风格"""
        self.nodes_card = CardWidget(self)
        layout = QVBoxLayout(self.nodes_card)
        layout.setContentsMargins(12, 12, 12, 12)

        title_lay = QHBoxLayout()
        title_icon = IconWidget(FluentIcon.BASKETBALL)  # 类似原子图标
        title_icon.setFixedSize(16, 16)
        title_lay.addWidget(title_icon)
        title_lay.addWidget(BodyLabel("内部成员状态监控"))
        title_lay.addStretch()
        self.expand_btn = TransparentToolButton(FluentIcon.ZOOM_IN)
        self.expand_btn.clicked.connect(self._toggle_nodes_expand)
        title_lay.addWidget(self.expand_btn)
        layout.addLayout(title_lay)

        self._backdrop_internal_nodes_list = InternalNodeList([], [], self)
        self._backdrop_internal_nodes_list.itemDoubleClicked.connect(self._on_internal_node_clicked)
        # 优化列表样式，使其更紧凑
        self._backdrop_internal_nodes_list.setStyleSheet("QListWidget { background: transparent; border: none; }")

        layout.addWidget(self._backdrop_internal_nodes_list)
        self.nodes_card.setFixedHeight(180)
        self.scroll_layout.addWidget(self.nodes_card)

    def _init_port_section(self, node):
        """端口区：保持简洁"""
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

    def update_data(self, node):
        """增量刷新数据：极致效率"""
        self.current_node = node
        flow_type = getattr(node, 'TYPE', 'unknown')

        # 1. 刷新 Dashboard
        current = node.model.get_property('current_index') or 0
        total = self._calculate_total(node, flow_type)
        self.progress_label.setText(f"{current} / {total}")
        self.progress_bar.setValue(int(current / max(1, total) * 100) if total > 0 else 0)

        # 2. 刷新配置页显隐
        self.config_card.setVisible(flow_type == "loop")
        if flow_type == "loop":
            self._update_loop_config_ui(node)

        # 3. 内部列表增量更新 (不重建列表)
        _, _, internal_nodes = node.get_nodes()
        if self._backdrop_internal_nodes_list:
            status_list = [self.main_window.get_node_status(n) for n in internal_nodes]
            name_list = [n.name() for n in internal_nodes]
            self._backdrop_internal_nodes_list.update_content(status_list, name_list)
        self._current_internal_nodes = internal_nodes

        # 4. 端口刷新
        if self._port_widget:
            self._port_widget.refresh(node)

    def _update_loop_config_ui(self, node):
        mode = node.model.get_property("loop_mode")
        mode_text = {'count': '固定次数', 'condition': '条件循环', 'while': 'While循环'}.get(mode, '固定次数')

        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(mode_text)
        self.mode_combo.blockSignals(False)

        # 使用 setVisible 结合布局自动收缩，物理上极度舒适
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

    # --- 辅助逻辑保持不变 ---
    def _get_variable_autocomplete_list(self):
        if not self.current_node: return []
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars: return []
        extra_keys = ['data', 'result', 'current_index', 'current_iteration', 'loop_mode', 'max_iterations']
        try:
            _, _, internal_nodes = self.current_node.get_nodes()
            for n in internal_nodes:
                name = re.sub(r'\s+', '_', n.name())
                for port in n.output_ports(): extra_keys.append(f"node_vars.{name}__{port.name()}")
        except:
            pass
        return global_vars.get_vars(extra_keys)

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
                self.update_data(self.current_node)

    def _calculate_total(self, node, flow_type):
        if flow_type == "loop":
            mode = node.model.get_property("loop_mode")
            return node.model.get_property("loop_nums") if mode == 'count' else node.model.get_property(
                "max_iterations")
        return node.model.get_property("loop_nums") or 0

    def _on_internal_node_clicked(self, item):
        row = self._backdrop_internal_nodes_list.row(item)
        if hasattr(self, '_current_internal_nodes') and 0 <= row < len(self._current_internal_nodes):
            self.main_window.canvas_widget.zoom_to_nodes([self._current_internal_nodes[row]._view])

    def _toggle_nodes_expand(self):
        if self.nodes_card.height() <= 180:
            count = self._backdrop_internal_nodes_list.count()
            self.nodes_card.setFixedHeight(max(180, count * 36 + 60))
            self.expand_btn.setIcon(FluentIcon.ZOOM_OUT)
        else:
            self.nodes_card.setFixedHeight(180)
            self.expand_btn.setIcon(FluentIcon.ZOOM_IN)

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