import os
import pickle
import platform
import re
import subprocess
import time

from NodeGraphQt import BaseNode
from PyQt5 import QtCore

from .node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from app.components.base import PropertyType, GlobalVariableContext
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import resource_path
from app.widgets.node_widget.code_editor_widget import CodeEditorWidgetWrapper
from app.widgets.node_widget.custom_node_item import CustomNodeItem
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper
from ..widgets.dialog_widget.component_log_message_box import LogMessageBox

_TEMP_COMPONENT_TEMPLATE = '''# -*- coding: utf-8 -*-
{import_code}

class DynamicComponent(BaseComponent):
    name = "动态代码组件"
    category = "代码执行"
    description = "由用户动态生成的组件"
    requirements = "{requirements}"

    inputs = [
{inputs_list}
    ]
    outputs = [
{outputs_list}
    ]
    properties = {{
{properties_dict}
    }}

    {user_run_code}
'''

DEFAULT_CODE_TEMPLATE = '''def run(self, params, inputs=None):
    """
    params: 节点属性（来自UI）
    inputs: 上游输入（key=输入端口名）
    return: 输出数据（key=输出端口名）
    """
    # 在这里编写你的组件逻辑
    input_data = inputs.get("input_data") if inputs else None
    param1 = params.get("param1", "default_value")
    # 处理逻辑
    result = f"处理结果: {input_data} + {param1}"
    return {
        "output_data": result
    }
'''


