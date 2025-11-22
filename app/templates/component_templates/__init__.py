# -*- coding: utf-8 -*-
from .base import DEFAULT_NODE_TEMPLATE
from .llm_template import LLM_NODE_TEMPLATE


default_templates = {
    "基础组件": DEFAULT_NODE_TEMPLATE,
    "大模型组件": LLM_NODE_TEMPLATE
}