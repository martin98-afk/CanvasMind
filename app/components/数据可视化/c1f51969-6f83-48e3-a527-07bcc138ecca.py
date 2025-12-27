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
    name = "损失函数与准确率双Y轴图"
    category = "数据可视化"
    description = "双Y轴图表：左侧显示损失函数值，右侧显示准确率，共用训练轮次X轴"
    requirements = "pyecharts,numpy"

    inputs = [
        PortDefinition(name="loss_data", label="损失函数值", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="accuracy_data", label="准确率值", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="output1", label="输出HTML", type=ArgumentType.TEXT),
    ]

    properties = {
        "title": PropertyDefinition(
            type=PropertyType.TEXT,
            default="训练过程：损失与准确率",
            label="图表标题",
        ),
        "widt": PropertyDefinition(
            type=PropertyType.RANGE,
            default="800.0",
            label="图表宽度",
            min=400.0,
            max=1200.0,
            step=100.0,
        ),
        "heigh": PropertyDefinition(
            type=PropertyType.RANGE,
            default="500.0",
            label="图表高度",
            min=300.0,
            max=1000.0,
            step=50.0,
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
            return [data]

    def run(self, params, inputs=None):
        import numpy as np
        from pyecharts import options as opts
        from pyecharts.charts import Line
        from pyecharts.globals import ThemeType
        import json

        inputs = inputs or {}
        title = params.get("title", "训练过程：损失与准确率")
        try:
            width = int(params.get("widt", "800"))
            height = int(params.get("heigh", "500"))
        except (ValueError, TypeError):
            width, height = 800, 500

        # 解析输入数据
        loss_raw = inputs.get("loss_data")
        acc_raw = inputs.get("accuracy_data")

        loss_data = self._to_list(loss_raw)
        acc_data = self._to_list(acc_raw)

        # 确保数据长度一致，补全或截断
        min_len = min(len(loss_data), len(acc_data))
        if min_len == 0:
            # 默认数据
            x_data = list(range(1, 11))
            loss_data = [0.8, 0.7, 0.6, 0.5, 0.4, 0.35, 0.3, 0.28, 0.25, 0.22]
            acc_data = [0.5, 0.55, 0.6, 0.65, 0.7, 0.72, 0.75, 0.78, 0.8, 0.82]
        else:
            x_data = list(range(1, min_len + 1))
            loss_data = loss_data[:min_len]
            acc_data = acc_data[:min_len]

        # 创建图表
        chart = Line(init_opts=opts.InitOpts(
            width=f"{width}px",
            height=f"{height}px",
            theme=ThemeType.DARK,
            bg_color="transparent"
        ))

        # 添加损失函数（左侧 Y 轴）
        chart.add_xaxis(x_data)
        chart.add_yaxis(
            series_name="损失函数",
            y_axis=loss_data,
            yaxis_index=0,  # 左侧 Y 轴
            color="#e74c3c",
            linestyle_opts=opts.LineStyleOpts(width=2),
            label_opts=opts.LabelOpts(is_show=False)
        )

        # 添加准确率（右侧 Y 轴）
        chart.add_yaxis(
            series_name="准确率",
            y_axis=acc_data,
            yaxis_index=1,  # 右侧 Y 轴
            color="#2ecc71",
            linestyle_opts=opts.LineStyleOpts(width=2),
            label_opts=opts.LabelOpts(is_show=False)
        )

        # 设置双 Y 轴
        chart.extend_axis(
            yaxis=opts.AxisOpts(
                name="损失函数",
                type_="value",
                position="right",
                axislabel_opts=opts.LabelOpts(color="#e74c3c"),
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#e74c3c")
                ),
                axistick_opts=opts.AxisTickOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#e74c3c")
                ),
                splitline_opts=opts.SplitLineOpts(
                    is_show=True,
                    linestyle_opts=opts.LineStyleOpts(color="#333333", width=1)
                )
            )
        )
        chart.extend_axis(
            yaxis=opts.AxisOpts(
                name="准确率",
                type_="value",
                position="right",
                axislabel_opts=opts.LabelOpts(color="#2ecc71"),
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#2ecc71")
                ),
                axistick_opts=opts.AxisTickOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#2ecc71")
                ),
                splitline_opts=opts.SplitLineOpts(
                    is_show=True,
                    linestyle_opts=opts.LineStyleOpts(color="#333333", width=1)
                )
            )
        )

        # 全局配置
        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title="损失函数与准确率曲线",
                title_textstyle_opts=opts.TextStyleOpts(color="#ffffff")
            ),
            legend_opts=opts.LegendOpts(
                is_show=True,
                textstyle_opts=opts.TextStyleOpts(color="#cccccc")
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="shadow",
                textstyle_opts=opts.TextStyleOpts(color="#000000"),
                background_color="#ffffff",
                border_color="#666666"
            ),
            toolbox_opts=opts.ToolboxOpts(is_show=False),
            xaxis_opts=opts.AxisOpts(
                type_="category",
                axislabel_opts=opts.LabelOpts(color="#aaaaaa"),
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#555555")
                ),
                axistick_opts=opts.AxisTickOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#555555")
                )
            ),
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
            )
        )

        # 渲染输出
        html_str = chart.render_embed()
        return {"output1": html_str}