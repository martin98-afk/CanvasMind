# -*- coding: utf-8 -*-
from app.plugins.base import DisplayPlugin
from app.widgets.node_widget.propeprty_widgets.text_edit_widget import TextWidgetWrapper
from app.components.base import PropertyType


class TextDisplayPlugin(DisplayPlugin):
    plugin_id = "display_str"
    plugin_name = "文本展示插件"
    plugin_desc = "用于在节点上展示指定文本"
    plugin_template = """self.emit_message(
            method="display_str",
            params={"training_loss": {"data": "preview_text"}}
        )
"""

    def render(self, node, port_name, data):
        key = f"text_{port_name}"
        if key not in node._inline_widgets:
            widget = TextWidgetWrapper(parent=node.view, name=key, default=data,
                                       type=PropertyType.MULTILINE, window=node.parent_window)
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            node._inline_widgets[key].set_value(data)