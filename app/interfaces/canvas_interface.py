# -*- coding: utf-8 -*-
import json
import os
import pathlib
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from NodeGraphQt import BackdropNode, BaseNode
from NodeGraphQt.constants import PipeLayoutEnum
from NodeGraphQt.widgets.viewer import NodeViewer
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QRectF, pyqtSignal, QSize, QTimer, QPoint
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFileDialog, QProgressDialog, QApplication
from loguru import logger
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition, FluentIcon, ComboBox, LineEdit, RoundMenu, Action, TransparentToolButton, FlyoutViewBase,
    PushButton, Flyout, VBoxLayout
)
from app.components.base import PropertyType, GlobalVariableContext
from app.nodes.backdrop_node import ControlFlowIterateNode, ControlFlowLoopNode, ControlFlowBackdrop
from app.nodes.branch_node import create_branch_node
from app.widgets.custom_nodegraph import CustomNodeGraph
from app.nodes.dynamic_code_node import create_dynamic_code_node
from app.nodes.execute_node import create_node_class
from app.nodes.port_node import CustomPortOutputNode, CustomPortInputNode
from app.nodes.status_node import NodeStatus, StatusNode
from app.scan_components import scan_components
from app.scheduler.workflow_scheduler import WorkflowScheduler  # ← 新增导入
from app.utils.config import Settings
from app.utils.quick_component_manager import QuickComponentManager
from app.utils.threading_utils import ThumbnailGenerator
from app.utils.utils import serialize_for_json, deserialize_from_json, get_icon
from app.widgets.dialog_widget.custom_messagebox import ProjectExportDialog
from app.widgets.dialog_widget.input_selection_dialog import InputSelectionDialog
from app.widgets.dialog_widget.output_selection_dialog import OutputSelectionDialog
from app.widgets.minimap_widget import MinimapWidget
from app.widgets.property_panel import PropertyPanel
from app.widgets.tree_widget.draggable_component_tree import DraggableTreePanel


