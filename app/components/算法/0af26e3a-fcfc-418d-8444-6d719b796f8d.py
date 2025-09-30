from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType
class LogisticRegressionComponent(BaseComponent):
    name = "逻辑回归"
    category = "算法"
    description = "组件开发生成组件"
    inputs = [
        PortDefinition(name="feature", label="特征", type=ArgumentType.CSV),
        PortDefinition(name="target", label="目标", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="value", label="预测值", type=ArgumentType.TEXT),
        PortDefinition(name="model", label="模型参数", type=ArgumentType.TEXT),
    ]
    properties = {
        "solver": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="liblinear",
            label="求解器",
            choices=["liblinear"]
        ),
        "max_iter": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="最大迭代数",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        try:
            from sklearn.linear_model import LogisticRegression
            import matplotlib
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
