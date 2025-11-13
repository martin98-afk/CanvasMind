# -*- coding: utf-8 -*-
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

class DynamicComponent(BaseComponent):
    name = "动态代码组件"
    category = "代码执行"
    description = "由用户动态生成的组件"
    requirements = ""

    inputs = [
        PortDefinition(name="input", label="input", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
        PortDefinition(name="input_1", label="input_1", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="answer", label="answer", type=ArgumentType.TEXT),
    ]
    properties = {

    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        return {
            "answer": inputs.input.get("answer", "总结答案")
        }
