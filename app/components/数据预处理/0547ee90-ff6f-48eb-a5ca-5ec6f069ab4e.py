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


class PCA(BaseComponent):
    name = "PCA降维"
    category = "数据预处理"
    description = "对数据进行主成分分析降维处理"
    requirements = "numpy,scikit-learn"
    inputs = [
        PortDefinition(name="data", label="输入数据", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="transformed_data", label="降维后数据", type=ArgumentType.JSON),
        PortDefinition(name="explained_variance_ratio", label="方差解释比例", type=ArgumentType.JSON),
    ]

    properties = {
        "n_components": PropertyDefinition(
            type=PropertyType.INT,
            label="保留成分数量",
            default="2",
        ),
        "whiten": PropertyDefinition(
            type=PropertyType.BOOL,
            label="白化处理",
            default="False",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        from sklearn.decomposition import PCA
        import numpy as np

        # 获取输入数据
        data = np.array(inputs.data)

        # 初始化PCA
        pca = PCA(n_components=params.n_components, whiten=params.whiten)

        # 执行降维
        transformed = pca.fit_transform(data)
        explained_variance = pca.explained_variance_ratio_.tolist()

        return {
            "transformed_data": transformed.tolist(),
            "explained_variance_ratio": explained_variance
        }

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = PCA降维()
    result = model.debug(
        params={"n_components": "2", "whiten": "False"},
        inputs={"data": [[1,2,3], [4,5,6], [7,8,9]]},
        global_vars={},
        node_id="test_pca",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)