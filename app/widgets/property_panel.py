import json

from NodeGraphQt import BackdropNode
from PyQt5.QtWidgets import QVBoxLayout, QFrame, QHBoxLayout
from qfluentwidgets import CardWidget, BodyLabel, TextEdit, LineEdit

from app.utils.json_serializer import output_serializable
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
                child.widget().deleteLater()
            # QSpacerItem 会自动被清理，不需要额外处理

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
            for port_name, port_label in input_ports_info:
                # 显示端口名称和标签
                port_display = f"{port_label} ({port_name})"
                self.vbox.addWidget(BodyLabel(f"  • {port_display}"))

                # 显示数据（如果有）
                upstream_data = self.get_upstream_data(node, port_name)
                if upstream_data is not None:
                    value_str = json.dumps(output_serializable(upstream_data), indent=2, ensure_ascii=False)
                else:
                    value_str = "暂无数据"

                text_edit = TextEdit()
                text_edit.setPlainText(value_str)
                text_edit.setReadOnly(True)
                text_edit.setMaximumHeight(80)
                self.vbox.addWidget(text_edit)
        else:
            self.vbox.addWidget(BodyLabel("  无输入端口"))

        # 5. 输出端口（始终显示，无论是否有数据）
        self.vbox.addWidget(BodyLabel("📤 输出端口:"))
        output_ports = node.component_class.outputs
        if output_ports:
            result = self.get_node_result(node)
            for port_def in output_ports:
                port_name = port_def.name
                port_label = port_def.label
                port_type = getattr(port_def, 'type', ArgumentType.TEXT)

                self.vbox.addWidget(BodyLabel(f"  • {port_label} ({port_name})"))

                # 根据端口类型显示不同控件
                if port_type.is_file():
                    self._add_file_output_widget(node, port_name, port_type, result)
                else:
                    value = json.dumps(output_serializable(result.get(port_name)), indent=2,
                                       ensure_ascii=False) if result and port_name in result else "暂无数据"
                    self._add_text_edit(value)
        else:
            self.vbox.addWidget(BodyLabel("  无输出端口"))

        # 添加底部弹性空间
        self.vbox.addStretch(1)

    def _add_file_output_widget(self, node, port_name, port_type, result):
        """添加文件类型输出控件"""
        file_path = result.get(port_name) if result else None

        # 创建水平布局
        h_layout = QHBoxLayout()

        # 文件路径显示
        file_label = LineEdit()
        file_label.setReadOnly(True)
        if file_path and isinstance(file_path, str) and os.path.exists(file_path):
            file_label.setText(file_path)
            file_label.setToolTip(file_path)
        else:
            file_label.setText("无文件" if not file_path else str(file_path))
            file_label.setStyleSheet("color: #888888;")

        # 文件操作按钮
        if file_path and isinstance(file_path, str) and os.path.exists(file_path):
            if os.path.isfile(file_path):
                open_btn = PrimaryPushButton("📂 打开文件", self)
                open_btn.clicked.connect(lambda _, fp=file_path: self._open_file(fp))
            else:
                open_btn = PrimaryPushButton("📁 打开文件夹", self)
                open_btn.clicked.connect(lambda _, fp=file_path: self._open_folder(fp))
            h_layout.addWidget(open_btn)

        h_layout.addWidget(file_label)
        self.vbox.addLayout(h_layout)

    def _open_file(self, file_path):
        """打开文件"""
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":  # macOS
                subprocess.call(["open", file_path])
            else:  # Linux
                subprocess.call(["xdg-open", file_path])
        except Exception as e:
            MessageBox("错误", f"无法打开文件: {str(e)}", self).exec()

    def _open_folder(self, folder_path):
        """打开文件夹"""
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin":  # macOS
                subprocess.call(["open", folder_path])
            else:  # Linux
                subprocess.call(["xdg-open", folder_path])
        except Exception as e:
            MessageBox("错误", f"无法打开文件夹: {str(e)}", self).exec()

    def _add_separator(self):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #444444;")
        self.vbox.addWidget(separator)

    def _add_text_edit(self, text):
        edit = TextEdit()
        edit.setPlainText(str(text))
        edit.setReadOnly(True)
        edit.setMaximumHeight(80)
        self.vbox.addWidget(edit)

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

    def get_upstream_data(self, node, port_name):
        return self.main_window.get_node_input(node, port_name)

    def get_node_result(self, node):
        return self.main_window.node_results.get(node.id, {})