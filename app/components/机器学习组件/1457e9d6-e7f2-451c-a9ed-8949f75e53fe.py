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
    name = "LightGBM 模型训练"
    category = "机器学习组件"
    description = "使用 LightGBM 算法进行分类或回归"
    requirements = "pandas,lightgbm,scikit-learn"

    inputs = [
        PortDefinition(name="features", label="特征数据", type=ArgumentType.CSV),
        PortDefinition(name="target", label="目标变量", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="predictions", label="预测结果", type=ArgumentType.CSV),
        PortDefinition(name="model", label="训练好的模型", type=ArgumentType.TORCHMODEL),
    ]

    properties = {
        "num_leaves": PropertyDefinition(
            type=PropertyType.INT,
            default=31,
            label="最大叶子数",
        ),
        "max_depth": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="最大深度",
        ),
        "learning_rate": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.1,
            label="学习率",
        ),
        "n_estimators": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="树的数量",
        ),
        "random_state": PropertyDefinition(
            type=PropertyType.INT,
            default=42,
            label="随机种子",
        ),
        "objective": PropertyDefinition(
            type=PropertyType.TEXT,
            default="binary",
            label="目标函数",
        ),
        "boosting_type": PropertyDefinition(
            type=PropertyType.TEXT,
            default="gbdt",
            label="提升类型",
        ),
    }

    def run(self, params, inputs=None):
        import pandas as pd
        import lightgbm as lgb
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, mean_squared_error

        self.logger.info("开始 LightGBM 模型训练...")

        # 读取输入数据
        features_df = pd.read_csv(inputs["features"])
        target_series = pd.read_csv(inputs["target"]).iloc[:, 0]

        # 初始化 LightGBM 模型
        model = lgb.LGBMClassifier(
            num_leaves=params.get("num_leaves", 31),
            max_depth=params.get("max_depth", 0),
            learning_rate=params.get("learning_rate", 0.1),
            n_estimators=params.get("n_estimators", 100),
            random_state=params.get("random_state", 42),
            objective=params.get("objective", "binary"),
            boosting_type=params.get("boosting_type", "gbdt")
        )

        # 训练模型
        model.fit(features_df, target_series)

        # 预测结果
        predictions = model.predict(features_df)

        # 保存模型
        model_path = self.save_model(model, "lightgbm_model")

        # 返回结果
        result = {
            "predictions": pd.DataFrame(predictions, columns=["预测结果"]),
            "model": model_path
        }

        self.logger.info("LightGBM 模型训练完成")
        return result


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "num_leaves": 31,
            "max_depth": 0,
            "learning_rate": 0.1,
            "n_estimators": 100,
            "random_state": 42,
            "objective": "binary",
            "boosting_type": "gbdt"
        },
        inputs={
            "features": "path/to/features.csv",
            "target": "path/to/target.csv"
        },
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)