# -*- coding: utf-8 -*-
import re
import traceback
from pathlib import Path

from NodeGraphQt.widgets.viewer import NodeViewer
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal, QThreadPool, QPoint, QTimer
from PyQt5.QtWidgets import QWidget, QApplication, QTextEdit, QLineEdit
from loguru import logger
from qfluentwidgets import FluentIcon

from app.components.base import GlobalVariableContext
from app.interfaces.canvas_interaface.constants import TEMPLATE_START_SIZES
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
from app.widgets.basic_widget.category_filter import CategoryFilterDialog
from app.widgets.custom_nodegraphqt.custom_nodegraph import CustomNodeGraph, CustomNodeViewer


class CanvasPage(QWidget):
    canvas_deleted = pyqtSignal()
    canvas_saved = pyqtSignal(Path)
    global_variables_changed = pyqtSignal(str, str)  # 用于刷新组件中的变量下拉菜单
    env_changed = pyqtSignal(str)

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
        self.node_operations.register_components()
        # --- 快捷组件工具管理 ---
        self.quick_manager = QuickComponentManager(self, self.component_map)
        # --- 自动保存相关 ---
        self._auto_saver = AutoSaver(self, self.config)
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
        # 初始化右键菜单
        self.node_operations.setup_context_menu()
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
        self._connect_signals()

    # 代理方法
    @property
    def running_projects_changed(self):
        return self.manager.running_projects_changed

    @property
    def exported_projects_changed(self):
        return self.manager.exported_projects_changed

    @property
    def component_code_changed(self):
        return self.manager.component_code_changed

    @property
    def node_request_edit(self):
        return self.manager.node_request_edit

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
    def pause_btn(self):
        return self.ui_manager.pause_btn

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

    def rename_node_vars(self, old_name, new_name):
        old_name = re.sub(r'\s+', '_', old_name)
        new_name = re.sub(r'\s+', '_', new_name)
        input_proxy_old_name = f"input.{old_name}"
        input_proxy_new_name = f"input.{new_name}"
        old_names, new_names = self.global_variables.rename_node_vars(old_name, new_name)
        for old_name, new_name in zip(old_names, new_names):
            self.global_variables_changed.emit(old_name, "delete")
            self.global_variables_changed.emit(new_name, "add")
        for node in self.graph.all_nodes():
            node.rename_variable(
                old_names + [input_proxy_old_name], new_names + [input_proxy_new_name]
            )

    def show_intervention_dialog(self, title, message, schema, callback):
        self.canvas_runner.show_intervention_dialog(title, message, schema, callback)

    def show_category_dialog(self, categories, tag):
        all_categories = set()
        for full_path, comp_cls in self.component_map.items():
            category = getattr(comp_cls, 'category', 'General')
            all_categories.add(category)
        pos = tag.mapToGlobal(QPoint(0, 0))
        category_filter_dialog = CategoryFilterDialog(sorted(all_categories), self, categories, "auto")
        category_filter_dialog.categories_changed.connect(self.ui_manager.nav_panel.draggable_tree._on_categories_changed)
        category_filter_dialog.show_at(pos)

    def _on_global_variables_changed(self, var_type: str, var_name: str, action: str):
        self.property_panel._on_global_variables_changed(var_type, var_name, action)

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
            content = content if not "," in content else [x.strip() for x in content.split(",")]
            self.select_node_by_name(content)
        elif action.startswith("create"):
            self.node_operations.create_next_node_using_name(content)
        elif action.startswith("generate"):
            question = (f"历史对话上下文：{self.ui_manager.llm_chatter.session_manager.get_current_session().messages}\n\n"
                        f"你的任务是结合历史对啊信息生成这个 {content} 组件的代码")
            self.parent.switchTo(self.parent.develop_page)
            self.parent.develop_page.llm_context_provider.send_preset_generate_llm_request(question)

    def select_node_by_name(self, name_list, *args):
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

    def start_from_template(self):
        self.ui_manager.nav_panel.start_from_template()
        self.ui_manager.splitter.setSizes(TEMPLATE_START_SIZES)

    def switch_to_parent(self):
        self.parent.switchTo(self.parent.workflow_manager)

    def export_selected_nodes_as_project(self):
        CanvasExporter(
            self,
            self.component_map,
            self.file_map,
            self.property_panel.get_current_execution_order(),
        ).export_selected_nodes_as_project()

    def save_full_workflow(self, show_info=True):
        self.canvas_io.save_full_workflow(self.file_path, show_info)

    def load_full_workflow(self, file_path=None):
        self.canvas_io.load_full_workflow(file_path)

    def create_name_label(self):
        self.ui_manager.create_name_label()

    def create_next_node(self, key, icon_path=None):
        self.node_operations.create_next_node(key, icon_path)

    def create_backdrop_node(self, key):
        self.node_operations.create_backdrop_node(key)

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

    def _on_pause_resume_clicked(self):
        if self.canvas_runner.is_paused():
            self.canvas_runner.resume_workflow()
        else:
            self.canvas_runner.pause_workflow()

    def _on_workflow_started(self):
        """开始执行：隐藏 run，显示 pause + stop"""
        self.run_btn.hide()
        self.pause_btn.show()
        self.stop_btn.show()
        self.pause_btn.setIcon(FluentIcon.PAUSE)
        self.pause_btn.setToolTip("暂停工作流")

    def _on_workflow_paused(self):
        """进入暂停：pause 按钮变为 resume"""
        self.pause_btn.setIcon(FluentIcon.PLAY)
        self.pause_btn.setToolTip("继续工作流")

    def _on_workflow_resumed(self):
        """恢复执行：pause 按钮变回 pause"""
        self.pause_btn.setIcon(FluentIcon.PAUSE)
        self.pause_btn.setToolTip("暂停工作流")

    def _on_workflow_cancelled(self):
        """停止/取消：恢复 run 按钮"""
        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()

    def _on_workflow_finished(self):
        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()
        MessageManager.success("完成", "工作流执行完成!", self)

    def _on_workflow_error(self, msg=""):
        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()

    def on_node_error_simple(self, node_id):
        node = self.node_operations._get_node_by_id_cached(node_id)
        if node:
            node._output_values = {}
            MessageManager.error('错误', f'节点 "{node.name()}" 执行失败！', self)
            # 直接调用 set_node_status，恢复即时更新
            QtCore.QTimer.singleShot(0, lambda: self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED))

        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()
        self._scheduler = None

    def on_node_started_simple(self, node_id):
        node = self.node_operations._get_node_by_id_cached(node_id)
        if node:
            # 直接调用 set_node_status，恢复即时更新
            QtCore.QTimer.singleShot(0, lambda: self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING))

    def _connect_signals(self):
        """连接调度器信号到 UI 回调"""
        # 连接自动组件同步刷新信号
        ComponentScanner.register_on_change(self.nav_view.refresh_components)
        ComponentScanner.register_on_change(self.node_operations.register_components, False)
        # 画布上按钮信号
        self.ui_manager.run_btn.clicked.connect(self.canvas_runner.run_workflow)
        self.ui_manager.pause_btn.clicked.connect(self._on_pause_resume_clicked)  # 新增
        self.ui_manager.stop_btn.clicked.connect(self.canvas_runner.stop_workflow)
        self.ui_manager.save_btn.clicked.connect(lambda: self.save_full_workflow())
        self.ui_manager.export_model_btn.clicked.connect(self.export_selected_nodes_as_project)
        self.ui_manager.close_btn.clicked.connect(
            lambda: (
                QtCore.QTimer.singleShot(0, self.close_current_canvas),
                self.switch_to_parent()
            )
        )

        # 状态信号
        self.canvas_runner.workflow_started.connect(self._on_workflow_started)
        self.canvas_runner.workflow_paused.connect(self._on_workflow_paused)
        self.canvas_runner.workflow_resumed.connect(self._on_workflow_resumed)
        self.canvas_runner.workflow_cancelled.connect(self._on_workflow_cancelled)
        self.canvas_runner.workflow_finished.connect(self._on_workflow_finished)
        self.canvas_runner.workflow_error.connect(self._on_workflow_error)
        # 节点信号
        self.canvas_runner.node_status_changed.connect(self.set_node_status_by_id)
        # 画布样式更改信号
        self.config.canvas_grid_mode.valueChanged.connect(self.ui_manager._setup_pipeline_style)
        self.config.canvas_pipelayout.valueChanged.connect(self.ui_manager._setup_pipeline_style)
        self.config.canvas_direction.valueChanged.connect(self.ui_manager._setup_pipeline_style)
        # 面板刷新信号
        self.canvas_runner.property_changed.connect(self.property_panel.update_properties)
        self.canvas_runner.node_vars_changed.connect(self.property_panel.refresh_node_vars_page)

    # 断开信号
    def _disconnect_signals(self):
        # 原有
        ComponentScanner.unregister_on_change(self.node_operations.register_components)
        ComponentScanner.unregister_on_change(self.nav_view.refresh_components)

        # 新增：断开 UI 按钮信号
        try:
            self.ui_manager.run_btn.clicked.disconnect(self.canvas_runner.run_workflow)
            self.ui_manager.pause_btn.clicked.disconnect(self._on_pause_resume_clicked)
            self.ui_manager.stop_btn.clicked.disconnect(self.canvas_runner.stop_workflow)
            self.ui_manager.save_btn.clicked.disconnect()
            self.ui_manager.export_model_btn.clicked.disconnect()
            self.ui_manager.close_btn.clicked.disconnect()
        except TypeError:
            pass  # 未连接则忽略

        # 断开 Runner 信号
        self.canvas_runner.workflow_started.disconnect(self._on_workflow_started)
        self.canvas_runner.workflow_paused.disconnect(self._on_workflow_paused)
        self.canvas_runner.workflow_resumed.disconnect(self._on_workflow_resumed)
        self.canvas_runner.workflow_cancelled.disconnect(self._on_workflow_cancelled)
        self.canvas_runner.workflow_finished.disconnect(self._on_workflow_finished)
        self.canvas_runner.workflow_error.disconnect(self._on_workflow_error)
        self.canvas_runner.node_status_changed.disconnect(self.set_node_status_by_id)
        self.canvas_runner.property_changed.disconnect()
        self.canvas_runner.node_vars_changed.disconnect()

        # 断开配置信号
        self.config.canvas_grid_mode.valueChanged.disconnect(self.ui_manager._setup_pipeline_style)
        self.config.canvas_pipelayout.valueChanged.disconnect(self.ui_manager._setup_pipeline_style)
        self.config.canvas_direction.valueChanged.disconnect(self.ui_manager._setup_pipeline_style)

        # 断开环境/变量信号
        try:
            self.env_combo.currentIndexChanged.disconnect(self.on_environment_changed)
            self.env_changed.disconnect(self.connect_kernel)
            self.global_variables_changed.disconnect(self._on_global_variables_changed)
        except TypeError:
            pass

    # --- 画布按键信号 ---
    def _canvas_key_press_event(self, event):
        focused_widget = QApplication.focusWidget()
        if focused_widget :
            if hasattr(focused_widget, 'code_editor'):
                # 是代码编辑器获得焦点
                QApplication.sendEvent(focused_widget.code_editor, event)
                return
            elif isinstance(focused_widget, (QTextEdit, QLineEdit)):
                QApplication.sendEvent(focused_widget, event)
                return


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

        super(NodeViewer, self.canvas_widget).keyPressEvent(event)

    def eventFilter(self, obj, event):
        if obj is self.graph.viewer() and event.type() == event.Resize:
            self.ui_manager.update_position()
        return super().eventFilter(obj, event)

    def center_to(self, nodes):
        if not isinstance(nodes, list):
            nodes = [nodes]
        self.graph.clear_selection()
        for node in nodes:
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
            try:
                node.status = status
            except:
                pass
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
        if not hasattr(node, "input_ports"):
            return
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
        QTimer.singleShot(100, lambda: self.property_panel.update_properties(None))

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
        self._disconnect_signals()
        self.ui_manager.destroy_all()
        # ===== 7. 销毁 UI 控件（确保 parent=None）=====
        self.graph.deleteLater()
        # 8. 发射信号 & 移除自身
        self.canvas_deleted.emit()
        self.parent.removeInterface(self)
        self.deleteLater()  # 关键：触发 Qt 对象销毁
