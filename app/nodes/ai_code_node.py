# -*- coding: utf-8 -*-
import json
import re

import Qt
from PyQt5 import QtCore, QtWidgets
from loguru import logger
from qfluentwidgets import TransparentPushButton, PrimaryPushButton
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET

from app.components.base import ArgumentType
from app.nodes.dynamic_code_node import create_dynamic_code_node
from app.nodes.status_node import StatusNode
from app.utils.config import Settings
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_port_item import draw_special_outputport
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.propeprty_widgets.dynamic_form_widget import (
    DynamicFormWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.text_edit_widget import TextWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.longtext_dialog import (
    LongTextWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.code_editor_widget import (
    CodeEditorWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.variable_combo_widget import (
    VarComboBoxWidgetWrapper,
)
from app.widgets.node_widget.base import CustomNodeBaseWidget


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
        FILE_PATH = "AI_CODE"
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
            if parent_window:
                self.view.rename_signal.connect(parent_window.rename_node_vars)
            self._init_properties()

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
            from PyQt5.QtCore import QThread

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
                PortDefinition,
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

        def execute_sync(
            self,
            comp_obj,
            kernel_manager=None,
            check_cancel=None,
            global_variable=None,
            **kwargs,
        ):
            from app.nodes.dynamic_code_node import create_dynamic_code_node

            dynamic_node_class = create_dynamic_code_node(self.parent_window)
            temp_node = dynamic_node_class(self.parent_window)
            try:
                temp_node.set_property(
                    "code", self.get_property("generated_code") or ""
                )
                temp_node.set_property("input_ports", [])
                temp_node.set_property("output_ports", [])

                for i, port in enumerate(self.input_ports()):
                    port_type = "TEXT"
                    for inp in self._generated_config.get("inputs", []):
                        if inp.get("name") == port.name():
                            port_type = inp.get("type", "TEXT").lower()
                            break
                    temp_node.set_property(
                        "input_ports",
                        temp_node.get_property("input_ports")
                        + [
                            {
                                "name": port.name(),
                                "type": port_type,
                                "conn_type": "single",
                            }
                        ],
                    )

                for i, port in enumerate(self.output_ports()):
                    port_type = "TEXT"
                    for out in self._generated_config.get("outputs", []):
                        if out.get("name") == port.name():
                            port_type = out.get("type", "TEXT").lower()
                            break
                    temp_node.set_property(
                        "output_ports",
                        temp_node.get_property("output_ports")
                        + [{"name": port.name(), "type": port_type}],
                    )

                temp_node._sync_inputs_ports()
                temp_node._sync_outputs_ports()

                return temp_node.execute_sync(
                    comp_obj, kernel_manager, check_cancel, global_variable, **kwargs
                )
            finally:
                pass

    return AICodeNode
