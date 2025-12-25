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


class CustomOutlierFilter(BaseComponent):
    name = "自定义异常值过滤"
    category = "数据处理"
    description = "基于Z-Score或IQR方法过滤数据中的异常值"
    requirements = "numpy>=1.20, scipy>=1.5"
    inputs = [
        PortDefinition(name="data", label="输入数据", type=ArgumentType.JSON),
        PortDefinition(name="columns", label="处理列", type=ArgumentType.ARRAY),
    ]
    outputs = [
        PortDefinition(name="filtered_data", label="过滤后的数据", type=ArgumentType.JSON),
        PortDefinition(name="outliers", label="异常值列表", type=ArgumentType.JSON),
    ]

    properties = {
        "method": PropertyDefinition(
            type=PropertyType.CHOICE,
            label="检测方法",
            default="z_score",
            choices=["z_score", "iqr"]
        ),
        "z_score_threshold": PropertyDefinition(
            type=PropertyType.FLOAT,
            label="Z-Score阈值",
            default="3.0"
        ),
        "iqr_threshold": PropertyDefinition(
            type=PropertyType.FLOAT,
            label="IQR阈值",
            default="1.5"
        ),
        "remove_outliers": PropertyDefinition(
            type=PropertyType.BOOL,
            label="是否移除异常值",
            default="True"
        ),
    }

    def run(self, params, inputs=None):
        """
        实现基于Z-Score或IQR的异常值检测
        支持对指定列进行过滤处理
        """
        import numpy as np
        from scipy import stats

        data = inputs.data
        columns = params.columns or []

        filtered_data = data.copy()
        outliers = {}

        for col in columns:
            if col not in data.columns:
                continue

            values = data[col].dropna().values

            if params.method == "z_score":
                z_scores = np.abs(stats.zscore(values))
                threshold = params.z_score_threshold
                col_outliers = values[z_scores > threshold]

            else:  # IQR method
                Q1 = np.percentile(values, 25)
                Q3 = np.percentile(values, 75)
                IQR = Q3 - Q1
                threshold = params.iqr_threshold
                lower_bound = Q1 - threshold * IQR
                upper_bound = Q3 + threshold * IQR
                col_outliers = values[(values < lower_bound) | (values > upper_bound)]

            outliers[col] = col_outliers.tolist()

            if params.remove_outliers:
                filtered_data = filtered_data[~filtered_data[col].isin(col_outliers)]

        return {
            "filtered_data": filtered_data,
            "outliers": outliers
        }

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    model = CustomOutlierFilter()
    result = model.debug(
        params={
            "method": "z_score",
            "z_score_threshold": "3.0",
            "remove_outliers": "True"
        },
        inputs={
            "data": [
                {"value": 10}, {"value": 15}, {"value": 100},
                {"value": 20}, {"value": 25}, {"value": 30}
            ],
            "columns": ["value"]
        },
        global_vars={},
        node_id="outlier_filter_001"
    )
    print(result)
