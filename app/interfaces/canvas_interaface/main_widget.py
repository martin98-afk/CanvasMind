# -*- coding: utf-8 -*-
import traceback

from pathlib import Path
from NodeGraphQt.widgets.viewer import NodeViewer
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal, QThreadPool
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget
from loguru import logger

from app.components.base import GlobalVariableContext
from app.interfaces.canvas_interaface.llm_context import LLMContextProvider
from app.interfaces.canvas_interaface.utils.auto_saver import AutoSaver
from app.interfaces.canvas_interaface.utils.canvas_io import CanvasIO
from app.interfaces.canvas_interaface.utils.canvas_runner import CanvasRunner
from app.interfaces.canvas_interaface.utils.exporter import CanvasExporter
from app.interfaces.canvas_interaface.utils.node_operations import NodeOperations
from app.interfaces.canvas_interaface.utils.quick_component_manager import QuickComponentManager
from app.interfaces.canvas_interaface.widgets.environment_manager import EnvironmentManager
from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager
from app.interfaces.canvas_interaface.widgets.ui_setup import CanvasUISetUp
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.status_node import NodeStatus
from app.scan_components import ComponentScanner
from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.custom_nodegraphqt.custom_nodegraph import CustomNodeGraph, CustomNodeViewer
from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextRegistry


