# -*- coding: utf-8 -*-
import ast
import inspect
import re
import uuid
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTableWidgetItem, QHeaderView,
    QFormLayout
)
from qfluentwidgets import (
    CardWidget, BodyLabel, LineEdit, PrimaryPushButton, PushButton,
    TableWidget, ComboBox, InfoBar, InfoBarPosition, MessageBox, MessageBoxBase, FluentIcon
)

from app.components.base import COMPONENT_IMPORT_CODE, PropertyType, ArgumentType
from app.scan_components import scan_components
from app.widgets.code_editer import CodeEditorWidget, DEFAULT_CODE_TEMPLATE
from app.widgets.component_develop_tree import ComponentTreeWidget


# --- 组件开发主界面 (布局调整，修复同步) ---
class ComponentDeveloperWidget(QWidget):
    """组件开发主界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ComponentDeveloperWidget")
        self._current_component_file = None
        self._setup_ui()
        self._connect_signals()
        self._load_existing_components()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 左侧：组件树和开发区域
        splitter = QSplitter(Qt.Horizontal)
        # 组件树
        self.component_tree = ComponentTreeWidget()
        splitter.addWidget(self.component_tree)
        # 右侧：开发区域 - 使用新的左右布局
        self.development_area = self._create_development_area_new_layout()
        splitter.addWidget(self.development_area)
        splitter.setSizes([150, 800])  # 调整大小比例，给右侧更多空间
        layout.addWidget(splitter)

    def _create_development_area_new_layout(self):
        """创建新的开发区域布局（左右两栏）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        # 组件基本信息
        # 左右分割器
        main_splitter = QSplitter(Qt.Horizontal)
        # 左侧：端口和属性
        left_widget = self._create_left_panel()
        main_splitter.addWidget(left_widget)
        # 右侧：代码编辑器
        right_widget = self._create_right_panel()
        main_splitter.addWidget(right_widget)
        # 设置初始比例
        main_splitter.setSizes([400, 400])  # 左右各占一半
        layout.addWidget(main_splitter)
        # 保存按钮
        save_layout = QHBoxLayout()
        save_btn = PrimaryPushButton("💾 保存组件")
        save_btn.clicked.connect(lambda: self._save_component(True))
        cancel_btn = PushButton("❌ 取消")
        cancel_btn.clicked.connect(self._cancel_edit)
        save_layout.addStretch()
        save_layout.addWidget(cancel_btn)
        save_layout.addWidget(save_btn)
        layout.addLayout(save_layout)
        return widget

    def _create_left_panel(self):
        """创建左侧面板（端口和属性）"""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        basic_info_widget = CardWidget()
        basic_layout = QFormLayout(basic_info_widget)
        basic_layout.setContentsMargins(20, 20, 20, 20)
        self.name_edit = LineEdit()
        self.category_edit = LineEdit()
        self.description_edit = LineEdit()
        basic_layout.addRow(BodyLabel("组件名称:"), self.name_edit)
        basic_layout.addRow(BodyLabel("组件分类:"), self.category_edit)
        basic_layout.addRow(BodyLabel("组件描述:"), self.description_edit)
        left_layout.addWidget(BodyLabel("基本信息:"))
        left_layout.addWidget(basic_info_widget)
        # 端口编辑器（上下布局）
        port_splitter = QSplitter(Qt.Horizontal)
        # 输入输出端口编辑器
        self.input_port_editor = PortEditorWidget("input")
        self.output_port_editor = PortEditorWidget("output")
        port_splitter.addWidget(self.input_port_editor)
        port_splitter.addWidget(self.output_port_editor)
        port_splitter.setSizes([150, 150])  # 初始大小
        left_layout.addWidget(BodyLabel("端口设置:"))
        left_layout.addWidget(port_splitter)
        # 属性编辑器
        self.property_editor = PropertyEditorWidget()
        left_layout.addWidget(BodyLabel("参数设置:"))
        left_layout.addWidget(self.property_editor, stretch=1)
        return left_widget

    def _create_right_panel(self):
        """创建右侧面板（代码编辑器）"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        # 代码编辑器
        self.code_editor = CodeEditorWidget()
        right_layout.addWidget(BodyLabel("💻 组件代码:"))
        right_layout.addWidget(self.code_editor, stretch=1)
        return right_widget

    def _connect_signals(self):
        """连接信号"""
        self.component_tree.component_selected.connect(self._on_component_selected)
        self.component_tree.component_created.connect(self._on_component_created)
        self.component_tree.component_pasted.connect(self._on_component_pasted)
        # 连接编辑器改变信号
        self.input_port_editor.ports_changed.connect(self._sync_ports_to_code)
        self.output_port_editor.ports_changed.connect(self._sync_ports_to_code)  # 修复：连接输出端口信号
        self.property_editor.properties_changed.connect(self._sync_properties_to_code)
        self.code_editor.code_changed.connect(self._sync_code_to_ui)
        # 连接基本信息改变信号
        self.name_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.category_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.description_edit.textChanged.connect(self._sync_basic_info_to_code)

    def _load_existing_components(self):
        """加载现有组件"""
        try:
            component_map, file_map = scan_components()
            self.component_tree.load_components(component_map)
        except Exception as e:
            self._show_error(f"加载组件失败: {e}")

    def _on_component_selected(self, component):
        """组件选中回调"""
        self._load_component(component)

    def _on_component_created(self, component_info):
        """组件创建回调"""
        self._create_new_component(component_info)
        self._save_component()

    def _on_component_pasted(self):
        """组件粘贴回调"""
        self._load_component(self.component_tree._copied_component)
        self._save_component(delete_original_file=False)

    def _load_component(self, component):
        """加载组件到编辑器"""
        try:
            # 基本信息
            self.name_edit.setText(getattr(component, 'name', ''))
            self.category_edit.setText(getattr(component, 'category', ''))
            self.description_edit.setText(getattr(component, 'description', ''))
            # 加载输入端口
            inputs = getattr(component, 'inputs', [])
            self.input_port_editor.set_ports([
                {"name": port.name, "label": port.label, "type": getattr(port, 'type', 'text')}
                for port in inputs
            ])
            # 加载输出端口
            outputs = getattr(component, 'outputs', [])
            self.output_port_editor.set_ports([
                {"name": port.name, "label": port.label, "type": getattr(port, 'type', 'text')}
                for port in outputs
            ])
            # 加载属性
            properties = getattr(component, 'properties', {})
            self.property_editor.set_properties(properties)
            # 加载代码
            try:
                source_code = inspect.getsource(component)
                # 记录原始文件路径
                source_file = inspect.getfile(component)
                self._current_component_file = Path(source_file)
                self.code_editor.set_code(source_code)
            except:
                # 如果无法获取源码，使用默认模板
                template = DEFAULT_CODE_TEMPLATE
                template = template.replace("Component", component.__name__)
                template = template.replace("我的组件", getattr(component, 'name', ''))
                template = template.replace("数据处理", getattr(component, 'category', ''))
                template = template.replace("这是一个示例组件", getattr(component, 'description', ''))
                self.code_editor.set_code(template)
                # 对于新建的，原始文件路径为 None
                self._current_component_file = None

            self._sync_basic_info_to_code()
        except Exception as e:
            self._show_error(f"加载组件失败: {str(e)}")

    def _create_new_component(self, component_info):
        """创建新组件"""
        self.name_edit.setText(component_info["name"])
        self.category_edit.setText(component_info["category"])
        self.description_edit.setText(component_info["description"])
        # 清空编辑器
        self.input_port_editor.set_ports([])
        self.output_port_editor.set_ports([])
        self.property_editor.set_properties({})
        # 生成代码模板
        template = DEFAULT_CODE_TEMPLATE
        template = template.replace("我的组件", component_info["name"])
        template = template.replace("数据处理", component_info["category"])
        template = template.replace("这是一个示例组件", component_info["description"])
        self.code_editor.set_code(template)
        # 对于新建的，原始文件路径为 None
        self._current_component_file = None
        current_code = self.code_editor.get_code()
        if not current_code.strip():
            return
        # 解析并更新基本信息
        updated_code = self._update_basic_info_in_code(
            current_code,
            self.name_edit.text(),
            self.category_edit.text(),
            self.description_edit.text()
        )
        self.code_editor.set_code(updated_code)

    def _sync_ports_to_code(self):
        """同步端口到代码"""
        try:
            # 获取当前代码
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            # 解析并更新端口定义
            updated_code = self._update_ports_in_code(
                current_code,
                self.input_port_editor.get_ports(),  # 修复：传入输入端口
                self.output_port_editor.get_ports()  # 修复：传入输出端口
            )
            # 更新代码编辑器（避免触发递归）
            self.code_editor.code_editor.blockSignals(True)
            cursor_pos = self.code_editor.code_editor.textCursor().position()
            self.code_editor.set_code(updated_code)
            cursor = self.code_editor.code_editor.textCursor()
            cursor.setPosition(min(cursor_pos, len(updated_code)))
            self.code_editor.code_editor.setTextCursor(cursor)
            self.code_editor.code_editor.blockSignals(False)
        except Exception as e:
            print(f"同步端口到代码失败: {e}")

    def _sync_properties_to_code(self):
        """同步属性到代码"""
        try:
            # 获取当前代码
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            # 解析并更新属性定义
            updated_code = self._update_properties_in_code(
                current_code,
                self.property_editor.get_properties()
            )
            # 更新代码编辑器
            self.code_editor.code_editor.blockSignals(True)
            cursor_pos = self.code_editor.code_editor.textCursor().position()
            self.code_editor.set_code(updated_code)
            cursor = self.code_editor.code_editor.textCursor()
            cursor.setPosition(min(cursor_pos, len(updated_code)))
            self.code_editor.code_editor.setTextCursor(cursor)
            self.code_editor.code_editor.blockSignals(False)
        except Exception as e:
            print(f"同步属性到代码失败: {e}")

    def _sync_basic_info_to_code(self):
        """同步基本信息到代码"""
        try:
            # 获取当前代码
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            # 解析并更新基本信息
            updated_code = self._update_basic_info_in_code(
                current_code,
                self.name_edit.text(),
                self.category_edit.text(),
                self.description_edit.text()
            )
            # 更新代码编辑器
            self.code_editor.code_editor.blockSignals(True)
            cursor_pos = self.code_editor.code_editor.textCursor().position()
            self.code_editor.set_code(updated_code)
            cursor = self.code_editor.code_editor.textCursor()
            cursor.setPosition(min(cursor_pos, len(updated_code)))
            self.code_editor.code_editor.setTextCursor(cursor)
            self.code_editor.code_editor.blockSignals(False)
        except Exception as e:
            print(f"同步基本信息到代码失败: {e}")

    def _sync_code_to_ui(self):
        """从代码同步回UI"""
        pass

    def _update_ports_in_code(self, code, input_ports, output_ports):
        """更新代码中的端口定义"""
        lines = code.split('\n')
        new_lines = []
        i = 0
        inputs_replaced = False
        outputs_replaced = False

        while i < len(lines):
            line = lines[i]

            # 查找 inputs 或 outputs 定义的开始行
            if (not inputs_replaced and re.search(r'^\s*inputs\s*=\s*', line)
                    and ('[' in line or '[]' in line)):
                new_lines.append("    inputs = [")
                for port in input_ports:
                    new_lines.append(
                        f"        PortDefinition(name=\"{port['name']}\", label=\"{port['label']}\", type=ArgumentType.{port['type'].upper()}),")
                new_lines.append("    ]")
                inputs_replaced = True
                # 跳过原 inputs 定义的其余行
                if '[]' not in line:  # 如果不是空列表
                    bracket_count = line.count('[') - line.count(']')
                    j = i + 1
                    while j < len(lines) and bracket_count > 0:
                        bracket_count += lines[j].count('[') - lines[j].count(']')
                        j += 1
                    i = j
                else:  # 如果是空列表 [ ... ]
                    # 查找下一个非注释、非空白行，判断是否是 ] 结尾
                    j = i + 1
                    while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#')):
                        j += 1
                    if j < len(lines) and lines[j].strip() == ']':
                        i = j + 1
                    else:
                        i += 1  # 如果格式不标准，只跳过当前行
            elif (not outputs_replaced and re.search(r'^\s*outputs\s*=\s*', line) and
                  ('[' in line or '[]' in line)):
                new_lines.append("    outputs = [")
                for port in output_ports:
                    new_lines.append(
                        f"        PortDefinition(name=\"{port['name']}\", label=\"{port['label']}\", type=ArgumentType.{port['type'].upper()}),")
                new_lines.append("    ]")
                outputs_replaced = True
                # 跳过原 outputs 定义的其余行
                if '[]' not in line:  # 如果不是空列表
                    bracket_count = line.count('[') - line.count(']')
                    j = i + 1
                    while j < len(lines) and bracket_count > 0:
                        bracket_count += lines[j].count('[') - lines[j].count(']')
                        j += 1
                    i = j
                else:  # 如果是空列表 [ ... ]
                    # 查找下一个非注释、非空白行，判断是否是 ] 结尾
                    j = i + 1
                    while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#')):
                        j += 1
                    if j < len(lines) and lines[j].strip() == ']':
                        i = j + 1
                    else:
                        i += 1  # 如果格式不标准，只跳过当前行
            else:
                new_lines.append(line)
                i += 1

        # 如果代码中没有找到 inputs 或 outputs 行，则添加它们
        if not inputs_replaced:
            # 找到类定义开始后，插入空的 inputs 定义
            for idx, l in enumerate(new_lines):
                if l.strip().startswith('class ') and not any(
                        re.search(r'^\s*inputs\s*=\s*', ll) for ll in new_lines[idx:]):
                    new_lines.insert(idx + 1, "    inputs = []")
                    break
        if not outputs_replaced:
            # 找到类定义开始后，插入空的 outputs 定义
            for idx, l in enumerate(new_lines):
                if l.strip().startswith('class ') and not any(
                        re.search(r'^\s*outputs\s*=\s*', ll) for ll in new_lines[idx:]):
                    new_lines.insert(idx + 2, "    outputs = []")  # 假设 inputs 已存在或刚插入
                    break

        return '\n'.join(new_lines)

    def _update_properties_in_code(self, code, properties):
        """更新代码中的属性定义"""
        try:
            lines = code.split('\n')
            new_lines = []
            i = 0
            properties_replaced = False

            while i < len(lines):
                line = lines[i]

                # 查找 properties 定义的开始行
                if not properties_replaced and re.search(r'^\s*properties\s*=\s*', line) and (
                        '{' in line or '{}' in line):
                    new_lines.append("    properties = {")
                    for prop_name, prop_def in properties.items():
                        prop_type = prop_def['type']
                        default_value = prop_def['default']
                        label = prop_def['label']
                        # 格式化默认值
                        if prop_type in ['int', 'float']:
                            try:
                                default_value = str(eval(default_value)) if default_value else "0"
                            except:
                                default_value = "0" if prop_type == 'int' else "0.0"
                        elif prop_type == 'bool':
                            default_value = "True" if default_value.lower() in ['true', '1', 'yes'] else "False"
                        else:
                            default_value = f'"{default_value}"'
                        new_lines.append(f'        "{prop_name}": PropertyDefinition(')
                        new_lines.append(f'            type=PropertyType.{prop_type.upper()},')
                        new_lines.append(f'            default={default_value},')
                        new_lines.append(f'            label="{label}",')
                        # 处理 choice 类型的选项
                        if prop_type == 'choice' and 'choices' in prop_def:
                            choices = prop_def['choices']
                            choices_str = ', '.join([f'"{choice}"' for choice in choices])
                            new_lines.append(f'            choices=[{choices_str}]')
                        new_lines.append('        ),')
                    new_lines.append("    }")
                    properties_replaced = True
                    # 跳过原 properties 定义的其余行
                    if '{}' not in line:  # 如果不是空字典
                        bracket_count = line.count('{') - line.count('}')
                        j = i + 1
                        while j < len(lines) and bracket_count > 0:
                            bracket_count += lines[j].count('{') - lines[j].count('}')
                            j += 1
                        i = j
                    else:  # 如果是空字典 {{ ... }}
                        # 查找下一个非注释、非空白行，判断是否是 }} 结尾
                        j = i + 1
                        while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#')):
                            j += 1
                        if j < len(lines) and lines[j].strip() == '}':
                            i = j + 1
                        else:
                            i += 1  # 如果格式不标准，只跳过当前行
                else:
                    new_lines.append(line)
                    i += 1

            # 如果代码中没有找到 properties 行，则添加它
            if not properties_replaced:
                # 找到类定义开始后，插入空的 properties 定义
                for idx, l in enumerate(new_lines):
                    if l.strip().startswith('class ') and not any(
                            re.search(r'^\s*properties\s*=\s*', ll) for ll in new_lines[idx:]):
                        new_lines.insert(idx + 3, "    properties = {}")  # 假设 inputs, outputs 已存在或刚插入
                        break

            return '\n'.join(new_lines)
        except:
            return code

    def _update_basic_info_in_code(self, code, name, category, description):
        """更新代码中的基本信息"""
        try:
            lines = code.split('\n')
            new_lines = []
            for line in lines:
                if re.search(r'^\s*name\s*=\s*', line):
                    new_lines.append(f'    name = "{name}"')
                elif re.search(r'^\s*category\s*=\s*', line):
                    new_lines.append(f'    category = "{category}"')
                elif re.search(r'^\s*description\s*=\s*', line):
                    new_lines.append(f'    description = "{description}"')
                else:
                    new_lines.append(line)
            return '\n'.join(new_lines)
        except:
            return code

    def _save_component(self, delete_original_file: bool = True):
        """保存组件"""
        try:
            # 验证基本信息
            name = self.name_edit.text().strip()
            category = self.category_edit.text().strip()
            if not name or not category:
                self._show_warning("请输入组件名称和分类！")
                return
            # 生成组件代码
            code = self.code_editor.get_code()
            if not code.strip():
                self._show_warning("请输入组件代码！")
                return

            # --- 检查并添加必要的导入语句 ---
            if not code.startswith("try:"):
                # 简单的检查，如果开头不是预期的导入，就添加
                code = COMPONENT_IMPORT_CODE + code

            # 保存到文件，传入原始文件路径
            self._save_component_to_file(category, name, code, self._current_component_file, delete_original_file)
            # 刷新组件树
            self.component_tree.refresh_components()
            self._show_success("组件保存成功！")
        except Exception as e:
            self._show_error(f"保存组件失败: {str(e)}")

    def _save_component_to_file(self, category, name, code, original_file_path=None, delete_original_file=True):
        """保存组件到文件，可选择性地删除原始文件"""
        # 确保目录存在
        components_dir = Path(__file__).parent.parent / Path("components") / category
        components_dir.mkdir(parents=True, exist_ok=True)

        # --- 删除原始文件 ---
        if delete_original_file and original_file_path and original_file_path.exists():
            try:
                original_file_path.unlink()
                print(f"已删除原始组件文件: {original_file_path}")
            except Exception as e:
                print(f"删除原始组件文件失败: {e}")
            # 生成文件名
            filepath = original_file_path
        else:
            filename = f"{str(uuid.uuid4()).replace(' ', '_').lower()}.py"
            filepath = components_dir / filename

        # 写入新代码
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        self._current_component_file = filepath

    def _cancel_edit(self):
        """取消编辑"""
        w = MessageBox("确认", "确定要取消编辑吗？未保存的更改将丢失。", self.window())
        if w.exec():
            # 清空编辑器
            self.name_edit.clear()
            self.category_edit.clear()
            self.description_edit.clear()
            self.input_port_editor.set_ports([])
            self.output_port_editor.set_ports([])
            self.property_editor.set_properties({})
            self.code_editor.set_code(DEFAULT_CODE_TEMPLATE)
            self._current_component_file = None

    def _show_warning(self, message):
        """显示警告信息"""
        InfoBar.warning(
            title='警告',
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )

    def _show_error(self, message):
        """显示错误信息"""
        InfoBar.error(
            title='错误',
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
            parent=self
        )

    def _show_success(self, message):
        """显示成功信息"""
        InfoBar.success(
            title='成功',
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )


# --- 端口编辑器 (未改动) ---
class PortEditorWidget(QWidget):
    """端口编辑器 - 支持动态添加删除"""
    ports_changed = pyqtSignal()  # 端口改变信号

    def __init__(self, port_type="input", parent=None):
        super().__init__(parent)
        self.port_type = port_type
        layout = QVBoxLayout(self)

        # 表格
        self.table = TableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["端口名称", "端口标签", "端口类型"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda item: self.ports_changed.emit())
        # 在表头加按钮
        button_layout = QHBoxLayout()
        add_btn = PushButton(text=f"添加端口", icon=FluentIcon.ADD)
        add_btn.clicked.connect(lambda: self._add_port())
        remove_btn = PushButton(text="删除端口", icon=FluentIcon.CLOSE)
        remove_btn.clicked.connect(self._remove_port)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        layout.addWidget(self.table)

    def _on_item_changed(self, item):
        """表格项改变时发出信号"""
        self.ports_changed.emit()

    def _add_port(self, port: dict = {}):
        """添加端口"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        # 端口名称
        name_edit = QTableWidgetItem(port.get("name", f"port_{row}"))
        self.table.setItem(row, 0, name_edit)
        # 端口标签
        label_edit = QTableWidgetItem(port.get("label", f"端口{row + 1}"))
        self.table.setItem(row, 1, label_edit)
        # 端口类型
        type_combo = ComboBox()
        type_combo.addItems([item.value for item in ArgumentType])
        type_combo.setCurrentText(port.get("type", "text"))
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(lambda: self.ports_changed.emit())

    def _remove_port(self):
        """删除选中端口"""
        selected_ranges = self.table.selectedRanges()
        if selected_ranges:
            rows = []
            for range_ in selected_ranges:
                rows.extend(range(range_.topRow(), range_.bottomRow() + 1))
            rows = sorted(set(rows), reverse=True)
            for row in rows:
                self.table.removeRow(row)
            self.ports_changed.emit()

    def get_ports(self):
        """获取端口数据"""
        ports = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)
            if name_item and label_item:
                # 获取类型
                type_widget = self.table.cellWidget(row, 2)
                port_type = type_widget.currentText() if type_widget else "text"
                ports.append({
                    "name": name_item.text(),
                    "label": label_item.text(),
                    "type": port_type
                })
        return ports

    def set_ports(self, ports):
        """设置端口数据"""
        self.table.setRowCount(0)
        for port in ports:
            self._add_port(port)

