# -*- coding: utf-8 -*-
import json
import os
import pathlib
import shutil
from collections import deque, defaultdict
from datetime import datetime
from pathlib import Path

from NodeGraphQt import NodeGraph, BackdropNode
from NodeGraphQt.constants import PipeLayoutEnum
from PyQt5.QtCore import Qt, QThreadPool, QRectF
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFileDialog
from loguru import logger
from qfluentwidgets import (
    ToolButton, MessageBox, InfoBar,
    InfoBarPosition, FluentIcon, ComboBox, LineEdit
)

from app.components.base import PropertyType
from app.nodes.create_dynamic_node import create_node_class
from app.nodes.status_node import NodeStatus, StatusNode
from app.scan_components import scan_components
from app.utils.config import Settings
from app.utils.threading_utils import NodeListExecutor
from app.utils.utils import get_port_node, serialize_for_json, deserialize_from_json
from app.widgets.dialog_widget.custom_messagebox import ProjectExportDialog
from app.widgets.tree_widget.draggable_component_tree import DraggableTreePanel
from app.widgets.dialog_widget.input_selection_dialog import InputSelectionDialog
from app.widgets.dialog_widget.output_selection_dialog import OutputSelectionDialog
from app.widgets.property_panel import PropertyPanel


# ----------------------------
# 主界面页面
# ----------------------------
class CanvasPage(QWidget):

    PIPELINE_STYLE = {
        "折线": PipeLayoutEnum.ANGLE.value,
        "曲线": PipeLayoutEnum.CURVED.value,
        "直线": PipeLayoutEnum.STRAIGHT.value,
    }
    PIPELINE_DIRECTION = {
        "水平": 0,
        "垂直": 1
    }

    def __init__(self, parent=None, object_name: Path=None):
        super().__init__()
        self.parent = parent
        self.file_path = object_name  # 新增：当前文件路径
        self.workflow_name = object_name.stem.split(".")[0]
        self.setObjectName('canvas_page' if object_name is None else str(object_name))
        self.parent = parent
        # 初始化线程池
        self.threadpool = QThreadPool()

        # 初始化状态存储
        self.node_status = {}  # {node_id: status}
        self.node_type_map = {}
        self._registered_nodes = []
        # 初始化 NodeGraph
        self.graph = NodeGraph()
        self.config = Settings.get_instance()
        self._setup_pipeline_style()
        self.canvas_widget = self.graph.viewer()

        # 组件面板 - 使用可拖拽的树
        self.nav_panel = DraggableTreePanel(self)
        self.nav_view = self.nav_panel.tree

        self.register_components()
        # 属性面板
        self.property_panel = PropertyPanel(self)

        # 布局
        main_layout = QVBoxLayout(self)
        canvas_layout = QHBoxLayout()
        canvas_layout.addWidget(self.nav_panel)
        canvas_layout.addWidget(self.canvas_widget, 1)
        canvas_layout.addWidget(self.property_panel, 0, Qt.AlignRight)
        main_layout.addLayout(canvas_layout)

        # 创建悬浮按钮和环境选择
        self.create_floating_buttons()
        self.create_name_label()
        self.create_environment_selector()

        # 信号连接
        scene = self.graph.viewer().scene()
        scene.selectionChanged.connect(self.on_selection_changed)

        # 启用画布的拖拽放置
        self.canvas_widget.setAcceptDrops(True)
        self.canvas_widget.dragEnterEvent = self.canvas_drag_enter_event
        self.canvas_widget.dropEvent = self.canvas_drop_event
        self.canvas_widget.installEventFilter(self)
        # ✅ 启用右键菜单（关键步骤）
        self._setup_context_menus()

    def update_workflow_name(self, name):
        self.workflow_name = name

    def eventFilter(self, obj, event):
        if obj is self.canvas_widget and event.type() == event.Resize:
            self.env_selector_container.move(self.canvas_widget.width() - 200, 10)
            workflow_name_length = len(self.workflow_name) * 15
            self.name_container.move(int(self.canvas_widget.width() // 2) - workflow_name_length // 2, 10)
        return super().eventFilter(obj, event)

    def create_environment_selector(self):
        """创建运行环境选择下拉框"""
        # 创建下拉框容器
        self.env_selector_container = QWidget(self.canvas_widget)
        self.env_selector_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        # 放置在右上角
        self.env_selector_container.move(self.canvas_widget.width() - 200, 10)

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
        self.env_combo.setFixedWidth(140)
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

    def load_env_combos(self):
        self.env_combo.clear()
        # 添加选项
        # 添加环境管理器中的环境
        if hasattr(self.parent, 'package_manager') and self.parent.package_manager:
            envs = self.parent.package_manager.mgr.list_envs()
            for env in envs:
                self.env_combo.addItem(env, userData=env)

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
        # 返回环境管理器中的Python路径
        if hasattr(self.parent, 'package_manager') and self.parent.package_manager and current_data:
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
            node_class = create_node_class(comp_cls, full_path, self.file_map.get(full_path), self)
            # 继承 StatusNode 以支持状态显示
            node_class = type(f"Status{node_class.__name__}", (StatusNode, node_class), {})
            node_class.__name__ = f"StatusDynamicNode_{safe_name}"
            self.graph.register_node(node_class)
            self.node_type_map[full_path] = f"dynamic.{node_class.__name__}"
            if f"dynamic.{node_class.__name__}" not in self._registered_nodes:
                nodes_menu.add_command('▶ 运行此节点', lambda graph, node: self.run_node_list_async([node]),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('⏩ 运行到此节点', lambda graph, node: self.run_to_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                nodes_menu.add_command('⏭️ 从此节点开始运行', lambda graph, node: self.run_from_node(node),
                                       node_type=f"dynamic.{node_class.__name__}")
                # 编辑组件
                nodes_menu.add_command('📝 编辑组件', lambda graph, node: self.edit_node(node),
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
        # 停止按钮
        self.stop_btn = ToolButton(FluentIcon.PAUSE, self)
        self.stop_btn.setToolTip("停止运行")
        self.stop_btn.clicked.connect(self.stop_workflow)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        # 导出按钮
        self.export_btn = ToolButton(FluentIcon.SAVE, self)
        self.export_btn.setToolTip("导出工作流")
        self.export_btn.clicked.connect(self._save_via_dialog)
        button_layout.addWidget(self.export_btn)

        # 导入按钮
        self.import_btn = ToolButton(FluentIcon.FOLDER, self)
        self.import_btn.setToolTip("导入工作流")
        self.import_btn.clicked.connect(self._open_via_dialog)
        button_layout.addWidget(self.import_btn)
        # 导出模型按钮
        self.export_model_btn = ToolButton(FluentIcon.SHARE, self)
        self.export_model_btn.setToolTip("导出选中节点为独立模型")
        self.export_model_btn.clicked.connect(self.export_selected_nodes_as_project)
        button_layout.addWidget(self.export_model_btn)

        button_container.setLayout(button_layout)
        button_container.show()

    def create_name_label(self):
        """创建画布左上角的悬浮按钮"""
        # 创建下拉框容器
        self.name_container = QWidget(self.canvas_widget)
        self.name_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        # 放置在右上角
        # 计算workflow_name的长度
        workflow_name_length = len(self.workflow_name) * 15
        self.name_container.move(int(self.canvas_widget.width() // 2) - workflow_name_length // 2, 10)

        # 创建布局
        name_layout = QHBoxLayout(self.name_container)
        name_layout.setSpacing(5)
        name_layout.setContentsMargins(0, 0, 0, 0)

        # 添加标签
        name_label = LineEdit(self)
        name_label.setText(self.workflow_name)
        name_label.textChanged.connect(self.update_workflow_name)

        name_layout.addWidget(name_label)
        name_layout.addStretch()

        self.name_container.setLayout(name_layout)
        self.name_container.show()

    def _save_via_dialog(self):
        if self.file_path and self.file_path.stem.split(".")[0] == self.workflow_name:
            # 默认使用当前路径
            default_path = self.file_path
            self.save_full_workflow(default_path)

            return
        else:
            file_path = self.file_path.parent / f"{self.workflow_name}.workflow.json"

        self.save_full_workflow(file_path)
        self.file_path = file_path

    def _open_via_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开工作流", "", "工作流文件 (*.workflow.json)"
        )
        if file_path:
            self.load_full_workflow(file_path)

    def canvas_drag_enter_event(self, event):
        """画布拖拽进入事件"""
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def export_selected_nodes_as_project(self):
        """导出选中节点为独立项目（支持交互式定义输入/输出接口）"""
        try:
            selected_nodes = self.graph.selected_nodes()
            if not selected_nodes:
                self.create_warning_info("导出失败", "请先选中要导出的节点！")
                return

            # 过滤掉 Backdrop 节点
            nodes_to_export = [node for node in selected_nodes if not isinstance(node, BackdropNode)]
            if not nodes_to_export:
                self.create_warning_info("导出失败", "选中的节点无效（只有分组节点）！")
                return
            nodes_to_export.sort(key=lambda node: (node.pos()[0], node.pos()[1]))
            candidate_inputs = []
            for node in nodes_to_export:
                node_name = node.name()
                comp_cls = self.component_map.get(node.FULL_PATH)

                # 组件参数（超参数）
                editable_params = node.model.custom_properties
                for param_name, param_value in editable_params.items():
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
                    logger.info(prop_def.dict())
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

                    connected = port.connected_ports()
                    current_val = None
                    if connected:
                        upstream_out = connected[0]
                        upstream_node = upstream_out.node()
                        current_val = upstream_node._output_values.get(upstream_out.name(), None)
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

## 📂 目录结构

- `model.workflow.json`: 工作流定义文件（使用原始节点ID）
- `project_spec.json`: **项目输入/输出接口规范**
- `components/`: 组件代码
- `inputs/`: 输入文件
- `requirements.txt`: 依赖包列表
- `run.py`: 运行脚本
- `api_server.py`: 微服务脚本

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
                            print(f"警告：无法复制文件 {value}: {e}")
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
                "runtime": runtime_data
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

    def on_node_error_simple(self, node_id):
        """简单节点错误回调（用于批量执行）"""
        node = self._get_node_by_id(node_id)
        node._output_values = {}
        self.create_failed_info('错误', f'节点 "{node.name()}" 执行失败！')
        if node:
            self.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def run_node_list_async(self, nodes):
        """异步执行节点列表"""
        if not nodes:
            return
        # 将所有node状态变为未运行
        for node in nodes:
            self.set_node_status(node, NodeStatus.NODE_STATUS_UNRUN)
        # 创建执行器
        executor = NodeListExecutor(self, nodes, self.get_current_python_exe())  # 使用当前选择的Python环境
        self._current_executor = executor

        executor.signals.finished.connect(self._on_workflow_finished)
        executor.signals.error.connect(self._on_workflow_error)
        executor.signals.node_started.connect(self.on_node_started_simple)
        executor.signals.node_finished.connect(self.on_node_finished_simple)
        executor.signals.node_error.connect(self.on_node_error_simple)

        # 启动执行器
        self.threadpool.start(executor)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_workflow(self):
        if hasattr(self, '_current_executor') and self._current_executor:
            self._current_executor.cancel()
            self.create_info("已停止", "正在终止任务...")
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._current_executor = None

    def _on_workflow_finished(self):
        self._cleanup_execution()
        self.create_success_info("完成", "工作流执行完成!")
        self.save_full_workflow(self.file_path)

    def _on_workflow_error(self):
        self._cleanup_execution()
        self.create_failed_info("错误", "工作流执行失败!")

    def _cleanup_execution(self):
        self._current_executor = None
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

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

        # ✅ 自动生成预览图（同目录，同名，.png）
        self._generate_canvas_thumbnail(file_path)
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
            print(f"✅ 子图预览图已保存: {preview_path}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.create_warning_info("预览图", f"生成失败: {str(e)}")

    def _generate_canvas_thumbnail(self, workflow_path):
        """根据工作流文件路径生成同名 PNG 预览图"""
        try:
            # 构造预览图路径：xxx.workflow.json → xxx.png
            base_name = os.path.splitext(os.path.splitext(workflow_path)[0])[0]  # 去掉 .workflow.json
            png_path = base_name + ".png"

            # 获取场景和边界
            scene = self.graph.viewer().scene()
            rect = QRectF()
            for node in self.graph.all_nodes():
                item_rect = node.view.sceneBoundingRect()
                rect = rect.united(item_rect)

            if rect.isEmpty():
                # 如果没有节点，创建一个空白图
                image = QImage(800, 600, QImage.Format_ARGB32)
                image.fill(Qt.white)
            else:
                # 扩展一点边距，避免裁剪
                rect.adjust(-100, -100, 90, 90)
                image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
                image.fill(Qt.white)  # 背景设为白色（可选）

                painter = QPainter(image)
                # 将场景渲染到 QImage
                scene.render(painter, target=QRectF(image.rect()), source=rect)
                painter.end()

            # 保存图像
            image.save(png_path, "PNG")
            print(f"✅ 预览图已保存: {png_path}")

        except Exception as e:
            # 可选：弹出警告
            self.create_warning_info("预览图", f"生成失败: {str(e)}")

    def load_full_workflow(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            full_data = json.load(f)

        # 加载图
        self.graph.deserialize_session(full_data["graph"])
        self._setup_pipeline_style()
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
        self.create_success_info("加载成功", "工作流加载成功！")

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

    def edit_node(self, node):
        # 跳转到组件开发界面对应的组件
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