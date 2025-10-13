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
    name = "因子分析"
    category = "数据分析"
    description = "执行因子分析以降维和发现变量间潜在结构"
    requirements = "pandas>=1.3.0,scikit-learn>=1.0.2,numpy"
    inputs = [
        PortDefinition(name="data", label="输入数据", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="results", label="因子分析结果", type=ArgumentType.JSON),
    ]
    properties = {
        "n_components": PropertyDefinition(
            type=PropertyType.INT,
            default=2,
            label="公因子数",
            min=1,
            max=10,
            step=1
        ),
        "rotation": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="varimax",
            label="旋转方法",
            choices=["varimax", "promax", "none"]
        ),
        "standardize": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="标准化数据"
        )
    }
    def run(self, params, inputs=None):
        import pandas as pd
        import numpy as np
        from sklearn.decomposition import FactorAnalysis
        from sklearn.preprocessing import StandardScaler
        self.logger.info("开始因子分析组件执行")
        # 获取输入数据
        data = inputs.data
        # 标准化处理
        if params.standardize:
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(data)
        else:
            scaled_data = data
        # 执行因子分析
        n_components = params.n_components
        rotation = params.rotation
        fa = FactorAnalysis(n_components=n_components, rotation=rotation)
        factors = fa.fit_transform(scaled_data)
        # 构建结果字典
        results = {
            "factor_loadings": pd.DataFrame(fa.components_, columns=data.columns).to_dict(),
            "factor_scores": pd.DataFrame(factors, columns=[f"Factor{i+1}" for i in range(n_components)]).to_dict(),
            # "explained_variance_ratio": fa.explained_variance_ratio_.tolist()
        }
        self.logger.info("因子分析完成，返回结果")
        return {"results": results}
