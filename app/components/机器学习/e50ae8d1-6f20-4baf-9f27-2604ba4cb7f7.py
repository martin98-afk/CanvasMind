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


class TorchClassifierTrainer(BaseComponent):
    name = "Torch模型推理"
    category = "机器学习"
    description = "对输入的torch模型进行推理"
    requirements = "torch"
    inputs = [
        PortDefinition(name="test_data", label="推理数据", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="torch模型", type=ArgumentType.TORCHMODEL, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output", label="推理结果", type=ArgumentType.ARRAY),
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch

        data = inputs.test_data
        model = inputs.model
        data = torch.tensor(data, dtype=torch.float32)
        test_outputs = model.module()(data)
        _, predicted = test_outputs.max(1)


        # 10. 返回结果
        return {
            "output": predicted.cpu().numpy()
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = TorchClassifierTrainer()
    result = model.debug(
        params={
            "hidden_size": "64",
            "learning_rate": "0.001",
            "epochs": "50",
            "batch_size": "32",
            "test_split": "0.2",
            "labels": "target",
            "model_name": "test_model.pth"
        },
        inputs={
            "training_data": "sample_data.csv",
            "labels": "target"
        },
        global_vars={},
        node_id="torch_classifier_train",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)