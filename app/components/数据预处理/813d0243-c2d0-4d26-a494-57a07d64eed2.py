# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
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


class CsvOutlierRemover(BaseComponent):
    name = "CSV异常值剔除"
    category = "数据预处理"
    description = "使用Z-score或IQR方法去除CSV数据中的异常值"
    requirements = "pandas>=1.3.0,scipy,numpy"
    inputs = [
        PortDefinition(name="input_csv", label="CSV数据", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="cleaned_data", label="清洗后的数据", type=ArgumentType.CSV),
        PortDefinition(name="statistics", label="异常值统计", type=ArgumentType.JSON),
    ]
    properties = {
        "method": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="z-score",
            label="检测方法",
            choices=["z-score", "iqr"]
        ),
        "threshold": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=3.0,
            label="阈值",
        ),
    }

    def run(self, params, inputs=None):
        """
        实现CSV数据异常值剔除逻辑
        支持Z-score和IQR两种检测方法
        """
        import numpy as np
        import pandas as pd
        from scipy.stats import zscore

        # 读取CSV数据
        df = pd.read_csv(inputs.input_csv)

        # 异常值检测
        if params.method == "z-score":
            # 计算Z-score绝对值超过阈值的行
            z_scores = zscore(df.select_dtypes(include=[np.number]))
            outliers = (np.abs(z_scores) > float(params.threshold)).any(axis=1)
        else:  # IQR方法
            # 计算四分位距
            Q1 = df.select_dtypes(include=[np.number]).quantile(0.25)
            Q3 = df.select_dtypes(include=[np.number]).quantile(0.75)
            IQR = Q3 - Q1
            # 1.5倍IQR范围外的值视为异常
            outliers = ((df.select_dtypes(include=[np.number]) < (Q1 - 1.5 * IQR)) 
                      | (df.select_dtypes(include=[np.number]) > (Q3 + 1.5 * IQR))).any(axis=1)

        # 剔除异常值
        cleaned_df = df[~outliers]

        # 生成统计信息
        stats = {
            "total_rows": len(df),
            "removed_rows": int(outliers.sum()),
            "remaining_rows": len(cleaned_df),
            "method_used": params.method,
            "threshold": float(params.threshold)
        }

        return {
            "cleaned_data": cleaned_df.to_csv(index=False),
            "statistics": stats
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = CsvOutlierRemover()
    result = model.debug(
        params={"method": "z-score", "threshold": "3.0"},
        inputs={"input_csv": "name,age,score\nAlice,30,85\nBob,25,95\nCharlie,35,120\nDavid,28,150"},
        node_id="outlier_removal",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True,
        global_vars={}
    )
    print(result)
