# -*- coding: utf-8 -*-
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

from loguru import logger


def run_component_in_subprocess(
        comp_class,
        file_path: str,
        params: dict,
        inputs: dict,
        python_executable: str = None,
        log_file_path: str = None,
        timeout: int = 300
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
        script_content = _generate_execution_script(
            comp_class=comp_class,
            file_path=file_path,
            temp_script_path=temp_script_path,
            log_file_path=log_file_path or f"{temp_script_path}.log"
        )
        f.write(script_content)

    try:
        # 保存参数
        with open(f"{temp_script_path}.params", 'wb') as f:
            pickle.dump((params, inputs), f)

        # 第一次执行
        result = _run_subprocess(python_executable, temp_script_path, timeout)
        # 检查是否需要安装依赖
        needs_install = _check_needs_install(result, temp_script_path)

        if needs_install and requirements_str.strip():
            _install_requirements(python_executable, requirements_str)
            # 重新执行
            result = _run_subprocess(python_executable, temp_script_path, timeout)

        # 处理结果
        if os.path.exists(f"{temp_script_path}.result"):
            with open(f"{temp_script_path}.result", 'rb') as f:
                return pickle.load(f)
        elif os.path.exists(f"{temp_script_path}.error"):
            with open(f"{temp_script_path}.error", 'rb') as f:
                error_info = pickle.load(f)
            raise RuntimeError(f"组件执行失败: {error_info['error']}\n{error_info['traceback']}")
        else:
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
import json
import importlib.util
import traceback
from datetime import datetime
from loguru import logger
import subprocess
import re
import warnings
warnings.filterwarnings("ignore")


class FileLogHandler:
    def __init__(self, log_file_path, node_id="runner"):
        self.log_file_path = log_file_path
        self.logger = logger.bind(node_id=node_id)
        self.handler_id = logger.add(self._file_sink, level="INFO", enqueue=True)

    def _file_sink(self, message):
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(str(message) + '\\n')

    def info(self, msg): self.logger.info(msg)
    def success(self, msg): self.logger.success(msg)
    def error(self, msg): self.logger.error(msg)

try:
    spec = importlib.util.spec_from_file_location("{comp_class.__name__}", r"{file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    comp_class = getattr(module, "{comp_class.__name__}")

    with open(r"{temp_script_path}.params", 'rb') as f:
        params, inputs = pickle.load(f)

    comp_instance = comp_class()
    comp_instance.logger = FileLogHandler(r"{log_file_path}")

    if {len(getattr(comp_class, 'inputs', []))} > 0:
        output = comp_instance.execute(params, inputs)
    else:
        output = comp_instance.execute(params)

    comp_instance.logger.success("执行完成")
    with open(r"{temp_script_path}.result", 'wb') as f:
        pickle.dump(output, f)
    sys.exit(0)

except ImportError as e:
    error_info = {{"error": str(e), "traceback": traceback.format_exc(), "type": "ImportError"}}
    with open(r"{temp_script_path}.error", 'wb') as f:
        pickle.dump(error_info, f)
    print(f"EXECUTION_IMPORT_ERROR: {{e}}", flush=True)
    sys.exit(1)

except Exception as e:
    error_info = {{"error": str(e), "traceback": traceback.format_exc(), "type": "Other"}}
    with open(r"{temp_script_path}.error", 'wb') as f:
        pickle.dump(error_info, f)
    print(f"EXECUTION_ERROR: {{e}}", flush=True)
    sys.exit(1)
'''


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