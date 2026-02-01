# -- coding: utf-8 --
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget
from PyQt5.QtCore import pyqtSignal

from app.widgets.custom_nodegraphqt.custom_nodegraph import CustomNodeGraph, CustomNodeViewer
from ..constants import PIPELINE_STYLE, PIPELINE_DIRECTION, GRID_STYLE


class WorkflowCanvasManager(QWidget):
    """
    工作流画布管理器 (Widget)
    职责：
    1. 管理 QStackedWidget 中的多层画布
    2. 负责子图的创建、初始化（环境同步）、销毁
    3. 提供信号通知外部更新 UI (如面包屑)
    """

    # 信号：当前活跃的 Graph 实例发生变化（用于通知主窗口更新 self.graph 引用）
    current_graph_changed = pyqtSignal(object)
    # 信号：路径发生变化（用于更新面包屑），返回 list: [('0', 'Main'), ('1', 'Sub')...]
    navigation_changed = pyqtSignal(list)

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window  # NodeEditor 主窗口引用

        # 存储堆栈信息: [{'graph': instance, 'name': 'xxx', 'id': '0'}, ...]
        self._graph_stack_data = []

        self._init_ui()

    def _init_ui(self):
        # 布局初始化
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 核心堆栈容器
        self.stack_widget = QStackedWidget(self)
        layout.addWidget(self.stack_widget)

    def init_root_graph(self, root_graph=None):
        """初始化根节点图"""
        if self._graph_stack_data:
            return  # 防止重复初始化

        # 如果没有传入 root_graph，则内部创建一个
        if root_graph is None:
            root_graph = CustomNodeGraph(
                viewer=CustomNodeViewer(parent=self.parent_window),
                parent=self.parent_window
            )

        # 即使是根图，也最好应用一次样式配置
        self._apply_style_to_graph(root_graph)

        self._add_graph_to_stack(root_graph, "主工作流", "0")

    def current_graph(self):
        """获取当前显示的 Graph 实例"""
        if self._graph_stack_data:
            return self._graph_stack_data[-1]['graph']
        return None

    def create_sub_graph(self, name="未命名子图"):
        """【核心功能】创建并进入子图"""
        # 1. 实例化新图 (注意 viewer 的 parent 仍为主窗口，以便弹窗正常)
        new_graph = CustomNodeGraph(
            viewer=CustomNodeViewer(parent=self.parent_window),
            parent=self.parent_window
        )

        # 2. 同步环境配置 (解决无法操作的问题)
        self._sync_environment(new_graph)

        # 3. 计算新 ID
        new_id = str(len(self._graph_stack_data))

        # 4. 加入堆栈并显示
        self._add_graph_to_stack(new_graph, name, new_id)

        return new_graph

    def switch_to_level(self, index):
        """跳转到指定层级，并销毁之后的层级"""
        if index < 0 or index >= len(self._graph_stack_data):
            return

        target_info = self._graph_stack_data[index]
        target_graph = target_info['graph']

        # 1. 销毁之后的图层 (从栈顶开始弹出，直到剩下 index+1 个)
        while len(self._graph_stack_data) > index + 1:
            popped = self._graph_stack_data.pop()
            graph_instance = popped['graph']

            # 从 UI 移除
            self.stack_widget.removeWidget(graph_instance.widget)
            # 标记删除，释放内存
            graph_instance.widget.deleteLater()
            # 如果 NodeGraphQt 有显式关闭方法，也可以在这里调用

        # 2. 切换显示
        self.stack_widget.setCurrentWidget(target_graph.widget)

        # 3. 发送信号
        self._emit_updates()

    def _add_graph_to_stack(self, graph, name, id_str):
        """内部通用添加逻辑"""
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
        # 通知主窗口当前 Graph 变了
        self.current_graph_changed.emit(self.current_graph())

        # 通知面包屑更新数据
        nav_data = [(item['id'], item['name']) for item in self._graph_stack_data]
        self.navigation_changed.emit(nav_data)

    def _sync_environment(self, target_graph):
        """
        【关键】将主图的节点注册表和样式同步给新图
        没有这一步，新图就是一张白纸，无法创建节点
        """
        if not self._graph_stack_data: return
        base_graph = self._graph_stack_data[0]['graph']

        # 1. 同步节点注册表 (Factory)
        factory = base_graph._node_factory
        for alias, node_class in factory.nodes.items():
            target_graph.register_node(node_class, alias=alias)

        # 2. 同步画布样式
        self._apply_style_to_graph(target_graph)

    def _apply_style_to_graph(self, graph):
        """应用全局样式配置"""
        if not hasattr(self.parent_window, 'config'): return
        config = self.parent_window.config

        graph.set_grid_mode(GRID_STYLE.get(config.canvas_grid_mode.value))
        graph.set_pipe_style(PIPELINE_STYLE.get(config.canvas_pipelayout.value))
        graph.set_layout_direction(PIPELINE_DIRECTION.get(config.canvas_direction.value))