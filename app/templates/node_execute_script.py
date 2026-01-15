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
    def __init__(self, log_func):
        self.log_func = log_func
        self.line_buffer = ""
    def write(self, buf):
        if not buf: return
        self.line_buffer += buf
        while "\\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\\n", 1)
            self.log_func(line)
    def flush(self):
        if self.line_buffer:
            self.log_func(self.line_buffer)
            self.line_buffer = ""

def sink_formatter(record):
    if record["extra"].get("raw") is True: return "{{message}}\\n"
    return "[{{time:YYYY-MM-DD HH:mm:ss}}] {{function}}-{{line}} {{level}}: {{message}}\\n"

# ==================== 主执行逻辑 ====================
def run_node():
    # --- 参数填充 ---
    BASE_CLASS_NAME = "{class_name}"
    FILE_PATH = r"{file_path}"
    LOG_FILE_PATH = r"{log_file_path}"
    RESULT_PATH = r"{result_path}"
    ERROR_PATH = r"{error_path}"
    NODE_ID = "{node_id}"
    WORKFLOW_PATH = r"{workflow_path}"
    PARAMS_PATH = r"{params_path}"
    
    UNIQUE_MODULE_KEY = f"dynamic_mod_{{NODE_ID}}"
    UNIQUE_CLASS_NAME = f"{{BASE_CLASS_NAME}}_{{NODE_ID}}"
    UNIQUE_INSTANCE_NAME = f"INSTANCE_{{NODE_ID}}" # 实例的唯一标识

    # 1. 配置日志
    logger.remove()
    logger.add(LOG_FILE_PATH, format=sink_formatter, level="DEBUG", encoding='utf-8', enqueue=True,
               filter=lambda record: record["extra"].get("node_id") == NODE_ID)
    node_logger = logger.bind(node_id=NODE_ID)
    raw_logger = logger.bind(node_id=NODE_ID, raw=True)
    sys.stdout = StreamToLogger(raw_logger.info)
    sys.stderr = StreamToLogger(raw_logger.error)

    try:
        # 2. 内存复用逻辑（类与实例）
        comp_instance = None
        module = sys.modules.get(UNIQUE_MODULE_KEY)

        if module:
            # 尝试获取已经存在的实例
            comp_instance = getattr(module, UNIQUE_INSTANCE_NAME, None)
            if comp_instance:
                node_logger.info(f"检测到内存驻留实例，直接复用: {{UNIQUE_INSTANCE_NAME}}")

        if comp_instance is None:
            # 如果实例不存在，则需要加载/重新加载
            node_logger.info(f"内存中未找到实例，正在初始化...")
            
            if not module:
                spec = importlib.util.spec_from_file_location(UNIQUE_MODULE_KEY, FILE_PATH)
                module = importlib.util.module_from_spec(spec)
                sys.modules[UNIQUE_MODULE_KEY] = module
                spec.loader.exec_module(module)
            
            original_class = getattr(module, BASE_CLASS_NAME)
            # 创建带后缀的类
            comp_class = type(UNIQUE_CLASS_NAME, (original_class,), {{"__module__": UNIQUE_MODULE_KEY}})
            setattr(module, UNIQUE_CLASS_NAME, comp_class)
            
            # 【关键】实例化并存入模块，实现真正驻留
            comp_instance = comp_class()
            setattr(module, UNIQUE_INSTANCE_NAME, comp_instance)
            node_logger.info(f"新实例已创建并存入内存")

        # 3. 每次执行前更新必要的上下文信息
        comp_instance.logger = node_logger # 确保日志对象是最新的文件句柄

        # 4. 执行
        with open(PARAMS_PATH, 'rb') as f:
            params, inputs, global_variables = pickle.load(f)

        node_logger.info("开始执行组件方法")
        output = comp_instance.execute(params, inputs, global_variables, NODE_ID, WORKFLOW_PATH)

        with open(RESULT_PATH, 'wb') as f:
            pickle.dump(output, f)
        node_logger.success("节点执行成功")

    except Exception as e:
        tb = traceback.format_exc()
        with open(ERROR_PATH, 'wb') as f:
            pickle.dump({{"error": str(e), "traceback": tb, "node_id": NODE_ID}}, f)
        node_logger.error(f"执行异常: {{e}}")
    finally:
        sys.stdout.flush()
        sys.stderr.flush()

if __name__ == "__main__":
    run_node()
'''