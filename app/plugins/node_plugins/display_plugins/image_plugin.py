# -*- coding: utf-8 -*-
import os
import base64
import requests
from PyQt5.QtGui import QImage

from app.plugins.node_plugins.base import DisplayPlugin
from app.widgets.node_widget.display_widgets.image_widget import ImageWidgetWrapper


class ImageDisplayPlugin(DisplayPlugin):
    plugin_id = "display_image"
    plugin_name = "图片展示插件"
    # 更新描述，提示支持的格式
    plugin_desc = "支持展示图片。输入格式支持：Base64字符串(data:image/jpeg;base64,{b64_str})、本地文件绝对路径(path)、网络URL(http/https)"

    plugin_template = """buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        b64_str = base64.b64encode(buffer.getvalue()).decode()
        self.emit_message(
            method="display_image",
            params={"output": {"data": f"data:image/jpeg;base64,{b64_str}", "data_type": "image"}},
        )
"""

    def _process_image_data(self, image_data):
        """
        解析逻辑：
        1. 判断是否为 Base64
        2. 判断是否为 URL (http/https)
        3. 判断是否为 本地路径
        """
        if not isinstance(image_data, str):
            return image_data

        try:
            # Case 1: Base64 字符串
            if image_data.startswith("data:image"):
                try:
                    # 分割 data:image/jpeg;base64,xxxx 这种格式
                    header, context = image_data.split(",", 1)
                    return QImage.fromData(base64.b64decode(context))
                except Exception as e:
                    print(f"[ImageDisplayPlugin] Base64 decode error: {e}")
                    return None

            # Case 2: 网络 URL (新增)
            elif image_data.startswith(("http://", "https://")):
                try:
                    # 设置超时，防止界面长期卡死
                    response = requests.get(image_data, timeout=3)
                    response.raise_for_status()  # 检查 404 等错误
                    img = QImage.fromData(response.content)
                    return None if img.isNull() else img
                except Exception as e:
                    print(f"[ImageDisplayPlugin] URL download error: {e}")
                    return None

            # Case 3: 本地路径
            # os.path.exists 对网络路径可能会返回 False，所以放在最后
            elif os.path.exists(image_data):
                img = QImage(image_data)
                return None if img.isNull() else img

            else:
                print(f"[ImageDisplayPlugin] Invalid image path or data: {image_data[:50]}...")
                return None

        except Exception as e:
            print(f"[ImageDisplayPlugin] Unexpected error: {e}")
            return None

    def render(self, node, port_name, data):
        key = f"preview_{port_name}"

        # 获取处理后的 QImage 对象
        processed_img = self._process_image_data(data)

        if not processed_img:
            return

        if key not in node._inline_widgets:
            widget = ImageWidgetWrapper(
                parent=node.view,
                name=key,
                default=processed_img,
                window=node.parent_window
            )
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            node._inline_widgets[key].set_value(processed_img)