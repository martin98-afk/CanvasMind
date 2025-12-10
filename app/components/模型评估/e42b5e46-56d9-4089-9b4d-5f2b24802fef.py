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


class ModelEvaluationComponent(BaseComponent):
    name = "模型评估"
    category = "模型评估"
    description = "计算模型分类评估指标（准确率、F1分数等）"
    requirements = "scikit-learn>=0.24.0"
    inputs = [
        PortDefinition(name="predictions", label="预测结果", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="true_labels", label="真实标签", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE)
    ]
    outputs = [
        PortDefinition(name="evaluation_results", label="评估结果", type=ArgumentType.JSON, connection=ConnectionType.SINGLE)
    ]
    properties = {
        "metric": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="accuracy",
            label="评估指标",
            choices=["accuracy", "precision", "recall", "f1_score", "roc_auc"]
        ),
        "average": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="binary",
            label="平均方式",
            choices=["binary", "micro", "macro", "weighted", "none"]
        )
    }

    def run(self, params, inputs):
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

        predictions = inputs["predictions"]
        true_labels = inputs["true_labels"]
        metric = params["metric"]
        average = params["average"]
        try:
            if metric == "accuracy":
                result = {"accuracy": float(accuracy_score(true_labels, predictions))}
            elif metric == "precision":
                result = {"precision": float(precision_score(true_labels, predictions, average=average))}
            elif metric == "recall":
                result = {"recall": float(recall_score(true_labels, predictions, average=average))}
            elif metric == "f1_score":
                result = {"f1_score": float(f1_score(true_labels, predictions, average=average))}
            elif metric == "roc_auc":
                result = {"roc_auc": float(roc_auc_score(true_labels, predictions))}

            return {"evaluation_results": result}
        except Exception as e:
            self.logger.error(f"模型评估失败: {str(e)}")
            raise

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = ModelEvaluationComponent()
    result = model.debug(
        params={"metric": "accuracy", "average": "binary"},
        inputs={
            "predictions": [[0], [1], [1], [0], [1], [0], [1], [1]],  # 二维列表
            "true_labels": [[0], [1], [0], [0], [1], [0], [1], [0]]   # 二维列表
        },
        global_vars={},
        node_id="evaluate_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)