def create_dynamic_code_node(parent_window=None):
    class DynamicCodeNode(BaseNode, BasicNodeWithGlobalProperty):
        __identifier__ = 'dynamic'
        NODE_NAME = "代码编辑"
        FULL_PATH = f"代码执行/{NODE_NAME}"
        FILE_PATH = "DYNAMIC_CODE"  # 不需要真实文件路径

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self._view.set_align("center")
            self.set_icon(resource_path("icons/代码执行.svg"))  # 可选
            self._node_logs = ""
            self._output_values = {}
            self._input_values = {}
            self.log_capture = NodeLogHandler(self.id, self._log_message, use_file_logging=True)

            # 允许动态删除端口
            self.model.port_deletion_allowed = True

            # 初始化属性控件（含 code 编辑器）
            self._init_properties()

            # 延迟绑定端口同步（避免初始化时 widget 未就绪）
            QtCore.QTimer.singleShot(300, self._setup_port_sync)

        def _setup_port_sync(self):
            widget = self.input_widget.get_custom_widget()
            widget.valueChanged.connect(self._sync_inputs_ports)
            else_widget = self.output_widget.get_custom_widget()
            else_widget.valueChanged.connect(self._sync_outputs_ports)
            self._sync_inputs_ports()
            self._sync_outputs_ports()

        def _init_properties(self):
            """初始化条件列表和 else 开关（只创建 widget，不绑定逻辑）"""
            input_schema = {
                "name": {
                    "type": PropertyType.TEXT.value,
                    "default": "",
                    "label": "输入端口名称",
                },
                "var": {
                    "type": PropertyType.VARIABLE.value,
                    "default": "",
                    "label": "变量选择",
                }
            }
            processed_schema = {}
            for field_name, field_def in input_schema.items():
                field_type_enum = PropertyType(field_def["type"])
                processed_schema[field_name] = {
                    "type": field_type_enum.name,
                    "label": field_def.get("label", field_name),
                    "choices": field_def.get("choices", [])
                }
            self.input_widget = DynamicFormWidgetWrapper(
                parent=self.view,
                name="input_ports",
                label="输入端口定义",
                schema=processed_schema,
                window=parent_window,
                z_value=100
            )
            self.add_custom_widget(self.input_widget, tab='Properties')

            output_schema = {
                "name": {
                    "type": PropertyType.TEXT.value,
                    "default": "",
                    "label": "输出端口名称",
                }
            }
            processed_schema = {}
            for field_name, field_def in output_schema.items():
                field_type_enum = PropertyType(field_def["type"])
                processed_schema[field_name] = {
                    "type": field_type_enum.name,
                    "label": field_def.get("label", field_name),
                    "choices": field_def.get("choices", [])
                }
            self.output_widget = DynamicFormWidgetWrapper(
                parent=self.view,
                name="output_ports",
                label="输出端口定义",
                schema=processed_schema,
                window=parent_window,
                z_value=100
            )
            self.add_custom_widget(self.output_widget, tab='Properties')

            code_widget = CodeEditorWidgetWrapper(
                parent=self.view,
                name="code",
                label="执行代码",
                default=DEFAULT_CODE_TEMPLATE.strip(),
                window=parent_window
            )
            self.add_custom_widget(code_widget, tab='Properties')

        def _sanitize_port_name(self, name: str) -> str:
            if not name:
                name = "branch"
            name = re.sub(r"[^a-zA-Z0-9_]", "_", str(name))
            if name and name[0].isdigit():
                name = "b_" + name
            return name

        def _sync_inputs_ports(self):
            """同步输入端口：严格按表单顺序重建，仅当端口名未变时恢复连线"""
            input_configs = self.get_property("input_ports") or []

            # 1. 按顺序生成期望的输入端口名（自动去重）
            expected_names = []
            used_names = set()
            for i, item in enumerate(input_configs):
                raw_name = item.get("name", f"input_{i}").strip() or f"input_{i}"
                port_name = self._sanitize_port_name(raw_name)
                base = port_name
                counter = 1
                while port_name in used_names:
                    port_name = f"{base}_{counter}"
                    counter += 1
                used_names.add(port_name)
                expected_names.append(port_name)

            # 2. 记录当前所有输入端口的连线状态：{port_name: [connected_upstream_ports]}
            current_connections = {}
            for port in self.input_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)

            # 3. 安全删除所有现有输入端口
            for port in list(self.input_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_input(port.name())

            # 4. 按 expected_names 顺序重建输入端口
            for name in expected_names:
                self.add_input(name)

            # 5. 恢复连线：仅当“旧端口名 == 新端口名”且新端口存在
            new_ports = {p.name(): p for p in self.input_ports()}
            for old_name, connected_list in current_connections.items():
                if old_name in new_ports:
                    new_port = new_ports[old_name]
                    for upstream_port in connected_list:
                        try:
                            if upstream_port.node() and upstream_port.node().graph:
                                upstream_port.connect_to(new_port, push_undo=False, emit_signal=False)
                        except Exception:
                            continue

        def _sync_outputs_ports(self):
            """同步输出端口：严格按表单顺序重建，仅当端口名未变时恢复连线"""
            output_configs = self.get_property("output_ports") or []

            # 1. 按顺序生成期望的输出端口名（自动去重）
            expected_names = []
            used_names = set()
            for i, item in enumerate(output_configs):
                raw_name = item.get("name", f"output_{i}").strip() or f"output_{i}"
                port_name = self._sanitize_port_name(raw_name)
                base = port_name
                counter = 1
                while port_name in used_names:
                    port_name = f"{base}_{counter}"
                    counter += 1
                used_names.add(port_name)
                expected_names.append(port_name)

            # 2. 记录当前所有输出端口的连线状态：{port_name: [connected_downstream_ports]}
            current_connections = {}
            for port in self.output_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)

            # 3. 安全删除所有现有输出端口
            for port in list(self.output_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_output(port.name())

            # 4. 按 expected_names 顺序重建输出端口
            for name in expected_names:
                self.add_output(name)

            # 5. 恢复连线：仅当“旧端口名 == 新端口名”且新端口存在
            new_ports = {p.name(): p for p in self.output_ports()}
            for old_name, connected_list in current_connections.items():
                if old_name in new_ports:
                    new_port = new_ports[old_name]
                    for downstream_port in connected_list:
                        try:
                            if downstream_port.node() and downstream_port.node().graph:
                                new_port.connect_to(downstream_port, push_undo=False, emit_signal=False)
                        except Exception:
                            continue

        # === 保留你原有的日志、执行、输出方法 ===
        def _log_message(self, node_id, message):
            if isinstance(message, str) and message.strip():
                if not message.endswith('\n'):
                    message += '\n'
                self._node_logs += message

        def show_logs(self):
            log_content = self.get_logs()
            w = LogMessageBox(log_content, parent_window)
            w.exec()

        def get_logs(self):
            return self._node_logs or "无日志可用。"

        def set_output_value(self, port, val):
            self._output_values[port] = val

        def get_output_value(self, port):
            return self._output_values.get(port)

        def on_run_complete(self, output):
            self._output_values = output

        # === 关键：重写 execute_sync，使用动态代码模板 ===
        def execute_sync(self, comp_obj, python_executable=None, check_cancel=None):
            if python_executable is None:
                raise Exception("未指定Python执行环境。")

            # === 1. 收集参数 ===
            user_code = self.get_property("code") or ""
            requirements = self.get_property("requirements") or ""

            # === 2. 构建 inputs / outputs 列表 ===
            from app.components.base import ArgumentType

            # 输入端口（全部视为 TEXT + SINGLE）
            input_defs = []
            for port in self.input_ports():
                name = port.name()
                input_defs.append(
                    f'        PortDefinition(name="{name}", label="{name}", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),')

            # 输出端口
            output_defs = []
            for port in self.output_ports():
                name = port.name()
                output_defs.append(f'        PortDefinition(name="{name}", label="{name}", type=ArgumentType.TEXT),')

            # === 3. 拼接临时组件代码 ===
            from app.components.base import COMPONENT_IMPORT_CODE

            # 确保用户代码是 def run(...) 形式
            if "def run(" not in user_code:
                raise ValueError("代码必须包含 def run(self, params, inputs=None): 函数")

            temp_component_code = _TEMP_COMPONENT_TEMPLATE.format(
                import_code=COMPONENT_IMPORT_CODE.strip(),
                requirements=requirements,
                inputs_list="\n".join(input_defs) if input_defs else "",
                outputs_list="\n".join(output_defs) if output_defs else "",
                properties_dict="",
                user_run_code=user_code.strip()
            )

            # === 4. 收集 inputs / params / global_variable（与普通组件一致）===
            global_variable = self.model.get_property("global_variable")
            gv = GlobalVariableContext()
            gv.deserialize(global_variable)

            inputs_raw = {}
            for input_port in self.input_ports():
                port_name = input_port.name()
                connected = input_port.connected_ports()
                if connected:
                    if len(connected) == 1:
                        upstream = connected[0]
                        value = upstream.node()._output_values.get(upstream.name())
                        inputs_raw[port_name] = value
                    else:
                        inputs_raw[port_name] = [
                            upstream.node()._output_values.get(upstream.name()) for upstream in connected
                        ]

            input_vars = {f"input_{k}": v for k, v in inputs_raw.items()}
            expr_engine = ExpressionEngine(global_vars_context=gv)

            def _evaluate_with_inputs(value, engine, input_vars_dict):
                if isinstance(value, str):
                    return engine.evaluate_template(value, local_vars=input_vars_dict)
                elif isinstance(value, list):
                    return [_evaluate_with_inputs(v, engine, input_vars_dict) for v in value]
                elif isinstance(value, dict):
                    return {k: _evaluate_with_inputs(v, engine, input_vars_dict) for k, v in value.items()}
                else:
                    return value

            inputs = {k: _evaluate_with_inputs(v, expr_engine, input_vars) for k, v in inputs_raw.items()}
            params = {}  # 当前无额外属性，可扩展

            # === 5. 写入临时文件并执行（复用你现有的子进程逻辑）===
            import tempfile
            with tempfile.TemporaryDirectory() as tmp_dir:
                temp_component_path = os.path.join(tmp_dir, "temp_component.py")
                params_path = os.path.join(tmp_dir, "params.pkl")
                result_path = os.path.join(tmp_dir, "result.pkl")
                error_path = os.path.join(tmp_dir, "error.pkl")
                log_file_path = self.log_capture.get_log_file_path()

                # 保存组件代码
                with open(temp_component_path, 'w', encoding='utf-8') as f:
                    f.write(temp_component_code)

                # 保存执行参数
                with open(params_path, 'wb') as f:
                    pickle.dump((params, inputs, global_variable), f)

                # 使用通用执行模板
                script_content = _EXECUTION_SCRIPT_TEMPLATE.format(
                    class_name="DynamicComponent",
                    file_path=temp_component_path.replace("\\", "\\\\"),
                    params_path=params_path.replace("\\", "\\\\"),
                    result_path=result_path.replace("\\", "\\\\"),
                    error_path=error_path.replace("\\", "\\\\"),
                    log_file_path=log_file_path.replace("\\", "\\\\"),
                    node_id=self.id
                )

                temp_script_path = os.path.join(tmp_dir, "exec_script.py")
                with open(temp_script_path, 'w', encoding='utf-8') as f:
                    f.write(script_content)

                max_retries = 1
                retry_count = 0

                while retry_count <= max_retries:
                    # 检查是否已取消
                    if check_cancel and check_cancel():
                        raise Exception("执行已被用户取消")

                    # 启动子进程（非阻塞）
                    kwargs = {}
                    if platform.system() == "Windows":
                        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

                    proc = subprocess.Popen(
                        [python_executable, temp_script_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        encoding='utf-8',
                        **kwargs
                    )

                    # 轮询 + 超时 + 取消检查
                    start_time = time.time()
                    timeout = 300  # 5分钟
                    cancelled = False
                    last_log_pos = 0

                    while proc.poll() is None:
                        # 检查取消
                        if check_cancel and check_cancel():
                            proc.terminate()
                            try:
                                proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            cancelled = True
                            break

                        # 检查超时
                        if time.time() - start_time > timeout:
                            proc.terminate()
                            try:
                                proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                proc.kill()

                            self._log_message(self.id, "❌ 节点执行超时（5分钟）")
                            raise Exception("❌ 节点执行超时（5分钟）")

                        # 增量读取日志，实时输出
                        try:
                            if os.path.exists(log_file_path):
                                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                                    lf.seek(last_log_pos)
                                    new_content = lf.read()
                                    if new_content:
                                        self._log_message(self.id, new_content)
                                        last_log_pos = lf.tell()
                        except Exception:
                            pass

                        time.sleep(0.1)  # 避免 CPU 占用过高

                    if cancelled:
                        self._log_message(self.id, "执行已被用户取消")
                        raise Exception("执行已被用户取消")

                    # 读取剩余日志（无论成功失败）
                    try:
                        if os.path.exists(log_file_path):
                            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                                lf.seek(last_log_pos)
                                tail_content = lf.read()
                                if tail_content:
                                    self._log_message(self.id, tail_content)
                    except Exception:
                        pass

                    # 检查是否成功
                    if proc.returncode == 0:
                        break

                # === 处理最终结果 ===
                if os.path.exists(result_path):
                    with open(result_path, 'rb') as f:
                        output = pickle.load(f)
                    for port in comp_obj.outputs:
                        if port.type != ArgumentType.UPLOAD:
                            self.set_output_value(port.name, output.get(port.name))
                    return output

                elif os.path.exists(error_path):
                    with open(error_path, 'rb') as f:
                        error_info = pickle.load(f)
                    error_msg = f"❌ 节点执行失败: {error_info['traceback']}"
                    self._log_message(self.id, error_msg)
                    raise Exception(error_info['error'])

                else:
                    # 未生成结果或错误文件，视为未知异常
                    error_msg = "❌ 节点执行异常: 未知错误"
                    self._log_message(self.id, error_msg)
                    raise Exception("未知错误")

    return DynamicCodeNode
