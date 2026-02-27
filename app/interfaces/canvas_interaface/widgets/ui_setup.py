# -- coding: utf-8 --
import os

from PyQt5.QtCore import Qt, QSize, QPoint, QTimer
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFrame
from qfluentwidgets import (
    TransparentToolButton,
    FluentIcon,
    RoundMenu,
    Action,
    ComboBox,
    setFont,
    IconWidget,
    InfoBar,
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator
from qtpy import QtGui

from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.basic_widget.bread_crumb import Breadcrumb
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.side_dock_area import SideDockArea
from .canvas_left_panel import LeftPanel
from .canvas_setting_popup import CanvasSettingPopup
from .workflow_graph_manager import WorkflowCanvasManager
from ..constants import (
    DEFAULT_SPLITTER_SIZES,
    MAX_VISIBLE_QUICK_BUTTONS,
    GRID_STYLE,
    PIPELINE_STYLE,
    PIPELINE_DIRECTION,
)


class CanvasUISetUp:
    def __init__(self, parent):
        self.parent = parent
        self.nav_view = None
        self.nodes_container = None
        self._hidden_quick_components = []
        self.is_zen_mode = False

        # UI 引用
        self.env_combo = None
        self.run_btn = None
        self.pause_btn = None
        self.stop_btn = None
        self.save_btn = None
        self.export_model_btn = None
        self.close_btn = None
        self.btn_add_view = None  # 增加视角按钮
        self.btn_remove_view = None  # 减少视角按钮
        self.name_container = None
        self.buttons_container = None
        self.envs_container = None
        self.canvas_controls_container = None

        self.btn_mode_toggle = None
        self.btn_zoom_fit = None
        self.btn_canvas_setting = None
        self.btn_zen_mode = None
        self.view = None

        # 扩展引用
        self.btn_toggle_nav = None
        self.breadcrumb = None

        # 管理器
        self.canvas_manager = None

    def setup_ui(self):
        """第一阶段：构建纯 UI 框架"""
        main_layout = QHBoxLayout(self.parent)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. 核心布局组件
        self.nav_panel = LeftPanel(self.parent)
        self.nav_view = self.nav_panel.draggable_tree.tree

        # --- 使用 CanvasManager 替代原来的 Widget ---
        self.canvas_manager = WorkflowCanvasManager(self.parent)
        self.graph_widget = self.canvas_manager

        # 初始化主图
        self.canvas_manager.init_root_graph()

        # 初始引用
        self.graph = self.canvas_manager.current_graph()

        self.side_dock_area = SideDockArea(self.parent, "运行画布")

        self.splitter = ModernSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.nav_panel)
        self.splitter.addWidget(self.canvas_manager)  # 直接添加 Manager Widget
        self.splitter.addWidget(self.side_dock_area)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.last_right_width = DEFAULT_SPLITTER_SIZES[2]

        self.splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.splitter)
        main_layout.addWidget(self.side_dock_area.tool_panel)
        self.nav_panel.setVisible(False)

        # 2. 初始化悬浮磨砂面板
        self.create_name_label()
        self._create_env_and_buttons()  # 右上：环境+运行控制
        self._create_floating_nodes_base()  # 左侧：快捷工具
        self._create_canvas_controls_base()  # 右下：画布控制
        self._init_unified_font()

    def connect_signals(self):
        """第二阶段：绑定业务逻辑信号"""

        # --- 连接管理器信号 ---
        self.canvas_manager.current_graph_changed.connect(self._on_graph_changed)
        self.canvas_manager.navigation_changed.connect(self._update_breadcrumb_ui)

        # --- 顶部导航开关 ---
        if self.btn_toggle_nav:
            self.btn_toggle_nav.clicked.connect(self._toggle_nav_panel)

        # --- 基础控制信号 ---
        self.close_btn.clicked.connect(
            lambda: (
                QTimer.singleShot(0, self.parent.close_current_canvas),
                self.parent.switch_to_parent(),
            )
        )

        # --- 左侧功能按钮 ---
        self.iterate_node.clicked.connect(
            lambda: self.parent.create_backdrop_node(
                "control_flow.ControlFlowIterateNode"
            )
        )
        self.loop_node.clicked.connect(
            lambda: self.parent.create_backdrop_node("control_flow.ControlFlowLoopNode")
        )
        self.branch_node.clicked.connect(
            lambda: self.parent.create_next_node("control_flow.ControlFlowBranchNode")
        )
        self.echart_node.clicked.connect(
            lambda: self.parent.create_next_node("visualize.MediaNode")
        )
        self.code_node.clicked.connect(
            lambda: self.parent.create_next_node("dynamic.DYNAMIC_CODE")
        )
        self.ai_node.clicked.connect(lambda: self.parent.create_next_node("ai.AI_CODE"))
        self.note_node.clicked.connect(
            lambda: self.parent.create_backdrop_node(
                "general.StickyNote", init_io=False
            )
        )
        self.trigger_node.clicked.connect(
            lambda: self.parent.create_next_node("general.trigger")
        )

        if hasattr(self.parent, "quick_manager"):
            self.add_quick_btn.clicked.connect(
                lambda: self.parent.quick_manager.open_add_dialog(self.add_quick_btn)
            )
            self.more_quick_button.clicked.connect(self._show_more_quick_menu)
            self._refresh_quick_buttons()

        self.btn_mode_toggle.clicked.connect(self._toggle_viewer_mode)
        # 画布控制菜单
        view_split_right_action = Action(
            get_icon("向右拆分"), "向右拆分视角", parent=self.canvas_manager
        )
        view_split_right_action.triggered.connect(self._on_view_split_right)
        self.more_canvas_settings_menu.addAction(view_split_right_action)
        view_split_down_action = Action(
            get_icon("向下拆分"), "向下拆分视角", parent=self.canvas_manager
        )
        view_split_down_action.triggered.connect(self._on_view_split_down)
        self.more_canvas_settings_menu.addAction(view_split_down_action)
        view_remove_action = Action(
            FluentIcon.REMOVE, "关闭当前视角", parent=self.canvas_manager
        )
        view_remove_action.triggered.connect(
            lambda: self.canvas_manager.graph_splitter.remove_viewer()
        )
        self.more_canvas_settings_menu.addAction(view_remove_action)
        self.more_canvas_settings_button.clicked.connect(self._show_canvas_more_menu)
        self.btn_zoom_fit.clicked.connect(
            lambda: self.graph.viewer().zoom_to_nodes(
                [n.view for n in self.graph.all_nodes()]
            )
        )
        self.btn_zen_mode.clicked.connect(self.toggle_zen_mode)
        self.btn_canvas_setting.clicked.connect(self._show_canvas_settings)
        self.reboot_btn.clicked.connect(self.ipython_console.restart_kernel)
        # 强制刷新位置 (recalculate_size=True)
        QTimer.singleShot(100, lambda: self.update_position(recalculate_size=True))

    # ================= 信号响应 (新增) =================

    def _on_graph_changed(self, new_graph):
        """当底层 CanvasManager 切换了画布"""
        self.graph = new_graph
        self.update_position(recalculate_size=True)

    def _update_breadcrumb_ui(self, nav_list):
        """
        根据 Manager 发来的导航列表更新面包屑
        nav_list: [('0', 'Main'), ('1', 'Sub')...]
        """
        current_count = len(self.breadcrumb.items_data)
        target_count = len(nav_list)

        # 1. 增加 (进入子图)
        if target_count > current_count:
            for i in range(current_count, target_count):
                id_str, name = nav_list[i]
                self.breadcrumb.addItem(id_str, name)

        # 2. 减少 (返回上级)
        elif target_count < current_count:
            while len(self.breadcrumb.items_data) > target_count:
                self.breadcrumb.removeItem(self.breadcrumb.items_data[-1])

    # ================= 业务接口 =================

    def create_new_subgraph(self, name="未命名子图"):
        """【外部调用入口】创建子图"""
        # 委托给 Manager，Manager 会处理创建、同步环境、发射信号
        self.canvas_manager.create_sub_graph(name)

    def switch_to_graph_level(self, index):
        """保留此方法名以兼容旧调用，实际转发给 Manager"""
        self.canvas_manager.switch_to_level(index)

    def _on_breadcrumb_clicked(self, route_key):
        """点击面包屑项"""
        self.switch_to_graph_level(int(route_key))

    # ================= UI 磨砂面板构建 (保持原有样式) =================

    def _get_frosted_style(self):
        """统一磨砂质感样式"""
        return """
            QFrame {
                background: rgba(35, 35, 35, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
            }
            TransparentToolButton {
                border-radius: 4px;
            }
            TransparentToolButton:hover {
                background: rgba(255, 255, 255, 30);
            }
        """

    def create_name_label(self):
        if self.name_container:
            return
        self.name_container = QFrame(self.canvas_manager)  # Parent 设为 canvas_manager
        self.name_container.setObjectName("FrostedPanel")
        self.name_container.setStyleSheet(self._get_frosted_style())

        layout = QHBoxLayout(self.name_container)
        layout.setContentsMargins(6, 4, 10, 4)
        layout.setSpacing(5)

        self.btn_toggle_nav = self._build_tool_btn(FluentIcon.MENU, "展开/收起节点库")

        self.breadcrumb = Breadcrumb(self.name_container)
        # 初始化只加个空的，数据由 Manager 信号填充，或者手动加根节点
        # 由于 Manager init_root_graph 后会发射信号，这里可以只实例化对象
        # 为了保险起见，如果信号没触发，手动加根:
        if not self.breadcrumb.items_data:
            self.breadcrumb.addItem("0", self.parent.workflow_name)

        self.breadcrumb.currentItemChanged.connect(self._on_breadcrumb_clicked)
        setFont(self.breadcrumb, 20)

        layout.addWidget(self.btn_toggle_nav)
        layout.addWidget(self.breadcrumb)
        layout.setStretchFactor(self.breadcrumb, 1)

        self.name_container.show()

    def _create_env_and_buttons(self):
        self.envs_container = QFrame(self.canvas_manager)
        self.envs_container.setStyleSheet(self._get_frosted_style())
        # 注意: 内部布局代码完全相同
        layout = QHBoxLayout(self.envs_container)
        layout.setContentsMargins(6, 2, 3, 2)
        layout.setSpacing(2)

        label = IconWidget(get_icon("运行环境"), self.envs_container)
        label.setFixedSize(16, 16)
        self.env_combo = ComboBox(self.envs_container)
        self.env_combo.setMaxVisibleItems(15)
        self.env_combo.setFixedWidth(130)
        self.env_combo.setFixedHeight(28)
        layout.addWidget(label)
        layout.addSpacing(3)
        layout.addWidget(self.env_combo)
        layout.addSpacing(3)
        self.reboot_btn = self._build_tool_btn(get_icon("远程重启"), "环境重启")
        layout.addWidget(self.reboot_btn)

        self.buttons_container = QFrame(self.canvas_manager)
        self.buttons_container.setStyleSheet(self._get_frosted_style())
        # 注意: 内部布局代码完全相同
        layout = QHBoxLayout(self.buttons_container)
        layout.setContentsMargins(6, 2, 3, 2)
        layout.setSpacing(2)
        self.run_btn = self._build_tool_btn(get_icon("绿色运行"), "运行")
        self.pause_btn = self._build_tool_btn(get_icon("暂停"), "暂停")
        self.stop_btn = self._build_tool_btn(get_icon("结束"), "停止")
        self.save_btn = self._build_tool_btn(FluentIcon.SAVE, "保存")
        self.export_model_btn = self._build_tool_btn(FluentIcon.SHARE, "导出")
        self.close_btn = self._build_tool_btn(FluentIcon.CLOSE, "关闭")

        for btn in [
            self.run_btn,
            self.pause_btn,
            self.stop_btn,
            self.save_btn,
            self.export_model_btn,
            self.close_btn,
        ]:
            layout.addWidget(btn)

        self.pause_btn.hide()
        self.stop_btn.hide()
        self.envs_container.show()
        self.buttons_container.show()

    def reset_env_buttons_state(self):
        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()

    def _create_floating_nodes_base(self):
        self.nodes_container = QFrame(self.canvas_manager)
        self.nodes_container.setStyleSheet(self._get_frosted_style())
        self.node_layout = QVBoxLayout(self.nodes_container)
        self.node_layout.setContentsMargins(4, 8, 4, 8)
        self.node_layout.setSpacing(3)

        self.iterate_node = self._build_tool_btn(get_icon("更新"), "创建迭代")
        self.loop_node = self._build_tool_btn(get_icon("无限"), "创建循环")
        self.branch_node = self._build_tool_btn(get_icon("条件分支"), "创建分支")
        self.trigger_node = self._build_tool_btn(get_icon("触发器"), "创建触发器")
        self.echart_node = self._build_tool_btn(get_icon("多媒体"), "媒体展示")
        self.code_node = self._build_tool_btn(get_icon("代码执行"), "代码节点")
        self.ai_node = self._build_tool_btn(get_icon("大模型"), "AI生成节点")
        self.note_node = self._build_tool_btn(get_icon("文本注释"), "注释节点")

        for btn in [
            self.iterate_node,
            self.loop_node,
            self.branch_node,
            self.echart_node,
            self.code_node,
            self.ai_node,
            self.trigger_node,
            self.note_node,
        ]:
            self.node_layout.addWidget(btn)

        self.node_layout.addWidget(CardSeparator(self.nodes_container))

        self.visible_quick_container = QWidget(self.nodes_container)
        self.visible_quick_layout = QVBoxLayout(self.visible_quick_container)
        self.visible_quick_layout.setSpacing(3)
        self.visible_quick_layout.setContentsMargins(0, 0, 0, 0)
        self.node_layout.addWidget(self.visible_quick_container)

        self.more_quick_button = self._build_tool_btn(FluentIcon.MORE, "更多快捷组件")
        self.more_quick_menu = RoundMenu(parent=self.canvas_manager)
        self.add_quick_btn = self._build_tool_btn(FluentIcon.ADD, "添加快捷组件")

        self.node_layout.addWidget(self.more_quick_button)
        self.node_layout.addWidget(self.add_quick_btn)
        self.nodes_container.show()

    def _create_canvas_controls_base(self):
        self.canvas_controls_container = QFrame(self.canvas_manager)
        self.canvas_controls_container.setStyleSheet(self._get_frosted_style())

        layout = QHBoxLayout(self.canvas_controls_container)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # 原有按钮
        self.btn_mode_toggle = self._build_tool_btn(get_icon("框选"), "框选/拖拽切换")
        self.btn_mode_toggle.setCheckable(True)
        self.btn_mode_toggle.setChecked(True)
        self.btn_zoom_fit = self._build_tool_btn(get_icon("适应屏幕"), "缩放至适应")
        self.btn_zen_mode = self._build_tool_btn(get_icon("三图居中"), "切换纯净模式")
        self.btn_canvas_setting = self._build_tool_btn(FluentIcon.SETTING, "画布设置")

        # --- 新增：视角控制按钮 ---
        # 使用 ADD 和 REMOVE 图标，或者你可以换成 Layout 相关的图标
        self.more_canvas_settings_button = self._build_tool_btn(
            FluentIcon.MORE, "更多画布控制功能"
        )
        self.more_canvas_settings_menu = RoundMenu(parent=self.canvas_manager)
        # ------------------------

        self.view = CanvasSettingPopup(self.parent, self.parent.config)
        self.view.hide()

        # --- 修改：添加到布局的顺序 ---
        # 建议顺序：模式 -> 适应 -> [减少视角] -> [增加视角] -> 纯净 -> 设置
        widgets = [
            self.btn_mode_toggle,
            self.btn_zoom_fit,
            self.btn_zen_mode,
            self.more_canvas_settings_button,
            self.btn_canvas_setting,
        ]

        for btn in widgets:
            layout.addWidget(btn)

        self.canvas_controls_container.show()

    def _build_tool_btn(self, icon, tooltip):
        btn = TransparentToolButton(icon, parent=self.canvas_manager)
        btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(28, 28)
        btn.setToolTip(tooltip)
        return btn

    def _show_quick_button_menu(self, button, full_path, pos):
        menu = RoundMenu()
        menu.addAction(
            Action(
                "从快捷栏移除",
                triggered=lambda: self.parent.quick_manager.remove_component(full_path),
                parent=self.parent.canvas_widget,
            )
        )
        menu.exec_(button.mapToGlobal(pos))

    # ================= 属性代理代理 =================
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

    @property
    def execution_record(self):
        return self.side_dock_area.get_tool_instance("任务记录")

    # ================= 动态定位控制 (优化版) =================

    def update_position(self, recalculate_size=False):
        """
        [同步执行] 必须在 resizeEvent 中同步调用，避免右侧/底部控件抖动。
        :param recalculate_size: resizeEvent 中设为 False; 添加按钮/切图时设为 True
        """
        if not self.canvas_manager or not self.canvas_manager.isVisible():
            return

        w, h = self.canvas_manager.width(), self.canvas_manager.height()
        padding = 5

        # 1. 左上角 (名称)
        if self.name_container:
            if recalculate_size:
                self.name_container.adjustSize()
            self.name_container.move(padding, padding)

        # 2. 右上角 (环境 & 按钮) -> 必须实时计算 X
        if self.buttons_container:
            if recalculate_size:
                self.buttons_container.adjustSize()
            self.buttons_container.move(
                w - self.buttons_container.width() - padding, padding
            )
        # 环境紧靠 按钮左边
        if self.envs_container:
            if recalculate_size:
                self.envs_container.adjustSize()
            self.envs_container.move(
                self.buttons_container.x() - self.envs_container.width() - padding,
                self.buttons_container.y(),
            )

        # 3. 左侧 (节点栏) -> 垂直居中
        if self.nodes_container:
            if recalculate_size:
                self.nodes_container.adjustSize()
            self.nodes_container.move(padding, (h - self.nodes_container.height()) // 2)

        # 4. 右下角 (画布控制) -> 必须实时计算 X, Y
        if self.canvas_controls_container:
            if recalculate_size:
                self.canvas_controls_container.adjustSize()
            self.canvas_controls_container.move(
                w - self.canvas_controls_container.width() - padding,
                h - self.canvas_controls_container.height() - padding,
            )

    def _toggle_nav_panel(self):
        visible = self.nav_panel.isVisible()
        self.nav_panel.setVisible(not visible)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.btn_toggle_nav.setIcon(FluentIcon.MENU if visible else get_icon("左收起"))

    def show_splitter(self):
        self.side_dock_area.show()
        sizes = self.splitter.sizes()
        sizes[2] = self.last_right_width if self.last_right_width > 50 else 300
        self.splitter.setSizes(sizes)

    def hide_splitter(self):
        sizes = self.splitter.sizes()
        if sizes[2] > 0:
            self.last_right_width = sizes[2]
        sizes[2] = 0
        self.splitter.setSizes(sizes)
        self.side_dock_area.hide()

    def _toggle_viewer_mode(self):
        viewer = self.graph.viewer()
        if self.btn_mode_toggle.isChecked():
            viewer.set_navigation_mode(False)
            self.btn_mode_toggle.setIcon(get_icon("框选"))
        else:
            viewer.set_navigation_mode(True)
            self.btn_mode_toggle.setIcon(FluentIcon.MOVE)

    def _on_view_split_right(self):
        """点击增加视角"""
        new_viewer = self.canvas_manager.graph_splitter.split_right()
        new_viewer.graph = self.graph
        self.graph._wire_signals(new_viewer)
        new_viewer.zoom_to_nodes(
            [n.view for n in self.graph.selected_nodes() or self.graph.all_nodes()]
        )
        self.parent.node_operations.setup_graph_menu(new_viewer)

    def _on_view_split_down(self):
        """点击增加视角"""
        new_viewer = self.canvas_manager.graph_splitter.split_down()
        new_viewer.graph = self.graph
        self.graph._wire_signals(new_viewer)
        new_viewer.zoom_to_nodes(
            [n.view for n in self.graph.selected_nodes() or self.graph.all_nodes()]
        )
        self.parent.node_operations.setup_graph_menu(new_viewer)

    def toggle_zen_mode(self):
        if not self.is_zen_mode:
            self.saved_splitter_sizes = self.splitter.sizes()
            total_width = sum(self.saved_splitter_sizes)
            self.splitter.setSizes([0, total_width, 0])

            self.btn_zen_mode.setIcon(get_icon("画布2"))
            self.is_zen_mode = True
        else:
            self.splitter.setSizes(self.saved_splitter_sizes)
            self.btn_zen_mode.setIcon(get_icon("三图居中"))
            self.is_zen_mode = False

    def _show_canvas_settings(self):
        self.view.show_at_button(self.btn_canvas_setting)

    def _refresh_quick_buttons(self):
        if not hasattr(self.parent, "quick_manager") or not self.parent.quick_manager:
            return
        all_quick_components = self.parent.quick_manager.get_quick_components()
        while self.visible_quick_layout.count():
            child = self.visible_quick_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.more_quick_menu.clear()
        self._hidden_quick_components = []
        for i, qc in enumerate(all_quick_components):
            fp, idat = qc["full_path"], qc.get("icon_path")
            if i >= MAX_VISIBLE_QUICK_BUTTONS:
                self._hidden_quick_components.append((fp, idat))
                self.more_quick_button.show()
                continue
            btn = self._build_tool_btn(
                self._get_qc_icon(idat), f"创建 {os.path.basename(fp)}"
            )
            btn.clicked.connect(
                lambda _, f=fp, d=idat: self.parent.create_next_node(f, d)
            )
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn, fp=fp: self._show_quick_button_menu(b, fp, pos)
            )
            self.visible_quick_layout.addWidget(btn)
        if not self._hidden_quick_components:
            self.more_quick_button.hide()
        QTimer.singleShot(0, lambda: self.update_position(True))

    def _get_qc_icon(self, icon_path):
        if not icon_path:
            return FluentIcon.APPLICATION
        if icon_path.startswith("builtin:\\"):
            return FluentIcon[icon_path.split("\\")[-1]]
        return QtGui.QIcon(icon_path)

    def _show_more_quick_menu(self):
        self.more_quick_menu.clear()
        for fp, ip in self._hidden_quick_components:
            action = Action(
                self._get_qc_icon(ip),
                os.path.basename(fp).replace(".py", ""),
                parent=self.canvas_manager,
            )
            action.triggered.connect(
                lambda _, p=fp, i=ip: self.parent.create_next_node(p, i)
            )
            self.more_quick_menu.addAction(action)
        self.more_quick_menu.exec_(
            self.more_quick_button.mapToGlobal(
                QPoint(0, self.more_quick_button.height())
            )
        )

    def _show_canvas_more_menu(self):
        # 获取按钮左上角的全局坐标
        btn_pos = self.more_canvas_settings_button.mapToGlobal(QPoint(0, 0))

        # 获取菜单的推荐尺寸
        menu_height = self.more_canvas_settings_menu.sizeHint().height()
        menu_width = self.more_canvas_settings_menu.sizeHint().width()
        # 计算 X 和 Y
        # X 保持对齐，Y 向上偏移（按钮上方再留一点间距，比如 5 像素）
        x = btn_pos.x() - menu_width // 2
        y = btn_pos.y() - menu_height - 30

        # 3. 弹出
        self.more_canvas_settings_menu.exec_(QPoint(x, y))

    def _setup_pipeline_style(self):
        # 仅用于初始化，后续由 Manager 接管
        config = Settings.get_instance()
        if self.graph:
            self.graph.set_grid_mode(GRID_STYLE.get(config.canvas_grid_mode.value))
            self.graph.set_pipe_style(
                PIPELINE_STYLE.get(config.canvas_pipelayout.value)
            )
            self.graph.set_layout_direction(
                PIPELINE_DIRECTION.get(config.canvas_direction.value)
            )

    def _init_unified_font(self):
        font_name = getattr(
            self.parent.config.canvas_font_type, "value", "Microsoft YaHei"
        )
        self.parent.setStyleSheet(f'QWidget {{ font-family: "{font_name}"; }}')

    def destroy_all(self):
        try:
            for attr in [
                "splitter",
                "envs_container",
                "buttons_container",
                "nodes_container",
                "name_container",
                "canvas_controls_container",
                "side_dock_area",
            ]:
                obj = getattr(self, attr, None)
                if obj:
                    obj.setParent(None)
                    obj.deleteLater()
            self.parent = None
        except:
            pass
