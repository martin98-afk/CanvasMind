# -*- coding: utf-8 -*-
import os
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, QPoint
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from qfluentwidgets import TransparentToolButton, FluentIcon, RoundMenu, Action, LineEdit, ComboBox
from qfluentwidgets.components.widgets.card_widget import CardSeparator
from qtpy import QtGui, QtCore

from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.side_dock_area import SideDockArea
from app.interfaces.canvas_interaface.widgets.draggable_component_tree import DraggableTreePanel
from .canvas_left_panel import LeftPanel
from ..constants import BUTTONS_CONTAINER_X_OFFSET, DEFAULT_SPLITTER_SIZES, PIPELINE_STYLE, PIPELINE_DIRECTION, \
    MAX_VISIBLE_QUICK_BUTTONS, GRID_STYLE, HIDE_SPLITTER_SIZES


class CanvasUISetUp:
    def __init__(self, parent):
        self.parent = parent
        self.nav_view = None
        self.nodes_container = None

    # --- ui构建 --- 
    def setup_ui(self):
        # 布局
        self._setup_pipeline_style()
        # 节点拖拽树
        self.nav_panel = LeftPanel(self.parent)
        self.nav_view =  self.nav_panel.draggable_tree.tree
        # 属性面板
        self.side_dock_area = SideDockArea(self.parent, "运行画布")
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
        self.create_environment_selector()
        self.create_floating_buttons()
        self.create_floating_nodes()

    @property
    def property_panel(self):
        return self.side_dock_area.get_tool_instance("属性面板")

    @property
    def llm_chatter(self):
        return self.side_dock_area.get_tool_instance("大模型对话")

    @property
    def ipython_console(self):
        return self.side_dock_area.get_tool_instance("IPython 控制台")

    @property
    def log_window(self):
        return self.side_dock_area.get_tool_instance("模型日志")

    def hide_splitter(self):
        """强制 splitter 回到默认尺寸，无视用户拖动历史"""
        self.splitter.setSizes(HIDE_SPLITTER_SIZES)
        self.splitter.update()

    def show_splitter(self):
        """强制 splitter 恢复到默认尺寸"""
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.splitter.update()

    def create_environment_selector(self):
        container = QWidget(self.parent.canvas_widget)
        container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        container.move(0, 5)
        layout = QHBoxLayout(container)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        label = TransparentToolButton()
        label.setText("环境:")
        label.setFixedSize(50, 30)

        self.env_combo = ComboBox(container)
        self.env_combo.setFixedWidth(120)

        layout.addWidget(label)
        layout.addWidget(self.env_combo)
        layout.addStretch()
        container.setLayout(layout)
        container.show()

    def create_floating_buttons(self):
        self.buttons_container = QWidget(self.parent.graph.viewer())
        self.buttons_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.buttons_container.move(self.parent.graph.viewer().width() - BUTTONS_CONTAINER_X_OFFSET, 0)
        env_layout = QHBoxLayout(self.buttons_container)
        env_layout.setSpacing(0)
        env_layout.setContentsMargins(0, 0, 0, 0)

        # ▶️ 运行
        self.run_btn = TransparentToolButton(FluentIcon.PLAY, parent=self.parent.canvas_widget)
        self.run_btn.setToolTip("运行工作流")
        env_layout.addWidget(self.run_btn)

        # ⏸️ 暂停 / ▶️ 继续
        self.pause_btn = TransparentToolButton(FluentIcon.PAUSE, parent=self.parent.canvas_widget)
        self.pause_btn.setToolTip("暂停工作流")
        self.pause_btn.hide()
        env_layout.addWidget(self.pause_btn)

        # ⏹️ 停止（强制终止）
        self.stop_btn = TransparentToolButton(get_icon("停止"), parent=self.parent.canvas_widget)
        self.stop_btn.setToolTip("停止工作流")
        self.stop_btn.hide()
        env_layout.addWidget(self.stop_btn)

        # 其他按钮
        self.save_btn = TransparentToolButton(FluentIcon.SAVE, parent=self.parent.canvas_widget)
        self.save_btn.setToolTip("保存工作流")
        env_layout.addWidget(self.save_btn)

        self.export_model_btn = TransparentToolButton(FluentIcon.SHARE, parent=self.parent.canvas_widget)
        self.export_model_btn.setToolTip("导出选中节点为独立模型")
        env_layout.addWidget(self.export_model_btn)

        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, parent=self.parent.canvas_widget)
        self.close_btn.setToolTip("关闭当前画布")
        env_layout.addWidget(self.close_btn)

        env_layout.addStretch()
        self.buttons_container.setLayout(env_layout)
        self.buttons_container.show()

    def create_floating_nodes(self):
        self.nodes_container = QWidget(self.parent.canvas_widget)
        self.nodes_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._update_nodes_container_position()
        self.node_layout = QVBoxLayout(self.nodes_container)
        self.node_layout.setSpacing(5)
        self.node_layout.setContentsMargins(0, 0, 0, 0)

        # === 固定控制流按钮 ===
        self.iterate_node = TransparentToolButton(get_icon("更新"), parent=self.parent.canvas_widget)
        self.iterate_node.setIconSize(QSize(18, 18))
        self.iterate_node.setFixedSize(24, 24)
        self.iterate_node.setToolTip("创建迭代")
        self.iterate_node.clicked.connect(
            lambda: self.parent.create_backdrop_node("ControlFlowIterateNode")
        )
        self.node_layout.addWidget(self.iterate_node)

        self.loop_node = TransparentToolButton(get_icon("无限"), parent=self.parent.canvas_widget)
        self.loop_node.setIconSize(QSize(18, 18))
        self.loop_node.setFixedSize(24, 24)
        self.loop_node.setToolTip("创建循环")
        self.loop_node.clicked.connect(lambda: self.parent.create_backdrop_node("ControlFlowLoopNode"))
        self.node_layout.addWidget(self.loop_node)

        self.branch_node = TransparentToolButton(get_icon("条件分支"), parent=self.parent.canvas_widget)
        self.branch_node.setIconSize(QSize(18, 18))
        self.branch_node.setFixedSize(24, 24)
        self.branch_node.setToolTip("创建分支")
        self.branch_node.clicked.connect(lambda: self.parent.create_next_node("control_flow.ControlFlowBranchNode"))
        self.node_layout.addWidget(self.branch_node)

        self.echart_node = TransparentToolButton(get_icon("图表"), parent=self.parent.canvas_widget)
        self.echart_node.setIconSize(QSize(18, 18))
        self.echart_node.setFixedSize(24, 24)
        self.echart_node.setToolTip("创建图表节点")
        self.echart_node.clicked.connect(lambda: self.parent.create_next_node("visualize.EchartsNode"))
        self.node_layout.addWidget(self.echart_node)

        self.code_node = TransparentToolButton(get_icon("代码执行"), parent=self.parent.canvas_widget)
        self.code_node.setIconSize(QSize(18, 18))
        self.code_node.setFixedSize(24, 24)
        self.code_node.setToolTip("创建代码编辑")
        self.code_node.clicked.connect(lambda: self.parent.create_next_node("dynamic.DYNAMIC_CODE"))
        self.node_layout.addWidget(self.code_node)

        self.tool_node = TransparentToolButton(get_icon("工具"), parent=self.parent.canvas_widget)
        self.tool_node.setIconSize(QSize(18, 18))
        self.tool_node.setFixedSize(24, 24)
        self.tool_node.setToolTip("创建工具调用")
        self.tool_node.clicked.connect(
            lambda: self.parent.create_next_node("dynamic.StatusDynamicNode_大模型组件_工具调用",
                                          icon_path="icons/工具.svg")
        )
        self.node_layout.addWidget(self.tool_node)

        # === 分隔线 ===
        self.node_layout.addWidget(CardSeparator(self.nodes_container))

        # === 可显示的快捷按钮容器 ===
        self.visible_quick_container = QWidget(self.nodes_container)  # 用于存放可见的快捷按钮
        self.visible_quick_layout = QVBoxLayout(self.visible_quick_container)
        self.visible_quick_layout.setSpacing(3)
        self.visible_quick_layout.setContentsMargins(0, 0, 0, 0)  # 调整边距
        self.node_layout.addWidget(self.visible_quick_container)

        # === "更多"按钮及其菜单 ===
        self.more_quick_button = TransparentToolButton(FluentIcon.MORE, parent=self.parent.canvas_widget)  # 使用 FluentIcon.MORE 或自定义图标
        self.more_quick_button.setIconSize(QSize(18, 18))
        self.more_quick_button.setFixedSize(24, 24)
        self.more_quick_button.setToolTip("更多快捷组件")
        self.more_quick_menu = RoundMenu(parent=self.parent.canvas_widget)  # 使用 qfluentwidgets 的菜单
        self.more_quick_button.clicked.connect(self._show_more_quick_menu)

        # 添加 "更多" 按钮到布局
        self.node_layout.addWidget(self.more_quick_button)

        # === 原来的 "+" 按钮（始终在最后）===
        self.add_quick_btn = TransparentToolButton(FluentIcon.ADD, parent=self.parent.canvas_widget)
        self.add_quick_btn.setIconSize(QSize(18, 18))
        self.add_quick_btn.setFixedSize(24, 24)
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
            if icon_path:
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

                if icon_path:
                    icon = QtGui.QIcon(icon_path)
                elif icon_path.startswith("builtin:\\"):
                    icon_name = icon_path.split("\\")[-1]
                    icon = FluentIcon[icon_name]
                    icon_path = f":/qfluentwidgets/images/icons/{FluentIcon[icon_name].value}_white.svg"
                else:
                    icon = FluentIcon.APPLICATION
                    icon_path = f":/qfluentwidgets/images/icons/{FluentIcon.APPLICATION.value}_white.svg"

                btn = TransparentToolButton(icon, parent=self.parent.canvas_widget)
                btn.setIconSize(QSize(18, 18))
                btn.setFixedSize(24, 24)
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
        self.parent.file_path = Path("canvas_files") / "workflows" / text / f"{text}.workflow.json"
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

    def destroy_all(self):
        """彻底销毁 UI 所有动态创建的内容，防止内存泄漏"""
        try:
            # 1. 断开 splitter 信号（如有）
            if hasattr(self, 'splitter') and self.splitter:
                self.splitter.blockSignals(True)
                self.splitter.setParent(None)
                self.splitter.deleteLater()
                self.splitter = None

            # 2. 销毁 nav_panel（组件树）
            if hasattr(self, 'nav_panel') and self.nav_panel:
                self.nav_panel.setParent(None)
                self.nav_panel.deleteLater()
                self.nav_panel = None
                self.nav_view = None

            # 3. 销毁 side_dock_area（属性面板等）
            if hasattr(self, 'side_dock_area') and self.side_dock_area:
                self.side_dock_area.cleanup()
                self.side_dock_area.setParent(None)
                self.side_dock_area.deleteLater()
                self.side_dock_area = None

            # 4. 销毁悬浮按钮容器
            if hasattr(self, 'buttons_container') and self.buttons_container:
                self.buttons_container.setParent(None)
                self.buttons_container.deleteLater()
                self.buttons_container = None
                self.run_btn = None
                self.stop_btn = None
                self.save_btn = None
                self.export_model_btn = None
                self.close_btn = None

            # 5. 销毁快捷节点容器
            if hasattr(self, 'nodes_container') and self.nodes_container:
                self.nodes_container.setParent(None)
                self.nodes_container.deleteLater()
                self.nodes_container = None

            # 6. 销毁名称标签
            if hasattr(self, 'name_container') and self.name_container:
                self.name_container.setParent(None)
                self.name_container.deleteLater()
                self.name_container = None

            # 7. 销毁环境选择器
            if hasattr(self, 'env_combo') and self.env_combo:
                container = self.env_combo.parent()
                if container:
                    container.setParent(None)
                    container.deleteLater()
                self.env_combo = None

            # 8. 断开 parent 引用（谨慎！确保 parent 不依赖这些）
            self.parent = None

        except Exception as e:
            from loguru import logger
            logger.warning(f"CanvasUISetUp.destroy_all() 遇到异常（可忽略）: {e}")