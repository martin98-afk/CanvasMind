from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType
class Component(BaseComponent):
    name = "测试安装包"
    category = "算法"
    description = "terst"
    inputs = [
    ]
    outputs = [
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import matplotlib
        # 在这里编写你的组件逻辑
        input_data = inputs.get("input_data") if inputs else None
        param1 = params.get("param1", "default_value")
        # 处理逻辑
        result = f"处理结果: {input_data} + {param1}"
        return {
            "output_data": result
        }
