import base64
import io

from PIL import Image
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QImage, QPainter

from app.interfaces.canvas_interaface.constants import LLM_GRAPH_CONTEXT_NORMS, NODE_CREATE_CONTEXT_NORMS
from app.interfaces.canvas_interaface.widgets.ui_setup import CanvasUISetUp
from app.interfaces.canvas_interaface.utils.canvas_io import CanvasIO
from app.scan_components import ComponentScanner
from app.utils.threading_utils import ThumbnailGenerator
from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextRegistry


class LLMContextProvider:
    def __init__(
            self,
            graph,
            global_variables,
            canvas_io: CanvasIO,
            ui_manager: CanvasUISetUp,
            node_operations,
            select_node_callback,
            parent
    ):
        self.parent = parent
        self.graph = graph
        self.global_variables = global_variables
        self.canvas_io = canvas_io
        self.ui_manager = ui_manager
        self.node_operations = node_operations
        self.select_node_by_name = select_node_callback

        self.context_register = ContextRegistry()
        self._register_contexts()

    def _register_contexts(self):
        """注册所有支持的大模型上下文类型"""
        self.context_register.register("画布节点", self.extract_graph_info, self.select_node_by_name)
        self.context_register.register("画布节点图像", self.extract_graph_image, self.select_node_by_name)
        self.context_register.register("全局变量", self.extract_var_info, lambda *args, **kwargs: None)
        self.context_register.register("组件信息", self.get_component_info, lambda *args, **kwargs: None)

    def _extract_graph_info(self, nodes=None):
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
                    conn_desc.append(f"[{upstream.node().name()}](jump) → {upstream.name()}")
                if conn_only := ", ".join(conn_desc):
                    inputs.append(f"- **{port.name()}** ({port.model.type_}) ← {conn_only}")
                else:
                    inputs.append(f"- **{port.name()}** ({port.model.type_}) ← 无连接")

            # 输出端口
            outputs = []
            for port in node.output_ports():
                conn_desc = []
                for downstream in port.connected_ports():
                    conn_desc.append(f"[{downstream.node().name()}](jump) ← {downstream.name()}")
                if conn_only := ", ".join(conn_desc):
                    outputs.append(f"- **{port.name()}** ({port.model.type_}) → {conn_only}")
                else:
                    outputs.append(f"- **{port.name()}** ({port.model.type_}) → 无连接")

            # 构建节点描述块
            node_block = f"""### [{name}](jump)
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
- [节点名称](jump) 代表引用的原画布存在的 节点名
- 箭头 `←` 表示数据来源，`→` 表示数据去向。
- 端口类型（如 `str`, `DataFrame`, `image_base64`）用于提示数据格。

## 节点详情
    """
        final_desc += "\n".join(graph_desc_parts)

        return final_desc

    def extract_graph_info(self):
        response = "# 画布上下文信息\n{graph_info}\n\n# 画布上下文引用规范\n{LLM_GRAPH_CONTEXT_NORMS}\n\n"""
        selected_nodes = self.graph.selected_nodes()
        if len(selected_nodes) > 0:
            graph_info = self._extract_graph_info(selected_nodes)
            return (
                f"画布选中节点 {len(selected_nodes)} 个" if len(
                    selected_nodes) > 1 else f"节点: {selected_nodes[0].name()}",
                response.format(
                    LLM_GRAPH_CONTEXT_NORMS=LLM_GRAPH_CONTEXT_NORMS,
                    graph_info=graph_info
                ),
                [node.name() for node in selected_nodes]
            )
        else:
            return f"当前画布所有节点", response.format(
                LLM_GRAPH_CONTEXT_NORMS=LLM_GRAPH_CONTEXT_NORMS,
                graph_info=self._extract_graph_info()
            ), [node.name() for node in self.graph.all_nodes()]

    def extract_var_info(self):
        return "全局变量", self.global_variables.to_dict(), None

    def get_component_info(self):
        response = "# 组件上下文信息\n{component_info}\n\n# 组件上下文引用规范\n{NODE_CREATE_CONTEXT_NORMS}\n\n"""
        selected_categories = self.ui_manager.nav_view._selected_categories
        component_map, _ = ComponentScanner().get_components()
        selected_components = {
            key: value
            for key, value in component_map.items()
            if value.category in selected_categories
        }
        component_info = "\n".join(
            [
                f"名称：{value.name}\n"
                f"类别：{value.category}\n"
                f"描述：{value.description}\n"
                f"输入：\n{';'.join([f'名称：{item.label}, 类型：{item.type.value}' for item in value.inputs])}\n"
                f"输出：\n{';'.join([f'名称：{item.label}, 类型：{item.type.value}' for item in value.outputs])}\n"
                f"属性：\n{';'.join([f'名称：{item.label}, 类型：{item.type.value} 默认：{item.default}' for key, item in value.properties.items()])}\n"
                for key, value in selected_components.items()
            ]
        )
        return (
            f"{len(selected_components)}x 组件",
            response.format(NODE_CREATE_CONTEXT_NORMS=NODE_CREATE_CONTEXT_NORMS, component_info=component_info),
            None
        )

    def extract_graph_image(self):
        # 获取场景和边界
        selected_nodes = self.graph.selected_nodes()
        if len(selected_nodes) > 0:
            nodes = selected_nodes
        else:
            nodes = self.graph.all_nodes()
        scene = self.graph.viewer().scene()
        rect = QRectF()
        for node in nodes:
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

        image.save("canvas_files/canvas_context.png", format="PNG")
        with open("canvas_files/canvas_context.png", "rb") as f:  # 注意 'rb'！
            image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        return (
            f"画布当前{len(nodes)}个节点截图",
            {"url": f"data:image/png;base64,{image_base64}", "text": LLM_GRAPH_CONTEXT_NORMS},
            [node.name() for node in nodes]
        )
