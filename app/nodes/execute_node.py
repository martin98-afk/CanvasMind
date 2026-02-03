# -*- coding: utf-8 -*-
import os
import pickle
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

import paramiko  # 确保环境已安装 paramiko

from PyQt5 import QtCore
from loguru import logger
from qfluentwidgets import MessageBox

# --- 其他原有导入 ---
from app.components.base import ArgumentType, PropertyType, ConnectionType, GlobalVariableContext, \
    COMPONENT_IMPORT_CODE, resource_path
from app.nodes.status_node import StatusNode
from app.scan_components import ComponentScanner
from app.scheduler.expression_engine import ExpressionEngine
from app.templates.node_cleanup_script import CLEANUP_CODE
from app.templates.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import _safe_load_pickle, kill_proc_tree, serialize_for_json, sftp_download_dir, replace_remote_paths, sftp_upload_dir
from app.widgets.custom_nodegraphqt.custom_base_node import CustomBaseNode
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.custom_nodegraphqt.custom_port_item import draw_special_outputport, draw_square_port
from app.widgets.node_widget.propeprty_widgets.checkbox_widget import CheckBoxWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.code_editor_widget import CodeEditorWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.combobox_widget import ComboBoxWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.dynamic_form_widget import DynamicFormWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.dynamic_tree_widget import DynamicTreeWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.file_select_widget import FileSelectWrapper
from app.widgets.node_widget.propeprty_widgets.longtext_dialog import LongTextWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.range_widget import RangeWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.spinbox_widget import NumberWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.text_edit_widget import TextWidgetWrapper
from app.widgets.node_widget.propeprty_widgets.variable_combo_widget import VarComboBoxWidgetWrapper


