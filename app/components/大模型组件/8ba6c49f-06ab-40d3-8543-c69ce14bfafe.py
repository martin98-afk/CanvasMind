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
    name = "构建多轮对话"
    category = "大模型组件"
    description = "用于构建符合大模型输入格式的多轮对话消息列表，支持追加新消息。"
    requirements = ""

    inputs = [
        PortDefinition(name="history", label="输入1", type=ArgumentType.JSON, connection=ConnectionType.MULTIPLE),
    ]

    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.JSON),
    ]

    properties = {
        "prop1": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="新增消息",
            schema={
                "role": {
                    "type": PropertyType.CHOICE.value,
                    "default": "user",
                    "label": "角色",
                    "choices": ["system", "user", "assistant"]
                },
                "content": {
                    "type": PropertyType.LONGTEXT.value,
                    "default": "",
                    "label": "内容",
                },
            }
        ),
    }

    def run(self, params, inputs = None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 获取历史对话（如果有的话）
        self.logger.info(params.prop1[0].role)
        history = inputs.history if inputs else None
        if history is None:
            history = []

        # 验证 history 是否为 list
        if not isinstance(history, list):
            history = []
        self.logger.info(params.prop1)

        # 获取用户配置的新消息
        messages = history + [
            {
                "role": message.role,
                "content": message.content
            } for message in params.prop1
        ]

        # 返回符合大模型输入格式的对话列表
        return {
            "output1": messages  # 注意：必须与 outputs 中的 name 一致
        }
