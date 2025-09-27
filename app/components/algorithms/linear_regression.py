import pandas as pd
from sklearn.linear_model import LinearRegression

from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, ArgumentType


class LinearRegressionComponent(BaseComponent):
    name = "线性回归"
    category = "算法"
    description = "Linear Regression for CSV data"
    inputs = [
        PortDefinition(name="file", label="输入CSV文件")
    ]
    outputs = [
        PortDefinition(name="value", label="预测值"),
        PortDefinition(name="model", label="训练模型")
    ]
    properties = {
        "fit_intercept": PropertyDefinition(
            type=ArgumentType.BOOL,
            default=True,
            label="是否包含截距"
        )
    }

    def run(self, params, inputs=None):
        try:
            if not inputs or "file" not in inputs:
                raise ValueError("Invalid input")

            csv_file = inputs["file"]
            df = pd.read_csv(csv_file)

            X = df.iloc[:, :-1]
            y = df.iloc[:, -1]

            model = LinearRegression(fit_intercept=params.get("fit_intercept", True))
            model.fit(X, y)

            prediction = model.predict([X.iloc[0]])
            score = model.score(X, y)

            return {
                "value": prediction.tolist(),
                "model": {
                    "score": score,
                    "coef": model.coef_.tolist(),
                    "intercept": model.intercept_.tolist() if hasattr(model.intercept_, "tolist") else model.intercept_
                }
            }

        except Exception as e:
            self.logger.error(f"Error in LinearRegressionComponent: {e}")
            raise e