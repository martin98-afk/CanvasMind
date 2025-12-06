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
    name = "随机森林分类训练"
    category = "机器学习组件"
    description = ""
    requirements = "pandas,scikit-learn"

    inputs = [
        PortDefinition(name="features", label="特征数据", type=ArgumentType.CSV),
        PortDefinition(name="target", label="目标变量", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="predictions", label="预测结果", type=ArgumentType.CSV),
        PortDefinition(name="model", label="训练好的模型", type=ArgumentType.SKLEARNMODEL),
    ]

    properties = {
        "n_estimators": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="树的数量",
        ),
        "criterion": PropertyDefinition(
            type=PropertyType.TEXT,
            default="gini",
            label="分裂准则",
        ),
        "max_depth": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="最大深度",
        ),
        "min_samples_split": PropertyDefinition(
            type=PropertyType.INT,
            default=2,
            label="节点分裂最小样本",
        ),
        "random_state": PropertyDefinition(
            type=PropertyType.INT,
            default=42,
            label="随机种子",
        ),
    }

    def run(self, params, inputs=None):
        
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score

        self.logger.info("开始随机森林训练...")

        # 读取输入数据
        features_df = inputs.features
        target_series = inputs.target

        # 训练随机森林模型
        model = RandomForestClassifier(
            n_estimators=params.get("n_estimators", 100),
            criterion=params.get("criterion", "gini"),
            max_depth=params.get("max_depth", None),
            min_samples_split=params.get("min_samples_split", 2),
            random_state=params.get("random_state", 42)
        )
        model.fit(features_df, target_series)

        # 预测结果
        predictions = model.predict(features_df)
        
        # 返回结果
        result = {
            "predictions": pd.DataFrame(predictions, columns=["预测结果"]),
            "model": model
        }

        self.logger.info("随机森林训练完成")
        return result


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
