# -*- coding: utf-8 -*-
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from app.nodes.base_node import BasicNodeWithGlobalProperty, CustomBaseNode
from app.nodes.status_node import NoStatusNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.html_widget import HtmlWidgetWrapper
from app.widgets.node_widget.universal_display_widget import UniversalWidgetWrapper


def create_media_node(parent_window):

    class MediaNode(CustomBaseNode, NoStatusNode, BasicNodeWithGlobalProperty):
        category: str = "可视化"
        __identifier__ = 'visualize'
        NODE_NAME = '多媒体展示节点'
        FULL_PATH = f"{category}/{NODE_NAME}"
        description: str = "可展示 html格式的echarts图表、图片数据、语音数据、视频数据。"

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.set_icon(":/icons/多媒体.svg")
            self.model.port_deletion_allowed = False
            self._node_logs = ""
            self._output_values = {}
            self._input_values = {}
            self.view.set_align("center")

            # 添加输入端口
            self.add_input('data', False)

            # 添加图表控件
            media_widget = UniversalWidgetWrapper(
                parent=self.view,
                name="media_display",
                default="<center><small>等待输入 HTML</small></center>",
                window=parent_window
            )
            self.add_custom_widget(media_widget)

            # 连接信号到槽（确保在主线程执行）
            self.signals.htmlReady.connect(self._on_html_ready, Qt.QueuedConnection)

            self.set_disabled(False)

        def _on_html_ready(self, html: str, should_play: bool = False):
            """主线程中更新图表"""
            media_widget = self.get_widget("media_display")
            if media_widget:
                # 无论如何都更新 HTML 内容
                media_widget.set_value(html)

                # ⭐ 只有在 execute 触发时，should_play 才会为 True
                if should_play:
                    media_widget.get_custom_widget().play()

        def _trigger_media_update(self, should_play=False):
            """统一触发 HTML 更新，默认不播放"""
            html_val = ""
            port = self.get_input("data")
            if port and port.connected_ports():
                connected = port.connected_ports()[0]
                upstream_node = connected.node()
                html_val = upstream_node._output_values.get(connected.name(), "")

            # 发送数据和播放标识
            self.signals.htmlReady.emit(html_val, should_play)

        def on_input_connected(self, in_port, out_port):
            super().on_input_connected(in_port, out_port)
            # 仅仅是连线，不触发播放
            self._trigger_media_update(should_play=False)

        def on_input_disconnected(self, in_port, out_port):
            super().on_input_disconnected(in_port, out_port)
            # 断开连接，不触发播放
            self._trigger_media_update(should_play=False)

        def set_input_value(self, port_name, value):
            super().set_input_value(port_name, value)
            if port_name == "data":
                # 值改变（非执行状态），不触发播放
                self._trigger_media_update(should_play=False)

        def execute_sync(self, *args, **kwargs):
            self.init_logger()
            html_val = ""
            port = self.get_input("data")
            if port and port.connected_ports():
                connected = port.connected_ports()[0]
                upstream_node = connected.node()
                html_val = upstream_node._output_values.get(connected.name(), "")

            # ✅ 只有在这里，我们显式传入 True 触发播放
            self.signals.htmlReady.emit(html_val, True)
            self.clear_output_value()

    return MediaNode