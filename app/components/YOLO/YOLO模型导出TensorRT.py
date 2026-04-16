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
    """YOLO 模型导出为 TensorRT 组件"""
    
    name = "YOLO 模型导出 TensorRT"
    category = "YOLO/模型导出"
    description = "YOLO模型导出TensorRT组件用于将训练好的YOLO模型导出为TensorRT格式，以获得更快的GPU推理速度。输入为模型文件（.pt），输出为TensorRT引擎文件（.engine）。支持FP16量化，可显著加速推理同时保持较高精度。"
    requirements = "torch,Pillow,ultralytics,onnx,onnxruntime"
    
    # 输入端口定义
    inputs = [
        PortDefinition(name="model", label="YOLO模型文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    
    # 输出端口定义
    outputs = [
        PortDefinition(name="tensorrt_model.engine", label="TensorRT引擎文件", type=ArgumentType.FILE),
        PortDefinition(name="onnx_model.onnx", label="ONNX中间模型", type=ArgumentType.FILE),
        PortDefinition(name="export_info", label="导出信息", type=ArgumentType.JSON),
    ]
    
    # 属性定义
    properties = {
        "task_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="detect",
            label="任务类型",
            choices=["detect", "segment", "classify"]
        ),
        "half_precision": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="启用FP16半精度",
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cuda:0",
            label="目标设备",
            choices=["cuda:0", "cuda:1", "cpu"]
        ),
    }

    def run(self, params, inputs=None):
        """
        执行 YOLO 模型导出为 TensorRT 流程
        输入：YOLO模型文件（.pt）
        输出：TensorRT引擎文件（.engine）、ONNX中间模型
        """
        import os
        import tempfile
        from pathlib import Path
        from ultralytics import YOLO
        import torch
        import json

        # 1. 获取输入
        model_path = inputs.model

        if not model_path:
            raise ValueError("必须提供模型文件！")

        # 2. 验证模型文件
        model_path = Path(model_path)
        if not model_path.exists():
            raise ValueError(f"模型文件不存在: {model_path}")

        # 3. 加载模型
        self.logger.info(f"加载模型: {model_path}")
        try:
            model = YOLO(str(model_path))
        except Exception as e:
            raise RuntimeError(f"模型加载失败: {str(e)}")

        # 4. 创建输出目录
        output_dir = Path("runs/tensorrt_exports")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 5. 导出为 ONNX（TensorRT导出的中间步骤）
        self.logger.info("开始导出ONNX模型...")
        
        onnx_path = output_dir / f"{model_path.stem}_{params.task_type}.onnx"
        
        try:
            # 导出ONNX
            onnx_success = model.export(
                format='onnx',
                imgsz=640,
                half=params.half_precision,
                simplify=True,
                task=params.task_type
            )
            
            # 移动ONNX文件到目标位置
            if isinstance(onnx_success, str) and Path(onnx_success).exists():
                shutil.move(str(onnx_success), str(onnx_path))
            
            self.logger.info(f"ONNX模型已导出: {onnx_path}")
            
        except Exception as e:
            self.logger.warning(f"ONNX导出时出错: {str(e)}")
            # 尝试直接使用原始模型导出ONNX
            onnx_path = None

        # 6. 尝试导出 TensorRT
        tensorrt_path = output_dir / f"{model_path.stem}_{params.task_type}.engine"
        tensorrt_success = False
        tensorrt_error = None
        
        # 检查是否安装了 tensorrt
        try:
            import tensorrt as trt
            self.logger.info("检测到TensorRT，开始导出TensorRT引擎...")
            
            # 由于TensorRT导出需要特定的环境配置，这里提供一个完整的导出逻辑
            tensorrt_path, tensorrt_error = self._export_to_tensorrt(
                model, 
                onnx_path, 
                params,
                output_dir
            )
            
            if tensorrt_path and Path(tensorrt_path).exists():
                tensorrt_success = True
                self.logger.info(f"TensorRT引擎已导出: {tensorrt_path}")
            else:
                self.logger.warning(f"TensorRT导出失败: {tensorrt_error}")
                
        except ImportError:
            self.logger.warning("未安装TensorRT，跳过TensorRT导出")
            tensorrt_error = "TensorRT未安装"
        except Exception as e:
            self.logger.warning(f"TensorRT导出过程出错: {str(e)}")
            tensorrt_error = str(e)

        # 7. 生成导出信息
        export_info = {
            "model_name": model_path.name,
            "task_type": params.task_type,
            "input_size": params.img_size,
            "half_precision": params.half_precision,
            "onnx_export": {
                "success": onnx_path is not None and Path(onnx_path).exists(),
                "path": str(onnx_path) if onnx_path else None,
                "file_size_mb": float(Path(onnx_path).stat().st_size / 1024 / 1024) if onnx_path and Path(onnx_path).exists() else 0
            },
            "tensorrt_export": {
                "success": tensorrt_success,
                "path": str(tensorrt_path) if tensorrt_path else None,
                "file_size_mb": float(Path(tensorrt_path).stat().st_size / 1024 / 1024) if tensorrt_path and Path(tensorrt_path).exists() else 0,
                "error": tensorrt_error
            },
            "optimization_notes": self._get_optimization_notes(params)
        }

        # 8. 保存导出信息JSON
        info_json_path = output_dir / f"{model_path.stem}_export_info.json"
        with open(info_json_path, 'w', encoding='utf-8') as f:
            json.dump(export_info, f, indent=2, ensure_ascii=False)

        self.logger.info("=" * 50)
        self.logger.info("导出完成!")
        self.logger.info(f"ONNX模型: {'成功' if export_info['onnx_export']['success'] else '失败'}")
        self.logger.info(f"TensorRT引擎: {'成功' if export_info['tensorrt_export']['success'] else '失败'}")
        self.logger.info("=" * 50)

        # 返回结果
        return {
            "tensorrt_model.engine": str(tensorrt_path) if tensorrt_success and tensorrt_path else "",
            "onnx_model.onnx": str(onnx_path) if onnx_path and Path(onnx_path).exists() else "",
            "export_info": export_info
        }

    def _export_to_tensorrt(self, model, onnx_path, params, output_dir):
        """导出TensorRT引擎的内部方法"""
        import tensorrt as trt
        import pycuda.driver as cuda
        import pycuda.autoinit
        import os
        
        tensorrt_path = output_dir / f"{Path(onnx_path).stem}.engine"
        error_msg = None
        
        try:
            # 初始化TensorRT
            trt_logger = trt.Logger(trt.Logger.WARNING)
            builder = trt.Builder(trt_logger)
            network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
            parser = trt.OnnxParser(network, trt_logger)
            
            # 读取ONNX文件
            if not onnx_path or not Path(onnx_path).exists():
                return None, "ONNX模型文件不存在"
            
            with open(onnx_path, 'rb') as f:
                onnx_model_content = f.read()
            
            if not parser.parse(onnx_model_content):
                error_msg = f"ONNX解析失败: {parser.error_code()}"
                return None, error_msg
            
            # 配置builder
            config = builder.create_builder_config()
            
            # 设置工作空间大小
            workspace_size = 4 * (1 << 30)  # 4GB
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_size)
            
            # 启用FP16
            if params.half_precision and builder.platform_has_fast_fp16:
                config.set_flag(trt.BuilderFlag.FP16)
                self.logger.info("已启用FP16半精度")
            
            # 构建引擎
            self.logger.info("正在构建TensorRT引擎（这可能需要几分钟）...")
            engine = builder.build_serialized_network(network, config)
            
            if engine is None:
                error_msg = "TensorRT引擎构建失败"
                return None, error_msg
            
            # 保存引擎
            with open(tensorrt_path, 'wb') as f:
                f.write(engine)
            
            self.logger.info(f"TensorRT引擎已保存: {tensorrt_path}")
            return str(tensorrt_path), None
            
        except Exception as e:
            error_msg = f"TensorRT导出出错: {str(e)}"
            self.logger.error(error_msg)
            return None, error_msg

    def _get_optimization_notes(self, params):
        """获取优化建议"""
        notes = []
        
        if params.half_precision:
            notes.append("FP16半精度可以显著提升推理速度，适用于实时场景")
            notes.append("精度损失通常在可接受范围内（<1% mAP）")
        
        if params.dynamic_batch:
            notes.append("动态Batch可以根据输入自动调整批处理大小")
            notes.append("建议在输入尺寸固定的场景下关闭动态Batch")
        
        notes.append("TensorRT引擎只能在NVIDIA GPU上运行")
        notes.append("首次推理会有引擎构建延迟，后续推理速度更快")
        
        return notes


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    import shutil
    
    model = Component()
    result = model.debug(
        params={
            "task_type": "detect",
            "img_size": 640,
            "half_precision": True,
            "simplify_onnx": True,
            "dynamic_batch": False,
            "max_batch_size": 16,
            "device": "cuda:0",
            "workspace_size": 4,
        },
        inputs={
            "model": "yolov8n.pt"
        },
        global_vars={},
        node_id="test_tensorrt_export_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print("\n导出结果:")
    print(f"导出信息: {result.get('export_info')}")
