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


class ClusteringEvaluationComponent(BaseComponent):
    name = "聚类评估"
    category = "模型评估"
    description = "计算聚类模型评估指标（轮廓系数、Calinski-Harabasz指数等）"
    requirements = "scikit-learn"
    inputs = [
        PortDefinition(name="features", label="特征数据", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="labels", label="聚类标签", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE)
    ]
    outputs = [
        PortDefinition(name="evaluation_results", label="评估结果", type=ArgumentType.JSON, connection=ConnectionType.SINGLE)
    ]
    properties = {
        "show_silhouette": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="轮廓系数"
        ),
        "show_calinski": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="Calinski-Harabasz指数"
        ),
        "show_davies_bouldin": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="Davies-Bouldin指数"
        ),
    }

    def run(self, params, inputs):
        import numpy as np
        from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score

        features = np.array(inputs["features"])
        labels = np.array(inputs["labels"]).flatten()
        try:
            result = {}
            if params.get("show_silhouette"):
                result["silhouette_score"] = float(silhouette_score(features, labels))
            if params.get("show_calinski"):
                result["calinski_harabasz_score"] = float(calinski_harabasz_score(features, labels))
            if params.get("show_davies_bouldin"):
                result["davies_bouldin_score"] = float(davies_bouldin_score(features, labels))

            return {"evaluation_results": result}
        except Exception as e:
            self.logger.error(f"聚类评估失败: {str(e)}")
            raise

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = ClusteringEvaluationComponent()
    # 生成示例数据
    from sklearn.datasets import make_blobs
    X, y = make_blobs(n_samples=100, centers=3, random_state=42)
    model = ClusteringEvaluationComponent()
    result = model.debug(
        params={"show_silhouette": True, "show_calinski": True, "show_davies_bouldin": True},
        inputs={
            "features": X.tolist(),
            "labels": y.tolist()
        },
        global_vars={},
        node_id="clustering_eval_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
