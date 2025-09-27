"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: workflow.py
@time: 2025/9/26 14:21
@desc: 
"""
from collections import deque, defaultdict

from NodeGraphQt import NodeGraph
from PyQt5.QtCore import Qt, QThreadPool
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QTreeWidgetItem
from qfluentwidgets import (
    FluentWindow, setTheme, Theme, FluentIcon as FIF, ToolButton, MessageBox, InfoBar,
    InfoBarPosition
)

from app.nodes.create_dynamic_node import create_node_class
from app.nodes.status_node import NodeStatus, StatusNode
from app.scan_components import scan_components
from app.utils.threading_utils import NodeListExecutor, Worker
from app.utils.utils import get_port_node
from app.widgets.draggable_component_tree import DraggableTreeWidget
from app.widgets.property_panel import PropertyPanel


# ----------------------------
# 主窗口
# ----------------------------
class LowCodeWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        setTheme(Theme.DARK)
        from PyQt5.QtWidgets import QDesktopWidget
        screen_rect = QDesktopWidget().screenGeometry()
        screen_width, screen_height = screen_rect.width(), screen_rect.height()
        self.window_width = int(screen_width * 0.6)
        self.window_height = int(screen_height * 0.75)
        self.resize(self.window_width, self.window_height)

        # 初始化线程池
        self.threadpool = QThreadPool()
        print(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")

        # 扫描组件
        self.component_map = scan_components()

        # 初始化状态存储
        self.node_results = {}
        self.node_status = {}  # {node_id: status}

        # 初始化 NodeGraph
        self.graph = NodeGraph()

        # 动态注册所有组件
        self.node_type_map = {}

        for full_path, comp_cls in self.component_map.items():
            safe_name = full_path.replace("/", "_").replace(" ", "_").replace("-", "_")
            node_class = create_node_class(comp_cls)
            # 继承 StatusNode 以支持状态显示
            node_class = type(f"Status{node_class.__name__}", (StatusNode, node_class), {})
            node_class.__name__ = f"StatusDynamicNode_{safe_name}"
            self.graph.register_node(node_class)
            self.node_type_map[full_path] = f"dynamic.{node_class.__name__}"

        self.canvas_widget = self.graph.viewer()

        # 组件面板 - 使用可拖拽的树
        self.nav_view = DraggableTreeWidget(self)
        self.nav_view.setHeaderHidden(True)
        self.nav_view.setFixedWidth(200)
        self.nav_view.set_component_map(self.component_map)  # 设置组件映射用于预览
        self.build_component_tree(self.component_map)

        # 属性面板
        self.property_panel = PropertyPanel(self)

        # 布局（移除日志面板）
        central_widget = QWidget()
        central_widget.setObjectName('central_widget')
        main_layout = QVBoxLayout(central_widget)
        canvas_layout = QHBoxLayout()
        canvas_layout.addWidget(self.nav_view)
        canvas_layout.addWidget(self.canvas_widget, 1)
        canvas_layout.addWidget(self.property_panel, 0, Qt.AlignRight)
        main_layout.addLayout(canvas_layout)
        self.addSubInterface(central_widget, FIF.APPLICATION, 'Canvas')

        # 创建悬浮按钮
        self.create_floating_buttons()

        # 信号连接
        scene = self.graph.viewer().scene()
        scene.selectionChanged.connect(self.on_selection_changed)

        # 启用画布的拖拽放置
        self.canvas_widget.setAcceptDrops(True)
        self.canvas_widget.dragEnterEvent = self.canvas_drag_enter_event
        self.canvas_widget.dropEvent = self.canvas_drop_event

        # ✅ 启用右键菜单（关键步骤）
        self._setup_context_menus()

    def create_floating_buttons(self):
        """创建画布左上角的悬浮按钮"""
        button_container = QWidget(self.canvas_widget)
        button_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        button_container.move(10, 10)

        button_layout = QHBoxLayout(button_container)
        button_layout.setSpacing(5)
        button_layout.setContentsMargins(0, 0, 0, 0)

        # 运行按钮
        self.run_btn = ToolButton(FIF.PLAY, self)
        self.run_btn.setToolTip("运行工作流")
        self.run_btn.clicked.connect(self.run_workflow)
        button_layout.addWidget(self.run_btn)

        # 导出按钮
        self.export_btn = ToolButton(FIF.SAVE, self)
        self.export_btn.setToolTip("导出工作流")
        self.export_btn.clicked.connect(self.save_graph)
        button_layout.addWidget(self.export_btn)

        # 导入按钮
        self.import_btn = ToolButton(FIF.FOLDER, self)
        self.import_btn.setToolTip("导入工作流")
        self.import_btn.clicked.connect(self.load_graph)
        button_layout.addWidget(self.import_btn)

        button_container.setLayout(button_layout)
        button_container.show()

    def canvas_drag_enter_event(self, event):
        """画布拖拽进入事件"""
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def canvas_drop_event(self, event):
        """画布放置事件"""
        if event.mimeData().hasText():
            full_path = event.mimeData().text()
            node_type = self.node_type_map.get(full_path)
            if node_type:
                # 获取放置位置（相对于画布）
                pos = event.pos()
                # 转换为场景坐标
                scene_pos = self.canvas_widget.mapToScene(pos)
                # 创建节点
                node = self.graph.create_node(node_type)
                node.set_pos(scene_pos.x(), scene_pos.y())
                # 初始化状态
                self.node_status[node.id] = NodeStatus.NODE_STATUS_UNRUN
                # 设置节点状态（用于视觉显示）
                if hasattr(node, 'status'):
                    node.status = NodeStatus.NODE_STATUS_UNRUN
            event.accept()
        else:
            event.ignore()

    def get_node_status(self, node):
        """获取节点状态"""
        return self.node_status.get(node.id, NodeStatus.NODE_STATUS_UNRUN)

    def set_node_status(self, node, status):
        """设置节点状态"""
        self.node_status[node.id] = status
        # 更新节点视觉状态
        if hasattr(node, 'status'):
            node.status = status
        # 如果当前选中的是这个节点，更新属性面板
        if (self.property_panel.current_node and
                self.property_panel.current_node.id == node.id):
            self.property_panel.update_properties(self.property_panel.current_node)

    def run_single_node(self, node):
        """异步运行单个节点"""
        # 通知节点开始运行
        self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING)

        # 创建 Worker
        worker = Worker(node.execute_sync, self)
        worker.signals.finished.connect(lambda result: self.on_node_finished(node, result))
        worker.signals.error.connect(lambda: self.on_node_error(node))

        # 启动异步任务
        self.threadpool.start(worker)

    def on_node_finished(self, node, result):
        """节点执行完成回调"""
        self.node_results[node.id] = result
        self.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)

        # 刷新属性面板
        if (self.property_panel.current_node and
                self.property_panel.current_node.id == node.id):
            self.property_panel.update_properties(node)

    def on_node_error(self, node):
        """节点执行错误回调"""
        self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
        self.create_failed_info(
            '错误',
            f'节点 "{node.name()}" 执行失败！',
        )
        # 刷新属性面板
        if (self.property_panel.current_node and
                self.property_panel.current_node.id == node.id):
            self.property_panel.update_properties(node)

    def on_node_error_simple(self, node_id):
        """简单节点错误回调（用于批量执行）"""
        node = self._get_node_by_id(node_id)
        self.create_failed_info(
            '错误',
            f'节点 "{node.name()}" 执行失败！',
        )
        if node:
            self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)

    def run_node_list_async(self, nodes):
        """异步执行节点列表"""
        if not nodes:
            return

        # 创建执行器
        executor = NodeListExecutor(self, nodes)
        executor.signals.finished.connect(lambda: self.create_success_info("完成", "工作流执行完成!"))
        executor.signals.error.connect(lambda: self.create_failed_info("错误", f"工作流执行失败!"))
        executor.signals.node_finished.connect(self.on_node_finished_simple)
        executor.signals.node_error.connect(self.on_node_error_simple)

        # 启动执行器
        self.threadpool.start(executor)

    def on_node_finished_simple(self, node_id, result):
        """简单节点完成回调（用于批量执行）"""
        node = self._get_node_by_id(node_id)
        if node:
            self.node_results[node_id] = result
            self.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)

    def _get_node_by_id(self, node_id):
        """根据 ID 获取节点"""
        for node in self.graph.all_nodes():
            if node.id == node_id:
                return node
        return None

    def run_to_node(self, target_node):
        """运行到目标节点（包含所有上游节点）"""
        nodes_to_run = self.get_ancestors_and_self(target_node)
        self.run_node_list_async(nodes_to_run)

    def run_from_node(self, start_node):
        """从起始节点开始运行（包含所有下游节点）"""
        nodes_to_run = self.get_descendants_and_self(start_node)
        self.run_node_list_async(nodes_to_run)

    def get_ancestors_and_self(self, node):
        """获取 node 及其所有上游节点（拓扑顺序）"""
        visited = set()
        result = []

        def dfs(n):
            if n in visited:
                return
            visited.add(n)
            # 先处理上游
            for input_port in n.input_ports():
                for out_port in input_port.connected_ports():
                    upstream = get_port_node(out_port)
                    dfs(upstream)
            result.append(n)

        dfs(node)
        return result

    def get_descendants_and_self(self, node):
        """获取 node 及其所有下游节点（拓扑顺序）"""
        visited = set()
        result = []

        def dfs(n):
            if n in visited:
                return
            visited.add(n)
            result.append(n)
            # 处理下游
            for output_port in n.output_ports():
                for in_port in output_port.connected_ports():
                    downstream = get_port_node(in_port)
                    dfs(downstream)

        dfs(node)
        return result

    def delete_node(self, node):
        """删除节点"""
        if node:
            node_id = node.id
            # 清理数据
            if node_id in self.node_results:
                del self.node_results[node_id]
            if node_id in self.node_status:
                del self.node_status[node_id]

            self.graph.delete_node(node)

    def get_node_input(self, node, port_name):
        """获取节点某个输入端口的上游数据"""
        for input_port in node.input_ports():
            if input_port.name() == port_name:
                connected = input_port.connected_ports()
                if connected:
                    upstream_out = connected[0]
                    upstream_node = get_port_node(upstream_out)
                    return self.node_results.get(upstream_node.id, {}).get(upstream_out.name())
        return None

    def on_selection_changed(self):
        selected_nodes = self.graph.selected_nodes()
        if selected_nodes:
            self.on_node_selected(selected_nodes[0])
        else:
            self.property_panel.update_properties(None)

    def on_node_selected(self, node):
        self.property_panel.update_properties(node)

    def save_graph(self):
        self.graph.save_session('workflow.json')
        print("工作流已保存到 workflow.json")

    def load_graph(self):
        try:
            self.graph.load_session('workflow.json')
            print("工作流已从 workflow.json 加载")
            # 重新初始化所有节点状态
            self.node_status = {}
            for node in self.graph.all_nodes():
                self.node_status[node.id] = NodeStatus.NODE_STATUS_UNRUN
                if hasattr(node, 'status'):
                    node.status = NodeStatus.NODE_STATUS_UNRUN
        except FileNotFoundError:
            print("workflow.json 未找到！")

    def build_component_tree(self, component_map):
        self.nav_view.clear()
        categories = {}

        for full_path, comp_cls in component_map.items():
            category, name = full_path.split("/", 1)
            if category not in categories:
                cat_item = QTreeWidgetItem([category])
                self.nav_view.addTopLevelItem(cat_item)
                categories[category] = cat_item
            else:
                cat_item = categories[category]
            cat_item.addChild(QTreeWidgetItem([name]))

        self.nav_view.expandAll()

    def run_workflow(self):
        nodes = self.graph.all_nodes()
        if not nodes:
            # 显示错误消息
            w = MessageBox("无节点", "⚠️ 工作流中没有节点。", self)
            w.exec()
            return

        # 构建依赖图
        in_degree = {node: 0 for node in nodes}
        graph = defaultdict(list)

        for node in nodes:
            for input_port in node.input_ports():
                for upstream_out in input_port.connected_ports():
                    upstream = get_port_node(upstream_out)
                    graph[upstream].append(node)
                    in_degree[node] += 1

        # 拓扑排序
        queue = deque([n for n in nodes if in_degree[n] == 0])
        order = []
        while queue:
            n = queue.popleft()
            order.append(n)
            for neighbor in graph[n]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(nodes):
            w = MessageBox("循环依赖", "❌ 检测到循环依赖！", self)
            w.exec()
            return

        self.run_node_list_async(order)

    def _setup_context_menus(self):
        """设置画布和节点的右键菜单"""

        # 获取主画布菜单（graph menu）
        graph_menu = self.graph.get_context_menu('graph')

        # 添加画布级别的菜单项
        graph_menu.add_command('运行工作流', self.run_workflow, 'Ctrl+R')
        graph_menu.add_command('保存工作流', self.save_graph, 'Ctrl+S')
        graph_menu.add_command('加载工作流', self.load_graph, 'Ctrl+O')

        # 添加分隔符
        graph_menu.add_separator()

        # 添加自定义菜单
        edit_menu = graph_menu.add_menu('编辑')
        edit_menu.add_command('全选', lambda graph: graph.select_all(), 'Ctrl+A')
        edit_menu.add_command('取消选择', lambda graph: graph.clear_selection(), 'Ctrl+D')
        edit_menu.add_command('删除选中', lambda graph: graph.delete_nodes(graph.selected_nodes()), 'Del')

        # 获取节点菜单（nodes menu）
        nodes_menu = self.graph.get_context_menu('nodes')

        # 为所有动态节点添加通用命令
        for node_type in self.node_type_map.values():
            nodes_menu.add_command('▶ 运行此节点', lambda graph, node: self.run_single_node(node), node_type=node_type)
            nodes_menu.add_command('⏩ 运行到此节点', lambda graph, node: self.run_to_node(node), node_type=node_type)
            nodes_menu.add_command('⏭️ 从此节点开始运行', lambda graph, node: self.run_from_node(node),
                                   node_type=node_type)
            nodes_menu.add_command('📄 查看节点日志', lambda graph, node: node.show_logs(), node_type=node_type)
            nodes_menu.add_command('🗑️ 删除节点', lambda graph, node: self.delete_node(node), node_type=node_type)

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