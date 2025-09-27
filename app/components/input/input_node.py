"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: logistic_regression.py
@time: 2025/9/26 14:41
@desc: 
"""
from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, ArgumentType


class InputComponent(BaseComponent):
    name="文本输入"
    category="数据集成"
    description="文本输入内容"
    inputs=[]
    outputs=[
        PortDefinition(name="text", label="text")
    ]
    properties={
        "input": PropertyDefinition(
            type=ArgumentType.TEXT,
            default="文本内容",
            label="输入文本"
        )
    }

    def run(self, params, inputs=None):
        return {"text": params["input"]}