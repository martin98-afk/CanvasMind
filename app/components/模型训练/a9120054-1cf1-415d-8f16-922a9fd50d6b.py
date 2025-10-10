# -*- coding: utf-8 -*-
import importlib.util
import pathlib
base_path = pathlib.Path(__file__).parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType


class Component(BaseComponent):
    name = "图像分类测试"
    category = "模型训练"
    description = "使用pytorch中ResNet18预训练模型测试torch运行可行性"
    requirements = "Pillow,torch,torchvision"
    inputs = [
        PortDefinition(name="input_image", label="端口1", type=ArgumentType.IMAGE),
    ]
    outputs = [
        PortDefinition(name="predict_class", label="端口1", type=ArgumentType.TEXT),
        PortDefinition(name="confidence", label="端口2", type=ArgumentType.FLOAT),
        PortDefinition(name="model", label="端口3", type=ArgumentType.TORCHMODEL),
    ]
    properties = {
        "top_k": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="取前k个结果",
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cpu",
            label="运行设备",
            choices=["cpu", "cuda"]
        ),
    }
    
    def load_model(self, device: str):
        import torch
        from torchvision.models import resnet18, ResNet18_Weights
        if device == "cpu":
            self.device = torch.device(device)
           
        weights = ResNet18_Weights.DEFAULT
        self.model = resnet18(weights=weights).to(self.device)
        self.model.eval()
        self.process = weights.transforms()
        self.logger.info(f"Model loaded on {self.device}")

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        import torchvision.transforms as transforms
        from torchvision.models import resnet18, ResNet18_Weights
        from PIL import Image
        import io
        import base64
        self.load_model(params.get("device"))
        # 在这里编写你的组件逻辑
        input_image = inputs.get("input_image")
        if input_image is None:
            raise ValueError("未提供图像！")
        top_k = params.get("top_k", 1)
        input_tensor = self.process(input_image).unsqueeze(0).to(self.device)
        with torch.no_grad():
            output = self.model(input_tensor)
            prob = torch.nn.functional.softmax(output[0], dim=0)
            top_probs, top_indices = torch.topk(prob, top_k)
            
        # 获取ImageNet类别标签
        labels = ResNet18_Weights.DEFAULT.meta["categories"]
        top_labels = [labels[idx.item()] for idx in top_indices]
        predicted_class = top_labels[0]
        confidence = top_probs[0].item()
        
        return {
            "predict_class": predicted_class,
            "confidence": confidence,
            "model": self.model
        }
