import re

from NodeGraphQt import BaseNode
from PyQt5 import QtCore

from app.components.base import PropertyType
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import resource_path
from app.widgets.node_widget.code_editor_widget import CodeEditorWidgetWrapper
from app.widgets.node_widget.custom_node_item import CustomNodeItem
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper


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

        def get_logs(self): return self._node_logs or "无日志可用。"
        def set_output_value(self, port, val): self._output_values[port] = val
        def get_output_value(self, port): return self._output_values.get(port)
        def on_run_complete(self, output): self._output_values = output

        # === 关键：重写 execute_sync，使用动态代码模板 ===
        def execute_sync(self, comp_obj, python_executable=None, check_cancel=None):
            params = {
                "code": self.get_property("code"),
                "requirements": self.get_property("requirements") or "",
            }

    return DynamicCodeNode