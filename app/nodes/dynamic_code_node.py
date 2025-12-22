import os
import pickle
import re
import shutil
import time
import uuid
from pathlib import Path

from NodeGraphQt import BaseNode
from PyQt5 import QtCore

from app.components.base import PropertyType, GlobalVariableContext, ArgumentType
from app.nodes.base_node import BasicNodeWithGlobalProperty, CustomBaseNode
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.utils import resource_path, draw_special_outputport, canvas_file_dump_path, _safe_load_pickle
from app.widgets.node_widget.code_editor_widget import CodeEditorWidgetWrapper
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper
from app.templates.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from .status_node import StatusNode
from app.templates.glue_code_templates import GLUE_CODE_TEMPLATES
from app.widgets.node_widget.combobox_widget import ComboBoxWidgetWrapper

# 在 app/components 下创建 .temp 目录（隐藏目录）
TEMP_COMPONENTS_DIR = Path(__file__).parent.parent / "components" / ".temp"
TEMP_COMPONENTS_DIR.mkdir(exist_ok=True)
PERSISTENT_TEMP_ROOT = (canvas_file_dump_path() / "run_scripts").resolve()
PERSISTENT_TEMP_ROOT.mkdir(exist_ok=True, parents=True)


_TEMP_COMPONENT_TEMPLATE = '''{import_code}class DynamicComponent(BaseComponent):
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


def create_dynamic_code_node(parent_window=None):

    class DynamicCodeNode(CustomBaseNode, StatusNode, BasicNodeWithGlobalProperty):
        __identifier__ = 'dynamic'
        NODE_NAME = "代码编辑"
        FULL_PATH = f"代码执行/{NODE_NAME}"
        FILE_PATH = "DYNAMIC_CODE"  # 不需要真实文件路径

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self._view.set_align("center")
            self.set_icon(resource_path("icons/代码执行.svg"))
            self.model.port_deletion_allowed = True

            # 定时器：分离 input / output / property update
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
            if self.parent_window and hasattr(self.parent_window, 'property_panel'):
                self.parent_window.property_panel.update_properties(self)

        def _init_properties(self):
            """初始化条件列表和 else 开关（只创建 widget，不绑定逻辑）"""
            input_schema = {
                "name": {
                    "type": PropertyType.TEXT.value,
                    "default": "input{{id}}",
                    "label": "输入端口名称",
                },"type": {
                    "type": PropertyType.CHOICE.value,
                    "default": PropertyType.TEXT.value,
                    "label": "输入端口类型",
                    "choices": [item.value for item in ArgumentType]
                },
                "var": {
                    "type": PropertyType.VARIABLE.value,
                    "default": "全局变量",
                    "label": "默认变量选择",
                }
            }
            processed_schema = {}
            for field_name, field_def in input_schema.items():
                field_type_enum = PropertyType(field_def["type"])
                processed_schema[field_name] = {
                    "type": field_type_enum.name,
                    "label": field_def.get("label", field_name),
                    "choices": field_def.get("choices", []),
                    "default": field_def.get("default", "")
                }
            self.input_widget = DynamicFormWidgetWrapper(
                parent=self.view,
                name="input_ports",
                label="输入端口定义",
                schema=processed_schema,
                window=parent_window,
                z_value=4
            )
            self.add_custom_widget(self.input_widget, tab='Properties')

            output_schema = {
                "name": {
                    "type": PropertyType.TEXT.value,
                    "default": "output{{id}}",
                    "label": "输出端口名称",
                }, "type": {
                    "type": PropertyType.CHOICE.value,
                    "default": PropertyType.TEXT.value,
                    "label": "输入端口类型",
                    "choices": [item.value for item in ArgumentType]
                },
            }
            processed_schema = {}
            for field_name, field_def in output_schema.items():
                field_type_enum = PropertyType(field_def["type"])
                processed_schema[field_name] = {
                    "type": field_type_enum.name,
                    "label": field_def.get("label", field_name),
                    "choices": field_def.get("choices", []),
                    "default": field_def.get("default", "")
                }
            self.output_widget = DynamicFormWidgetWrapper(
                parent=self.view,
                name="output_ports",
                label="输出端口定义",
                schema=processed_schema,
                window=parent_window,
                z_value=3
            )
            self.add_custom_widget(self.output_widget, tab='Properties')
            template_items = [f"{key}:{info['name']}" for key, info in GLUE_CODE_TEMPLATES.items()]
            self.glue_templates_widget = ComboBoxWidgetWrapper(
                parent=self.view,
                name="glue_code_template",
                label="胶水代码模板",
                items=template_items,
                z_value=2
            )
            self.add_custom_widget(self.glue_templates_widget, tab='Properties')

            code_widget = CodeEditorWidgetWrapper(
                parent=self.view,
                name="code",
                label="执行代码",
                default=GLUE_CODE_TEMPLATES.get("default").get("code"),
                window=parent_window
            )
            self.code_editor = code_widget.get_custom_widget()
            self.add_custom_widget(code_widget, tab='Properties')

            glue_combo = self.glue_templates_widget.get_custom_widget()
            glue_combo.combobox.currentIndexChanged.connect(self._on_glue_template_changed)

        def _on_glue_template_changed(self, index):
            """当下拉选择胶水模板时，自动更新代码编辑器内容"""
            combo = self.glue_templates_widget.get_custom_widget()
            current_text = combo.combobox.currentText()
            if not current_text:
                return

            # 解析 key（格式为 "key:name"）
            try:
                template_key = current_text.split(":", 1)[0]
                template_code = GLUE_CODE_TEMPLATES[template_key]["code"]
            except (IndexError, KeyError):
                return

            # 更新 code 编辑器
            self.code_editor.set_code(template_code)

        def _sanitize_port_name(self, name: str) -> str:
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
            name_mapping = {}  # {原始索引: 最终端口名}
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
                name_mapping[i] = port_name

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
            if self.selected():
                self._property_update_timer.start(500)

        def _sync_outputs_ports(self):
            """同步输出端口：严格按表单顺序重建，仅当端口名未变时恢复连线"""
            output_configs = self.get_property("output_ports") or []

            # 1. 按顺序生成期望的输出端口名（自动去重）
            expected_names = []
            used_names = set()
            name_mapping = {}  # {原始索引: 最终端口名}
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
                node_name = re.sub(r'\s+', '_', self.name())
                if f"{node_name}__{name}" in parent_window.global_variables.node_vars:
                    self.add_output(name, painter_func=draw_special_outputport)
                else:
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

            if self.selected():
                self._property_update_timer.start(500)

        def _sync_names_to_form(self, ports, name_mapping, type="input"):
            """将生成的端口名称同步回表单"""
            updated_ports = []
            name_changed = False

            for i, cond in enumerate(ports):
                original_name = cond.get("name", type).strip() or type
                generated_name = name_mapping.get(i, type)

                # 检查是否需要更新名称
                # 如果原始名称不符合规范（如包含特殊字符、以数字开头等）或与生成的名称不同，则更新
                sanitized_original = self._sanitize_port_name(original_name)
                needs_update = sanitized_original != generated_name

                if needs_update:
                    new_cond = cond.copy()
                    new_cond["name"] = generated_name
                    updated_ports.append(new_cond)
                    name_changed = True
                else:
                    updated_ports.append(cond)

            # 如果有名称变化，更新表单值（避免无限循环）
            if name_changed and updated_ports != ports:
                # 临时断开信号连接以避免循环触发
                if type == "input":
                    widget = self.input_widget.get_custom_widget()
                    widget.valueChanged.disconnect(self._on_inputs_changed)
                else:
                    widget = self.output_widget.get_custom_widget()
                    widget.valueChanged.disconnect(self._on_outputs_changed)
                # 更新表单值
                self.set_property(f"{type}_ports", updated_ports)

                # 重新连接信号
                if type == "input":
                    widget.valueChanged.connect(self._on_inputs_changed)
                else:
                    widget.valueChanged.connect(self._on_outputs_changed)

        def save_to_component(self):
            parent_window.parent.develop_page.code_editor.set_code(self.format_code(add_import=False))
            parent_window.parent.switchTo(parent_window.parent.develop_page)

        def format_code(self, add_import=True):
            # === 1. 收集参数（不变）===
            user_code = self.get_property("code") or ""
            requirements = self.get_property("requirements") or ""
            type_dict = {item.value: item.name for item in ArgumentType}

            input_defs = []
            for port, port_def in zip(self.input_ports(), self.get_property("input_ports")):
                name = port.name()
                input_defs.append(
                    f'        PortDefinition(name="{name}", label="{name}", type=ArgumentType.{type_dict[port_def["type"]]}, connection=ConnectionType.SINGLE),'
                )

            output_defs = []
            for port, port_def in zip(self.output_ports(), self.get_property("output_ports")):
                name = port.name()
                output_defs.append(
                    f'        PortDefinition(name="{name}", label="{name}", type=ArgumentType.{type_dict[port_def["type"]]}),')

            # === 2. 拼接临时组件代码（不变）===
            from app.components.base import COMPONENT_IMPORT_CODE

            if "def run(" not in user_code:
                raise ValueError("代码必须包含 def run(self, params, inputs=None): 函数")
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
                user_run_code=indented_user_code.strip()
            )
            return temp_component_code

        # === 关键：重写 execute_sync，使用动态代码模板 ===
        def execute_sync(self, comp_obj, kernel_manager=None, python_executable=None, check_cancel=None):
            try:
                self.init_logger()
                temp_component_name = f"dynamic_{uuid.uuid4().hex}.py"
                temp_component_path = TEMP_COMPONENTS_DIR / temp_component_name
                run_id = f"run_{self.persistent_id}"
                run_dir = PERSISTENT_TEMP_ROOT / run_id
                shutil.rmtree(run_dir, ignore_errors=True)
                run_dir.mkdir(parents=True, exist_ok=True)
                temp_script_path = run_dir / "exec_script.py"
                params_path = run_dir / "params.pkl"
                result_path = run_dir / "result.pkl"
                error_path = run_dir / "error.pkl"
                log_file_path = self.log_capture.get_log_file_path()
                if python_executable is None:
                    raise Exception("未指定Python执行环境。")

                temp_component_code = self.format_code()
                # 保存组件代码
                with open(temp_component_path, 'w', encoding='utf-8') as f:
                    f.write(temp_component_code)
                # === 3. 收集 inputs / params / global_variable（不变）===
                global_variable = self.global_variable
                gv = GlobalVariableContext()
                gv.deserialize(global_variable)

                inputs_raw = {}
                for i, input_port in enumerate(self.input_ports()):
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
                    else:
                        inputs_raw[port_name] = gv.get(self.get_property("input_ports")[i]["var"])

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
                params = {}  # 动态节点无额外参数

                # === 4. 准备临时文件（不变）===
                # 保存执行参数（IPython 和 subprocess 都需要）
                with open(params_path, 'wb') as f:
                    pickle.dump((params, inputs, global_variable), f)

                # 生成执行脚本（使用原始 subprocess 模板，不需双模式）
                script_content = _EXECUTION_SCRIPT_TEMPLATE.format(
                    class_name="DynamicComponent",
                    file_path=temp_component_path,
                    params_path=params_path,
                    result_path=result_path,
                    error_path=error_path,
                    log_file_path=log_file_path,
                    node_id=self.persistent_id
                )
                with open(temp_script_path, 'w', encoding='utf-8') as f:
                    f.write(script_content)
                # === 5. 执行 ===
                if kernel_manager is not None:
                    return self._execute_dynamic_via_ipython(
                        temp_script_path, result_path, error_path, log_file_path,
                        check_cancel, kernel_manager, temp_component_path
                    )
                else:
                    return self._execute_dynamic_via_subprocess(
                        python_executable, temp_script_path, result_path, error_path,
                        log_file_path, check_cancel, temp_component_path
                    )
            finally:
                # 清理临时组件
                try:
                    temp_component_path.unlink(missing_ok=True)
                    params_path.unlink(missing_ok=True)
                    temp_script_path.unlink(missing_ok=True)
                except Exception:
                    pass


        def _execute_dynamic_via_ipython(
                self, temp_script_path, result_path, error_path, log_file_path,
                check_cancel, kernel_manager, temp_component_path
        ):
            run_code = f'%reset -f'
            kernel_manager.execute_code(run_code, hidden=True)
            # 执行脚本（无需注入变量，统一走文件）
            run_code = f'%run -i "{temp_script_path.as_posix()}"'
            kernel_manager.execute_code(run_code, hidden=False)

            # 轮询结果（与 subprocess 一致）
            start_time = time.time()
            timeout = 300
            last_log_pos = os.path.getsize(log_file_path) if os.path.exists(log_file_path) else 0

            while not (result_path.exists() or error_path.exists()):
                if check_cancel and check_cancel():
                    raise Exception("执行被用户取消")
                if time.time() - start_time > timeout:
                    raise Exception("❌ 节点执行超时（5分钟）")

                try:
                    if os.path.exists(log_file_path):
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                            lf.seek(last_log_pos)
                            new_content = lf.read()
                            if new_content:
                                self._log_message(self.persistent_id, new_content)
                                last_log_pos = lf.tell()
                except Exception:
                    pass
                time.sleep(0.1)

            # 读取剩余日志
            try:
                if os.path.exists(log_file_path):
                    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                        lf.seek(last_log_pos)
                        tail_content = lf.read()
                        if tail_content:
                            self._log_message(self.persistent_id, tail_content)
            except Exception:
                pass

            # 清理临时组件文件
            try:
                if temp_component_path.exists():
                    temp_component_path.unlink()
            except Exception:
                pass
            # 处理结果
            if result_path.exists():
                output = _safe_load_pickle(result_path)
                for port in self.output_ports():
                    if port.name() in output:
                        self.set_output_value(port.name(), output[port.name()])
                return output
            elif error_path.exists():
                with open(error_path, 'rb') as f:
                    error_info = pickle.load(f)
                error_msg = f"❌ 节点执行失败: {error_info['traceback']}"
                self._log_message(self.persistent_id, error_msg)
                raise Exception(error_info['error'])
            else:
                raise Exception("未知错误：未生成结果或错误文件")

        def _execute_dynamic_via_subprocess(
                self, python_executable, temp_script_path, result_path, error_path,
                log_file_path, check_cancel, temp_component_path
        ):
            import subprocess, platform, time, os, pickle

            # 检查取消
            if check_cancel and check_cancel():
                raise Exception("执行已被用户取消")

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

            start_time = time.time()
            timeout = 300
            cancelled = False
            last_log_pos = os.path.getsize(log_file_path) if os.path.exists(log_file_path) else 0

            while proc.poll() is None:
                if check_cancel and check_cancel():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    cancelled = True
                    break

                if time.time() - start_time > timeout:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    self._log_message(self.persistent_id, "❌ 节点执行超时（5分钟）")
                    raise Exception("❌ 节点执行超时（5分钟）")

                try:
                    if os.path.exists(log_file_path):
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                            lf.seek(last_log_pos)
                            new_content = lf.read()
                            if new_content:
                                self._log_message(self.persistent_id, new_content)
                                last_log_pos = lf.tell()
                except Exception:
                    pass
                time.sleep(0.1)

            if cancelled:
                self._log_message(self.persistent_id, "执行已被用户取消")
                raise Exception("执行已被用户取消")

            try:
                if os.path.exists(log_file_path):
                    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                        lf.seek(last_log_pos)
                        tail_content = lf.read()
                        if tail_content:
                            self._log_message(self.persistent_id, tail_content)
            except Exception:
                pass

            if result_path.exists():
                with open(result_path, 'rb') as f:
                    output = pickle.load(f)
                for port in self.output_ports():
                    if port.name() in output:
                        self.set_output_value(port.name(), output[port.name()])
                return output
            elif error_path.exists():
                with open(error_path, 'rb') as f:
                    error_info = pickle.load(f)
                error_msg = f"❌ 节点执行失败: {error_info['traceback']}"
                self._log_message(self.persistent_id, error_msg)
                raise Exception(error_info['error'])
            else:
                raise Exception("未知错误")

        def __del__(self):
            # 注意：__del__ 在 PyQt 中不一定可靠，但可加强保障
            if hasattr(self, '_input_sync_timer'):
                self._input_sync_timer.stop()
            if hasattr(self, '_output_sync_timer'):
                self._output_sync_timer.stop()
            if hasattr(self, '_property_update_timer'):
                self._property_update_timer.stop()

    return DynamicCodeNode
