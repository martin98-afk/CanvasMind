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

# ==================== 输出重定向（捕获 stdout/stderr） ====================
class StreamToLogger:
    def __init__(self, log_func):
        self.log_func = log_func
        self.line_buffer = ""

    def write(self, buf):
        if not buf:
            return
        self.line_buffer += buf
        while "\\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\\n", 1)
            self.log_func(line)

    def flush(self):
        if self.line_buffer:
            self.log_func(self.line_buffer)
            self.line_buffer = ""

# ==================== 动态日志格式化 ====================
def sink_formatter(record):
    """
    此处花括号已双重转义，防止 .format() 报错
    """
    if record["extra"].get("raw") is True:
        return "{{message}}\\n"
    return "[{{time:YYYY-MM-DD HH:mm:ss}}] {{function}}-{{line}} {{level}}: {{message}}\\n"

# ==================== 主执行逻辑 ====================
if __name__ == "__main__":
    # --- 以下是 .format() 填充的变量 ---
    CLASS_NAME = "{class_name}"
    FILE_PATH = r"{file_path}"
    LOG_FILE_PATH = r"{log_file_path}"
    RESULT_PATH = r"{result_path}"
    ERROR_PATH = r"{error_path}"
    NODE_ID = "{node_id}"
    WORKFLOW_PATH = "{workflow_path}"
    PARAMS_PATH = r"{params_path}"
    # 1. 配置唯一的 Sink
    logger.remove()
    logger.add(
        LOG_FILE_PATH,
        format=sink_formatter,
        level="DEBUG",
        encoding='utf-8',
        enqueue=True,
        rotation="10 MB",
        filter=lambda record: record["extra"].get("node_id") == NODE_ID
    )

    node_logger = logger.bind(node_id=NODE_ID)
    raw_logger = logger.bind(node_id=NODE_ID, raw=True)

    # 2. 重定向
    sys.stdout = StreamToLogger(raw_logger.info)
    sys.stderr = StreamToLogger(raw_logger.error)

    try:
        node_output_dir = Path(WORKFLOW_PATH) / "workspace" / NODE_ID
        node_output_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(str(node_output_dir))
        spec = importlib.util.spec_from_file_location(CLASS_NAME, FILE_PATH)
        if spec is None:
            raise ImportError(f"无法加载模块: {{FILE_PATH}}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        comp_class = getattr(module, CLASS_NAME, None)
        if comp_class is None:
            raise AttributeError(f"模块中未找到类: {{CLASS_NAME}}")

        with open(PARAMS_PATH, 'rb') as f:
            params, inputs, global_variables = pickle.load(f)

        node_logger.info("开始执行组件")

        comp_instance = comp_class()
        comp_instance.logger = node_logger
        output = comp_instance.execute(params, inputs, global_variables, NODE_ID, WORKFLOW_PATH)

        with open(RESULT_PATH, 'wb') as f:
            pickle.dump(output, f)

        node_logger.success("节点执行成功")

    except Exception as e:
        tb = traceback.format_exc()
        # 字典字面量也需要双花括号转义
        error_info = {{
            "error": str(e),
            "traceback": tb,
            "type": type(e).__name__,
            "node_id": NODE_ID
        }}
        with open(ERROR_PATH, 'wb') as f:
            pickle.dump(error_info, f)

        node_logger.error(f"执行异常: {{e}}")

    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        logger.complete() 
'''