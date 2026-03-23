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
    name = "文件重命名为时间戳文件"
    category = "数据存储"
    description = "将文件重命名为 {原文件名}_{时间戳}.{原扩展名}，生成唯一的带时间戳文件名"
    requirements = ""
    
    inputs = [
        PortDefinition(name="input_file", label="输入文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_path", label="输出路径", type=ArgumentType.TEXT),
    ]
    
    properties = {
        "time_format": PropertyDefinition(
            type=PropertyType.TEXT,
            default="%Y%m%d_%H%M%S",
            label="时间格式",
            description="Python时间格式化字符串，默认: %Y%m%d_%H%M%S",
        ),
        "preserve_extension": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="保留原扩展名",
            description="是否保留原文件扩展名",
        ),
        "output_dir": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="输出目录",
            description="输出目录路径，留空则使用原文件目录",
        ),
    }
    
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import os
        import shutil
        from datetime import datetime
        
        # 获取配置参数
        time_format = params.get("time_format", "%Y%m%d_%H%M%S")
        preserve_extension = params.get("preserve_extension", True)
        output_dir = params.get("output_dir", "")
        
        # 获取输入文件路径
        input_file = inputs.get("input_file") if inputs else None
        
        if not input_file:
            raise ValueError("未提供输入文件，请连接输入端口")
        
        # 处理输入（可能是路径字符串或文件对象）
        if hasattr(input_file, 'read'):
            # 文件对象，临时保存
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(getattr(input_file, 'name', ''))[1]) as tmp:
                shutil.copyfileobj(input_file, tmp)
                input_path = tmp.name
                temp_file = True
        else:
            input_path = str(input_file)
            temp_file = False
        
        # 检查文件是否存在
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        
        # 获取原文件信息
        original_dir = os.path.dirname(input_path)
        original_name = os.path.splitext(os.path.basename(input_path))[0]
        original_ext = os.path.splitext(os.path.basename(input_path))[1]
        
        # 生成时间戳
        timestamp = datetime.now().strftime(time_format)
        
        # 构建新文件名
        if preserve_extension:
            new_filename = f"{original_name}_{timestamp}{original_ext}"
        else:
            new_filename = f"{original_name}_{timestamp}"
        
        # 确定输出目录
        if output_dir:
            target_dir = output_dir
        else:
            target_dir = original_dir
        
        # 确保输出目录存在
        os.makedirs(target_dir, exist_ok=True)
        
        # 构建完整输出路径
        output_path = os.path.join(target_dir, new_filename)
        
        # 复制文件（保留原文件）
        shutil.copy2(input_path, output_path)
        
        # 清理临时文件
        if temp_file:
            try:
                os.unlink(input_path)
            except:
                pass
        
        self.logger.info(f"文件已重命名为时间戳文件: {output_path}")
        
        return {
            "output_path": output_path
        }


if __name__ == "__main__":
    import warnings
    import tempfile
    import os
    warnings.filterwarnings("ignore")
    
    # 创建测试文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        test_file_path = f.name
        f.write("测试文件内容")
    
    try:
        model = Component()
        result = model.debug(
            params={
                "time_format": "%Y%m%d_%H%M%S",
                "preserve_extension": True,
                "output_dir": ""
            },
            inputs={"input_file": test_file_path},
            node_id="文件重命名测试",
            show_input_types=True,
            show_output_types=True,
            show_execution_time=True,
            global_vars={}
        )
        print("测试结果:", result)
        print(f"✓ 文件重命名成功！新文件路径: {result.get('output_path')}")
        
        # 清理测试文件
        if os.path.exists(test_file_path):
            os.unlink(test_file_path)
        output_path = result.get('output_path')
        if output_path and os.path.exists(output_path):
            os.unlink(output_path)
            
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保临时文件被清理
        if os.path.exists(test_file_path):
            try:
                os.unlink(test_file_path)
            except:
                pass
