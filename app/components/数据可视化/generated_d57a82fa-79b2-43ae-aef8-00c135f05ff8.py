# -*- coding: utf-8 -*-
import importlib.util
import pathlib
base_path = pathlib.Path(__file__).parent.parent / "base.py"
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
    name = "Matplotlib画图"
    category = "数据可视化"
    description = "使用Matplotlib绘制图表，支持多维数组矩阵图"
    requirements = "Pillow,numpy,matplotlib"
    inputs = [
        PortDefinition(name="x", label="输入1", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="y", label="输入2", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
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
        "xlabel": PropertyDefinition(
            type=PropertyType.TEXT,
            default="X轴",
            label="X轴标签",
        ),
        "ylabel": PropertyDefinition(
            type=PropertyType.TEXT,
            default="Y轴",
            label="Y轴标签",
        ),
        "plot_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="折线图",
            label="绘制方式",
            choices=["散点图", "折线图", "柱状图", "填充图"]
        ),
        "line_color": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="blue",
            label="线条颜色",
            choices=["blue", "yellow", "green", "red", "black"]
        ),
        "line_width": PropertyDefinition(
            type=PropertyType.RANGE,
            default=1.0,
            label="线条宽度",
            min=0.1,
            max=10.0,
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
        "auto_arrange": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="自动排列多维数据",
        ),
    }

    def run(self, params, inputs=None):
        import matplotlib.pyplot as plt
        from PIL import Image
        import io
        import numpy as np

        # 设置中文字体支持
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'Microsoft YaHei']
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

        # 获取输入数据
        x_data = inputs.x
        y_data = inputs.y

        # 解析图像尺寸
        fig_size_str = params.fig_size.strip()
        try:
            fig_width, fig_height = map(float, fig_size_str.split(','))
        except:
            fig_width, fig_height = 8.0, 6.0  # 默认尺寸

        # 转换为numpy数组以处理多维情况
        x_data = np.array(x_data)
        y_data = np.array(y_data)

        # 检查是否为多维数组
        if len(x_data.shape) > 1 or len(y_data.shape) > 1:
            # 处理多维数组
            if params.auto_arrange:
                # 计算子图布局
                n_cols = x_data.shape[1]
                n_rows = y_data.shape[1]

                # 创建子图
                fig, axes = plt.subplots(n_rows, n_cols, figsize=(fig_width, fig_height))

                # 绘制每个子图
                for i in range(n_cols):
                    for j in range(n_rows):
                        ax = axes[i][j]
                        
                        # 获取当前子数组
                        if len(x_data.shape) > 1:
                            current_x = x_data[:, i] if i < x_data.shape[1] else x_data[:, -1]
                        else:
                            current_x = x_data
                            
                        if len(y_data.shape) > 1:
                            current_y = y_data[:, j] if j < y_data.shape[1] else y_data[:, -1]
                        else:
                            current_y = y_data
    
                        # 根据绘制方式绘制图表
                        if params.plot_mode == "折线图":
                            ax.plot(current_x, current_y,
                                    color=params.line_color,
                                    linewidth=params.line_width)
                        elif params.plot_mode == "散点图":
                            ax.scatter(current_x, current_y,
                                       c=params.line_color,
                                       s=50)
                        elif params.plot_mode == "柱状图":
                            ax.bar(current_x, current_y,
                                   color=params.line_color,
                                   width=max(0.1, (max(current_x) - min(current_x)) / len(current_x) * 0.8))
                        elif params.plot_mode == "填充图":
                            ax.fill_between(current_x, current_y,
                                            color=params.line_color,
                                            alpha=0.5)
                            ax.plot(current_x, current_y,
                                    color=params.line_color,
                                    linewidth=params.line_width)
    
                        # 设置子图标题
                        ax.set_title(f'子图 {i+1}')
                        ax.set_xlabel(params.xlabel)
                        ax.set_ylabel(params.ylabel)
                        if params.show_grid:
                            ax.grid(True, linestyle='--', alpha=0.7)

                plt.suptitle(params.title, fontsize=14)
                plt.tight_layout()
            else:
                # 不自动排列，将多维数据展平处理
                x_flat = x_data.flatten()
                y_flat = y_data.flatten()

                # 创建图表
                plt.figure(figsize=(fig_width, fig_height))

                # 根据绘制方式绘制图表
                if params.plot_mode == "折线图":
                    plt.plot(x_flat, y_flat,
                             color=params.line_color,
                             linewidth=params.line_width)
                elif params.plot_mode == "散点图":
                    plt.scatter(x_flat, y_flat,
                                c=params.line_color,
                                s=50)
                elif params.plot_mode == "柱状图":
                    plt.bar(x_flat, y_flat,
                            color=params.line_color,
                            width=max(0.1, (max(x_flat) - min(x_flat)) / len(x_flat) * 0.8))
                elif params.plot_mode == "填充图":
                    plt.fill_between(x_flat, y_flat,
                                     color=params.line_color,
                                     alpha=0.5)
                    plt.plot(x_flat, y_data,
                             color=params.line_color,
                             linewidth=params.line_width)

                # 设置标题和轴标签
                plt.title(params.title, fontsize=14)
                plt.xlabel(params.xlabel, fontsize=12)
                plt.ylabel(params.ylabel, fontsize=12)

                # 显示网格
                if params.show_grid:
                    plt.grid(True, linestyle='--', alpha=0.7)

                # 调整布局
                plt.tight_layout()
        else:
            # 单维数组处理
            # 创建图表
            plt.figure(figsize=(fig_width, fig_height))

            # 根据绘制方式绘制图表
            if params.plot_mode == "折线图":
                plt.plot(x_data, y_data,
                         color=params.line_color,
                         linewidth=params.line_width)
            elif params.plot_mode == "散点图":
                plt.scatter(x_data, y_data,
                            c=params.line_color,
                            s=50)
            elif params.plot_mode == "柱状图":
                plt.bar(x_data, y_data,
                        color=params.line_color,
                        width=max(0.1, (max(x_data) - min(x_data)) / len(x_data) * 0.8))
            elif params.plot_mode == "填充图":
                plt.fill_between(x_data, y_data,
                                 color=params.line_color,
                                 alpha=0.5)
                plt.plot(x_data, y_data,
                         color=params.line_color,
                         linewidth=params.line_width)

            # 设置标题和轴标签
            plt.title(params.title, fontsize=14)
            plt.xlabel(params.xlabel, fontsize=12)
            plt.ylabel(params.ylabel, fontsize=12)

            # 显示网格
            if params.show_grid:
                plt.grid(True, linestyle='--', alpha=0.7)

            # 调整布局
            plt.tight_layout()

        # 保存到临时文件
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        image = Image.open(buf)
        return {"output": image}