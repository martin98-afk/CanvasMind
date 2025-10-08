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
    name = "大模型对话"
    category = "大模型组件"
    description = "调用大语言模型（如 GPT）进行对话"
    requirements = "openai"

    inputs = [
        PortDefinition(name="user_input", label="用户输入", type=ArgumentType.TEXT),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON),
    ]
    outputs = [
        PortDefinition(name="response", label="模型回复", type=ArgumentType.TEXT),
        PortDefinition(name="raw_output", label="原始响应", type=ArgumentType.JSON),
    ]

    properties = {
        "model": PropertyDefinition(
            type=PropertyType.TEXT,
            label="模型名称",
            default="gpt-3.5-turbo",
        ),
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            label="API Key",
            default="",
        ),
        "system_prompt": PropertyDefinition(
            type=PropertyType.TEXT,
            label="系统提示词",
            default="你是一个乐于助人的AI助手。",
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.RANGE,
            label="温度（随机性）",
            default="0.7",
            min=0.0,
            max=2.0,
            step=0.1,
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.INT,
            label="最大生成长度",
            default="1000",
        ),
    }

    def run(self, params, inputs):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import os
        import json
        from openai import OpenAI

        # 获取输入
        user_input = inputs.get("user_input", "").strip() if inputs else ""
        history = inputs.get("history", []) if inputs else []

        # 确保 history 是 list 格式
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except:
                history = []

        # 获取参数
        api_key = params.get("api_key") or os.getenv("OPENAI_API_KEY")
        model = params.get("model", "gpt-3.5-turbo")
        system_prompt = params.get("system_prompt", "你是一个乐于助人的AI助手。")
        temperature = float(params.get("temperature", 0.7))
        max_tokens = int(params.get("max_tokens", 1000))

        if not api_key:
            error_msg = "错误：未提供 API Key，请在组件属性中设置或配置环境变量 OPENAI_API_KEY"
            self.logger.error(error_msg)
            return {
                "response": error_msg,
                "raw_output": {"error": "Missing API Key"}
            }

        if not user_input:
            return {
                "response": "",
                "raw_output": {}
            }

        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # 调用大模型
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            reply = response.choices[0].message.content.strip()
            raw_data = response.model_dump()  # 转为 dict，兼容 JSON 输出

            self.logger.info(f"模型回复: {reply[:100]}...")

            return {
                "response": reply,
                "raw_output": raw_data
            }

        except Exception as e:
            error_msg = f"调用大模型失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "response": error_msg,
                "raw_output": {"error": str(e)}
            }
