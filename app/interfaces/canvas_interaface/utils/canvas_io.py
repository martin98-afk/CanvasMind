import json
import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtWidgets import QProgressDialog, QApplication

from app.utils.threading_utils import WorkflowLoader, ThumbnailGenerator
from app.utils.utils import serialize_for_json, deserialize_from_json
from .logger import get_logger
from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager

logger = get_logger("CanvasIO")


class CanvasIO(QObject):
    canvas_saved = pyqtSignal(Path)

    def __init__(self, graph, env_manager, global_variables, parent):
        super().__init__(parent)
        self.graph = graph
        self.env_manager = env_manager
        self.global_variables = global_variables
        self.parent = parent
        self.node_status = parent.node_status

    def save_full_workflow(self, file_path, show_info=True):
        graph_data = self.graph.serialize_session()
        for node_data in graph_data["nodes"].values():
            node_data["custom"].pop("global_variable", None)

        runtime = {
            "environment": self.env_manager.env_combo.currentData(),
            "environment_exe": self.env_manager.get_current_python_exe(),
            "node_id2stable_key": {},
            "node_states": {},
            "node_inputs": {},
            "node_outputs": {},
            "column_select": {}
        }

        for node in self.graph.all_nodes():
            full_path = getattr(node, 'FULL_PATH', 'unknown')
            stable_key = f"{full_path}||{node.name()}"
            runtime["node_id2stable_key"][node.id] = stable_key
            runtime["node_states"][stable_key] = self.node_status.get(node.id, "unrun")
            runtime["node_inputs"][stable_key] = getattr(node, '_input_values', {})
            runtime["node_outputs"][stable_key] = getattr(node, '_output_values', {})
            runtime["column_select"][stable_key] = getattr(node, 'column_select', {})

        full_data = {
            "version": "1.0",
            "graph": graph_data,
            "runtime": runtime,
            "global_variable": self.global_variables.serialize()
        }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(serialize_for_json(full_data), f, indent=2, ensure_ascii=False)

        self._generate_canvas_thumbnail_async(file_path)
        if show_info:
            MessageManager.success("保存成功", "工作流保存成功！", self.parent)

    def _generate_canvas_thumbnail_async(self, workflow_path):
        self.thumbnail_thread = ThumbnailGenerator(self.graph, workflow_path)
        self.thumbnail_thread.finished.connect(self._on_thumbnail_generated)
        self.thumbnail_thread.start()

    def _on_thumbnail_generated(self, png_path):
        if png_path:
            logger.info(f"✅ 预览图已保存: {png_path}")
            self.parent.canvas_saved.emit(self.parent.file_path)

    def load_full_workflow(self, file_path):
        self.workflow_loader = WorkflowLoader(file_path, self.graph, self.parent.node_type_map)
        self.workflow_loader.finished.connect(
            lambda gd, rd, ns, gv: self._on_workflow_loaded(gd, rd, ns, gv, file_path))
        self.workflow_loader.start()

    def _on_workflow_loaded(self, graph_data, runtime_data, node_status_data, global_variable, file_path):
        try:
            self.global_variables.deserialize(global_variable)
            nodes_data = graph_data.get("nodes", {})
            total_nodes = len(nodes_data)
            if total_nodes == 0:
                self.graph.deserialize_session(graph_data)
                self._finish_loading(runtime_data, node_status_data, file_path)
                return

            progress = QProgressDialog("正在加载节点...", "取消", 0, total_nodes, self.parent)
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle("加载中")
            progress.setCancelButton(None)
            progress.setAutoClose(True)
            progress.setMinimumDuration(0)
            progress.setValue(0)

            original_add_node = self.graph.add_node
            count = [0]

            def patched_add_node(node, pos=None, inherite_graph_style=True):
                result = original_add_node(node, pos, False, False, inherite_graph_style)
                count[0] += 1
                progress.setValue(count[0])
                QApplication.processEvents()
                return result

            self.graph.add_node = patched_add_node
            try:
                self.graph.deserialize_session(graph_data)
            finally:
                self.graph.add_node = original_add_node
                progress.close()

            self._finish_loading(runtime_data, node_status_data, file_path)
        except Exception as e:
            logger.error(f"❌ 加载失败: {traceback.format_exc()}")
            MessageManager.error("加载失败", f"工作流加载失败: {str(e)}", self.parent)

    def _finish_loading(self, runtime_data, node_status_data, file_path):
        self.parent._setup_pipeline_style()

        env = runtime_data.get("environment")
        if env:
            for i in range(self.env_manager.env_combo.count()):
                if self.env_manager.env_combo.itemData(i) == env:
                    self.env_manager.env_combo.setCurrentIndex(i)
                    break

        for node in self.graph.all_nodes():
            full_path = getattr(node, 'FULL_PATH', 'unknown')
            stable_key = f"{full_path}||{node.name()}"
            node_status = node_status_data.get(stable_key, {})
            node._input_values = deserialize_from_json(node_status.get("node_inputs", {}))
            node._output_values = deserialize_from_json(node_status.get("node_outputs", {}))
            node.column_select = node_status.get("column_select", {})
            custom_props = node_status.get("custom_property", {})
            for key, value in custom_props.items():
                if not node.has_property(key):
                    node.create_property(key, value)
                else:
                    node.set_property(key, value)
            status_str = node_status.get("node_states", "unrun") or "unrun"
            from app.nodes.status_node import NodeStatus
            status_enum = getattr(NodeStatus, f"NODE_STATUS_{status_str.upper()}", NodeStatus.NODE_STATUS_UNRUN)
            self.node_status[node.id] = status_enum
            if hasattr(node, 'status'):
                node.status = status_enum

        self.parent._node_id_cache = {node.id: node for node in self.graph.all_nodes()}
        self.parent._node_id_cache_valid = True
        self.parent.ui_manager.create_name_label()
        self.parent._delayed_fit_view()
        MessageManager.success("加载成功", "工作流加载成功！", self.parent)

        # 更新路径
        self.parent.file_path = Path(file_path)
        self.parent.workflow_name = self.parent.file_path.stem.split(".")[0]

    def extract_graph_info(self, nodes=None):
        """过滤掉 session data 中的复杂/内部信息，生成面向大模型的结构化画布描述。
        若 nodes 为 None，总结整张画布；否则仅总结指定节点及其连接上下文。
        """
        if nodes is None:
            nodes = self.graph.all_nodes()

        # 按拓扑顺序或用户顺序组织节点（这里按原顺序）
        graph_desc_parts = []

        for node in nodes:
            name = node.name()
            node_type = getattr(node.model, "node_type", "未知类型")  # 建议你节点有 type 字段
            custom_props = {
                k: v for k, v in node.model._custom_prop.items()
                if k not in {"persistent_id", "temp_data", "cache", "global_variable", "debug_code"}  # 可扩展过滤
            }

            # 输入端口：聚合连接信息
            inputs = []
            for port in node.input_ports():
                conn_desc = []
                for upstream in port.connected_ports():
                    conn_desc.append(f"[{upstream.node().name()}](画布节点) → {upstream.name()}")
                if conn_only := ", ".join(conn_desc):
                    inputs.append(f"- **{port.name()}** ({port.model.type_}) ← {conn_only}")
                else:
                    inputs.append(f"- **{port.name()}** ({port.model.type_}) ← 无连接")

            # 输出端口
            outputs = []
            for port in node.output_ports():
                conn_desc = []
                for downstream in port.connected_ports():
                    conn_desc.append(f"[{downstream.node().name()}](画布节点) ← {downstream.name()}")
                if conn_only := ", ".join(conn_desc):
                    outputs.append(f"- **{port.name()}** ({port.model.type_}) → {conn_only}")
                else:
                    outputs.append(f"- **{port.name()}** ({port.model.type_}) → 无连接")

            # 构建节点描述块
            node_block = f"""### [{name}](画布节点)
- **类型**: {node_type}
- **属性**: {custom_props if custom_props else "无"}
- **输入**:
{"; ".join(inputs) if inputs else "  无输入端口"}
- **输出**:
{"; ".join(outputs) if outputs else "  无输出端口"}
    """
            graph_desc_parts.append(node_block)

        final_desc = """## 画布结构说明
以下描述了当前画布中各节点的类型、配置属性及其数据流连接关系。
- [节点名称](画布节点) 代表引用的原画布节点名
- 箭头 `←` 表示数据来源，`→` 表示数据去向。
- 端口类型（如 `str`, `DataFrame`, `image_base64`）用于提示数据格。

## 节点详情
    """
        final_desc += "\n".join(graph_desc_parts)
        # + """\n\n## 回复语法规范
        # - 当回答中需要使用任何已有节点名时，请使用 `[节点名称](画布节点)` 语法, (画布节点)是当前工具名称，属于固定前缀，节点名放到后前面中括号中。
        # - 除此之外已有节点名绝对不能单独以文本形式输出\n\n"""

        return final_desc