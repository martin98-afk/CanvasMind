from collections import deque, defaultdict

from NodeGraphQt import NodeGraph, BackdropNode
from PyQt5.QtCore import Qt, QThreadPool
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    ToolButton, MessageBox, InfoBar,
    InfoBarPosition, FluentIcon, ComboBox
)

from app.nodes.create_dynamic_node import create_node_class
from app.nodes.status_node import NodeStatus, StatusNode
from app.scan_components import scan_components
from app.utils.threading_utils import NodeListExecutor, Worker
from app.utils.utils import get_port_node
from app.widgets.draggable_component_tree import DraggableTreeWidget
from app.widgets.property_panel import PropertyPanel


# ----------------------------
# 主界面页面
# ----------------------------
class CanvasPage(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.setObjectName('canvas_page')
        self.parent = parent
        # 初始化线程池
        self.threadpool = QThreadPool()
        print(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")

        # 初始化状态存储
        self.node_status = {}  # {node_id: status}
        self.node_type_map = {}
        self._registered_nodes = []
        # 初始化 NodeGraph
        self.graph = NodeGraph()

        self.canvas_widget = self.graph.viewer()

        # 组件面板 - 使用可拖拽的树
        self.nav_view = DraggableTreeWidget(self)
        self.nav_view.setHeaderHidden(True)
        self.nav_view.setFixedWidth(200)
        self.register_components()
        # 属性面板
        self.property_panel = PropertyPanel(self)

        # 布局
        main_layout = QVBoxLayout(self)
        canvas_layout = QHBoxLayout()
        canvas_layout.addWidget(self.nav_view)
        canvas_layout.addWidget(self.canvas_widget, 1)
        canvas_layout.addWidget(self.property_panel, 0, Qt.AlignRight)
        main_layout.addLayout(canvas_layout)

        # 创建悬浮按钮和环境选择
        self.create_floating_buttons()
        self.create_environment_selector()

        # 信号连接
        scene = self.graph.viewer().scene()
        scene.selectionChanged.connect(self.on_selection_changed)

        # 启用画布的拖拽放置
        self.canvas_widget.setAcceptDrops(True)
        self.canvas_widget.dragEnterEvent = self.canvas_drag_enter_event
        self.canvas_widget.dropEvent = self.canvas_drop_event
        # ✅ 启用右键菜单（关键步骤）
        self._setup_context_menus()

    def create_environment_selector(self):
        """创建运行环境选择下拉框"""
        # 创建下拉框容器
        self.env_selector_container = QWidget(self.canvas_widget)
        self.env_selector_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        # 放置在右上角
        self.env_selector_container.move(self.canvas_widget.width() - 260, 10)

        # 创建布局
        env_layout = QHBoxLayout(self.env_selector_container)
        env_layout.setSpacing(5)
        env_layout.setContentsMargins(0, 0, 0, 0)

        # 添加标签
        env_label = ToolButton(self)
        env_label.setText("环境:")
        env_label.setFixedSize(50, 30)

        # 创建环境选择下拉框
        self.env_combo = ComboBox(self.env_selector_container)
        self.env_combo.setFixedWidth(200)
        # 设置默认选项
        self.env_combo.setCurrentIndex(0)
        self.load_env_combos()
        # 连接信号
        self.env_combo.currentIndexChanged.connect(self.on_environment_changed)
        self.parent.package_manager.env_changed.connect(self.load_env_combos)

        env_layout.addWidget(env_label)
        env_layout.addWidget(self.env_combo)
        env_layout.addStretch()

        self.env_selector_container.setLayout(env_layout)
        self.env_selector_container.show()

        # 当画布大小改变时，重新定位环境选择器
        self.canvas_widget.resizeEvent = self._on_canvas_resize

    def load_env_combos(self):
        self.env_combo.clear()
        # 添加选项
        self.env_combo.addItem("系统环境", userData="system")
        # 添加环境管理器中的环境
        if hasattr(self.parent, 'package_manager') and self.parent.package_manager:
            envs = self.parent.package_manager.mgr.list_envs()
            for env in envs:
                self.env_combo.addItem(f"独立环境：{env}", userData=env)

    def _on_canvas_resize(self, event):
        """画布大小改变时重新定位环境选择器"""
        super(type(self.canvas_widget), self.canvas_widget).resizeEvent(event)
        # 重新定位到右上角
        self.env_selector_container.move(self.canvas_widget.width() - 260, 10)

    def on_environment_changed(self):
        """环境选择改变时的处理"""
        current_text = self.env_combo.currentText()
        current_data = self.env_combo.currentData()

        if current_data == "system":
            self.create_info("环境切换", f"当前运行环境: {current_text}")
        else:
            self.create_info("环境切换", f"当前运行环境: {current_text}")

    def get_current_python_exe(self):
        """获取当前选择的Python解释器路径"""
        current_data = self.env_combo.currentData()

        if current_data == "system":
            return None
        else:
            # 返回环境管理器中的Python路径
            if hasattr(self.parent, 'package_manager') and self.parent.package_manager:
                try:
                    return str(self.parent.package_manager.mgr.get_python_exe(current_data))
                except Exception as e:
                    self.create_failed_info("错误", f"获取环境 {current_data} 的Python路径失败: {str(e)}")
                    return None  # 返回系统Python作为备选
            else:
                return None

    def register_components(self):
        # 扫描组件
        self._registered_nodes.extend(list(self.graph.registered_nodes()))
        self.graph._node_factory.clear_registered_nodes()
        self.component_map, self.file_map = scan_components()
        # 获取节点菜单（nodes menu）
        nodes_menu = self.graph.get_context_menu('nodes')
        for full_path, comp_cls in self.component_map.items():
            safe_name = full_path.replace("/", "_").replace(" ", "_").replace("-", "_")
            node_class = create_node_class(comp_cls, full_path, self.file_map.get(full_path))
            # 继承 StatusNode 以支持状态显示
            node_class = type(f"Status{node_class.__name__}", (StatusNode, node_class), {})
            node_class.__name__ = f"StatusDynamicNode_{safe_name}"
            self.graph.register_node(node_class)
            self.node_type_map[full_path] = f"dynamic.{node_class.__name__}"
            if f"dynamic.{node_class.__name__}" not in self._registered_nodes:
                nodes_menu.add_command('▶ 运行此节点', lambda graph, node: self.run_single_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('⏩ 运行到此节点', lambda graph, node: self.run_to_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('⏭️ 从此节点开始运行', lambda graph, node: self.run_from_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('📄 查看节点日志', lambda graph, node: node.show_logs(),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('🗑️ 删除节点', lambda graph, node: self.delete_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")

    def create_floating_buttons(self):
        """创建画布左上角的悬浮按钮"""
        button_container = QWidget(self.canvas_widget)
        button_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        button_container.move(10, 10)

        button_layout = QHBoxLayout(button_container)
        button_layout.setSpacing(5)
        button_layout.setContentsMargins(0, 0, 0, 0)

        # 运行按钮
        self.run_btn = ToolButton(FluentIcon.PLAY, self)
        self.run_btn.setToolTip("运行工作流")
        self.run_btn.clicked.connect(self.run_workflow)
        button_layout.addWidget(self.run_btn)

        # 导出按钮
        self.export_btn = ToolButton(FluentIcon.SAVE, self)
        self.export_btn.setToolTip("导出工作流")
        self.export_btn.clicked.connect(self.save_graph)
        button_layout.addWidget(self.export_btn)

        # 导入按钮
        self.import_btn = ToolButton(FluentIcon.FOLDER, self)
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
        # 启动异步任务
        current_python_exe = self.get_current_python_exe()  # 使用当前选择的Python环境
        worker = Worker(
            node.execute_sync,
            self.component_map.get(node.FULL_PATH),
            True if current_python_exe else False,
            current_python_exe
        )
        worker.signals.finished.connect(lambda result: self.on_node_finished(node, result))
        worker.signals.error.connect(lambda error: self.on_node_error(node))
        self.threadpool.start(worker)

    def execute_backdrop_loop(self, backdrop_node, loop_config):
        """执行 Backdrop 内的循环"""
        # 获取 Backdrop 内的节点
        nodes_in_backdrop = self._get_nodes_in_backdrop(backdrop_node)

        # 拓扑排序（Backdrop 内部应该是无环的）
        execution_order = self._topological_sort(nodes_in_backdrop)

        # 循环执行
        max_iterations = loop_config.get("max_iterations", 10)
        current_data = loop_config.get("initial_data", {})

        for iteration in range(max_iterations):
            # 执行一次循环体
            node_outputs = {}
            for node in execution_order:
                # 准备输入数据
                inputs = self._prepare_node_inputs(node, node_outputs, current_data)
                # 执行节点
                output = node.execute_sync({"iteration": iteration, **inputs}, self)
                node_outputs[node.id] = output

            # 更新循环数据
            current_data = self._update_loop_data(current_data, node_outputs)

            # 检查退出条件
            if self._check_exit_condition(loop_config, current_data, iteration):
                break

        return current_data

    def _get_nodes_in_backdrop(self, backdrop_node):
        """获取 Backdrop 内的所有节点"""
        nodes_in_backdrop = []
        for node in self.graph.all_nodes():
            if hasattr(node, 'parent') and node.parent == backdrop_node:
                nodes_in_backdrop.append(node)
        return nodes_in_backdrop

    # 通过代码创建 Backdrop
    def create_backdrop(self, title="循环体"):
        """创建包含指定节点的 Backdrop"""

        # 创建 backdrop 节点
        backdrop = self.graph.create_node('Backdrop')
        backdrop.set_name(title)

        return backdrop

    def _resize_backdrop_to_fit_nodes(self, backdrop, nodes):
        """调整 backdrop 大小以适应包含的节点"""
        if not nodes:
            return

        # 计算节点边界
        min_x = min(node.pos()[0] for node in nodes)
        min_y = min(node.pos()[1] for node in nodes)
        max_x = max(node.pos()[0] + 200 for node in nodes)  # 200 是节点宽度估计
        max_y = max(node.pos()[1] + 100 for node in nodes)  # 100 是节点高度估计

        # 设置 backdrop 位置和大小
        backdrop.set_pos(min_x - 20, min_y - 20)
        width = max_x - min_x + 40
        height = max_y - min_y + 40
        backdrop.width = width
        backdrop.height = height

    def on_node_finished(self, node, result):
        """节点执行完成回调"""
        self.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
        # 刷新属性面板
        if (self.property_panel.current_node and
                self.property_panel.current_node.id == node.id):
            self.property_panel.update_properties(node)

    def on_node_error(self, node):
        """节点执行错误回调"""
        node.clear_output_value()
        self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
        self.create_failed_info('错误', f'节点 "{node.name()}" 执行失败！')
        # 刷新属性面板
        if (self.property_panel.current_node and
                self.property_panel.current_node.id == node.id):
            self.property_panel.update_properties(node)

    def on_node_error_simple(self, node_id):
        """简单节点错误回调（用于批量执行）"""
        node = self._get_node_by_id(node_id)
        node.clear_output_value()
        self.create_failed_info('错误', f'节点 "{node.name()}" 执行失败！')
        if node:
            self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)

    def run_node_list_async(self, nodes):
        """异步执行节点列表"""
        if not nodes:
            return
        # 将所有node状态变为未运行
        for node in nodes:
            self.set_node_status(node, NodeStatus.NODE_STATUS_UNRUN)
        # 创建执行器
        executor = NodeListExecutor(self, nodes, self.get_current_python_exe())  # 使用当前选择的Python环境
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
            if node_id in self.node_status:
                del self.node_status[node_id]

            self.graph.delete_node(node)

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
        self.create_success_info("工作流已保存到 workflow.json", "")

    def load_graph(self):
        try:
            self.graph.load_session('workflow.json')
            self.create_success_info("工作流已从 workflow.json 加载", "")
            # 重新初始化所有节点状态
            self.node_status = {}
            for node in self.graph.all_nodes():
                self.node_status[node.id] = NodeStatus.NODE_STATUS_UNRUN
                if hasattr(node, 'status'):
                    node.status = NodeStatus.NODE_STATUS_UNRUN
        except Exception:
            self.create_failed_info("错误", "workflow.json 未找到！")

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
            if isinstance(node, BackdropNode):
                continue
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
        graph_menu.add_command('创建 Backdrop', lambda: self.create_backdrop("新分组"))
        # 添加分隔符
        graph_menu.add_separator()

        # 添加自定义菜单
        edit_menu = graph_menu.add_menu('编辑')
        edit_menu.add_command('全选', lambda graph: graph.select_all(), 'Ctrl+A')
        edit_menu.add_command('取消选择', lambda graph: graph.clear_selection(), 'Ctrl+D')
        edit_menu.add_command('删除选中', lambda graph: graph.delete_nodes(graph.selected_nodes()), 'Del')

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