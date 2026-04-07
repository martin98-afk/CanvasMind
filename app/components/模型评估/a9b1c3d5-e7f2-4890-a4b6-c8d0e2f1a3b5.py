# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
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


class ConfusionMatrixComponent(BaseComponent):
    name = "混淆矩阵"
    category = "模型评估"
    description = "计算并生成混淆矩阵，用于分类模型评估"
    requirements = "scikit-learn, numpy"
    inputs = [
        PortDefinition(name="y_true", label="真实标签", type=ArgumentType.CSV, connection=ConnectionType.SINGLE),
        PortDefinition(name="y_pred", label="预测标签", type=ArgumentType.CSV, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="confusion_matrix", label="混淆矩阵", type=ArgumentType.ARRAY),
        PortDefinition(name="matrix_data", label="矩阵数据", type=ArgumentType.JSON),
    ]
    properties = {
        "labels": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="类别标签",
            description="逗号分隔的类别标签，如: 0,1 或 苹果,香蕉,橙子",
        ),
        "normalize": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="none",
            label="归一化方式",
            choices=["none", "true", "pred", "all"]
        ),
    }

    def run(self, params, inputs):
        import numpy as np
        from sklearn.metrics import confusion_matrix

        y_true = np.array(inputs["y_true"]).flatten()
        y_pred = np.array(inputs["y_pred"]).flatten()
        labels_str = params.get("labels", "")
        normalize = params["normalize"]

        # 验证输入长度一致性
        if len(y_true) != len(y_pred):
            raise ValueError(
                f"输入长度不一致: y_true 有 {len(y_true)} 个样本, "
                f"y_pred 有 {len(y_pred)} 个样本。"
                f"请确保真实标签和预测标签的长度相同。"
            )

        try:
            # 解析标签
            if labels_str.strip():
                labels = [label.strip() for label in labels_str.split(",")]
            else:
                labels = sorted(set(y_true) | set(y_pred))

            # 计算混淆矩阵
            cm = confusion_matrix(y_true, y_pred, labels=labels, normalize=normalize if normalize != "none" else None)
            
            # 构建返回数据（二分类情况下提供详细指标）
            result = {
                "confusion_matrix": cm.tolist(),
                "labels": labels,
                "normalize": normalize,
                "sample_count": len(y_true),
                "accuracy": float(np.trace(cm) / np.sum(cm)) if normalize == "none" and np.sum(cm) > 0 else None,
            }

            # 二分类时额外提供 TN, FP, FN, TP
            if len(labels) == 2:
                tn, fp, fn, tp = cm.ravel()
                result["matrix_data"] = {
                    "tn": int(tn),
                    "fp": int(fp),
                    "fn": int(fn),
                    "tp": int(tp),
                }
            else:
                result["matrix_data"] = None

            return {"confusion_matrix": cm.tolist(), "matrix_data": result}
        except ValueError as ve:
            # 重新抛出明确的验证错误
            raise
        except Exception as e:
            self.logger.error(f"混淆矩阵计算失败: {str(e)}")
            raise

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = ConfusionMatrixComponent()
    result = model.debug(
        params={"labels": "0,1", "normalize": "none"},
        inputs={
            "y_true": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
            "y_pred": [0, 0, 0, 1, 1, 1, 0, 1, 1, 0]
        },
        global_vars={},
        node_id="confusion_matrix_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
