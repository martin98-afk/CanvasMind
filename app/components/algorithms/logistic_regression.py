"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: logistic_regression.py
@time: 2025/9/26 14:41
@desc: 
"""
import pandas as pd
from sklearn.linear_model import LogisticRegression

from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, ArgumentType


class LogisticRegressionComponent(BaseComponent):
    name="逻辑回归"
    category="算法"
    description="Logistic Regression classifier for CSV data"
    inputs=[
        PortDefinition(name="file", label="输入CSV文件", type=ArgumentType.CSV),
        PortDefinition(name="value", label="输入值")
    ]
    outputs=[
        PortDefinition(name="value", label="预测值"),
        PortDefinition(name="model", label="训练模型")
    ]
    properties={
        "solver": PropertyDefinition(
            type=ArgumentType.CHOICE,
            default="liblinear",
            label="求解器",
            choices=["liblinear", "lbfgs", "newton-cg", "sag", "saga"]
        ),
        "max_iter": PropertyDefinition(
            type=ArgumentType.INT,
            default=100,
            label="最大迭代次数"
        ),
        "test_size": PropertyDefinition(
            type=ArgumentType.FLOAT,
            default=0.2,
            label="测试集比例"
        )
    }

    def run(self, params, inputs=None):
        try:
            self.logger.info(inputs)

            # 读取数据
            df = inputs.get("file")
            self.logger.info(f"Data shape: {df.shape}")

            # 获取参数
            solver = params.get("solver", "liblinear")
            max_iter = int(params.get("max_iter", 100))

            # 假设最后1列是目标变量，前面是特征
            X = df.iloc[:, :-1]
            y = df.iloc[:, -1]

            # 训练模型
            model = LogisticRegression(solver=solver, max_iter=max_iter, multi_class='ovr')
            model.fit(X, y)

            # 预测示例（使用第一行数据）
            sample_prediction = model.predict([X.iloc[0]])
            accuracy = model.score(X, y)

            self.logger.info(f"Model accuracy: {accuracy:.4f}")

            return {
                "value": sample_prediction.tolist(),
                "model": {
                    "accuracy": accuracy,
                    "classes": model.classes_.tolist(),
                    "coef": model.coef_.tolist() if hasattr(model, 'coef_') else None
                }
            }

        except Exception as e:
            self.logger.error(f"Error in LogisticRegressionComponent: {e}")
            raise e