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
ConnectionType = base_module.ConnectionType


class Component(BaseComponent):
    name = "Matplotlib画图"
    category = "数据可视化"
    description = "使用Matplotlib绘制图表"
    requirements = "matplotlib,Pillow"
    inputs = [
        PortDefinition(name="x", label="输入1", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="y", label="输入2", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output", label="输出图像", type=ArgumentType.IMAGE),
    ]
    properties = {}
    def run(self, params, inputs=None):
        import matplotlib.pyplot as plt
        from PIL import Image
        import io
        import base64
        # 获取输入数据
        # 创建图表
        plt.figure()
        try:
            # 假设数据为x,y列表格式
            plt.plot(inputs.x, inputs.y)
            plt.title("Matplotlib Chart")
            # 保存到临时文件
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            plt.close()
            buf.seek(0)    
            image = Image.open(buf)
            return {"output": image}
        except:
            plt.close()
            raise
