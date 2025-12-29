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


class DynamicComponent(BaseComponent):
    name = "平行坐标图"
    category = "数据可视化"
    description = "生成平行坐标图的html文本，如果提供目标数据，曲线的颜色会根据目标数据进行区分"
    requirements = "pyecharts"

    inputs = [
        PortDefinition(name="input1", label="input1", type=ArgumentType.CSV, connection=ConnectionType.SINGLE),
        PortDefinition(name="target", label="目标数据", type=ArgumentType.CSV, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="output1", type=ArgumentType.TEXT),
    ]
    properties = {

    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import numpy as np
        import pandas as pd
        from pyecharts import options as opts
        from pyecharts.charts import Parallel
        input_df = inputs.get("input1")
        target_df = inputs.get("target")

        if input_df is None or not isinstance(input_df, pd.DataFrame):
            raise ValueError("输入数据 'input1' 必须为有效的 CSV（DataFrame）")
        if input_df.empty:
            raise ValueError("输入数据为空")

        # 确保所有列为数值型（平行坐标图只支持数值）
        numeric_df = input_df.select_dtypes(include=[np.number])
        if numeric_df.shape[1] == 0:
            raise ValueError("输入数据中没有数值列，无法绘制平行坐标图")
        if numeric_df.shape[1] != input_df.shape[1]:
            # 可选：警告非数值列被忽略
            pass
        input_df = numeric_df

        columns = input_df.columns.tolist()
        all_data = input_df.values  # shape: (n_rows, n_cols)

        # 计算每个维度的全局 min / max
        col_mins = np.nanmin(all_data, axis=0)
        col_maxs = np.nanmax(all_data, axis=0)

        # 构建 schema，显式设置范围
        schema = [
            opts.ParallelAxisOpts(
                dim=i,
                name=col,
                min_=float(col_mins[i]),
                max_=float(col_maxs[i])
            )
            for i, col in enumerate(columns)
        ]

        chart = Parallel()
        chart.add_schema(schema)

        # 如果有 target，分组绘制
        if target_df is not None and not target_df.empty:
            if target_df.shape[1] != 1:
                raise ValueError("目标数据必须为单列")
            if len(target_df) != len(input_df):
                raise ValueError("目标数据与输入数据的行数不一致")

            target_series = target_df.iloc[:, 0].astype(str)
            from collections import defaultdict
            grouped = defaultdict(list)
            for row, label in zip(all_data.tolist(), target_series):
                grouped[label].append(row)

            for label, group_data in grouped.items():
                chart.add(label, group_data)
        else:
            # 无分组，全部数据一个系列
            chart.add("data", all_data.tolist())

        chart.set_global_opts(title_opts=opts.TitleOpts(title="平行坐标图"))
        return {"output1": chart.render_embed()}
