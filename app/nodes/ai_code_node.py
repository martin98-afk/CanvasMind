# -*- coding: utf-8 -*-
import json
import os
import pickle
import platform
import re
import shutil
import subprocess
import time
import uuid

import Qt
import paramiko
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5 import QtCore, QtWidgets
from loguru import logger
from qfluentwidgets import PrimaryPushButton

from app.components.base import (
    ArgumentType,
    GlobalVariableContext,
    resource_path,
)
from app.nodes.status_node import StatusNode
from app.scheduler.expression_engine import ExpressionEngine
from app.templates.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from app.utils.config import Settings
from app.utils.utils import (
    _safe_load_pickle,
    kill_proc_tree,
    sftp_download_dir,
    replace_remote_paths,
    sftp_upload_dir,
    get_free_port,
)
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.custom_nodegraphqt.custom_port_item import draw_special_outputport
from app.widgets.node_widget.base import CustomNodeBaseWidget
from app.widgets.node_widget.propeprty_widgets.code_editor_widget import (
    CodeEditorWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.longtext_dialog import (
    LongTextWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.variable_combo_widget import (
    VarComboBoxWidgetWrapper,
)

_TEMP_COMPONENT_TEMPLATE = """{import_code}class DynamicComponent(BaseComponent):
    name = "AI生成组件"
    category = "AI生成"
    description = "由AI生成的组件"
    requirements = ""

    inputs = [
{inputs_list}
    ]
    outputs = [
{outputs_list}
    ]
    properties = {{

    }}

    {user_run_code}
"""


class ButtonWidget(QtWidgets.QWidget):
    clicked = Qt.QtCore.Signal()
    fixed_height = True

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.main_window = parent
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = PrimaryPushButton(text, self)
        self.button.setFixedHeight(32)
        self.button.clicked.connect(self.clicked)
        layout.addWidget(self.button)

    def setText(self, text):
        self.button.setText(text)

    def get_value(self):
        return None

    def set_value(self, value):
        pass


class ButtonWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", text="", window=None, z_value=0):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(label)
        widget = ButtonWidget(text=text, parent=window)
        self.set_custom_widget(widget, add_on_label=True)
        widget.clicked.connect(self.on_value_changed)

    def _get_local_value(self):
        return None

    def _set_local_value(self, value):
        pass


def create_ai_code_node(parent_window=None):
    class AICodeNode(CustomBaseNode, StatusNode):
        __identifier__ = "ai"
        NODE_NAME = "AI生成节点"
        FULL_PATH = f"AI/{NODE_NAME}"
        CACHE_PATH = (
            parent_window.file_path.parent.resolve()
            if parent_window and hasattr(parent_window, "file_path")
            else None
        )

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self.set_icon(":/icons/大模型.svg")
            self.model.port_deletion_allowed = True
            self._dynamic_code_node = None
            self._generated_config = None
            self.object_io = False
            self._ai_node_uuid = f"ai_node_{id(self)}"
            if parent_window:
                self.view.rename_signal.connect(parent_window.rename_node_vars)
            self._init_properties()
            QtCore.QTimer.singleShot(100, self._build_ports)

        def _build_ports(self):
            custom_props = self.model._custom_prop
            generated_inputs = (
                custom_props.get("generated_inputs") or custom_props.get("inputs") or []
            )
            generated_outputs = (
                custom_props.get("generated_outputs")
                or custom_props.get("outputs")
                or []
            )

            if not generated_inputs and not generated_outputs:
                return

            for port in list(self.input_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_input(port.name())

            for port in list(self.output_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_output(port.name())

            for inp in generated_inputs:
                self.add_input(
                    inp.get("name", "input") if isinstance(inp, dict) else inp
                )

            for out in generated_outputs:
                self.add_output(
                    out.get("name", "out") if isinstance(out, dict) else out
                )

            if hasattr(self.parent_window, "global_variables"):
                node_name = re.sub(r"\s+", "_", self.name())
                for port in self.output_ports():
                    full_key = f"{node_name}__{port.name()}"
                    if full_key in self.parent_window.global_variables.node_vars:
                        port.set_painter_func(draw_special_outputport)

        def _init_properties(self):
            self.set_property("ai_state", "clay")

            self.requirement_widget = LongTextWidgetWrapper(
                parent=self.view,
                name="user_requirement",
                label="需求描述",
                default="",
                window=parent_window,
                z_value=10,
            )
            self.add_custom_widget(self.requirement_widget, tab="Properties")

            self.llm_config_widget = VarComboBoxWidgetWrapper(
                parent=self.view,
                name="llm_config_key",
                label="LLM配置",
                var_type="全局变量",
                main_window=parent_window,
                z_value=9,
            )
            self.add_custom_widget(self.llm_config_widget, tab="Properties")
            self.set_property("llm_config_key", "无")

            self.generate_button = ButtonWidgetWrapper(
                parent=self.view,
                name="generate_btn",
                label="生成节点",
                text="AI生成节点",
                window=parent_window,
                z_value=8,
            )
            self.add_custom_widget(self.generate_button, tab="Properties")
            self.generate_button.get_custom_widget().button.clicked.connect(
                self._on_generate_clicked
            )

            self.code_editor_widget = CodeEditorWidgetWrapper(
                parent=self.view,
                name="generated_code",
                label="生成代码",
                default="",
                window=parent_window,
            )
            self.code_editor = self.code_editor_widget.get_custom_widget()
            self.add_custom_widget(self.code_editor_widget, tab="Properties")

        def _update_status(self, status_text):
            self.set_property("status", status_text)
            logger.info(status_text)

        def _on_generate_clicked(self):
            requirement = self.requirement_widget.get_value() or ""
            requirement = requirement.strip() if isinstance(requirement, str) else ""
            llm_config_key = self.llm_config_widget.get_value() or "无"

            if not requirement:
                self._update_status("请输入需求描述")
                return

            self._update_status("正在调用AI生成节点...")
            self.set_property("ai_state", "generating")

            from app.widgets.side_dock_area.plugins.llm_chatter.utils.worker import (
                OpenAIChatWorker,
            )

            llm_config = self._get_llm_config(llm_config_key)
            if not llm_config:
                self._update_status("未找到有效的LLM配置")
                self.set_property("ai_state", "clay")
                return

            filtered_config = {
                k: v
                for k, v in llm_config.items()
                if not isinstance(v, (list, tuple, dict))
            }

            prompt = self._build_generation_prompt(requirement)

            self._worker = OpenAIChatWorker(
                messages=[{"role": "user", "content": prompt}],
                llm_config=filtered_config,
                tools=[],
                stream=True,
            )
            self._worker.finished_with_content.connect(self._on_generation_finished)
            self._worker.error_occurred.connect(self._on_generation_error)
            self._worker.start()

        def _get_llm_config(self, config_key):
            setting = Settings.get_instance()
            if (
                config_key
                and config_key != "无"
                and hasattr(self.parent_window, "global_variables")
            ):
                try:
                    global_vars = self.parent_window.global_variables
                    config = global_vars.get(config_key)
                    if config and isinstance(config, dict):
                        return config
                except Exception as e:
                    logger.warning(f"获取LLM配置失败: {e}")

            return {
                "模型名称": setting.llm_model.value,
                "API_KEY": setting.llm_api_key.value,
                "API_URL": setting.llm_api_base.value,
                "最大Token": setting.llm_max_tokens.value,
                "温度": setting.llm_temperature.value,
            }

        def _build_generation_prompt(self, requirement):
            return f"""你是一个工作流节点生成助手。请根据用户的需求描述，生成一个工作流节点的完整配置。

## 需求描述
{requirement}

## 输出要求
请严格按照以下JSON格式输出，不要有其他内容：
```json
{{
    "name": "节点名称（中文，不超过20字）",
    "description": "节点功能描述（不超过100字）",
    "inputs": [
        {{"name": "输入端口名", "label": "显示标签", "type": "类型"}}
    ],
    "outputs": [
        {{"name": "输出端口名", "label": "显示标签", "type": "类型"}}
    ],
    "properties": [
        {{"name": "属性名", "label": "显示标签", "type": "类型", "default": "默认值", "description": "描述"}}
    ],
    "code": "Python执行代码（def run函数）"
}}
```

## 类型说明
- 输入/输出端口 type 可选值: TEXT, INT, FLOAT, BOOL, OBJECT, FILE, IMAGE, JSON, CSV, EXCEL, ARRAY
- 属性 type 可选值: TEXT, INT, FLOAT, BOOL, CHOICE, LONGTEXT, FILE, RANGE

## 代码模板
def run(self, params, inputs=None):
    # params: 属性参数 (dict)
    # inputs: 输入端口数据 (dict, key=端口名)
    # 返回: dict (key=输出端口名)
    
    # 示例：
    # input_data = inputs.get("input1", "")
    # result = do_something(input_data)
    # return {{"output1": result}}

请根据需求生成完整的节点配置。"""

        def _on_generation_finished(self, content):
            try:
                self._update_status("解析AI返回结果...")
                config = self._parse_llm_response(content)
                if not config:
                    self._update_status("解析失败，请重试")
                    self.set_property("ai_state", "clay")
                    return

                self._generated_config = config
                self._update_status("构建节点...")
                self._apply_generated_config(config)
                self._update_status("生成完成！")
                self.set_property("ai_state", "ready")

                if self.parent_window and hasattr(self.parent_window, "property_panel"):
                    self.parent_window.property_panel.update_properties(self)

            except Exception as e:
                logger.exception("AI节点生成失败")
                self._update_status(f"生成失败: {str(e)}")
                self.set_property("ai_state", "clay")

        def _on_generation_error(self, error_msg):
            self._update_status(f"调用失败: {error_msg}")
            self.set_property("ai_state", "clay")

        def _parse_llm_response(self, content):
            json_match = re.search(r"\{[\s\S]*\}", content)
            if not json_match:
                return None
            try:
                config = json.loads(json_match.group())
                return config
            except json.JSONDecodeError:
                return None

        def _apply_generated_config(self, config):
            existing_inputs = list(self.input_ports())
            for port in existing_inputs:
                self.delete_input(port.name())

            existing_outputs = list(self.output_ports())
            for port in existing_outputs:
                self.delete_output(port.name())

            input_type_map = {
                "TEXT": ArgumentType.TEXT,
                "INT": ArgumentType.INT,
                "FLOAT": ArgumentType.FLOAT,
                "BOOL": ArgumentType.BOOL,
                "OBJECT": ArgumentType.OBJECT,
                "FILE": ArgumentType.FILE,
                "IMAGE": ArgumentType.IMAGE,
                "JSON": ArgumentType.JSON,
                "CSV": ArgumentType.CSV,
                "EXCEL": ArgumentType.EXCEL,
                "ARRAY": ArgumentType.ARRAY,
            }

            for inp in config.get("inputs", []):
                port_type = input_type_map.get(
                    inp.get("type", "TEXT"), ArgumentType.TEXT
                )
                self.add_input(inp.get("name", "input"))

            for out in config.get("outputs", []):
                port_type = input_type_map.get(
                    out.get("type", "TEXT"), ArgumentType.TEXT
                )
                self.add_output(out.get("name", "output"))

            node_name = re.sub(r"\s+", "_", self.name())
            for port in self.output_ports():
                full_key = f"{node_name}__{port.name()}"
                if (
                    hasattr(self.parent_window, "global_variables")
                    and full_key in self.parent_window.global_variables.node_vars
                ):
                    port.set_painter_func(draw_special_outputport)

            self.set_property("generated_name", config.get("name", ""))
            self.set_property("generated_description", config.get("description", ""))
            self.set_property("generated_code", config.get("code", ""))
            self.set_property("generated_inputs", config.get("inputs", []))
            self.set_property("generated_outputs", config.get("outputs", []))
            self.set_property("generated_properties", config.get("properties", []))

            self.NODE_NAME = config.get("name", "AI生成节点")
            self.model.set_property("name", self.NODE_NAME)

            generated_code = config.get("code", "")
            if self.code_editor:
                self.code_editor.set_code(generated_code)
            self.set_property("code", generated_code)

        def get_generated_code(self):
            return self.get_property("generated_code") or ""

        def format_code(self, add_import=True):
            from app.components.base import (
                COMPONENT_IMPORT_CODE,
                ArgumentType,
            )

            config = self._generated_config or {}
            code = config.get("code", "")

            type_dict = {item.value: item.name for item in ArgumentType}

            input_defs = []
            for port in self.input_ports():
                port_def = {"type": "TEXT"}
                for inp in config.get("inputs", []):
                    if inp.get("name") == port.name():
                        port_def = inp
                        break
                input_type = type_dict.get(port_def.get("type", "TEXT"), "TEXT")
                input_defs.append(
                    f'        PortDefinition(name="{port.name()}", label="{port.name()}", type=ArgumentType.{input_type}),'
                )

            output_defs = []
            for port in self.output_ports():
                port_def = {"type": "TEXT"}
                for out in config.get("outputs", []):
                    if out.get("name") == port.name():
                        port_def = out
                        break
                output_type = type_dict.get(port_def.get("type", "TEXT"), "TEXT")
                output_defs.append(
                    f'        PortDefinition(name="{port.name()}", label="{port.name()}", type=ArgumentType.{output_type}),'
                )

            name = config.get("name", "AI生成节点")
            description = config.get("description", "")

            indented_code = "\n".join(
                "    " + line if line.strip() else line for line in code.splitlines()
            )

            template = """{import_code}class DynamicComponent(BaseComponent):
    name = "{name}"
    category = "AI生成"
    description = "{description}"
    requirements = ""

    inputs = [
{inputs_list}
    ]
    outputs = [
{outputs_list}
    ]
    properties = {{

    }}

    {user_run_code}
"""
            return template.format(
                import_code=COMPONENT_IMPORT_CODE if add_import else "",
                name=name,
                description=description,
                inputs_list="\n".join(input_defs) if input_defs else "",
                outputs_list="\n".join(output_defs) if output_defs else "",
                user_run_code=indented_code.strip(),
            )

        def save_to_component(self):
            if hasattr(self.parent_window, "parent"):
                self.parent_window.parent.develop_page.reset_edit()
                self.parent_window.parent.develop_page.code_editor.set_code(
                    self.format_code(add_import=False)
                )
                self.parent_window.parent.switchTo(
                    self.parent_window.parent.develop_page
                )

        def format_code_for_execute(self):
            from app.components.base import COMPONENT_IMPORT_CODE

            config = self._generated_config or {}
            code = self.get_property("generated_code") or config.get("code", "")

            type_dict = {item.value: item.name for item in ArgumentType}

            input_defs = []
            for port in self.input_ports():
                port_type = "TEXT"
                for inp in config.get("inputs", []):
                    if inp.get("name") == port.name():
                        port_type = inp.get("type", "TEXT")
                        break
                input_type = type_dict.get(port_type, "TEXT")
                input_defs.append(
                    f'        PortDefinition(name="{port.name()}", label="{port.name()}", type=ArgumentType.{input_type}, connection=ConnectionType.SINGLE),'
                )

            output_defs = []
            for port in self.output_ports():
                port_type = "TEXT"
                for out in config.get("outputs", []):
                    if out.get("name") == port.name():
                        port_type = out.get("type", "TEXT")
                        break
                output_type = type_dict.get(port_type, "TEXT")
                output_defs.append(
                    f'        PortDefinition(name="{port.name()}", label="{port.name()}", type=ArgumentType.{output_type}),'
                )

            name = config.get("name", "AI生成组件")
            description = config.get("description", "")

            indented_code = "\n".join(
                "    " + line if line.strip() else line for line in code.splitlines()
            )

            return _TEMP_COMPONENT_TEMPLATE.format(
                import_code=COMPONENT_IMPORT_CODE,
                name=name,
                description=description,
                inputs_list="\n".join(input_defs) if input_defs else "",
                outputs_list="\n".join(output_defs) if output_defs else "",
                user_run_code=indented_code.strip(),
            )

        def execute_sync(
            self,
            comp_obj,
            kernel_manager=None,
            check_cancel=None,
            global_variable=None,
            **kwargs,
        ):
            try:
                self.hide_inline_widgets()
                self.clear_output_value()
                self.init_logger()

                env_data = self.parent_window.env_data
                if not env_data:
                    raise Exception("未检测到有效的执行环境，请先在环境管理器中选择。")

                temp_component_name = f"ai_dynamic_{uuid.uuid4().hex}.py"
                run_id = f"run_{self.persistent_id}"
                run_dir = self.CACHE_PATH / "run_scripts" / run_id
                temp_component_path = run_dir / temp_component_name
                shutil.rmtree(run_dir, ignore_errors=True)
                run_dir.mkdir(parents=True, exist_ok=True)

                local_script_path = run_dir / "exec_script.py"
                local_comp_path = run_dir / "component.py"
                params_path = run_dir / "params.pkl"
                result_path = run_dir / "result.pkl"
                error_path = run_dir / "error.pkl"
                log_file_path = self.log_capture.get_log_file_path()

                temp_component_code = self.format_code_for_execute()
                with open(temp_component_path, "w", encoding="utf-8") as f:
                    f.write(temp_component_code)
                with open(local_comp_path, "w", encoding="utf-8") as f:
                    f.write(temp_component_code)

                gv = GlobalVariableContext()
                gv.deserialize(global_variable)
                inputs_raw = {}
                input_vars = {}
                global_variable["inputs"] = {}
                for i, input_port in enumerate(self.input_ports()):
                    port_name = input_port.name()
                    connected = input_port.connected_ports()
                    if connected:
                        if input_port.model.multi_connection:
                            inputs_raw[port_name] = [
                                upstream.node()._output_values.get(upstream.name())
                                for upstream in connected
                            ]
                            safe_key = f"input_{port_name}"
                            input_vars[safe_key] = inputs_raw[port_name]
                            for index, upstream in enumerate(connected):
                                safe_name = upstream.node().name().replace(" ", "_")
                                safe_key = f"input_{safe_name}__{upstream.name()}"
                                input_vars[safe_key] = (
                                    upstream.node()._output_values.get(upstream.name())
                                )
                                global_variable["inputs"][
                                    f"input.{safe_name}__{upstream.name()}"
                                ] = index
                        else:
                            inputs_raw[port_name] = (
                                connected[0]
                                .node()
                                ._output_values.get(connected[0].name())
                            )
                            safe_key = f"input_{port_name}"
                            input_vars[safe_key] = inputs_raw[port_name]
                            safe_name = connected[0].node().name().replace(" ", "_")
                            safe_key = f"input_{safe_name}__{connected[0].name()}"
                            input_vars[safe_key] = inputs_raw[port_name]
                        if port_name in self.get_property("_data_select"):
                            inputs_raw[f"{port_name}_data_select"] = self.get_property(
                                "_data_select"
                            ).get(port_name)
                            inputs_raw[f"{port_name}_data_select_visible"] = (
                                self.get_property("_data_select_visible") or {}
                            ).get(port_name, False)

                expr_engine = ExpressionEngine(global_vars_context=gv)

                def _evaluate(v):
                    if isinstance(v, str):
                        return expr_engine.evaluate_template(v, local_vars=input_vars)
                    if isinstance(v, list):
                        return [_evaluate(i) for i in v]
                    if isinstance(v, dict):
                        return {k: _evaluate(val) for k, val in v.items()}
                    return v

                inputs = {k: _evaluate(v) for k, v in inputs_raw.items()}

                if Settings.get_instance().communication_method.value == "ZMQ通信":
                    remote_ip = (
                        env_data.get("host") if env_data.get("type") == "ssh" else None
                    )
                    self._zmq_pub_port = get_free_port()
                    self._zmq_svc_port = get_free_port()
                    zmq_env_vars = self.setup_zmq_env(
                        self._zmq_pub_port, self._zmq_svc_port, remote_ip
                    )
                else:
                    zmq_env_vars = {}

                with open(params_path, "wb") as f:
                    pickle.dump(({}, inputs, global_variable), f)

                self.last_log_pos = (
                    os.path.getsize(log_file_path)
                    if os.path.exists(log_file_path)
                    else 0
                )
                self.timeout_enabled = (
                    self.parent_window.config.node_run_timeout_toggle.value
                )
                self.timeout_seconds = self.parent_window.config.node_run_timeout.value

                if env_data.get("type") == "ssh":
                    self._execute_via_ssh(
                        comp_obj,
                        env_data,
                        kernel_manager,
                        run_dir,
                        log_file_path,
                        error_path,
                        check_cancel,
                        zmq_env_vars,
                    )
                else:
                    shutil.copyfile(
                        resource_path("app/components/base.py"),
                        str(run_dir.parent / "base.py"),
                    )
                    python_exe = env_data["path"]
                    env_inject_code = "\n".join(
                        [f"os.environ['{k}'] = '{v}'" for k, v in zmq_env_vars.items()]
                    )
                    script_content = (
                        "import os\n"
                        + env_inject_code
                        + "\n"
                        + _EXECUTION_SCRIPT_TEMPLATE.format(
                            class_name="DynamicComponent",
                            file_path=str(local_comp_path.resolve()),
                            params_path=str(params_path.resolve()),
                            result_path=str(result_path.resolve()),
                            error_path=str(error_path.resolve()),
                            log_file_path=str(log_file_path.resolve()),
                            node_id=self.persistent_id,
                            workflow_path=str(self.CACHE_PATH),
                            is_memory_resident=self.view.current_mode == "ipython",
                        )
                    )
                    with open(local_script_path, "w", encoding="utf-8") as f:
                        f.write(script_content)

                    if (
                        self.model.get_property("_exec_mode") == "ipython"
                        or self.object_io
                    ):
                        self._execute_via_ipython(
                            local_script_path,
                            result_path,
                            error_path,
                            log_file_path,
                            check_cancel,
                            kernel_manager,
                        )
                    else:
                        self._execute_via_subprocess(
                            python_exe, local_script_path, log_file_path, check_cancel
                        )

                with open(log_file_path, "r", encoding="utf-8", errors="ignore") as lf:
                    lf.seek(self.last_log_pos)
                    new_content = lf.read()
                    if new_content:
                        self._log_message(self.persistent_id, new_content)
                        self.last_log_pos = lf.tell()

                if result_path.exists():
                    output = _safe_load_pickle(result_path)
                    for port in self.output_ports():
                        if port.name() in output:
                            self.set_output_value(port.name(), output[port.name()])
                    self._sync_buffer_to_global()
                    return output
                elif error_path.exists():
                    error_info = _safe_load_pickle(error_path)
                    raise Exception(error_info["traceback"])
                else:
                    raise Exception("执行结束，未发现结果。")

            finally:
                try:
                    temp_component_path.unlink(missing_ok=True)
                    shutil.rmtree(run_dir, ignore_errors=True)
                except:
                    pass

        def _execute_via_ssh(
            self,
            comp_obj,
            env_data,
            kernel_manager,
            run_dir,
            log_file_path,
            error_path,
            check_cancel,
            zmq_env_vars,
        ):
            local_result_path = run_dir / "result.pkl"
            remote_root = "/tmp/workspace"
            upload_dir = f"{remote_root}/{self.persistent_id}/upload"
            result_dir = f"{remote_root}/{self.persistent_id}/result"
            remote_run_dir = f"{remote_root}/{self.persistent_id}/run_scripts"
            log_path = f"{remote_root}/node_logs/{self.persistent_id}.log"
            local_node_workspace = self.CACHE_PATH / "workspace" / self.persistent_id

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                ssh.connect(
                    env_data["host"],
                    int(env_data.get("port", 22)),
                    env_data["user"],
                    env_data["pwd"],
                    timeout=15,
                    compress=True,
                )
                sftp = ssh.open_sftp()
                ssh.exec_command(
                    f"mkdir -p {upload_dir} {result_dir} {remote_run_dir} {remote_root}/node_logs"
                )
                ssh.exec_command(f"rm -f {log_path}| touch {log_path}")

                env_inject_code = "\n".join(
                    [f"os.environ['{k}'] = '{v}'" for k, v in zmq_env_vars.items()]
                )

                remote_script_content = (
                    "import os\n"
                    + env_inject_code
                    + "\n"
                    + _EXECUTION_SCRIPT_TEMPLATE.format(
                        class_name=comp_obj.__name__,
                        file_path=f"{remote_run_dir}/component.py",
                        params_path=f"{remote_run_dir}/params.pkl",
                        result_path=f"{remote_run_dir}/result.pkl",
                        error_path=f"{remote_run_dir}/error.pkl",
                        log_file_path=log_path,
                        node_id=self.persistent_id,
                        workflow_path="/tmp",
                        is_memory_resident=self.view.current_mode == "ipython",
                    )
                )
                with open(run_dir / "exec_script.py", "w", encoding="utf-8") as f:
                    f.write(remote_script_content)

                local_upload_dir = local_node_workspace / "upload"
                if local_upload_dir.exists():
                    sftp_upload_dir(sftp, local_upload_dir, upload_dir)
                sftp_upload_dir(
                    sftp,
                    resource_path(f"app/component_extensions/{self._ai_node_uuid}"),
                    f"{remote_root}/{self.persistent_id}",
                )
                sftp_upload_dir(sftp, run_dir, remote_run_dir)
                sftp.put(
                    resource_path("app/components/base.py"),
                    f"{remote_root}/{self.persistent_id}/base.py",
                )

                last_log_pos = 0
                if self.view.current_mode == "ipython" or self.object_io:
                    if not kernel_manager:
                        raise Exception("远程 IPython 内核未连接。")
                    kernel_manager.execute_code(remote_script_content, hidden=True)
                    start_time = time.time()
                    remote_res = f"{remote_run_dir}/result.pkl"
                    remote_err = f"{remote_run_dir}/error.pkl"
                    while True:
                        if check_cancel and check_cancel():
                            kernel_manager.interrupt_kernel()
                            raise Exception("远程 IPython 执行被取消")
                        _, stdout, _ = ssh.exec_command(f"ls {remote_res} {remote_err}")
                        found = stdout.read().decode()

                        try:
                            with sftp.open(log_path, "r") as f:
                                f.seek(last_log_pos)
                                new_data = f.read().decode("utf-8", errors="ignore")
                                if new_data:
                                    self._log_message(self.persistent_id, new_data)
                                    last_log_pos = f.tell()
                        except:
                            pass

                        if remote_res in found or remote_err in found:
                            break
                        if (
                            self.timeout_enabled
                            and time.time() - start_time > self.timeout_seconds
                        ):
                            kernel_manager.interrupt_kernel()
                            raise Exception("远程 IPython 执行超时")
                        time.sleep(0.5)
                else:
                    python_exe = env_data["path"]
                    env_cmd = " ".join([f"{k}={v}" for k, v in zmq_env_vars.items()])
                    cmd = f"export PYTHONPATH={remote_root}:$PYTHONPATH && export {env_cmd} && {python_exe} {remote_run_dir}/exec_script.py"
                    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
                    stdout.channel.setblocking(0)
                    start_time = time.time()
                    while not stdout.channel.exit_status_ready():
                        if check_cancel and check_cancel():
                            ssh.exec_command(
                                f"pkill -f {remote_run_dir}/exec_script.py"
                            )
                            ssh.close()
                            raise Exception("远程执行被用户取消")
                        try:
                            with sftp.open(log_path, "r") as f:
                                f.seek(last_log_pos)
                                new_data = f.read().decode("utf-8", errors="ignore")
                                if new_data:
                                    self._log_message(self.persistent_id, new_data)
                                    last_log_pos = f.tell()
                        except:
                            pass
                        if (
                            self.timeout_enabled
                            and time.time() - start_time > self.timeout_seconds
                        ):
                            ssh.exec_command(
                                f"pkill -f {remote_run_dir}/exec_script.py"
                            )
                            ssh.close()
                            raise Exception("执行超时")
                        time.sleep(0.5)

                try:
                    sftp.get(f"{remote_run_dir}/result.pkl", str(local_result_path))
                    replace_remote_paths(
                        local_result_path,
                        f"{remote_root}/{self.persistent_id}",
                        str(local_node_workspace),
                    )
                except:
                    os.remove(local_result_path) if os.path.exists(
                        local_result_path
                    ) else None
                try:
                    sftp.get(f"{remote_run_dir}/error.pkl", str(error_path))
                except:
                    os.remove(error_path) if os.path.exists(error_path) else None
                local_res_dir = local_node_workspace / "result"
                local_res_dir.mkdir(parents=True, exist_ok=True)
                try:
                    sftp_download_dir(sftp, result_dir, local_res_dir, ssh=ssh)
                except:
                    pass

                ssh.exec_command(f"rm -rf {remote_run_dir}")
                with sftp.open(log_path, "r") as f:
                    f.seek(last_log_pos)
                    new_data = f.read().decode("utf-8", errors="ignore")
                    if new_data:
                        self._log_message(self.persistent_id, new_data)
                self._log_message(self.persistent_id, "✅ 节点在ssh远程环境执行完成")

            except Exception as e:
                raise Exception(f"远程执行失败: {str(e)}")
            finally:
                if "sftp" in locals():
                    sftp.close()
                ssh.close()

        def _execute_via_ipython(
            self,
            temp_script_path,
            result_path,
            error_path,
            log_file_path,
            check_cancel,
            kernel_manager,
        ):
            run_code = f"%reset -f"
            kernel_manager.execute_code(run_code, hidden=True)

            with open(temp_script_path, "r", encoding="utf-8") as f:
                code = f.read()
            kernel_manager.execute_code(code, hidden=True)

            start_time = time.time()
            while not (result_path.exists() or error_path.exists()):
                if check_cancel and check_cancel():
                    try:
                        kernel_manager.interrupt_kernel()
                        self._log_message(
                            self.persistent_id, "✅ 内核已重启，执行已终止。"
                        )
                    except Exception as e:
                        self._log_message(self.persistent_id, f"⚠️ 内核重启失败: {e}")
                    raise Exception("执行被用户取消")
                try:
                    if os.path.exists(log_file_path):
                        with open(
                            log_file_path, "r", encoding="utf-8", errors="ignore"
                        ) as lf:
                            lf.seek(self.last_log_pos)
                            new_content = lf.read()
                            if new_content:
                                self._log_message(self.persistent_id, new_content)
                                self.last_log_pos = lf.tell()
                except Exception:
                    pass
                if (
                    self.timeout_enabled
                    and time.time() - start_time > self.timeout_seconds
                ):
                    kernel_manager.interrupt_kernel()
                    raise Exception(f"❌ 节点执行超时（{self.timeout_seconds} 秒）")

                time.sleep(0.1)
            self._log_message(self.persistent_id, "✅ 节点在ipython环境执行完成")

        def _execute_via_subprocess(
            self, python_executable, temp_script_path, log_file_path, check_cancel
        ):
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(
                [python_executable, temp_script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                **kwargs,
            )

            start_time = time.time()
            while proc.poll() is None:
                if check_cancel and check_cancel():
                    kill_proc_tree(proc.pid)
                    raise Exception("执行已被用户取消")
                if (
                    self.timeout_enabled
                    and time.time() - start_time > self.timeout_seconds
                ):
                    kill_proc_tree(proc.pid)
                    raise Exception(f"❌ 节点执行超时（{self.timeout_seconds} 秒）")
                try:
                    if os.path.exists(log_file_path):
                        with open(
                            log_file_path, "r", encoding="utf-8", errors="ignore"
                        ) as lf:
                            lf.seek(self.last_log_pos)
                            new_content = lf.read()
                            if new_content:
                                self._log_message(self.persistent_id, new_content)
                                self.last_log_pos = lf.tell()
                except Exception:
                    pass
                time.sleep(0.1)
            self._log_message(self.persistent_id, "✅ 节点在独立环境执行完成")

    return AICodeNode
