import os

from NodeGraphQt import BaseNode
from PyQt5.QtWidgets import QFileDialog

from app.utils.node_logger import NodeLogHandler
from app.widgets.component_log_message_box import LogMessageBox


def create_node_class(component_class):
    """直接返回一个完整的节点类，支持文件上传按钮和独立日志"""

    class DynamicNode(BaseNode):
        __identifier__ = 'dynamic'
        NODE_NAME = component_class.name

        def __init__(self):
            super().__init__()
            self.component_class = component_class
            self._node_logs = ""  # 节点独立日志存储
            self._output_values = {}  # 存储输出端口值
            self._input_values = {}
            # 执行（捕获stdout/stderr）
            self.log_capture = NodeLogHandler(self.id, self._log_message)
            self.component_class.logger = self.log_capture.get_logger()

            # 添加属性
            for prop_name, prop_def in component_class.get_properties().items():
                prop_type = prop_def.get("type", "text")
                default = prop_def.get("default", "")
                label = prop_def.get("label", prop_name)

                if prop_type == "bool":
                    self.add_checkbox(prop_name, text=label, state=default)

                elif prop_type == "int":
                    self.add_text_input(prop_name, label, text=str(default))

                elif prop_type == "float":
                    self.add_text_input(prop_name, label, text=str(default))

                elif prop_type == "choice":
                    choices = prop_def.get("choices", [])
                    if choices:
                        self.add_combo_menu(prop_name, label, items=choices)
                        if default in choices:
                            self.set_property(prop_name, default)
                        else:
                            self.set_property(prop_name, choices[0])
                    else:
                        self.add_text_input(prop_name, label, text=str(default))
                else:
                    # 默认文本输入
                    self.add_text_input(prop_name, label, text=str(default))

            # 添加输入端口
            for port_name, label in component_class.get_inputs():
                self.add_input(port_name, label)

            # 添加输出端口
            for port_name, label in component_class.get_outputs():
                self.add_output(port_name, label)

        def _select_file(self, prop_name):
            """选择文件"""
            current_path = self.get_property(prop_name)
            directory = os.path.dirname(current_path) if current_path else ""

            file_filter = self.model.properties.get(f"{prop_name}_file_filter", "All Files (*)")
            path, _ = QFileDialog.getOpenFileName(
                None, "选择文件", directory, file_filter
            )
            if path:
                self.set_property(prop_name, path)

        def _select_folder(self, prop_name):
            """选择文件夹"""
            current_path = self.get_property(prop_name)
            directory = current_path if current_path and os.path.isdir(current_path) else ""

            path = QFileDialog.getExistingDirectory(
                None, "选择文件夹", directory
            )
            if path:
                self.set_property(prop_name, path)

        def _select_csv(self, prop_name):
            """选择CSV文件"""
            current_path = self.get_property(prop_name)
            directory = os.path.dirname(current_path) if current_path else ""

            path, _ = QFileDialog.getOpenFileName(
                None, "选择CSV文件", directory, "CSV Files (*.csv)"
            )
            if path:
                self.set_property(prop_name, path)

        def set_property(self, name, value, push_undo=True):
            """重写 set_property 以支持特殊属性"""
            if name.endswith('_file_filter'):
                self.model.properties[name] = value
                return
            super().set_property(name, value, push_undo)

        def _log_message(self, node_id, message):
            """记录节点日志"""
            if isinstance(message, str) and message.strip():
                if not message.endswith('\n'):
                    message += '\n'
                self._node_logs += message

        def get_logs(self):
            """获取节点日志"""
            return self._node_logs if self._node_logs else "无日志可用。"

        def show_logs(self):
            """显示节点日志"""
            log_content = self.get_logs()
            w = LogMessageBox(log_content, self.view.viewer())
            w.exec()

        def set_output_value(self, port_name, value):
            """设置输出端口的值"""
            self._output_values[port_name] = value

        def get_output_value(self, port_name):
            """获取输出端口的值"""
            return self._output_values.get(port_name)

        def on_run_complete(self, output):
            """节点运行完成后自动映射结果到输出端口"""
            self._output_values = output

        def execute_sync(self, main_window=None):
            """
            同步执行节点（由主窗口调用）
            upstream_outputs: {node_id: output_dict}
            main_window: 主窗口引用（用于状态更新，可选）
            """
            try:
                # 获取组件类
                comp_cls = self.component_class
                comp_instance = comp_cls()

                # 参数
                params = {}
                component_properties = comp_cls.get_properties()
                for prop_name, prop_def in component_properties.items():
                    default_value = prop_def.get("default", "")
                    if self.has_property(prop_name):
                        params[prop_name] = self.get_property(prop_name)
                    else:
                        params[prop_name] = default_value

                # 输入 - 关键修改：优先从 _input_values 获取
                inputs = {}
                for input_port in self.input_ports():
                    port_name = input_port.name()
                    connected = input_port.connected_ports()
                    if not connected:
                        continue
                    # 优先从 _input_values 获取（包含列选择结果）
                    if hasattr(self, '_input_values') and port_name in self._input_values:
                        inputs[port_name] = self._input_values[port_name]
                    else:
                        # 如果没有 _input_values，尝试从连接获取
                        upstream_out = connected[0]
                        upstream_node = upstream_out.node()
                        if hasattr(upstream_node, 'get_output_value'):
                            inputs[port_name] = upstream_node.get_output_value(upstream_out.name())

                if comp_cls.get_inputs():
                    output = comp_instance.run(params, inputs)
                else:
                    output = comp_instance.run(params)
                if output is not None:
                    # 记录执行结果
                    component_class.logger.success("✅ 节点执行完成")
                    self.on_run_complete(output)

                    return output

            except Exception as e:
                error_msg = f"❌ 节点执行失败: {str(e)}"
                component_class.logger.error(error_msg)
                raise e

    return DynamicNode