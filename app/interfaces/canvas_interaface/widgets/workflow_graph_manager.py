# -- coding: utf-8 --
import logging
import uuid
import weakref
from typing import List, Optional, Dict, Any, Set

from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

from app.widgets.custom_nodegraphqt.custom_nodegraph import CustomNodeGraph, CustomNodeViewer, GraphSplitter
from ..constants import PIPELINE_STYLE, PIPELINE_DIRECTION, GRID_STYLE

logger = logging.getLogger(__name__)


class WorkflowCanvasManager(QWidget):
    """
    工作流画布管理器 (Widget)
    职责：
    1. 管理 QStackedWidget 中的多层画布
    2. 为每个子图分配唯一ID并支持ID-based切换
    3. 负责子图的创建、初始化（环境同步）、销毁
    4. 资源生命周期管理 (防止内存泄漏)
    """

    # 信号：当前活跃的 Graph 实例发生变化
    current_graph_changed = pyqtSignal(object)
    # 信号：路径发生变化，返回 list: [('0', 'Main'), ('1', 'Sub')...]
    navigation_changed = pyqtSignal(list)
    # 新增信号：子图被销毁时触发 (id, name)
    graph_destroyed = pyqtSignal(str, str)
    graph_splitter = None

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self._parent_window_ref = weakref.ref(parent_window)

        # 核心数据结构优化：
        # 1. 栈式存储保持层级关系
        self._graph_stack_data: List[Dict[str, Any]] = []
        # 2. ID索引映射加速查找 (id -> stack_index)
        self._graph_id_index: Dict[str, int] = {}
        # 3. 活跃ID集合用于快速验证
        self._active_graph_ids: Set[str] = set()

        # 根图预分配固定ID，确保稳定性
        self._root_graph_id = "0"

        self._init_ui()

    @property
    def parent_window(self):
        return self._parent_window_ref()

    @property
    def current_graph_id(self) -> Optional[str]:
        """获取当前活跃子图的ID"""
        if self._graph_stack_data:
            return self._graph_stack_data[-1]['id']
        return None

    @property
    def all_graph_ids(self) -> List[str]:
        """获取所有活跃子图的ID列表（按栈顺序）"""
        return [item['id'] for item in self._graph_stack_data]

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack_widget = QStackedWidget(self)
        layout.addWidget(self.stack_widget)

    def init_root_graph(self, root_graph: Optional[CustomNodeGraph] = None):
        """初始化根节点图（固定ID为'0'）"""
        if self._graph_stack_data:
            logger.warning("Root graph already initialized. Skipping.")
            return

        if root_graph is None:
            if not self.parent_window:
                logger.error("Parent window is dead, cannot create graph.")
                return
            # 1. 创建视图分割器容器 (这将是实际显示在 UI 上的控件)
            self.graph_splitter = GraphSplitter(parent=self.parent_window)

            # 2. 创建主视角 (Master Viewer)
            # 注意：parent 依然传 parent_window，保证业务逻辑正常
            master_viewer = CustomNodeViewer(parent=self.parent_window)
            master_viewer._is_main = True
            # 3. 将主视角加入分割器
            self.graph_splitter.add_viewer(master_viewer)

            # 4. 初始化 Graph，依然绑定主视角
            # NodeGraphQt 的逻辑主要依赖一个 viewer 进行初始化
            root_graph = CustomNodeGraph(
                viewer=master_viewer,
                parent=self.parent_window,
                splitter=self.graph_splitter
            )
            root_graph.master_viewer = master_viewer
            master_viewer.graph = root_graph
        self._apply_style_to_graph(root_graph)
        self._add_graph_to_stack(root_graph, "Main Workflow", self._root_graph_id)

    def  current_graph(self) -> Optional[CustomNodeGraph]:
        """获取当前显示的 Graph 实例"""
        return self.get_graph_by_id(self.current_graph_id)

    def create_sub_graph(self, name: str = "Untitled Subgraph",
                         custom_id: Optional[str] = None) -> (str, Optional[CustomNodeGraph]):
        """
        【核心功能】创建并进入子图

        Args:
            name: 子图显示名称
            custom_id: 可选自定义ID（必须全局唯一），若未提供则自动生成

        Returns:
            创建的子图实例，失败返回None
        """
        if not self.parent_window:
            logger.error("Parent window is dead, cannot create sub-graph.")
            return None, None

        # 生成唯一ID（优先使用自定义ID，需验证唯一性）
        graph_id = custom_id or self._generate_unique_id()
        if graph_id in self._active_graph_ids:
            logger.error(f"Graph ID '{graph_id}' already exists. Cannot create duplicate ID.")
            return None, None

        self.setUpdatesEnabled(False)
        try:
            # 1. 实例化
            new_graph = CustomNodeGraph(
                viewer=CustomNodeViewer(parent=self.parent_window),
                parent=self.parent_window,
                splitter=self.graph_splitter
            )

            # 2. 同步环境
            if not self._sync_environment(new_graph):
                logger.warning("Partial environment sync completed for new sub-graph.")

            # 3. 加入堆栈（关键：先更新索引再添加到UI）
            self._add_graph_to_stack(new_graph, name, graph_id)

            logger.debug(f"Created sub-graph '{name}' with ID: {graph_id}")
            return graph_id, new_graph

        except Exception as e:
            logger.exception(f"Critical error creating sub-graph '{name}': {e}")
            return None, None
        finally:
            self.setUpdatesEnabled(True)

    def switch_to_graph_by_id(self, graph_id: str, destroy_intermediates: bool = False) -> bool:
        """
        根据子图ID切换视图

        Args:
            graph_id: 目标子图的唯一ID
            destroy_intermediates: 是否销毁目标层级之上的子图（默认True）

        Returns:
            切换成功返回True，失败返回False
        """
        if graph_id not in self._graph_id_index:
            logger.warning(f"Graph with ID '{graph_id}' not found in active stack.")
            return False

        target_index = self._graph_id_index[graph_id]

        # 性能优化：批量操作期间禁止界面刷新
        self.stack_widget.setUpdatesEnabled(False)
        try:
            # 销毁中间层级（如果需要）
            if destroy_intermediates and len(self._graph_stack_data) > target_index + 1:
                self._destroy_graphs_above_level(target_index)

            # 切换显示
            target_graph = self._graph_stack_data[target_index]['graph']
            if self.stack_widget.currentWidget() != target_graph.widget:
                self.stack_widget.setCurrentWidget(target_graph.widget)

            # 仅当实际切换了层级时才发送信号
            if target_index != len(self._graph_stack_data) - 1:
                self._emit_updates()

            logger.debug(f"Switched to graph '{self._graph_stack_data[target_index]['name']}' (ID: {graph_id})")
            return True

        except Exception as e:
            logger.exception(f"Error switching to graph ID '{graph_id}': {e}")
            return False
        finally:
            self.stack_widget.setUpdatesEnabled(True)

    def switch_to_level(self, index: int, destroy_intermediates: bool = False) -> bool:
        """
        跳转到指定层级（兼容旧接口）

        Args:
            index: 目标层级索引（0=根图）
            destroy_intermediates: 是否销毁目标层级之上的子图

        Returns:
            切换成功返回True
        """
        if index < 0 or index >= len(self._graph_stack_data):
            logger.warning(f"Invalid level index: {index} (valid range: 0-{len(self._graph_stack_data) - 1})")
            return False

        target_id = self._graph_stack_data[index]['id']
        return self.switch_to_graph_by_id(target_id, destroy_intermediates)

    def _destroy_graphs_above_level(self, target_index: int):
        """安全销毁目标层级之上的所有子图"""
        while len(self._graph_stack_data) > target_index + 1:
            self._pop_and_destroy_top_graph()

    def _pop_and_destroy_top_graph(self):
        """安全地弹出并销毁栈顶的图"""
        if not self._graph_stack_data:
            return

        popped = self._graph_stack_data.pop()
        graph_id = popped['id']
        graph_name = popped['name']
        graph_instance: CustomNodeGraph = popped['graph']

        # 从索引中移除
        self._graph_id_index.pop(graph_id, None)
        self._active_graph_ids.discard(graph_id)

        # 从 UI 移除
        if graph_instance.widget and self.stack_widget.indexOf(graph_instance.widget) >= 0:
            self.stack_widget.removeWidget(graph_instance.widget)

        # 清理资源
        self._cleanup_graph_resources(graph_instance)

        # 发出销毁信号
        self.graph_destroyed.emit(graph_id, graph_name)
        logger.debug(f"Destroyed graph '{graph_name}' (ID: {graph_id})")

    def _cleanup_graph_resources(self, graph: CustomNodeGraph):
        """深度清理 Graph 资源"""
        try:
            # 1. 断开信号连接
            try:
                if isinstance(graph, QObject):
                    graph.disconnect()
            except (TypeError, RuntimeError):
                pass  # 忽略无连接或对象已销毁的情况

            # 2. 清理会话数据
            if hasattr(graph, 'clear_session'):
                graph.clear_session()
            elif hasattr(graph, 'clear'):
                graph.clear()

            # 3. 安全销毁Widget
            if hasattr(graph, 'widget') and graph.widget:
                try:
                    graph.widget.setParent(None)
                    graph.widget.deleteLater()
                except RuntimeError:
                    pass  # Widget可能已被销毁

            # 4. 清理引用
            graph._viewer = None
            graph._model = None

        except Exception as e:
            logger.error(f"Error during graph cleanup: {e}", exc_info=True)

    def _add_graph_to_stack(self, graph: CustomNodeGraph, name: str, graph_id: str):
        """将图添加到管理栈（内部方法）"""
        # 更新索引结构
        stack_index = len(self._graph_stack_data)
        self._graph_id_index[graph_id] = stack_index
        self._active_graph_ids.add(graph_id)

        # 添加到UI
        self.stack_widget.addWidget(self.graph_splitter)
        self.stack_widget.setCurrentWidget(self.graph_splitter)

        # 添加到数据栈
        self._graph_stack_data.append({
            'graph': graph,
            'name': name,
            'id': graph_id
        })

        self._emit_updates()
        logger.debug(f"Added graph to stack: ID={graph_id}, name='{name}', index={stack_index}")

    def _emit_updates(self):
        """统一发送状态更新信号"""
        # 更新索引映射（重建以确保准确性）
        self._graph_id_index = {
            item['id']: idx
            for idx, item in enumerate(self._graph_stack_data)
        }

        self.current_graph_changed.emit(self.current_graph())
        nav_data = [(item['id'], item['name']) for item in self._graph_stack_data]
        self.navigation_changed.emit(nav_data)

    def _sync_environment(self, target_graph: CustomNodeGraph) -> bool:
        """同步节点注册表和样式"""
        if not self._graph_stack_data:
            logger.error("No base graph available for environment sync")
            return False

        base_graph = self._graph_stack_data[0]['graph']
        factory = getattr(base_graph, '_node_factory', None)

        if not factory:
            logger.error("Base graph missing _node_factory for sync")
            return False

        # 同步节点类型注册
        nodes_dict = getattr(factory, 'nodes', {})
        registered_count = 0
        for alias, node_class in nodes_dict.items():
            try:
                target_graph.register_node(node_class, alias=alias)
                registered_count += 1
            except Exception as e:
                logger.debug(f"Node '{alias}' already registered or failed: {e}")

        # 同步画布样式
        self._apply_style_to_graph(target_graph)

        logger.debug(f"Synced {registered_count} node types to new sub-graph")
        return True

    def _apply_style_to_graph(self, graph: CustomNodeGraph):
        """应用画布样式配置"""
        parent = self.parent_window
        if not parent or not hasattr(parent, 'config'):
            return

        config = parent.config
        try:
            graph.set_grid_mode(GRID_STYLE.get(config.canvas_grid_mode.value, 0))
            graph.set_pipe_style(PIPELINE_STYLE.get(config.canvas_pipelayout.value, 0))
            graph.set_layout_direction(PIPELINE_DIRECTION.get(config.canvas_direction.value, 0))
        except Exception as e:
            logger.warning(f"Partial style application failed: {e}")

    def _generate_unique_id(self) -> str:
        """生成全局唯一子图ID（使用短UUID避免数字冲突）"""
        # 优先尝试数字ID保持可读性，冲突时回退到UUID
        candidate_id = str(len(self._graph_stack_data))
        if candidate_id not in self._active_graph_ids:
            return candidate_id

        # 生成短UUID（8字符）
        return uuid.uuid4().hex[:8]

    def get_graph_by_id(self, graph_id: str) -> Optional[CustomNodeGraph]:
        """通过ID安全获取子图实例（不触发视图切换）"""
        index = self._graph_id_index.get(graph_id)
        if index is not None and index < len(self._graph_stack_data):
            return self._graph_stack_data[index]['graph']
        return None

    def get_graph_info(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """获取子图元数据（ID、名称、层级索引）"""
        index = self._graph_id_index.get(graph_id)
        if index is not None and index < len(self._graph_stack_data):
            item = self._graph_stack_data[index].copy()
            item['level_index'] = index
            return item
        return None

    def closeEvent(self, event):
        """窗口关闭时的清理"""
        logger.info("Closing WorkflowCanvasManager, cleaning up all graphs...")
        # 从后往前销毁所有子图
        while self._graph_stack_data:
            self._pop_and_destroy_top_graph()
        super().closeEvent(event)