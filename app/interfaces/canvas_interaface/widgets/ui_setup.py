# -*- coding: utf-8 -*-
import os
from pathlib import Path
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from qfluentwidgets import TransparentToolButton, FluentIcon, RoundMenu, Action, LineEdit, ComboBox
from qfluentwidgets.components.widgets.card_widget import CardSeparator
from qtpy import QtGui, QtCore

from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.side_dock_area import SideDockArea
from .canvas_left_panel import LeftPanel
from ..constants import (BUTTONS_CONTAINER_X_OFFSET, DEFAULT_SPLITTER_SIZES,
                         PIPELINE_STYLE, PIPELINE_DIRECTION, MAX_VISIBLE_QUICK_BUTTONS, GRID_STYLE)


class CanvasUISetUp:

    def __init__(self, parent):
        self.parent = parent
        self.nav_view = None
        self.nodes_container = None
        self._hidden_quick_components = []

        # UI 引用
        self.env_combo = None
        self.run_btn = None
        self.pause_btn = None
        self.stop_btn = None
        self.save_btn = None
        self.export_model_btn = None
        self.close_btn = None
        self.name_container = None
        self.buttons_container = None
        self.canvas_controls_container = None
        self.btn_mode_toggle = None  # 框选/拖拽切换
        self.btn_zoom_fit = None  # 缩放至适应
        self.btn_minimap = None  # 缩略图开关

    def setup_ui(self):
        """第一阶段：构建纯 UI 框架（只负责实例化和布局，不负责位置微调和信号）"""
        # 1. 基础布局
        main_layout = QHBoxLayout(self.parent)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 2. 核心组件
        self.nav_panel = LeftPanel(self.parent)
        self.nav_view = self.nav_panel.draggable_tree.tree
        self.side_dock_area = SideDockArea(self.parent, "运行画布")

        # 3. 分割器
        self.splitter = ModernSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.nav_panel)
        self.splitter.addWidget(self.parent.canvas_widget)
        self.splitter.addWidget(self.side_dock_area)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.last_right_width = DEFAULT_SPLITTER_SIZES[2]

        self.splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.splitter)
        main_layout.addWidget(self.side_dock_area.tool_panel)

        # 4. 创建悬浮 UI 容器（仅实例化，坐标由 update_position 统一负责）
        self._create_environment_selector_base()
        self._create_floating_buttons_base()
        self._create_floating_nodes_base()
        self._create_canvas_controls_base()
        # 5. 初始化样式
        self._setup_pipeline_style()
        self._init_unified_font()

    def connect_signals(self):
        """第二阶段：绑定业务逻辑信号"""
        # --- 基础控制信号 ---
        self.close_btn.clicked.connect(lambda: (
            QTimer.singleShot(0, self.parent.close_current_canvas),
            self.parent.switch_to_parent()
        ))

        # --- 左侧固定工具栏信号 ---
        self.iterate_node.clicked.connect(
            lambda: self.parent.create_backdrop_node("control_flow.ControlFlowIterateNode"))
        self.loop_node.clicked.connect(lambda: self.parent.create_backdrop_node("control_flow.ControlFlowLoopNode"))
        self.branch_node.clicked.connect(lambda: self.parent.create_next_node("control_flow.ControlFlowBranchNode"))
        self.echart_node.clicked.connect(lambda: self.parent.create_next_node("visualize.MediaNode"))
        self.code_node.clicked.connect(lambda: self.parent.create_next_node("dynamic.DYNAMIC_CODE"))
        self.note_node.clicked.connect(lambda: self.parent.create_backdrop_node("general.StickyNote", init_io=False))
        self.group_node.clicked.connect(lambda: self.parent.create_group_node())
        # --- 快捷组件管理 ---
        if hasattr(self.parent, 'quick_manager'):
            self.add_quick_btn.clicked.connect(self.parent.quick_manager.open_add_dialog)
            self.more_quick_button.clicked.connect(self._show_more_quick_menu)
            self._refresh_quick_buttons()
        # 1. 切换框选/拖拽模式
        self.btn_mode_toggle.clicked.connect(self._toggle_viewer_mode)
        # 2. 缩放至适应
        self.btn_zoom_fit.clicked.connect(
            lambda: self.parent.canvas_widget.zoom_to_nodes([n.view for n in self.parent.graph.all_nodes()])
        )
        # 3. 缩略图控制
        self.btn_minimap.clicked.connect(self._toggle_minimap)
        # --- 顶部名称标签 ---
        self.create_name_label()

        # 立即刷一次坐标
        QTimer.singleShot(50, self.update_position)

    # ================= UI 基础构建 (无坐标偏移计算) =================

    def _create_environment_selector_base(self):
        self.env_container = QWidget(self.parent.canvas_widget)
        self.env_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        layout = QHBoxLayout(self.env_container)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        label = TransparentToolButton()
        label.setText("环境:")
        label.setFixedSize(50, 30)
        self.env_combo = ComboBox(self.env_container)
        self.env_combo.setFixedWidth(120)
        layout.addWidget(label)
        layout.addWidget(self.env_combo)
        self.env_container.show()

    def _create_floating_buttons_base(self):
        # 必须 parent 到 viewer 才能浮动在画布上
        self.buttons_container = QWidget(self.parent.graph.viewer())
        self.buttons_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        btn_layout = QHBoxLayout(self.buttons_container)
        btn_layout.setSpacing(0)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self.run_btn = TransparentToolButton(FluentIcon.PLAY, parent=self.parent.canvas_widget)
        self.pause_btn = TransparentToolButton(FluentIcon.PAUSE, parent=self.parent.canvas_widget)
        self.stop_btn = TransparentToolButton(get_icon("停止"), parent=self.parent.canvas_widget)
        self.save_btn = TransparentToolButton(FluentIcon.SAVE, parent=self.parent.canvas_widget)
        self.export_model_btn = TransparentToolButton(FluentIcon.SHARE, parent=self.parent.canvas_widget)
        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, parent=self.parent.canvas_widget)

        for btn in [self.run_btn, self.pause_btn, self.stop_btn, self.save_btn, self.export_model_btn, self.close_btn]:
            btn_layout.addWidget(btn)

        self.pause_btn.hide()
        self.stop_btn.hide()
        self.buttons_container.show()

    def _create_floating_nodes_base(self):
        self.nodes_container = QWidget(self.parent.canvas_widget)
        self.nodes_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.node_layout = QVBoxLayout(self.nodes_container)
        self.node_layout.setSpacing(5)
        self.node_layout.setContentsMargins(0, 0, 0, 0)

        # 核心控制节点图标
        self.iterate_node = self._build_tool_btn(get_icon("更新"), "创建迭代")
        self.loop_node = self._build_tool_btn(get_icon("无限"), "创建循环")
        self.branch_node = self._build_tool_btn(get_icon("条件分支"), "创建分支")
        self.group_node = self._build_tool_btn(get_icon("组节点"), "创建组节点")
        self.echart_node = self._build_tool_btn(get_icon("多媒体"), "媒体展示")
        self.code_node = self._build_tool_btn(get_icon("代码执行"), "代码节点")
        self.note_node = self._build_tool_btn(get_icon("文本注释"), "注释节点")

        for btn in [self.iterate_node, self.loop_node, self.branch_node, self.echart_node, self.code_node,
                    self.group_node, self.note_node]:
            self.node_layout.addWidget(btn)

        self.node_layout.addWidget(CardSeparator(self.nodes_container))

        self.visible_quick_container = QWidget(self.nodes_container)
        self.visible_quick_layout = QVBoxLayout(self.visible_quick_container)
        self.visible_quick_layout.setSpacing(3)
        self.visible_quick_layout.setContentsMargins(0, 0, 0, 0)
        self.node_layout.addWidget(self.visible_quick_container)

        self.more_quick_button = self._build_tool_btn(FluentIcon.MORE, "更多快捷组件")
        self.more_quick_menu = RoundMenu(parent=self.parent.canvas_widget)
        self.add_quick_btn = self._build_tool_btn(FluentIcon.ADD, "添加快捷组件")

        self.node_layout.addWidget(self.more_quick_button)
        self.node_layout.addWidget(self.add_quick_btn)
        self.nodes_container.show()

    def _create_canvas_controls_base(self):
        """创建右下角画布控制栏"""
        self.canvas_controls_container = QWidget(self.parent.graph.viewer())
        self.canvas_controls_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        layout = QHBoxLayout(self.canvas_controls_container)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 5, 10, 5)

        # 1. 模式切换按钮 (框选 vs 拖拽)
        # NodeGraphQt 默认左键是框选，按住 Alt 是拖拽。我们要实现点击切换默认行为
        self.btn_mode_toggle = self._build_tool_btn(get_icon("框选"), "当前模式: 框选 (点击切换为拖拽)")
        self.btn_mode_toggle.setCheckable(True)
        self.btn_mode_toggle.setChecked(True)  # 默认拖拽

        # 2. 缩放至适应按钮
        self.btn_zoom_fit = self._build_tool_btn(FluentIcon.ZOOM_IN, "缩放至适应 (快捷键: F)")

        # 3. 缩略图开关
        self.btn_minimap = self._build_tool_btn(FluentIcon.TILES, "显示/隐藏缩略图")
        self.btn_minimap.setCheckable(True)
        self.btn_minimap.setChecked(True)  # 默认开启

        layout.addWidget(self.btn_mode_toggle)
        layout.addWidget(self.btn_zoom_fit)
        layout.addWidget(self.btn_minimap)

        # 设置容器背景样式（毛玻璃或半透明）
        self.canvas_controls_container.setStyleSheet("""
            QWidget {
                background: rgba(40, 40, 40, 180);
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
        """)
        self.canvas_controls_container.show()

    def _build_tool_btn(self, icon, tooltip):
        btn = TransparentToolButton(icon, parent=self.parent.canvas_widget)
        btn.setIconSize(QSize(18, 18))
        btn.setFixedSize(24, 24)
        btn.setToolTip(tooltip)
        return btn

    # ================= 动态定位逻辑 (核心修正点) =================

    def update_position(self):
        """统一计算所有悬浮组件的坐标，解决缩放和初始化错位问题"""
        if not self.parent.canvas_widget or not self.parent.canvas_widget.isVisible():
            return

        canvas_w = self.parent.canvas_widget.width()
        canvas_h = self.parent.canvas_widget.height()

        # 1. 环境选择器 (左上角)
        if hasattr(self, 'env_container') and self.env_container:
            self.env_container.move(0, 5)

        # 2. 功能按钮组 (右上角 - 严格对齐原逻辑)
        if self.buttons_container:
            # 原逻辑：viewer().width() - BUTTONS_CONTAINER_X_OFFSET
            # 注意：此处确保 offset 减去的是容器自身的宽度，或者使用你的固定常量
            target_x = canvas_w - BUTTONS_CONTAINER_X_OFFSET
            self.buttons_container.move(max(0, target_x), 5)

        # 3. 节点工具栏 (左侧垂直居中)
        if self.nodes_container:
            self.nodes_container.adjustSize()
            container_h = self.nodes_container.height()
            target_y = (canvas_h - container_h) // 2
            self.nodes_container.move(0, max(50, target_y))

        # 4. 工作流名称 (顶部水平居中)
        if self.name_container:
            name_edit = self.name_container.findChild(LineEdit)
            if name_edit:
                self._update_name_label_width(name_edit)
                target_x = (canvas_w - self.name_container.width()) // 2
                self.name_container.move(max(0, target_x), 0)

        if hasattr(self, 'canvas_controls_container') and self.canvas_controls_container:
            self.canvas_controls_container.adjustSize()
            ctrl_w = self.canvas_controls_container.width()
            ctrl_h = self.canvas_controls_container.height()

            # 距离右边 20px，底边 20px
            target_x = canvas_w - ctrl_w - 20
            target_y = canvas_h - ctrl_h - 20
            self.canvas_controls_container.move(max(0, target_x), max(0, target_y))

    def _update_name_label_width(self, line_edit):
        """辅助计算名称输入框宽度"""
        text = line_edit.text() or " "
        font_metrics = line_edit.fontMetrics()
        text_width = font_metrics.horizontalAdvance(text)
        total_width = text_width + 24
        line_edit.setFixedWidth(max(total_width, 80))
        self.name_container.setFixedWidth(line_edit.width())

    def create_name_label(self):
        """初始化名称标签逻辑"""
        if self.name_container: return
        self.name_container = QWidget(self.parent.canvas_widget)
        self.name_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self.name_label = LineEdit(self.name_container)
        self.name_label.setStyleSheet(
            "LineEdit { background: transparent; border: none; color: white; font-size: 18px; font-weight: bold; }")
        self.name_label.setText(self.parent.workflow_name)
        self.name_label.setReadOnly(True)

        layout = QHBoxLayout(self.name_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.name_label)
        self.name_container.show()
        self.update_position()

    def _refresh_quick_buttons(self):
        """刷新快捷按钮区域"""
        if not hasattr(self.parent, 'quick_manager') or not self.parent.quick_manager:
            return

        all_quick_components = self.parent.quick_manager.get_quick_components()

        # 清空布局
        while self.visible_quick_layout.count():
            child = self.visible_quick_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        self.more_quick_menu.clear()
        self._hidden_quick_components = []

        for i, qc in enumerate(all_quick_components):
            full_path = qc["full_path"]
            icon_data = qc.get("icon_path")

            if i >= MAX_VISIBLE_QUICK_BUTTONS:
                self._hidden_quick_components.append((full_path, icon_data))
                self.more_quick_button.show()
                continue

            icon = self._get_qc_icon(icon_data)
            btn = self._build_tool_btn(icon, f"创建 {os.path.basename(full_path)}")
            btn.clicked.connect(lambda _, fp=full_path, idat=icon_data: self.parent.create_next_node(fp, idat))

            # 右键菜单
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn, fp=full_path: self._show_quick_button_menu(b, fp, pos))
            self.visible_quick_layout.addWidget(btn)

        if not self._hidden_quick_components:
            self.more_quick_button.hide()

        # 刷新后重新计算高度和位置
        QTimer.singleShot(0, self.update_position)

    def _get_qc_icon(self, icon_path):
        if not icon_path: return FluentIcon.APPLICATION
        if icon_path.startswith("builtin:\\"):
            icon_name = icon_path.split("\\")[-1]
            return FluentIcon[icon_name]
            icon_path = f":/qfluentwidgets/images/icons/{FluentIcon[icon_name].value}_white.svg"

        return QtGui.QIcon(icon_path)

    def _show_more_quick_menu(self):
        self.more_quick_menu.clear()
        for fp, ip in self._hidden_quick_components:
            action = Action(self._get_qc_icon(ip), os.path.basename(fp).replace('.py', ''),
                            parent=self.parent.canvas_widget)
            action.triggered.connect(lambda _, path=fp, icon=ip: self.parent.create_next_node(path, icon))
            self.more_quick_menu.addAction(action)
        self.more_quick_menu.exec_(self.more_quick_button.mapToGlobal(QPoint(0, self.more_quick_button.height())))

    def _show_quick_button_menu(self, button, full_path, pos):
        menu = RoundMenu(parent=self.parent.canvas_widget)
        menu.addAction(Action("移除", triggered=lambda: self.parent.quick_manager.remove_component(full_path)))
        menu.exec_(button.mapToGlobal(pos))

    # ================= 属性面板/分割器控制 =================
    @property
    def node_doc(self):
        return self.side_dock_area.get_tool_instance("节点说明")

    @property
    def property_panel(self):
        return self.side_dock_area.get_tool_instance("属性面板")

    @property
    def dependency_checker(self):
        return self.side_dock_area.get_tool_instance("依赖检查")

    @property
    def llm_chatter(self):
        return self.side_dock_area.get_tool_instance("大模型对话")

    @property
    def ipython_console(self):
        return self.side_dock_area.get_tool_instance("IPython 控制台")

    @property
    def log_window(self):
        return self.side_dock_area.get_tool_instance("模型日志")

    def _setup_pipeline_style(self):
        config = self.parent.config
        self.parent.graph.set_grid_mode(GRID_STYLE.get(config.canvas_grid_mode.value))
        self.parent.graph.set_pipe_style(PIPELINE_STYLE.get(config.canvas_pipelayout.value))
        self.parent.graph.set_layout_direction(PIPELINE_DIRECTION.get(config.canvas_direction.value))

    def _init_unified_font(self):
        font_name = getattr(self.parent.config.canvas_font_type, 'value', "Microsoft YaHei")
        self.parent.setStyleSheet(f'QWidget {{ font-family: "{font_name}"; }}')

    def show_splitter(self):
        self.side_dock_area.show()
        sizes = self.splitter.sizes()
        sizes[2] = self.last_right_width if self.last_right_width > 50 else 300
        self.splitter.setSizes(sizes)

    def hide_splitter(self):
        sizes = self.splitter.sizes()
        if sizes[2] > 0: self.last_right_width = sizes[2]
        sizes[2] = 0
        self.splitter.setSizes(sizes)
        self.side_dock_area.hide()

    def _toggle_viewer_mode(self):
        """切换左键模式：框选 vs 导航"""
        viewer = self.parent.graph.viewer()
        if self.btn_mode_toggle.isChecked():
            # 切换为框选模式
            viewer.set_navigation_mode(False)  # 0: MODE_SELECTION
            self.btn_mode_toggle.setIcon(get_icon("框选"))
            self.btn_mode_toggle.setToolTip("当前模式: 框选 (点击切换为拖拽)")
        else:
            # 切换为拖拽模式
            viewer.set_navigation_mode(True)  # 1: MODE_NAVIGATION (Panning)
            self.btn_mode_toggle.setIcon(FluentIcon.MOVE)
            self.btn_mode_toggle.setToolTip("当前模式: 拖拽 (点击切换为框选)")

    def _toggle_minimap(self):
        """控制 NodeGraphQt 的缩略图显示"""
        # NodeGraphQt 的 overview 实际上是 QGraphicsView 的一部分
        viewer = self.parent.graph.viewer()
        overview = viewer.get_scene_overview()
        if overview:
            visible = self.btn_minimap.isChecked()
            overview.setVisible(visible)

    def destroy_all(self):
        try:
            for attr in ['splitter', 'env_container', 'buttons_container', 'nodes_container', 'name_container']:
                obj = getattr(self, attr, None)
                if obj:
                    obj.setParent(None)
                    obj.deleteLater()
            self.parent = None
        except:
            pass