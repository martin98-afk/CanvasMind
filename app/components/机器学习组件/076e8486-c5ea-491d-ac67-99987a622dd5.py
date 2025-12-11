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
    description = "使用随机森林算法进行分类任务训练"
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
            min=1,
            max=1000,
            step=10,
        ),
        "max_depth": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="最大深度",
            min=1,
            max=20,
            step=1,
        ),
        "min_samples_split": PropertyDefinition(
            type=PropertyType.INT,
            default=2,
            label="分裂所需最小样本数",
            min=2,
            max=100,
            step=1,
        ),
        "min_samples_leaf": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="叶节点最小样本数",
            min=1,
            max=50,
            step=1,
        ),
        "max_features": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="sqrt",
            label="最大特征数",
            choices=["sqrt", "log2", "auto", "None"],
        ),
        "random_state": PropertyDefinition(
            type=PropertyType.INT,
            default=42,
            label="随机种子",
        ),
        "n_jobs": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="并行任务数",
            min=-1,
            max=16,
            step=1,
        ),
    }

    def run(self, params, inputs=None):
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, classification_report
        import joblib

        self.logger.info("开始随机森林分类模型训练...")

        # 读取输入数据
        features_df = inputs.features
        target_series = inputs.target

        # 初始化随机森林模型
        model = RandomForestClassifier(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth", 5),
            min_samples_split=params.get("min_samples_split", 2),
            min_samples_leaf=params.get("min_samples_leaf", 1),
            max_features=params.get("max_features", "sqrt"),
            random_state=params.get("random_state", 42),
            n_jobs=params.get("n_jobs", -1),
            verbose=0
        )

        # 训练模型
        model.fit(features_df, target_series)

        # 预测结果
        predictions = model.predict(features_df)

        # 生成预测结果 DataFrame
        predictions_df = pd.DataFrame(predictions, columns=["预测结果"])

        # 可选：输出评估报告（可作为日志或附加输出）
        accuracy = accuracy_score(target_series, predictions)
        self.logger.info(f"模型训练完成，准确率: {accuracy:.4f}")

        # 返回结果
        result = {
            "predictions": predictions_df,
            "model": model
        }

        self.logger.info("随机森林分类模型训练完成")
        return result


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "n_estimators": 100,
            "max_depth": 5,
            "min_samples_split": 2,
            "min_samples_leaf": 1,
            "max_features": "sqrt",
            "random_state": 42,
            "n_jobs": -1
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