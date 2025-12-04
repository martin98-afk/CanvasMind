from app.interfaces.canvas_interaface.constants import LLM_GRAPH_CONTEXT_NORMS
from app.interfaces.canvas_interaface.widgets.ui_setup import CanvasUISetUp
from app.interfaces.canvas_interaface.utils.canvas_io import CanvasIO
from app.scan_components import ComponentScanner
from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextRegistry


class LLMContextProvider:
    def __init__(
        self,
        graph,
        global_variables,
        canvas_io: CanvasIO,
        ui_manager: CanvasUISetUp,
        node_operations,
        select_node_callback
    ):
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
        self.context_register.register("全局变量", self.extract_var_info, lambda *args, **kwargs: None)
        self.context_register.register("组件信息", self.get_component_info, lambda *args, **kwargs: None)

    def extract_graph_info(self):
        response = "# 画布上下文引用规范\n{LLM_GRAPH_CONTEXT_NORMS}\n\n# 画布上下文信息\n{graph_info}"""
        selected_nodes = self.graph.selected_nodes()
        if len(selected_nodes) > 0:
            graph_info = self.canvas_io.extract_graph_info(selected_nodes)
            return (
                f"画布选中节点 {len(selected_nodes)} 个" if len(selected_nodes) > 1 else f"节点: {selected_nodes[0].name()}",
                response.format(
                    LLM_GRAPH_CONTEXT_NORMS=LLM_GRAPH_CONTEXT_NORMS,
                    graph_info=graph_info
                ),
                [node.name() for node in selected_nodes]
            )
        else:
            return f"当前画布所有节点", response.format(
                    LLM_GRAPH_CONTEXT_NORMS=LLM_GRAPH_CONTEXT_NORMS,
                    graph_info=self.canvas_io.extract_graph_info()
                ), None

    def extract_var_info(self):
        return "全局变量", self.global_variables.to_dict(), None

    def get_component_info(self):
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
        return f"{len(selected_components)}x 组件", component_info, None