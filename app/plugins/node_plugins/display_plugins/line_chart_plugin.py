# -*- coding: utf-8 -*-
from pyecharts import options as opts
from pyecharts.charts import Line
from pyecharts.globals import ThemeType

from app.plugins.node_plugins.base import DisplayPlugin
from app.widgets.node_widget.display_widgets.html_widget import HtmlWidgetWrapper


class ChartDisplayPlugin(DisplayPlugin):
    plugin_id = "display_list"
    plugin_name = "echarts折线图展示"
    plugin_desc = "用于在节点上展示指定echarts折现"
    plugin_template = """self.emit_message(
            method="display_list",
            params={"training_loss": [1,2,3,4,5],"accuracy": [5,6,7,8,9]}
        )
"""

    def _generate_html(self, title, data):
        """渲染逻辑内聚在插件内部"""
        if not isinstance(data, list) or not data: return ""

        # 采样逻辑防止 WebEngine 崩溃
        display_data = data
        if len(data) > 500:
            step = len(data) // 500
            display_data = data[::step]

        x_data = list(range(len(display_data)))
        chart = Line(
            init_opts=opts.InitOpts(width="500px", height="280px", theme=ThemeType.DARK, bg_color="transparent"))
        chart.add_xaxis(x_data).add_yaxis(series_name=title, y_axis=display_data, is_smooth=True, symbol="none")
        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title, title_textstyle_opts=opts.TextStyleOpts(font_size=12, color="#eee")),
            legend_opts=opts.LegendOpts(is_show=False)
        )
        return chart.render_embed()

    def render(self, node, port_name, data):
        key = f"chart_{port_name}"
        html_content = self._generate_html(port_name, data)

        if key not in node._inline_widgets:
            widget = HtmlWidgetWrapper(parent=node.view, name=key, window=node.parent_window)
            node._add_inline_widget(key, widget, tab='Visual')
        else:
            node._inline_widgets[key].set_value(html_content)