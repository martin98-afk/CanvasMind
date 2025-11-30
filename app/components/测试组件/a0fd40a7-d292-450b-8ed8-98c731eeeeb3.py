# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent / "base.py" if (Path(__file__).parent / "base.py").exists() else Path(__file__).parent.parent / "base.py"
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
    name = "测试参数效果"
    category = "测试组件"
    description = "根据输入文本使用大模型判断其类别"
    requirements = "openai"
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="class", label="判断类别", type=ArgumentType.TEXT),
    ]
    properties = {
        "model_config": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="",
            label="大模型配置",
        ),
        "classes": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="类别定义",
            schema={
                "clas": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="类别",
                ),
            }
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        prompt_template = """
        ## 任务
        你的任务是将用户输入的问题进行分类
        
        ## 类别名
        {}
        
        ## 输出格式
        只输出用户问题所属的类别名，如果不属于任何类别则返回 “错误”。
        
        ## 用户问题
        {}
        """.format(
            "\n".join([c.clas for c in params.classes]),
            inputs.input1
        )
        from openai import OpenAI
        # 在这里编写你的组件逻辑
        if self.global_variable.get(params.model_config.get("API_KEY")):
            client = OpenAI(
                api_key=self.global_variable.get(params.model_config.get("API_KEY")),
                base_url=self.global_variable.get(params.model_config.get("API_URL"))
                )
        else:
            client = OpenAI(
                api_key="",
                base_url=self.global_variable.get(params.model_config.get("API_URL"))
                )
        messages = [
            {
                "role": "user",
                "content": prompt_template
            }
        ]
        try:
            response = client.chat.completions.create(
                model=self.global_variable.get(params.model_config.get("模型名称")),
                messages=messages,
                temperature=self.global_variable.get(params.model_config.get("温度")),
                max_tokens=self.global_variable.get(params.model_config.get("最大Token")),
            )
        except:
            pass
        return {
            "class": response.choices[0].message.content.strip()
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
