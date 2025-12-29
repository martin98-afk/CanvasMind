# -*- coding: utf-8 -*-
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from app.nodes.base_node import BasicNodeWithGlobalProperty, CustomBaseNode
from app.nodes.status_node import NoStatusNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.html_widget import HtmlWidgetWrapper


# ✅ 信号类必须独立于非-QObject 节点
class ChartNodeSignals(QObject):
    htmlReady = pyqtSignal(str)


def create_chart_node(parent_window):

    class ChartNode(CustomBaseNode, NoStatusNode, BasicNodeWithGlobalProperty):
        category: str = "可视化"
        __identifier__ = 'visualize'
        NODE_NAME = 'HTML 图表'
        FULL_PATH = f"{category}/{NODE_NAME}"

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.set_icon(":/icons/图表")
            self.model.port_deletion_allowed = False
            self._node_logs = ""
            self._output_values = {}
            self._input_values = {}
            self.view.set_align("center")

            # 添加输入端口
            self.add_input('html', False)

            # 添加图表控件
            chart_widget = HtmlWidgetWrapper(
                parent=self.view,
                name="chart_display",
                default="<center><small>等待输入 HTML</small></center>",
                window=parent_window
            )
            self.add_custom_widget(chart_widget)

            # ✅ 创建信号对象（必须是 QObject 子类实例）
            self.signals = ChartNodeSignals()
            # 连接信号到槽（确保在主线程执行）
            self.signals.htmlReady.connect(self._on_html_ready, Qt.QueuedConnection)

            self.set_disabled(False)

        def _on_html_ready(self, html: str):
            """主线程中更新图表"""
            chart_widget = self.get_widget("chart_display")
            if chart_widget:
                chart_widget.set_value(html)

        def _trigger_chart_update(self):
            """统一触发 HTML 更新"""
            html_val = ""
            port = self.get_input("html")
            if port and port.connected_ports():
                connected = port.connected_ports()[0]
                upstream_node = connected.node()
                html_val = upstream_node._output_values.get(connected.name(), "")
            # ✅ 通过信号对象 emit
            self.signals.htmlReady.emit(html_val)

        def on_input_connected(self, in_port, out_port):
            super().on_input_connected(in_port, out_port)
            self._trigger_chart_update()

        def on_input_disconnected(self, in_port, out_port):
            super().on_input_disconnected(in_port, out_port)
            self._trigger_chart_update()

        def set_input_value(self, port_name, value):
            super().set_input_value(port_name, value)
            if port_name == "html":
                self._trigger_chart_update()

        def execute_sync(self, *args, **kwargs):
            self.init_logger()
            html_val = ""
            port = self.get_input("html")
            if port and port.connected_ports():
                connected = port.connected_ports()[0]
                upstream_node = connected.node()
                html_val = upstream_node._output_values.get(connected.name(), "")
            # ✅ 安全 emit
            self.signals.htmlReady.emit(html_val)
            self.clear_output_value()

    return ChartNode