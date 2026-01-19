import os
import base64
from PyQt5.QtGui import QImage

from app.plugins.base import DisplayPlugin
from app.widgets.node_widget.display_widgets.image_widget import ImageWidgetWrapper


class ImageDisplayPlugin(DisplayPlugin):
    plugin_id = "display_image"

    def _process_image_data(self, image_data):
        """解析逻辑内聚在插件内部"""
        if isinstance(image_data, str):
            if image_data.startswith("data:image"):
                try:
                    return QImage.fromData(base64.b64decode(image_data.split(",", 1)[1]))
                except: return None
            elif os.path.exists(image_data):
                img = QImage(image_data)
                return None if img.isNull() else img
        return image_data

    def render(self, node, port_name, data):
        key = f"preview_{port_name}"
        processed_img = self._process_image_data(data)
        if not processed_img: return

        if key not in node._inline_widgets:
            widget = ImageWidgetWrapper(parent=node.view, name=key, default=processed_img, window=node.parent_window)
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            node._inline_widgets[key].set_value(processed_img)