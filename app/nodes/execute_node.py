# -*- coding: utf-8 -*-
import os
import pickle
import platform
import re
import shutil
import subprocess
import time

from PyQt5 import QtCore
from loguru import logger
from qfluentwidgets import MessageBox

# --- 其他原有导入 ---
from app.components.base import ArgumentType, PropertyType, ConnectionType, GlobalVariableContext, \
    COMPONENT_IMPORT_CODE, resource_path
from app.nodes.status_node import StatusNode
from app.scan_components import ComponentScanner
from app.scheduler.expression_engine import ExpressionEngine
from app.templates.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import draw_square_port, draw_special_outputport, \
    _safe_load_pickle, kill_proc_tree, serialize_for_json  # 假设 resource_path 也在 utils
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.checkbox_widget import CheckBoxWidgetWrapper
# 导入代码编辑器组件
from app.widgets.node_widget.code_editor_widget import CodeEditorWidgetWrapper
from app.widgets.node_widget.combobox_widget import ComboBoxWidgetWrapper
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper
from app.widgets.node_widget.longtext_dialog import LongTextWidgetWrapper
from app.widgets.node_widget.range_widget import RangeWidgetWrapper
from app.widgets.node_widget.text_edit_widget import TextWidgetWrapper
from app.widgets.node_widget.variable_combo_widget import VarComboBoxWidgetWrapper


