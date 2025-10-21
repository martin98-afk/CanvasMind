# -*- coding: utf-8 -*-
import os
import pickle
import platform
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from NodeGraphQt import BaseNode, NodeBaseWidget
from NodeGraphQt.constants import NodePropWidgetEnum
from NodeGraphQt.errors import NodeWidgetError
from PyQt5.QtWidgets import QFileDialog
from loguru import logger
# 导入代码编辑器组件
from app.widgets.node_widget.code_editor_widget import CodeEditorWidgetWrapper
from app.widgets.node_widget.checkbox_widget import CheckBoxWidgetWrapper
# --- 其他原有导入 ---
from app.components.base import ArgumentType, PropertyType, ConnectionType, GlobalVariableContext
from app.nodes.base_node import BasicNodeWithGlobalProperty
from app.nodes.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import draw_square_port, resource_path  # 假设 resource_path 也在 utils
from app.widgets.node_widget.combobox_widget import ComboBoxWidgetWrapper
from app.widgets.node_widget.custom_node_item import CustomNodeItem
from app.widgets.node_widget.dynamic_form_widget import DynamicFormWidgetWrapper
from app.widgets.node_widget.longtext_dialog import LongTextWidgetWrapper
from app.widgets.node_widget.range_widget import RangeWidgetWrapper
from app.widgets.node_widget.text_edit_widget import TextWidgetWrapper
from app.widgets.node_widget.variable_combo_widget import GlobalVarComboBoxWidgetWrapper
from app.widgets.dialog_widget.component_log_message_box import LogMessageBox

PERSISTENT_TEMP_ROOT = Path("temp_runs").resolve()
PERSISTENT_TEMP_ROOT.mkdir(exist_ok=True, parents=True)


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


def _install_requirements(python_executable, requirements_str):
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


