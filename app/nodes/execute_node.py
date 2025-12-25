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
from app.nodes.base_node import BasicNodeWithGlobalProperty, CustomBaseNode
from app.scan_components import ComponentScanner
from app.templates.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import draw_square_port, draw_special_outputport, \
    canvas_file_dump_path, _safe_load_pickle, kill_proc_tree  # 假设 resource_path 也在 utils
from app.widgets.node_widget.checkbox_widget import CheckBoxWidgetWrapper
# 导入代码编辑器组件
from app.widgets.node_widget.code_editor_widget import CodeEditorWidgetWrapper
from app.widgets.node_widget.combobox_widget import ComboBoxWidgetWrapper
from app.widgets.custom_nodegraphqt.custom_node_item import CustomNodeItem
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper
from app.widgets.node_widget.longtext_dialog import LongTextWidgetWrapper
from app.widgets.node_widget.range_widget import RangeWidgetWrapper
from app.widgets.node_widget.text_edit_widget import TextWidgetWrapper
from app.widgets.node_widget.variable_combo_widget import VarComboBoxWidgetWrapper


def _is_import_error(proc_or_result, error_file_path):
    """判断是否为 ImportError"""
    if os.path.exists(error_file_path):
        try:
            with open(error_file_path, 'rb') as f:
                error_info = pickle.load(f)
            return error_info.get("type") == "ImportError"
        except Exception:
            pass
    # 回退：检查 stderr（如果 proc 已结束）
    if hasattr(proc_or_result, 'stderr') and proc_or_result.stderr:
        return "ImportError" in proc_or_result.stderr
    return False


def _install_requirements(python_executable, requirements_str, logger=logger):
    """安装依赖包"""
    if not requirements_str.strip():
        logger.warning("组件 requirements 为空，跳过安装。")
        return
    packages = [pkg.strip() for pkg in requirements_str.split(',') if pkg.strip()]
    if not packages:
        return
    logger.info(f"检测到 ImportError，开始安装依赖: {packages}")
    for pkg in packages:
        try:
            logger.info(f"正在安装 {pkg} ...")
            subprocess.run(
                [python_executable, "-m", "pip", "install", pkg],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=True,
                timeout=300
            )
            logger.info(f"✅ 安装 {pkg} 成功。")
        except subprocess.TimeoutExpired:
            logger.error(f"❌ 安装 {pkg} 超时。")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ 安装 {pkg} 失败: {e.stderr}")
        except Exception as e:
            logger.error(f"❌ 安装 {pkg} 异常: {e}")


