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


class Component(BaseComponent):
    name = "MinMax归一化"
    category = "数据预处理"
    description = "MinMax归一化组件用于对输入的CSV格式数据进行最小最大值归一化处理，输入为单个CSV文件，输出为归一化后的CSV数据及对应的sklearn MinMaxScaler模型，无额外参数配置。"
    requirements = "pandas,scikit-learn"
    inputs = [
        PortDefinition(name="input", label="端口1", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="output", label="端口1", type=ArgumentType.CSV),
        PortDefinition(name="scaler", label="端口2", type=ArgumentType.SKLEARNMODEL),
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        from sklearn.preprocessing import MinMaxScaler
        import pandas as pd
        input = inputs.input
        scaler = MinMaxScaler()
        output = scaler.fit_transform(input)
        output = pd.DataFrame(output, columns=input.columns)
        return {
            "output": output,
            "scaler": scaler
        }