class CanvasPage(QWidget):
    canvas_deleted = pyqtSignal()
    canvas_saved = pyqtSignal(Path)
    global_variables_changed = pyqtSignal(str, str, str)
    env_changed = pyqtSignal(str)

    PIPELINE_STYLE = {
        "折线": PipeLayoutEnum.ANGLE.value,
        "曲线": PipeLayoutEnum.CURVED.value,
        "直线": PipeLayoutEnum.STRAIGHT.value,
    }
    PIPELINE_DIRECTION = {
        "水平": 0,
        "垂直": 1
    }

    def __init__(self, parent=None, object_name: Path = None):
        super().__init__()
        self.parent = parent
        self.file_path = object_name
        self.workflow_name = object_name.stem.split(".")[0] if object_name else "未命名工作流"
        self.setObjectName('canvas_page' if object_name is None else str(object_name))
        self.parent = parent
        self.config = Settings.get_instance()
        # 初始化状态存储数据分析/因子分析
        self.node_status = {}  # {node_id: status}
        self.node_type_map = {}
        self._registered_nodes = []
        self._node_flyout = None
        self._clipboard_data = None
        self._scheduler = None  # ← 新增：调度器引用
        self._selection_update_pending = False
        # --- 新增：性能优化相关 ---
        self._node_id_cache = {}  # 缓存：node_id -> node_object
        self._node_id_cache_valid = False  # 标记缓存是否有效
        # ---

        # 初始化 NodeGraph
        self.graph = CustomNodeGraph()
        self.graph.node_created.connect(self.on_node_created)
        self._setup_pipeline_style()
        self.canvas_widget = self.graph.viewer()
        self.canvas_widget.keyPressEvent = self._canvas_key_press_event
        self.global_variables = GlobalVariableContext()
        # 组件面板
        self.register_components()
        self.nav_panel = DraggableTreePanel(self)
        self.nav_view = self.nav_panel.tree
        # 属性面板
        self.property_panel = PropertyPanel(self)
        # 布局
        main_layout = VBoxLayout(self)
        canvas_layout = QHBoxLayout()
        canvas_layout.addWidget(self.nav_panel)
        canvas_layout.addWidget(self.canvas_widget, 1)
        canvas_layout.addWidget(self.property_panel, 0, Qt.AlignRight)
        main_layout.addLayout(canvas_layout)
        # 信号连接
        self.graph.viewer().node_selection_changed.connect(self.on_selection_changed)
        # 快捷组件工具管理
        self.quick_manager = QuickComponentManager(
            parent_widget=self,
            component_map=self.component_map
        )
        self.quick_manager.quick_components_changed.connect(self._refresh_quick_buttons)
        # 创建悬浮按钮和环境选择
        self.create_environment_selector()
        self.create_floating_buttons()
        self.create_floating_nodes()
        # 启用画布拖拽
        self.canvas_widget.setAcceptDrops(True)
        self.canvas_widget.dragEnterEvent = self.canvas_drag_enter_event
        self.canvas_widget.dropEvent = self.canvas_drop_event
        self.canvas_widget.installEventFilter(self)
        # 右键菜单
        self._setup_context_menus()

    # ========================
    # 调度器相关（核心新增）
    # ========================
    def _create_scheduler(self):
        """创建工作流调度器"""
        scheduler = WorkflowScheduler(
            graph=self.graph,
            component_map=self.component_map,
            get_node_status=self.get_node_status,
            get_python_exe=self.get_current_python_exe,
            global_variables=self.global_variables,
            parent=self
        )
        # 优化：直接连接到 set_node_status_by_id
        scheduler.node_status_changed.connect(self.set_node_status_by_id)
        scheduler.property_changed.connect(self.update_node_property)
        scheduler.node_variable_updated.connect(self.update_node_variable)
        return scheduler

    def update_node_variable(self, name, value, policy):
        node_var_obj = self.global_variables.node_vars.get(name)
        if policy == "更新":
            node_var_obj.value = value
        elif policy == "追加":
            current_value = node_var_obj.value
            # 尝试进行追加操作
            try:
                # --- 处理字符串 ---
                if isinstance(current_value, list):
                    if isinstance(value, list):
                        node_var_obj.value = current_value + value
                        logger.debug(f"变量 '{name}' (list) 已追加列表: {value}")
                    else:
                        # 如果当前是列表，但新值不是列表，将新值作为一个元素追加
                        node_var_obj.value = current_value + [value]
                        logger.debug(f"变量 '{name}' (list) 已追加单个元素: {value}")
                # --- 处理字典 ---
                elif isinstance(current_value, dict):
                    if isinstance(value, dict):
                        # 合并字典，新值会覆盖同名键的旧值
                        node_var_obj.value = {**current_value, **value}
                        logger.debug(f"变量 '{name}' (dict) 已合并字典: {value}")
                    else:
                        logger.warning(f"无法将非字典值 {value} (type: {type(value)}) 追加到字典变量 '{name}'。")
                # --- 其他类型 ---
                else:
                    # 对于其他类型，尝试直接相加，如果失败则覆盖
                    node_var_obj.value = [current_value, value]
                    logger.debug(f"变量 '{name}' (type: {type(current_value)}) 已尝试追加: {value}")
            except TypeError as e:
                # 如果相加操作不支持（例如 list + int），则记录警告并覆盖
                logger.warning(f"追加变量 '{name}' 失败: {e}. 将覆盖旧值。")
                node_var_obj.value = value
            except Exception as e:
                # 捕获其他任何可能的异常，记录警告并覆盖
                logger.error(f"追加变量 '{name}' 时发生未知错误: {e}. 将覆盖旧值。")
                node_var_obj.value = value
        QtCore.QTimer.singleShot(0, self.property_panel._refresh_node_vars_page)

    def set_node_status_by_id(self, node_id, status):
        node = self._get_node_by_id_cached(node_id)
        if node:
            self.set_node_status(node, status)

    def update_node_property(self, node_id):
        selected_nodes = self.graph.selected_nodes()
        backdrop = None
        for node in selected_nodes:
            if isinstance(node, ControlFlowBackdrop):
                backdrop = node
                break
        node = self._get_node_by_id_cached(node_id)
        if selected_nodes and node == backdrop:
            QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(node))

    def _connect_scheduler_signals(self):
        """连接调度器信号到 UI 回调"""
        # 优化：直接连接到具体处理方法，避免不必要的中间信号
        self._scheduler.node_started.connect(self.on_node_started_simple)
        self._scheduler.node_finished.connect(self.on_node_finished_simple)
        self._scheduler.node_error.connect(self.on_node_error_simple)
        self._scheduler.finished.connect(self._on_workflow_finished)
        self._scheduler.error.connect(self._on_workflow_error)
        self.run_btn.hide()
        self.stop_btn.show()

    def run_workflow(self):
        """执行整个工作流"""
        self._scheduler = self._create_scheduler()
        self._connect_scheduler_signals()
        self._scheduler.run_full()

    def run_to_node(self, target_node):
        """执行到目标节点"""
        self._scheduler = self._create_scheduler()
        self._connect_scheduler_signals()
        self._scheduler.run_to(target_node)

    def run_node(self, node):
        """从起始节点开始执行"""
        self._scheduler = self._create_scheduler()
        self._connect_scheduler_signals()
        self._scheduler.run(node)

    def run_from_node(self, start_node):
        """从起始节点开始执行"""
        self._scheduler = self._create_scheduler()
        self._connect_scheduler_signals()
        self._scheduler.run_from(start_node)

    def stop_workflow(self):
        """停止当前执行"""
        if self._scheduler:
            self._scheduler.cancel()
            self.create_info("已停止", "正在终止任务...")
            self.run_btn.show()
            self.stop_btn.hide()
            self._scheduler = None

    def _canvas_key_press_event(self, event):
        super(NodeViewer, self.canvas_widget).keyPressEvent(event)
        self.canvas_widget.ALT_state = event.modifiers() == QtCore.Qt.AltModifier
        self.canvas_widget.CTRL_state = event.modifiers() == QtCore.Qt.ControlModifier
        self.canvas_widget.SHIFT_state = event.modifiers() == QtCore.Qt.ShiftModifier
        if event.modifiers() == QtCore.Qt.ControlModifier:
            if event.key() == QtCore.Qt.Key_C:
                self._copy_selected_nodes()
            elif event.key() == QtCore.Qt.Key_V:
                self._paste_nodes()
        if event.modifiers() == (QtCore.Qt.AltModifier | QtCore.Qt.ShiftModifier):
            self.canvas_widget.ALT_state = True
            self.canvas_widget.SHIFT_state = True
        if self.canvas_widget._LIVE_PIPE.isVisible():
            super(NodeViewer, self.canvas_widget).keyPressEvent(event)
            return
        # show cursor text
        overlay_text = None
        self.canvas_widget._cursor_text.setVisible(False)
        if not self.canvas_widget.ALT_state:
            if self.canvas_widget.SHIFT_state:
                overlay_text = '\n    SHIFT:\n    Toggle/Extend Selection'
            elif self.canvas_widget.CTRL_state:
                overlay_text = '\n    CTRL:\n    Deselect Nodes'
        elif self.canvas_widget.ALT_state and self.canvas_widget.SHIFT_state:
            if self.canvas_widget.pipe_slicing:
                overlay_text = '\n    ALT + SHIFT:\n    连线删除模式'
        if overlay_text:
            self.canvas_widget._cursor_text.setPlainText(overlay_text)
            self.canvas_widget._cursor_text.setFont(QtGui.QFont('Arial', 10))
            self.canvas_widget._cursor_text.setDefaultTextColor(Qt.white)
            self.canvas_widget._cursor_text.setPos(self.canvas_widget.mapToScene(self.canvas_widget._previous_pos))
            self.canvas_widget._cursor_text.setVisible(True)

    def eventFilter(self, obj, event):
        if obj is self.graph.viewer() and event.type() == event.Resize:
            self._update_nodes_container_position()
            self.buttons_container.move(self.graph.viewer().width() - 170, 10)
            self._position_name_container()
        return super().eventFilter(obj, event)

    def create_floating_buttons(self):
        self.buttons_container = QWidget(self.graph.viewer())
        self.buttons_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.buttons_container.move(self.graph.viewer().width() - 170, 10)
        env_layout = QHBoxLayout(self.buttons_container)
        env_layout.setSpacing(5)
        env_layout.setContentsMargins(0, 0, 0, 0)
        self.run_btn = TransparentToolButton(FluentIcon.PLAY, self)
        self.run_btn.setToolTip("运行工作流")
        self.run_btn.clicked.connect(self.run_workflow)
        env_layout.addWidget(self.run_btn)
        self.stop_btn = TransparentToolButton(FluentIcon.PAUSE, self)
        self.stop_btn.setToolTip("停止运行")
        self.stop_btn.clicked.connect(self.stop_workflow)
        self.stop_btn.hide()
        env_layout.addWidget(self.stop_btn)
        self.export_btn = TransparentToolButton(FluentIcon.SAVE, self)
        self.export_btn.setToolTip("导出工作流")
        self.export_btn.clicked.connect(self._save_via_dialog)
        env_layout.addWidget(self.export_btn)
        self.export_model_btn = TransparentToolButton(FluentIcon.SHARE, self)
        self.export_model_btn.setToolTip("导出选中节点为独立模型")
        self.export_model_btn.clicked.connect(self.export_selected_nodes_as_project)
        env_layout.addWidget(self.export_model_btn)
        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.close_btn.setToolTip("关闭当前画布")
        self.close_btn.clicked.connect(self.close_current_canvas)
        env_layout.addWidget(self.close_btn)
        env_layout.addStretch()
        self.buttons_container.setLayout(env_layout)
        self.buttons_container.show()

    def create_environment_selector(self):
        self.env_selector_container = QWidget(self.graph.viewer())
        self.env_selector_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.env_selector_container.move(0, 10)
        env_layout = QHBoxLayout(self.env_selector_container)
        env_layout.setSpacing(5)
        env_layout.setContentsMargins(0, 0, 0, 0)
        env_label = TransparentToolButton(self)
        env_label.setText("环境:")
        env_label.setFixedSize(50, 30)
        self.env_combo = ComboBox(self.env_selector_container)
        self.env_combo.setFixedWidth(140)
        self.load_env_combos()
        self.env_combo.currentIndexChanged.connect(self.on_environment_changed)
        if hasattr(self.parent, 'package_manager'):
            self.parent.package_manager.env_changed.connect(self.load_env_combos)
        env_layout.addWidget(env_label)
        env_layout.addWidget(self.env_combo)
        env_layout.addStretch()
        self.env_selector_container.setLayout(env_layout)
        self.env_selector_container.show()

    def load_env_combos(self):
        self.env_combo.clear()
        if hasattr(self.parent, 'package_manager') and self.parent.package_manager:
            envs = self.parent.package_manager.mgr.list_envs()
            for env in envs:
                self.env_combo.addItem(env, userData=env)

    def on_environment_changed(self):
        current_text = self.env_combo.currentText()
        self.env_changed.emit(
            str(self.parent.package_manager.mgr.get_python_exe(self.env_combo.currentData()))
        )
        self.create_info("环境切换", f"当前运行环境: {current_text}")

    def get_current_python_exe(self):
        current_data = self.env_combo.currentData()
        if hasattr(self.parent, 'package_manager') and self.parent.package_manager and current_data:
            try:
                return str(self.parent.package_manager.mgr.get_python_exe(current_data))
            except Exception as e:
                self.create_failed_info("错误", f"获取环境 {current_data} 的Python路径失败: {str(e)}")
                return None
        return None

    def register_components(self):
        self._registered_nodes.extend(list(self.graph.registered_nodes()))
        self.graph._node_factory.clear_registered_nodes()
        self.component_map, self.file_map = scan_components()
        # 普通节点
        nodes_menu = self.graph.get_context_menu('nodes')
        for full_path, comp_cls in self.component_map.items():
            safe_name = full_path.replace("/", "_").replace(" ", "_").replace("-", "_")
            node_class = create_node_class(comp_cls, full_path, self.file_map.get(full_path), self)
            node_class = type(f"Status{node_class.__name__}", (StatusNode, node_class), {})
            node_class.__name__ = f"StatusDynamicNode_{safe_name}"
            self.graph.register_node(node_class)
            self.node_type_map[full_path] = f"dynamic.{node_class.__name__}"
            if f"dynamic.{node_class.__name__}" not in self._registered_nodes:
                nodes_menu.add_command('运行此节点', lambda graph, node: self.run_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('运行到此节点', lambda graph, node: self.run_to_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('从此节点开始运行', lambda graph, node: self.run_from_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('调试模式', lambda graph, node: node._toggle_debug_mode(),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('编辑组件', lambda graph, node: self.edit_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('查看节点日志', lambda graph, node: node.show_logs(),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('删除节点', lambda graph, node: self.delete_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
        # 迭代节点
        code_node = create_dynamic_code_node(self)
        code_node.__name__ = "DYNAMIC_CODE"
        self.graph.register_node(code_node)
        nodes_menu.add_command('运行此节点', lambda graph, node: self.run_node(node),
                               node_type=f"dynamic.{code_node.__name__}")
        nodes_menu.add_command('运行到此节点', lambda graph, node: self.run_to_node(node),
                               node_type=f"dynamic.{code_node.__name__}")
        nodes_menu.add_command('从此节点开始运行', lambda graph, node: self.run_from_node(node),
                               node_type=f"dynamic.{code_node.__name__}")
        nodes_menu.add_command('查看节点日志', lambda graph, node: node.show_logs(),
                               node_type=f"dynamic.{code_node.__name__}")
        nodes_menu.add_command('删除节点', lambda graph, node: self.delete_node(node),
                               node_type=f"dynamic.{code_node.__name__}")
        self.node_type_map[code_node.FULL_PATH] = f"dynamic.{code_node.__name__}"
        # 迭代节点
        iterate_node = ControlFlowIterateNode
        iterate_node.__name__ = "ControlFlowIterateNode"
        self.graph.register_node(iterate_node)
        nodes_menu.add_command('运行此节点', lambda graph, node: self.run_node(node),
                               node_type=f"control_flow.{iterate_node.__name__}")
        nodes_menu.add_command('运行到此节点', lambda graph, node: self.run_to_node(node),
                               node_type=f"control_flow.{iterate_node.__name__}")
        nodes_menu.add_command('从此节点开始运行', lambda graph, node: self.run_from_node(node),
                               node_type=f"control_flow.{iterate_node.__name__}")
        nodes_menu.add_command('删除节点', lambda graph, node: self.delete_node(node),
                               node_type=f"control_flow.{iterate_node.__name__}")
        self.node_type_map[iterate_node.FULL_PATH] = f"control_flow.{iterate_node.__name__}"
        # 循环节点
        loop_node = ControlFlowLoopNode
        loop_node.__name__ = "ControlFlowLoopNode"
        self.graph.register_node(loop_node)
        nodes_menu.add_command('运行此节点', lambda graph, node: self.run_node(node),
                               node_type=f"control_flow.{loop_node.__name__}")
        nodes_menu.add_command('运行到此节点', lambda graph, node: self.run_to_node(node),
                               node_type=f"control_flow.{loop_node.__name__}")
        nodes_menu.add_command('从此节点开始运行', lambda graph, node: self.run_from_node(node),
                               node_type=f"control_flow.{loop_node.__name__}")
        nodes_menu.add_command('删除节点', lambda graph, node: self.delete_node(node),
                               node_type=f"control_flow.{loop_node.__name__}")
        self.node_type_map[loop_node.FULL_PATH] = f"control_flow.{loop_node.__name__}"
        # 输入端口节点
        input_port_node = CustomPortInputNode
        input_port_node.__name__ = "ControlFlowInputPort"
        self.graph.register_node(input_port_node)
        # 输出端口节点
        output_port_node = CustomPortOutputNode
        output_port_node.__name__ = "ControlFlowOutputPort"
        self.graph.register_node(output_port_node)
        # 注册分支节点
        branch_node = create_branch_node(self)
        branch_node.__name__ = "ControlFlowBranchNode"
        self.graph.register_node(branch_node)
        nodes_menu.add_command('运行此节点', lambda graph, node: self.run_node(node),
                               node_type=f"control_flow.{branch_node.__name__}")
        nodes_menu.add_command('运行到此节点', lambda graph, node: self.run_to_node(node),
                               node_type=f"control_flow.{branch_node.__name__}")
        nodes_menu.add_command('从此节点开始运行', lambda graph, node: self.run_from_node(node),
                               node_type=f"control_flow.{branch_node.__name__}")
        nodes_menu.add_command('删除节点', lambda graph, node: self.delete_node(node),
                               node_type=f"control_flow.{branch_node.__name__}")
        self.node_type_map[branch_node.FULL_PATH] = f"control_flow.{branch_node.__name__}"

    def create_minimap(self):
        self.minimap = MinimapWidget(self)
        QtCore.QTimer.singleShot(0, self._position_minimap)
        self.graph.node_created.connect(self._on_graph_changed)
        self.graph.nodes_deleted.connect(self._on_graph_changed)
        self.graph.port_connected.connect(self._on_graph_changed)
        self.graph.port_disconnected.connect(self._on_graph_changed)
        self.canvas_widget.installEventFilter(self)
        QtCore.QTimer.singleShot(500, self.minimap.show)

    def _on_graph_changed(self):
        QtCore.QTimer.singleShot(300, self.minimap.update_minimap)

    def _position_minimap(self):
        if not hasattr(self, 'minimap') or not self.minimap.isVisible():
            return
        cw = self.canvas_widget
        if cw.width() <= 0 or cw.height() <= 0:
            QtCore.QTimer.singleShot(5, self._position_minimap)
            return
        margin = 10
        x = margin
        y = cw.height() - self.minimap.height() - margin
        self.minimap.move(x, y)

    def create_floating_nodes(self):
        self.nodes_container = QWidget(self.canvas_widget)
        self.nodes_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._update_nodes_container_position()
        self.node_layout = QVBoxLayout(self.nodes_container)
        self.node_layout.setSpacing(3)
        self.node_layout.setContentsMargins(0, 0, 0, 0)

        # === 固定控制流按钮 ===
        self.iterate_node = TransparentToolButton(get_icon("更新"), self)
        self.iterate_node.setIconSize(QSize(20, 20))
        self.iterate_node.setToolTip("创建迭代")
        self.iterate_node.clicked.connect(lambda: self.create_backdrop_node("ControlFlowIterateNode"))
        self.node_layout.addWidget(self.iterate_node)

        self.loop_node = TransparentToolButton(get_icon("无限"), self)
        self.loop_node.setIconSize(QSize(20, 20))
        self.loop_node.setToolTip("创建循环")
        self.loop_node.clicked.connect(lambda: self.create_backdrop_node("ControlFlowLoopNode"))
        self.node_layout.addWidget(self.loop_node)

        self.branch_node = TransparentToolButton(get_icon("条件分支"), self)
        self.branch_node.setIconSize(QSize(20, 20))
        self.branch_node.setToolTip("创建分支")
        self.branch_node.clicked.connect(lambda: self.create_next_node("control_flow.ControlFlowBranchNode"))
        self.node_layout.addWidget(self.branch_node)

        self.code_node = TransparentToolButton(get_icon("代码执行"), self)
        self.code_node.setIconSize(QSize(20, 20))
        self.code_node.setToolTip("创建代码编辑")
        self.code_node.clicked.connect(lambda: self.create_next_node("dynamic.DYNAMIC_CODE"))
        self.node_layout.addWidget(self.code_node)

        self.tool_node = TransparentToolButton(get_icon("工具"), self)
        self.tool_node.setIconSize(QSize(20, 20))
        self.tool_node.setToolTip("创建工具调用")
        self.tool_node.clicked.connect(lambda: self.create_next_node("dynamic.StatusDynamicNode_大模型组件_工具调用"))
        self.node_layout.addWidget(self.tool_node)

        # === 分隔线 ===
        from PyQt5.QtWidgets import QFrame
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setStyleSheet("color: #555;")
        self.node_layout.addWidget(self.separator)

        # === 可显示的快捷按钮容器 ===
        self.visible_quick_container = QWidget(self.nodes_container) # 用于存放可见的快捷按钮
        self.visible_quick_layout = QVBoxLayout(self.visible_quick_container)
        self.visible_quick_layout.setSpacing(3)
        self.visible_quick_layout.setContentsMargins(0, 0, 0, 0) # 调整边距
        self.node_layout.addWidget(self.visible_quick_container)

        # === "更多"按钮及其菜单 ===
        self.more_quick_button = TransparentToolButton(FluentIcon.MORE, self) # 使用 FluentIcon.MORE 或自定义图标
        self.more_quick_button.setIconSize(QSize(20, 20))
        self.more_quick_button.setToolTip("更多快捷组件")
        self.more_quick_menu = RoundMenu(parent=self) # 使用 qfluentwidgets 的菜单
        self.more_quick_button.clicked.connect(self._show_more_quick_menu)

        # 添加 "更多" 按钮到布局
        self.node_layout.addWidget(self.more_quick_button)

        # === 原来的 "+" 按钮（始终在最后）===
        self.add_quick_btn = TransparentToolButton(FluentIcon.ADD, self)
        self.add_quick_btn.setIconSize(QSize(20, 20))
        self.add_quick_btn.setToolTip("添加快捷组件")
        self.add_quick_btn.clicked.connect(self.quick_manager.open_add_dialog)
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
            else:
                icon = FluentIcon.APPLICATION
            action = Action(
                icon, f"创建 {comp_name}",
                triggered=lambda _, fp=full_path, ip=icon_path: self.create_next_node(fp, ip)
            )
            action.setProperty("full_path", full_path)
            self.more_quick_menu.addAction(action)
        # Show the menu
        self.more_quick_menu.exec_(self.more_quick_button.mapToGlobal(QPoint(0, self.more_quick_button.height())))

    def _update_nodes_container_position(self):
        if not hasattr(self, 'nodes_container') or not self.canvas_widget:
            return
        # 计算 layout 所需高度
        self.nodes_container.adjustSize()  # ← 关键：让容器按内容自适应高度
        width = self.nodes_container.width()
        height = self.nodes_container.height()
        # 垂直居中（可调）
        y = max(50, (self.canvas_widget.height() - height) // 2)
        self.nodes_container.move(0, y)

    def _refresh_quick_buttons(self):
        MAX_VISIBLE_QUICK_BUTTONS = 7

        all_quick_components = self.quick_manager.get_quick_components()
        num_quick = len(all_quick_components)

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
                if i == MAX_VISIBLE_QUICK_BUTTONS:
                    self.more_quick_button.show()
            else:

                if icon_path and os.path.exists(icon_path):
                    icon = QtGui.QIcon(icon_path)
                else:
                    icon = FluentIcon.APPLICATION

                btn = TransparentToolButton(icon, self)
                btn.setIconSize(QSize(20, 20))
                btn.setToolTip(f"创建 {comp_name}")
                btn.setProperty("full_path", full_path)
                btn.clicked.connect(lambda _, ip=icon_path, fp=full_path: self.create_next_node(fp, ip))

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
            Action("从快捷栏移除", triggered=lambda: self.quick_manager.remove_component(full_path))
        )
        menu.exec_(button.mapToGlobal(pos))

    def create_next_node(self, key, icon_path=None):
        """按钮节点通用创建方法"""
        selected_nodes = self.graph.selected_nodes()
        try:
            node = self.graph.create_node(key)
        except:
            node_type = self.node_type_map.get(key)
            node = self.graph.create_node(node_type)

        QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(node))
        if icon_path:
            node.set_icon(icon_path)
        if selected_nodes:
            node_x = selected_nodes[0].x_pos()
            node_y = selected_nodes[0].y_pos()
            node.set_pos(node_x + selected_nodes[0].view.width + 100, node_y)
        else:
            # 获取当前视图中心的世界坐标
            viewer = self.graph.viewer()
            # 获取视口中心（widget 坐标）
            viewport_center = viewer.viewport().rect().center()
            # 转换为场景坐标（scene coordinates）
            scene_center = viewer.mapToScene(viewport_center)
            node.set_pos(scene_center.x(), scene_center.y())

    def create_backdrop_node(self, key):
        selected_nodes = self.graph.selected_nodes()
        input_port_node = None
        output_port_node = None
        other_nodes = []
        # Step 1: 分离已有的 Input/Output Port 和其他节点
        for node in selected_nodes:
            if node.type_ == "control_flow.ControlFlowInputPort":
                input_port_node = node
            elif node.type_ == "control_flow.ControlFlowOutputPort":
                output_port_node = node
            elif isinstance(node, ControlFlowBackdrop):
                self.create_failed_info("当前版本无法进行循环迭代嵌套操作！", content="")
                return
            else:
                other_nodes.append(node)
        # Step 2: 获取参考位置（用于无选中节点时）
        viewer = self.graph.viewer()
        viewport_center = viewer.viewport().rect().center()
        scene_center = viewer.mapToScene(viewport_center)
        center_x, center_y = scene_center.x(), scene_center.y()
        # Step 3: 如果没有选中任何节点，创建一个默认的"空"结构
        if not selected_nodes:
            # 创建 Input 和 Output Port，围绕视图中心布局
            input_port_node = self.graph.create_node("control_flow.ControlFlowInputPort")
            output_port_node = self.graph.create_node("control_flow.ControlFlowOutputPort")
            input_port_node.set_pos(center_x - 350, center_y - input_port_node.view.height / 2)
            output_port_node.set_pos(center_x + 350, center_y - output_port_node.view.height / 2)
            nodes_to_wrap = [input_port_node, output_port_node]
        else:
            # Step 4: 有选中节点时，按原逻辑处理
            unconnected_inputs = []
            unconnected_outputs = []
            for node in other_nodes:
                for input_port in node.input_ports():
                    if not input_port.connected_ports():
                        unconnected_inputs.append((node, input_port))
                for output_port in node.output_ports():
                    if not output_port.connected_ports():
                        unconnected_outputs.append((node, output_port))
            # 创建缺失的 Input Port
            if not input_port_node:
                input_port_node = self.graph.create_node("control_flow.ControlFlowInputPort")
                if other_nodes:
                    min_x = min(n.x_pos() for n in other_nodes)
                    avg_y = sum(n.y_pos() for n in other_nodes) / len(other_nodes)
                    input_port_node.set_pos(min_x - 300, avg_y - input_port_node.view.height / 2)
                else:
                    input_port_node.set_pos(center_x - 250, center_y - input_port_node.view.height / 2)
            # 创建缺失的 Output Port
            if not output_port_node:
                output_port_node = self.graph.create_node("control_flow.ControlFlowOutputPort")
                if other_nodes:
                    max_x = max(n.x_pos() + n.view.width for n in other_nodes)
                    avg_y = sum(n.y_pos() for n in other_nodes) / len(other_nodes)
                    output_port_node.set_pos(max_x + 150, avg_y - output_port_node.view.height / 2)
                else:
                    output_port_node.set_pos(center_x + 250, center_y - output_port_node.view.height / 2)
            nodes_to_wrap = other_nodes + [input_port_node, output_port_node]
        # Step 5: 创建 Backdrop 并包裹
        if not nodes_to_wrap:
            self.create_warning_info("创建失败", "没有可包裹的节点！")
            return
        backdrop_node = self.graph.create_node(f"control_flow.{key}")
        backdrop_node.wrap_nodes(nodes_to_wrap)
        QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(backdrop_node))
        # Step 6: 特定配置
        if key == "ControlFlowIterateNode":
            backdrop_node.model.set_property("loop_nums", 3)

    def close_current_canvas(self):
        self.canvas_deleted.emit()
        self.parent.switchTo(self.parent.workflow_manager)
        self.parent.removeInterface(self)

    def create_name_label(self):
        self.name_container = QWidget(self.canvas_widget)
        self.name_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        name_label = LineEdit(self.name_container)
        name_label.setText(self.workflow_name)
        name_label.textChanged.connect(self.update_workflow_name)
        self._update_name_label_width(name_label)
        name_layout = QHBoxLayout(self.name_container)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(5)
        name_layout.addWidget(name_label)
        name_layout.addStretch()
        self.name_container.setLayout(name_layout)
        QtCore.QTimer.singleShot(0, self._position_name_container)
        self.name_container.show()

    def _update_name_label_width(self, line_edit):
        text = line_edit.text() or " "
        font_metrics = line_edit.fontMetrics()
        text_width = font_metrics.horizontalAdvance(text)
        padding = 24
        total_width = text_width + padding
        line_edit.setFixedWidth(max(total_width, 80))
        self.name_container.setFixedWidth(line_edit.width())

    def _position_name_container(self):
        if not hasattr(self, 'name_container') or not self.name_container.isVisible():
            return
        if not hasattr(self, 'canvas_widget') or self.canvas_widget.width() <= 0:
            return
        name_edit = self.name_container.findChild(LineEdit)
        if not name_edit:
            return
        self._update_name_label_width(name_edit)
        container_width = self.name_container.width()
        x = max(0, (self.canvas_widget.width() - container_width) // 2)
        self.name_container.move(x, 10)

    def update_workflow_name(self, text):
        self.workflow_name = text
        name_edit = self.name_container.findChild(LineEdit)
        if name_edit:
            self._update_name_label_width(name_edit)
            QtCore.QTimer.singleShot(0, self._position_name_container)

    def _save_via_dialog(self):
        if self.file_path and self.file_path.stem.split(".")[0] == self.workflow_name:
            file_path = self.file_path
        else:
            file_path = (self.file_path.parent if self.file_path else Path(".")) / f"{self.workflow_name}.workflow.json"
        self.save_full_workflow(file_path)
        self.file_path = file_path

    def _open_via_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开工作流", "", "工作流文件 (*.workflow.json)"
        )
        if file_path:
            self.load_full_workflow(file_path)

    def canvas_drag_enter_event(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def export_selected_nodes_as_project(self):
        """导出选中节点为独立项目（支持交互式定义输入/输出接口）"""
        try:
            nodes_to_export = self.graph.selected_nodes()
            if not nodes_to_export:
                self.create_warning_info("导出失败", "选中的节点无效（只有分组节点）！")
                return
            nodes_to_export.sort(key=lambda node: (node.pos()[0], node.pos()[1]))
            candidate_inputs = []
            for node in nodes_to_export:
                node_name = node.name()
                comp_cls = self.component_map.get(node.FULL_PATH)
                if comp_cls is None:
                    continue
                # 组件参数（超参数）
                editable_params = node.model.custom_properties
                for param_name, param_value in editable_params.items():
                    if param_name not in comp_cls.properties:
                        continue
                    prop_def = comp_cls.properties.get(param_name)
                    candidate_inputs.append({
                        "type": "组件超参数",
                        "node_id": node.id,
                        "node_name": node_name,
                        "param_name": param_name,
                        "current_value": param_value,
                        "display_name": f"{node_name} → {param_name}",
                        "format": getattr(prop_def, 'type', PropertyType.TEXT).name if prop_def else "TEXT"
                    })
                    if prop_def.type == PropertyType.RANGE:
                        candidate_inputs[-1].update({
                            "min": float(prop_def.min),
                            "max": float(prop_def.max),
                            "step": float(prop_def.step)
                        })
                    elif prop_def.type == PropertyType.DYNAMICFORM and prop_def.schema:
                        candidate_inputs[-1]["schema"] = {
                            key: {
                                "type": getattr(value, 'type', PropertyType.TEXT).name if value else "TEXT"
                            }
                            for key, value in prop_def.schema.items()
                        }
                # 输入端口
                for port in node.input_ports():
                    port_name = port.name()
                    # 获取端口类型（ArgumentType）
                    port_type = "TEXT"
                    if comp_cls and hasattr(comp_cls, 'inputs'):
                        for inp in comp_cls.inputs:
                            if inp.name == port_name:
                                port_type = inp.type.name
                                break
                    if port.multi_connection():
                        port_type = f"ARRAY[{port_type}]"
                    connected = port.connected_ports()
                    current_val = None
                    if connected and len(connected) == 1:
                        upstream_out = connected[0]
                        upstream_node = upstream_out.node()
                        value = upstream_node._output_values.get(upstream_out.name())
                        if value is not None:
                            current_val = value
                        else:
                            current_val = None
                    elif len(connected) > 1:
                        current_val = [
                            upstream_out.node()._output_values.get(upstream_out.name())
                            if upstream_out.node()._output_values.get(upstream_out.name()) is not None else None
                            for upstream_out in connected
                        ]
                    else:
                        current_val = getattr(node, '_input_values', {}).get(port_name, None)
                    candidate_inputs.append({
                        "type": "组件输入",
                        "node_id": node.id,
                        "node_name": node_name,
                        "port_name": port_name,
                        "current_value": current_val,
                        "display_name": f"{port_name} → {node_name}",
                        "format": port_type  # ← ArgumentType 的 name，如 "JSON"
                    })
            # === 收集所有候选输出项 ===
            candidate_outputs = []
            for node in nodes_to_export:
                node_name = node.name()
                comp_cls = self.component_map.get(node.FULL_PATH)
                outputs = getattr(node, '_output_values', {})
                for out_name, out_val in outputs.items():
                    out_format = "TEXT"
                    if comp_cls and hasattr(comp_cls, 'outputs'):
                        for out in comp_cls.outputs:
                            if out.name == out_name:
                                out_format = out.type.name
                                break
                    candidate_outputs.append({
                        "node_id": node.id,
                        "node_name": node_name,
                        "output_name": out_name,
                        "sample_value": str(out_val)[:50] + "..." if len(str(out_val)) > 50 else str(out_val),
                        "display_name": f"{node_name} → {out_name}",
                        "format": out_format  # ← 新增
                    })
            # === 弹出选择对话框 ===
            if candidate_inputs:
                input_dialog = InputSelectionDialog(candidate_inputs, self)
                if not input_dialog.exec():
                    return
                selected_input_items = input_dialog.get_selected_items()
            else:
                selected_input_items = []
            if candidate_outputs:
                output_dialog = OutputSelectionDialog(candidate_outputs, self)
                if not output_dialog.exec():
                    return
                selected_output_items = output_dialog.get_selected_items()
            else:
                selected_output_items = []
            # === 构建 project_spec.json ===
            project_spec = {"version": "1.0", "graph_name": self.workflow_name, "inputs": {}, "outputs": {}}
            for item in selected_input_items:
                key = item.get("custom_key", f"input_{len(project_spec['inputs'])}")
                project_spec["inputs"][key] = item
            for item in selected_output_items:
                key = item.get("custom_key", f"output_{len(project_spec['outputs'])}")
                project_spec["outputs"][key] = {
                    "node_id": item["node_id"],
                    "output_name": item["output_name"],
                    "format": item["format"]  # ← 新增
                }
            # === 收集组件和依赖 ===
            used_components = set()
            for node in nodes_to_export:
                used_components.add(node.FULL_PATH)
            requirements = set()
            for full_path in used_components:
                comp_cls = self.component_map.get(full_path)
                if comp_cls:
                    req_str = getattr(comp_cls, 'requirements', '')
                    if req_str:
                        for pkg in req_str.split(','):
                            pkg = pkg.strip()
                            if pkg:
                                requirements.add(pkg)
            # === 构建详细 README（关键增强）===
            project_name_placeholder = self.workflow_name
            original_canvas = getattr(self, 'workflow_name', '未知画布')
            export_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 输入描述
            input_desc = []
            if selected_input_items:
                for i, item in enumerate(selected_input_items):
                    key = item.get("custom_key", f"input_{i}")
                    fmt = item["format"]
                    if item["type"] == "组件超参数":
                        desc = f"- `{key}` (`{fmt}`): 超参数 `{item['param_name']}` of `{item['node_name']}`"
                    else:
                        desc = f"- `{key}` (`{fmt}`): 输入端口 `{item['port_name']}` of `{item['node_name']}`"
                    input_desc.append(desc)
            else:
                input_desc = ["- 无外部输入"]
            # 输出描述
            output_desc = []
            if selected_output_items:
                for i, item in enumerate(selected_output_items):
                    key = item.get("custom_key", f"output_{i}")
                    fmt = item["format"]
                    desc = f"- `{key}` (`{fmt}`): 输出 `{item['output_name']}` from `{item['node_name']}`"
                    output_desc.append(desc)
            else:
                output_desc = ["- 无外部输出"]
            # 组件列表
            component_names = []
            for full_path in used_components:
                name = os.path.basename(full_path).replace('.py', '')
                component_names.append(f"- `{name}`")
            if not component_names:
                component_names = ["- 无组件"]
            # 连接数估算
            original_connections = self.graph.serialize_session()["connections"]
            node_ids_set = {node.id for node in nodes_to_export}
            conn_count = sum(
                1 for conn in original_connections
                if conn["out"][0] in node_ids_set and conn["in"][0] in node_ids_set
            )
            # 详细 README 内容
            detailed_readme = f"""# {project_name_placeholder}
> 从 **{original_canvas}** 导出的子项目 · {export_time}
---
## 📌 项目概览
- **来源画布**: `{original_canvas}`
- **导出时间**: `{export_time}`
- **节点数量**: {len(nodes_to_export)}
- **内部连接**: {conn_count}
- **组件数量**: {len(component_names)}
## 🧩 输入接口
{chr(10).join(input_desc)}
## 📤 输出接口
{chr(10).join(output_desc)}
## 🧱 包含组件
{chr(10).join(component_names)}
## ▶️ 使用方法
1. 安装依赖: `pip install -r requirements.txt`
2. 准备输入: 创建 `inputs.json`，如 `{{"input_0": "hello"}}`
3. 直接运行: `python run.py --input inputs.json`
4. 创建微服务: `python api_server.py --port 8888`
"""
            # === 弹出新对话框 ===
            export_dialog = ProjectExportDialog(
                project_name=project_name_placeholder,
                requirements='\n'.join(sorted(requirements)) if requirements else "# 无依赖",
                readme=detailed_readme,
                parent=self
            )
            if not export_dialog.exec():
                return
            project_name = export_dialog.get_project_name()
            if not project_name:
                self.create_warning_info("导出失败", "项目名不能为空！")
                return
            export_path = pathlib.Path("./projects") / project_name
            export_path.mkdir(parents=True, exist_ok=True)
            # 创建目录
            components_dir = export_path / "components"
            inputs_dir = export_path / "inputs"
            components_dir.mkdir(parents=True, exist_ok=True)
            inputs_dir.mkdir(parents=True, exist_ok=True)
            # 复制组件代码（略，保持你原有逻辑）
            component_path_map = {}
            for full_path in used_components:
                if full_path in self.file_map:
                    src_path = Path(self.file_map[full_path])
                    if src_path.exists():
                        try:
                            base_dir = src_path.parent.parent
                            if base_dir in src_path.parents:
                                src_rel_path = src_path.relative_to(base_dir)
                            else:
                                src_rel_path = src_path.name
                        except ValueError:
                            src_rel_path = src_path.name
                        dst_path = components_dir / src_rel_path
                        dst_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_path, dst_path)
                        rel_to_project = ("components" / src_rel_path).as_posix()
                        component_path_map[str(src_path)] = rel_to_project

            # 构建节点数据（略，保持你原有逻辑）
            def _process_value_for_export(value, inputs_dir: Path, export_path: Path):
                if isinstance(value, str):
                    file_path = Path(value)
                    if file_path.is_file():
                        try:
                            filename = file_path.name
                            dst_path = inputs_dir / filename
                            if not dst_path.exists():
                                shutil.copy2(file_path, dst_path)
                            return (Path("inputs") / filename).as_posix()
                        except Exception as e:
                            logger.error(f"警告：无法复制文件 {value}: {e}")
                            return value
                elif isinstance(value, dict):
                    return {k: _process_value_for_export(v, inputs_dir, export_path) for k, v in value.items()}
                elif isinstance(value, list):
                    return [_process_value_for_export(v, inputs_dir, export_path) for v in value]
                return value

            new_nodes_data = {}
            for node in nodes_to_export:
                editable_params = node.model.custom_properties
                exported_params = {
                    param_name: _process_value_for_export(param_value, inputs_dir, export_path)
                    for param_name, param_value in editable_params.items()
                }
                current_inputs = {}
                for port in node.input_ports():
                    port_name = port.name()
                    connected = port.connected_ports()
                    if connected and len(connected) == 1:
                        upstream_out = connected[0]
                        upstream_node = upstream_out.node()
                        value = upstream_node._output_values.get(upstream_out.name())
                        if value is not None:
                            current_inputs[port_name] = _process_value_for_export(value, inputs_dir, export_path)
                        else:
                            current_inputs[port_name] = None
                    elif len(connected) > 1:
                        current_inputs[port_name] = [
                            _process_value_for_export(
                                upstream_out.node()._output_values.get(upstream_out.name()), inputs_dir, export_path
                            )
                            if upstream_out.node()._output_values.get(upstream_out.name()) is not None else None
                            for upstream_out in connected
                        ]
                    else:
                        current_val = getattr(node, '_input_values', {}).get(port_name, None)
                        current_inputs[port_name] = _process_value_for_export(current_val, inputs_dir, export_path)
                node_data = {
                    "name": node.name(),
                    "type_": node.type_,
                    "pos": node.pos(),
                    "custom": {
                        "FULL_PATH": node.FULL_PATH,
                        "FILE_PATH": component_path_map.get(self.file_map.get(node.FULL_PATH, ""), ""),
                        "params": exported_params,
                        "input_values": serialize_for_json(current_inputs)
                    }
                }
                if isinstance(node, ControlFlowBackdrop):
                    node_data["custom"] = node_data["custom"] | {
                        "internal_nodes": [node.id for node in node.nodes()]
                    }
                new_nodes_data[node.id] = node_data
            # 构建连接
            original_connections = self.graph.serialize_session()["connections"]
            new_connections = []
            node_ids_set = {node.id for node in nodes_to_export}
            for conn in original_connections:
                out_id, out_port = conn["out"]
                in_id, in_port = conn["in"]
                if out_id in node_ids_set and in_id in node_ids_set:
                    new_connections.append({"out": [out_id, out_port], "in": [in_id, in_port]})
            # runtime_data
            runtime_data = {
                "environment": self.env_combo.currentData(),
                "environment_exe": self.get_current_python_exe(),
                "node_id2stable_key": {},
                "node_states": {},
                "node_outputs": {},
                "column_select": {},
                "global_variable": self.global_variables.serialize()
            }
            for node in nodes_to_export:
                full_path = getattr(node, 'FULL_PATH', 'unknown')
                node_name = node.name()
                stable_key = f"{full_path}||{node_name}"
                runtime_data["node_id2stable_key"][node.id] = stable_key
                runtime_data["node_states"][stable_key] = self.node_status.get(node.id, "unrun")
                runtime_data["node_outputs"][stable_key] = serialize_for_json(getattr(node, '_output_values', {}))
                runtime_data["column_select"][stable_key] = getattr(node, 'column_select', {})
            # 保存文件
            graph_data = {
                "nodes": new_nodes_data,
                "connections": new_connections,
                "grid": self.graph.serialize_session().get("grid", None)
            }
            project_data = {
                "version": "1.0",
                "graph": graph_data,
                "runtime": runtime_data,
                "candidate_inputs": candidate_inputs,
                "candidate_outputs": candidate_outputs
            }
            (export_path / "model.workflow.json").write_text(
                json.dumps(project_data, indent=2, ensure_ascii=False), encoding='utf-8'
            )
            (export_path / "project_spec.json").write_text(
                json.dumps(project_spec, indent=2, ensure_ascii=False), encoding='utf-8'
            )
            # 保存 requirements 和 README（使用用户编辑后的内容）
            (export_path / "requirements.txt").write_text(export_dialog.get_requirements(), encoding='utf-8')
            # 复制 runner 等（略）
            current_dir = Path(__file__).parent
            runner_src = current_dir / ".." / "runner"
            if runner_src.exists():
                shutil.copytree(str(runner_src), str(export_path / "runner"), dirs_exist_ok=True)
            base_src = current_dir.parent / "components" / "base.py"
            if base_src.exists():
                shutil.copy(str(base_src), str(components_dir / "base.py"))
            for file in ["run.py", "scan_components.py", "api_server.py"]:
                src = export_path / "runner" / file
                if src.exists():
                    shutil.move(str(src), str(export_path / file))
            # ✅ 保存用户编辑后的 README
            (export_path / "README.md").write_text(export_dialog.get_readme_content(), encoding='utf-8')
            self._generate_selected_nodes_thumbnail(export_path)
            self.create_success_info("导出成功", f"模型项目已导出到:\n{export_path}")
        except Exception as e:
            import traceback
            logger.error(traceback.format_exc())
            self.create_failed_info("导出失败", f"错误: {str(e)}")

    def canvas_drop_event(self, event):
        if event.mimeData().hasText():
            full_path = event.mimeData().text()
            node_type = self.node_type_map.get(full_path)
            if node_type:
                pos = event.pos()
                scene_pos = self.canvas_widget.mapToScene(pos)
                node = self.graph.create_node(node_type)
                node.set_pos(scene_pos.x(), scene_pos.y())
                QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(node))
                self.node_status[node.id] = NodeStatus.NODE_STATUS_UNRUN
                if hasattr(node, 'status'):
                    node.status = NodeStatus.NODE_STATUS_UNRUN
            event.accept()
        else:
            event.ignore()

    def get_node_status(self, node):
        return self.node_status.get(node.id, NodeStatus.NODE_STATUS_UNRUN)

    def set_node_status(self, node, status):
        self.node_status[node.id] = status
        if hasattr(node, 'status'):
            node.status = status
        # 优化：只高亮目标节点相关的连接线
        self._highlight_node_connections(node, status)
        # 优化：只在选中的节点是当前节点时才更新属性面板
        if self.property_panel.current_node and self.property_panel.current_node.id == node.id:
            self.property_panel.update_properties(self.property_panel.current_node)

    def on_node_error_simple(self, node_id):
        node = self._get_node_by_id_cached(node_id)
        if node:
            node._output_values = {}
            self.create_failed_info('错误', f'节点 "{node.name()}" 执行失败！')
            # 直接调用 set_node_status，恢复即时更新
            self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
        self.run_btn.show()
        self.stop_btn.hide()
        self._scheduler = None

    def _on_workflow_finished(self):
        self.run_btn.show()
        self.stop_btn.hide()
        self._scheduler = None
        self.create_success_info("完成", "工作流执行完成!")
        if self.file_path:
            self.save_full_workflow(self.file_path, show_info=False)

    def _on_workflow_error(self, msg=""):
        self._scheduler = None
        self.run_btn.show()
        self.stop_btn.hide()
        self.create_failed_info("错误", f"工作流执行失败! {msg}")

    def on_node_started_simple(self, node_id):
        node = self._get_node_by_id_cached(node_id)
        if node:
            # 直接调用 set_node_status，恢复即时更新
            self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING)

    def _highlight_node_connections(self, node, status):
        """优化的连接线高亮方法"""
        viewer = self.graph.viewer()
        from NodeGraphQt.constants import PipeEnum
        default_color = PipeEnum.COLOR.value
        default_width = 2
        default_style = PipeEnum.DRAW_TYPE_DEFAULT.value

        # 1. 重置与当前节点相关的所有连接线
        for input_port in node.input_ports():
            for out_port in input_port.connected_ports():
                pipe = self._find_pipe_by_ports(out_port, input_port, viewer.all_pipes())
                if pipe:
                    pipe.set_pipe_styling(color=default_color, width=default_width, style=default_style)
        for output_port in node.output_ports():
            for in_port in output_port.connected_ports():
                pipe = self._find_pipe_by_ports(output_port, in_port, viewer.all_pipes())
                if pipe:
                    pipe.set_pipe_styling(color=default_color, width=default_width, style=default_style)

        # 2. 如果状态是运行中，则高亮
        if status == NodeStatus.NODE_STATUS_RUNNING:
            input_color = (64, 158, 255, 255)  # 蓝色
            output_color = (50, 205, 50, 255)  # 绿色
            for input_port in node.input_ports():
                for out_port in input_port.connected_ports():
                    pipe = self._find_pipe_by_ports(out_port, input_port, viewer.all_pipes())
                    if pipe:
                        pipe.set_pipe_styling(color=input_color, width=default_width, style=default_style)
            for output_port in node.output_ports():
                for in_port in output_port.connected_ports():
                    pipe = self._find_pipe_by_ports(output_port, in_port, viewer.all_pipes())
                    if pipe:
                        pipe.set_pipe_styling(color=output_color, width=default_width, style=default_style)

    def _find_pipe_by_ports(self, out_port, in_port, pipes):
        """根据输入输出端口查找对应的连接线"""
        for pipe in pipes:
            if pipe.output_port == out_port.view and pipe.input_port == in_port.view:
                return pipe
        return None

    def on_node_finished_simple(self, node_id):
        node = self._get_node_by_id_cached(node_id)
        if node:
            # 直接调用 set_node_status，恢复即时更新
            self.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
        # 优化：只在节点被选中时更新属性面板
        if node and node.selected():
            QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(node))

    def _get_node_by_id_cached(self, node_id):
        """原始方法，保留用于兼容性"""
        if node_id in self._node_id_cache:
            return self._node_id_cache[node_id]
        for node in self.graph.all_nodes():
            if node.id == node_id:
                return node
        return None

    def on_node_created(self, node):
        self._node_id_cache[node.id] = node

    def _invalidate_node_cache(self):
        """当节点被创建或删除时，标记缓存无效"""
        self._node_id_cache_valid = False
        self._node_id_cache.clear()  # 可选，清空以节省内存

    def delete_node(self, node):
        if node and node.id in self.node_status:
            del self.node_status[node.id]
        # 删除节点后，使缓存无效
        self._invalidate_node_cache()
        self.graph.delete_node(node)

    def on_selection_changed(self, node_ids, prev_ids):
        if len(node_ids) == 0 and len(self.graph.selected_nodes()) > 0:
            # nodegraphqt bug在选中点时用中键拖拽画布会触发选中点变化信号
            return
        if self._selection_update_pending:
            return
        self._selection_update_pending = True
        QtCore.QTimer.singleShot(50, self._do_selection_update)

    def _do_selection_update(self):
        self._selection_update_pending = False
        selected_nodes = self.graph.selected_nodes()
        # 原有属性面板逻辑
        if selected_nodes:
            for node in selected_nodes:
                if isinstance(node, ControlFlowBackdrop):
                    QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(node))
                    return
            if isinstance(selected_nodes[0], BaseNode):
                QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(selected_nodes[0]))
            else:
                QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(None))
        else:
            QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(None))

    def _show_node_flyout(self, node):
        self._hide_node_flyout()

        view_pos = self._get_node_top_right_global_pos(node)
        if not view_pos:
            return

        # ✅ 创建普通 QWidget 作为内容容器
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        content_widget.setFixedWidth(120)

        config_btn = PushButton('⚙️ 配置', content_widget)
        run_btn = PushButton('▶️ 运行', content_widget)
        delete_btn = PushButton('🗑️ 删除', content_widget)

        config_btn.clicked.connect(lambda: self.edit_node(node))
        run_btn.clicked.connect(lambda: self.run_node(node))
        delete_btn.clicked.connect(lambda: self.delete_node(node))

        layout.addWidget(config_btn)
        layout.addWidget(run_btn)
        layout.addWidget(delete_btn)

        # ✅ 直接传 content_widget 给 Flyout.make()
        self._node_flyout = Flyout.make(
            content_widget,
            target=self.canvas_widget,  # 或 self
            parent=self.canvas_widget
        )
        # 手动定位
        flyout_pos = view_pos - QtCore.QPoint(0, self._node_flyout.height())
        self._node_flyout.move(flyout_pos)
        self._node_flyout.show()

    def _hide_node_flyout(self):
        if self._node_flyout:
            try:
                self._node_flyout.close()
            except RuntimeError:
                pass  # 已被销毁，忽略
            self._node_flyout = None

    def _get_node_top_right_global_pos(self, node):
        """获取节点右上角的全局屏幕坐标"""
        try:
            node_item = node.view
            scene_rect = node_item.boundingRect()
            scene_pos = node_item.scenePos()
            top_right_scene = scene_pos + QtCore.QPointF(scene_rect.width(), 0)
            # 转为 view 坐标
            view_pos = self.canvas_widget.mapFromScene(top_right_scene)
            # 转为全局坐标
            global_pos = self.canvas_widget.viewport().mapToGlobal(view_pos)
            return global_pos
        except Exception:
            return None

    def save_full_workflow(self, file_path, show_info=True):
        graph_data = self.graph.serialize_session()
        # 解析图节点数据类
        runtime = {
            "environment": self.env_combo.currentData(),
            "environment_exe": self.get_current_python_exe(),
            "node_id2stable_key": {},
            "node_states": {},
            "node_inputs": {},
            "node_outputs": {},
            "column_select": {},
        }
        for node in self.graph.all_nodes():
            full_path = getattr(node, 'FULL_PATH', 'unknown')
            node_name = node.name()
            stable_key = f"{full_path}||{node_name}"
            runtime["node_id2stable_key"][node.id] = stable_key
            runtime["node_states"][stable_key] = self.node_status.get(node.id, "unrun")
            runtime["node_inputs"][stable_key] = serialize_for_json(getattr(node, '_input_values', {}))
            runtime["node_outputs"][stable_key] = serialize_for_json(getattr(node, '_output_values', {}))
            runtime["column_select"][stable_key] = getattr(node, 'column_select', {})
        full_data = {
            "version": "1.0",
            "graph": graph_data,
            "runtime": runtime,
            "global_variable": self.global_variables.serialize()
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, indent=2, ensure_ascii=False)
        self._generate_canvas_thumbnail_async(file_path)
        if show_info:
            self.create_success_info("保存成功", "工作流保存成功！")

    def _generate_selected_nodes_thumbnail(self, export_path: pathlib.Path):
        """为选中的节点生成缩略图并保存到 export_path 下（如 preview.png）"""
        try:
            selected_nodes = self.graph.selected_nodes()
            if not selected_nodes:
                return  # 无选中节点，不生成
            # 获取选中节点的包围盒
            scene = self.graph.viewer().scene()
            rect = QRectF()
            for node in selected_nodes:
                item_rect = node.view.sceneBoundingRect()
                rect = rect.united(item_rect)
            if rect.isEmpty():
                return
            # 扩展边距
            rect.adjust(-25, -25, 25, 25)
            # 创建图像
            image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
            image.fill(Qt.white)
            painter = QPainter(image)
            # 渲染选中区域
            scene.render(painter, target=QRectF(image.rect()), source=rect)
            painter.end()
            # 保存为 preview.png
            preview_path = export_path / "preview.png"
            image.save(str(preview_path), "PNG")
            logger.info(f"✅ 子图预览图已保存: {preview_path}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.create_warning_info("预览图", f"生成失败: {str(e)}")

    def _generate_canvas_thumbnail_async(self, workflow_path):
        self.thumbnail_thread = ThumbnailGenerator(self.graph, workflow_path)
        self.thumbnail_thread.finished.connect(self._on_thumbnail_generated)
        self.thumbnail_thread.start()

    def _on_thumbnail_generated(self, png_path):
        if png_path:
            logger.info(f"✅ 预览图已保存: {png_path}")
            self.canvas_saved.emit(self.file_path)
        else:
            self.create_warning_info("预览图", "生成失败")

    def load_full_workflow(self, file_path):
        from app.utils.threading_utils import WorkflowLoader
        self.workflow_loader = WorkflowLoader(file_path, self.graph, self.node_type_map)
        self.workflow_loader.finished.connect(self._on_workflow_loaded)
        self.workflow_loader.start()

    def _on_workflow_loaded(self, graph_data, runtime_data, node_status_data, global_variable):
        try:
            self.global_variables.deserialize(global_variable)
            self.property_panel.update_properties(None)
            # === 1. 准备数据 ===
            nodes_data = graph_data.get("nodes", {})
            total_nodes = len(nodes_data)
            if total_nodes == 0:
                self.graph.deserialize_session(graph_data)
                self._finish_loading(runtime_data, node_status_data)
                return

            # === 2. 创建进度对话框 ===
            progress = QProgressDialog("正在加载节点...", "取消", 0, total_nodes, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle("加载中")
            progress.setCancelButton(None)  # 禁用取消，避免状态不一致
            progress.setAutoClose(True)
            progress.setMinimumDuration(0)
            progress.setValue(0)

            # === 3. Monkey patch add_node ===
            original_add_node = self.graph.add_node
            count = [0]  # 使用 list 保持引用

            def patched_add_node(node, pos=None, inherite_graph_style=True):
                result = original_add_node(node, pos, inherite_graph_style)
                count[0] += 1
                progress.setValue(count[0])
                QApplication.processEvents()  # 刷新 UI
                return result

            self.graph.add_node = patched_add_node

            # === 4. 执行反序列化（使用 NodeGraphQt 原生逻辑）===
            try:
                self.graph.deserialize_session(graph_data)
            finally:
                # 恢复原始方法
                self.graph.add_node = original_add_node
                progress.close()

            # === 5. 完成后续加载 ===
            self._finish_loading(runtime_data, node_status_data)

        except Exception as e:
            logger.error(f"❌ 加载失败: {traceback.format_exc()}")
            self.create_failed_info("加载失败", f"工作流加载失败: {str(e)}")

    def _finish_loading(self, runtime_data, node_status_data):
        """加载完成后恢复状态"""
        self._setup_pipeline_style()

        # 环境
        env = runtime_data.get("environment")
        if env:
            for i in range(self.env_combo.count()):
                if self.env_combo.itemData(i) == env:
                    self.env_combo.setCurrentIndex(i)
                    break

        # 节点状态（批量，无 UI 更新）
        all_nodes = self.graph.all_nodes()
        for node in all_nodes:
            full_path = getattr(node, 'FULL_PATH', 'unknown')
            stable_key = f"{full_path}||{node.name()}"
            node_status = node_status_data.get(stable_key)
            if node_status:
                node._input_values = deserialize_from_json(node_status.get("node_inputs", {}))
                node._output_values = deserialize_from_json(node_status.get("node_outputs", {}))
                node.column_select = node_status.get("column_select", {})
                custom_props = node_status.get("custom_property", {})
                for key, value in custom_props.items():
                    if not node.has_property(key):
                        node.create_property(key, value)
                    else:
                        node.set_property(key, value)
                status_str = node_status.get("node_states", "unrun") or "unrun"
                status_enum = getattr(NodeStatus, f"NODE_STATUS_{status_str.upper()}", NodeStatus.NODE_STATUS_UNRUN)
                self.node_status[node.id] = status_enum
                if hasattr(node, 'status'):
                    node.status = status_enum

        # 缓存 & UI
        self._node_id_cache = {node.id: node for node in self.graph.all_nodes()}
        self._node_id_cache_valid = True

        QTimer.singleShot(0, self.create_name_label)
        QTimer.singleShot(300, self._delayed_fit_view)
        self.create_success_info("加载成功", "工作流加载成功！")

    def _delayed_fit_view(self):
        QtCore.QTimer.singleShot(100, lambda: self.graph._viewer.zoom_to_nodes(self.graph._viewer.all_nodes()))

    def edit_node(self, node):
        self.parent.switchTo(self.parent.develop_page)
        self.parent.develop_page._load_component(node.component_class)

    def _setup_pipeline_style(self):
        self.graph.set_pipe_style(
            self.PIPELINE_STYLE.get(self.config.canvas_pipelayout.value)
        )
        self.graph.set_layout_direction(
            self.PIPELINE_DIRECTION.get(self.config.canvas_direction.value)
        )

    def _setup_context_menus(self):
        graph_menu = self.graph.get_context_menu('graph')
        graph_menu.add_command('运行工作流', self.run_workflow, 'Ctrl+R')
        graph_menu.add_command('保存工作流', self._save_via_dialog, 'Ctrl+S')
        graph_menu.add_separator()
        graph_menu.add_command('撤销', self._undo, 'Ctrl+Z')
        graph_menu.add_command('重做', self._redo, 'Ctrl+Y')  # 或 'Ctrl+Shift+Z'
        graph_menu.add_command('自动布局', self._auto_layout_selected, 'Ctrl+L')
        edit_menu = graph_menu.add_menu('编辑')
        edit_menu.add_command('全选', lambda graph: graph.select_all(), 'Ctrl+A')
        edit_menu.add_command('取消选择', lambda graph: graph.clear_selection(), 'Ctrl+D')
        edit_menu.add_command('删除选中', lambda graph: self.delete_selected_nodes(graph), 'Del')

    def delete_selected_nodes(self, graph):
        # 清除选中节点的输入输出端口连接线
        for node in graph.selected_nodes():
            if isinstance(node, BackdropNode):
                for port in node.input_ports():
                    port.clear_connections(push_undo=True, emit_signal=True)
                for port in node.output_ports():
                    port.clear_connections(push_undo=True, emit_signal=True)
        graph.delete_nodes(graph.selected_nodes())
        # 删除节点后，使缓存无效
        self._invalidate_node_cache()

    def _undo(self):
        try:
            if self.graph.undo_stack().canUndo():
                self.graph.undo_stack().undo()
            else:
                self.create_info("提示", "没有可撤销的操作")
        except Exception as e:
            logger.warning(f"撤销失败: {e}")

    def _redo(self):
        try:
            if self.graph.undo_stack().canRedo():
                self.graph.undo_stack().redo()
            else:
                self.create_info("提示", "没有可重做的操作")
        except Exception as e:
            logger.warning(f"重做失败: {e}")

    def _auto_layout_selected(self, node=None):
        selected = self.graph.selected_nodes()
        if selected:
            self.graph.auto_layout_nodes(nodes=selected, start_nodes=[node] if node else None)
        else:
            self.graph.auto_layout_nodes(nodes=self.graph.all_nodes(), start_nodes=[node] if node else None)

    def _copy_selected_nodes(self):
        selected_nodes = self.graph.selected_nodes()
        if not selected_nodes:
            return
        self._clipboard_data = self.graph.copy_nodes()
        self.create_info("复制成功", f"已复制 {len(selected_nodes)} 个节点")

    def _paste_nodes(self):
        if not self._clipboard_data:
            return
        selected_nodes = self.graph.selected_nodes()
        if selected_nodes:
            avg_x = sum(n.pos()[0] for n in selected_nodes) / len(selected_nodes)
            avg_y = sum(n.pos()[1] for n in selected_nodes) / len(selected_nodes)
            offset = (50, 50)
        else:
            viewer = self.graph.viewer()
            center = viewer.mapToScene(viewer.rect().center())
            avg_x, avg_y = center.x(), center.y()
            offset = (0, 0)
        pasted_nodes = self.graph.paste_nodes(self._clipboard_data)
        if pasted_nodes:
            min_x = min(n.pos()[0] for n in pasted_nodes)
            min_y = min(n.pos()[1] for n in pasted_nodes)
            for node in pasted_nodes:
                x, y = node.pos()
                new_x = x - min_x + avg_x + offset[0]
                new_y = y - min_y + avg_y + offset[1]
                node.set_pos(new_x, new_y)
            self.create_info("粘贴成功", f"已粘贴 {len(pasted_nodes)} 个节点")
        # 粘贴节点后，使缓存无效
        self._invalidate_node_cache()

    def create_success_info(self, title, content):
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )

    def create_failed_info(self, title, content):
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )

    def create_warning_info(self, title, content):
        InfoBar.warning(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )

    def create_info(self, title, content):
        InfoBar.info(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )
