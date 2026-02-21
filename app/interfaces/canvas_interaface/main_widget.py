# -*- coding: utf-8 -*-
import re
import shutil
from pathlib import Path

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QThreadPool, QPoint, QTimer
from PyQt5.QtWidgets import QWidget
from loguru import logger

from app.interfaces.canvas_interaface.constants import TEMPLATE_START_SIZES
from app.interfaces.canvas_interaface.llm_context import LLMContextProvider
from app.interfaces.canvas_interaface.utils.auto_saver import AutoSaver
from app.interfaces.canvas_interaface.utils.canvas_io import CanvasIO
from app.interfaces.canvas_interaface.utils.canvas_runner import CanvasRunner
from app.interfaces.canvas_interaface.utils.exporter import CanvasExporter
from app.interfaces.canvas_interaface.utils.node_operations import NodeOperations
from app.interfaces.canvas_interaface.utils.quick_component_manager import QuickComponentManager
from app.interfaces.canvas_interaface.utils.environment_manager import EnvironmentManager
from app.interfaces.canvas_interaface.utils.message_manager import MessageManager
from app.interfaces.canvas_interaface.widgets.ui_setup import CanvasUISetUp
from app.nodes.backdrop_node import ControlFlowBackdrop
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.status_node import NodeStatus
from app.scan_components import ComponentScanner
from app.trigger_plugins.base_trigger import ALL_MANAGERS
from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.basic_widget.category_filter import CategoryFilterDialog


