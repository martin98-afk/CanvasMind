# -- coding: utf-8 --
import os

from PyQt5.QtCore import Qt, QSize, QPoint, QTimer
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFrame
from qfluentwidgets import (TransparentToolButton, FluentIcon, RoundMenu, Action,
                            ComboBox, BreadcrumbBar, setFont, BodyLabel, IconWidget)
from qfluentwidgets.components.widgets.card_widget import CardSeparator
from qtpy import QtGui

from app.utils.utils import get_icon
from app.widgets.basic_widget.bread_crumb import Breadcrumb
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.side_dock_area import SideDockArea
from .canvas_left_panel import LeftPanel
from .canvas_setting_popup import CanvasSettingPopup
from ..constants import (DEFAULT_SPLITTER_SIZES,
                         PIPELINE_STYLE, PIPELINE_DIRECTION, MAX_VISIBLE_QUICK_BUTTONS, GRID_STYLE)


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

        self.name_container = None
        self.buttons_container = None
        self.env_container = None  # 环境选择容器
        self.canvas_controls_container = None

        self.btn_mode_toggle = None
        self.btn_zoom_fit = None
        self.btn_canvas_setting = None
        self.btn_zen_mode = None
        self.view = None

        # 扩展引用
        self.btn_toggle_nav = None
        self.breadcrumb = None

    def setup_ui(self):
        """第一阶段：构建纯 UI 框架"""
        main_layout = QHBoxLayout(self.parent)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. 核心布局组件
        self.nav_panel = LeftPanel(self.parent)
        self.nav_view = self.nav_panel.draggable_tree.tree
        self.side_dock_area = SideDockArea(self.parent, "运行画布")

        self.splitter = ModernSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.nav_panel)
        self.splitter.addWidget(self.parent.graph.widget)
        self.splitter.addWidget(self.side_dock_area)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.last_right_width = DEFAULT_SPLITTER_SIZES[2]

        self.splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.splitter)
        main_layout.addWidget(self.side_dock_area.tool_panel)
        self.nav_panel.setVisible(False)
        # 2. 初始化悬浮磨砂面板 (必须先实例化对象，connect_signals 才能绑定)
        self.create_name_label()
        self._create_env_and_buttons()  # 右上：环境+运行控制
        self._create_floating_nodes_base()  # 左侧：快捷工具
        self._create_canvas_controls_base()  # 右下：画布控制

        self._setup_pipeline_style()
        self._init_unified_font()

    def connect_signals(self):
        """第二阶段：绑定业务逻辑信号"""
        # --- 顶部导航开关 ---
        if self.btn_toggle_nav:
            self.btn_toggle_nav.clicked.connect(self._toggle_nav_panel)

        # --- 基础控制信号 ---
        self.close_btn.clicked.connect(lambda: (
            QTimer.singleShot(0, self.parent.close_current_canvas),
            self.parent.switch_to_parent()
        ))

        # --- 左侧功能按钮 ---
        self.iterate_node.clicked.connect(
            lambda: self.parent.create_backdrop_node("control_flow.ControlFlowIterateNode"))
        self.loop_node.clicked.connect(lambda: self.parent.create_backdrop_node("control_flow.ControlFlowLoopNode"))
        self.branch_node.clicked.connect(lambda: self.parent.create_next_node("control_flow.ControlFlowBranchNode"))
        self.echart_node.clicked.connect(lambda: self.parent.create_next_node("visualize.MediaNode"))
        self.code_node.clicked.connect(lambda: self.parent.create_next_node("dynamic.DYNAMIC_CODE"))
        self.note_node.clicked.connect(lambda: self.parent.create_backdrop_node("general.StickyNote", init_io=False))
        self.group_node.clicked.connect(lambda: self.parent.create_group_node())

        if hasattr(self.parent, 'quick_manager'):
            self.add_quick_btn.clicked.connect(self.parent.quick_manager.open_add_dialog)
            self.more_quick_button.clicked.connect(self._show_more_quick_menu)
            self._refresh_quick_buttons()

        self.btn_mode_toggle.clicked.connect(self._toggle_viewer_mode)
        self.btn_zoom_fit.clicked.connect(
            lambda: self.parent.canvas_widget.zoom_to_nodes([n.view for n in self.parent.graph.all_nodes()])
        )
        self.btn_zen_mode.clicked.connect(self.toggle_zen_mode)
        self.btn_canvas_setting.clicked.connect(self._show_canvas_settings)

        # 强制刷新位置
        QTimer.singleShot(100, self.update_position)

    # ================= UI 磨砂面板构建 =================

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
        """左上角面板：核心修复 BreadcrumbBar 的显示"""
        if self.name_container: return
        self.name_container = QFrame(self.parent.canvas_widget)
        self.name_container.setObjectName("FrostedPanel")
        self.name_container.setStyleSheet(self._get_frosted_style())

        layout = QHBoxLayout(self.name_container)
        layout.setContentsMargins(6, 4, 10, 4)
        layout.setSpacing(10)

        self.btn_toggle_nav = self._build_tool_btn(FluentIcon.MENU, "展开/收起节点库")

        self.breadcrumb = Breadcrumb(self.name_container)
        self.breadcrumb.addItem("workflow", self.parent.workflow_name)

        setFont(self.breadcrumb, 16)

        layout.addWidget(self.btn_toggle_nav)
        layout.addWidget(self.breadcrumb)
        layout.setStretchFactor(self.breadcrumb, 1)  # 核心修复2：设置拉伸系数

        self.name_container.show()

    def _create_env_and_buttons(self):
        """右上角面板：[环境 ComboBox] | [运行按钮组]"""
        self.buttons_container = QFrame(self.parent.canvas_widget)
        self.buttons_container.setStyleSheet(self._get_frosted_style())

        layout = QHBoxLayout(self.buttons_container)
        layout.setContentsMargins(6, 2, 3, 2)
        layout.setSpacing(2)

        # 环境选择
        label = IconWidget(get_icon("运行环境"), self.buttons_container)
        label.setFixedSize(16, 16)
        self.env_combo = ComboBox(self.buttons_container)
        self.env_combo.setFixedWidth(130)
        self.env_combo.setFixedHeight(28)
        layout.addWidget(label)
        layout.addSpacing(3)
        layout.addWidget(self.env_combo)
        layout.addSpacing(23)

        # 控制按钮
        self.run_btn = self._build_tool_btn(FluentIcon.PLAY, "运行")
        self.pause_btn = self._build_tool_btn(FluentIcon.PAUSE, "暂停")
        self.stop_btn = self._build_tool_btn(get_icon("停止"), "停止")
        self.save_btn = self._build_tool_btn(FluentIcon.SAVE, "保存")
        self.export_model_btn = self._build_tool_btn(FluentIcon.SHARE, "导出")
        self.close_btn = self._build_tool_btn(FluentIcon.CLOSE, "关闭")

        for btn in [self.run_btn, self.pause_btn, self.stop_btn, self.save_btn, self.export_model_btn, self.close_btn]:
            layout.addWidget(btn)

        self.pause_btn.hide()
        self.stop_btn.hide()
        self.buttons_container.show()

    def _create_floating_nodes_base(self):
        """左侧面板：垂直节点按钮"""
        self.nodes_container = QFrame(self.parent.canvas_widget)
        self.nodes_container.setStyleSheet(self._get_frosted_style())

        self.node_layout = QVBoxLayout(self.nodes_container)
        self.node_layout.setContentsMargins(4, 8, 4, 8)
        self.node_layout.setSpacing(6)

        self.iterate_node = self._build_tool_btn(get_icon("更新"), "创建迭代")
        self.loop_node = self._build_tool_btn(get_icon("无限"), "创建循环")
        self.branch_node = self._build_tool_btn(get_icon("条件分支"), "创建分支")
        self.group_node = self._build_tool_btn(get_icon("组节点"), "创建组节点")
        self.echart_node = self._build_tool_btn(get_icon("多媒体"), "媒体展示")
        self.code_node = self._build_tool_btn(get_icon("代码执行"), "代码节点")
        self.note_node = self._build_tool_btn(get_icon("文本注释"), "注释节点")

        for btn in [self.iterate_node, self.loop_node, self.branch_node, self.echart_node,
                    self.code_node, self.group_node, self.note_node]:
            self.node_layout.addWidget(btn)

        self.node_layout.addWidget(CardSeparator(self.nodes_container))

        self.visible_quick_container = QWidget(self.nodes_container)
        self.visible_quick_layout = QVBoxLayout(self.visible_quick_container)
        self.visible_quick_layout.setSpacing(6)
        self.visible_quick_layout.setContentsMargins(0, 0, 0, 0)
        self.node_layout.addWidget(self.visible_quick_container)

        self.more_quick_button = self._build_tool_btn(FluentIcon.MORE, "更多快捷组件")
        self.more_quick_menu = RoundMenu(parent=self.parent.canvas_widget)
        self.add_quick_btn = self._build_tool_btn(FluentIcon.ADD, "添加快捷组件")

        self.node_layout.addWidget(self.more_quick_button)
        self.node_layout.addWidget(self.add_quick_btn)
        self.nodes_container.show()

    def _create_canvas_controls_base(self):
        """右下面板：视图控制"""
        self.canvas_controls_container = QFrame(self.parent.canvas_widget)
        self.canvas_controls_container.setStyleSheet(self._get_frosted_style())

        layout = QHBoxLayout(self.canvas_controls_container)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.btn_mode_toggle = self._build_tool_btn(get_icon("框选"), "框选/拖拽切换")
        self.btn_mode_toggle.setCheckable(True)
        self.btn_mode_toggle.setChecked(True)
        self.btn_zoom_fit = self._build_tool_btn(get_icon("适应屏幕"), "缩放至适应")
        self.btn_zen_mode = self._build_tool_btn(get_icon("三图居中"), "切换纯净模式")
        self.btn_canvas_setting = self._build_tool_btn(FluentIcon.SETTING, "画布设置")

        self.view = CanvasSettingPopup(self.parent, self.parent.config)
        self.view.hide()
        for btn in [self.btn_mode_toggle, self.btn_zoom_fit, self.btn_zen_mode, self.btn_canvas_setting]:
            layout.addWidget(btn)
        self.canvas_controls_container.show()

    def _build_tool_btn(self, icon, tooltip):
        btn = TransparentToolButton(icon, parent=self.parent.canvas_widget)
        btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(28, 28)
        btn.setToolTip(tooltip)
        return btn

    # ================= 属性代理代理 (保持引用完整) =================
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

    # ================= 动态定位控制 =================

    def update_position(self):
        if not self.parent.canvas_widget or not self.parent.canvas_widget.isVisible(): return
        w, h = self.parent.canvas_widget.width(), self.parent.canvas_widget.height()
        padding = 5

        if self.name_container:
            self.name_container.adjustSize()
            self.name_container.move(padding, padding)

        if self.buttons_container:
            self.buttons_container.adjustSize()
            self.buttons_container.move(w - self.buttons_container.width() - padding, padding)

        if self.nodes_container:
            self.nodes_container.adjustSize()
            self.nodes_container.move(padding, (h - self.nodes_container.height()) // 2)

        if self.canvas_controls_container:
            self.canvas_controls_container.adjustSize()
            self.canvas_controls_container.move(w - self.canvas_controls_container.width() - padding,
                                                h - self.canvas_controls_container.height() - padding)

    def _toggle_nav_panel(self):
        visible = self.nav_panel.isVisible()
        self.nav_panel.setVisible(not visible)
        self.btn_toggle_nav.setIcon(FluentIcon.MENU if visible else get_icon("左收起"))

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
        viewer = self.parent.graph.viewer()
        if self.btn_mode_toggle.isChecked():
            viewer.set_navigation_mode(False);
            self.btn_mode_toggle.setIcon(get_icon("框选"))
        else:
            viewer.set_navigation_mode(True);
            self.btn_mode_toggle.setIcon(FluentIcon.MOVE)

    def toggle_zen_mode(self):
        if not self.is_zen_mode:
            self.saved_splitter_sizes = self.splitter.sizes()
            total_width = sum(self.saved_splitter_sizes)
            self.splitter.setSizes([0, total_width, 0])
            self.btn_zen_mode.setIcon(get_icon("画布2"));
            self.is_zen_mode = True
        else:
            self.splitter.setSizes(self.saved_splitter_sizes)
            self.btn_zen_mode.setIcon(get_icon("三图居中"));
            self.is_zen_mode = False

    def _show_canvas_settings(self):
        self.view.show_at_button(self.btn_canvas_setting)

    def _refresh_quick_buttons(self):
        if not hasattr(self.parent, 'quick_manager') or not self.parent.quick_manager: return
        all_quick_components = self.parent.quick_manager.get_quick_components()
        while self.visible_quick_layout.count():
            child = self.visible_quick_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        self.more_quick_menu.clear()
        self._hidden_quick_components = []
        for i, qc in enumerate(all_quick_components):
            fp, idat = qc["full_path"], qc.get("icon_path")
            if i >= MAX_VISIBLE_QUICK_BUTTONS:
                self._hidden_quick_components.append((fp, idat));
                self.more_quick_button.show();
                continue
            btn = self._build_tool_btn(self._get_qc_icon(idat), f"创建 {os.path.basename(fp)}")
            btn.clicked.connect(lambda _, f=fp, d=idat: self.parent.create_next_node(f, d))
            self.visible_quick_layout.addWidget(btn)
        if not self._hidden_quick_components: self.more_quick_button.hide()
        QTimer.singleShot(0, self.update_position)

    def _get_qc_icon(self, icon_path):
        if not icon_path: return FluentIcon.APPLICATION
        if icon_path.startswith("builtin:\\"): return FluentIcon[icon_path.split("\\")[-1]]
        return QtGui.QIcon(icon_path)

    def _show_more_quick_menu(self):
        self.more_quick_menu.clear()
        for fp, ip in self._hidden_quick_components:
            action = Action(self._get_qc_icon(ip), os.path.basename(fp).replace('.py', ''),
                            parent=self.parent.canvas_widget)
            action.triggered.connect(lambda _, p=fp, i=ip: self.parent.create_next_node(p, i))
            self.more_quick_menu.addAction(action)
        self.more_quick_menu.exec_(self.more_quick_button.mapToGlobal(QPoint(0, self.more_quick_button.height())))

    def _setup_pipeline_style(self):
        config = self.parent.config
        self.parent.graph.set_grid_mode(GRID_STYLE.get(config.canvas_grid_mode.value))
        self.parent.graph.set_pipe_style(PIPELINE_STYLE.get(config.canvas_pipelayout.value))
        self.parent.graph.set_layout_direction(PIPELINE_DIRECTION.get(config.canvas_direction.value))

    def _init_unified_font(self):
        font_name = getattr(self.parent.config.canvas_font_type, 'value', "Microsoft YaHei")
        self.parent.setStyleSheet(f'QWidget {{ font-family: "{font_name}"; }}')

    def destroy_all(self):
        try:
            for attr in ['splitter', 'buttons_container', 'nodes_container', 'name_container',
                         'canvas_controls_container']:
                obj = getattr(self, attr, None)
                if obj: obj.setParent(None); obj.deleteLater()
            self.parent = None
        except:
            pass