def create_node_class(full_path, file_path, parent_window=None):
    """返回一个高性能、支持独立环境执行的动态节点类"""

    class DynamicNode(CustomBaseNode, BasicNodeWithGlobalProperty):
        __identifier__ = 'dynamic'
        NODE_NAME = parent_window.component_map[full_path].name
        FULL_PATH = full_path
        FILE_PATH = file_path  # 现在 FILE_PATH 是真实的组件文件路径
        CACHE_PATH = (canvas_file_dump_path() / "workflows" / parent_window.workflow_name).resolve()

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.CACHE_PATH.mkdir(exist_ok=True, parents=True)
            self.set_property("version", "latest")
            self.parent_window = parent_window
            self.model.add_property("debug_code", {})
            if hasattr(ComponentScanner().get_component_by_uuid(self.uuid), "icon"):
                self.set_icon(ComponentScanner().get_component_by_uuid(self.uuid).icon)
            
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
            expected_names = [port_name for port_name, _ in ComponentScanner().get_component_by_uuid(self.uuid).get_outputs()]
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
            self._add_custom_widget(self._debug_widget, tab='Debug')

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
                self.graph.viewer().force_update()
                self._debug_widget = None
                logger.info(f"节点 {self.NODE_NAME} ({self.id}) 禁用调试模式。")

        def _save_debug_code(self, code_text):
            """保存调试编辑器中的代码到本地文件"""
            if code_text != self.current_code:
                self.current_code = code_text

        def _generate_parms_widget(self):
            """生成节点属性配置控件"""
            # 生成其他组件属性控件
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
                                z_value=len(ComponentScanner().get_component_by_uuid(self.uuid).get_properties()) - i
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
                        z_value=len(ComponentScanner().get_component_by_uuid(self.uuid).get_properties()) - i
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
                            z_value=len(ComponentScanner().get_component_by_uuid(self.uuid).get_properties()) - i
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

        def _add_custom_widget(self, widget, widget_type=None, tab=None):
            # widget_type = widget_type or NodePropWidgetEnum.HIDDEN.value
            self.set_property(widget.get_name(), widget.get_value())
            widget.value_changed.connect(lambda k, v: self.set_property(k, v))
            widget._node = self
            self.view.add_widget(widget)
            #: redraw node to address calls outside the "__init__" func.
            self.view.draw_node()
            widget.parent()

        def set_property(self, name, value, push_undo=True):
            if name.endswith('_file_filter'):
                self.model.properties[name] = value
                return
            super().set_property(name, value, push_undo)

        def remove_property(self, name):
            self.model._custom_prop[name] = None

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

        def execute_sync(self, comp_obj, kernel_manager=None, python_executable=None, check_cancel=None, max_retries=1):
            """
            在独立Python环境中执行组件
            :param check_cancel: 可选回调函数，返回 True 表示应取消执行
            """
            if not hasattr(self, "log_capture"):
                self.init_logger()
            if python_executable is None:
                raise Exception("未指定Python执行环境。")

            # === 收集参数 ===
            params = {}
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

            # === 全局变量 ===
            global_variable = self.global_variable
            # === 【关键】创建表达式引擎并求值 ===
            if global_variable is not None:
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
            else:
                # 无全局变量时，按原逻辑收集 inputs
                inputs = {}
                for input_port in self.input_ports():
                    port_name = input_port.name()
                    connected = input_port.connected_ports()
                    if connected:
                        if len(connected) == 1:
                            upstream = connected[0]
                            value = upstream.node()._output_values.get(upstream.name())
                            inputs[port_name] = value
                        else:
                            inputs[port_name] = [
                                upstream.node()._output_values.get(upstream.name()) for upstream in connected
                            ]
                        if port_name in self.column_select:
                            inputs[f"{port_name}_column_select"] = self.column_select.get(port_name)

            # === 获取 requirements ===
            requirements_str = getattr(comp_obj, 'requirements', '').strip()

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
                file_path=temp_component_path,  # 使用历史版本文件
                params_path=params_path,
                result_path=result_path,
                error_path=error_path,
                log_file_path=log_file_path,
                node_id=self.persistent_id,
                workflow_path=parent_window.workflow_name
            )
            with open(temp_script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)

            try:
                if kernel_manager is not None:
                    # 使用 IPython 内核执行
                    return self._execute_via_ipython(
                        comp_obj=comp_obj,
                        temp_script_path=temp_script_path,
                        result_path=result_path,
                        error_path=error_path,
                        log_file_path=log_file_path,
                        check_cancel=check_cancel,
                        kernel_manager=kernel_manager
                    )
                else:
                    # 回退到 subprocess（兼容模式）
                    return self._execute_via_subprocess(
                        python_executable, temp_script_path, comp_obj, result_path, error_path,
                        log_file_path, check_cancel, max_retries, requirements_str
                    )
            finally:
                time.sleep(0.05)  # 小延迟释放文件句柄
                shutil.rmtree(run_dir, ignore_errors=True)

        def _execute_via_ipython(
                self, comp_obj, temp_script_path, result_path, error_path, log_file_path,
                check_cancel, kernel_manager
        ):
            # 清空变量，防止污染
            run_code = f'%reset -f'
            kernel_manager.execute_code(run_code, hidden=True)
            # 获取 requirements
            requirements_str = getattr(comp_obj, 'requirements', '').strip()

            # 执行 %run -i
            with open(temp_script_path, 'r', encoding='utf-8') as f:
                code = f.read()
            kernel_manager.execute_code(code, hidden=True)

            # 轮询结果文件
            start_time = time.time()
            timeout = 300  # 5分钟
            last_log_pos = os.path.getsize(log_file_path) if os.path.exists(log_file_path) else 0

            while not (result_path.exists() or error_path.exists()):
                if check_cancel and check_cancel():
                    try:
                        kernel_manager.restart_kernel()  # now=True 表示立即重启（不等待）
                        self._log_message(self.persistent_id, "✅ 内核已重启，执行已终止。")
                    except Exception as e:
                        self._log_message(self.persistent_id, f"⚠️ 内核重启失败: {e}")
                    raise Exception("执行被用户取消")

                if time.time() - start_time > timeout:
                    raise Exception("❌ 节点执行超时（5分钟）")
                # 实时日志轮询
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

            # 检查结果/错误
            if result_path.exists():
                output = _safe_load_pickle(result_path)
                self._log_message(self.persistent_id, "✅ 节点在 IPython 内核中执行完成")
                for port in comp_obj.outputs:
                    if port.type != ArgumentType.UPLOAD:
                        self.set_output_value(port.name, output.get(port.name))
                return output
            elif error_path.exists():
                with open(error_path, 'rb') as f:
                    error_info = pickle.load(f)

                # 检查是否为 ImportError 并尝试安装依赖
                if error_info.get("type") == "ImportError" and requirements_str:
                    self._log_message(self.persistent_id, "检测到 ImportError，尝试安装依赖包...")

                    # 解析并安装依赖包
                    packages = [pkg.strip() for pkg in requirements_str.split(',') if pkg.strip()]
                    if packages:
                        parent_window.parent.package_manager.run_pip_command("安装", " ".join(packages))

                        self._log_message(self.persistent_id, "依赖包安装完成，重新执行...")

                        # 清理之前的错误文件
                        error_path.unlink(missing_ok=True)
                        result_path.unlink(missing_ok=True)

                        # 重新执行 %run -i
                        kernel_manager.execute_code(run_code, hidden=False)

                        # 再次轮询结果
                        start_time = time.time()
                        last_log_pos = os.path.getsize(log_file_path) if os.path.exists(log_file_path) else 0

                        while not (result_path.exists() or error_path.exists()):
                            if check_cancel and check_cancel():
                                raise Exception("执行被用户取消")

                            if time.time() - start_time > timeout:
                                raise Exception("❌ 节点执行超时（5分钟）")

                            # 实时日志轮询
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

                        # 检查重试后的结果
                        if result_path.exists():
                            output = _safe_load_pickle(result_path)
                            self._log_message(self.persistent_id, "✅ 节点在 IPython 内核中执行完成（重试后）")
                            for port in comp_obj.outputs:
                                if port.type != ArgumentType.UPLOAD:
                                    self.set_output_value(port.name, output.get(port.name))
                            return output
                        elif error_path.exists():
                            with open(error_path, 'rb') as f:
                                error_info_retry = pickle.load(f)
                            error_msg = f"❌ 节点执行失败（重试后）: {error_info_retry['traceback']}"
                            raise Exception(error_info_retry['traceback'])
                        else:
                            raise Exception("未知错误：未生成结果或错误文件（重试后）")
                else:
                    raise Exception(error_info['traceback'])
            else:
                raise Exception("未知错误：未生成结果或错误文件")

        def _execute_via_subprocess(
                self, python_executable, temp_script_path, comp_obj, result_path, error_path,
                log_file_path, check_cancel, max_retries, requirements_str
        ):
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
                last_log_pos = os.path.getsize(log_file_path) if os.path.exists(log_file_path) else 0
                while proc.poll() is None:
                    # 检查取消
                    if check_cancel and check_cancel():
                        kill_proc_tree(proc.pid)
                        cancelled = True
                        break
                    # 检查超时
                    if time.time() - start_time > timeout:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        self._log_message(self.persistent_id, "❌ 节点执行超时（5分钟）")
                        raise Exception("❌ 节点执行超时（5分钟）")

                    # 增量读取日志，实时输出
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
                    time.sleep(0.1)  # 避免 CPU 占用过高

                if cancelled:
                    self._log_message(self.persistent_id, "执行已被用户取消")
                    raise Exception("执行已被用户取消")

                # 读取剩余日志（无论成功失败）
                try:
                    if os.path.exists(log_file_path):
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                            lf.seek(last_log_pos)
                            tail_content = lf.read()
                            if tail_content:
                                self._log_message(self.persistent_id, tail_content)
                except Exception:
                    pass

                # 检查是否成功
                if proc.returncode == 0:
                    break

                # 判断是否为 ImportError 且可重试
                if retry_count == 0 and _is_import_error(proc, error_path):
                    _install_requirements(python_executable, requirements_str, comp_obj.logger)
                    retry_count += 1
                    continue
                else:
                    break

            # === 处理最终结果 ===
            if os.path.exists(result_path):
                with open(result_path, 'rb') as f:
                    output = pickle.load(f)
                comp_obj.logger.success("✅ 节点在独立环境执行完成")
                for port in comp_obj.outputs:
                    if port.type != ArgumentType.UPLOAD:
                        self.set_output_value(port.name, output.get(port.name))
                return output
            elif os.path.exists(error_path):
                with open(error_path, 'rb') as f:
                    error_info = pickle.load(f)
                error_msg = f"❌ 节点执行失败: {error_info['traceback']}"
                raise Exception(error_info['traceback'])
            else:
                # 未生成结果或错误文件，视为未知异常
                error_msg = "❌ 节点执行异常: 未知错误"
                raise Exception("未知错误")

    return DynamicNode