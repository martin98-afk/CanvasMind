# -*- coding: utf-8 -*-
import os
import pickle
import subprocess
import sys
import tempfile
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
        python_executable: str = None,
        log_file_path: str = None,
        timeout: int = 300,
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
    if python_executable is None:
        python_executable = sys.executable

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
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        temp_script_path = f.name
        log_file_path = log_file_path or f"{temp_script_path}.log"
        script_content = _generate_execution_script(
            comp_class=comp_class,
            file_path=file_path,
            temp_script_path=temp_script_path,
            log_file_path=log_file_path
        )
        f.write(script_content)

    try:
        # 保存参数
        with open(f"{temp_script_path}.params", 'wb') as f:
            pickle.dump((params, inputs, global_variable), f)

        # 第一次执行
        result = _run_subprocess(python_executable, temp_script_path, timeout)
        # 检查是否需要安装依赖
        needs_install = _check_needs_install(result, temp_script_path)

        if needs_install and requirements_str.strip():
            _install_requirements(python_executable, requirements_str)
            # 重新执行
            result = _run_subprocess(python_executable, temp_script_path, timeout, logger)
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
        if os.path.exists(f"{temp_script_path}.result"):
            with open(f"{temp_script_path}.result", 'rb') as f:
                return pickle.load(f)
        elif os.path.exists(f"{temp_script_path}.error"):
            with open(f"{temp_script_path}.error", 'rb') as f:
                error_info = pickle.load(f)
                logger.error(f"组件执行失败: {error_info['error']}\n{error_info['traceback']}")
            raise RuntimeError(f"组件执行失败: {error_info['error']}\n{error_info['traceback']}")
        else:
            logger.error(f"执行异常: {result.stderr}")
            raise RuntimeError(f"执行异常: {result.stderr}")

    finally:
        # 清理临时文件
        for ext in ['', '.params', '.result', '.error', '.log']:
            path = f"{temp_script_path}{ext}"
            if os.path.exists(path):
                os.remove(path)


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
    CLASS_NAME = "{comp_class.__name__}"
    FILE_PATH = r"{file_path}"
    PARAMS_PATH = r"{temp_script_path}.params"
    LOG_FILE_PATH = r"{log_file_path}"
    RESULT_PATH = r"{temp_script_path}.result"
    ERROR_PATH = r"{temp_script_path}.error"
    NODE_ID = "{str(uuid.uuid4())}"
    file_path = Path(FILE_PATH)
    original_cwd = os.getcwd()
    os.chdir(file_path.parent.parent.parent)  # 切到组件所在目录
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
            logger.remove(log_handler_id)'''


def _run_subprocess(python_executable, script_path, timeout):
    result = subprocess.run(
        [python_executable, script_path],
        capture_output=True, text=True, timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
        encoding='utf-8'
    )
    # 调试时可打印子进程日志
    if result.stdout.strip():
        logger.debug("子进程 stdout:\n{}", result.stdout)
    if result.stderr.strip():
        logger.warning("子进程 stderr:\n{}", result.stderr)
    return result


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