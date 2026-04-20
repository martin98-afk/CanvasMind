# -*- coding: utf-8 -*-
import re

from PyQt5 import QtCore

from app.components.base import (
    PropertyType,
    ArgumentType,
    ConnectionType,
    COMPONENT_IMPORT_CODE,
)
from app.nodes.base.executable_node import ExecutableNode
from app.templates.glue_code_templates import GLUE_CODE_TEMPLATES
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.custom_nodegraphqt.custom_port_item import (
    draw_special_outputport,
    draw_square_port,
)
from app.widgets.node_widget.propeprty_widgets.code_editor_widget import (
    CodeEditorWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.combobox_widget import (
    ComboBoxWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.dynamic_form_widget import (
    DynamicFormWidgetWrapper,
)

_TEMP_COMPONENT_TEMPLATE = """{import_code}class DynamicComponent(BaseComponent):
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
"""


def create_dynamic_code_node(parent_window=None):
    class DynamicCodeNode(CustomBaseNode, ExecutableNode):
        __identifier__ = "dynamic"
        NODE_NAME = "代码编辑"
        FULL_PATH = f"代码执行/{NODE_NAME}"
        FILE_PATH = "DYNAMIC_CODE"
        description = "动态代码组件，右键选择固化为组件可以将当前代码保存为固定组件。"
        CACHE_PATH = parent_window.file_path.parent.resolve()

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self.set_icon(":/icons/代码执行.svg")
            self.model.port_deletion_allowed = True
            self.view.rename_signal.connect(parent_window.rename_node_vars)
            self.view.exec_mode_signal.connect(self._clear_ipython_memory_context)

            self._input_sync_timer = QtCore.QTimer()
            self._input_sync_timer.setSingleShot(True)
            self._input_sync_timer.timeout.connect(self._sync_inputs_ports)

            self._output_sync_timer = QtCore.QTimer()
            self._output_sync_timer.setSingleShot(True)
            self._output_sync_timer.timeout.connect(self._sync_outputs_ports)

            self._property_update_timer = QtCore.QTimer()
            self._property_update_timer.setSingleShot(True)
            self._property_update_timer.timeout.connect(self._deferred_property_update)

            self._init_properties()
            self._setup_port_sync()

        def _setup_port_sync(self):
            input_widget = self.input_widget.get_custom_widget()
            input_widget.valueChanged.connect(self._on_inputs_changed)
            output_widget = self.output_widget.get_custom_widget()
            output_widget.valueChanged.connect(self._on_outputs_changed)
            self._sync_inputs_ports()
            self._sync_outputs_ports()

        def _on_inputs_changed(self):
            self._input_sync_timer.start(100)

        def _on_outputs_changed(self):
            self._output_sync_timer.start(100)

        def _deferred_property_update(self):
            """防抖后的属性面板更新"""
            if self.parent_window and hasattr(self.parent_window, "property_panel"):
                self.parent_window.property_panel.update_properties(self)

        def _init_properties(self):
            # self.set_property(f"_port_type_choices", [item.value for item in ArgumentType])
            input_schema = {
                "name": {
                    "type": PropertyType.TEXT.value,
                    "default": "input{{id}}",
                    "label": "输入端口名称",
                },
                "type": {
                    "type": PropertyType.CHOICE.value,
                    "default": PropertyType.TEXT.value,
                    "label": "输入端口类型",
                    "choices": [item.value for item in ArgumentType],
                },
                "conn_type": {
                    "type": PropertyType.CHOICE.value,
                    "default": ConnectionType.SINGLE.value,
                    "label": "单/多输入",
                    "choices": [item.value for item in ConnectionType],
                },
            }
            processed_schema = {}
            for field_name, field_def in input_schema.items():
                field_type_enum = PropertyType(field_def["type"])
                processed_schema[field_name] = {
                    "type": field_type_enum.name,
                    "label": field_def.get("label", field_name),
                    "choices": field_def.get("choices", []),
                    "default": field_def.get("default", ""),
                }
            self.input_widget = DynamicFormWidgetWrapper(
                parent=self.view,
                name="input_ports",
                label="输入端口定义",
                schema=processed_schema,
                window=parent_window,
                z_value=4,
            )
            self.add_custom_widget(self.input_widget, tab="Properties")
            output_schema = {
                "name": {
                    "type": PropertyType.TEXT.value,
                    "default": "output{{id}}",
                    "label": "输出端口名称",
                },
                "type": {
                    "type": PropertyType.CHOICE.value,
                    "default": PropertyType.TEXT.value,
                    "label": "输入端口类型",
                    "choices": [item.value for item in ArgumentType],
                },
            }
            processed_schema = {}
            for field_name, field_def in output_schema.items():
                field_type_enum = PropertyType(field_def["type"])
                processed_schema[field_name] = {
                    "type": field_type_enum.name,
                    "label": field_def.get("label", field_name),
                    "choices": field_def.get("choices", []),
                    "default": field_def.get("default", ""),
                }
            self.output_widget = DynamicFormWidgetWrapper(
                parent=self.view,
                name="output_ports",
                label="输出端口定义",
                schema=processed_schema,
                window=parent_window,
                z_value=3,
            )
            self.add_custom_widget(self.output_widget, tab="Properties")
            self.glue_templates_widget = ComboBoxWidgetWrapper(
                parent=self.view,
                name="glue_code_template",
                label="胶水代码模板",
                items=[key for key in GLUE_CODE_TEMPLATES],
                z_value=2,
                window=parent_window,
            )
            self.add_custom_widget(self.glue_templates_widget, tab="Properties")

            code_widget = CodeEditorWidgetWrapper(
                parent=self.view,
                name="code",
                label="执行代码",
                default=GLUE_CODE_TEMPLATES.get("空白模板"),
                window=parent_window,
            )
            self.code_editor = code_widget.get_custom_widget()
            self.add_custom_widget(code_widget, tab="Properties")

            glue_combo = self.glue_templates_widget.get_custom_widget()
            glue_combo.combobox.currentIndexChanged.connect(
                self._on_glue_template_changed
            )

        def _on_glue_template_changed(self, index):
            combo = self.glue_templates_widget.get_custom_widget()
            current_text = combo.combobox.currentText()
            if not current_text:
                return
            try:
                template_code = GLUE_CODE_TEMPLATES[current_text]
            except (IndexError, KeyError):
                return
            self.code_editor.set_code(template_code)

        def _sanitize_port_name(self, name: str) -> str:
            name = re.sub(r"[^a-zA-Z0-9_]", "_", str(name))
            if name and name[0].isdigit():
                name = "b_" + name
            return name

        @property
        def port_info(self):
            type_dict = {item.value: item.name for item in ArgumentType}
            port_info = "输入端口: "
            for port, port_def in zip(
                    self.input_ports(), self.get_property("input_ports")
            ):
                port_info += f"{port.name()} ({type_dict[port_def["type"]]});"
            port_info += "\n输出端口: "
            for port, port_def in zip(
                    self.output_ports(), self.get_property("output_ports")
            ):
                port_info += f"{port.name()} ({type_dict[port_def["type"]]});"
            return port_info

        def _sync_inputs_ports(self):
            input_configs = self.get_property("input_ports") or []

            expected_names = []
            conn_types = []
            used_names = set()
            name_mapping = {}
            for i, item in enumerate(input_configs):
                raw_name = item.get("name", f"input{i}").strip() or f"input{i}"
                port_name = self._sanitize_port_name(raw_name)
                base = port_name
                counter = 1
                while port_name in used_names:
                    port_name = f"{base}{counter}"
                    counter += 1
                used_names.add(port_name)
                expected_names.append(port_name)
                conn_types.append(item.get("conn_type", ConnectionType.SINGLE.value))
                name_mapping[i] = port_name

            current_connections = {}
            for port in self.input_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)

            for port in list(self.input_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_input(port.name())

            for name, conn_type in zip(expected_names, conn_types):
                if conn_type == ConnectionType.MULTIPLE.value:
                    self.add_input(
                        name, multi_input=True, painter_func=draw_square_port
                    )
                else:
                    self.add_input(name)

            new_ports = {p.name(): p for p in self.input_ports()}
            for old_name, connected_list in current_connections.items():
                if old_name in new_ports:
                    new_port = new_ports[old_name]
                    for upstream_port in connected_list:
                        try:
                            if upstream_port.node() and upstream_port.node().graph:
                                upstream_port.connect_to(
                                    new_port, push_undo=False, emit_signal=False
                                )
                        except Exception:
                            continue
            if self.selected():
                self._property_update_timer.start(500)

        def _sync_outputs_ports(self):
            output_configs = self.get_property("output_ports") or []

            expected_names = []
            used_names = set()
            name_mapping = {}
            for i, item in enumerate(output_configs):
                raw_name = item.get("name", f"output{i}").strip() or f"output{i}"
                port_name = self._sanitize_port_name(raw_name)
                base = port_name
                counter = 1
                while port_name in used_names:
                    port_name = f"{base}{counter}"
                    counter += 1
                used_names.add(port_name)
                expected_names.append(port_name)
                name_mapping[i] = port_name

            current_connections = {}
            for port in self.output_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)

            for port in list(self.output_ports()):
                port.clear_connections(push_undo=False, emit_signal=False)
                self.delete_output(port.name())

            for name in expected_names:
                node_name = re.sub(r"\s+", "_", self.name())
                safe_name = re.sub(r".", "_", name)
                if f"{node_name}__{safe_name}" in parent_window.global_variables.node_vars:
                    self.add_output(name, painter_func=draw_special_outputport)
                else:
                    self.add_output(name)

            new_ports = {p.name(): p for p in self.output_ports()}
            for old_name, connected_list in current_connections.items():
                if old_name in new_ports:
                    new_port = new_ports[old_name]
                    for downstream_port in connected_list:
                        try:
                            if downstream_port.node() and downstream_port.node().graph:
                                new_port.connect_to(
                                    downstream_port, push_undo=False, emit_signal=False
                                )
                        except Exception:
                            continue

            if self.selected():
                self._property_update_timer.start(500)

        def _sync_names_to_form(self, ports, name_mapping, type="input"):
            updated_ports = []
            name_changed = False

            for i, cond in enumerate(ports):
                original_name = cond.get("name", type).strip() or type
                generated_name = name_mapping.get(i, type)

                sanitized_original = self._sanitize_port_name(original_name)
                needs_update = sanitized_original != generated_name

                if needs_update:
                    new_cond = cond.copy()
                    new_cond["name"] = generated_name
                    updated_ports.append(new_cond)
                    name_changed = True
                else:
                    updated_ports.append(cond)

            if name_changed and updated_ports != ports:
                if type == "input":
                    widget = self.input_widget.get_custom_widget()
                    widget.valueChanged.disconnect(self._on_inputs_changed)
                else:
                    widget = self.output_widget.get_custom_widget()
                    widget.valueChanged.disconnect(self._on_outputs_changed)

                self.set_property(f"{type}_ports", updated_ports)

                if type == "input":
                    widget.valueChanged.connect(self._on_inputs_changed)
                else:
                    widget.valueChanged.connect(self._on_outputs_changed)

        def save_to_component(self):
            parent_window.parent.develop_page.reset_edit()
            parent_window.parent.develop_page.code_editor.set_code(
                self.format_code(add_import=False)
            )
            parent_window.parent.switchTo(parent_window.parent.develop_page)

        def format_code(self, add_import=True):
            self.object_io = False
            user_code = self.get_property("code") or ""
            requirements = self.get_property("requirements") or ""
            type_dict = {item.value: item.name for item in ArgumentType}

            input_defs = []
            for port, port_def in zip(
                self.input_ports(), self.get_property("input_ports")
            ):
                name = port.name()
                if type_dict[port_def["type"]] == "OBJECT":
                    self.object_io = True
                input_defs.append(
                    f'        PortDefinition(name="{name}", label="{name}", type=ArgumentType.{type_dict[port_def["type"]]}, connection=ConnectionType.SINGLE),'
                )

            output_defs = []
            for port, port_def in zip(
                self.output_ports(), self.get_property("output_ports")
            ):
                name = port.name()
                if type_dict[port_def["type"]] == "OBJECT":
                    self.object_io = True
                output_defs.append(
                    f'        PortDefinition(name="{name}", label="{name}", type=ArgumentType.{type_dict[port_def["type"]]}),'
                )

            if "def run(" not in user_code:
                raise ValueError(
                    "代码必须包含 def run(self, params, inputs=None): 函数"
                )
            indented_user_code = "\n".join(
                "    " + line if line.strip() else line
                for line in user_code.splitlines()
            )
            temp_component_code = _TEMP_COMPONENT_TEMPLATE.format(
                import_code=COMPONENT_IMPORT_CODE if add_import else "",
                requirements=requirements,
                inputs_list="\n".join(input_defs) if input_defs else "",
                outputs_list="\n".join(output_defs) if output_defs else "",
                properties_dict="",
                user_run_code=indented_user_code.strip(),
            )
            return temp_component_code

        def get_component_code(self) -> str:
            return self.format_code()

        def get_class_name(self) -> str:
            return "DynamicComponent"

        def init_logger(self):
            from app.utils.node_logger import NodeLogHandler

            self.log_capture = NodeLogHandler(
                self.persistent_id,
                self._log_message,
                self.CACHE_PATH,
                use_file_logging=True,
            )

        def __del__(self):
            if hasattr(self, "_input_sync_timer"):
                self._input_sync_timer.stop()
            if hasattr(self, "_output_sync_timer"):
                self._output_sync_timer.stop()
            if hasattr(self, "_property_update_timer"):
                self._property_update_timer.stop()

    return DynamicCodeNode


def get_dynamic_component_class(node):
    """动态创建组件类用于执行"""
    from app.components.base import resource_path
    from pathlib import Path
    import importlib.util

    code = node.format_code(add_import=True)

    base_path = Path(resource_path("app/components/base.py"))

    # 预加载 base_module 以避免 __file__ 路径问题
    spec = importlib.util.spec_from_file_location("base", str(base_path))
    base_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base_module)

    # 更简单的方案：直接在命名空间中提供所需的类
    local_namespace = {
        "__file__": str(base_path),
        "__name__": "DynamicComponent",
        "__path__": [str(base_path.parent)],
    }

    # 将 COMPONENT_IMPORT_CODE 替换为直接导入
    import_code = """
import importlib.util
from pathlib import Path

# 直接使用预加载的 base_module
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType
"""

    # 移除原始代码中的 COMPONENT_IMPORT_CODE 部分
    code = code.replace(COMPONENT_IMPORT_CODE, import_code)

    # 添加 base_module 到命名空间
    local_namespace["base_module"] = base_module

    exec(code, local_namespace)

    return local_namespace.get("DynamicComponent", None)
