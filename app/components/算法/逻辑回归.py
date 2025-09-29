from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType
class LogisticRegressionComponent(BaseComponent):
    name="逻辑回归"
    category="算法"
    description="Logistic Regression classifier for CSV data"
    inputs=[
        PortDefinition(name="feature", label="输入特征", type=ArgumentType.CSV),
        PortDefinition(name="target", label="输入目标", type=ArgumentType.CSV)
    ]
    outputs=[
        PortDefinition(name="value", label="预测值"),
        PortDefinition(name="model", label="训练模型")
    ]
    properties={
        "solver": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="liblinear",
            label="求解器",
            choices=["liblinear", "lbfgs", "newton-cg", "sag", "saga"]
        ),
        "max_iter": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="最大迭代次数"
        ),
        "test_size": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.2,
            label="测试集比例"
        )
    }

    def run(self, params, inputs=None):
        from sklearn.linear_model import LogisticRegression
        try:
            self.logger.info(inputs)

            # 读取数据
            feature = inputs.get("feature")
            target = inputs.get("target")
            # 获取参数
            solver = params.get("solver", "liblinear")
            max_iter = int(params.get("max_iter", 100))

            # 训练模型
            model = LogisticRegression(solver=solver, max_iter=max_iter, multi_class='ovr')
            model.fit(feature, target)

            # 预测示例（使用第一行数据）
            sample_prediction = model.predict([feature.iloc[0]])
            accuracy = model.score(feature, target)

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