# --- 属性编辑器 (未改动) ---
class PropertyEditorWidget(QWidget):
    """属性编辑器 - 支持动态添加删除"""
    properties_changed = pyqtSignal()  # 属性改变信号

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        # 属性表格
        self.table = TableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["属性名", "标签", "类型", "默认值", "选项"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda item: self.properties_changed.emit())

        button_layout = QHBoxLayout()
        add_btn = PushButton(text="添加属性", icon=FluentIcon.ADD)
        add_btn.clicked.connect(lambda: self._add_property())
        remove_btn = PushButton(text="删除选中", icon=FluentIcon.CLOSE)
        remove_btn.clicked.connect(self._remove_property)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        layout.addWidget(self.table)

    def _add_property(self, prop_name: str=None, prop_def: PropertyType=None):
        """添加属性"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        # 属性名
        name_item = QTableWidgetItem(prop_name if prop_name else f"prop_{row}")
        self.table.setItem(row, 0, name_item)
        # 标签
        label_item = QTableWidgetItem(getattr(prop_def, 'label', f"属性{row + 1}"))
        self.table.setItem(row, 1, label_item)
        # 类型
        type_combo = ComboBox()
        type_combo.addItems([item.value for item in PropertyType])
        type_combo.setCurrentText(getattr(prop_def, 'type', 'text'))
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(
            lambda text: self._on_type_changed(row, text)
        )
        # 默认值
        default_item = QTableWidgetItem(str(getattr(prop_def, 'default', '')))
        self.table.setItem(row, 3, default_item)
        # 选项（用于 choice 类型）
        options_item = QTableWidgetItem("")
        if getattr(prop_def, 'type', 'text') == "choice":
            choices = getattr(prop_def, 'choices', [])
            options_item.setText(",".join(choices))
            options_item.setFlags(options_item.flags() | Qt.ItemIsEditable)
        else:
            options_item.setFlags(options_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 4, options_item)

    def _on_type_changed(self, row, prop_type):
        """属性类型改变时的处理"""
        options_item = self.table.item(row, 4)
        if options_item:
            if prop_type == "choice":
                options_item.setFlags(options_item.flags() | Qt.ItemIsEditable)
                options_item.setText("")
            else:
                options_item.setFlags(options_item.flags() & ~Qt.ItemIsEditable)
                options_item.setText("")
        self.properties_changed.emit()

    def _remove_property(self):
        """删除选中属性"""
        selected_ranges = self.table.selectedRanges()
        if selected_ranges:
            rows = []
            for range_ in selected_ranges:
                rows.extend(range(range_.topRow(), range_.bottomRow() + 1))
            rows = sorted(set(rows), reverse=True)
            for row in rows:
                self.table.removeRow(row)
            self.properties_changed.emit()

    def get_properties(self):
        """获取属性数据"""
        properties = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)
            type_widget = self.table.cellWidget(row, 2)
            default_item = self.table.item(row, 3)
            options_item = self.table.item(row, 4)
            if name_item and type_widget and default_item:
                prop_name = name_item.text()
                prop_type = type_widget.currentText()
                default_value = default_item.text()
                properties[prop_name] = {
                    "type": prop_type,
                    "default": default_value,
                    "label": label_item.text() if label_item else prop_name
                }
                if prop_type == "choice" and options_item:
                    choices_text = options_item.text()
                    if choices_text:
                        properties[prop_name]["choices"] = [
                            opt.strip() for opt in choices_text.split(",")
                            if opt.strip()
                        ]
        return properties

    def set_properties(self, properties):
        """设置属性数据"""
        self.table.setRowCount(0)
        for prop_name, prop_def in properties.items():
            self._add_property(prop_name, prop_def)