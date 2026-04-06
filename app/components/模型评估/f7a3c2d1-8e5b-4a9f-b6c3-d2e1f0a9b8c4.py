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


class RegressionEvaluationComponent(BaseComponent):
    name = "回归评估"
    category = "模型评估"
    description = "计算回归模型评估指标（MSE、RMSE、MAE、R²）"
    requirements = "scikit-learn, numpy"
    inputs = [
        PortDefinition(name="y_true", label="真实值", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="y_pred", label="预测值", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE)
    ]
    outputs = [
        PortDefinition(name="evaluation_results", label="评估结果", type=ArgumentType.JSON, connection=ConnectionType.SINGLE)
    ]
    properties = {
        "show_mse": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="计算MSE"
        ),
        "show_rmse": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="计算RMSE"
        ),
        "show_mae": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="计算MAE"
        ),
        "show_r2": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="计算R²"
        ),
        "show_mape": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="计算MAPE"
        ),
    }

    def run(self, params, inputs):
        import numpy as np
        from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

        y_true = np.array(inputs["y_true"]).flatten()
        y_pred = np.array(inputs["y_pred"]).flatten()
        try:
            result = {}
            if params.get("show_mse"):
                result["mse"] = float(mean_squared_error(y_true, y_pred))
            if params.get("show_rmse"):
                result["rmse"] = float(np.sqrt(mean_squared_error(y_true, y_pred)))
            if params.get("show_mae"):
                result["mae"] = float(mean_absolute_error(y_true, y_pred))
            if params.get("show_r2"):
                result["r2"] = float(r2_score(y_true, y_pred))
            if params.get("show_mape"):
                # 避免除以零
                mask = y_true != 0
                if np.any(mask):
                    result["mape"] = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)
                else:
                    result["mape"] = None

            return {"evaluation_results": result}
        except Exception as e:
            self.logger.error(f"回归评估失败: {str(e)}")
            raise

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = RegressionEvaluationComponent()
    result = model.debug(
        params={"show_mse": True, "show_rmse": True, "show_mae": True, "show_r2": True, "show_mape": False},
        inputs={
            "y_true": [3.0, -0.5, 2.0, 7.0, 5.0, 2.5],
            "y_pred": [2.5, 0.0, 2.1, 7.8, 5.0, 2.0]
        },
        global_vars={},
        node_id="regression_eval_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
