# -- coding: utf-8 --
import logging
import weakref
from typing import List, Optional, Dict, Any, Tuple

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QApplication
from PyQt5.QtCore import pyqtSignal, QObject

# 假设这些类依然存在
from app.widgets.custom_nodegraphqt.custom_nodegraph import CustomNodeGraph, CustomNodeViewer
from ..constants import PIPELINE_STYLE, PIPELINE_DIRECTION, GRID_STYLE

# 配置日志
logger = logging.getLogger(__name__)


class WorkflowCanvasManager(QWidget):
    """
    工作流画布管理器 (Widget)
    职责：
    1. 管理 QStackedWidget 中的多层画布
    2. 负责子图的创建、初始化（环境同步）、销毁
    3. 资源生命周期管理 (防止内存泄漏)
    """

    # 信号：当前活跃的 Graph 实例发生变化
    current_graph_changed = pyqtSignal(object)
    # 信号：路径发生变化，返回 list: [('0', 'Main'), ('1', 'Sub')...]
    navigation_changed = pyqtSignal(list)

    def __init__(self, parent_window):
        super().__init__(parent_window)
        # 使用 weakref 防止循环引用导致父窗口无法释放
        self._parent_window_ref = weakref.ref(parent_window)

        # 存储堆栈信息: [{'graph': instance, 'name': 'xxx', 'id': '0'}, ...]
        # 显式定义结构有助于代码提示
        self._graph_stack_data: List[Dict[str, Any]] = []

        self._init_ui()

    @property
    def parent_window(self):
        return self._parent_window_ref()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack_widget = QStackedWidget(self)
        layout.addWidget(self.stack_widget)

    def init_root_graph(self, root_graph: Optional[CustomNodeGraph] = None):
        """初始化根节点图"""
        if self._graph_stack_data:
            logger.warning("Root graph already initialized. Skipping.")
            return

        if root_graph is None:
            if not self.parent_window:
                logger.error("Parent window is dead, cannot create graph.")
                return
            root_graph = CustomNodeGraph(
                viewer=CustomNodeViewer(parent=self.parent_window),
                parent=self.parent_window
            )

        self._apply_style_to_graph(root_graph)
        self._add_graph_to_stack(root_graph, "Main Workflow", "0")

    def current_graph(self) -> Optional[CustomNodeGraph]:
        """获取当前显示的 Graph 实例"""
        if self._graph_stack_data:
            return self._graph_stack_data[-1]['graph']
        return None

    def create_sub_graph(self, name: str = "Untitled Subgraph") -> Optional[CustomNodeGraph]:
        """【核心功能】创建并进入子图"""
        if not self.parent_window:
            return None

        # 性能优化：在创建和配置过程中关闭 UI 更新，避免不必要的重绘
        self.setUpdatesEnabled(False)
        try:
            # 1. 实例化
            new_graph = CustomNodeGraph(
                viewer=CustomNodeViewer(parent=self.parent_window),
                parent=self.parent_window
            )

            # 2. 同步环境 (关键：错误处理)
            if not self._sync_environment(new_graph):
                logger.error("Failed to sync environment to new sub-graph.")
                # 即使同步失败，可能仍需继续，或者选择中断

            # 3. 计算 ID
            new_id = str(len(self._graph_stack_data))

            # 4. 加入堆栈
            self._add_graph_to_stack(new_graph, name, new_id)

            return new_graph
        except Exception as e:
            logger.exception(f"Error creating sub-graph: {e}")
            return None
        finally:
            self.setUpdatesEnabled(True)

    def switch_to_level(self, index: int):
        """跳转到指定层级，并安全销毁之后的层级"""
        if index < 0 or index >= len(self._graph_stack_data):
            logger.warning(f"Invalid level index: {index}")
            return

        # 性能优化：批量操作期间禁止界面刷新
        self.stack_widget.setUpdatesEnabled(False)
        try:
            target_info = self._graph_stack_data[index]
            target_graph = target_info['graph']

            # 1. 销毁之后的图层
            while len(self._graph_stack_data) > index + 1:
                self._pop_and_destroy_top_graph()

            # 2. 切换显示
            if self.stack_widget.currentWidget() != target_graph.widget:
                self.stack_widget.setCurrentWidget(target_graph.widget)

            # 3. 发送信号
            self._emit_updates()
        finally:
            self.stack_widget.setUpdatesEnabled(True)

    def _pop_and_destroy_top_graph(self):
        """安全地弹出并销毁栈顶的图"""
        if not self._graph_stack_data:
            return

        popped = self._graph_stack_data.pop()
        graph_instance: CustomNodeGraph = popped['graph']

        # 从 UI 移除
        self.stack_widget.removeWidget(graph_instance.widget)

        # 【安全关键】显式清理资源
        self._cleanup_graph_resources(graph_instance)

    def _cleanup_graph_resources(self, graph: CustomNodeGraph):
        """
        深度清理 Graph 资源
        """
        try:
            # 1. 断开该 Graph 对象发出的所有信号，防止回调到已删除对象
            # 注意：PyQt5 中 disconnect 可能会抛出异常如果未连接，需 try-catch
            try:
                if isinstance(graph, QObject):
                    graph.disconnect()
            except TypeError:
                pass  # 没有任何连接时可能报错

            # 2. 如果 NodeGraphQt 提供了 session 清理或 clear 方法，先调用
            # 这有助于移除 Scene 中的 Items
            if hasattr(graph, 'clear_session'):
                graph.clear_session()
            elif hasattr(graph, 'clear'):
                graph.clear()

            # 3. 销毁 Widget
            # deleteLater 会在事件循环回到主循环时清理，是安全的
            if hasattr(graph, 'widget') and graph.widget:
                graph.widget.deleteLater()

            # 4. 显式设为 None 帮助 GC
            graph = None

        except Exception as e:
            logger.error(f"Error cleaning up graph resources: {e}")

    def _add_graph_to_stack(self, graph: CustomNodeGraph, name: str, id_str: str):
        self.stack_widget.addWidget(graph.widget)
        self.stack_widget.setCurrentWidget(graph.widget)

        self._graph_stack_data.append({
            'graph': graph,
            'name': name,
            'id': id_str
        })

        self._emit_updates()

    def _emit_updates(self):
        """统一发送状态更新信号"""
        self.current_graph_changed.emit(self.current_graph())
        nav_data = [(item['id'], item['name']) for item in self._graph_stack_data]
        self.navigation_changed.emit(nav_data)

    def _sync_environment(self, target_graph: CustomNodeGraph) -> bool:
        """
        同步节点注册表和样式
        """
        if not self._graph_stack_data:
            return False

        base_graph = self._graph_stack_data[0]['graph']

        # 安全性优化：防御性获取 factory
        # 假设 NodeGraphQt 内部结构可能变化，这里做个检查
        factory = getattr(base_graph, '_node_factory', None)
        if not factory:
            logger.error("Could not find _node_factory in base graph.")
            return False

        # 1. 同步节点注册表
        # 直接访问 nodes 字典可能也是私有的，最好检查一下
        nodes_dict = getattr(factory, 'nodes', {})
        for alias, node_class in nodes_dict.items():
            # 避免重复注册警告
            try:
                target_graph.register_node(node_class, alias=alias)
            except Exception:
                pass  # 忽略已存在的注册

        # 2. 同步画布样式
        self._apply_style_to_graph(target_graph)

        return True

    def _apply_style_to_graph(self, graph: CustomNodeGraph):
        parent = self.parent_window
        if not parent or not hasattr(parent, 'config'):
            return

        config = parent.config
        try:
            # 增加 try-catch 防止枚举值对不上导致崩溃
            graph.set_grid_mode(GRID_STYLE.get(config.canvas_grid_mode.value))
            graph.set_pipe_style(PIPELINE_STYLE.get(config.canvas_pipelayout.value))
            graph.set_layout_direction(PIPELINE_DIRECTION.get(config.canvas_direction.value))
        except Exception as e:
            logger.warning(f"Failed to apply style config: {e}")

    def closeEvent(self, event):
        """窗口关闭时的清理"""
        logger.info("Closing WorkflowCanvasManager, cleaning up graphs...")
        # 从后往前销毁
        while self._graph_stack_data:
            self._pop_and_destroy_top_graph()
        super().closeEvent(event)