# -*- coding: utf-8 -*-
import re

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QFrame
from qfluentwidgets import (CardWidget, BodyLabel, ProgressBar, TransparentToolButton,
                            StrongBodyLabel, ComboBox, SpinBox, SmoothScrollArea,
                            IconWidget, FluentIcon, CaptionLabel, Slider)

from app.utils.utils import get_icon, get_port_node
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit
from app.widgets.node_widget.propeprty_widgets.longtext_dialog import LongTextEditorDialog
from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList
from app.widgets.side_dock_area.plugins.property_panel.port_widget import PortWidget


class FlowControlPanelWidget(QWidget):
    """
    极致舒适版：控制流面板
    优化说明：
    1. 修复内部节点展开/收起的高度计算逻辑。
    2. 解决底部端口被挤压的问题。
    3. 保持高科技 Dashboard 视觉风格。
    """

    def __init__(self, main_window, parent_panel, node):
        super().__init__(parent_panel)
        self.main_window = main_window
        self.parent_panel = parent_panel
        self.current_node = node
        self.current_segment = 'input'

        # 状态记录
        self._is_nodes_expanded = False
        self._backdrop_internal_nodes_list = None
        self._port_widget = None

        # 1. 骨架初始化
        self._setup_ui(node)

        # 2. 填充数据
        self.update_data(node)

    def _setup_ui(self, node):
        self.setObjectName("FlowControlPanel")
        self.setStyleSheet("background-color: transparent;")

        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 8, 10, 8)
        self.main_layout.setSpacing(5)

        # --- [1] 状态控制台 (Dashboard Header) ---
        self._setup_status_dashboard()

        # --- [2] 滚动内容区 ---
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(SmoothScrollArea.NoFrame)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 8, 0)
        self.scroll_layout.setSpacing(3)

        # 初始化：循环配置卡片
        self._init_loop_config_section()
        self._init_parallel_section()
        # 初始化：内部成员监控卡片
        self._init_internal_nodes_section(node)
        # 初始化：端口管理区域
        self._init_port_section(node)

        self.scroll_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area, 1)

    def _setup_status_dashboard(self):
        """创建一个科技感 HUD 状态显示区域"""
        dash_container = QFrame()
        dash_container.setObjectName("Dashboard")
        dash_container.setStyleSheet("""
            #Dashboard {
                background-color: rgba(0, 162, 255, 0.05);
                border: 1px solid rgba(0, 162, 255, 0.1);
                border-radius: 8px;
            }
        """)
        dash_layout = QVBoxLayout(dash_container)
        dash_layout.setContentsMargins(12, 10, 12, 10)
        dash_layout.setSpacing(6)

        status_line = QHBoxLayout()
        status_icon = IconWidget(FluentIcon.PLAY)
        status_icon.setFixedSize(14, 14)

        self.status_title = CaptionLabel("循环节点运行状态")
        self.status_title.setStyleSheet("color: #00a2ff; font-weight: bold;")

        self.progress_label = StrongBodyLabel("0 / 0")
        self.progress_label.setFont(QFont("Consolas", 11, QFont.Bold))
        self.progress_label.setStyleSheet("color: #ffffff;")

        status_line.addWidget(status_icon)
        status_line.addWidget(self.status_title)
        status_line.addStretch()
        status_line.addWidget(self.progress_label)
        dash_layout.addLayout(status_line)

        self.progress_bar = ProgressBar(self, useAni=True)
        self.progress_bar.setFixedHeight(4)
        dash_layout.addWidget(self.progress_bar)

        self.main_layout.addWidget(dash_container)

    def _init_loop_config_section(self):
        """配置区域卡片"""
        self.config_card = CardWidget(self)
        self.config_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self.config_card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(BodyLabel("循环模式:"))
        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems(['固定次数', '条件循环', 'While循环'])
        self.mode_combo.currentTextChanged.connect(self._on_mode_ui_changed)
        layout.addWidget(self.mode_combo)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: rgba(255, 255, 255, 0.05);")
        layout.addWidget(line)

        # 固定次数页面
        self.container_count = QWidget()
        count_lay = QVBoxLayout(self.container_count)
        count_lay.setContentsMargins(0, 0, 0, 0)
        count_lay.addWidget(CaptionLabel("固定循环次数设定"))
        self.max_iter_spin = SpinBox(self)
        self.max_iter_spin.setRange(1, 10000)
        self.max_iter_spin.setMinimumWidth(120)
        self.max_iter_spin.valueChanged.connect(lambda v: self._set_node_prop('loop_nums', v))
        count_lay.addWidget(self.max_iter_spin)
        layout.addWidget(self.container_count)

        # 条件页面
        self.container_condition = QWidget()
        cond_lay = QVBoxLayout(self.container_condition)
        cond_lay.setContentsMargins(0, 0, 0, 0)

        expr_head = QHBoxLayout()
        expr_head.addWidget(CaptionLabel("循环条件(为False时退出循环)"))
        expr_head.addStretch()
        self.browse_btn = TransparentToolButton(get_icon("放大"))
        self.browse_btn.setFixedSize(24, 24)
        self.browse_btn.clicked.connect(self._open_long_text_editor)
        expr_head.addWidget(self.browse_btn)
        cond_lay.addLayout(expr_head)

        self.condition_edit = VariableCompletionTextEdit(
            get_variable_list_func=self._get_variable_autocomplete_list,
            parent=self
        )
        self.condition_edit.setMaximumHeight(80)
        self.condition_edit.textChanged.connect(
            lambda: self._set_node_prop('loop_condition', self.condition_edit.toPlainText())
        )
        cond_lay.addWidget(self.condition_edit)

        cond_lay.addSpacing(5)
        cond_lay.addWidget(CaptionLabel("最大循环次数 (安全退出)"))
        self.cond_max_spin = SpinBox(self)
        self.cond_max_spin.setRange(1, 10000)
        self.cond_max_spin.valueChanged.connect(lambda v: self._set_node_prop('max_iterations', v))
        cond_lay.addWidget(self.cond_max_spin)
        layout.addWidget(self.container_condition)

        self.scroll_layout.addWidget(self.config_card)

    def _init_internal_nodes_section(self, node):
        """内部成员监控：处理高度自适应逻辑"""
        self.nodes_card = CardWidget(self)
        self.nodes_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self.nodes_card)
        layout.setContentsMargins(10, 10, 10, 10)

        title_lay = QHBoxLayout()
        title_lay.addWidget(BodyLabel("区域内部节点："))
        title_lay.addStretch()
        self.expand_btn = TransparentToolButton(get_icon("放大"))
        self.expand_btn.setFixedSize(QSize(26, 26))
        self.expand_btn.clicked.connect(self._toggle_nodes_expand)
        title_lay.addWidget(self.expand_btn)
        layout.addLayout(title_lay)

        self._backdrop_internal_nodes_list = InternalNodeList([], [], self)
        self._backdrop_internal_nodes_list.itemDoubleClicked.connect(self._on_internal_node_clicked)
        layout.addWidget(self._backdrop_internal_nodes_list)

        # 初始高度计算
        self._update_nodes_card_height()
        self.scroll_layout.addWidget(self.nodes_card)

    def _init_parallel_section(self):
        """新增：并行度配置区域"""
        self.parallel_card = CardWidget(self)
        layout = QVBoxLayout(self.parallel_card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 标题和数值显示
        head_lay = QHBoxLayout()
        head_lay.addWidget(BodyLabel("并行设置"))
        self.parallel_val_label = StrongBodyLabel("1")
        self.parallel_val_label.setStyleSheet("color: #00a2ff;")
        head_lay.addStretch()
        head_lay.addWidget(CaptionLabel("并发进程数: "))
        head_lay.addWidget(self.parallel_val_label)
        layout.addLayout(head_lay)

        # 并行度滑动条
        self.parallel_slider = Slider(Qt.Horizontal, self)
        self.parallel_slider.setRange(1, 16)  # 根据需求设置最大并发数
        self.parallel_slider.valueChanged.connect(self._on_parallel_changed)
        reminder = CaptionLabel("注意：1.总并行数受设置影响; 2.并行模式下节点间的数据竞争需自行处理")
        reminder.setWordWrap(True)
        layout.addWidget(reminder)
        layout.addWidget(self.parallel_slider)

        self.scroll_layout.addWidget(self.parallel_card)

    def _on_parallel_changed(self, value):
        """并行度改变回调"""
        self.parallel_val_label.setText(str(value))
        if self.current_node:
            self.current_node.model.set_property('parallel_count', value)

    def update_data(self, node):
        """增量刷新逻辑"""
        self.current_node = node
        # 获取节点类型 (假设迭代组件的 TYPE 是 'iteration'，循环是 'loop')
        flow_type = getattr(node, 'TYPE', 'unknown')

        # 1. 刷新 Dashboard (运行状态)
        current = node.model.get_property('current_index') or 0
        total = self._calculate_total(node, flow_type)
        self.progress_label.setText(f"{current} / {total}")
        self.progress_bar.setValue(int(current / max(1, total) * 100) if total > 0 else 0)

        # 2. 刷新【循环配置】卡片显隐 (仅 loop 类型显示)
        self.config_card.setVisible(flow_type == "loop")
        if flow_type == "loop":
            self._update_loop_config_ui(node)

        # 3. 刷新【并行配置】卡片显隐 (仅 iteration 类型显示)
        is_iteration = (flow_type != "loop")
        self.parallel_card.setVisible(is_iteration)
        if is_iteration:
            p_count = node.model.get_property("parallel_count") or 1
            self.parallel_slider.blockSignals(True)
            self.parallel_slider.setValue(p_count)
            self.parallel_val_label.setText(str(p_count))
            self.parallel_slider.blockSignals(False)

        # 4. 内部列表更新 (保持不变)
        _, _, internal_nodes = node.get_nodes()
        if self._backdrop_internal_nodes_list:
            status_list = [n.get_property("_status") for n in internal_nodes]
            name_list = [n.name() for n in internal_nodes]
            self._backdrop_internal_nodes_list.update_content(status_list, name_list)
            self._update_nodes_card_height()

        # 5. 端口刷新 (保持不变)
        if self._port_widget:
            self._port_widget.refresh(node)

    def _update_nodes_card_height(self):
        """核心：计算并设置内部节点卡片的高度"""
        if not self._backdrop_internal_nodes_list:
            return

        count = self._backdrop_internal_nodes_list.count()
        # 估算高度：每行约 38px + 头部间距约 50px
        actual_needed_h = count * 38 + 52

        if self._is_nodes_expanded:
            # 放大：匹配全长
            self.nodes_card.setFixedHeight(actual_needed_h)
            self.expand_btn.setIcon(get_icon("缩小"))
        else:
            # 缩小：最大限制 180px，若节点少则匹配实际高度
            self.nodes_card.setFixedHeight(min(actual_needed_h, 180))
            self.expand_btn.setIcon(get_icon("放大"))

    def _init_port_section(self, node):
        """端口区：增加权重防止被挤压"""
        self._port_widget = PortWidget(
            main_window=self.main_window, parent_panel=self.parent_panel, node=node,
            port_info_func=self.parent_panel.get_port_info,
            copy_as_expression_func=self.parent_panel._copy_as_expression,
            add_func=self.parent_panel._add_output_to_global_variable,
            delete_func=self.parent_panel._delete_output_from_global_variable,
            is_in_func=self.parent_panel._is_output_in_global_variable,
            parent=self
        )
        # 设置最小高度确保可见，并将 stretch 设为 1
        self._port_widget.setMinimumHeight(350)
        self._port_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll_layout.addWidget(self._port_widget, 1)

    def _update_loop_config_ui(self, node):
        mode = node.model.get_property("loop_mode")
        mode_text = {'count': '固定次数', 'condition': '条件循环', 'while': 'While循环'}.get(mode, '固定次数')

        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(mode_text)
        self.mode_combo.blockSignals(False)

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

    def _toggle_nodes_expand(self):
        """切换展开/收起状态"""
        self._is_nodes_expanded = not self._is_nodes_expanded
        self._update_nodes_card_height()

    # --- 辅助逻辑 ---
    def _get_variable_autocomplete_list(self):
        if not self.current_node: return []
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars: return []
        extra_keys = ['current_index', 'max_iterations', 'loop_mode']
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
        if self.current_node:
            self.current_node.model.set_property("loop_mode", mode_map.get(text, "count"))
            self.update_properties_trigger()

    def update_properties_trigger(self):
        # 触发父面板重新布局（由于配置容器切换了显隐）
        if hasattr(self.parent_panel, 'update_properties'):
            self.parent_panel.update_properties(self.current_node, node_changed=True)

    def _set_node_prop(self, key, value):
        if self.current_node:
            self.current_node.model.set_property(key, value)
            if key in ['loop_nums', 'max_iterations']:
                self.update_data(self.current_node)

    def _get_input_data(self, backdrop):
        data = []
        for input_port in backdrop.input_ports():
            for out_port in input_port.connected_ports():
                upstream = get_port_node(out_port)
                if upstream and hasattr(upstream, '_output_values'):
                    data.append(upstream._output_values.get(out_port.name(), None))
        return data if len(data) != 1 else data[0]

    def _calculate_total(self, node, flow_type):
        if flow_type == "loop":
            mode = node.model.get_property("loop_mode")
            return node.model.get_property("loop_nums") if mode == 'count' else node.model.get_property(
                "max_iterations")
        return len(self._get_input_data(node)) or 0

    def _on_internal_node_clicked(self, item):
        row = self._backdrop_internal_nodes_list.row(item)
        if hasattr(self, '_current_internal_nodes') and 0 <= row < len(self._current_internal_nodes):
            self.main_window.canvas_widget.zoom_to_nodes([self._current_internal_nodes[row]._view])

    def _open_long_text_editor(self):
        keys = self._get_variable_autocomplete_list()
        dialog = LongTextEditorDialog(
            content=self.condition_edit.toPlainText(), extra_keys=keys,
            parent=self.window(), main_window=self.main_window
        )
        if dialog.exec():
            self.condition_edit.setPlainText(dialog.text_edit.toPlainText().strip())