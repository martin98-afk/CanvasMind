# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt

from app.nodes.status_node import NoStatusNode
from app.utils.utils import draw_square_port
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.display_widgets.universal_display_widget import UniversalWidgetWrapper


def create_media_node(parent_window):

    class MediaNode(CustomBaseNode, NoStatusNode):
        category: str = "可视化"
        __identifier__ = 'visualize'
        NODE_NAME = '多媒体展示节点'
        FULL_PATH = f"{category}/{NODE_NAME}"
        description: str = "可展示 html格式的echarts图表、图片数据、语音数据、视频数据。"

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self.set_icon(":/icons/多媒体.svg")
            self.model.port_deletion_allowed = False
            # 添加输入端口
            self.add_input('data', True, painter_func=draw_square_port)

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

                # 只有在 execute 触发时，should_play 才会为 True
                if should_play:
                    media_widget.get_custom_widget().play()

        def _trigger_media_update(self, should_play=False):
            """统一触发更新"""
            port = self.get_input("data")
            if not port:
                return

            connected_ports = port.connected_ports()

            if not connected_ports:
                # 当没有连线时，显式发送 None
                self.signals.htmlReady.emit(None, False)
                return

            # 获取所有连接过来的数据
            results = []
            for cp in connected_ports:
                upstream_node = cp.node()
                # 获取上游节点的输出值
                val = upstream_node._output_values.get(cp.name())
                if val is not None:
                    results.append(val)

            # 决定发送什么数据
            if len(results) == 1:
                # 单个数据，直接发送
                data_to_send = results[0]
            elif len(results) >= 2:
                # 多个数据，发送列表（对比控件会处理前两个）
                data_to_send = results
            else:
                data_to_send = ""

            # 发送信号
            self.signals.htmlReady.emit(data_to_send, should_play)

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
            port = self.get_input("data")
            results = []
            if port:
                for cp in port.connected_ports():
                    val = cp.node()._output_values.get(cp.name())
                    if val is not None:
                        results.append(val)

            data_to_send = results if len(results) >= 2 else (results[0] if results else "")
            self.signals.htmlReady.emit(data_to_send, True)

    return MediaNode