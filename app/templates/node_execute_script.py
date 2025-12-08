_EXECUTION_SCRIPT_TEMPLATE = '''# -*- coding: utf-8 -*-
import sys
import os
import pickle
import importlib.util
import traceback
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path

# ==================== 全局日志写入函数（保序核心） ====================
LOG_FILE_PATH = r"{log_file_path}"
NODE_ID = "{node_id}"

def write_log_message(message: str, level: str = "INFO", is_raw: bool = False):
    """
    统一日志写入点，保证顺序。
    - is_raw=True: 来自 print / stdout / stderr → 无前缀
    - is_raw=False: 来自 logger → 带前缀
    """
    import datetime
    if is_raw:
        line = message
    else:
        # 模拟 loguru 的格式：[时间] 函数-行号 级别: message
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{{now}} | {{level}}: {{message}}"
    try:
        with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\\n')
    except Exception:
        pass  # 避免日志写入错误导致主程序崩溃


# ==================== 重定向 stdout/stderr ====================
class StreamToLogger:
    def __init__(self, is_error=False):
        self.is_error = is_error
        self.line_buffer = ""

    def write(self, buf):
        if not buf:
            return
        self.line_buffer += buf
        while "\\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\\n", 1)
            if line.strip():
                write_log_message(line, is_raw=True)
        # 注意：非完整行暂不写入，等 flush 或下一行

    def flush(self):
        if self.line_buffer.strip():
            write_log_message(self.line_buffer.rstrip(), is_raw=True)
            self.line_buffer = ""

    def isatty(self):
        return False


# ==================== 自定义 logger 代理 ====================
class SimpleLogger:
    def __init__(self, node_id):
        self.node_id = node_id

    def info(self, message):
        write_log_message(str(message), level="INFO", is_raw=False)

    def error(self, message):
        write_log_message(str(message), level="ERROR", is_raw=False)

    def success(self, message):
        write_log_message(str(message), level="SUCCESS", is_raw=False)
        
    def debug(self, message):
        write_log_message(str(message), level="DEBUG", is_raw=False)

    def warning(self, message):
        write_log_message(str(message), level="WARNING", is_raw=False)

# ==================== 主执行逻辑 ====================
if __name__ == "__main__":
    CLASS_NAME = "{class_name}"
    FILE_PATH = r"{file_path}"
    RESULT_PATH = r"{result_path}"
    ERROR_PATH = r"{error_path}"
    PARAMS_PATH = r"{params_path}"

    # 重定向标准流
    sys.stdout = StreamToLogger(is_error=False)
    sys.stderr = StreamToLogger(is_error=True)

    # 创建组件可用的 logger（不使用 loguru！）
    node_logger = SimpleLogger(NODE_ID)

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

        # === 加载参数 ===
        with open(PARAMS_PATH, 'rb') as f:
            loaded = pickle.load(f)
            if not isinstance(loaded, (tuple, list)) or len(loaded) != 3:
                raise ValueError("参数文件格式错误：应为 (params, inputs, global_vars) 三元组")
            params, inputs, global_variables = loaded

        node_logger.info("从参数文件加载配置执行")

        # === 执行组件 ===
        comp_instance = comp_class()
        comp_instance.logger = node_logger  # 注入自定义 logger
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
        sys.stderr.write(f"EXECUTION_IMPORT_ERROR: {{e}}\\n")

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
        sys.stderr.write(f"EXECUTION_ERROR: {{e}}\\n")

    finally:
        # 确保缓冲区 flush
        sys.stdout.flush()
        sys.stderr.flush()
'''
