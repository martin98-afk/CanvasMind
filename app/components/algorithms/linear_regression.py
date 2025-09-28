import pandas as pd
from sklearn.linear_model import LinearRegression

from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, ArgumentType, PropertyType


class LinearRegressionComponent(BaseComponent):
    name = "线性回归"
    category = "算法"
    description = "Linear Regression for CSV data"
    inputs = [
        PortDefinition(name="feature", label="输入特征", type=ArgumentType.CSV),
        PortDefinition(name="target", label="输入目标", type=ArgumentType.CSV)
    ]
    outputs = [
        PortDefinition(name="value", label="预测值"),
        PortDefinition(name="model", label="训练模型")
    ]
    properties = {
        "fit_intercept": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="是否包含截距"
        )
    }

    def run(self, params, inputs=None):
        try:
            feature = inputs.get("feature")
            target = inputs.get("target")
            model = LinearRegression(fit_intercept=params.get("fit_intercept", True))
            model.fit(feature, target)

            prediction = model.predict([feature.iloc[0]])
            score = model.score(feature, target)

            return {
                "value": prediction.tolist(),
                "model": {
                    "score": score,
                    "coef": model.coef_.tolist(),
                    "intercept": model.intercept_.tolist() if hasattr(model.intercept_, "tolist") else model.intercept_
                }
            }

        except Exception as e:
            import traceback
            self.logger.error(f"Error in LinearRegressionComponent: {traceback.format_exc()}")
            raise e