class CanvasPage(QWidget):
    canvas_deleted = pyqtSignal()
    canvas_saved = pyqtSignal(Path)
    global_variables_changed = pyqtSignal(str, str, str)
    env_changed = pyqtSignal(str)
    component_code_changed = pyqtSignal(str, str) # 组件文件地址、更新代码

    def __init__(self, parent=None, object_name: Path = None, manager=None):
        super().__init__()
        self.parent = parent
        self.manager = manager
        self.file_path = object_name
        self.workflow_name = object_name.stem.split(".")[0] if object_name else "未命名工作流"
        self.setObjectName('canvas_page' if object_name is None else str(object_name))
        self.config = Settings.get_instance()
        self._pending_property_update = None
        # 线程池
        self.thread_pool = QThreadPool.globalInstance()
        # 全局变量
        self.global_variables = GlobalVariableContext()
        # 初始化 NodeGraph
        self.graph = CustomNodeGraph(viewer=CustomNodeViewer(), parent=self)
        self.canvas_widget = self.graph.viewer()
        # 去除边框
        self.canvas_widget.setStyleSheet("QWidget {border: none;}")
        self.canvas_widget.keyPressEvent = self._canvas_key_press_event
        # 启用画布拖拽
        self.canvas_widget.setAcceptDrops(True)
        self.canvas_widget.dragEnterEvent = self.canvas_drag_enter_event
        self.canvas_widget.dropEvent = self.canvas_drop_event
        self.canvas_widget.installEventFilter(self)
        # ========== 注册工具 ====================
        # --- 节点操作 ---
        self.node_operations = NodeOperations(self, self.graph, self.manager.recommendation_engine, self.thread_pool)
        # 注册节点
        QtCore.QTimer.singleShot(10, self.node_operations.register_components)
        # --- 快捷组件工具管理 ---
        self.quick_manager = QuickComponentManager(self, self.component_map)
        # --- 自动保存相关 ---
        self._auto_saver = AutoSaver(self, self.file_path, self.config)
        # --- 环境管理 ---
        self.environment_manager = EnvironmentManager(self)
        # --- 画布io管理 ---
        self.canvas_io = CanvasIO(
            self.graph,
            self.environment_manager,
            self.global_variables,
            self
        )
        # --- 画布运行管理 ---
        self.canvas_runner = CanvasRunner(
            self.environment_manager.get_current_python_exe, self
        )
        # =======================================
        # 初始化ui
        self.ui_manager = CanvasUISetUp(self)
        self.ui_manager.setup_ui()
        # 注册大模型画布上下文
        self.llm_context_provider = LLMContextProvider(
            graph=self.graph,
            global_variables=self.global_variables,
            canvas_io=self.canvas_io,
            ui_manager=self.ui_manager,
            node_operations=self.node_operations,
            select_node_callback=self.select_node_by_name,
            parent=self
        )
        # 注册右键菜单
        self._setup_context_menus()
        # 连接ui信号
        self.load_env_combos()
        self.env_combo.currentIndexChanged.connect(self.on_environment_changed)
        # 连接ipython控制台
        self.connect_kernel(self.environment_manager.get_current_python_exe())
        self.env_changed.connect(self.connect_kernel)
        self.graph.node_created.connect(self.node_operations.on_node_created)
        self.graph.port_connected.connect(self._on_port_connected)
        self.graph.viewer().node_selection_changed.connect(
            lambda: QtCore.QTimer.singleShot(0, self.on_selection_changed)
        )
        self.ui_manager.log_window.cardDoubleClicked.connect(self.node_operations.select_nodes_by_name)
        self.quick_manager.quick_components_changed.connect(self.ui_manager._refresh_quick_buttons)
        self._connect_runner_signals()

    # 代理方法
    @property
    def context_register(self):
        return self.llm_context_provider.context_register

    @property
    def env_combo(self):
        return self.ui_manager.env_combo

    @property
    def run_btn(self):
        return self.ui_manager.run_btn

    @property
    def stop_btn(self):
        return self.ui_manager.stop_btn

    @property
    def node_status(self):
        return self.node_operations.node_status

    @property
    def node_type_map(self):
        return self.node_operations.node_type_map

    @property
    def registered_nodes(self):
        return self.node_operations._registered_nodes

    @property
    def component_map(self):
        component_map, _ = ComponentScanner().get_components()
        return component_map

    @property
    def file_map(self):
        _, file_map = ComponentScanner().get_components()
        return file_map

    @property
    def property_panel(self):
        return self.ui_manager.property_panel

    @property
    def nav_view(self):
        return self.ui_manager.nav_view

    @property
    def ipython_kernel(self):
        return self.ui_manager.ipython_console

    @property
    def selected_categories(self):
        return self.ui_manager.nav_view._selected_categories

    @property
    def log_window(self):
        return self.ui_manager.log_window

    def _on_global_variables_changed(self, *args):
        self.property_panel._on_global_variables_changed(*args)

    def show_splitter(self):
        self.ui_manager.show_splitter()

    def hide_splitter(self):
        self.ui_manager.hide_splitter()

    def load_env_combos(self):
        self.environment_manager.load_env_combos()

    def on_environment_changed(self):
        self.environment_manager.on_environment_changed()

    def on_context_action(self, content: str, action: str):
        """
        content: "数据加载器"
        action: "jump:node_102"
        """
        if action.startswith("jump"):
            self.select_node_by_name(content)
        elif action.startswith("create"):
            self.node_operations.create_next_node_using_name(content)
        elif action == "inspect":
            pass
            # self.homepage.show_variable_inspector("var_input")

    def select_node_by_name(self, name_list):
        if name_list is None:
            return
        return self.node_operations.select_nodes_by_name(name_list)

    def connect_kernel(self, python_exe):
        if python_exe:
            if self.ipython_kernel.kernel_manager.python_exe_path != python_exe or \
                    not self.ipython_kernel.kernel_manager.get_kernel_info().get("is_alive"):
                self.ipython_kernel.kernel_manager.shutdown_kernel()
                self.ipython_kernel.start_kernel(python_exe)

    def run_from(self, node):
        self.canvas_runner.run_from(node)

    def run_to(self, node):
        self.canvas_runner.run_to(node)

    def run_node(self, node):
        self.canvas_runner.run_node(node)

    def delete_node(self, node):
        self.node_operations.delete_node(node)

    def get_current_python_exe(self):
        return self.environment_manager.get_current_python_exe()

    def _setup_pipeline_style(self):
        return self.ui_manager._setup_pipeline_style()

    def switch_to_parent(self):
        self.parent.switchTo(self.parent.workflow_manager)

    def export_selected_nodes_as_project(self):
        CanvasExporter(
            self,
            self.component_map,
            self.file_map,
            self.property_panel.get_current_execution_order(),
        ).export_selected_nodes_as_project()

    def save_full_workflow(self, file_path=None, show_info=True):
        if not isinstance(file_path, str) or not isinstance(file_path, Path):
            if self.file_path and self.file_path.stem.split(".")[0] == self.workflow_name:
                file_path = self.file_path
            else:
                file_path = (self.file_path.parent if self.file_path else Path(
                    "../app/interfaces")) / f"{self.workflow_name}.workflow.json"
        self.canvas_io.save_full_workflow(file_path, show_info)
        self.file_path = file_path

    def load_full_workflow(self, file_path=None):
        self.canvas_io.load_full_workflow(file_path)

    def create_name_label(self):
        self.ui_manager.create_name_label()

    def create_next_node(self, key, icon_path=None):
        self.node_operations.create_next_node(key, icon_path)

    def create_backdrop_node(self, key):
        self.node_operations.create_backdrop_node(key)

    def register_components(self):
        self.node_operations.register_components()

    def _setup_context_menus(self):
        graph_menu = self.graph.get_context_menu('graph')
        graph_menu.add_command('运行工作流', self.canvas_runner.run_workflow, 'Ctrl+R')
        graph_menu.add_command('保存工作流', self.save_full_workflow, 'Ctrl+S')
        graph_menu.add_separator()
        graph_menu.add_command('撤销', self._undo, 'Ctrl+Z')
        graph_menu.add_command('重做', self._redo, 'Ctrl+Y')  # 或 'Ctrl+Shift+Z'
        graph_menu.add_command('自动布局', self._auto_layout_selected, 'Ctrl+L')
        edit_menu = graph_menu.add_menu('编辑')
        edit_menu.add_command('全选', lambda graph: graph.select_all(), 'Ctrl+A')
        edit_menu.add_command('取消选择', lambda graph: graph.clear_selection(), 'Ctrl+D')
        edit_menu.add_command(
            '删除选中', lambda graph: (
                self.node_operations.delete_selected_nodes(graph), self.property_panel.update_properties(None)
            ), 'Del'
        )
        nodes_menu = self.graph.get_context_menu('nodes')
        for special_node in [
            "dynamic.DYNAMIC_CODE", "control_flow.ControlFlowIterateNode",
            "control_flow.ControlFlowLoopNode", "control_flow.ControlFlowBranchNode"
        ]:
            nodes_menu.add_command('运行此节点', lambda graph, node: self.run_node(node),
                                   node_type=special_node, icon=get_icon("运行"))
            nodes_menu.add_command('运行到此节点', lambda graph, node: self.run_to(node),
                                   node_type=special_node, icon=get_icon("运行到此处"))
            nodes_menu.add_command('从此节点开始运行', lambda graph, node: self.run_from(node),
                                   node_type=special_node, icon=get_icon("从此处运行"))
            if special_node == "dynamic.DYNAMIC_CODE":
                nodes_menu.add_command(
                    '查看节点日志', lambda graph, node: node.show_logs(),
                    node_type=special_node, icon=get_icon("系统运行日志")
                )
            nodes_menu.add_separator(node_type=special_node)
            nodes_menu.add_command(
                '删除节点', lambda graph, node: self.delete_node(node),
                node_type=special_node, icon=QIcon(f":/qfluentwidgets/images/icons/Delete_white.svg")
            )

    def _schedule_property_update(self, nodes):
        if self._pending_property_update:
            self._pending_property_update.stop()
        self._pending_property_update = QtCore.QTimer()
        self._pending_property_update.setSingleShot(True)
        self._pending_property_update.timeout.connect(
            lambda: self.property_panel.update_properties(nodes)
        )
        self._pending_property_update.start(10)  # 10ms 防抖

    # --- 信号绑定 ---
    def set_node_status_by_id(self, node_id, status):
        node = self.node_operations._get_node_by_id_cached(node_id)
        if node:
            self.set_node_status(node, status)

    def _on_workflow_started(self):
        """开始执行"""
        self.run_btn.hide()
        self.stop_btn.show()

    def _on_workflow_cancelled(self):
        """停止当前执行"""
        self.run_btn.show()
        self.stop_btn.hide()

    def on_node_error_simple(self, node_id):
        node = self.node_operations._get_node_by_id_cached(node_id)
        if node:
            node._output_values = {}
            MessageManager.error('错误', f'节点 "{node.name()}" 执行失败！', self)
            # 直接调用 set_node_status，恢复即时更新
            QtCore.QTimer.singleShot(0, lambda: self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED))

        self.run_btn.show()
        self.stop_btn.hide()
        self._scheduler = None

    def _on_workflow_finished(self):
        self.run_btn.show()
        self.stop_btn.hide()
        self._scheduler = None
        MessageManager.success("完成", "工作流执行完成!", self)

    def _on_workflow_error(self, msg=""):
        self._scheduler = None
        self.run_btn.show()
        self.stop_btn.hide()
        MessageManager.error("错误", f"工作流执行失败! {msg}", self)

    def on_node_started_simple(self, node_id):
        node = self.node_operations._get_node_by_id_cached(node_id)
        if node:
            # 直接调用 set_node_status，恢复即时更新
            QtCore.QTimer.singleShot(0, lambda: self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING))

    def _connect_runner_signals(self):
        """连接调度器信号到 UI 回调"""
        # 优化：直接连接到具体处理方法，避免不必要的中间信号
        self.canvas_runner.workflow_started.connect(self._on_workflow_started)
        self.canvas_runner.node_started.connect(self.on_node_started_simple)
        self.canvas_runner.node_finished.connect(self.on_node_finished_simple)
        self.canvas_runner.node_error.connect(self.on_node_error_simple)
        self.canvas_runner.workflow_finished.connect(self._on_workflow_finished)
        self.canvas_runner.workflow_error.connect(self._on_workflow_error)
        self.canvas_runner.node_status_changed.connect(self.set_node_status_by_id)
        self.canvas_runner.workflow_cancelled.connect(self._on_workflow_cancelled)

        # 面板刷新信号
        self.canvas_runner.property_changed.connect(self.property_panel.update_properties)
        self.canvas_runner.node_vars_changed.connect(self.property_panel.refresh_node_vars_page)

    # --- 画布按键信号 ---
    def _canvas_key_press_event(self, event):
        super(NodeViewer, self.canvas_widget).keyPressEvent(event)
        self.canvas_widget.ALT_state = event.modifiers() == QtCore.Qt.AltModifier
        self.canvas_widget.CTRL_state = event.modifiers() == QtCore.Qt.ControlModifier
        self.canvas_widget.SHIFT_state = event.modifiers() == QtCore.Qt.ShiftModifier
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
                overlay_text = '\n    SHIFT:\n    扩展节点选择'
            elif self.canvas_widget.CTRL_state:
                overlay_text = '\n    CTRL:\n    取消节点选择'
        elif self.canvas_widget.ALT_state and self.canvas_widget.SHIFT_state:
            if self.canvas_widget.pipe_slicing:
                overlay_text = '\n    ALT + SHIFT:\n    连线删除模式'
        if overlay_text:
            self.canvas_widget._cursor_text.setPlainText(overlay_text)
            self.canvas_widget._cursor_text.setFont(QtGui.QFont('Arial', 10))
            self.canvas_widget._cursor_text.setDefaultTextColor(Qt.white)
            self.canvas_widget._cursor_text.setPos(self.canvas_widget.mapToScene(self.canvas_widget._previous_pos))
            self.canvas_widget._cursor_text.setVisible(True)
        if event.modifiers() == QtCore.Qt.ControlModifier:
            if event.key() == QtCore.Qt.Key_C:
                self.node_operations._copy_selected_nodes()
            elif event.key() == QtCore.Qt.Key_V:
                self.node_operations._paste_nodes()

    def eventFilter(self, obj, event):
        if obj is self.graph.viewer() and event.type() == event.Resize:
            self.ui_manager.update_position()
        return super().eventFilter(obj, event)

    def center_to(self, node):
        self.graph.clear_selection()
        if node not in self.graph.all_nodes():
            MessageManager.warning("错误", "原节点不存在！", self)
            return
        node.set_selected(True)
        self.graph.fit_to_selection()

    def canvas_drag_enter_event(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def canvas_drop_event(self, event):
        try:
            if event.mimeData().hasText():
                full_path = event.mimeData().text()
                node_type = self.node_type_map.get(full_path)
                if node_type:
                    pos = event.pos()
                    scene_pos = self.canvas_widget.mapToScene(pos)
                    node = self.graph.create_node(node_type)
                    self.nav_view.record_usage(full_path)
                    node.set_pos(scene_pos.x(), scene_pos.y())
                    QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(node))
                    self.node_status[node.id] = NodeStatus.NODE_STATUS_UNRUN
                    if hasattr(node, 'status'):
                        node.status = NodeStatus.NODE_STATUS_UNRUN
                event.accept()
            else:
                event.ignore()
        except Exception as e:
            logger.error(traceback.format_exc())

    def get_node_status(self, node):
        return self.node_status.get(node.id, NodeStatus.NODE_STATUS_UNRUN)

    def set_node_status(self, node, status):
        self.node_status[node.id] = status
        if hasattr(node, 'status'):
            node.status = status
        # 优化：只高亮目标节点相关的连接线
        self._highlight_node_connections(node, status)

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
        node = self.node_operations._get_node_by_id_cached(node_id)
        if node:
            # 直接调用 set_node_status，恢复即时更新
            QtCore.QTimer.singleShot(0, lambda: self.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS))
        # 优化：只在只选中该节点时更新其属性面板
        if node and node.selected() and len(self.graph.selected_nodes()) == 1:
            QtCore.QTimer.singleShot(0, lambda: self.property_panel.update_properties(node))

    def _on_port_connected(self, input_port, output_port):
        in_node = input_port.node()
        out_node = output_port.node()
        src_path = getattr(out_node, 'FULL_PATH', None)
        dst_path = getattr(in_node, 'FULL_PATH', None)
        if src_path and dst_path:
            self.manager.recommendation_engine._stats_manager.record_connection(src_path, dst_path)

    def on_selection_changed(self):
        selected_nodes = self.graph.selected_nodes()
        # 原有属性面板逻辑
        if selected_nodes:
            # 展示控制流面板
            backdrop_internal_nodes = []
            for node in selected_nodes:
                if isinstance(node, ControlFlowBackdrop):
                    internal_nodes = [n for n in node.nodes()]
                    backdrop_internal_nodes.extend(internal_nodes)
                    only_backdrop = all(n in internal_nodes for n in selected_nodes if n != node)
                    if only_backdrop:
                        self.nav_view.clear_recommendations()
                        self._schedule_property_update(node)
                        self.property_panel.reset_current_components()
                        return
            # 展示选中节点列表
            if len(selected_nodes) > 1:
                # 过滤掉在backdrop内部的节点，只保留顶层节点（包括backdrop本身）
                top_level_nodes = [n for n in selected_nodes if n not in backdrop_internal_nodes]
                self._schedule_property_update(top_level_nodes)
            # 展示单独节点面板
            elif isinstance(selected_nodes[0], BasicNodeWithGlobalProperty):
                self._schedule_property_update(selected_nodes[0])
                self.property_panel.reset_current_components()
                QtCore.QTimer.singleShot(0, lambda: self.node_operations._request_recommendations(selected_nodes[0]))
            # 展示全局变量面板
            else:
                self.nav_view.clear_recommendations()
                self.property_panel.reset_current_components()
                self._schedule_property_update(None)
        else:
            self.nav_view.clear_recommendations()
            self.property_panel.reset_current_components()
            self._schedule_property_update(None)

    def _delayed_fit_view(self):
        self.graph._viewer.zoom_to_nodes(self.graph._viewer.all_nodes())
        self.property_panel.set_allowed_update(True)
        self.property_panel.update_properties(None)

    def edit_node(self, node):
        self.parent.switchTo(self.parent.develop_page)
        self.parent.develop_page._load_component(node.FULL_PATH)

    def _undo(self):
        try:
            if self.graph.undo_stack().canUndo():
                self.graph.undo_stack().undo()
            else:
                MessageManager.info("提示", "没有可撤销的操作", self)
        except Exception as e:
            logger.warning(f"撤销失败: {e}")

    def _redo(self):
        try:
            if self.graph.undo_stack().canRedo():
                self.graph.undo_stack().redo()
            else:
                MessageManager.info("提示", "没有可重做的操作", self)
        except Exception as e:
            logger.warning(f"重做失败: {e}")

    def _auto_layout_selected(self, graph, node=None):
        selected = self.graph.selected_nodes()
        if selected:
            self.graph.auto_layout_nodes(nodes=selected, start_nodes=[node] if node else None)
        else:
            self.graph.auto_layout_nodes(nodes=self.graph.all_nodes(), start_nodes=[node] if node else None)

    # --- 画布关闭逻辑 ---
    def close_current_canvas(self):
        # 1. 停止并断开所有定时器
        self._auto_saver.stop()
        self.ipython_kernel.stop_kernel()
        self.ui_manager.destroy_all()
        # ===== 7. 销毁 UI 控件（确保 parent=None）=====
        self.graph.deleteLater()
        # 8. 发射信号 & 移除自身
        self.canvas_deleted.emit()
        self.parent.removeInterface(self)
        self.deleteLater()  # 关键：触发 Qt 对象销毁
