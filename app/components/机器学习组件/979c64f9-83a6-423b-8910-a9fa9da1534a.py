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
    name = "随机森林分类"
    category = "机器学习组件"
    description = "使用随机森林算法进行分类"
    requirements = "scikit-learn,pandas"

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
        "max_depth": PropertyDefinition(
            type=PropertyType.INT,
            default=None,
            label="最大深度",
        ),
        "min_samples_split": PropertyDefinition(
            type=PropertyType.INT,
            default=2,
            label="分割节点最小样本数",
        ),
        "random_state": PropertyDefinition(
            type=PropertyType.INT,
            default=42,
            label="随机种子",
        ),
        "criterion": PropertyDefinition(
            type=PropertyType.TEXT,
            default="gini",
            label="分裂标准",
        ),
    }

    def run(self, params, inputs=None):
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score

        self.logger.info("开始随机森林训练...")

        # 读取输入数据
        features_df = pd.read_csv(inputs["features"])
        target_series = pd.read_csv(inputs["target"]).iloc[:, 0]

        # 训练随机森林模型
        model = RandomForestClassifier(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth", None),
            min_samples_split=params.get("min_samples_split", 2),
            random_state=params.get("random_state", 42),
            criterion=params.get("criterion", "gini")
        )
        model.fit(features_df, target_series)

        # 预测结果
        predictions = model.predict(features_df)

        # 保存模型
        model_path = self.save_model(model, "random_forest_model")

        # 返回结果
        result = {
            "predictions": pd.DataFrame(predictions, columns=["预测结果"]),
            "model": model_path
        }

        self.logger.info("随机森林训练完成")
        return result