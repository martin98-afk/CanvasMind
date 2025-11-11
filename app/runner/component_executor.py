# -*- coding: utf-8 -*-
import importlib
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import traceback
import uuid
from pathlib import Path

from loguru import logger
from wcwidth import wcswidth


def run_component_in_subprocess(
        comp_class,
        file_path: str,
        params: dict,
        inputs: dict,
        global_variable: dict = None,
        log_file_path: str = None,
        logger: logger = logger
):
    """
    在独立子进程中执行组件（无 GUI 依赖）

    :param comp_class: 组件类（用于获取 requirements, inputs, outputs）
    :param file_path: 组件源码文件路径
    :param params: 组件属性参数
    :param inputs: 输入数据字典
    :param python_executable: Python 解释器路径
    :param log_file_path: 日志文件路径（可选）
    :param timeout: 超时时间（秒）
    :return: 组件输出字典
    """
    dir_path = Path(__file__).parent.parent
    sys.path.append(str(dir_path))

    # 获取 requirements
    requirements_str = getattr(comp_class, 'requirements', '')
    if not requirements_str:
        try:
            source_code = Path(file_path).read_text(encoding='utf-8')
            for line in source_code.split('\n'):
                if line.strip().startswith('requirements ='):
                    req_line = line.split('=', 1)[1].strip().strip('"\'')
                    requirements_str = req_line
                    break
        except Exception as e:
            logger.warning(f"无法解析 requirements: {e}")

    # 创建临时脚本
    temp_script_path = dir_path / "run"
    shutil.rmtree(temp_script_path, ignore_errors=True)
    temp_script_path.mkdir(parents=True, exist_ok=True)
    log_file_path = log_file_path or temp_script_path / "run.log"

    CLASS_NAME = comp_class.__name__
    FILE_PATH = file_path
    ERROR_PATH = temp_script_path / 'run.error'
    NODE_ID = str(uuid.uuid4())
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

        # === 3. 执行组件 ===
        comp_instance = comp_class()
        comp_instance.logger = logger
        logger.info("开始执行组件")
        output = comp_instance.execute(params, inputs, global_variable, NODE_ID)

        logger.success("节点执行完成")
    except ImportError as e:
        error_info = {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": "ImportError",
            "node_id": NODE_ID
        }
        with open(ERROR_PATH, 'wb') as f:
            pickle.dump(error_info, f)
        logger.error(f"导入错误: {e}")
        print(f"EXECUTION_IMPORT_ERROR: {e}", flush=True)

    except Exception as e:
        error_info = {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": type(e).__name__,
            "node_id": NODE_ID
        }
        with open(ERROR_PATH, 'wb') as f:
            pickle.dump(error_info, f)
        logger.error(f"执行异常: {e}")
        print(f"EXECUTION_ERROR: {e}", flush=True)

    # 打印节点日志
    if os.path.exists(log_file_path):
        with open(log_file_path, 'r', encoding='utf-8') as f:
            inner_lines = f.read().splitlines()

        node_name = comp_class.name
        title = f"节点 {node_name} 日志"

        # 计算每行的显示宽度（含中文）
        content_widths = [wcswidth(line) for line in inner_lines]
        title_width = wcswidth(title)
        max_content_width = max(content_widths + [title_width, 0])

        # 总宽度 = 内容最大宽 + 左右空格(2) + 两边 | (2) → 共 +4
        total_width = max_content_width + 4
        total_width = max(total_width, 60)  # 最小宽度保障

        raw_logger = logger.opt(raw=True)

        # 顶部边框（纯等号，宽度 = total_width）
        raw_logger.info("=" * total_width + "\n")

        # 标题行：左对齐，右侧补齐空格到 total_width - 2（因为有 "| " 和 " |"）
        title_padded = f"| {title}"
        title_display = wcswidth(title_padded)
        needed_spaces = total_width - 2 - title_display  # -2 是末尾的 " |"
        title_line = title_padded + " " * needed_spaces + "|\n"
        raw_logger.info(title_line)

        # 内容行
        for line in inner_lines:
            line_padded = f"| {line}"
            line_display = wcswidth(line_padded)
            needed_spaces = total_width - 2 - line_display
            content_line = line_padded + " " * needed_spaces + "|\n"
            raw_logger.info(content_line)

        # 底部边框
        raw_logger.info("=" * total_width + "\n")

    # 处理结果
    return output


def _generate_execution_script(comp_class, file_path, temp_script_path, log_file_path):
    return f'''# -*- coding: utf-8 -*-
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
    CLASS_NAME = "{comp_class.__name__}"
    FILE_PATH = r"{str(file_path)}"
    PARAMS_PATH = r"{str(temp_script_path / 'run.params')}"  
    LOG_FILE_PATH = r"{str(log_file_path)}"
    RESULT_PATH = r"{str(temp_script_path / 'run.result')}"
    ERROR_PATH = r"{str(temp_script_path / 'run.error')}"
    NODE_ID = "{str(uuid.uuid4())}"
    try:
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
        logger.remove(log_handler_id)'''


def _check_needs_install(result, temp_script_path):
    if result.returncode == 0:
        return False
    if os.path.exists(f"{temp_script_path}.error"):
        with open(f"{temp_script_path}.error", 'rb') as f:
            error_info = pickle.load(f)
        return error_info.get("type") == "ImportError"
    return "ImportError" in result.stderr


def _install_requirements(python_executable, requirements_str):
    packages = [pkg.strip() for pkg in requirements_str.split(',') if pkg.strip()]
    for pkg in packages:
        logger.info(f"安装依赖: {pkg}")
        subprocess.run(
            [python_executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=True
        )