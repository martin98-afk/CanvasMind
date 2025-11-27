# -*- coding: utf-8 -*-
import os

from PyQt5.QtCore import Qt, QSize, QPoint
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from qfluentwidgets import TransparentToolButton, FluentIcon, RoundMenu, Action, LineEdit
from qtpy import QtGui, QtCore

from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.side_dock_area import SideDockArea
from app.widgets.tree_widget.draggable_component_tree import DraggableTreePanel
from ..constants import BUTTONS_CONTAINER_X_OFFSET, DEFAULT_SPLITTER_SIZES, PIPELINE_STYLE, PIPELINE_DIRECTION, \
    MAX_VISIBLE_QUICK_BUTTONS, GRID_STYLE, HIDE_SPLITTER_SIZES


class CanvasUISetUp:
    def __init__(self, parent):
        self.parent = parent
        self.nav_view = None
        self.property_panel = None
        self.nodes_container = None

    # --- ui构建 --- 
    def setup_ui(self):
        # 布局
        self._setup_pipeline_style()
        # 节点拖拽树
        self.nav_panel = DraggableTreePanel(self.parent)
        self.nav_view =  self.nav_panel.tree
        # 属性面板
        self.side_dock_area = SideDockArea(self.parent)
        self.property_panel = self.side_dock_area.get_tool_instance("属性面板")
        self.ipython_console = self.side_dock_area.get_tool_instance("IPython 控制台")
        self.variable_explorer = self.side_dock_area.get_tool_instance("变量浏览器")

        main_layout = QHBoxLayout(self.parent)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.splitter = ModernSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.nav_panel)
        self.splitter.addWidget(self.parent.canvas_widget)
        self.splitter.addWidget(self.side_dock_area)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)

        # 设置分割器的拉伸因子，确保画布区域优先扩展
        self.splitter.setStretchFactor(0, 0)  # 左侧导航不拉伸
        self.splitter.setStretchFactor(1, 1)  # 中间画布拉伸（主要区域）
        self.splitter.setStretchFactor(2, 0)  # 右侧属性不拉伸
        main_layout.addWidget(self.splitter)
        main_layout.addWidget(self.side_dock_area.tool_panel)

        # 创建悬浮按钮和环境选择
        self.parent.environment_manager.create_environment_selector()
        self.create_floating_buttons()
        self.create_floating_nodes()

    def hide_splitter(self):
        """强制 splitter 回到默认尺寸，无视用户拖动历史"""
        self.splitter.setSizes(HIDE_SPLITTER_SIZES)
        # 可选：刷新布局
        self.splitter.update()

    def show_splitter(self):
        """强制 splitter 恢复到默认尺寸"""
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        # 可选：刷新布局
        self.splitter.update()

    def create_floating_buttons(self):
        self.buttons_container = QWidget(self.parent.graph.viewer())
        self.buttons_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.buttons_container.move(self.parent.graph.viewer().width() - BUTTONS_CONTAINER_X_OFFSET, 5)
        env_layout = QHBoxLayout(self.buttons_container)
        env_layout.setSpacing(2)
        env_layout.setContentsMargins(0, 0, 0, 0)
        self.run_btn = TransparentToolButton(FluentIcon.PLAY, parent=self.parent.canvas_widget)
        self.run_btn.setToolTip("运行工作流")
        self.run_btn.clicked.connect(self.parent.canvas_runner.run_workflow)
        env_layout.addWidget(self.run_btn)
        self.stop_btn = TransparentToolButton(FluentIcon.PAUSE, parent=self.parent.canvas_widget)
        self.stop_btn.setToolTip("停止运行")
        self.stop_btn.clicked.connect(self.parent.canvas_runner.stop_workflow)
        self.stop_btn.hide()
        env_layout.addWidget(self.stop_btn)
        self.save_btn = TransparentToolButton(FluentIcon.SAVE, parent=self.parent.canvas_widget)
        self.save_btn.setToolTip("保存工作流")
        self.save_btn.clicked.connect(self.parent.save_full_workflow)
        env_layout.addWidget(self.save_btn)
        self.export_model_btn = TransparentToolButton(FluentIcon.SHARE, parent=self.parent.canvas_widget)
        self.export_model_btn.setToolTip("导出选中节点为独立模型")
        self.export_model_btn.clicked.connect(self.parent.export_selected_nodes_as_project)
        env_layout.addWidget(self.export_model_btn)
        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, parent=self.parent.canvas_widget)
        self.close_btn.setToolTip("关闭当前画布")
        self.close_btn.clicked.connect(
            lambda: (
                self.parent.switch_to_parent(),
                QtCore.QTimer.singleShot(300, self.parent.close_current_canvas)
            )
        )
        env_layout.addWidget(self.close_btn)
        env_layout.addStretch()
        self.buttons_container.setLayout(env_layout)
        self.buttons_container.show()

    def create_floating_nodes(self):
        self.nodes_container = QWidget(self.parent.canvas_widget)
        self.nodes_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._update_nodes_container_position()
        self.node_layout = QVBoxLayout(self.nodes_container)
        self.node_layout.setSpacing(3)
        self.node_layout.setContentsMargins(0, 0, 0, 0)

        # === 固定控制流按钮 ===
        self.iterate_node = TransparentToolButton(get_icon("更新"), parent=self.parent.canvas_widget)
        self.iterate_node.setIconSize(QSize(20, 20))
        self.iterate_node.setToolTip("创建迭代")
        self.iterate_node.clicked.connect(
            lambda: self.parent.create_backdrop_node("ControlFlowIterateNode")
        )
        self.node_layout.addWidget(self.iterate_node)

        self.loop_node = TransparentToolButton(get_icon("无限"), parent=self.parent.canvas_widget)
        self.loop_node.setIconSize(QSize(20, 20))
        self.loop_node.setToolTip("创建循环")
        self.loop_node.clicked.connect(lambda: self.parent.create_backdrop_node("ControlFlowLoopNode"))
        self.node_layout.addWidget(self.loop_node)

        self.branch_node = TransparentToolButton(get_icon("条件分支"), parent=self.parent.canvas_widget)
        self.branch_node.setIconSize(QSize(20, 20))
        self.branch_node.setToolTip("创建分支")
        self.branch_node.clicked.connect(lambda: self.parent.create_next_node("control_flow.ControlFlowBranchNode"))
        self.node_layout.addWidget(self.branch_node)

        self.code_node = TransparentToolButton(get_icon("代码执行"), parent=self.parent.canvas_widget)
        self.code_node.setIconSize(QSize(20, 20))
        self.code_node.setToolTip("创建代码编辑")
        self.code_node.clicked.connect(lambda: self.parent.create_next_node("dynamic.DYNAMIC_CODE"))
        self.node_layout.addWidget(self.code_node)

        self.tool_node = TransparentToolButton(get_icon("工具"), parent=self.parent.canvas_widget)
        self.tool_node.setIconSize(QSize(20, 20))
        self.tool_node.setToolTip("创建工具调用")
        self.tool_node.clicked.connect(
            lambda: self.parent.create_next_node("dynamic.StatusDynamicNode_大模型组件_工具调用",
                                          icon_path="icons/工具.svg")
        )
        self.node_layout.addWidget(self.tool_node)

        # === 分隔线 ===
        from PyQt5.QtWidgets import QFrame
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setStyleSheet("color: #555;")
        self.node_layout.addWidget(self.separator)

        # === 可显示的快捷按钮容器 ===
        self.visible_quick_container = QWidget(self.nodes_container)  # 用于存放可见的快捷按钮
        self.visible_quick_layout = QVBoxLayout(self.visible_quick_container)
        self.visible_quick_layout.setSpacing(3)
        self.visible_quick_layout.setContentsMargins(0, 0, 0, 0)  # 调整边距
        self.node_layout.addWidget(self.visible_quick_container)

        # === "更多"按钮及其菜单 ===
        self.more_quick_button = TransparentToolButton(FluentIcon.MORE, parent=self.parent.canvas_widget)  # 使用 FluentIcon.MORE 或自定义图标
        self.more_quick_button.setIconSize(QSize(20, 20))
        self.more_quick_button.setToolTip("更多快捷组件")
        self.more_quick_menu = RoundMenu(parent=self.parent.canvas_widget)  # 使用 qfluentwidgets 的菜单
        self.more_quick_button.clicked.connect(self._show_more_quick_menu)

        # 添加 "更多" 按钮到布局
        self.node_layout.addWidget(self.more_quick_button)

        # === 原来的 "+" 按钮（始终在最后）===
        self.add_quick_btn = TransparentToolButton(FluentIcon.ADD, parent=self.parent.canvas_widget)
        self.add_quick_btn.setIconSize(QSize(20, 20))
        self.add_quick_btn.setToolTip("添加快捷组件")
        self.add_quick_btn.clicked.connect(self.parent.quick_manager.open_add_dialog)
        self.node_layout.addWidget(self.add_quick_btn)

        self.nodes_container.setLayout(self.node_layout)
        self.nodes_container.show()

        # 初次加载快捷组件
        self._refresh_quick_buttons()

    def _show_more_quick_menu(self):
        """显示“更多”按钮的菜单"""
        # Clear the menu first
        self.more_quick_menu.clear()
        # Add actions for hidden quick components
        for full_path, icon_path in self._hidden_quick_components:
            comp_name = os.path.basename(full_path).replace('.py', '')
            if icon_path and os.path.exists(icon_path):
                icon = QtGui.QIcon(icon_path)
            elif icon_path.startswith("builtin:\\"):
                icon_name = icon_path.split("\\")[-1]
                icon = FluentIcon[icon_name]
            else:
                icon = FluentIcon.APPLICATION
            action = Action(
                icon, f"创建 {comp_name}",
                triggered=lambda _, fp=full_path, ip=icon_path: self.parent.create_next_node(fp, ip),
                parent=self.parent.canvas_widget
            )
            action.setProperty("full_path", full_path)
            self.more_quick_menu.addAction(action)
        # Show the menu
        self.more_quick_menu.exec_(self.more_quick_button.mapToGlobal(QPoint(0, self.more_quick_button.height())))

    def _update_nodes_container_position(self):
        if not hasattr(self, 'nodes_container') or not self.parent.canvas_widget:
            return
        # 计算 layout 所需高度
        self.nodes_container.adjustSize()  # ← 关键：让容器按内容自适应高度
        height = self.nodes_container.height()
        # 垂直居中（可调）
        y = max(50, (self.parent.canvas_widget.height() - height) // 2)
        self.nodes_container.move(0, y)

    def _refresh_quick_buttons(self):
        all_quick_components = self.parent.quick_manager.get_quick_components()
        # --- 清理现有按钮 ---
        # 清除可见容器中的按钮
        while self.visible_quick_layout.count():
            item = self.visible_quick_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 清空菜单
        self.more_quick_menu.clear()
        # 重置隐藏列表
        self._hidden_quick_components = []

        # --- 重新分配按钮 ---
        for i, qc in enumerate(all_quick_components):
            full_path = qc["full_path"]
            comp_name = os.path.basename(full_path).replace('.py', '')
            icon_path = qc.get("icon_path")

            if i > MAX_VISIBLE_QUICK_BUTTONS:
                self._hidden_quick_components.append((qc["full_path"], qc.get("icon_path")))
                self.more_quick_button.show()
            else:

                if icon_path and os.path.exists(icon_path):
                    icon = QtGui.QIcon(icon_path)
                elif icon_path.startswith("builtin:\\"):
                    icon_name = icon_path.split("\\")[-1]
                    icon = FluentIcon[icon_name]
                    icon_path = f":/qfluentwidgets/images/icons/{FluentIcon[icon_name].value}_white.svg"
                else:
                    icon = FluentIcon.APPLICATION
                    icon_path = f":/qfluentwidgets/images/icons/{FluentIcon.APPLICATION.value}_white.svg"

                btn = TransparentToolButton(icon, parent=self.parent.canvas_widget)
                btn.setIconSize(QSize(20, 20))
                btn.setToolTip(f"创建 {comp_name}")
                btn.setProperty("full_path", full_path)
                btn.clicked.connect(lambda _, ip=icon_path, fp=full_path: self.parent.create_next_node(fp, ip))

                # 右键菜单：删除
                btn.setContextMenuPolicy(Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, b=btn, fp=full_path: self._show_quick_button_menu(b, fp, pos)
                )
                self.visible_quick_layout.addWidget(btn)

        # 如果没有隐藏的组件，隐藏“更多”按钮
        if not self._hidden_quick_components:
            self.more_quick_button.hide()

        QtCore.QTimer.singleShot(0, self._update_nodes_container_position)

    def _show_quick_button_menu(self, button, full_path, pos):
        menu = RoundMenu()
        menu.addAction(
            Action("从快捷栏移除", triggered=lambda: self.parent.quick_manager.remove_component(full_path),
                   parent=self.parent.canvas_widget)
        )
        menu.exec_(button.mapToGlobal(pos))

    def create_name_label(self):
        self.name_container = QWidget(self.parent.canvas_widget)
        self.name_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        name_label = LineEdit(self.name_container)
        # 设置透明背景
        name_label.setStyleSheet("""
               LineEdit {
                   background: transparent;
                   border: none;
                   padding: 2px 4px;
                   color: white; /* 或你主题对应的文字颜色 */
                   font-size: 18px;
                   font-weight: bold;
               }
           """)
        name_label.setText(self.parent.workflow_name)
        name_label.textChanged.connect(self.update_workflow_name)
        self._update_name_label_width(name_label)
        name_layout = QHBoxLayout(self.name_container)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(5)
        name_layout.addWidget(name_label)
        name_layout.addStretch()
        self.name_container.setLayout(name_layout)
        self.name_container.show()
        self._position_name_container()

    def _update_name_label_width(self, line_edit):
        text = line_edit.text() or " "
        font_metrics = line_edit.fontMetrics()
        text_width = font_metrics.horizontalAdvance(text)
        padding = 24
        total_width = text_width + padding
        line_edit.setFixedWidth(max(total_width, 80))
        self.name_container.setFixedWidth(line_edit.width())

    def _position_name_container(self):
        name_edit = self.name_container.findChild(LineEdit)
        self._update_name_label_width(name_edit)
        container_width = self.name_container.width()
        x = max(0, (self.parent.canvas_widget.width() - container_width) // 2)
        self.name_container.move(x, 0)

    def update_workflow_name(self, text):
        self.parent.workflow_name = text
        name_edit = self.name_container.findChild(LineEdit)
        if name_edit:
            self._update_name_label_width(name_edit)
            QtCore.QTimer.singleShot(0, self._position_name_container)

    def update_position(self):
        self._update_nodes_container_position()
        self.buttons_container.move(self.parent.graph.viewer().width() - BUTTONS_CONTAINER_X_OFFSET, 5)
        if hasattr(self, "name_container"):
            self._position_name_container()

    def _setup_pipeline_style(self):
        self.parent.graph.set_grid_mode(GRID_STYLE.get(self.parent.config.canvas_grid_mode.value))
        self.parent.graph.set_pipe_style(
            PIPELINE_STYLE.get(self.parent.config.canvas_pipelayout.value)
        )
        self.parent.graph.set_layout_direction(
            PIPELINE_DIRECTION.get(self.parent.config.canvas_direction.value)
        )