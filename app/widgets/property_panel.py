import json

from NodeGraphQt import BackdropNode
from PyQt5.QtWidgets import QVBoxLayout, QFrame, QPushButton, QFileDialog
from qfluentwidgets import CardWidget, BodyLabel, TextEdit, PushButton

from app.components.base import ArgumentType


class PropertyPanel(CardWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setFixedWidth(280)
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(20, 20, 20, 20)
        self.vbox.setSpacing(8)
        self.current_node = None

    def update_properties(self, node):
        # ✅ 完全清空布局（包括所有 items）
        while self.vbox.count():
            child = self.vbox.takeAt(0)
            if child.widget():
                # 关键修复：断开所有按钮类型的信号连接后再删除
                widget = child.widget()
                try:
                    # 断开 QPushButton 和 PushButton 的 clicked 信号
                    if isinstance(widget, (QPushButton, PushButton)):
                        widget.clicked.disconnect()
                except (TypeError, RuntimeError):
                    # 如果没有连接或已经断开，忽略错误
                    pass
                widget.deleteLater()

        self.current_node = node
        if not node or isinstance(node, BackdropNode):
            label = BodyLabel("请选择一个节点查看详情。")
            self.vbox.addWidget(label)
            return

        # 1. 节点标题
        title = BodyLabel(f"📌 {node.name()}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.vbox.addWidget(title)

        # 2. 节点描述（如果组件有描述）
        description = self.get_node_description(node)
        if description and description.strip():
            desc_label = BodyLabel(f"📝 {description}")
            desc_label.setStyleSheet("color: #888888; font-size: 12px;")
            self.vbox.addWidget(desc_label)

        # 添加分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        self.vbox.addWidget(separator)

        # 4. 输入端口（始终显示，无论是否有数据）
        self.vbox.addWidget(BodyLabel("📥 输入端口:"))

        # 获取组件的输入端口定义
        input_ports_info = self.get_node_input_ports_info(node)

        if input_ports_info:
            for input_port, port_def in zip(node.input_ports(), node.component_class.inputs):
                # 显示端口名称和标签
                port_display = f"{port_def.label} ({port_def.name})"
                self.vbox.addWidget(BodyLabel(f"  • {port_display}"))

                # 显示数据（如果有）
                connected = input_port.connected_ports()
                if connected:
                    upstream_out = connected[0]
                    upstream_node = upstream_out.node()
                    upstream_data_display = upstream_node.get_output_value(upstream_out.name())
                elif node._input_values.get(port_def.name) is not None:
                    upstream_data_display = node._input_values.get(port_def.name)
                else:
                    upstream_data_display = "暂无数据"

                port_type = getattr(port_def, 'type', ArgumentType.TEXT)
                # 根据端口类型显示不同控件
                if port_type.is_file():
                    self._add_file_widget(node, port_def.name)
                self._add_text_edit(port_type.to_dict(upstream_data_display))

        else:
            self.vbox.addWidget(BodyLabel("  无输入端口"))

        # 5. 输出端口（始终显示，无论是否有数据）
        self.vbox.addWidget(BodyLabel("📤 输出端口:"))
        output_ports = node.component_class.outputs
        if output_ports:
            result = node._output_values
            for port_def in output_ports:
                port_name = port_def.name
                port_label = port_def.label
                self.vbox.addWidget(BodyLabel(f"  • {port_label} ({port_name})"))

                output_data = result.get(port_name) if result and port_name in result else "暂无数据"
                port_type = getattr(port_def, 'type', ArgumentType.TEXT)
                self._add_text_edit(port_type.to_dict(output_data))
        else:
            self.vbox.addWidget(BodyLabel("  无输出端口"))

        # 添加底部弹性空间
        self.vbox.addStretch(1)

    def _add_text_edit(self, text):
        """智能显示不同类型的数据"""
        edit = TextEdit()

        # 智能格式化不同类型的数据
        if text is None:
            display_text = "None"
        elif isinstance(text, str):
            display_text = text
        elif hasattr(text, '__dict__') and not isinstance(text, (list, tuple, dict)):
            # 自定义对象
            try:
                display_text = f"[{text.__class__.__name__}] {str(text)}"
            except:
                display_text = str(text)
        elif isinstance(text, (list, tuple, dict)):
            # 容器类型，使用 JSON 格式化
            try:
                display_text = json.dumps(text, indent=2, ensure_ascii=False, default=str)
            except:
                display_text = str(text)
        else:
            # 其他类型
            display_text = str(text)

        edit.setPlainText(display_text)
        edit.setReadOnly(True)
        edit.setMaximumHeight(80)
        self.vbox.addWidget(edit)

    def _add_file_widget(self, node, port_name):
        """添加文件类型输出控件 - 包含文件选择功能"""
        # 文件选择按钮
        select_file_button = PushButton("📁 选择文件", self)
        select_file_button.clicked.connect(lambda _, p=port_name, n=node: self._select_input_file(p, n))

        # 将水平布局添加到主布局
        self.vbox.addWidget(select_file_button)

    def _select_input_file(self, port_name, node):
        """为输出端口选择文件"""
        # 根据端口类型设置文件过滤器
        if hasattr(node, 'component_class'):
            # 查找对应的输出端口定义
            output_ports = node.component_class.outputs
            for port_def in output_ports:
                if port_def.name == port_name:
                    port_type = getattr(port_def, 'type', None)
                    if port_type:
                        if port_type == ArgumentType.CSV:
                            file_filter = "CSV Files (*.csv)"
                        elif port_type == ArgumentType.JSON:
                            file_filter = "JSON Files (*.json)"
                        elif port_type == ArgumentType.FOLDER:
                            # 文件夹选择
                            folder_path = QFileDialog.getExistingDirectory(
                                self, "选择文件夹", ""
                            )
                            if folder_path:
                                self._update_output_file(node, port_name, folder_path)
                            return
                        else:
                            file_filter = "All Files (*)"
                    break
            else:
                file_filter = "All Files (*)"
        else:
            file_filter = "All Files (*)"

        # 文件选择对话框
        if 'FOLDER' in file_filter or file_filter == "All Files (*)":
            # 默认使用文件选择
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择文件", "", file_filter
            )
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择文件", "", file_filter
            )

        if file_path:
            self._update_input_file(node, port_name, file_path)

    def _update_input_file(self, node, port_name, file_path):
        """更新输出文件路径并刷新显示"""
        # 更新主窗口的 node_results
        node._input_values[port_name] = file_path
        # 刷新属性面板以显示新选择的文件
        self.update_properties(node)

    def _add_separator(self):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        self.vbox.addWidget(separator)

    def get_node_description(self, node):
        """获取节点描述"""
        if hasattr(node, 'component_class'):
            return getattr(node.component_class, 'description', '')
        return ''

    def get_node_input_ports_info(self, node):
        """获取节点输入端口信息 [(name, label), ...]"""
        if hasattr(node, 'component_class'):
            return node.component_class.get_inputs()
        # 回退到从端口对象获取
        ports_info = []
        for input_port in node.input_ports():
            port_name = input_port.name()
            # 尝试从组件定义获取标签，否则使用端口名作为标签
            ports_info.append((port_name, port_name))
        return ports_info

    def get_node_output_ports_info(self, node):
        """获取节点输出端口信息 [(name, label), ...]"""
        if hasattr(node, 'component_class'):
            return node.component_class.get_outputs()
        # 回退到从端口对象获取
        ports_info = []
        for output_port in node.output_ports():
            port_name = output_port.name()
            ports_info.append((port_name, port_name))
        return ports_info