def create_node_class(component_class, full_path, file_path, parent_window=None):
    """返回一个高性能、支持独立环境执行的动态节点类"""

    class DynamicNode(BaseNode, BasicNodeWithGlobalProperty):
        __identifier__ = 'dynamic'
        NODE_NAME = component_class.name
        FULL_PATH = full_path
        FILE_PATH = file_path  # 现在 FILE_PATH 是真实的组件文件路径

        def __init__(self, qgraphics_item=None):
            super().__init__(CustomNodeItem)
            self.model.add_property("debug_code", {})
            self.component_class = component_class
            if hasattr(component_class, "icon"):
                self.set_icon(component_class.icon)
            self._node_logs = ""
            self._output_values = {}
            self._input_values = {}
            self.column_select = {}

            # --- 调试模式新增 ---
            self._debug_enabled = False
            self._debug_widget = None
            self._debug_code_content = ""
            # --- /调试模式新增 ---

            # === 动态生成属性 ===
            self._generate_parms_widget()
            # === 端口 ===
            for port_name, label, connection in component_class.get_inputs():
                if connection == ConnectionType.SINGLE:
                    self.add_input(port_name)
                else:
                    self.add_input(port_name, True, painter_func=draw_square_port)
            for port_name, label in component_class.get_outputs():
                self.add_output(port_name)

        def init_logger(self):
            if not self.has_property("persistent_id"):
                self.create_property("persistent_id", str(uuid.uuid4()))
            self._persistent_id = self.get_property("persistent_id")
            self.log_capture = NodeLogHandler(self._persistent_id, self._log_message, use_file_logging=True)

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
            if self._debug_widget is not None:
                # 已经存在，直接返回或刷新内容
                self._refresh_debug_code_content()
                return

            try:
                # 读取当前组件文件的代码
                with open(self.FILE_PATH, 'r', encoding='utf-8') as f:
                    initial_code = f.read()
            except FileNotFoundError:
                logger.warning(f"组件文件 {self.FILE_PATH} 未找到，无法加载调试代码。")
                initial_code = f"# 文件未找到: {self.FILE_PATH}\n"
            except Exception as e:
                logger.error(f"读取组件文件 {self.FILE_PATH} 失败: {e}")
                initial_code = f"# 读取文件失败: {e}\n"

            self._debug_code_content = initial_code

            # 创建代码编辑器控件
            self._debug_widget = CodeEditorWidgetWrapper(
                parent=self.view,
                name="debug_code",
                label="调试代码编辑器",
                default=self._debug_code_content,
                window=parent_window,
                width=600, height=400
            )
            # 连接信号，实现编辑时保存
            self._debug_widget.valueChanged.connect(self._save_debug_code)

            # 添加到节点属性面板
            self._add_custom_widget(self._debug_widget, tab='Debug')

            logger.info(f"节点 {self.NODE_NAME} ({self.id}) 启用调试模式。")

        def _disable_debug_mode(self):
            """禁用调试模式，移除代码编辑器"""
            if self._debug_widget is not None:
                # 断开信号连接（可选，但推荐）
                try:
                    self._debug_widget.valueChanged.disconnect(self._save_debug_code)
                except TypeError:
                    pass  # 可能未连接
                # 从节点移除控件
                self.remove_property("debug_code")
                self.view.remove_widget(self._debug_widget)
                #: redraw node to address calls outside the "__init__" func.
                self.view.draw_node()
                # Note: 直接从 UI 移除控件可能比较复杂，取决于框架实现。
                # 通常将控件放在一个特定的 'Debug' 标签页，禁用时可以隐藏标签页或清空其内容。
                # 这里我们移除属性，控件应随之消失或被隐藏。
                self._debug_widget = None
                logger.info(f"节点 {self.NODE_NAME} ({self.id}) 禁用调试模式。")

        def _refresh_debug_code_content(self):
            """刷新调试代码编辑器中的内容"""
            if self._debug_widget:
                try:
                    with open(self.FILE_PATH, 'r', encoding='utf-8') as f:
                        current_code = f.read()
                    self._debug_code_content = current_code
                    # 更新控件内容（如果控件支持）
                    # self._debug_widget.set_value(current_code) # 如果有此方法
                    # 或者，如果 valueChanged 信号只在用户交互时触发，可以手动更新内部值
                    # 这取决于 CodeEditorWidgetWrapper 的具体实现
                    # 此处假设控件内部会处理内容更新或需要用户手动刷新
                    logger.info(f"刷新了节点 {self.NODE_NAME} 的调试代码编辑器内容。")
                except Exception as e:
                    logger.error(f"刷新节点 {self.NODE_NAME} 调试代码内容失败: {e}")

        def _save_debug_code(self, code_text):
            """保存调试编辑器中的代码到本地文件"""
            if code_text != self._debug_code_content:
                try:
                    # 将编辑器中的内容写入原始文件
                    with open(self.FILE_PATH, 'w', encoding='utf-8') as f:
                        f.write(code_text)
                    self._debug_code_content = code_text
                    logger.info(f"已将调试代码保存到 {self.FILE_PATH}")
                except Exception as e:
                    logger.error(f"保存调试代码到 {self.FILE_PATH} 失败: {e}")
                    # 可以考虑弹窗提示用户保存失败
                    # QMessageBox.warning(self.view, "保存失败", f"无法保存代码到 {self.FILE_PATH}: {e}")

        def _generate_parms_widget(self):
            """生成节点属性配置控件"""
            # 生成其他组件属性控件
            for i, (prop_name, prop_def) in enumerate(component_class.get_properties().items()):
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
                                z_value=len(component_class.get_properties()) - i
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
                            "label": field_def.get("label", field_name),
                            "choices": field_def.get("choices", []),
                            "default": field_def.get("default", "")
                        }
                    widget = DynamicFormWidgetWrapper(
                        parent=self.view,
                        name=prop_name,
                        label=label,
                        schema=processed_schema,
                        window=parent_window,
                        z_value=len(component_class.get_properties()) - i
                    )
                    self.add_custom_widget(widget, tab='Properties')
                elif prop_type == PropertyType.VARIABLE:  # 新增类型
                    self.add_custom_widget(
                        GlobalVarComboBoxWidgetWrapper(
                            parent=self.view,
                            name=prop_name,
                            label=label,
                            main_window=parent_window,  # 传入 main_window 引用
                            z_value=len(component_class.get_properties()) - i
                        ),
                        tab="properties"
                    )
                    self.set_property(prop_name, default)
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

        def _select_file(self, prop_name):
            current_path = self.get_property(prop_name)
            directory = os.path.dirname(current_path) if current_path else ""
            file_filter = self.model.properties.get(f"{prop_name}_file_filter", "All Files (*)")
            # 添加creationflags参数以防止出现白色控制台窗口
            path, _ = QFileDialog.getOpenFileName(
                None, "选择文件", directory, file_filter
            )
            if path:
                self.set_property(prop_name, path)

        def _select_folder(self, prop_name):
            current_path = self.get_property(prop_name)
            directory = current_path if current_path else ""
            # 添加creationflags参数以防止出现白色控制台窗口
            path = QFileDialog.getExistingDirectory(None, "选择文件夹", directory)
            if path:
                self.set_property(prop_name, path)

        def _select_csv(self, prop_name):
            current_path = self.get_property(prop_name)
            directory = os.path.dirname(current_path) if current_path else ""
            # 添加creationflags参数以防止出现白色控制台窗口
            path, _ = QFileDialog.getOpenFileName(
                None, "选择CSV文件", directory, "CSV Files (*.csv)"
            )
            if path:
                self.set_property(prop_name, path)

        def _add_custom_widget(self, widget, widget_type=None, tab=None):
            if not isinstance(widget, NodeBaseWidget):
                raise NodeWidgetError(
                    '\'widget\' must be an instance of a NodeBaseWidget')

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

        def _log_message(self, node_id, message):
            """可选：仍保留内存日志用于实时滚动显示（如控制台面板）"""
            # 如果你有实时日志面板，可以保留；否则可删除整个方法
            if not hasattr(self, '_realtime_logs'):
                self._realtime_logs = ""
            if isinstance(message, str) and message.strip():
                if not message.endswith('\n'):
                    message += '\n'
                self._realtime_logs += message

        def get_logs(self):
            """从持久化日志文件读取内容（最多5000行）"""
            if not hasattr(self, "log_capture"):
                self.init_logger()
            try:
                return self.log_capture.read_log_file()
            except Exception as e:
                logger.warning(f"读取日志失败: {e}")
                return "日志读取失败。"

        def show_logs(self):
            log_content = self.get_logs()
            w = LogMessageBox(log_content, parent_window)
            w.exec()

        def set_output_value(self, port_name, value):
            self._output_values[port_name] = value

        def clear_output_value(self):
            self._output_values = {}

        def get_output_value(self, port_name):
            return self._output_values.get(port_name)

        def on_run_complete(self, output):
            self._output_values = output

        def execute_sync(self, comp_obj, python_executable=None, check_cancel=None, max_retries=1, retry_delay=1):
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
            global_variable = self.model.get_property("global_variable")
            # === 【关键】创建表达式引擎并求值 ===
            if global_variable is not None:
                gv = GlobalVariableContext()
                gv.deserialize(global_variable)
                # === 收集 inputs_raw ===
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
                        if port_name in self.column_select:
                            inputs_raw[f"{port_name}_column_select"] = self.column_select.get(port_name)

                # === 构建 input_xxx 变量 ===
                input_vars = {}
                for k, v in inputs_raw.items():
                    # 将 input.port_name 转为 input_port_name（避免点号）
                    safe_key = f"input_{k}"
                    input_vars[safe_key] = v

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
            run_id = f"run_{self._persistent_id}_{int(time.time())}"
            run_dir = PERSISTENT_TEMP_ROOT / run_id
            run_dir.mkdir(exist_ok=True)
            temp_script_path = run_dir / "exec_script.py"
            params_path = run_dir / "params.pkl"
            result_path = run_dir / "result.pkl"
            error_path = run_dir / "error.pkl"

            # ✅ 复用 NodeLogHandler 的持久化日志路径
            log_file_path = self.log_capture.get_log_file_path()

            # 保存参数
            with open(params_path, 'wb') as f:
                pickle.dump((params, inputs, global_variable), f)

            # 生成执行脚本
            # 注意：这里仍然使用原始的 FILE_PATH，执行的是保存后的代码
            script_content = _EXECUTION_SCRIPT_TEMPLATE.format(
                class_name=comp_obj.__name__,
                file_path=self.FILE_PATH,  # 使用原始文件路径
                params_path=params_path,
                result_path=result_path,
                error_path=error_path,
                log_file_path=log_file_path,
                node_id=self._persistent_id
            )
            with open(temp_script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)

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
                        self._log_message(self._persistent_id, "❌ 节点执行超时（5分钟）")
                        raise Exception("❌ 节点执行超时（5分钟）")

                    # 增量读取日志，实时输出
                    try:
                        if os.path.exists(log_file_path):
                            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                                lf.seek(last_log_pos)
                                new_content = lf.read()
                                if new_content:
                                    self._log_message(self._persistent_id, new_content)
                                    last_log_pos = lf.tell()
                    except Exception:
                        pass
                    time.sleep(0.1)  # 避免 CPU 占用过高

                if cancelled:
                    self._log_message(self._persistent_id, "执行已被用户取消")
                    raise Exception("执行已被用户取消")

                # 读取剩余日志（无论成功失败）
                try:
                    if os.path.exists(log_file_path):
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                            lf.seek(last_log_pos)
                            tail_content = lf.read()
                            if tail_content:
                                self._log_message(self._persistent_id, tail_content)
                except Exception:
                    pass

                # 检查是否成功
                if proc.returncode == 0:
                    break

                # 判断是否为 ImportError 且可重试
                if retry_count == 0 and _is_import_error(proc, error_path):
                    _install_requirements(python_executable, requirements_str)
                    retry_count += 1
                    continue
                else:
                    break

            # === 处理最终结果 ===
            if os.path.exists(result_path):
                with open(result_path, 'rb') as f:
                    output = pickle.load(f)
                component_class.logger.success("✅ 节点在独立环境执行完成")
                for port in comp_obj.outputs:
                    if port.type != ArgumentType.UPLOAD:
                        self.set_output_value(port.name, output.get(port.name))
                return output
            elif os.path.exists(error_path):
                with open(error_path, 'rb') as f:
                    error_info = pickle.load(f)
                error_msg = f"❌ 节点执行失败: {error_info['traceback']}"
                print(error_msg)
                self._log_message(self._persistent_id, error_msg)
                raise Exception(error_info['error'])
            else:
                # 未生成结果或错误文件，视为未知异常
                error_msg = "❌ 节点执行异常: 未知错误"
                self._log_message(self._persistent_id, error_msg)
                raise Exception("未知错误")

    return DynamicNode