def create_node_class(full_path, file_path, parent_window=None):
    """返回一个高性能、支持独立环境执行的动态节点类"""

    class DynamicNode(CustomBaseNode, StatusNode):
        __identifier__ = 'dynamic'
        NODE_NAME = parent_window.component_map[full_path].name
        FULL_PATH = full_path
        FILE_PATH = file_path
        CACHE_PATH = parent_window.file_path.parent.resolve()
        object_io = False  # 用于判断当前节点是否存在内存对象传递，内存对象传递运行模式必须是ipython
        # 调试模式缓存
        _debug_enabled = False
        _debug_widget = None
        _debug_code_content = ""

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.parent_window = parent_window
            self._set_icon()
            self.CACHE_PATH.mkdir(exist_ok=True, parents=True)
            self.set_property("version", "latest")
            comp_class = ComponentScanner().get_component_by_uuid(self.uuid)
            if hasattr(comp_class, "icon"):
                self.set_icon(ComponentScanner().get_component_by_uuid(self.uuid).icon)

            self.view.exec_mode_signal.connect(self._clear_ipython_memory_context)
            # 组件ui构建
            self._generate_parms_widget()
            for port_name, label, connection, port_type, description in (
                    ComponentScanner().get_component_by_uuid(self.uuid).get_inputs()):
                if port_type == ArgumentType.OBJECT:
                    self.object_io = True
                if connection == ConnectionType.SINGLE:
                    _, port = self.add_input(port_name)
                else:
                    _, port = self.add_input(port_name, True, painter_func=draw_square_port)
                if description:
                    port.setToolTip(description)
            QtCore.QTimer.singleShot(0, self.build_outputs)
            # 调试模式信号连接
            self.view.debug_signal.connect(self._toggle_debug_mode)
            self.view.rename_signal.connect(parent_window.rename_node_vars)

        def _set_icon(self):
            """自动寻找扩展文件中的图标"""
            extension_path = Path(resource_path("app/component_extensions")) / self.uuid
            # 支持icon格式
            for icon_path in (extension_path / "assets/component_icon").glob("*"):
                if icon_path.is_file() and icon_path.suffix in [".png", ".jpg", ".jpeg", ".gif", ".svg", "ico"]:
                    self.set_icon(str(icon_path))
                    break

        @property
        def uuid(self):
            return self.model.type_.split("StatusDynamicNode_")[1]

        def build_outputs(self):
            for port_name, label, port_type, description in (
                    ComponentScanner().get_component_by_uuid(self.uuid).get_outputs()):
                if port_type == ArgumentType.OBJECT:
                    self.object_io = True
                self.delete_output(port_name)
                name = re.sub(r'\s+', '_', self.name())
                if f"{name}__{port_name}" in parent_window.global_variables.node_vars:
                    _, port = self.add_output(port_name, painter_func=draw_special_outputport)
                else:
                    _, port = self.add_output(port_name)
                if description:
                    port.setToolTip(description)

        def refresh_node_outports(self):
            self.set_port_deletion_allowed(True)
            # 1. 记录当前所有输出端口的连线状态：{port_name: [connected_downstream_ports]}
            expected_names = [
                port_name for port_name, _, _ in ComponentScanner().get_component_by_uuid(self.uuid).get_outputs()
            ]
            current_connections = {}
            for port in self.output_ports():
                connected = port.connected_ports()
                if connected:
                    current_connections[port.name()] = list(connected)
                port.clear_connections(push_undo=False, emit_signal=False)
            for port_name in expected_names:
                self.delete_output(port_name)

            # 2. 按 expected_names 顺序重建输出端口
            for name in expected_names:
                node_name = re.sub(r'\s+', '_', self.name())
                if f"{node_name}__{name}" in parent_window.global_variables.node_vars:
                    self.add_output(name, painter_func=draw_special_outputport)
                else:
                    self.add_output(name)

            # 3. 恢复连线：仅当“旧端口名 == 新端口名”且新端口存在
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
                description = prop_def.get("description", "")
                if prop_type == PropertyType.BOOL:
                    widget = CheckBoxWidgetWrapper(
                        parent=self.view, name=prop_name, text=label, state=default, window=parent_window,
                        z_value=custom_widgets_num - i
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="properties")

                elif prop_type in (PropertyType.INT, PropertyType.FLOAT):
                    widget = NumberWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, default=default, window=parent_window,
                        type=prop_type.name.lower(), z_value=custom_widgets_num - i
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="properties")

                elif prop_type == PropertyType.CHOICE:
                    choices = prop_def.get("choices", [])
                    if choices:
                        widget = ComboBoxWidgetWrapper(
                            parent=self.view, name=prop_name, label=label, items=choices, window=parent_window,
                            z_value=custom_widgets_num - i
                        )
                        if description:
                            widget.setToolTip(description)
                        self.add_custom_widget(widget, tab="properties")
                        self.set_property(prop_name, default if default in choices else choices[0])

                elif prop_type == PropertyType.LONGTEXT:
                    widget = LongTextWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, default=default, window=parent_window,
                        z_value=custom_widgets_num - i
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab='Properties')

                elif prop_type == PropertyType.RANGE:
                    min_val = prop_def.get("min", 0)
                    max_val = prop_def.get("max", 100)
                    step_val = prop_def.get("step", 1)
                    default_val = prop_def.get("default", min_val)
                    widget = RangeWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, min_val=min_val, max_val=max_val,
                        step=step_val, default=default_val, window=parent_window,
                        z_value=custom_widgets_num - i
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab='Properties')

                elif prop_type == PropertyType.DYNAMICTREE:
                    widget = DynamicTreeWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, window=parent_window,
                        z_value=custom_widgets_num - i
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
                            "step": field_def.get("step", 1)
                        }
                    widget = DynamicFormWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, schema=processed_schema,
                        window=parent_window, z_value=custom_widgets_num - i
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab='Properties')

                elif prop_type == PropertyType.VARIABLE:
                    default_val = prop_def.get("default")
                    widget = VarComboBoxWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, var_type=default_val or "全局变量",
                        main_window=parent_window, z_value=custom_widgets_num - i
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab="properties")
                    self.set_property(prop_name, "无")

                elif prop_type == PropertyType.FILE:
                    widget = FileSelectWrapper(
                        parent=self.view, name=prop_name, label=label, default=default, window=parent_window,
                        z_value=custom_widgets_num - i
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab='Properties')

                else:
                    widget = TextWidgetWrapper(
                        parent=self.view, name=prop_name, label=label, type=prop_type, default=str(default),
                        window=parent_window, z_value=custom_widgets_num - i
                    )
                    if description:
                        widget.setToolTip(description)
                    self.add_custom_widget(widget, tab='Properties')

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

        def execute_sync(self, comp_obj, kernel_manager=None, check_cancel=None, global_variable=None, **kwargs):
            """
            在本地或远程Python环境中执行组件
            """
            self.hide_inline_widgets()
            self.clear_output_value()
            if not hasattr(self, "log_capture"):
                self.init_logger()

            # 从环境管理器获取当前选中的完整 env_data
            env_data = self.parent_window.env_data
            if not env_data:
                raise Exception("未检测到有效的执行环境，请先在环境管理器中选择。")

            # === 收集参数与输入 (保持原有逻辑) ===
            params = serialize_for_json(self.model._custom_prop)
            reserved_properties_name = self.model.properties.keys()
            properties = comp_obj.get_properties()
            for prop_name, prop_def in properties.items():
                prop_ori_name = prop_name
                if prop_name in reserved_properties_name:
                    prop_name = f"_{prop_name}"
                    params.pop(prop_name)
                prop_type = prop_def.get("type", PropertyType.TEXT)
                default = prop_def.get("default", "")
                if prop_type == PropertyType.DYNAMICFORM:
                    widget = self.get_widget(prop_name)
                    params[prop_ori_name] = widget.get_value() if widget else (default or [])
                else:
                    params[prop_ori_name] = self.get_property(prop_name) if self.has_property(prop_name) else default
            gv = GlobalVariableContext()
            gv.deserialize(global_variable)
            inputs_raw = {}
            input_vars = {}
            global_variable["inputs"] = {}
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
                        for index, upstream in enumerate(connected):
                            safe_name = upstream.node().name().replace(" ", "_")
                            safe_key = f"input_{safe_name}__{upstream.name()}"
                            input_vars[safe_key] = upstream.node()._output_values.get(upstream.name())
                            global_variable["inputs"][f"input.{safe_name}__{upstream.name()}"] = index
                    else:
                        inputs_raw[port_name] = connected[0].node()._output_values.get(connected[0].name())
                        # 当前节点输入端口key
                        safe_key = f"input_{port_name}"
                        input_vars[safe_key] = inputs_raw[port_name]
                        safe_name = connected[0].node().name().replace(" ", "_")
                        # 上游节点输出端口key
                        safe_key = f"input_{safe_name}__{connected[0].name()}"
                        input_vars[safe_key] = inputs_raw[port_name]
                    if port_name in self.get_property("_column_select"):
                        inputs_raw[f"{port_name}_column_select"] = self.get_property("_column_select").get(port_name)

            expr_engine = ExpressionEngine(global_vars_context=gv)

            def _evaluate(value):
                if isinstance(value, str): return expr_engine.evaluate_template(value, local_vars=input_vars)
                if isinstance(value, list): return [_evaluate(v) for v in value]
                if isinstance(value, dict): return {k: _evaluate(v) for k, v in value.items()}
                return value

            params = {k: _evaluate(v) for k, v in params.items()}
            inputs = {k: _evaluate(v) for k, v in inputs_raw.items()}

            # === 准备本地运行目录 ===
            run_id = f"run_{self.persistent_id}"
            run_dir = self.CACHE_PATH / "run_scripts" / run_id
            shutil.rmtree(run_dir, ignore_errors=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            local_script_path = run_dir / "exec_script.py"
            local_comp_path = run_dir / "component.py"
            params_path = run_dir / "params.pkl"
            result_path = run_dir / "result.pkl"
            error_path = run_dir / "error.pkl"
            log_file_path = self.log_capture.get_log_file_path()

            with open(params_path, 'wb') as f:
                pickle.dump((params, inputs, global_variable), f)

            component_code = self.current_code if self._debug_widget else self.get_current_code()
            with open(local_comp_path, 'w', encoding='utf-8') as f:
                f.write(component_code)

            # === 分支：本地还是远程 ===
            self.last_log_pos = os.path.getsize(log_file_path) if os.path.exists(log_file_path) else 0
            self.timeout_enabled = parent_window.config.node_run_timeout_toggle.value
            self.timeout_seconds = parent_window.config.node_run_timeout.value
            if env_data.get('type') == 'ssh':
                # 远程 SSH 执行
                self._execute_via_ssh(comp_obj, env_data, kernel_manager, run_dir, log_file_path, error_path, check_cancel)
            else:
                shutil.copyfile(resource_path("app/components/base.py"), str(run_dir.parent / "base.py"))
                # 将组件扩展全部复制到运行目录
                extension_dir = Path(resource_path("app/component_extensions")) / self.uuid
                if extension_dir.exists():
                    if not (extension_dir / "manifest.json").exists():
                        raise FileNotFoundError(f"组件包损坏: 缺少 manifest.json ({extension_dir})")
                    shutil.copytree(extension_dir, self.CACHE_PATH / "workspace" / self.persistent_id,
                                    dirs_exist_ok=True)
                # 本地执行 (Subprocess 或 IPython)
                python_exe = env_data['path']
                # 注意：本地执行脚本中的路径需要是本地绝对路径
                script_content = _EXECUTION_SCRIPT_TEMPLATE.format(
                    class_name=comp_obj.__name__,
                    file_path=str(local_comp_path.resolve()),
                    params_path=str(params_path.resolve()),
                    result_path=str(result_path.resolve()),
                    error_path=str(error_path.resolve()),
                    log_file_path=str(log_file_path.resolve()),
                    node_id=self.persistent_id,
                    workflow_path=str(self.CACHE_PATH),
                    is_memory_resident=self.view.current_mode == "ipython"
                )
                with open(local_script_path, 'w', encoding='utf-8') as f:
                    f.write(script_content)
                if self.view.current_mode == "ipython" or self.object_io:
                    self._execute_via_ipython(local_script_path, result_path, error_path, log_file_path, check_cancel,
                                              kernel_manager)
                else:
                    self._execute_via_subprocess(python_exe, local_script_path, log_file_path, check_cancel)
            try:
                # === 结果读取重试机制 ===
                max_wait_time = 3.0  # 最大等待3秒
                retry_interval = 0.2
                elapsed_time = 0
                output = None
                last_error = "未发现结果或错误反馈文件。"

                while elapsed_time < max_wait_time:
                    # 1. 检查结果文件
                    if os.path.exists(result_path):
                        try:
                            # 增加一层保护：有时文件存在但正在写入，内容为空或不完整
                            if os.path.getsize(result_path) > 0:
                                output = _safe_load_pickle(result_path)
                                if output is not None:
                                    break  # 成功读取，跳出循环
                        except Exception as e:
                            last_error = f"结果文件读取失败(可能正在写入): {str(e)}"

                    # 2. 检查错误文件
                    elif os.path.exists(error_path):
                        try:
                            if os.path.getsize(error_path) > 0:
                                error_info = _safe_load_pickle(error_path)
                                self._log_message(self.persistent_id, error_info.get('traceback'))
                                raise Exception(error_info.get('traceback', '未知进程内错误'))
                        except Exception as e:
                            if "未知进程内错误" in str(e) or "traceback" in str(e): raise  # 业务错误直接抛出
                            last_error = f"错误文件读取失败: {str(e)}"

                    # 3. 未就绪，等待后重试
                    time.sleep(retry_interval)
                    elapsed_time += retry_interval

                # --- 退出循环后的处理 ---
                if output is not None:
                    # 填充输出端口数据
                    for port in comp_obj.outputs:
                        if port.type != ArgumentType.UPLOAD:
                            self.set_output_value(port.name, output.get(port.name))
                        else:
                            self.set_output_value(port.name, self.model.get_property(f"{port.name}_upload"))
                    self._sync_buffer_to_global()
                    return output
                else:
                    # 达到最大重试时间仍未获取结果
                    raise Exception(f"节点运行结束(超时)，{last_error}")

            finally:
                # === 后续处理结果 (通用) ===
                # 在删除目录前，务必先处理日志，确保最后一段日志被抓取
                try:
                    if os.path.exists(log_file_path):
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                            lf.seek(self.last_log_pos)
                            new_content = lf.read()
                            if new_content:
                                self._log_message(self.persistent_id, new_content)
                                self.last_log_pos = lf.tell()
                except:
                    pass

                # 最后删除临时运行目录
                # 如果在高并发下这里报错，可以加一个小延迟
                shutil.rmtree(run_dir, ignore_errors=True)

        def _execute_via_ssh(self, comp_obj, env_data, kernel_manager, run_dir, log_file_path, error_path, check_cancel):
            """远程 SSH 执行逻辑 - 针对日志文件流式读取优化"""
            local_result_path = run_dir / "result.pkl"
            remote_root = "/tmp/workspace"
            upload_dir = f"{remote_root}/{self.persistent_id}/upload"
            result_dir = f"{remote_root}/{self.persistent_id}/result"
            remote_run_dir = f"{remote_root}/{self.persistent_id}/run_scripts"
            log_path = f"{remote_root}/node_logs/{self.persistent_id}.log"

            # 本地对应路径
            local_node_workspace = self.CACHE_PATH / "workspace" / self.persistent_id

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                ssh.connect(
                    hostname=env_data['host'],
                    port=int(env_data.get('port', 22)),
                    username=env_data['user'],
                    password=env_data['pwd'],
                    timeout=15,
                    compress=True  # 开启 zlib 压缩
                )
                transport = ssh.get_transport()
                # 设置窗口大小（默认 2MB 左右，可以加大）
                transport.set_keepalive(30)
                sftp = ssh.open_sftp()

                # 1. 准备远程目录
                ssh.exec_command(f"mkdir -p {upload_dir} {result_dir} {remote_run_dir} {remote_root}/node_logs")
                ssh.exec_command(f"rm -f {log_path}")  # 强制删除远程旧日志
                # 2. 生成执行脚本
                remote_script_content = _EXECUTION_SCRIPT_TEMPLATE.format(
                    class_name=comp_obj.__name__,
                    file_path=f"{remote_run_dir}/component.py",
                    params_path=f"{remote_run_dir}/params.pkl",
                    result_path=f"{remote_run_dir}/result.pkl",
                    error_path=f"{remote_run_dir}/error.pkl",
                    log_file_path=log_path,
                    node_id=self.persistent_id,
                    workflow_path="/tmp",
                    is_memory_resident=self.view.current_mode == "ipython"
                )
                with open(run_dir / "exec_script.py", 'w', encoding='utf-8') as f:
                    f.write(remote_script_content)
                # 3. 上传文件
                # 上传 upload 文件夹内的内容
                local_upload_dir = local_node_workspace / "upload"
                if local_upload_dir.exists():
                    sftp_upload_dir(sftp, local_upload_dir, upload_dir)
                # 将本地运行目录上传至ssh服务器
                sftp_upload_dir(sftp, resource_path(f"app/component_extensions/{self.uuid}"), f"{remote_root}/{self.persistent_id}")
                sftp_upload_dir(sftp, run_dir, remote_run_dir)
                sftp.put(resource_path("app/components/base.py"), f"{remote_root}/{self.persistent_id}/base.py")

                # 4. 执行
                if self.view.current_mode == "ipython" or self.object_io:
                    if not kernel_manager:
                        raise Exception("远程 IPython 内核未连接。请确保右侧控制台已连接到对应的 SSH 环境。")

                    # B. 通过 SSH 隧道发送给远程内核执行 (非阻塞发送)
                    kernel_manager.execute_code(remote_script_content, hidden=True)

                    # C. 轮询远程文件系统，等待结果生成，同时拉取日志
                    start_time = time.time()
                    remote_res_file = f"{remote_run_dir}/result.pkl"
                    remote_err_file = f"{remote_run_dir}/error.pkl"
                    while True:
                        # 1. 检查取消信号
                        if check_cancel and check_cancel():
                            kernel_manager.interrupt_kernel()
                            raise Exception("远程 IPython 执行被用户取消")

                        # 2. 检查远程结果文件是否存在 (ls 比 stat 在某些 SSH 环境下更稳定)
                        _, stdout, _ = ssh.exec_command(f"ls {remote_res_file} {remote_err_file}")
                        found_files = stdout.read().decode()
                        with sftp.open(log_path, 'r') as f:
                            f.seek(self.last_log_pos)
                            new_data = f.read().decode('utf-8', errors='ignore')
                            if new_data:
                                self._log_message(self.persistent_id, new_data)
                                with open(log_file_path, 'a', encoding='utf-8') as lf:
                                    lf.write(new_data)
                                self.last_log_pos += len(new_data)
                        if remote_res_file in found_files or remote_err_file in found_files:
                            # 如果文件生成了，跳出轮询准备下载
                            break

                        # 4. 检查超时
                        if self.timeout_enabled and time.time() - start_time > self.timeout_seconds:
                            kernel_manager.interrupt_kernel()
                            raise Exception(f"远程 IPython 执行超时 {self.timeout_seconds} 秒")

                        time.sleep(0.5)  # 降低轮询频率
                else:
                    python_exe = env_data['path']
                    cmd = f"export PYTHONPATH={remote_root}:$PYTHONPATH && {python_exe} {remote_run_dir}/exec_script.py"
                    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
                    stdout.channel.setblocking(0)
                    # 轮询直到进程结束
                    start_time = time.time()
                    while not stdout.channel.exit_status_ready():
                        if check_cancel and check_cancel():
                            ssh.exec_command(f"pkill -f {remote_run_dir}/exec_script.py")
                            ssh.close()
                            raise Exception("远程执行被用户取消")

                        # 只有当远程日志文件产生时才尝试读取
                        try:
                            with sftp.open(log_path, 'r') as f:
                                f.seek(self.last_log_pos)
                                new_data = f.read().decode('utf-8', errors='ignore')
                                if new_data:
                                    self._log_message(self.persistent_id, new_data)
                                    with open(log_file_path, 'a', encoding='utf-8') as lf:
                                        lf.write(new_data)
                                    self.last_log_pos += len(new_data)
                        except IOError:
                            # 脚本可能还没开始写日志，忽略
                            pass
                        if self.timeout_enabled and time.time() - start_time > self.timeout_seconds:
                            ssh.exec_command(f"pkill -f {remote_run_dir}/exec_script.py")
                            ssh.close()
                            raise Exception(f"节点执行超时{self.timeout_seconds}秒")
                        time.sleep(0.5)  # 适当降低轮询频率，减少 IO 开销

                # 下载并处理 result.pkl
                remote_pkl = f"{remote_run_dir}/result.pkl"
                try:
                    sftp.get(remote_pkl, str(local_result_path))
                    # 路径替换：将远程路径前缀换为本地路径前缀
                    replace_remote_paths(
                        local_result_path, f"{remote_root}/{self.persistent_id}", str(local_node_workspace)
                    )
                except:
                    os.remove(local_result_path)
                # 下载错误文件
                try:
                    sftp.get(f"{remote_run_dir}/error.pkl", str(error_path))
                except:
                    os.remove(error_path)

                # 下载结果文件夹 result/
                local_res_dir = local_node_workspace / "result"
                local_res_dir.mkdir(parents=True, exist_ok=True)
                try:
                    sftp_download_dir(sftp, result_dir, local_res_dir, ssh=ssh)
                except:
                    pass

                # 6. 清理
                ssh.exec_command(f"rm -rf {remote_run_dir}")
                self._log_message(self.persistent_id, "✅ 节点在ssh远程环境执行完成")
            except Exception as e:
                raise Exception(f"远程执行失败: {str(e)}")
            finally:
                if 'sftp' in locals(): sftp.close()
                ssh.close()

        def _clear_ipython_memory_context(self, mode):
            """在 IPython 内核中执行清理脚本，彻底删除模块和实例引用"""
            logger.info(f"节点 {self.NODE_NAME} 模式切换至: {mode}，已尝试清理残留内存。")
            # 检查 parent_window 是否有可用的 kernel_manager
            km = self.parent_window.ipython_kernel.kernel_manager
            if km and mode == "subprocess":
                unique_key = f"dynamic_mod_{self.persistent_id}"

                # 构建清理代码
                # 1. 从 sys.modules 删除模块
                # 2. 显式触发垃圾回收
                cleanup_code = CLEANUP_CODE.format(unique_key=unique_key)
                try:
                    # 使用 hidden=True 避免在用户控制台输出日志
                    km.execute_code(cleanup_code, hidden=True)
                except Exception as e:
                    logger.warning(f"清理节点 {self.persistent_id} 内存失败: {e}")

        def _execute_via_ipython(
                self, temp_script_path, result_path, error_path, log_file_path,
                check_cancel, kernel_manager
        ):
            # 读取模板生成的代码并执行
            with open(temp_script_path, 'r', encoding='utf-8') as f:
                code = f.read()

            # 注意：在 IPython 中，直接执行 run_node() 函数名
            # 我们将代码块发送给内核执行
            kernel_manager.execute_code(code, hidden=True)
            # 轮询结果文件 (保持原逻辑不变)
            start_time = time.time()
            while not (result_path.exists() or error_path.exists()):
                if check_cancel and check_cancel():
                    # 如果用户取消，此时才考虑是否重启内核（慎用）
                    success = kernel_manager.interrupt_kernel()
                    if not success:
                        self._log_message(self.persistent_id, "⚠️ 中断失败，强制重启内核...")
                        kernel_manager.restart_kernel()
                    else:
                        self._log_message(self.persistent_id, "✅ 中断信号已发送。")
                    raise Exception("执行被用户取消")
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
                if self.timeout_enabled and time.time() - start_time > self.timeout_seconds:
                    kernel_manager.interrupt_kernel()
                    raise Exception(f"❌ 节点执行超时（{self.timeout_seconds} 秒）")
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
            while proc.poll() is None:
                if check_cancel and check_cancel():
                    kill_proc_tree(proc.pid)
                    raise Exception("执行已被用户取消")
                if self.timeout_enabled and time.time() - start_time > self.timeout_seconds:
                    kill_proc_tree(proc.pid)
                    raise Exception(f"❌ 节点执行超时（{self.timeout_seconds} 秒）")
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

        # 构建节点变量引用逻辑图
        def get_logical_inputs(self) -> list:
            """
            解析当前节点所有属性，捕获 $node_vars.XXX$ 格式的依赖
            返回格式: ['节点名__端口名', ...]
            """
            reads = set()
            # 匹配 $node_vars.xxxx_xxxx$
            pattern = re.compile(r"\$node_vars\.([a-zA-Z0-9_]+)\$")

            for name, value in self.model.custom_properties.items():
                # 只扫描字符串类型的属性（比如提示词、输入框）
                if isinstance(value, str) and value.startswith("node_vars."):
                    reads.add(value)
                if isinstance(value, str):
                    matches = pattern.findall(value)
                    for m in matches:
                        reads.add(m)
            return list(reads)

    return DynamicNode