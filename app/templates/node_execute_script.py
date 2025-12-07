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

# ==================== 输出重定向 ====================
class StreamToLogger:
    def __init__(self, logger_func, node_id):
        self.logger_func = logger_func
        self.node_id = node_id
        self.line_buffer = ""

    def write(self, buf):
        # 处理不完整的行（避免中途截断）
        self.line_buffer += buf
        while "\\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\\n", 1)
            if line.strip():  # 忽略纯空行（可选）
                self.logger_func(f"[STDOUT] {{line}}")

    def flush(self):
        # 处理最后未换行的输出（非严格必要，但更健壮）
        if self.line_buffer.strip():
            self.logger_func(f"[STDOUT] {{self.line_buffer}}")
            self.line_buffer = ""

# 同理处理 stderr（可复用，但用不同前缀）
class StreamToErrorLogger:
    def __init__(self, logger_func, node_id):
        self.logger_func = logger_func
        self.node_id = node_id
        self.line_buffer = ""

    def write(self, buf):
        self.line_buffer += buf
        while "\\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\\n", 1)
            if line.strip():
                self.logger_func(f"[STDERR] {{line}}")

    def flush(self):
        if self.line_buffer.strip():
            self.logger_func(f"[STDERR] {{self.line_buffer}}")
            self.line_buffer = ""

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

    # === 重定向 stdout/stderr 到日志 ===
    sys.stdout = StreamToLogger(node_logger.info, NODE_ID)
    sys.stderr = StreamToErrorLogger(node_logger.error, NODE_ID)

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
'''