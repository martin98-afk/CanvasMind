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


class ModelExportToOnnx(BaseComponent):
    name = "模型导出为 ONNX"
    category = "YOLO/模型导出"
    description = "将训练好的模型导出为 ONNX 格式，便于跨平台部署与推理"
    requirements = "onnx,torch"
    inputs = [
        PortDefinition(name="model", label="输入模型", type=ArgumentType.TORCHMODEL),
        PortDefinition(name="dummy_input", label="示例输入", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="onnx_model", label="导出的 ONNX 模型", type=ArgumentType.FILE),
        PortDefinition(name="model_path", label="ONNX 文件路径", type=ArgumentType.TEXT),
    ]

    properties = {
        "opset_version": PropertyDefinition(
            type=PropertyType.INT,
            default=13,
            label="ONNX Opset 版本",
        ),
        "input_names": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="input",
            label="输入名称列表",
        ),
        "output_names": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="output",
            label="输出名称列表",
        ),
        "dynamic_axes": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="启用动态轴",
        ),
        "verbose": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="输出详细信息",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import os
        import torch
        import onnx
        from pathlib import Path

        # 获取输入模型和示例输入
        model = inputs.model
        dummy_input = inputs.dummy_input

        # 获取参数
        opset_version = int(params.opset_version)
        input_names = [n.strip() for n in params.input_names.split('\n') if n.strip()]
        output_names = [n.strip() for n in params.output_names.split('\n') if n.strip()]
        dynamic_axes = params.dynamic_axes == "true"
        verbose = params.verbose == "true"

        # 生成输出路径
        output_dir = Path("outputs/onnx_models")
        output_dir.mkdir(parents=True, exist_ok=True)
        model_name = "exported_model.onnx"
        output_path = output_dir / model_name

        # 设置动态轴
        dynamic_axes_dict = {}
        if dynamic_axes:
            # 假设输入是 tensor，动态轴为 batch 维度
            for i, name in enumerate(input_names):
                dynamic_axes_dict[name] = {0: 'batch'}
            for i, name in enumerate(output_names):
                dynamic_axes_dict[name] = {0: 'batch'}

        try:
            # 导出模型
            torch.onnx.export(
                model,
                dummy_input,
                str(output_path),
                opset_version=opset_version,
                input_names=input_names,
                output_names=output_names,
                dynamic_axes=dynamic_axes_dict if dynamic_axes else None,
                verbose=verbose,
            )

            # 验证导出的 ONNX 模型
            onnx_model = onnx.load(str(output_path))
            onnx.checker.check_model(onnx_model)

            self.logger.info(f"模型成功导出为 ONNX 格式: {output_path}")

            return {
                "onnx_model": str(output_path),
                "model_path": str(output_path)
            }

        except Exception as e:
            self.logger.error(f"模型导出失败: {str(e)}")
            raise RuntimeError(f"ONNX 导出失败: {str(e)}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = ModelExportToOnnx()
    result = model.debug(
        params={
            "opset_version": "13",
            "input_names": "input",
            "output_names": "output",
            "dynamic_axes": "true",
            "verbose": "false",
        },
        inputs={
            "model": None,  # 实际使用时由上游提供
            "dummy_input": torch.randn(1, 3, 224, 224),  # 示例输入张量
        },
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
