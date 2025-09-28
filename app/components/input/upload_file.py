"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: upload_file.py
@time: 2025/9/28 15:21
@desc: 
"""
import pandas as pd

from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, ArgumentType


class Component(BaseComponent):
    name="文档上传"
    category="数据集成"
    description="接收本地上传文件"
    outputs=[PortDefinition(name="file", label="csv文件", type=ArgumentType.FILE)]

    def run(self, params, inputs=None):
        pass