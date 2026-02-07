# -*- coding: utf-8 -*-
import os

from PyQt5.QtGui import QImage

from app.node_plugins.base import DisplayPlugin
from app.widgets.node_widget.display_widgets.image_gallery_widget import ImageGalleryWidgetWrapper


class ImageGalleryDisplayPlugin(DisplayPlugin):
    plugin_id = "display_image_gallery"
    plugin_name = "图片画廊插件"
    plugin_desc = "展示多张图片。输入支持：本地路径对象列表"

    # Python 侧的执行模板：假设输入变量名为 images (list of PIL/Numpy)
    # 将其全部转换为 Base64 列表传回前端
    plugin_template = """self.emit_message(
            method="display_image_gallery",
            params={"output": {"data": ["img1.png", "img2.png"], "data_type": "image_list"}},
        )
"""

    def _process_single_item(self, item):
        """解析单个图片数据 (复用之前的逻辑)"""
        if isinstance(item, QImage):
            return item

        if not isinstance(item, str):
            return item  # 交给 Widget 内部处理 (如 numpy/PIL)

        try:
            # 暂时图像列表只支持本地路径，base64传递文本信息量太大
            if os.path.exists(item):
                return item

        except Exception as e:
            print(f"[Gallery] Item error: {e}")

        return None

    def _process_data_list(self, data):
        """处理列表数据"""
        if data is None:
            return []

        # 如果不是列表，包装成列表
        if not isinstance(data, (list, tuple)):
            data = [data]

        processed_list = []
        for item in data:
            # 解析每个元素
            img = self._process_single_item(item)
            if img:
                processed_list.append(img)

        return processed_list

    def render(self, node, port_name, data):
        key = f"gallery_{port_name}"

        # 1. 预处理数据：将各种乱七八糟的输入转为 QImage 列表
        img_list = self._process_data_list(data)

        if not img_list:
            return

        # 2. 创建或更新 Widget
        if key not in node._inline_widgets:
            # 实例化包装后的 Widget
            widget = ImageGalleryWidgetWrapper(
                parent=node.view,
                name=key,
                window=node.parent_window
            )
            widget.set_value(img_list)
            # 添加到节点 UI 中 (Tab 名称通常可选 'Visual' 或 'Result')
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            # 更新已有 Widget 的数据
            node._inline_widgets[key].set_value(img_list)