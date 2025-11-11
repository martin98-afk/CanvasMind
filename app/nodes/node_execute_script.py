_EXECUTION_SCRIPT_TEMPLATE = '''# -*- coding: utf-8 -*-
import sys
import os
import pickle
import importlib.util
import traceback
from pathlib import Path
from loguru import logger

# ==================== 配置 ====================
logger.remove()  # 禁用默认 handler

# ==================== 工具函数 ====================

def _is_safe_path(base_path: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(base_path.resolve())
        return True
    except ValueError:
        return False

# ==================== 主执行逻辑 ====================

if __name__ == "__main__":
    CLASS_NAME = "{class_name}"
    FILE_PATH = r"{file_path}"
    LOG_FILE_PATH = r"{log_file_path}"
    RESULT_PATH = r"{result_path}"
    ERROR_PATH = r"{error_path}"
    NODE_ID = "{node_id}"

    # 日志配置（与原逻辑一致）
    log_handler_id = logger.add(
        LOG_FILE_PATH,
        level="DEBUG",
        format="[{{time:YYYY-MM-DD HH:mm:ss}}] {{function}}-{{line}} {{level}}: {{message}}",
        encoding='utf-8',
        filter=lambda record: record["extra"].get("node_id") == NODE_ID,
        enqueue=True,
        rotation="10 MB",
        retention=3
    )
    node_logger = logger.bind(node_id=NODE_ID)

    try:
        # === 1. 加载组件类（不变）===
        spec = importlib.util.spec_from_file_location(CLASS_NAME, FILE_PATH)
        if spec is None:
            raise ImportError(f"无法加载模块: {{FILE_PATH}}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        comp_class = getattr(module, CLASS_NAME, None)
        if comp_class is None:
            raise AttributeError(f"模块中未找到类: {{CLASS_NAME}}")

        # === 2. 获取 params, inputs, global_variables ===
        # subprocess 模式：从文件加载
        PARAMS_PATH = r"{params_path}"  # 注意：这行只在 subprocess 模式下有意义
        with open(PARAMS_PATH, 'rb') as f:
            loaded = pickle.load(f)
            if not isinstance(loaded, (tuple, list)) or len(loaded) != 3:
                raise ValueError("参数文件格式错误：应为 (params, inputs, global_vars) 三元组")
            params, inputs, global_variables = loaded
        node_logger.info("从参数文件加载配置执行")

        # === 3. 执行组件 ===
        comp_instance = comp_class()
        comp_instance.logger = node_logger
        node_logger.info("开始执行组件")
        output = comp_instance.execute(params, inputs, global_variables, NODE_ID)

        # === 4. 保存结果 ===
        with open(RESULT_PATH, 'wb') as f:
            pickle.dump(output, f)

        node_logger.success("节点执行完成")

    except ImportError as e:
        error_info = {{
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": "ImportError",
            "node_id": NODE_ID
        }}
        with open(ERROR_PATH, 'wb') as f:
            pickle.dump(error_info, f)
        node_logger.error(f"导入错误: {{e}}")
        print(f"EXECUTION_IMPORT_ERROR: {{e}}", flush=True)
        
    except Exception as e:
        error_info = {{
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": type(e).__name__,
            "node_id": NODE_ID
        }}
        with open(ERROR_PATH, 'wb') as f:
            pickle.dump(error_info, f)
        node_logger.error(f"执行异常: {{e}}")
        print(f"EXECUTION_ERROR: {{e}}", flush=True)
        
    finally:
        if 'log_handler_id' in locals:
            logger.remove(log_handler_id)
'''