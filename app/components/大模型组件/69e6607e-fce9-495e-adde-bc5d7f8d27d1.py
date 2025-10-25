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
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON),
    ]

    properties = {
        "model": PropertyDefinition(
            type=PropertyType.TEXT,
            default="$custom.model_name$",
            label="模型名称",
        ),
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="API Key（本地模型可留空）",
        ),
        "base_url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="$custom.url$",
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
        from openai import OpenAI

        self.logger.info(params)
        # 获取输入
        user_input = inputs.user_input.strip()
        history = inputs.history if inputs.history else []

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
        enable_visual = params.visual  # 获取视觉识别开关

        # 构建消息
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)

        # 构建用户消息内容
        user_content = []

        # 如果启用了视觉识别且提供了图像
        if enable_visual:
            # 移除可能的data URI前缀
            image_data = user_input
            if image_data.startswith('data:image'):
                # 提取base64部分
                image_data = image_data.split(',')[1]

            # 验证base64格式
            if self._is_valid_base64(image_data):
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}"
                    }
                })
            else:
                self.logger.warning("提供的base64图像格式无效，将忽略图像输入")
        else:
            user_content.append({
                "type": "text",
                "text": user_input
            })

        # 将用户内容添加到消息中
        messages.append({
            "role": "user",
            "content": user_content if user_content else user_input
        })

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
                    "raw_output": {"error": "Missing API Key or base_url"},
                    "history": history
                }
            client = OpenAI(api_key=api_key)

        # 解析额外模型配置信息
        extra_body = {}
        for item in params.model_params:
            try:
                extra_body[item["key"]] = json.loads(item["value"])
            except json.JSONDecodeError:
                # 如果无法解析为JSON，直接使用字符串值
                extra_body[item["key"]] = item["value"]

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

            # 更新历史记录
            history_message = {
                "role": "user",
                "content": user_input
            }
            if enable_visual:
                # 如果有图像，创建包含图像的历史记录
                history_message = {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                    ]
                }

            history.extend([
                history_message,
                {"role": "assistant", "content": reply}
            ])

            return {
                "response": reply,
                "raw_output": raw_data,
                "history": history
            }

        except Exception as e:
            self.logger.error(f"调用大模型时发生错误: {str(e)}")
            raise e

    def _is_valid_base64(self, s: str) -> bool:
        """
        验证字符串是否为有效的base64编码
        """
        import base64
        try:
            # 检查字符串长度是否为4的倍数
            if len(s) % 4 != 0:
                return False

            # 尝试解码base64
            base64.b64decode(s, validate=True)
            return True
        except Exception:
            return False
