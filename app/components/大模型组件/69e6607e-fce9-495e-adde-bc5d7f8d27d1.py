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
    description = "调用大语言模型（支持 OpenAI 或本地兼容 API 的模型）"
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
            default="qwen/qwen3-30b-a3b",  # 示例：Ollama 模型名
            label="模型名称",
        ),
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="API Key（本地模型可留空）",
        ),
        "base_url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="http://127.0.0.1:1234/v1",  # Ollama 默认地址
            label="API 基础地址（本地模型必填）",
        ),
        "system_prompt": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="你是一个乐于助人的AI助手。",
            label="系统提示词",
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.7",
            label="温度（随机性）",
            min=0.0,
            max=2.0,
            step=0.1,
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.INT,
            default=1000,
            label="最大生成长度",
        ),
    }

    def run(self, params, inputs):
        import os
        import json
        from openai import OpenAI

        # 获取输入
        user_input = inputs.get("user_input", "").strip() if inputs else ""
        history = inputs.get("history", []) if inputs else []

        if isinstance(history, str):
            try:
                history = json.loads(history)
            except:
                history = []

        # 获取参数
        model = params.get("model", "qwen:7b")
        api_key = params.get("api_key") or os.getenv("OPENAI_API_KEY")
        base_url = params.get("base_url", "").strip()
        system_prompt = params.get("system_prompt", "你是一个乐于助人的AI助手。")
        temperature = float(params.get("temperature", 0.7))
        max_tokens = int(params.get("max_tokens", 1000))

        if not user_input:
            return {"response": "", "raw_output": {}}

        # 构建消息
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # 自动处理 API Key：本地模型通常不需要
        use_local = bool(base_url)
        if use_local:
            # 本地模型：api_key 可为空，base_url 必须有效
            client = OpenAI(api_key=api_key or "ollama", base_url=base_url)
        else:
            # 云端 OpenAI
            if not api_key:
                error_msg = "错误：未提供 API Key，且未设置本地 API 地址"
                self.logger.error(error_msg)
                return {
                    "response": error_msg,
                    "raw_output": {"error": "Missing API Key or base_url"}
                }
            client = OpenAI(api_key=api_key)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            reply = response.choices[0].message.content.strip()
            raw_data = response.model_dump()

            self.logger.info(f"模型回复: {reply[:100]}...")
            return {
                "response": reply,
                "raw_output": raw_data
            }

        except Exception as e:
            import traceback
            error_msg = f"调用大模型失败: {traceback.format_exc()}"
            self.logger.error(error_msg)
            raise e
