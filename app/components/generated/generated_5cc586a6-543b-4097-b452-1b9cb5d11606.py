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
    name = "大模型智能问题分类"
    category = "大模型组件"
    description = "根据用户的问题文本，使用大模型进行智能问题分类"
    requirements = "numpy,pandas"

    inputs = [
        PortDefinition(name="question", label="用户的问题文本", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="classification", label="问题分类结果", type=ArgumentType.TEXT),
    ]

    properties = {
        "category_list": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="['技术问题', '业务咨询', '产品建议', '其他']",
            label="问题分类列表",
        ),
    }

    def run(self, params, inputs = None):
        import re
        import numpy
        import pandas
        self.logger.info(inputs)
        question = inputs.get("question", "") if inputs else ""
        category_list = params.get("category_list", "['技术问题', '业务咨询', '产品建议', '其他']")

        # 将分类列表转换为Python列表
        try:
            category_list = eval(category_list)
        except:
            category_list = ["技术问题", "业务咨询", "产品建议", "其他"]

        # 简单的分类逻辑（可以根据实际需求进行扩展）
        if any(keyword in question for keyword in ["如何", "什么", "哪里", "当", "为什么", "when", "where", "why"]):
            classification = "技术问题"
        elif any(keyword in question for keyword in ["建议", "改进", "优化"]):
            classification = "产品建议"
        elif any(keyword in question for keyword in ["业务", "流程", "操作"]):
            classification = "业务咨询"
        else:
            classification = "其他"

        self.logger.info(f"分类结果: {classification}")    # 组件内日志输出使用类中定义的self.logger，使用方法与loguru.logger使用方法一致。
        
        return {"classification": classification}