_EXECUTION_SCRIPT_TEMPLATE = '''# -*- coding: utf-8 -*-
import sys
import os
import gc 
import pickle
import importlib.util
import traceback
import warnings
import types
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

    # 控制参数：是否驻留内存 (True/False)
    IS_MEMORY_RESIDENT = {is_memory_resident}

    UNIQUE_MODULE_KEY = f"dynamic_mod_{{NODE_ID}}"
    UNIQUE_CLASS_NAME = f"{{BASE_CLASS_NAME}}_{{NODE_ID}}"
    UNIQUE_INSTANCE_NAME = f"INSTANCE_{{NODE_ID}}" # 实例的唯一标识
    DATA_CONTAINER_NAME = f"DATA_{{NODE_ID}}" # 独立数据容器的名称

    # 1. 配置日志
    logger.remove()
    logger.add(LOG_FILE_PATH, format=sink_formatter, level="INFO", encoding='utf-8', enqueue=True,
               filter=lambda record: record["extra"].get("node_id") == NODE_ID)
    node_logger = logger.bind(node_id=NODE_ID)
    raw_logger = logger.bind(node_id=NODE_ID, raw=True)
    sys.stdout = StreamToLogger(raw_logger.info)
    sys.stderr = StreamToLogger(raw_logger.error)

    module = None
    comp_instance = None

    try:
        # 2. 工作目录和当前路径设置
        node_output_dir = Path(WORKFLOW_PATH) / "workspace" / NODE_ID
        node_output_dir.mkdir(parents=True, exist_ok=True)
        sys.path.insert(0, str(node_output_dir))
        os.chdir(str(node_output_dir))

        # ==================== 智能加载与实例化逻辑 ====================

        # 1. 尝试获取现有模块
        module = sys.modules.get(UNIQUE_MODULE_KEY)

        need_reload = True

        if module and hasattr(module, BASE_CLASS_NAME) and IS_MEMORY_RESIDENT:
            need_reload = False
            node_logger.info("内存驻留生效：复用现有模块代码")

        # 2. 如果需要加载/重载代码
        if need_reload:
            node_logger.debug(f"准备加载/重载模块代码: {{UNIQUE_MODULE_KEY}}")

            preserved_data_container = None
            if module and hasattr(module, DATA_CONTAINER_NAME):
                preserved_data_container = getattr(module, DATA_CONTAINER_NAME)
                node_logger.debug("缓存了旧的独立数据容器")

            spec = importlib.util.spec_from_file_location(UNIQUE_MODULE_KEY, FILE_PATH)
            module = importlib.util.module_from_spec(spec)
            sys.modules[UNIQUE_MODULE_KEY] = module 

            if preserved_data_container:
                setattr(module, DATA_CONTAINER_NAME, preserved_data_container)
                node_logger.debug("已恢复独立数据容器")

            spec.loader.exec_module(module)
            node_logger.debug("模块代码执行完毕")

        # 3. 实例化逻辑
        original_class = getattr(module, BASE_CLASS_NAME)

        # 【双花括号修正】字典定义需要转义
        comp_class = type(UNIQUE_CLASS_NAME, (original_class,), {{"__module__": UNIQUE_MODULE_KEY}})

        if IS_MEMORY_RESIDENT:
            setattr(module, UNIQUE_CLASS_NAME, comp_class)

        if IS_MEMORY_RESIDENT and hasattr(module, UNIQUE_INSTANCE_NAME):
            comp_instance = getattr(module, UNIQUE_INSTANCE_NAME)
            node_logger.info("复用已驻留的组件实例")
        else:
            comp_instance = comp_class()
            if IS_MEMORY_RESIDENT:
                setattr(module, UNIQUE_INSTANCE_NAME, comp_instance)
                node_logger.info("创建了新的组件实例并驻留")
            else:
                node_logger.debug("创建了临时组件实例 (非驻留模式)")

        comp_instance.logger = node_logger

        # ==================== 执行组件方法 ====================
        with open(PARAMS_PATH, 'rb') as f:
            params, inputs, global_variables = pickle.load(f)

        node_logger.info("开始执行组件方法 execute")
        output = comp_instance.execute(params, inputs, global_variables, NODE_ID, WORKFLOW_PATH)

        with open(RESULT_PATH, 'wb') as f:
            pickle.dump(output, f)
        node_logger.success("节点执行成功")

    except Exception as e:
        tb = traceback.format_exc()
        # 【双花括号修正】字典定义需要转义
        with open(ERROR_PATH, 'wb') as f:
            pickle.dump({{"error": str(e), "traceback": tb, "node_id": NODE_ID}}, f)
        # 【双花括号修正】f-string中的变量需要转义
        node_logger.error(f"执行异常: {{e}}")

    finally:
        # ==================== 内存防溢出清理 ====================
        if not IS_MEMORY_RESIDENT and module:
            node_logger.debug("非驻留模式：执行内存清理")

            if hasattr(module, UNIQUE_INSTANCE_NAME):
                delattr(module, UNIQUE_INSTANCE_NAME)
                # 【双花括号修正】f-string中的变量需要转义
                node_logger.debug(f"已移除实例引用: {{UNIQUE_INSTANCE_NAME}}")

            if hasattr(module, UNIQUE_CLASS_NAME):
                delattr(module, UNIQUE_CLASS_NAME)
                # 【双花括号修正】f-string中的变量需要转义
                node_logger.debug(f"已移除类名引用: {{UNIQUE_CLASS_NAME}}")

            if hasattr(module, BASE_CLASS_NAME):
                delattr(module, BASE_CLASS_NAME)
                # 【双花括号修正】f-string中的变量需要转义
                node_logger.debug(f"已移除基类名引用: {{BASE_CLASS_NAME}}")

            has_data_container = hasattr(module, DATA_CONTAINER_NAME)

            if not has_data_container:
                if UNIQUE_MODULE_KEY in sys.modules:
                    del sys.modules[UNIQUE_MODULE_KEY]
                    # 【双花括号修正】f-string中的变量需要转义
                    node_logger.debug(f"模块 {{UNIQUE_MODULE_KEY}} 无数据残留，已从 sys.modules 移除")
            else:
                # 【双花括号修正】f-string中的变量需要转义
                node_logger.debug(f"模块 {{UNIQUE_MODULE_KEY}} 中保留独立数据容器.")
                pass

            comp_instance = None
            gc.collect()

        sys.stdout.flush()
        sys.stderr.flush()

if __name__ == "__main__":
    run_node()
'''