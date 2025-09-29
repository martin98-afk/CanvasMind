from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType
class RandomForestComponent(BaseComponent):
    name = "随机森林分类器"
    category = "算法"
    description = "Random Forest Classifier for CSV data"
    inputs = [
        PortDefinition(name="file", label="输入CSV文件", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="value", label="预测值", type=ArgumentType.TEXT),
        PortDefinition(name="model", label="训练模型", type=ArgumentType.TEXT),
        PortDefinition(name="port_2", label="端口3", type=ArgumentType.TEXT),
    ]
    properties = {
        "n_estimators": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="树数量",
        ),
        "max_depth": PropertyDefinition(
            type=PropertyType.INT,
            default=None,
            label="最大深度",
        ),
        "prop_2": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="属性3",
        ),
    }

    def run(self, params, inputs=None):
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier

        try:
            if not inputs or "file" not in inputs:
                raise ValueError("Invalid input")

            csv_file = inputs["file"]
            df = pd.read_csv(csv_file)

            X = df.iloc[:, :-1]
            y = df.iloc[:, -1]

            model = RandomForestClassifier(
                n_estimators=int(params.get("n_estimators", 100)),
                max_depth=params.get("max_depth", None)
            )
            model.fit(X, y)

            prediction = model.predict([X.iloc[0]])
            score = model.score(X, y)

            return {
                "value": prediction.tolist(),
                "model": {
                    "score": score,
                    "n_estimators": model.n_estimators,
                    "classes": model.classes_.tolist()
                }
            }

        except Exception as e:
            self.logger.error(f"Error in RandomForestComponent: {e}")
            raise e