class CanvasPage(QWidget):
    canvas_deleted = pyqtSignal()
    canvas_saved = pyqtSignal(Path)
    global_variables_changed = pyqtSignal(str, str)  # 用于刷新组件中的变量下拉菜单
    env_changed = pyqtSignal(str)

    def __init__(self, parent=None, object_name: Path = None, manager=None):
        super().__init__()
        # --- 第一阶段：基础数据准备 (必须同步) ---
        self.parent = parent
        self.manager = manager
        self.file_path = object_name
        # 国际化工作流名称
        self.workflow_name = ".".join(object_name.stem.split(".")[:-1]) if object_name else self.tr("未命名工作流")
        self.setObjectName('canvas_page' if object_name is None else str(object_name))
        self.config = Settings.get_instance()
        self._pending_property_update = None
        # 线程池
        self.thread_pool = QThreadPool.globalInstance()
        # --- 第二阶段：UI 框架搭建 (视觉先行) ---
        # 初始化 UI 管理器并构建布局
        self.ui_manager = CanvasUISetUp(self)
        self.ui_manager.setup_ui()

        # 节点注册
        # 1. 节点操作与注册
        self.node_operations = NodeOperations(self, self.graph, self.manager.recommendation_engine,
                                              QThreadPool.globalInstance())
        # 异步注册或分批注册节点
        self.node_operations.register_components()
        self.canvas_widget = self.graph.viewer()

        # 全局变量与基础 IO 工具
        self.canvas_io = CanvasIO(self.graph, self.global_variables, self)

    def _deferred_initialization(self):
        # 1. 环境管理
        self.environment_manager = EnvironmentManager(self)

        # 2. 运行控制逻辑
        self.canvas_runner = CanvasRunner(self)

        # 3. 辅助工具
        self.quick_manager = QuickComponentManager(self, self.component_map)
        self._auto_saver = AutoSaver(self, self.config)

        # 4. LLM 上下文 (这个通常涉及大量对象绑定，延迟处理)
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
        self._connect_signals()
        self.node_operations.setup_context_menu()

    @property
    def run_strategies(self):
        return {
            "从此处运行": self.canvas_runner.run_from,
            "运行到此处": self.canvas_runner.run_to,
            "运行所在子图": self.canvas_runner.run_subgraph,
            "运行所有节点": self.canvas_runner.run_full
        }

    @property
    def graph(self):
        return self.ui_manager.canvas_manager.current_graph()

    @property
    def global_variables(self):
        return self.graph.global_variables

    @property
    def node_created(self):
        return self.graph.node_created

    @property
    def nav_panel(self):
        return self.ui_manager.nav_panel

    @property
    def dependency_checker(self):
        return self.ui_manager.dependency_checker

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
    def node_type_map(self):
        return self.node_operations.node_type_map

    @property
    def node_uuid_map(self):
        return self.node_operations.node_uuid_map

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
    def template_manager(self):
        return self.ui_manager.nav_panel.template_container

    @property
    def ipython_kernel(self):
        return self.ui_manager.ipython_console

    @property
    def selected_categories(self):
        return self.ui_manager.nav_view._selected_categories

    @property
    def log_window(self):
        return self.ui_manager.log_window

    @property
    def execution_record(self):
        return self.ui_manager.execution_record

    @property
    def side_dock_area(self):
        return self.ui_manager.side_dock_area

    @property
    def node_doc(self):
        return self.ui_manager.node_doc

    @property
    def scheduler(self):
        return self.canvas_runner._scheduler

    @property
    def env_data(self):
        return self.environment_manager.env_data

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
            if hasattr(node, "rename_variable"):
                node.rename_variable(
                    old_names + [input_proxy_old_name], new_names + [input_proxy_new_name]
                )

    def show_category_dialog(self, categories, tag):
        pos = tag.mapToGlobal(QPoint(0, 0))
        category_filter_dialog = CategoryFilterDialog(self, categories)
        category_filter_dialog.categories_changed.connect(
            self.ui_manager.nav_panel.draggable_tree._on_categories_changed)
        category_filter_dialog.show_at(pos)

    def add_template(self):
        self.ui_manager.nav_panel.template_container.add_template()

    def _on_global_variables_changed(self, var_type: str, var_name: str, action: str):
        self.property_panel._on_global_variables_changed(var_type, var_name, action)

    def show_splitter(self):
        self.ui_manager.show_splitter()

    def hide_splitter(self):
        self.ui_manager.hide_splitter()

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
            # LLM prompt 通常保持业务逻辑，但UI反馈可国际化
            question = self.tr("历史对话上下文：{}\n\n你的任务是结合历史信息生成这个 {} 组件的代码").format(
                self.ui_manager.llm_chatter.session_manager.get_current_session().messages,
                content
            )
            self.parent.switchTo(self.parent.develop_page)
            self.parent.develop_page.llm_context_provider.send_preset_generate_llm_request(question)

    def select_node_by_name(self, name_list, *args):
        if name_list is None:
            return
        return self.node_operations.select_nodes_by_name(name_list)

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
        QTimer.singleShot(0, self._deferred_initialization)

    def create_next_node(self, key, icon_path=None):
        self.node_operations.create_next_node(key, icon_path)

    def create_group_node(self):
        self.node_operations.create_group_node()

    def create_backdrop_node(self, key, init_io=True):
        self.node_operations.create_backdrop_node(key, init_io)

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
        self.pause_btn.setIcon(get_icon("暂停"))
        self.ui_manager.update_position(True)
        self.pause_btn.setToolTip(self.tr("暂停工作流"))

    def _on_workflow_paused(self):
        """进入暂停：pause 按钮变为 resume"""
        self.pause_btn.setIcon(get_icon("绿色运行"))
        self.pause_btn.setToolTip(self.tr("继续工作流"))

    def _on_workflow_resumed(self):
        """恢复执行：pause 按钮变回 pause"""
        self.pause_btn.setIcon(get_icon("暂停"))
        self.pause_btn.setToolTip(self.tr("暂停工作流"))

    def _on_workflow_cancelled(self):
        """停止/取消：恢复 run 按钮"""
        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()
        self.ui_manager.update_position(True)

    def _on_workflow_finished(self):
        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()
        self.ui_manager.update_position(True)

    def _on_workflow_error(self, msg=""):
        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()
        self.ui_manager.update_position(True)

    def on_node_error_simple(self, node_id):
        node = self.node_operations._get_node_by_id_cached(node_id)
        if node:
            node._output_values = {}
            # 国际化错误弹窗
            title = self.tr("错误")
            content = self.tr('节点 "{}" 执行失败！').format(node.name())
            MessageManager.error(title, content, self)
            QtCore.QTimer.singleShot(0, lambda: self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED))

        self.run_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()
        self.ui_manager.update_position(True)

    def on_node_started_simple(self, node_id):
        node = self.node_operations._get_node_by_id_cached(node_id)
        if node:
            QtCore.QTimer.singleShot(0, lambda: self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING))

    def _connect_signals(self):
        """连接调度器信号到 UI 回调"""
        # 界面刷新信号
        self.ui_manager.connect_signals()
        self.graph.node_created.connect(self.node_operations.on_node_created)
        self.graph.node_double_clicked.connect(self.node_operations.on_node_double_clicked)
        self.graph.port_connected.connect(self._on_port_connected)
        self.graph.node_selection_changed.connect(
            lambda: QtCore.QTimer.singleShot(0, self.on_selection_changed)
        )
        self.ui_manager.log_window.cardDoubleClicked.connect(self.node_operations.select_nodes_by_name)
        self.quick_manager.quick_components_changed.connect(self.ui_manager._refresh_quick_buttons)
        self.canvas_io.canvas_loaded.connect(self.environment_manager.load_env_combos)
        # 连接自动组件同步刷新信号
        ComponentScanner.register_on_change(self.nav_view.refresh_components)
        ComponentScanner.register_on_change(self.node_operations.register_components, False)
        # 画布上按钮信号
        self.ui_manager.run_btn.clicked.connect(self.canvas_runner.run_workflow)
        self.ui_manager.pause_btn.clicked.connect(self._on_pause_resume_clicked)
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
        self.config.canvas_auto_collapse.valueChanged.connect(self.ui_manager._setup_pipeline_style)
        # 面板刷新信号
        self.canvas_runner.property_changed.connect(self.property_panel.update_properties)
        self.canvas_runner.node_vars_changed.connect(self.property_panel.refresh_node_vars_page)

    # 断开信号
    def _disconnect_signals(self):
        ComponentScanner.unregister_on_change(self.node_operations.register_components)
        ComponentScanner.unregister_on_change(self.nav_view.refresh_components)

        try:
            self.ui_manager.run_btn.clicked.disconnect(self.canvas_runner.run_workflow)
            self.ui_manager.pause_btn.clicked.disconnect(self._on_pause_resume_clicked)
            self.ui_manager.stop_btn.clicked.disconnect(self.canvas_runner.stop_workflow)
            self.ui_manager.save_btn.clicked.disconnect()
            self.ui_manager.export_model_btn.clicked.disconnect()
            self.ui_manager.close_btn.clicked.disconnect()
            self.graph.disconnect()
        except TypeError:
            pass
        try:
            self.canvas_runner.workflow_paused.disconnect(self._on_workflow_paused)
            self.canvas_runner.workflow_resumed.disconnect(self._on_workflow_resumed)
            self.canvas_runner.workflow_cancelled.disconnect(self._on_workflow_cancelled)
            self.canvas_runner.workflow_finished.disconnect(self._on_workflow_finished)
            self.canvas_runner.workflow_error.disconnect(self._on_workflow_error)
            self.canvas_runner.node_status_changed.disconnect(self.set_node_status_by_id)
            self.canvas_runner.workflow_started.disconnect(self._on_workflow_started)
            self.canvas_runner.property_changed.disconnect()
            self.canvas_runner.node_vars_changed.disconnect()
        except TypeError:
            pass

        try:
            self.config.canvas_grid_mode.valueChanged.disconnect(self.ui_manager._setup_pipeline_style)
            self.config.canvas_pipelayout.valueChanged.disconnect(self.ui_manager._setup_pipeline_style)
            self.config.canvas_direction.valueChanged.disconnect(self.ui_manager._setup_pipeline_style)
            self.env_combo.currentIndexChanged.disconnect(self.on_environment_changed)
            self.global_variables_changed.disconnect(self._on_global_variables_changed)
        except TypeError:
            pass

    # --- 画布按键信号 ---

    def center_to(self, nodes):
        if not isinstance(nodes, list):
            nodes = [nodes]
        self.graph.clear_selection()
        for node in nodes:
            if node not in self.graph.all_nodes():
                MessageManager.warning(self.tr("错误"), self.tr("原节点不存在！"), self)
                return
            node.set_selected(True)
        self.graph.fit_to_selection()

    def set_node_status(self, node, status):
        if hasattr(node, 'status'):
            try:
                node.status = status
            except:
                pass
        self._highlight_node_connections(node, status)
        if status == NodeStatus.NODE_STATUS_SUCCESS:
            self.on_node_finished_simple(node)

    def _highlight_node_connections(self, node, status):
        """优化的连接线高亮方法"""
        viewer = self.graph.viewer()

        # 状态判断：是否处于运行中
        # 假设你的 NodeStatus 定义中包含 NODE_STATUS_RUNNING
        is_running = (status == NodeStatus.NODE_STATUS_RUNNING)
        if not hasattr(node, "input_ports"):
            return
        # 1. 先处理输入端口
        for port in node.input_ports():
            for connected_port in port.connected_ports():
                # 找到连接线：注意参数顺序 (源端口, 目标端口)
                # 输入端口的连接，源通常是对方的输出端口
                pipe = self._find_pipe_by_ports(connected_port, port, viewer.all_pipes())
                if pipe:
                    if is_running:
                        pipe.running(type="input")
                    else:
                        if hasattr(pipe, 'reset'):
                            pipe.reset()

        # 2. 再处理输出端口
        for port in node.output_ports():
            for connected_port in port.connected_ports():
                # 输出端口的连接，源是自己
                pipe = self._find_pipe_by_ports(port, connected_port, viewer.all_pipes())
                if pipe:
                    if is_running:
                        pipe.running(type="output")
                    else:
                        if hasattr(pipe, 'reset'):
                            pipe.reset()

    def _find_pipe_by_ports(self, out_port, in_port, pipes):
        """根据输入输出端口查找对应的连接线"""
        for pipe in pipes:
            if pipe.output_port == out_port.view and pipe.input_port == in_port.view:
                return pipe
        return None

    def on_node_finished_simple(self, node):
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

        # 1. 快速退出：无选中
        if not selected_nodes:
            self.nav_view.clear_recommendations()
            self.property_panel.reset_current_components()
            self._schedule_property_update(None)
            return

        # 2. 分类节点：找出 Backdrop 和其他节点
        # 使用 set 提高后续查找速度
        selected_set = set(selected_nodes)
        backdrops = [n for n in selected_nodes if isinstance(n, ControlFlowBackdrop)]

        # 3. 收集所有被选中 Backdrop 的内部节点
        # 使用 set 存储内部节点，查找复杂度从 O(N) 降为 O(1)
        all_backdrop_internals = set()
        for bd in backdrops:
            # 假设 bd.nodes() 返回的是列表或迭代器
            all_backdrop_internals.update(bd.nodes())

        # 4. 判断 "仅选中 Backdrop 模式"
        target_backdrop_update = None

        if backdrops:
            # 只有当选中了 Backdrop 时才进行此复杂判断
            for bd in backdrops:
                bd_internals = set(bd.nodes())
                # 检查：是否所有非当前Backdrop的选中节点，实际上都是这个Backdrop的子节点
                remaining_selection = selected_set - {bd}
                if remaining_selection and remaining_selection.issubset(bd_internals):
                    target_backdrop_update = bd
                    break

        if target_backdrop_update:
            # 命中特殊逻辑：只显示 Backdrop 属性
            self.nav_view.clear_recommendations()
            self._schedule_property_update(target_backdrop_update)
            self.property_panel.reset_current_components()
            return

        # 5. 常规逻辑：过滤掉作为"内部节点"被连带选中的节点
        # 使用集合差集高效过滤：保留那些 "不是任何选中Backdrop的子节点" 的节点
        top_level_nodes = [n for n in selected_nodes if n not in all_backdrop_internals]
        # 6. 根据过滤后的顶层节点数量处理
        if len(top_level_nodes) > 1:
            self.nav_view.clear_recommendations()  # 多选时不显示推荐
            self._schedule_property_update(top_level_nodes)

        elif len(top_level_nodes) == 1:
            node = top_level_nodes[0]
            if isinstance(node, BasicNodeWithGlobalProperty):
                self._schedule_property_update(node)
                self.property_panel.reset_current_components()
                # 避免框选过程中快速划过节点时频繁触发 IO/LLM 计算
                if hasattr(self, "_recommendation_timer"):
                    self._recommendation_timer.stop()
                else:
                    self._recommendation_timer = QTimer()
                    self._recommendation_timer.setSingleShot(True)
                    self._recommendation_timer.timeout.connect(
                        lambda: self.node_operations._request_recommendations(node))

                self._recommendation_timer.start(50)  # 50ms 延迟
            else:
                self.nav_view.clear_recommendations()
                self.property_panel.reset_current_components()
                self._schedule_property_update(None)
        else:
            # 这种情况可能是只选了内部节点但没选父 Backdrop，或者被全部过滤了
            self.nav_view.clear_recommendations()
            self.property_panel.reset_current_components()
            self._schedule_property_update(None)

    def _delayed_fit_view(self):
        self.graph._viewer.zoom_to_nodes(self.graph._viewer.all_nodes())
        # self.property_panel.set_allowed_update(True)
        QTimer.singleShot(100, lambda: self.property_panel.update_properties(None))

    def _undo(self):
        try:
            if self.graph.undo_stack().canUndo():
                self.graph.undo_stack().undo()
            else:
                MessageManager.info(self.tr("提示"), self.tr("没有可撤销的操作"), self)
        except Exception as e:
            logger.warning(self.tr("撤销失败: {}").format(e))

    def _redo(self):
        try:
            if self.graph.undo_stack().canRedo():
                self.graph.undo_stack().redo()
            else:
                MessageManager.info(self.tr("提示"), self.tr("没有可重做的操作"), self)
        except Exception as e:
            logger.warning(self.tr("重做失败: {}").format(e))

    def _auto_layout_selected(self, graph, node=None):
        selected = self.graph.selected_nodes()
        if selected:
            self.graph.auto_layout_nodes(nodes=selected, start_nodes=[node] if node else None)
        else:
            self.graph.auto_layout_nodes(nodes=self.graph.all_nodes(), start_nodes=[node] if node else None)

    # --- 画布关闭逻辑 ---
    def close_current_canvas(self):
        try:
            if not self.file_path.exists():
                self.clean_canvas()

            # 清除注册的触发器
            for manager in ALL_MANAGERS:
                try:
                    manager.remove_by_canvas(self.workflow_name)
                except Exception as e:
                    logger.exception(f"清理管理器 {manager.manager_name} 失败: {e}")
        # 定时器关闭
            self._auto_saver.stop()
            self.ipython_kernel.stop_kernel()
            self._disconnect_signals()
            self.ui_manager.destroy_all()
            self.canvas_runner.stop_workflow()
            self.graph.deleteLater()
            self.canvas_deleted.emit()
            self.parent.removeInterface(self)
            self.deleteLater()
        except:
            logger.exception("关闭画布时发生错误")

    def clean_canvas(self):
        def cleanup_task():
            base_path = self.file_path.parent
            if base_path.exists():
                shutil.rmtree(base_path)

        self.thread_pool.start(cleanup_task)