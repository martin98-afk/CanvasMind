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
    name = "大模型对话测试"
    category = "大模型组件"
    description = "调用大语言模型（支持 OpenAI 或本地兼容 API 的模型）"
    requirements = "Pillow,openai"
    inputs = [
        PortDefinition(name="input_data", label="输入数据", type=ArgumentType.TEXT),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON),
    ]
    outputs = [
        PortDefinition(name="response", label="模型回复", type=ArgumentType.TEXT),
        PortDefinition(name="raw_output", label="原始响应", type=ArgumentType.JSON),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON),
    ]
    properties = {
        "model": PropertyDefinition(
            type=PropertyType.TEXT,
            default="qwen3-30b-a3b",
            label="模型名称",
        ),
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="API Key（本地模型可留空）",
        ),
        "base_url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="http://168.168.10.110:20000",
            label="API 基础地址（本地模型必填）",
        ),
        "system_prompt": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="""你是一个乐于助人的AI助手。""",
            label="系统提示词",
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.7",
            label="温度（随机性）",
            min=0.0,
            max=1.0,
            step=0.1,
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.INT,
            default=1000,
            label="最大生成长度",
        ),
        "visual": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="启用视觉识别",
        ),
        "model_params": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="模型配置",
            schema={
                "key": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="key",
                ),
                "value": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="value",
                ),
            }
        ),
    }
    def run(self, params, inputs):
        import os
        import json
        import base64
        from openai import OpenAI
        from PIL import Image
        import io
        self.logger.info(params)
        # 处理输入数据
        if params.visual:
            # 处理图像输入
            input_data = inputs.input_data
        else:
            # 处理文本输入
            user_input = inputs.input_data.strip() if inputs else ""
            processed_input = user_input
        history = inputs.history if inputs.history else []
        # 处理历史记录
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except:
                history = []
        # 获取参数
        model = params.model
        api_key = params.api_key
        base_url = params.base_url.strip()
        system_prompt = params.system_prompt
        temperature = float(params.temperature)
        max_tokens = int(params.max_tokens)
        # 构建消息
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        # 添加多模态内容
        if params.visual:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{input_data}"}}
                ]
            })
        else:
            messages.append({"role": "user", "content": processed_input})
        self.logger.info(messages)
        # 处理API密钥
        use_local = bool(base_url)
        if use_local:
            client = OpenAI(api_key=api_key or "ollama", base_url=base_url)
        else:
            if not api_key:
                error_msg = "错误：未提供 API Key，且未设置本地 API 地址"
                self.logger.error(error_msg)
                return {
                    "response": error_msg,
                    "raw_output": {"error": "Missing API Key or base_url"}
                }
            client = OpenAI(api_key=api_key)
        # 解析额外模型配置信息
        extra_body = {}
        for item in params.model_params:
            extra_body[item["key"]] = json.loads(item["value"])
        try:
            response = client.chat.completions.create(
                extra_body=extra_body,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self.logger.info(response)
            reply = response.choices[0].message.content.strip()
            raw_data = response.model_dump()
            # 更新对话历史
            if params.visual:
                messages.append({
                    "role": "assistant",
                    "content": reply
                })
            else:
                messages.append({"role": "assistant", "content": reply})
            return {
                "response": reply,
                "raw_output": raw_data,
                "history": messages
            }
        except Exception as e:
            self.logger.error(f"模型调用失败: {str(e)}")
            raise RuntimeError(f"模型推理错误: {str(e)}") from e