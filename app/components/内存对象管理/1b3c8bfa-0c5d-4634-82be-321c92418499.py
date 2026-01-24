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
    name = "删除内存对象"
    category = "内存对象管理"
    description = "显式释放输入端口连接的内存对象，并触发垃圾回收以释放系统内存。"
    requirements = "numpy"
    
    # 保持 MULTIPLE 连接以接收多个上游对象
    inputs = [
        PortDefinition(name="input_objects", label="待删除对象", type=ArgumentType.TEXT, connection=ConnectionType.MULTIPLE),
    ]
    outputs = [
    ]
    properties = {}

    def run(self, params, inputs=None):
        import sys
        import gc
        import numpy as np

        # 1. 获取输入数据
        # 注意：由于是 MULTIPLE 连接，inputs.get("input_objects") 通常是一个列表
        objects_to_delete = inputs.get("input_objects", [])
        
        if not isinstance(objects_to_delete, list):
            objects_to_delete = [objects_to_delete]

        count = len(objects_to_delete)
        self.logger.info(f"开始清理内存，收到对象数量: {count}")

        # 2. 执行清理逻辑
        try:
            # 遍历并清理列表中的对象
            for i in range(len(objects_to_delete)):
                object_name, attr_name = objects_to_delete[i].split('.', 1)

                # 解析 node_id
                # 兼容 INSTANCE_xxx 和 DATA_xxx 两种前缀
                if object_name.startswith("INSTANCE_"):
                    node_id = object_name.replace("INSTANCE_", "")
                elif object_name.startswith("DATA_"):
                    node_id = object_name.replace("DATA_", "")
                else:
                    # 尝试通过正则提取最后的ID部分 (备用逻辑)
                    node_id = object_name.split("_")[-1]
    
                module_key = f"dynamic_mod_{node_id}"
                del sys.modules[module_key]
                # 如果是 numpy 数组，可以手动清除其引用
                objects_to_delete[i] = None 
            
            # 清空列表引用
            del objects_to_delete
            
            # 3. 强制触发 Python 垃圾回收
            # 这一步是关键，尤其是对于包含循环引用的复杂对象
            gc.collect()
            
            msg = f"成功释放 {count} 个内存对象引用并触发 GC"
            self.logger.info(msg)
            return {"status": msg}

        except Exception as e:
            self.logger.error(f"清理过程中发生错误: {str(e)}")
            return {"status": f"清理失败: {str(e)}"}

if __name__ == "__main__":
    import warnings
    import numpy as np
    warnings.filterwarnings("ignore")
    
    model = Component()
    # 模拟输入一个列表（代表多个连接）
    result = model.debug(
        params={},
        inputs={"input_objects": [np.zeros((100, 100)), "some_data"]},
        node_id="删除对象测试",
        show_execution_time=True
    )
    print(result)