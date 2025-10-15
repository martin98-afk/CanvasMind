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
    name = "组件保存"
    category = "数据存储"
    description = "生成新组建"
    requirements = ""

    inputs = [
        PortDefinition(name="text", label="输入文本", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="file_path", label="保存路径", type=ArgumentType.TEXT),
    ]

    properties = {
    }
    
    COMPONENT_IMPORT_CODE = """# -*- coding: utf-8 -*-
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
ConnectionType = base_module.ConnectionType\n\n\n"""

    def run(self, params, inputs=None):
        import os
        import uuid
        from pathlib import Path
        # 获取参数
        file_path = Path(__file__).parent.parent / "generated"
        self.logger.info(file_path)
        
        # 确保目录存在
        file_path.mkdir(parents=True, exist_ok=True)
        file_name = f"generated_{uuid.uuid4()}.py"
        # 生成文件路径
        file_full_path = file_path / file_name
        
        # 获取输入文本
        text = inputs.text if inputs else ""
        self.logger.info(inputs)
        # 保存文本到文件
        with open(file_full_path, "w", encoding="utf-8") as f:
            f.write(self.COMPONENT_IMPORT_CODE + text.replace("\\n", "\n").replace('\\"', '"'))
        
        self.logger.info(f"文本已保存到: {file_full_path}")
        
        return {"file_path": file_full_path}
