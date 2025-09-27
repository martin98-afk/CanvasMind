import json

from PyQt5.QtWidgets import QVBoxLayout, QFrame
from qfluentwidgets import CardWidget, BodyLabel, TextEdit

from app.utils.json_serializer import output_serializable


class PropertyPanel(CardWidget):
    # ----------------------------
    # 属性面板（右侧）- 规范化样式
    # ----------------------------
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setFixedWidth(280)
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(20, 20, 20, 20)
        self.vbox.setSpacing(8)  # 减少间距
        self.current_node = None

    def update_properties(self, node):
        # ✅ 完全清空布局（包括所有 items）
        while self.vbox.count():
            child = self.vbox.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            # QSpacerItem 会自动被清理，不需要额外处理

        self.current_node = node
        if not node:
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

        # 获取组件的输出端口定义
        output_ports_info = self.get_node_output_ports_info(node)

        if output_ports_info:
            result = self.get_node_result(node)
            for port_name, port_label in output_ports_info:
                # 显示端口名称和标签
                port_display = f"{port_label} ({port_name})"
                self.vbox.addWidget(BodyLabel(f"  • {port_display}"))

                # 显示数据（如果有）
                if result and port_name in result:
                    value_str = json.dumps(output_serializable(result[port_name]), indent=2, ensure_ascii=False)
                else:
                    value_str = "暂无数据"

                text_edit = TextEdit()
                text_edit.setPlainText(value_str)
                text_edit.setReadOnly(True)
                text_edit.setMaximumHeight(80)
                self.vbox.addWidget(text_edit)
        else:
            self.vbox.addWidget(BodyLabel("  无输出端口"))

        # 添加底部弹性空间
        self.vbox.addStretch(1)

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