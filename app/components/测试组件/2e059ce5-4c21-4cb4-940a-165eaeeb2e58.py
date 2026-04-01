# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
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
    """路径测试组件 - 用于处理文件路径相关操作"""
    
    name = "路径测试"
    category = "测试组件"
    description = "处理路径参数，支持文件路径解析和转换"
    requirements = "numpy"
    
    inputs = [
        PortDefinition(name="file_path", label="文件路径", type=ArgumentType.TEXT),
    ]
    
    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.TEXT),
        PortDefinition(name="file_name", label="文件名", type=ArgumentType.TEXT),
        PortDefinition(name="file_dir", label="目录路径", type=ArgumentType.TEXT),
    ]
    
    properties = {
        "width": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="宽度参数",
        ),
        "prefix": PropertyDefinition(
            type=PropertyType.TEXT,
            default="output_",
            label="输出前缀",
        ),
    }
    
    def run(self, params, inputs=None) -> dict:
        """
        处理路径参数并返回结果
        
        Args:
            params: 节点属性（来自UI）
            inputs: 上游输入（key=输入端口名）
            
        Returns:
            输出数据（key=输出端口名）
        """
        # 获取输入
        file_path = inputs.get("file_path", "") if inputs else ""
        
        # 获取属性
        width = getattr(params, "width", "") or ""
        prefix = getattr(params, "prefix", "output_") or "output_"
        
        # 处理文件路径
        file_name = ""
        file_dir = ""
        
        if file_path:
            path_obj = Path(file_path)
            file_name = path_obj.name
            file_dir = str(path_obj.parent)
            self.logger.info(f"处理文件路径: {file_path}")
        
        # 组合输出
        output_value = f"{prefix}{width}" if width else file_name or "default"
        
        self.logger.info(f"输出结果: {output_value}")
        
        return {
            "output1": output_value,
            "file_name": file_name,
            "file_dir": file_dir,
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"width": "100", "prefix": "test_"},
        inputs={"file_path": "D:/test/file.txt"},
        node_id="测试模型",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True,
        global_vars={}
    )
    print(result)
