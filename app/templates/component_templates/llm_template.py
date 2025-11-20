# -*- coding: utf-8 -*-
LLM_NODE_TEMPLATE = '''class Component(BaseComponent):
    name = ""
    category = ""
    description = ""
    requirements = "openai"
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="class", label="判断类别", type=ArgumentType.TEXT),
    ]
    properties = {
        "classes": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="类别定义",
            schema={
                "class": PropertyDefinition(
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
            "\n".join([c.get("class") for c in params.classes]),
            inputs.input1
        )
        from openai import OpenAI
        # 在这里编写你的组件逻辑
        client = OpenAI(api_key="", base_url=self.global_variable.url)
        messages = [
            {
                "role": "user",
                "content": prompt_template
            }
        ]
        try:
            response = client.chat.completions.create(
                model=self.global_variable.model_name,
                messages=messages
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
'''