def create_node_class(full_path, file_path, parent_window=None):
    """返回一个高性能、支持独立环境执行的动态节点类"""

    class DynamicNode(CustomBaseNode, StatusNode):
        __identifier__ = 'dynamic'
        NODE_NAME = parent_window.component_map[full_path].name
        FULL_PATH = full_path
        FILE_PATH = file_path  # 现在 FILE_PATH 是真实的组件文件路径
        CACHE_PATH = parent_window.file_path.parent.resolve()

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self.CACHE_PATH.mkdir(exist_ok=True, parents=True)
            self.set_property("version", "latest")
            if hasattr(ComponentScanner().get_component_by_uuid(self.uuid), "icon"):
                self.set_icon(ComponentScanner().get_component_by_uuid(self.uuid).icon)
            self.view.set_align("center")
            # 重命名节点自动同步全局变量名
            self.view.rename_signal.rename.connect(parent_window.rename_node_vars)
            # --- 调试模式新增 ---
            self._debug_enabled = False
            self._debug_widget = None
            self._debug_code_content = ""
            # --- /调试模式新增 ---

            # === 动态生成属性 ===
            self._generate_parms_widget()
            for port_name, label, connection in ComponentScanner().get_component_by_uuid(self.uuid).get_inputs():
                if connection == ConnectionType.SINGLE:
                    self.add_input(port_name)
                else:
                    self.add_input(port_name, True, painter_func=draw_square_port)
            QtCore.QTimer.singleShot(0, self.build_outputs)
            
        @property
        def uuid(self):
            return self.model.type_.split("StatusDynamicNode_")[1]

        def build_outputs(self):
            for port_name, label in ComponentScanner().get_component_by_uuid(self.uuid).get_outputs():
                self.delete_output(port_name)
                name = re.sub(r'\s+', '_', self.name())
                if f"{name}__{port_name}" in parent_window.global_variables.node_vars:
                    self.add_output(port_name, painter_func=draw_special_outputport)
                else:
                    self.add_output(port_name)

        def refresh_node_outports(self):
            self.set_port_deletion_allowed(True)
            # 2. 记录当前所有输出端口的连线状态：{port_name: [connected_downstream_ports]}
            expected_names = [
                port_name for port_name, _ in ComponentScanner().get_component_by_uuid(self.uuid).get_outputs()
            ]
            current_connections = {}
            for port in self.output_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)
                port.clear_connections(push_undo=False, emit_signal=False)
            for port_name in expected_names:
                self.delete_output(port_name)

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
            self.set_port_deletion_allowed(False)

        def _toggle_debug_mode(self):
            """调试模式开关回调"""
            if not self._debug_enabled:
                self._debug_enabled = True
                self._enable_debug_mode()
            else:
                self._debug_enabled = False
                self._disable_debug_mode()

        def _enable_debug_mode(self):
            """启用调试模式，添加代码编辑器"""
            self.current_code = self.get_current_code()
            if "debug_code" in self.model._custom_prop:
                self.model._custom_prop.pop("debug_code")
            # 创建代码编辑器控件
            self._debug_widget = CodeEditorWidgetWrapper(
                parent=self.view,
                name="debug_code",
                label="调试代码编辑器",
                default=self.current_code,
                window=parent_window,
                width=700, height=400
            )
            # 连接信号，实现编辑时保存
            self._debug_widget.valueChanged.connect(self._save_debug_code)

            # 添加到节点属性面板
            self.view.set_proxy_mode(False)
            self.add_custom_widget(self._debug_widget, tab='Debug')

            logger.info(f"节点 {self.NODE_NAME} ({self.id}) 启用调试模式。")

        def _disable_debug_mode(self):
            """禁用调试模式，移除代码编辑器，并在代码变更时提示保存（qfluentwidgets 风格）"""
            if self._debug_widget is not None:
                current_editor_code = self._debug_widget.get_value()
                original_code = self.get_current_code()

                if current_editor_code != original_code:
                    # 创建对话框内容
                    title = "保存修改"
                    content = "调试代码已修改，是否保存到原组件？"

                    # 使用 qfluentwidgets.Dialog
                    w = MessageBox(title, content, self.parent_window)
                    w.yesButton.setText("保存")
                    w.cancelButton.setText("不保存")

                    # 设置按钮样式（可选，qfluentwidgets 默认已适配深色）
                    if w.exec():  # 用户点击“保存”
                        if self.parent_window and hasattr(self.parent_window, 'component_code_changed'):
                            self.parent_window.component_code_changed.emit(self.FULL_PATH, current_editor_code)

                # 清理控件
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

        def _generate_parms_widget(self):
            """生成节点属性配置控件"""
            # 生成其他组件属性控件
            custom_widgets_num = len(ComponentScanner().get_component_by_uuid(self.uuid).get_properties()) + 10
            for i, (prop_name, prop_def) in enumerate(ComponentScanner().get_component_by_uuid(self.uuid).get_properties().items()):
                prop_type = prop_def.get("type", PropertyType.TEXT)
                default = prop_def.get("default", "")
                label = prop_def.get("label", prop_name)
                if prop_type == PropertyType.BOOL:
                    self.add_custom_widget(
                        CheckBoxWidgetWrapper(parent=self.view, name=prop_name, text=label, state=default),
                        tab="properties"
                    )
                elif prop_type == PropertyType.CHOICE:
                    choices = prop_def.get("choices", [])
                    if choices:
                        self.add_custom_widget(
                            ComboBoxWidgetWrapper(
                                parent=self.view, name=prop_name, label=label, items=choices,
                                z_value=custom_widgets_num - i
                            ),
                            tab="properties"
                        )
                        self.set_property(prop_name, default if default in choices else choices[0])
                elif prop_type == PropertyType.LONGTEXT:
                    widget = LongTextWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        default=default,
                        window=parent_window
                    )
                    self.add_custom_widget(widget, tab='Properties')
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
                        default=default_val
                    )
                    self.add_custom_widget(widget, tab='Properties')
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
                            "step": field_def.get("step", 1)
                        }
                    widget = DynamicFormWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        schema=processed_schema,
                        window=parent_window,
                        z_value=custom_widgets_num - i
                    )
                    self.add_custom_widget(widget, tab='Properties')
                elif prop_type == PropertyType.VARIABLE:  # 新增类型
                    default_val = prop_def.get("default")
                    self.add_custom_widget(
                        VarComboBoxWidgetWrapper(
                            parent=self.view,
                            name=prop_name,
                            label=label,
                            var_type=default_val or "全局变量",
                            main_window=parent_window,  # 传入 main_window 引用
                            z_value=custom_widgets_num - i
                        ),
                        tab="properties"
                    )
                    self.set_property(prop_name, "无")
                else:
                    self.add_custom_widget(
                        TextWidgetWrapper(
                            parent=self.view,
                            name=prop_name,
                            label=label,
                            type=prop_type,
                            default=str(default),
                            window=parent_window
                        ), tab='Properties'
                    )

        def remove_property(self, name):
            self.model._custom_prop.pop(name)

        def set_version(self, version):
            self.model.set_property("version", version)

        def get_current_code(self):
            # 获取当前版本的代码
            current_version = self.get_property("version")
            if current_version == "latest":
                with open(self.FILE_PATH, 'r', encoding='utf-8') as f:
                    current_code = f.read()
            else:
                current_code = None
                for version_file in ComponentScanner().get_component_by_uuid(self.uuid)._history_file:
                    if version_file["version"] == current_version:
                        current_code = COMPONENT_IMPORT_CODE + version_file["code"]
                        break
                if current_code is None:
                    raise Exception("Cannot find component code for version: {}".format(current_version))

            return current_code

        def init_logger(self):
            self.log_capture = NodeLogHandler(
                self.persistent_id, self._log_message, self.CACHE_PATH, use_file_logging=True
            )

        def execute_sync(self, comp_obj, kernel_manager=None, python_executable=None, check_cancel=None, global_variable=None):
            """
            在独立Python环境中执行组件
            :param check_cancel: 可选回调函数，返回 True 表示应取消执行
            """
            self.clear_output_value()
            if not hasattr(self, "log_capture"):
                self.init_logger()
            if python_executable is None:
                raise Exception("未指定Python执行环境。")

            # === 收集参数 ===
            params = serialize_for_json(self.model._custom_prop)
            # === 组件参数 ===
            properties = comp_obj.get_properties()
            for prop_name, prop_def in properties.items():
                prop_type = prop_def.get("type", PropertyType.TEXT)
                default = prop_def.get("default", "")
                if prop_type == PropertyType.DYNAMICFORM:
                    widget = self.get_widget(prop_name)
                    params[prop_name] = widget.get_value() if widget else (default or [])
                else:
                    params[prop_name] = self.get_property(prop_name) if self.has_property(prop_name) else default

            # === 全局变量 创建表达式引擎并求值 ===
            gv = GlobalVariableContext()
            gv.deserialize(global_variable)
            # === 收集 inputs_raw ===
            inputs_raw = {}
            input_vars = {}
            for input_port in self.input_ports():
                port_name = input_port.name()
                connected = input_port.connected_ports()
                if connected:
                    if input_port.model.multi_connection:
                        inputs_raw[port_name] = [
                                upstream.node()._output_values.get(upstream.name()) for upstream in connected
                            ]
                        safe_key = f"input_{port_name}"
                        input_vars[safe_key] = inputs_raw[port_name]
                        for upstream in connected:
                            safe_name = upstream.node().name().replace(" ", "_")
                            safe_key = f"input_{safe_name}__{upstream.name()}"
                            input_vars[safe_key] = upstream.node()._output_values.get(upstream.name())
                    else:
                        inputs_raw[port_name] = connected[0].node()._output_values.get(connected[0].name())
                        # 当前节点输入端口key
                        safe_key = f"input_{port_name}"
                        input_vars[safe_key] = inputs_raw[port_name]
                        safe_name = connected[0].node().name().replace(" ", "_")
                        # 上游节点输出端口key
                        safe_key = f"input_{safe_name}__{connected[0].name()}"
                        input_vars[safe_key] = inputs_raw[port_name]
                    if port_name in self.column_select:
                        inputs_raw[f"{port_name}_column_select"] = self.column_select.get(port_name)

            # === 创建表达式引擎（带全局变量）===
            expr_engine = ExpressionEngine(global_vars_context=gv)

            # === 递归求值 params，传入 input_vars ===
            def _evaluate_with_inputs(value, engine, input_vars_dict):
                if isinstance(value, str):
                    return engine.evaluate_template(value, local_vars=input_vars_dict)
                elif isinstance(value, list):
                    return [_evaluate_with_inputs(v, engine, input_vars_dict) for v in value]
                elif isinstance(value, dict):
                    return {k: _evaluate_with_inputs(v, engine, input_vars_dict) for k, v in value.items()}
                else:
                    return value

            params = {k: _evaluate_with_inputs(v, expr_engine, input_vars) for k, v in params.items()}
            inputs = {k: _evaluate_with_inputs(v, expr_engine, input_vars) for k, v in inputs_raw.items()}
            # ✅ 关键修改：使用持久化运行目录，而非临时目录
            run_id = f"run_{self.persistent_id}"
            run_dir = self.CACHE_PATH / "run_scripts" / run_id
            shutil.rmtree(run_dir, ignore_errors=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resource_path("app/components/base.py"), str(run_dir.parent / "base.py"))
            temp_script_path = run_dir / "exec_script.py"
            temp_component_path = run_dir / "component.py"
            params_path = run_dir / "params.pkl"
            result_path = run_dir / "result.pkl"
            error_path = run_dir / "error.pkl"
            # ✅ 复用 NodeLogHandler 的持久化日志路径
            log_file_path = self.log_capture.get_log_file_path()

            # 保存参数
            with open(params_path, 'wb') as f:
                pickle.dump((params, inputs, global_variable), f)
            if self._debug_widget is not None:
                # debug 模式 直接使用当前编辑器代码
                with open(temp_component_path, 'w', encoding='utf-8') as f:
                    f.write(self.current_code)
            else:
                current_version = self.get_property("version")
                if current_version == comp_obj._version or current_version == "latest":
                    temp_component_path = self.FILE_PATH
                else:
                    component_code = self.get_current_code()
                    with open(temp_component_path, 'w', encoding='utf-8') as f:
                        f.write(component_code)

            # 生成执行脚本
            # 注意：这里仍然使用原始的 FILE_PATH，执行的是保存后的代码
            script_content = _EXECUTION_SCRIPT_TEMPLATE.format(
                class_name=comp_obj.__name__,
                file_path=str(temp_component_path.resolve()),  # 使用历史版本文件
                params_path=str(params_path.resolve()),
                result_path=str(result_path.resolve()),
                error_path=str(error_path.resolve()),
                log_file_path=str(log_file_path.resolve()),
                node_id=self.persistent_id,
                workflow_path=str(self.CACHE_PATH)
            )
            with open(temp_script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            self.last_log_pos = os.path.getsize(log_file_path) if os.path.exists(log_file_path) else 0
            try:
                if kernel_manager is not None:
                    # 使用 IPython 内核执行
                    self._execute_via_ipython(
                        temp_script_path=temp_script_path,
                        result_path=result_path,
                        error_path=error_path,
                        log_file_path=log_file_path,
                        check_cancel=check_cancel,
                        kernel_manager=kernel_manager
                    )
                else:
                    # 回退到 subprocess（兼容模式）
                    self._execute_via_subprocess(
                        python_executable, temp_script_path, log_file_path, check_cancel
                    )
                # === 读取剩余日志 ===
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                    lf.seek(self.last_log_pos)
                    new_content = lf.read()
                    if new_content:
                        self._log_message(self.persistent_id, new_content)
                        self.last_log_pos = lf.tell()
                # === 处理最终结果 ===
                if os.path.exists(result_path):
                    output = _safe_load_pickle(result_path)
                    for port in comp_obj.outputs:
                        if port.type != ArgumentType.UPLOAD:
                            self.set_output_value(port.name, output.get(port.name))
                        else:
                            self.set_output_value(port.name, self.model.get_property(f"{port.name}_upload"))
                    self._sync_buffer_to_global()
                    return output
                elif os.path.exists(error_path):
                    error_info = _safe_load_pickle(error_path)
                    raise Exception(error_info['traceback'])
                else:
                    raise Exception("未知错误")
            finally:
                shutil.rmtree(run_dir, ignore_errors=True)

        def _execute_via_ipython(
                self, temp_script_path, result_path, error_path, log_file_path,
                check_cancel, kernel_manager
        ):
            # 清空变量，防止污染
            run_code = f'%reset -f'
            kernel_manager.execute_code(run_code, hidden=True)

            # 执行 %run -i
            with open(temp_script_path, 'r', encoding='utf-8') as f:
                code = f.read()
            kernel_manager.execute_code(code, hidden=True)

            # 轮询结果文件
            start_time = time.time()
            timeout = parent_window.config.node_run_timeout.value  # 5分钟

            while not (result_path.exists() or error_path.exists()):
                if check_cancel and check_cancel():
                    try:
                        kernel_manager.restart_kernel()  # now=True 表示立即重启（不等待）
                        self._log_message(self.persistent_id, "✅ 内核已重启，执行已终止。")
                    except Exception as e:
                        self._log_message(self.persistent_id, f"⚠️ 内核重启失败: {e}")
                    raise Exception("执行被用户取消")
                try:
                    if os.path.exists(log_file_path):
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                            lf.seek(self.last_log_pos)
                            new_content = lf.read()
                            if new_content:
                                # --- 关键修改 ---
                                self._log_message(self.persistent_id, new_content)
                                self.last_log_pos = lf.tell()
                except Exception:
                    pass
                if time.time() - start_time > timeout:
                    raise Exception(f"❌ 节点执行超时（{timeout} 秒）")

                time.sleep(0.1)
            self._log_message(self.persistent_id, "✅ 节点在ipython环境执行完成")

        def _execute_via_subprocess(
                self, python_executable, temp_script_path, log_file_path, check_cancel
        ):
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

            start_time = time.time()
            timeout = parent_window.config.node_run_timeout.value
            while proc.poll() is None:
                if check_cancel and check_cancel():
                    kill_proc_tree(proc.pid)
                    raise Exception("执行已被用户取消")
                if time.time() - start_time > timeout:
                    kill_proc_tree(proc.pid)
                    raise Exception(f"❌ 节点执行超时（{timeout} 秒）")
                # 增量读取日志，实时输出
                try:
                    if os.path.exists(log_file_path):
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                            lf.seek(self.last_log_pos)
                            new_content = lf.read()
                            if new_content:
                                self._log_message(self.persistent_id, new_content)
                                self.last_log_pos = lf.tell()
                except Exception:
                    pass
                time.sleep(0.1)
            self._log_message(self.persistent_id, "✅ 节点在独立环境执行完成")

    return DynamicNode