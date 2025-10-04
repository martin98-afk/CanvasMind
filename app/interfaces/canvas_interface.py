# -*- coding: utf-8 -*-
import json
import pathlib
import shutil
import uuid

from pathlib import Path
from collections import deque, defaultdict

from NodeGraphQt import NodeGraph, BackdropNode
from PyQt5.QtCore import Qt, QThreadPool
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox
from qfluentwidgets import (
    ToolButton, MessageBox, InfoBar,
    InfoBarPosition, FluentIcon, ComboBox
)

from app.nodes.create_dynamic_node import create_node_class
from app.nodes.status_node import NodeStatus, StatusNode
from app.scan_components import scan_components
from app.utils.threading_utils import NodeListExecutor, Worker
from app.utils.utils import get_port_node, serialize_for_json, deserialize_from_json
from app.widgets.draggable_component_tree import DraggableTreeWidget
from app.widgets.property_panel import PropertyPanel


# ----------------------------
# 主界面页面
# ----------------------------
class CanvasPage(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.file_path = None  # 新增：当前文件路径
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
        # 添加环境管理器中的环境
        if hasattr(self.parent, 'package_manager') and self.parent.package_manager:
            envs = self.parent.package_manager.mgr.list_envs()
            for env in envs:
                self.env_combo.addItem(env, userData=env)

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
        self.export_btn.clicked.connect(self._save_via_dialog)
        button_layout.addWidget(self.export_btn)

        # 导入按钮
        self.import_btn = ToolButton(FluentIcon.FOLDER, self)
        self.import_btn.setToolTip("导入工作流")
        self.import_btn.clicked.connect(self._open_via_dialog)

        # 导出模型按钮
        self.export_model_btn = ToolButton(FluentIcon.SHARE, self)
        self.export_model_btn.setToolTip("导出选中节点为独立模型")
        self.export_model_btn.clicked.connect(self.export_selected_nodes_as_project)
        button_layout.addWidget(self.export_model_btn)

        button_layout.addWidget(self.import_btn)

        button_container.setLayout(button_layout)
        button_container.show()

    def _save_via_dialog(self):
        from PyQt5.QtWidgets import QFileDialog
        if self.file_path:
            # 默认使用当前路径
            default_path = self.file_path
        else:
            default_path = "workflow"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存工作流", default_path, "工作流文件 (*.workflow.json)"
        )
        if file_path:
            if not file_path.endswith('.workflow.json'):
                file_path += '.workflow.json'
            self.save_full_workflow(file_path)
            self.file_path = file_path

    def _open_via_dialog(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开工作流", "", "工作流文件 (*.workflow.json)"
        )
        if file_path:
            self.load_full_workflow(file_path)
            self.file_path = file_path

    def canvas_drag_enter_event(self, event):
        """画布拖拽进入事件"""
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def export_selected_nodes_as_project(self):
        """导出选中节点为独立项目（仅选中节点，不包含上游依赖）"""

        selected_nodes = self.graph.selected_nodes()
        if not selected_nodes:
            self.create_warning_info("导出失败", "请先选中要导出的节点！")
            return

        # 过滤掉 Backdrop 节点
        nodes_to_export = [node for node in selected_nodes if not isinstance(node, BackdropNode)]
        if not nodes_to_export:
            self.create_warning_info("导出失败", "选中的节点无效（只有分组节点）！")
            return

        # 检查未连接的输入端口
        unconnected_inputs = []
        for node in nodes_to_export:
            for input_port in node.input_ports():
                if not input_port.connected_ports():
                    unconnected_inputs.append(f"• {node.name()} → {input_port.name()}")

        if unconnected_inputs:
            msg = "检测到未连接的输入端口，这些端口需要在运行时提供数据：\n\n" + "\n".join(unconnected_inputs)
            msg += "\n\n是否继续导出？"
            reply = QMessageBox.question(
                self, "未连接输入", msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        # 选择导出目录
        project_dir_str = QFileDialog.getExistingDirectory(
            self, "选择导出目录", "", QFileDialog.ShowDirsOnly
        )
        if not project_dir_str:
            return

        project_dir = Path(project_dir_str)
        project_name = "model_" + str(uuid.uuid4())[:8]
        export_path = project_dir / project_name
        export_path.mkdir(parents=True, exist_ok=True)

        try:
            # 1. 创建项目目录结构
            components_dir = export_path / "components"
            inputs_dir = export_path / "inputs"
            components_dir.mkdir(parents=True, exist_ok=True)
            inputs_dir.mkdir(parents=True, exist_ok=True)

            # 2. 收集需要的组件
            used_components = set()
            node_id_map = {}  # old_id -> new_id
            new_nodes_data = {}
            new_connections = []

            for node in nodes_to_export:
                used_components.add(node.FULL_PATH)
                new_id = str(uuid.uuid4())
                node_id_map[node.id] = new_id

            # 3. 复制组件代码
            component_path_map = {}  # old_path -> new_relative_path (as str with forward slash)
            for full_path in used_components:
                if full_path in self.file_map:
                    src_path = Path(self.file_map[full_path])
                    if src_path.exists():
                        # 尝试保持原始目录结构: 假设 src_path 是在某个根目录下的组件
                        # 原逻辑: relpath(src, dirname(dirname(src))) — 这其实是取最后两级？
                        # 例如: /a/b/c.py → relpath to /a → b/c.py
                        try:
                            # 获取 src 的父目录的父目录作为 base
                            base_dir = src_path.parent.parent
                            if base_dir in src_path.parents:
                                src_rel_path = src_path.relative_to(base_dir)
                            else:
                                # fallback: just use filename
                                src_rel_path = src_path.name
                        except ValueError:
                            # 如果 relative_to 失败（不在父目录中），回退到文件名
                            src_rel_path = src_path.name

                        dst_path = components_dir / src_rel_path
                        dst_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(src_path), str(dst_path))
                        # 记录相对于项目根目录的路径（使用正斜杠）
                        rel_to_project = ("components" / src_rel_path).as_posix()
                        component_path_map[str(src_path)] = rel_to_project

            # 4. 构建节点数据和连接
            for node in nodes_to_export:
                new_id = node_id_map[node.id]
                node_data = {
                    "name": node.name(),
                    "type_": node.type_,
                    "pos": node.pos(),
                    "custom": {
                        "FULL_PATH": node.FULL_PATH,
                        "FILE_PATH": component_path_map.get(self.file_map.get(node.FULL_PATH, ""), "")
                    }
                }
                new_nodes_data[new_id] = node_data

            # 只保留选中节点之间的连接
            original_connections = self.graph.serialize_session()["connections"]
            for conn in original_connections:
                out_id, out_port = conn["out"]
                in_id, in_port = conn["in"]
                if out_id in node_id_map and in_id in node_id_map:
                    new_connections.append({
                        "out": [node_id_map[out_id], out_port],
                        "in": [node_id_map[in_id], in_port]
                    })

            # 5. 构建 runtime 数据（包含当前输入值）
            runtime_data = {
                "environment": self.env_combo.currentData(),
                "environment_exe": self.get_current_python_exe(),
                "node_id2stable_key": {},
                "node_states": {},
                "node_inputs": {},
                "node_outputs": {},
                "column_select": {},
            }

            # 辅助函数：处理文件路径重写
            def _process_value_for_export(value, inputs_dir: Path, export_path: Path):
                """处理值，如果是文件路径则复制到 inputs_dir 并返回相对路径"""
                if isinstance(value, str):
                    file_path = Path(value)
                    if file_path.is_file():
                        try:
                            filename = file_path.name
                            dst_path = inputs_dir / filename
                            if not dst_path.exists():
                                shutil.copy2(str(file_path), str(dst_path))
                            return ("inputs" / filename).as_posix()
                        except Exception as e:
                            print(f"警告：无法复制文件 {value}: {e}")
                            return value
                elif isinstance(value, dict):
                    return {k: _process_value_for_export(v, inputs_dir, export_path) for k, v in value.items()}
                elif isinstance(value, list):
                    return [_process_value_for_export(v, inputs_dir, export_path) for v in value]
                return value

            for node in nodes_to_export:
                new_id = node_id_map[node.id]
                full_path = getattr(node, 'FULL_PATH', 'unknown')
                node_name = node.name()
                stable_key = f"{full_path}||{node_name}"

                current_inputs = {}
                for input_port in node.input_ports():
                    port_name = input_port.name()
                    connected = input_port.connected_ports()
                    if connected:
                        upstream_out = connected[0]
                        upstream_node = upstream_out.node()
                        value = upstream_node._output_values.get(upstream_out.name())
                        if value is not None:
                            current_inputs[port_name] = _process_value_for_export(value, inputs_dir, export_path)
                        else:
                            current_inputs[port_name] = None
                    else:
                        current_inputs[port_name] = None

                runtime_data["node_id2stable_key"][new_id] = stable_key
                runtime_data["node_states"][stable_key] = self.node_status.get(node.id, "unrun")
                runtime_data["node_inputs"][stable_key] = serialize_for_json(current_inputs)
                runtime_data["node_outputs"][stable_key] = serialize_for_json(getattr(node, '_output_values', {}))
                runtime_data["column_select"][stable_key] = getattr(node, 'column_select', {})

            # 6. 保存项目文件
            graph_data = {
                "nodes": new_nodes_data,
                "connections": new_connections,
                "grid": self.graph.serialize_session().get("grid", None)
            }

            project_data = {
                "version": "1.0",
                "graph": graph_data,
                "runtime": runtime_data
            }

            model_json_path = export_path / "model.workflow.json"
            with open(model_json_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)

            # 7. 生成 requirements.txt
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

            if requirements:
                req_path = export_path / "requirements.txt"
                with open(req_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(sorted(requirements)))

            # 8. 生成运行脚本
            run_script = '''# -*- coding: utf-8 -*-
import sys
import os
from loguru import logger

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner.workflow_runner import execute_workflow

if __name__ == "__main__":
    # 可以传入外部输入参数
    # inputs = {"node_id": {"input_port": "value"}}
    outputs = execute_workflow("model.workflow.json")
    logger.info("模型执行完成，输出:")
    for node_id, output in outputs.items():
        logger.info(f"  {node_id}: {output}")
        '''
            (export_path / "run.py").write_text(run_script, encoding='utf-8')

            # 9. 复制 workflow_runner.py 和 utils
            current_dir = Path(__file__).parent
            runner_src = current_dir / ".." / "runner"
            if runner_src.exists():
                shutil.copytree(str(runner_src), str(export_path / "runner"), dirs_exist_ok=True)

            # 复制 base.py
            base_src = current_dir.parent / "components" / "base.py"
            if base_src.exists():
                shutil.copy(str(base_src), str(components_dir / "base.py"))

            # 转移 scan_components
            scan_src = export_path / "runner" / "scan_components.py"
            if scan_src.exists():
                shutil.move(str(scan_src), str(export_path / "scan_components.py"))

            # 10. 创建 README
            readme_content = f"""# 导出的模型项目

    ## 目录结构
    - `model.workflow.json`: 工作流定义文件
    - `components/`: 组件代码
    - `inputs/`: 输入文件（如模型文件、数据文件）
    - `requirements.txt`: 依赖包列表
    - `run.py`: 运行脚本

    ## 使用方法
    1. 安装依赖: `pip install -r requirements.txt`
    2. 运行模型: `python run.py`

    ## 注意事项
    - 未连接的输入端口需要在运行时提供数据
    - 文件路径已重写为相对路径
    """
            (export_path / "README.md").write_text(readme_content, encoding='utf-8')

            self.create_success_info("导出成功", f"模型项目已导出到:\n{export_path}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.create_failed_info("导出失败", f"错误: {str(e)}")

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
        executor.signals.node_started.connect(self.on_node_started_simple)
        executor.signals.node_finished.connect(self.on_node_finished_simple)
        executor.signals.node_error.connect(self.on_node_error_simple)

        # 启动执行器
        self.threadpool.start(executor)

    def on_node_started_simple(self, node_id):
        """简单节点完成回调（用于批量执行）"""
        node = self._get_node_by_id(node_id)
        if node:
            self.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING)

    def on_node_finished_simple(self, node_id):
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

    def save_full_workflow(self, file_path):
        graph_data = self.graph.serialize_session()

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
            if isinstance(node, BackdropNode):
                continue

            # ✅ 使用 (FULL_PATH, name) 作为稳定 key
            full_path = getattr(node, 'FULL_PATH', 'unknown')
            node_name = node.name()  # 或 node.model.name
            stable_key = f"{full_path}||{node_name}"
            runtime["node_id2stable_key"][node.id] = stable_key
            runtime["node_states"][stable_key] = self.node_status.get(node.id, "unrun")
            runtime["node_inputs"][stable_key] = serialize_for_json(getattr(node, '_input_values', {}))
            runtime["node_outputs"][stable_key] = serialize_for_json(getattr(node, '_output_values', {}))
            runtime["column_select"][stable_key] = getattr(node, 'column_select', {})

        full_data = {
            "version": "1.0",
            "graph": graph_data,
            "runtime": runtime
        }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, indent=2, ensure_ascii=False)

    def load_full_workflow(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            full_data = json.load(f)

        # 加载图
        self.graph.deserialize_session(full_data["graph"])

        # 恢复环境
        env = full_data.get("runtime", {}).get("environment")
        if env:
            for i in range(self.env_combo.count()):
                if self.env_combo.itemData(i) == env:
                    self.env_combo.setCurrentIndex(i)
                    break

        # 恢复节点状态
        rt = full_data.get("runtime", {})
        for node in self.graph.all_nodes():
            if isinstance(node, BackdropNode):
                continue

            # ✅ 用相同方式生成 stable_key
            full_path = getattr(node, 'FULL_PATH', 'unknown')
            node_name = node.name()
            stable_key = f"{full_path}||{node_name}"

            # 恢复数据
            node._input_values = deserialize_from_json(rt.get("node_inputs", {}).get(stable_key, {}))
            node._output_values = deserialize_from_json(rt.get("node_outputs", {}).get(stable_key, {}))
            node.column_select = rt.get("column_select", {}).get(stable_key, {})

            status_str = rt.get("node_states", {}).get(stable_key, "unrun")
            self.set_node_status(
                node, getattr(NodeStatus, f"NODE_STATUS_{status_str.upper()}", NodeStatus.NODE_STATUS_UNRUN)
            )

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
        graph_menu.add_command('保存工作流', self._save_via_dialog, 'Ctrl+S')
        graph_menu.add_command('加载工作流', self._open_via_dialog, 'Ctrl+O')
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