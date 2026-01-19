# -*- coding: utf-8 -*-
from app.plugins.base import DisplayPlugin
from app.widgets.node_widget.propeprty_widgets.text_edit_widget import TextWidgetWrapper
from app.components.base import PropertyType


class TextDisplayPlugin(DisplayPlugin):
    plugin_id = "display_str"

    def render(self, node, port_name, data):
        key = f"text_{port_name}"
        if key not in node._inline_widgets:
            widget = TextWidgetWrapper(parent=node.view, name=key, default=f"预览: {port_name}",
                                       type=PropertyType.MULTILINE, window=node.parent_window)
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            node._inline_widgets[key].set_value(data)