_EXECUTION_SCRIPT_TEMPLATE = '''# -*- coding: utf-8 -*-
import sys
import os
import pickle
import importlib.util
import traceback
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path
from loguru import logger

# ==================== 输出重定向（干净输出，无前缀） ====================
class StreamToLogger:
    def __init__(self, log_func):
        self.log_func = log_func
        self.line_buffer = ""

    def write(self, buf):
        self.line_buffer += buf
        while "\\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\\n", 1)
            if line.strip():
                self.log_func(line)

    def flush(self):
        if self.line_buffer.strip():
            self.log_func(self.line_buffer)
            self.line_buffer = ""


# ==================== 配置 ====================
logger.remove()  # 移除默认 handler

# ==================== 主执行逻辑 ====================
if __name__ == "__main__":
    CLASS_NAME = "{class_name}"
    FILE_PATH = r"{file_path}"
    LOG_FILE_PATH = r"{log_file_path}"
    RESULT_PATH = r"{result_path}"
    ERROR_PATH = r"{error_path}"
    NODE_ID = "{node_id}"

    # --- 1. 结构化日志 handler（带时间、级别）---
    structured_handler_id = logger.add(
        LOG_FILE_PATH,
        level="DEBUG",
        format="[{{time:YYYY-MM-DD HH:mm:ss}}] {{function}}-{{line}} {{level}}: {{message}}",
        encoding='utf-8',
        filter=lambda record: record["extra"].get("node_id") == NODE_ID and not record["extra"].get("raw", False),
        enqueue=True,
        rotation="10 MB",
        retention=3
    )
    node_logger = logger.bind(node_id=NODE_ID)  # 用于组件内部日志

    # --- 2. 原始输出 handler（无任何前缀）---
    raw_handler_id = logger.add(
        LOG_FILE_PATH,
        level="DEBUG",
        format="{{message}}",  # 关键：只输出 message
        encoding='utf-8',
        filter=lambda record: record["extra"].get("node_id") == NODE_ID and record["extra"].get("raw", True),
        enqueue=True,
        rotation="10 MB",
        retention=3
    )
    raw_logger = logger.bind(node_id=NODE_ID, raw=True)  # 专用于 stdout/stderr

    # --- 3. 重定向 stdout/stderr 到 raw_logger ---
    sys.stdout = StreamToLogger(raw_logger.info)
    sys.stderr = StreamToLogger(raw_logger.error)

    try:
        # === 加载组件类 ===
        spec = importlib.util.spec_from_file_location(CLASS_NAME, FILE_PATH)
        if spec is None:
            raise ImportError(f"无法加载模块: {{FILE_PATH}}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        comp_class = getattr(module, CLASS_NAME, None)
        if comp_class is None:
            raise AttributeError(f"模块中未找到类: {{CLASS_NAME}}")

        # === 从参数文件加载 (params, inputs, global_variables) ===
        PARAMS_PATH = r"{params_path}"
        with open(PARAMS_PATH, 'rb') as f:
            loaded = pickle.load(f)
            if not isinstance(loaded, (tuple, list)) or len(loaded) != 3:
                raise ValueError("参数文件格式错误：应为 (params, inputs, global_vars) 三元组")
            params, inputs, global_variables = loaded
        node_logger.info("从参数文件加载配置执行")

        # === 执行组件 ===
        comp_instance = comp_class()
        comp_instance.logger = node_logger  # 组件内部可使用带前缀的 logger
        node_logger.info("开始执行组件")
        output = comp_instance.execute(params, inputs, global_variables, NODE_ID)

        # === 保存结果 ===
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
        raw_logger.error(f"EXECUTION_IMPORT_ERROR: {{e}}")

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
        raw_logger.error(f"EXECUTION_ERROR: {{e}}")
'''