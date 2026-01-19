# -*- coding: utf-8 -*-

from app.plugins.base import DisplayPlugin
from app.widgets.node_widget.display_widgets.html_widget import HtmlWidgetWrapper


class ChartDisplayPlugin(DisplayPlugin):
    plugin_id = "display_html"

    def render(self, node, port_name, data):
        key = f"html_{port_name}"

        if key not in node._inline_widgets:
            widget = HtmlWidgetWrapper(parent=node.view, name=key, default=data, window=node.parent_window)
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            node._inline_widgets[key].set_value(data)