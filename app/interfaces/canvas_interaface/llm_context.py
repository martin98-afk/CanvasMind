import base64

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QImage, QPainter

from app.interfaces.canvas_interaface.constants import LLM_GRAPH_CONTEXT_NORMS, NODE_CREATE_CONTEXT_NORMS
from app.interfaces.canvas_interaface.widgets.ui_setup import CanvasUISetUp
from app.interfaces.canvas_interaface.utils.canvas_io import CanvasIO
from app.scan_components import ComponentScanner
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.context_selector import ContextRegistry


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
        self.context_register.register("画布节点图像", self.extract_graph_image, self.select_node_by_name)
        self.context_register.register("全局变量", self.extract_var_info, lambda *args: None)
        self.context_register.register("画布节点", self.extract_graph_info, self.select_node_by_name)
        self.context_register.register("组件信息", self.get_component_info, self.parent.show_category_dialog)

    def _extract_graph_info(self, nodes=None):
        """生成面向大模型的画布结构描述，以无箭头的 Markdown 表格形式呈现。"""
        if nodes is None:
            nodes = self.graph.all_nodes()

        rows = [
            "## 画布结构说明",
            "下表描述了画布中各节点的类型、原组件、配置属性、输入来源及输出去向。",
            "- 端口格式为：`端口名 (数据类型)`。",
            "",
            "| 节点名称 | 类型 | 原组件名 | 属性 | 输入来源 | 输出去向 |",
            "|----------|------|--------|------|----------|----------|"
        ]

        for node in nodes:
            if not hasattr(node, 'input_ports'):
                continue
            name = f"[{node.name()}](jump)"
            # ✅ 新增：原组件名称
            component_name = "/"
            node_type = "未知"
            if hasattr(node, 'FULL_PATH'):
                node_type = node.FULL_PATH.split("/")[0]
                component_name = str(node.FULL_PATH.split("/")[1])
            # 属性：过滤 + 格式化
            custom_props = {
                k: v for k, v in node.model._custom_prop.items()
                if k not in {"persistent_id", "temp_data", "cache", "global_variable"}
            }
            if custom_props:
                props_str = "; ".join(f"{k}={repr(v) if isinstance(v, str) else v}" for k, v in custom_props.items())
            else:
                props_str = "/"

            # 输入来源：端口名 (类型): 节点:上游节点名 输出端口:端口名
            input_lines = []
            for port in node.input_ports():
                conns = []
                for upstream in port.connected_ports():
                    upstream_nodename = f"[{upstream.node().name()}](jump)"
                    conns.append(f"节点:{upstream_nodename} 输出端口:{upstream.name()}")
                if conns:
                    input_lines.append(f"{port.name()} ({port.model.type_}): {', '.join(conns)}")
                else:
                    input_lines.append(f"{port.name()} ({port.model.type_}): /")
            inputs_str = "<br>".join(input_lines) if input_lines else "/"

            # 输出去向：端口名 (类型): 节点:下游节点名 输入端口:端口名
            output_lines = []
            for port in node.output_ports():
                conns = []
                for downstream in port.connected_ports():
                    # ✅ 修复：这里必须用 downstream，不是 upstream！
                    downstream_nodename = f"[{downstream.node().name()}](jump)"
                    conns.append(f"节点:{downstream_nodename} 输入端口:{downstream.name()}")
                if conns:
                    output_lines.append(f"{port.name()} ({port.model.type_}): {', '.join(conns)}")
                else:
                    output_lines.append(f"{port.name()} ({port.model.type_}): /")
            outputs_str = "<br>".join(output_lines) if output_lines else "/"

            row = f"| {name} | {node_type} | {component_name} | {props_str} | {inputs_str} | {outputs_str} |"
            rows.append(row)

        return "\n".join(rows)

    def extract_graph_info(self):
        response = "# 画布上下文信息\n{graph_info}\n\n# 画布上下文交互规范\n{LLM_GRAPH_CONTEXT_NORMS}\n\n"""
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
        response = "# 组件上下文信息\n{component_info}\n\n# 组件上下文交互规范\n{NODE_CREATE_CONTEXT_NORMS}\n\n"
        selected_categories = self.ui_manager.nav_view._selected_categories
        component_map, _ = ComponentScanner().get_components()
        selected_components = {
            key: value
            for key, value in component_map.items()
            if value.category in selected_categories
        }

        # 构建 Markdown 表格
        rows = []
        for value in selected_components.values():
            inputs_str = "; ".join([f"{item.label} ({item.type.value})" for item in value.inputs]) or "无"
            outputs_str = "; ".join([f"{item.label} ({item.type.value})" for item in value.outputs]) or "无"
            props_str = "; ".join([
                f"{item.label} ({item.type.value}, 默认: {item.default})"
                for item in value.properties.values()
            ]) or "无"

            # 转义竖线和换行，避免破坏表格
            name = value.name.replace("|", "\\|")
            category = value.category.replace("|", "\\|")
            description = value.description.replace("|", "\\|").replace("\n", " ")
            inputs_str = inputs_str.replace("|", "\\|")
            outputs_str = outputs_str.replace("|", "\\|")
            props_str = props_str.replace("|", "\\|")

            rows.append(f"| {name} | {category} | {description} | {inputs_str} | {outputs_str} | {props_str} |")

        if rows:
            header = "| 名称 | 类别 | 描述 | 输入 | 输出 | 属性 |"
            separator = "|---|---|---|---|---|---|"
            component_info = "\n".join([header, separator] + rows)
        else:
            component_info = "暂无组件"

        return (
            f"{len(selected_components)}x 组件",
            response.format(NODE_CREATE_CONTEXT_NORMS=NODE_CREATE_CONTEXT_NORMS, component_info=component_info),
            selected_categories
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
