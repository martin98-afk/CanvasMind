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


class RobustScaler(BaseComponent):
    name = "Robust Scaler"
    category = "数据处理"
    description = "对数据进行鲁棒缩放处理，基于中位数和IQR（四分位距）"
    requirements = "scikit-learn>=0.20"
    inputs = [
        PortDefinition(name="data", label="输入数据", type=ArgumentType.CSV)
    ]
    outputs = [
        PortDefinition(name="scaled_data", label="标准化后的数据", type=ArgumentType.CSV)
    ]

    properties = {
        "with_centering": PropertyDefinition(
            type=PropertyType.BOOL,
            label="中心化处理",
            default="True"
        ),
        "with_scaling": PropertyDefinition(
            type=PropertyType.BOOL,
            label="缩放处理",
            default="True"
        ),
        "unit_variance": PropertyDefinition(
            type=PropertyType.BOOL,
            label="单位方差",
            default="False"
        )
    }

    def run(self, params, inputs=None):
        """
        实现基于中位数和IQR的鲁棒缩放
        支持对指定列进行标准化处理
        """
        from sklearn.preprocessing import RobustScaler
        import pandas as pd

        data = pd.DataFrame(inputs.data)

        scaler = RobustScaler(
            with_centering=params.with_centering,
            with_scaling=params.with_scaling,
            unit_variance=params.unit_variance
        )

        # 处理指定列
        scaled_values = pd.DataFrame(scaler.fit_transform(data), columns=data.columns)

        return {
            "scaled_data": scaled_values
        }

if __name__ == "__main__":
    import warnings
    import pandas as pd
    warnings.filterwarnings("ignore")

    model = RobustScaler()
    result = model.debug(
        params={
            "with_centering": "True",
            "with_scaling": "True",
            "unit_variance": "False"
        },
        inputs={
            "data": pd.DataFrame([
                {"feature1": 10, "feature2": 100},
                {"feature1": 20, "feature2": 200},
                {"feature1": 30, "feature2": 300}
            ])
        },
        global_vars={},
        node_id="robust_scaler_001"
    )
    print(result)
