# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType


class Component(BaseComponent):
    name = "ECharts 图表绘制"
    category = "数据可视化"
    description = "支持柱状图、折线图、饼图、散点图，输出 HTML 嵌入片段"
    requirements = "numpy,pyecharts"

    inputs = [
        PortDefinition(name="x_data", label="X 轴数据", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="y_data", label="Y 轴数据（支持多组）", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.TEXT),
    ]

    properties = {
        "chart_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="bar",
            label="图表类型",
            choices=["bar", "line", "pie", "scatter"]
        ),
        "title": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="图表标题",
        ),
    }

    def _to_list(self, data):
        """将 np.ndarray / list / scalar 转为 list"""
        import numpy as np
        if data is None:
            return []
        if isinstance(data, np.ndarray):
            return np.squeeze(data).tolist()
        elif isinstance(data, (list, tuple)):
            return list(data)
        else:
            return [data]  # 标量转为单元素列表

    def run(self, params, inputs=None):
        import numpy as np
        from pyecharts import options as opts
        from pyecharts.charts import Bar, Line, Pie, Scatter
        from pyecharts.globals import ThemeType
        import json

        inputs = inputs or {}
        chart_type = params.get("chart_type", "bar")
        title = params.get("title", "ECharts 图表")
        try:
            width = int(params.get("width", "700"))
            height = int(params.get("height", "500"))
        except (ValueError, TypeError):
            width, height = 700, 500

        # 解析输入（支持 np.array）
        x_raw = inputs.get("x_data")
        y_raw = inputs.get("y_data")

        x_data = self._to_list(x_raw)
        y_data_raw = self._to_list(y_raw)

        # 处理 y_data：确保是二维列表
        if not y_data_raw:
            if x_data:
                y_data = [[1 for _ in x_data]]
            else:
                x_data = ["A", "B", "C"]
                y_data = [[10, 20, 30]]
        else:
            # 判断是否多组：检查第一个元素是否是 list
            if y_data_raw and isinstance(y_data_raw[0], (list, tuple, np.ndarray)):
                y_data = [self._to_list(series) for series in y_data_raw]
            else:
                y_data = [y_data_raw]  # 单组

        # 如果 x_data 为空，用索引
        if not x_data:
            x_data = list(range(1, len(y_data[0]) + 1))

        # 补全系列名称
        series_names = [f"系列{i+1}" for i in range(len(y_data))]
        init_opts = opts.InitOpts(
            width=f"{width}px",
            height=f"{height}px",
            theme=ThemeType.DARK,          # ← 启用深色主题
            bg_color="transparent"         # ← 背景透明，融入节点深色背景
        )
        # 创建图表
        if chart_type == "bar":
            chart = Bar(init_opts=init_opts)
        elif chart_type == "line":
            chart = Line(init_opts=init_opts)
        elif chart_type == "pie":
            chart = Pie(init_opts=init_opts)
        elif chart_type == "scatter":
            chart = Scatter(init_opts=init_opts)
        else:
            chart = Bar(init_opts=init_opts)

        # 设置数据
        if chart_type == "pie":
            # 饼图：x 为标签，y[0] 为值
            values = y_data[0] if y_data else []
            if len(x_data) != len(values):
                min_len = min(len(x_data), len(values))
                x_data = x_data[:min_len]
                values = values[:min_len]
            pie_data = list(zip(x_data, values))
            chart.add("", pie_data)
        else:
            # 非饼图：设置 X 轴
            chart.add_xaxis(x_data)
            for i, y_series in enumerate(y_data):
                name = series_names[i]
                if chart_type == "scatter":
                    # 散点图：数据为 [(x0,y0), (x1,y1), ...]
                    if len(x_data) != len(y_series):
                        min_len = min(len(x_data), len(y_series))
                        x_scatter = x_data[:min_len]
                        y_scatter = y_series[:min_len]
                    else:
                        x_scatter, y_scatter = x_data, y_series
                    scatter_data = list(zip(x_scatter, y_scatter))
                    chart.add(name, scatter_data)
                else:
                    # 柱状图/折线图
                    if len(x_data) != len(y_series):
                        min_len = min(len(x_data), len(y_series))
                        y_series = y_series[:min_len]
                    chart.add_yaxis(name, y_series)

        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title=title,
                title_textstyle_opts=opts.TextStyleOpts(color="#ffffff")
            ),
            legend_opts=opts.LegendOpts(
                is_show=True,
                textstyle_opts=opts.TextStyleOpts(color="#cccccc")
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="item",
                textstyle_opts=opts.TextStyleOpts(color="#000000"),
                background_color="#ffffff",
                border_color="#666666"
            ),
            toolbox_opts=opts.ToolboxOpts(is_show=False),
            # 坐标轴样式（非饼图）
            xaxis_opts=opts.AxisOpts(
                axislabel_opts=opts.LabelOpts(color="#aaaaaa"),
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#555555")
                ),
                axistick_opts=opts.AxisTickOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#555555")
                )
            ) if chart_type not in ["pie"] else None,
            yaxis_opts=opts.AxisOpts(
                axislabel_opts=opts.LabelOpts(color="#aaaaaa"),
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#555555")
                ),
                axistick_opts=opts.AxisTickOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#555555")
                ),
                splitline_opts=opts.SplitLineOpts(
                    is_show=True,
                    linestyle_opts=opts.LineStyleOpts(color="#333333", width=1)
                )
            ) if chart_type not in ["pie"] else None,
        )

        html_str = chart.render_embed()
        return {"output1": html_str}
    

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
