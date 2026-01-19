# -*- coding: utf-8 -*-
from pyecharts import options as opts
from pyecharts.charts import Line
from pyecharts.globals import ThemeType

from app.plugins.base import DisplayPlugin
from app.widgets.node_widget.html_widget import HtmlWidgetWrapper


class ChartDisplayPlugin(DisplayPlugin):
    plugin_id = "display_html"

    def render(self, node, port_name, data):
        key = f"html_{port_name}"

        if key not in node._inline_widgets:
            widget = HtmlWidgetWrapper(parent=node.view, name=key, default=data, window=node.parent_window)
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            node._inline_widgets[key].set_value(data)