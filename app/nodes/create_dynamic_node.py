# -*- coding: utf-8 -*-
import inspect
import os
import pickle
import re
import subprocess
import sys
import tempfile

from NodeGraphQt import BaseNode
from PyQt5.QtWidgets import QFileDialog
from loguru import logger

from app.components.base import ArgumentType
from app.utils.node_logger import NodeLogHandler
from app.widgets.component_log_message_box import LogMessageBox


def create_node_class(component_class, full_path, file_path):
    """直接返回一个完整的节点类，支持文件上传按钮和独立Python环境执行"""

    class DynamicNode(BaseNode):
        __identifier__ = 'dynamic'
        NODE_NAME = component_class.name
        FULL_PATH = full_path
        FILE_PATH = file_path

        def __init__(self):
            super().__init__()
            self.component_class = component_class
            self._node_logs = ""  # 节点独立日志存储
            self._output_values = {}  # 存储输出端口值
            self._input_values = {}
            self.column_select = {}
            # 执行（捕获stdout/stderr）
            self.log_capture = NodeLogHandler(self.id, self._log_message)

            # 添加属性
            for prop_name, prop_def in component_class.get_properties().items():
                prop_type = prop_def.get("type", "text")
                default = prop_def.get("default", "")
                label = prop_def.get("label", prop_name)

                if prop_type == "bool":
                    self.add_checkbox(prop_name, text=label, state=default)

                elif prop_type == "int":
                    self.add_text_input(prop_name, label, text=str(default))

                elif prop_type == "float":
                    self.add_text_input(prop_name, label, text=str(default))

                elif prop_type == "choice":
                    choices = prop_def.get("choices", [])
                    if choices:
                        self.add_combo_menu(prop_name, label, items=choices)
                        if default in choices:
                            self.set_property(prop_name, default)
                        else:
                            self.set_property(prop_name, choices[0])
                    else:
                        self.add_text_input(prop_name, label, text=str(default))
                else:
                    # 默认文本输入
                    self.add_text_input(prop_name, label, text=str(default))

            # 添加输入端口
            for port_name, label in component_class.get_inputs():
                self.add_input(port_name)

            # 添加输出端口
            for port_name, label in component_class.get_outputs():
                self.add_output(port_name)

        def _select_file(self, prop_name):
            """选择文件"""
            current_path = self.get_property(prop_name)
            directory = os.path.dirname(current_path) if current_path else ""

            file_filter = self.model.properties.get(f"{prop_name}_file_filter", "All Files (*)")
            path, _ = QFileDialog.getOpenFileName(
                None, "选择文件", directory, file_filter
            )
            if path:
                self.set_property(prop_name, path)

        def _select_folder(self, prop_name):
            """选择文件夹"""
            current_path = self.get_property(prop_name)
            directory = current_path if current_path and os.path.isdir(current_path) else ""

            path = QFileDialog.getExistingDirectory(
                None, "选择文件夹", directory
            )
            if path:
                self.set_property(prop_name, path)

        def _select_csv(self, prop_name):
            """选择CSV文件"""
            current_path = self.get_property(prop_name)
            directory = os.path.dirname(current_path) if current_path else ""

            path, _ = QFileDialog.getOpenFileName(
                None, "选择CSV文件", directory, "CSV Files (*.csv)"
            )
            if path:
                self.set_property(prop_name, path)

        def set_property(self, name, value, push_undo=True):
            """重写 set_property 以支持特殊属性"""
            if name.endswith('_file_filter'):
                self.model.properties[name] = value
                return
            super().set_property(name, value, push_undo)

        def _log_message(self, node_id, message):
            """记录节点日志"""
            if isinstance(message, str) and message.strip():
                if not message.endswith('\n'):
                    message += '\n'
                self._node_logs += message

        def get_logs(self):
            """获取节点日志"""
            return self._node_logs if self._node_logs else "无日志可用。"

        def show_logs(self):
            """显示节点日志"""
            log_content = self.get_logs()
            w = LogMessageBox(log_content, self.view.viewer())
            w.exec()

        def set_output_value(self, port_name, value):
            """设置输出端口的值"""
            self._output_values[port_name] = value

        def clear_output_value(self):
            """清除输出端口的值"""
            self._output_values = {}

        def get_output_value(self, port_name):
            """获取输出端口的值"""
            return self._output_values.get(port_name)

        def on_run_complete(self, output):
            """节点运行完成后自动映射结果到输出端口"""
            self._output_values = output

        def execute_in_separate_env(self, comp_obj, python_executable=None):
            """
            在独立Python环境中执行组件
            python_executable: 目标Python解释器路径，如果为None则使用当前环境
            """
            if python_executable is None:
                python_executable = sys.executable

            # 创建文件日志处理器
            file_log_handler = NodeLogHandler(self.id, self._log_message, use_file_logging=True)

            try:
                # 准备执行参数
                params = {}
                component_properties = comp_obj.get_properties()
                for prop_name, prop_def in component_properties.items():
                    default_value = prop_def.get("default", "")
                    if self.has_property(prop_name):
                        params[prop_name] = self.get_property(prop_name)
                    else:
                        params[prop_name] = default_value

                # 获取输入数据
                inputs = {}
                for input_port in self.input_ports():
                    port_name = input_port.name()
                    connected = input_port.connected_ports()
                    if not connected:
                        continue
                    upstream_out = connected[0]
                    upstream_node = upstream_out.node()
                    inputs[port_name] = upstream_node._output_values.get(upstream_out.name())
                    if port_name in self.column_select:
                        inputs[f"{port_name}_column_select"] = self.column_select.get(port_name)

                # 获取日志文件路径
                log_file_path = file_log_handler.get_log_file_path()

                # --- 新增：尝试从组件源码获取 requirements ---
                requirements_str = getattr(comp_obj, 'requirements', '')  # 从类属性获取
                if not requirements_str:
                    try:
                        # 如果类属性没有，尝试从源码解析
                        source_code = inspect.getsource(comp_obj)
                        # 解析 requirements = "..." 行
                        lines = source_code.split('\n')
                        for line in lines:
                            if line.strip().startswith('requirements ='):
                                req_line = line.split('=', 1)[1].strip().strip('"\'')  # 去掉赋值号、引号和空格
                                requirements_str = req_line
                                break
                    except Exception as e:
                        print(f"警告：无法从组件代码解析 requirements: {e}")
                        requirements_str = ""  # 如果解析失败，设为空字符串

                # 创建临时脚本文件 - 使用UTF-8编码
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False,
                                                 encoding='utf-8') as temp_script:
                    temp_script_path = temp_script.name

                    # 生成执行脚本 - 添加UTF-8编码声明
                    # --- 修改：脚本不再预先安装，而是先尝试执行，捕获 ImportError 后再安装 ---
                    script_content = f'''# -*- coding: utf-8 -*-
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

# 文件日志处理器
class FileLogHandler:
    def __init__(self, log_file_path, node_id):
        self.log_file_path = log_file_path
        self.node_id = node_id
        self.logger = logger.bind(node_id=self.node_id)

        # 添加文件处理器
        self.handler_id = logger.add(
            self._file_sink,
            level="INFO",
            enqueue=True,
            filter=lambda record: "node_id" in record["extra"]
        )

    def _file_sink(self, message):
        record = message.record
        if record["extra"].get("node_id") != self.node_id:
            return  # 忽略其他节点的日志
        timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        function = record["function"]
        line = record["line"]
        level = record["level"].name
        msg = record["message"]

        formatted_msg = f"[{{timestamp}}] {{function}}-{{line}} {{level}}: {{msg}}\\n"

        # 将日志写入文件
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(formatted_msg)

    def info(self, msg):
        self.logger.info(msg)

    def success(self, msg):
        self.logger.success(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def debug(self, msg):
        self.logger.debug(msg)

# --- 尝试导入组件并执行 ---
try:
    # 从文件路径导入组件类
    spec = importlib.util.spec_from_file_location("{comp_obj.__name__}", r"{self.FILE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 获取组件类
    comp_class = getattr(module, "{comp_obj.__name__}")

    # 读取输入参数
    with open(r"{temp_script_path}.params", 'rb') as f:
        params, inputs = pickle.load(f)

    # 创建组件实例
    comp_instance = comp_class()

    # 创建文件日志处理器并赋值给组件实例
    comp_instance.logger = FileLogHandler(r"{log_file_path}", "{self.id}")

    # 执行组件
    if {len(comp_obj.get_inputs())} > 0:
        output = comp_instance.execute(params, inputs)
    else:
        output = comp_instance.execute(params)

    # 记录成功日志
    comp_instance.logger.success("节点执行完成")

    # 保存结果
    with open(r"{temp_script_path}.result", 'wb') as f:
        pickle.dump(output, f)

    sys.exit(0) # 成功退出

except ImportError as e:
    # 捕获导入错误
    error_msg = str(e)
    print(f"EXECUTION_IMPORT_ERROR: {{error_msg}}", flush=True) # 使用特定前缀标记 ImportError
    # 保存错误信息，包含特定标记，以便主进程识别
    error_info = {{
        "error": str(e),
        "traceback": traceback.format_exc(),
        "type": "ImportError" # 添加错误类型标记
    }}
    with open(r"{temp_script_path}.error", 'wb') as f:
        pickle.dump(error_info, f)

    # 记录错误日志
    if 'comp_instance' in locals() and hasattr(comp_instance, 'logger'):
        comp_instance.logger.error(f"执行失败 (ImportError): {{e}}")
    else:
        temp_logger = FileLogHandler(r"{log_file_path}", "{self.id}")
        temp_logger.error(f"执行失败 (ImportError): {{e}}")
    sys.exit(1) # 失败退出

except Exception as e:
    # 捕获其他错误
    error_info = {{
        "error": str(e),
        "traceback": traceback.format_exc(),
        "type": "Other" # 添加错误类型标记
    }}
    with open(r"{temp_script_path}.error", 'wb') as f:
        pickle.dump(error_info, f)

    # 记录错误日志
    if 'comp_instance' in locals() and hasattr(comp_instance, 'logger'):
        comp_instance.logger.error(f"执行失败 (Other): {{e}}")
    else:
        temp_logger = FileLogHandler(r"{log_file_path}", "{self.id}")
        temp_logger.error(f"执行失败 (Other): {{e}}")
    print(f"EXECUTION_ERROR: {{e}}", flush=True) # 使用通用前缀标记其他错误
    sys.exit(1) # 失败退出
            '''
                    temp_script.write(script_content)

                try:
                    # 保存参数到临时文件
                    with open(f"{temp_script_path}.params", 'wb') as f:
                        pickle.dump((params, inputs), f)

                    # --- 修改：执行子进程，并根据结果判断是否需要安装 ---
                    result = subprocess.run(
                        [python_executable, temp_script_path],
                        capture_output=True, text=True, timeout=300,  # 5分钟超时
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        encoding='utf-8'  # 或 'utf-8-sig'
                    )

                    # 读取日志文件内容并添加到节点日志
                    log_content = file_log_handler.read_log_file()
                    if log_content.strip():
                        self._log_message(self.id, log_content)

                    # --- 检查是否是 ImportError 导致的失败 ---
                    needs_install = False
                    if result.returncode != 0:
                        # 检查是否有 .error 文件
                        error_file_path = f"{temp_script_path}.error"
                        if os.path.exists(error_file_path):
                            with open(error_file_path, 'rb') as f:
                                error_info = pickle.load(f)
                            # 如果错误类型是 ImportError，则需要安装
                            if error_info.get("type") == "ImportError":
                                needs_install = True
                        else:
                            # 如果没有 .error 文件，但有 stderr，也可能是 ImportError 但未被捕获到文件
                            # 这种情况比较少见，但可以检查 stderr 内容
                            if "ImportError" in result.stderr:
                                needs_install = True

                    if needs_install:
                        logger.info("检测到 ImportError，开始根据 requirements 安装包...")
                        # --- 安装逻辑 ---
                        if requirements_str.strip():
                            logger.info(f"requirements: {requirements_str}")
                            packages = [pkg.strip() for pkg in requirements_str.split(',')]
                            packages = [pkg for pkg in packages if pkg]  # 过滤空字符串

                            for pkg in packages:
                                if pkg:  # 确保包名不为空
                                    try:
                                        logger.info(f"正在安装 {pkg} ...")
                                        install_result = subprocess.run(
                                            [python_executable, "-m", "pip", "install", pkg],
                                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
                                            check=True
                                        )
                                        logger.info(f"安装 {pkg} 成功。")
                                    except subprocess.CalledProcessError as e:
                                        logger.info(f"安装 {pkg} 失败: {e.stderr}")
                                        # 可以选择在此处 raise 或者记录错误继续安装下一个
                                        # 这里选择记录错误并继续
                                        logger.info(f"  -> 警告: 继续尝试安装其他包。")
                                        continue  # 继续安装下一个包
                        else:
                            logger.info("组件 requirements 为空，无法自动安装缺失的包。")

                        # 安装完成后，再次运行子进程
                        logger.info("安装完成，重新执行组件...")
                        result = subprocess.run(
                            [python_executable, temp_script_path],
                            capture_output=True, text=True, timeout=300,  # 5分钟超时
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            encoding='utf-8'  # 或 'utf-8-sig'
                        )

                        # 再次读取日志
                        log_content = file_log_handler.read_log_file()
                        if log_content.strip():
                            self._log_message(self.id, log_content)

                    # --- 处理最终执行结果 ---
                    if os.path.exists(f"{temp_script_path}.result"):
                        with open(f"{temp_script_path}.result", 'rb') as f:
                            output = pickle.load(f)

                        # 记录成功日志
                        component_class.logger.success("✅ 节点在独立环境执行完成")

                        # 检查是否有UPLOAD类型输出且结果为None的情况
                        for port in comp_obj.outputs:
                            if port.type == ArgumentType.UPLOAD:
                                continue
                            else:
                                self.set_output_value(port.name, output.get(port.name))

                        return output

                    elif os.path.exists(f"{temp_script_path}.error"):
                        with open(f"{temp_script_path}.error", 'rb') as f:
                            error_info = pickle.load(f)

                        error_msg = f"❌ 节点在独立环境执行失败: {error_info['error']}"
                        component_class.logger.error(error_msg)
                        logger.error(error_info['traceback'])  # 输出详细错误信息
                        raise Exception(error_info['error'])

                    else:
                        error_msg = f"❌ 节点执行异常: {result.stderr}"
                        component_class.logger.error(error_msg)
                        raise Exception(result.stderr)

                finally:
                    # 清理临时文件
                    for ext in ['', '.params', '.result', '.error']:
                        temp_file = f"{temp_script_path}{ext}"
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
            except Exception as e:
                raise e

        def execute_sync(self, comp_obj, use_separate_env=True, python_executable=None):
            """
            执行节点，支持在独立Python环境中运行
            use_separate_env: 是否使用独立环境
            python_executable: 目标Python解释器路径
            """
            if use_separate_env:
                return self.execute_in_separate_env(comp_obj, python_executable)
            else:
                # 保持原有的同步执行方式
                return self._execute_in_current_env(comp_obj)

        def _execute_in_current_env(self, comp_obj):
            """在当前环境中执行（原有逻辑）"""
            try:
                # 获取组件类
                comp_instance = comp_obj()
                comp_instance.logger = self.log_capture.get_logger()
                # 参数
                params = {}
                component_properties = comp_obj.get_properties()
                for prop_name, prop_def in component_properties.items():
                    default_value = prop_def.get("default", "")
                    if self.has_property(prop_name):
                        params[prop_name] = self.get_property(prop_name)
                    else:
                        params[prop_name] = default_value

                # 输入
                inputs = {}
                for input_port in self.input_ports():
                    port_name = input_port.name()
                    connected = input_port.connected_ports()
                    if not connected:
                        continue
                    # 优先从 _input_values 获取（包含列选择结果）
                    if hasattr(self, '_input_values') and port_name in self._input_values:
                        inputs[port_name] = self._input_values[port_name]
                    else:
                        # 如果没有 _input_values，尝试从连接获取
                        upstream_out = connected[0]
                        upstream_node = upstream_out.node()
                        if hasattr(upstream_node, 'get_output_value'):
                            inputs[port_name] = upstream_node.get_output_value(upstream_out.name())

                if comp_obj.get_inputs():
                    output = comp_instance.execute(params, inputs)
                else:
                    output = comp_instance.execute(params)

                # 检查是否有UPLOAD类型输出且结果为None的情况
                has_upload_output = any(port.type == "upload" for port in comp_obj.outputs)
                if has_upload_output and output is None:
                    output = {}  # 转换为空字典

                if output is not None:
                    # 记录执行结果
                    component_class.logger.success("✅ 节点执行完成")
                    self.on_run_complete(output)
                    return output

            except Exception as e:
                error_msg = f"❌ 节点执行失败: {str(e)}"
                component_class.logger.error(error_msg)
                raise e

    return DynamicNode