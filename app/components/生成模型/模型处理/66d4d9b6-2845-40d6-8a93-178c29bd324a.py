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
    name = "分片模型合并(Safetensors)"
    category = "生成模型/模型处理"
    description = "将多个分片 safetensors 文件合并为一个完整的文件，支持 .001 或 sharded 格式"
    requirements = "safetensors,torch"
    
    inputs = []
    outputs = [
        PortDefinition(name="model_path", label="合并后模型路径", type=ArgumentType.TEXT),
    ]
    
    properties = {
        "output_name": PropertyDefinition(
            type=PropertyType.TEXT,
            default="merged_model.safetensors",
            label="输出文件名",
        ),
        "model_list": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="分片文件列表(按顺序)",
            schema={
                "model_path": PropertyDefinition(
                    type=PropertyType.FILE,
                    default="",
                    label="文件路径",
                ),
            }
        ),
    }

    def run(self, params, inputs=None):
        import os
        import torch
        from safetensors.torch import load_file, save_file
        import gc

        # 1. 获取并排序文件路径
        model_items = params.get("model_list", [])
        if not model_items:
            raise ValueError("未提供任何模型分片文件")
        
        # 按照你填写的顺序提取路径
        file_paths = [item["model_path"] for item in model_items if item["model_path"]]
        self.logger.info(f"准备合并以下分片: {file_paths}")

        # 2. 确定输出路径
        # 默认保存到第一个文件所在的目录下
        workspace_dir = os.path.dirname(file_paths[0])
        output_filename = params.get("output_name", "merged_model.safetensors")
        save_path = os.path.join(workspace_dir, output_filename)

        # 3. 执行合并 (优化内存模式)
        merged_state_dict = {}
        
        try:
            for i, p in enumerate(file_paths):
                if not os.path.exists(p):
                    self.logger.error(f"分片不存在: {p}")
                    continue
                
                self.logger.info(f"正在加载分片 [{i+1}/{len(file_paths)}]: {os.path.basename(p)}")
                
                # 加载当前分片
                current_sd = load_file(p, device="cpu")
                
                # 将 Key 合并进主字典
                merged_state_dict.update(current_sd)
                
                # 立即释放当前分片的引用
                del current_sd
                gc.collect() # 强制垃圾回收

            # 4. 保存合并后的文件
            self.logger.info(f"所有分片读取完成，正在写入文件: {save_path}")
            # 使用 float16 保存以减少空间占用（SD 3.5 建议用这个）
            # 也可以根据原模型自动判断
            save_file(merged_state_dict, save_path)
            
            # 5. 彻底释放内存
            merged_state_dict.clear()
            del merged_state_dict
            gc.collect()

            self.logger.info(f"✅ 合并成功！文件已保存至: {save_path}")
            
            # 返回文件路径，给下游的 ComfyUI 加载器使用
            return {"model_path": save_path}

        except Exception as e:
            self.logger.error(f"合并过程中出错: {str(e)}")
            raise e