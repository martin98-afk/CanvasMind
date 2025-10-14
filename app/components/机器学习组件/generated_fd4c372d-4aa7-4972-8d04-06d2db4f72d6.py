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


class Component(BaseComponent):
    name = "逻辑回归"
    category = "机器学习组件"
    description = "使用逻辑回归算法进行分类"
    requirements = "scikit-learn"

    inputs = [
        PortDefinition(name="features", label="特征数据", type=ArgumentType.CSV),
        PortDefinition(name="target", label="目标变量", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="predictions", label="预测结果", type=ArgumentType.CSV),
        PortDefinition(name="model", label="训练好的模型", type=ArgumentType.SKLEARNMODEL),
    ]

    properties = {
        "max_iter": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="最大迭代次数",
        ),
        "C": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="正则化强度",
        ),
        "random_state": PropertyDefinition(
            type=PropertyType.INT,
            default=42,
            label="随机种子",
        ),
        "penalty": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="惩罚",
        ),
        "solver": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="属性5",
        ),
    }

    def run(self, params, inputs=None):
        import pandas as pd
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score
        
        self.logger.info("开始逻辑回归训练...")
        
        # 读取输入数据
        features_df = pd.read_csv(inputs["features"])
        target_series = pd.read_csv(inputs["target"]).iloc[:, 0]
        
        # 训练逻辑回归模型
        model = LogisticRegression(
            max_iter=params.get("max_iter", 100),
            C=params.get("C", 1.0),
            random_state=params.get("random_state", 42)
        )
        model.fit(features_df, target_series)
        
        # 预测结果
        predictions = model.predict(features_df)
        
        # 保存模型
        model_path = self.save_model(model, "logistic_regression_model")
        
        # 返回结果
        result = {
            "predictions": pd.DataFrame(predictions, columns=["预测结果"]),
            "model": model_path
        }
        
        self.logger.info("逻辑回归训练完成")
        return result
