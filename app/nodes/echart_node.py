# -*- coding: utf-8 -*-

from app.nodes.base_node import BasicNodeWithGlobalProperty, CustomBaseNode
from app.nodes.status_node import StatusNode
from app.utils.utils import resource_path, draw_square_port
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.pyecharts_widget import ChartWidgetWrapper


def create_chart_node(parent_window):

    class ChartNode(CustomBaseNode, StatusNode, BasicNodeWithGlobalProperty):
        category: str = "可视化"
        __identifier__ = 'visualize'
        NODE_NAME = 'HTML 图表'
        FULL_PATH = f"{category}/{NODE_NAME}"

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.set_icon(":/icons/图表")  # 确保图标存在
            self.model.port_deletion_allowed = False
            self._node_logs = ""
            self._output_values = {}
            self._input_values = {}
            self.view.set_align("center")

            # 添加输入端口（接收 HTML 字符串）
            self.add_input('html', False)

            # 添加图表控件到节点内部（非属性面板）
            chart_widget = ChartWidgetWrapper(
                parent=self.view,
                name="chart_display",
                label="图表预览",
                default="<center><small>等待输入 HTML</small></center>",
                window=parent_window
            )
            self.add_custom_widget(chart_widget)

            # 监听输入变化（可选：通过端口连接触发更新）
            self.set_disabled(False)
            # 注意：NodeGraphQt 不会自动调用 execute，除非在流程中。我们改为监听端口数据更新。

        def on_input_connected(self, in_port, out_port):
            super().on_input_connected(in_port, out_port)
            self._update_chart_from_input()

        def on_input_disconnected(self, in_port, out_port):
            super().on_input_disconnected(in_port, out_port)
            self._update_chart_from_input()

        def set_input_value(self, port_name, value):
            super().set_input_value(port_name, value)
            if port_name == "html":
                self._update_chart_from_input()

        def _update_chart_from_input(self):
            """从输入端口读取 html 并更新图表控件"""
            html_val = ""
            port = self.get_input("html")
            if port and port.connected_ports():
                # 假设上游节点设置了 _output_values
                connected = port.connected_ports()[0]
                upstream_node = connected.node()
                html_val = upstream_node._output_values.get(connected.name(), "")
            else:
                html_val = ""
            chart_widget = self.get_widget("chart_display")
            if chart_widget:
                chart_widget.set_value(html_val)

        def execute_sync(self, *args, **kwargs):
            # 可选：如果该节点参与执行流程
            self.init_logger()
            # 读取输入
            html_input = ""
            input_port = self.get_input("html")
            if input_port and input_port.connected_ports():
                upstream = input_port.connected_ports()[0]
                html_input = upstream.node()._output_values.get(upstream.name(), "")

            # 更新内部控件
            self._update_chart_from_input()

            # 无输出（不调用 set_output_value）
            self._output_values.clear()

    return ChartNode