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
    name = "类别分类器"
    category = "大模型组件"
    description = "根据输入文本使用大模型判断其类别"
    requirements = "openai"
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="class", label="判断类别", type=ArgumentType.TEXT),
        PortDefinition(name="reason", label="判别原因", type=ArgumentType.TEXT),
    ]
    properties = {
        "model": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="全局变量",
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
    def _parse_json(self, text: str):
        import json
        import re
        # Step 1: 尝试从 markdown 代码块中提取 json 内容
        # 支持 ```json ... ``` 或 ```python ... ``` 等，只取 json 类型
        json_match = re.search(r"```(?:json|JSON)\s*([\s\S]*?)\s*```", text, re.DOTALL)
        if json_match:
            candidate = json_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                # 如果代码块内 JSON 无效，继续尝试其他方式
                pass
        
        # Step 2: 尝试直接解析整个文本（可能包含多个 JSON 块）
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Step 3: 如果没有完整 JSON，尝试提取最外层的 JSON 对象或数组
        # 支持 {} 或 []，考虑嵌套括号/方括号
        stack = 0
        start = None
        bracket_type = None  # 'curly' for {}, 'square' for []
        
        for i, char in enumerate(text):
            if char == '{':
                if stack == 0:
                    start = i
                    bracket_type = 'curly'
                stack += 1
            elif char == '}':
                if stack == 1 and start is not None:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        # 如果失败，继续寻找下一个匹配
                        start = None
                stack -= 1
            elif char == '[':
                if stack == 0:
                    start = i
                    bracket_type = 'square'
                stack += 1
            elif char == ']':
                if stack == 1 and start is not None:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        start = None
                stack -= 1
        
        # 如果仍无法解析，返回错误
        raise ValueError("No valid JSON object or array found in input")
    
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 构造提示模板，要求模型返回类别和原因
        prompt_template = """
    ## 任务
    你的任务是将用户输入的问题进行分类，并说明判别原因。
    
    ## 类别名
    {}
    
    ## 输出格式
    请严格按照以下 JSON 格式输出，不要输出任何其他内容：
    {{
      "class": "类别名",
      "reason": "判别原因说明"
    }}
    
    ## 用户问题
    {}
    """.format(
            "\n".join([c.clas for c in params.classes]),
            inputs.input1
        )
    
        from openai import OpenAI
    
        try:
            # 初始化客户端
            if self.global_variable.get(params.model).get("API_KEY"):
                client = OpenAI(
                    api_key=self.global_variable.get(params.model).get("API_KEY"),
                    base_url=self.global_variable.get(params.model).get("API_URL")
                )
            else:
                client = OpenAI(
                    api_key="",
                    base_url=self.global_variable.get(params.model).get("API_URL")
                )
    
            messages = [
                {"role": "user", "content": prompt_template}
            ]
    
            response = client.chat.completions.create(
                model=self.global_variable.get(params.model).get("模型名称"),
                messages=messages,
                temperature=self.global_variable.get(params.model).get("温度"),
                max_tokens=self.global_variable.get(params.model).get("最大Token"),
            )
    
            # 解析模型返回的 JSON 内容
            content = response.choices[0].message.content.strip()
            import json
            result = self._parse_json(content)
    
            # 返回两个输出字段
            return {
                "class": result.get("class", "错误"),
                "reason": result.get("reason", "无原因说明")
            }
    
        except Exception as e:
            import traceback
            self.logger.error(f"模型调用失败: {traceback.format_exc()}")
            # 出错时返回默认值
            return {
                "class": "错误",
                "reason": "模型调用失败或返回格式错误"
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
