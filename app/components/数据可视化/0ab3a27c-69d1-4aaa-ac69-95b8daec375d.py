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
    name = "Seaborn画图"
    category = "数据可视化"
    description = "使用 Seaborn 绘制图表，支持多种图表类型（线图、散点图、柱状图、热力图等）"
    requirements = " pillow, pandas,seaborn, matplotlib, numpy"
    inputs = [
        PortDefinition(name="data", label="输入数据", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
        PortDefinition(name="x", label="X轴数据", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="y", label="Y轴数据", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output", label="输出图像", type=ArgumentType.IMAGE),
    ]
    properties = {
        "title": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="标题",
        ),
        "plot_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="lineplot",
            label="图表类型",
            choices=["lineplot", "scatterplot", "barplot", "heatmap", "jointplot", "pairplot"]
        ),
        "x_label": PropertyDefinition(
            type=PropertyType.TEXT,
            default="X轴",
            label="X轴标签",
        ),
        "y_label": PropertyDefinition(
            type=PropertyType.TEXT,
            default="Y轴",
            label="Y轴标签",
        ),
        "color_": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="blue",
            label="颜色主题",
            choices=["blue", "yellow", "green", "red", "black"]
        ),
        "style": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="whitegrid",
            label="图表样式",
            choices=["darkgrid", "whitegrid", "dark", "white", "ticks"]
        ),
        "aspect": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.0",
            label="图表宽高比",
            min=0.5,
            max=3.0,
            step=0.1,
        ),
        "show_grid": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="显示网格",
        ),
        "fig_size": PropertyDefinition(
            type=PropertyType.TEXT,
            default="8,6",
            label="图像尺寸(宽,高)",
        ),
    }

    def run(self, params, inputs=None):
        import seaborn as sns
        import matplotlib.pyplot as plt
        import numpy as np
        import pandas as pd
        from PIL import Image
        import io

        # 设置中文字体支持
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'Microsoft YaHei']
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

        # 获取输入数据
        data = inputs.data
        x_data = inputs.x
        y_data = inputs.y

        # 解析图像尺寸
        fig_size_str = params.fig_size.strip()
        try:
            fig_width, fig_height = map(float, fig_size_str.split(','))
        except:
            fig_width, fig_height = 8.0, 6.0  # 默认尺寸

        # 将输入数据转换为 DataFrame
        if data is not None:
            df = pd.DataFrame(data)
        else:
            df = pd.DataFrame({
                'x': np.squeeze(x_data),
                'y': np.squeeze(y_data)
            })

        # 设置图表样式
        sns.set_style(params.style)
        sns.set_context("notebook", rc={"axes.labelsize": 14, "xtick.labelsize": 12, "ytick.labelsize": 12})

        # 创建图表
        plt.figure(figsize=(fig_width, fig_height))

        # 根据图表类型绘制
        if params.plot_type == "lineplot":
            sns.lineplot(data=df, x="x", y="y", color=params.color_)
        elif params.plot_type == "scatterplot":
            sns.scatterplot(data=df, x="x", y="y", color=params.color_)
        elif params.plot_type == "barplot":
            sns.barplot(data=df, x="x", y="y", color=params.color_)
        elif params.plot_type == "heatmap":
            # 假设数据是二维的
            if df.shape[1] > 2:
                df = df.iloc[:, :2]
            df.columns = ['x', 'y']
            df = df.pivot(index="x", columns="y", values="y")
            sns.heatmap(df, annot=True, fmt=".1f", cmap="YlGnBu")
        elif params.plot_type == "jointplot":
            sns.jointplot(data=df, x="x", y="y", kind="reg", color=params.color_)
        elif params.plot_type == "pairplot":
            sns.pairplot(df, hue="x", palette=params.color_)

        # 设置标题和轴标签
        plt.title(params.title, fontsize=14)
        plt.xlabel(params.x_label, fontsize=12)
        plt.ylabel(params.y_label, fontsize=12)

        # 显示网格
        if params.show_grid:
            plt.grid(True, linestyle='--', alpha=0.7)

        # 保存到临时文件
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        image = Image.open(buf)
        return {"output": image}