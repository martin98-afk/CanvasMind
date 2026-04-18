# -*- coding: utf-8 -*-
import re
from pathlib import Path

from PyQt5 import QtCore
from loguru import logger
from qfluentwidgets import MessageBox

from app.components.base import (
    ArgumentType,
    PropertyType,
    ConnectionType,
    resource_path,
    COMPONENT_IMPORT_CODE,
)
from app.nodes.base.executable_node import ExecutableNode
from app.scan_components import ComponentScanner
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.custom_nodegraphqt.custom_port_item import (
    draw_special_outputport,
    draw_square_port,
)
from app.widgets.node_widget.propeprty_widgets.checkbox_widget import (
    CheckBoxWidgetWrapper,
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
from app.widgets.node_widget.propeprty_widgets.dynamic_tree_widget import (
    DynamicTreeWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.file_select_widget import (
    FileSelectWrapper,
)
from app.widgets.node_widget.propeprty_widgets.longtext_dialog import (
    LongTextWidgetWrapper,
)
from app.widgets.node_widget.propeprty_widgets.range_widget import RangeWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.spinbox_widget import NumberWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.text_edit_widget import TextWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.variable_combo_widget import (
    VarComboBoxWidgetWrapper,
)


def create_node_class(full_path, file_path, parent_window=None):
    """返回一个高性能、支持独立环境执行的动态节点类"""

    class DynamicNode(CustomBaseNode, ExecutableNode):
        __identifier__ = "dynamic"
        NODE_NAME = parent_window.component_map[full_path].name
        FULL_PATH = full_path
        FILE_PATH = file_path
        CACHE_PATH = parent_window.file_path.parent.resolve()
        object_io = False
        _debug_enabled = False
        _debug_widget = None
        _debug_code_content = ""

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self._set_icon()
            self.CACHE_PATH.mkdir(exist_ok=True, parents=True)
            self.set_property("_version", "latest")
            comp_class = ComponentScanner().get_component_by_uuid(self.uuid)
            self.view.exec_mode_signal.connect(self._clear_ipython_memory_context)
            self._generate_parms_widget()
            port_infos = comp_class.get_inputs()
            port_sub_types = comp_class.get_input_sub_types()
            for (port_name, label, connection, port_type, description), sub_type in zip(
                port_infos, port_sub_types
            ):
                if port_type == ArgumentType.OBJECT:
                    self.object_io = True
                if connection == ConnectionType.SINGLE:
                    _, port = self.add_input(port_name)
                else:
                    _, port = self.add_input(
                        port_name, True, painter_func=draw_square_port
                    )
                port_description = f"名称: {label}\n类型: {port_type.value}"
                if sub_type:
                    port_description += f"\n类型标识: {sub_type}"
                if description:
                    port_description += f"\n{description}"
                port.setToolTip(port_description)
            QtCore.QTimer.singleShot(0, self.build_outputs)

            self.view.debug_signal.connect(self._toggle_debug_mode)
            self.view.rename_signal.connect(parent_window.rename_node_vars)

        def _set_icon(self):
            """自动寻找扩展文件中的图标"""
            extension_path = Path(resource_path("app/component_extensions")) / self.uuid
            for icon_path in (extension_path / "assets/component_icon").glob("*"):
                if icon_path.is_file() and icon_path.suffix in [
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".svg",
                    "ico",
                ]:
                    self.set_icon(str(icon_path))
                    return

        @property
        def comp_cls(self):
            return ComponentScanner().get_component_by_uuid(self.uuid)

        @property
        def description(self):
            return ComponentScanner().get_component_by_uuid(self.uuid).description

        @property
        def uuid(self):
            return self.model.type_.split("StatusDynamicNode_")[1]

        @property
        def port_info(self):
            port_info = "输入端口: "
            port_infos = self.comp_cls.get_inputs()
            for port_name, label, connection, port_type, description in port_infos:
                port_info += f"{port_name} ({label})({port_type.value})({connection.value}) {description};"
            port_info += "\n输出端口: "
            port_infos = self.comp_cls.get_outputs()
            for port_name, label, port_type, description in port_infos:
                port_info += f"{port_name} ({label})({port_type.value}) {description};"
            return port_info

        def build_outputs(self):
            port_infos = self.comp_cls.get_outputs()
            port_sub_types = self.comp_cls.get_output_sub_types()
            for (port_name, label, port_type, description), sub_type in zip(
                port_infos, port_sub_types
            ):
                if port_type == ArgumentType.OBJECT:
                    self.object_io = True
                self.delete_output(port_name)
                name = re.sub(r"\s+", "_", self.name())
                if f"{name}__{port_name}" in parent_window.global_variables.node_vars:
                    _, port = self.add_output(
                        port_name, painter_func=draw_special_outputport
                    )
                else:
                    _, port = self.add_output(port_name)
                port_description = f"名称: {label}\n类型: {port_type.value}"
                if sub_type:
                    port_description += f"\n类型标识: {sub_type}"
                if description:
                    port_description += f"\n{description}"
                port.setToolTip(port_description)

        def refresh_node_outports(self):
            self.set_port_deletion_allowed(True)
            expected_names = [
                port_name
                for port_name, _, _, _ in ComponentScanner()
                .get_component_by_uuid(self.uuid)
                .get_outputs()
            ]
            current_connections = {}
            for port in self.output_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)
                port.clear_connections(push_undo=False, emit_signal=False)
            for port_name in expected_names:
                self.delete_output(port_name)
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
            self.set_port_deletion_allowed(False)

        def _toggle_debug_mode(self):
            self.graph.clear_selection()
            self.set_selected(True)
            if not self._debug_enabled:
                self._debug_enabled = True
                self._enable_debug_mode()
                QtCore.QTimer.singleShot(
                    0, lambda: self.graph.viewer().zoom_to_nodes([self.view])
                )
                parent_window.side_dock_area.switch_to("模型日志")
            else:
                self._debug_enabled = False
                self._disable_debug_mode()

        def _enable_debug_mode(self):
            self.current_code = self.get_current_code()
            if "debug_code" in self.model._custom_prop:
                self.model._custom_prop.pop("debug_code")
            self._debug_widget = CodeEditorWidgetWrapper(
                parent=self.view,
                name="debug_code",
                label="调试代码编辑器",
                default=self.current_code,
                window=parent_window,
                width=700,
                height=400,
            )
            self._debug_widget.valueChanged.connect(self._save_debug_code)
            self.view.set_proxy_mode(False)
            self.add_custom_widget(self._debug_widget, tab="Debug")
            logger.info(f"节点 {self.NODE_NAME} ({self.id}) 启用调试模式。")

        def _disable_debug_mode(self):
            if self._debug_widget is not None:
                current_editor_code = self._debug_widget.get_value()
                original_code = self.get_current_code()
                if current_editor_code != original_code:
                    w = MessageBox(
                        "保存修改",
                        "调试代码已修改，是否保存到原组件？",
                        self.parent_window,
                    )
                    w.yesButton.setText("保存")
                    w.cancelButton.setText("不保存")
                    if w.exec():
                        if self.parent_window and hasattr(
                            self.parent_window, "component_code_changed"
                        ):
                            self.parent_window.component_code_changed.emit(
                                self.FULL_PATH, current_editor_code
                            )
                try:
                    self._debug_widget.valueChanged.disconnect(self._save_debug_code)
                except TypeError:
                    pass
                self.remove_property("debug_code")
                self.view.remove_widget(self._debug_widget)
                self.view.draw_node()
                self._debug_widget = None
                logger.info(f"节点 {self.NODE_NAME} ({self.id}) 禁用调试模式。")

        def _save_debug_code(self, code_text):
            """保存调试编辑器中的代码到本地文件"""
            if code_text != self.current_code:
                self.current_code = code_text

        def get_current_code(self):
            current_version = self.get_property("_version")
            if current_version == "latest":
                with open(ComponentScanner().get_component_by_uuid(self.uuid)._source_file, "r", encoding="utf-8") as f:
                    current_code = f.read()
            else:
                current_code = None
                for version_file in (
                    ComponentScanner().get_component_by_uuid(self.uuid)._history_file
                ):
                    if version_file["version"] == current_version:
                        current_code = COMPONENT_IMPORT_CODE + version_file["code"]
                        break
                if current_code is None:
                    raise Exception(
                        "Cannot find component code for version: {}".format(
                            current_version
                        )
                    )
            return current_code

        def get_component_code(self) -> str:
            """返回组件代码"""
            return self.current_code if self._debug_enabled else self.get_current_code()

        def get_class_name(self) -> str:
            """返回组件类名"""
            return self.comp_cls.__name__

        def _generate_parms_widget(self):
            """生成节点属性配置控件"""
            custom_widgets_num = (
                len(
                    ComponentScanner().get_component_by_uuid(self.uuid).get_properties()
                )
                + 10
            )
            for i, (prop_name, prop_def) in enumerate(
                ComponentScanner()
                .get_component_by_uuid(self.uuid)
                .get_properties()
                .items()
            ):
                prop_type = prop_def.get("type", PropertyType.TEXT)
                default = prop_def.get("default", "")
                label = prop_def.get("label", prop_name)
                description = prop_def.get("description", "")
                if prop_type == PropertyType.BOOL:
                    widget = CheckBoxWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        text=label,
                        state=default,
                        window=parent_window,
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="properties")
                elif prop_type in (PropertyType.INT, PropertyType.FLOAT):
                    widget = NumberWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        default=default,
                        window=parent_window,
                        type=prop_type.name.lower(),
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="properties")
                elif prop_type == PropertyType.CHOICE:
                    choices = prop_def.get("choices", [])
                    if choices:
                        widget = ComboBoxWidgetWrapper(
                            parent=self.view,
                            name=prop_name,
                            label=label,
                            items=choices,
                            window=parent_window,
                            z_value=custom_widgets_num - i,
                        )
                        if description:
                            widget.setToolTip(description)
                        self.add_custom_widget(widget, tab="properties")
                        self.set_property(
                            prop_name, default if default in choices else choices[0]
                        )
                elif prop_type == PropertyType.LONGTEXT:
                    widget = LongTextWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        default=default,
                        window=parent_window,
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="Properties")
                elif prop_type == PropertyType.RANGE:
                    min_val = prop_def.get("min", 0)
                    max_val = prop_def.get("max", 100)
                    step_val = prop_def.get("step", 1)
                    default_val = prop_def.get("default", min_val)
                    widget = RangeWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        min_val=min_val,
                        max_val=max_val,
                        step=step_val,
                        default=default_val,
                        window=parent_window,
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="Properties")
                elif prop_type == PropertyType.DYNAMICTREE:
                    widget = DynamicTreeWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        window=parent_window,
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="properties")
                elif prop_type == PropertyType.DYNAMICFORM:
                    raw_schema = prop_def.get("schema", {})
                    processed_schema = {}
                    for field_name, field_def in raw_schema.items():
                        field_type_enum = PropertyType(field_def["type"])
                        processed_schema[field_name] = {
                            "type": field_type_enum.name,
                            "name": field_name,
                            "label": field_def.get("label", field_name),
                            "choices": field_def.get("choices", []),
                            "default": field_def.get("default", ""),
                            "min": field_def.get("min", 0),
                            "max": field_def.get("max", 100),
                            "step": field_def.get("step", 1),
                        }
                    widget = DynamicFormWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        schema=processed_schema,
                        window=parent_window,
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="Properties")
                elif prop_type == PropertyType.VARIABLE:
                    default_val = prop_def.get("default")
                    widget = VarComboBoxWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        var_type=default_val or "全局变量",
                        main_window=parent_window,
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="properties")
                    self.set_property(prop_name, "无")
                elif prop_type == PropertyType.FILE:
                    widget = FileSelectWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        default=default,
                        window=parent_window,
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="Properties")
                else:
                    widget = TextWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        type=prop_type,
                        default=str(default),
                        window=parent_window,
                        z_value=custom_widgets_num - i,
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="Properties")

        def remove_property(self, name):
            self.model._custom_prop.pop(name)

        def set_version(self, version):
            self.model.set_property("_version", version)

        def init_logger(self):
            from app.utils.node_logger import NodeLogHandler

            self.log_capture = NodeLogHandler(
                self.persistent_id,
                self._log_message,
                self.CACHE_PATH,
                use_file_logging=True,
            )

        def get_logical_inputs(self) -> list:
            reads = set()
            pattern = re.compile(r"\$node_vars\.([a-zA-Z0-9_]+)\$")
            for name, value in self.model.custom_properties.items():
                if isinstance(value, str) and value.startswith("node_vars."):
                    reads.add(value)
                if isinstance(value, str):
                    matches = pattern.findall(value)
                    for m in matches:
                        reads.add(m)
            return list(reads)

    return DynamicNode
