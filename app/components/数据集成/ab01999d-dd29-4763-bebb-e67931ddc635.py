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
    name = "获取当前时间"
    category = "数据集成"
    description = "使用datetime获取当前时间，返回结果格式：yyyy-mm-dd HH:MM:SS"
    requirements = ""
    inputs = [
    ]
    outputs = [
        PortDefinition(name="timestamp", label="输出时间", type=ArgumentType.TEXT),
    ]
    properties = {
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "timestamp": now
        }
