# === 执行脚本模板（模块级常量，避免重复拼接）===
_EXECUTION_SCRIPT_TEMPLATE = '''# -*- coding: utf-8 -*-
import sys
import os
import pickle
import importlib.util
import traceback
from pathlib import Path
from loguru import logger

# ==================== 配置 ====================
# 禁用默认 stderr handler，避免日志重复
logger.remove()

# ==================== 工具函数 ====================

def _is_safe_path(base_path: Path, path: Path) -> bool:
    """防止路径遍历攻击"""
    try:
        path.resolve().relative_to(base_path.resolve())
        return True
    except ValueError:
        return False

def _validate_execution_paths(
    file_path: str,
    params_path: str,
    log_file_path: str,
    result_path: str,
    error_path: str
):
    """校验所有路径是否在安全目录下（可选）"""
    # 示例：限制在当前工作目录下
    base = Path.cwd().resolve()
    for p in [file_path, params_path, log_file_path, result_path, error_path]:
        if not _is_safe_path(base, Path(p)):
            raise PermissionError(f"路径超出允许范围: {{p}}")

# ==================== 主执行逻辑 ====================

if __name__ == "__main__":
    # 从环境变量或命令行传入（更安全，避免脚本模板硬编码）
    # 此处保留模板占位符，实际使用时由外部替换
    CLASS_NAME = "{class_name}"
    FILE_PATH = r"{file_path}"
    PARAMS_PATH = r"{params_path}"
    LOG_FILE_PATH = r"{log_file_path}"
    RESULT_PATH = r"{result_path}"
    ERROR_PATH = r"{error_path}"
    NODE_ID = "{node_id}"

    # 可选：路径安全检查（根据你的部署环境决定是否启用）
    # _validate_execution_paths(FILE_PATH, PARAMS_PATH, LOG_FILE_PATH, RESULT_PATH, ERROR_PATH)

    # 配置日志：直接写入文件，按 node_id 过滤
    log_handler_id = logger.add(
        LOG_FILE_PATH,
        level="DEBUG",
        format="[{{time:YYYY-MM-DD HH:mm:ss}}] {{function}}-{{line}} {{level}}: {{message}}",
        encoding='utf-8',
        filter=lambda record: record["extra"].get("node_id") == NODE_ID,
        enqueue=True,  # 异步写入，避免阻塞
        rotation="10 MB",  # 防止单文件过大
        retention=3  # 保留3个历史日志
    )

    # 绑定 node_id 到 logger
    node_logger = logger.bind(node_id=NODE_ID)

    try:
        # 1. 加载组件类
        spec = importlib.util.spec_from_file_location(CLASS_NAME, FILE_PATH)
        if spec is None:
            raise ImportError(f"无法加载模块: {{FILE_PATH}}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        comp_class = getattr(module, CLASS_NAME, None)
        if comp_class is None:
            raise AttributeError(f"模块中未找到类: {{CLASS_NAME}}")

        # 2. 加载参数
        with open(PARAMS_PATH, 'rb') as f:
            loaded = pickle.load(f)
            if not isinstance(loaded, (tuple, list)) or len(loaded) != 3:
                raise ValueError("参数文件格式错误：应为 (params, inputs, global_vars) 三元组")
            params, inputs, global_variables = loaded

        # 3. 实例化并执行
        comp_instance = comp_class()
        comp_instance.logger = node_logger  # 注入带 node_id 的 logger

        node_logger.info("开始执行组件")
        output = comp_instance.execute(params, inputs, global_variables, NODE_ID)

        # 4. 保存结果
        with open(RESULT_PATH, 'wb') as f:
            pickle.dump(output, f)

        node_logger.success("节点执行完成")
        sys.exit(0)

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
        sys.exit(1)

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
        sys.exit(1)

    finally:
        # 清理 logger handler，防止文件句柄泄漏
        if 'log_handler_id' in locals():
            logger.remove(log_handler_id)
'''
