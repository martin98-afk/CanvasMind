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


class LLMGenerateAPIComponent(BaseComponent):
    name = "大模型生成接口"
    category = "大模型组件"
    description = "调用大模型API生成文本内容，支持自定义提示词和参数配置"
    requirements = "openai>=1.0"
    inputs = [
        PortDefinition(name="prompt", label="提示词", type=ArgumentType.TEXT),
        PortDefinition(name="system_prompt", label="系统指令", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="generated_text", label="生成文本", type=ArgumentType.TEXT),
        PortDefinition(name="response_metadata", label="响应元数据", type=ArgumentType.JSON),
    ]

    properties = {
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            label="模型名称",
            default="gpt-3.5-turbo",
            choices=[
                "gpt-3.5-turbo",
                "gpt-4",
                "gpt-4-turbo",
                "qwen-max",
                "qwen-plus",
                "qwen/qwen3-30b-a3b-2507"
            ]
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.FLOAT,
            label="温度",
            default="0.7",
            min=0.0,
            max=2.0,
            step=0.1
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.INT,
            label="最大生成长度",
            default="1024",
            min=1,
            max=8192
        ),
        "top_p": PropertyDefinition(
            type=PropertyType.FLOAT,
            label="Top P",
            default="1.0",
            min=0.0,
            max=1.0,
            step=0.01
        ),
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            label="API密钥",
            default="",
            description="输入你的大模型API密钥，如OpenAI或通义千问API Key"
        ),
        "base_url": PropertyDefinition(
            type=PropertyType.TEXT,
            label="API基础地址",
            default="https://api.openai.com/v1",
            description="如使用自定义API网关或代理，请填写对应地址"
        ),
        "use_stream": PropertyDefinition(
            type=PropertyType.BOOL,
            label="启用流式输出",
            default="false"
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import openai
        from typing import Dict, Any
        import json

        # 获取输入数据
        prompt = inputs.get("prompt", "") if inputs else ""
        system_prompt = inputs.get("system_prompt", "") if inputs else ""

        # 获取配置参数
        model_name = params.model
        temperature = float(params.temperature)
        max_tokens = int(params.max_tokens)
        top_p = float(params.top_p)
        api_key = params.api_key
        base_url = params.base_url
        use_stream = params.use_stream == "true"

        # 验证API密钥
        if not api_key:
            self.logger.error("API密钥未配置")
            raise ValueError("API密钥不能为空")

        # 初始化OpenAI客户端
        client = openai.OpenAI(api_key=api_key, base_url=base_url)

        # 构建消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 调用API生成文本
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stream=use_stream
            )

            # 处理流式输出
            if use_stream:
                full_response = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                generated_text = full_response
            else:
                generated_text = response.choices[0].message.content

            # 构建元数据
            metadata = {
                "model": model_name,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "created": response.created,
                "request_id": response.id
            }

            self.logger.info(f"大模型生成成功，使用模型: {model_name}, 总token数: {metadata['total_tokens']}")

            return {
                "generated_text": generated_text,
                "response_metadata": json.dumps(metadata, ensure_ascii=False, indent=2)
            }

        except Exception as e:
            self.logger.error(f"调用大模型API失败: {str(e)}")
            raise RuntimeError(f"大模型生成失败: {str(e)}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = LLMGenerateAPIComponent()
    result = model.debug(
        params={
            "model": "qwen/qwen3-30b-a3b-2507",
            "temperature": "0.7",
            "max_tokens": "512",
            "top_p": "1.0",
            "api_key": "xxx",
            "base_url": "http://127.0.0.1:1234/v1",
            "use_stream": "false"
        },
        inputs={
            "prompt": "请用中文写一段关于人工智能的短文。",
            "system_prompt": "你是一个专业的科技作家，擅长用简洁明了的语言撰写科普文章。"
        },
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
