# -*- coding: utf-8 -*-
import ast
import json
import re
import shutil
import textwrap
import traceback
import uuid
from pathlib import Path
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidgetItem
)
from loguru import logger
from qfluentwidgets import (
    BodyLabel, MessageBox, FluentIcon, TransparentToolButton,
    TransparentDropDownToolButton, Action, RoundMenu
)
from app.components.base import COMPONENT_IMPORT_CODE, PropertyType, ArgumentType, ConnectionType
from app.interfaces.component_developer.utils.component_history_manager import ComponentHistoryManager
from app.interfaces.component_developer.constants import *
from app.interfaces.component_developer.llm_context import LLMContextProvider
from app.interfaces.component_developer.utils.message_manager import MessageManager
from app.scan_components import ComponentUsageTracker, ComponentScanner
from app.scan_components import resource_path
from app.templates.component_templates import default_templates
from app.templates.component_templates.base import DEFAULT_NODE_TEMPLATE
from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.code_editor.code_editer import CodeEditorWidget
from app.widgets.side_dock_area.side_dock_area import SideDockArea
from app.interfaces.component_developer.widgets.component_develop_tree import ComponentTreePanel


class ComponentDeveloperPage(QWidget):
    """组件开发主界面（已修复双向同步问题）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.home = parent
        self.package_manager = self.home.package_manager
        self.setObjectName("ComponentDeveloperWidget")
        self._current_component_file = None
        self._current_component_code = ""  # 存储当前加载的代码
        self.llm_context_provider = LLMContextProvider(self)
        self._setup_ui()
        self._connect_signals()
        # --- 添加一个定时器用于延迟分析 ---
        self._analysis_timer = QTimer()
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.timeout.connect(self._analyze_code_for_requirements)
        # --- 添加一个标志，防止循环更新 ---
        self._updating_requirements_from_analysis = False
        self._saving = False  # 防止重复保存
        self._property_sync_timer = QTimer()
        self._property_sync_timer.setSingleShot(True)
        self._property_sync_timer.setInterval(300)  # 300ms 防抖
        self._property_sync_timer.timeout.connect(self._sync_properties_to_code)
        # ✅ 新增：代码 → UI 同步防抖
        self._code_to_ui_sync_timer = QTimer()
        self._code_to_ui_sync_timer.setSingleShot(True)
        self._code_to_ui_sync_timer.setInterval(300)
        self._code_to_ui_sync_timer.timeout.connect(self._sync_code_to_ui)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 左侧：组件树和开发区域
        self.splitter = ModernSplitter(Qt.Horizontal)
        self.component_tree_panel = ComponentTreePanel(self)
        self.component_tree = self.component_tree_panel.tree
        self.splitter.addWidget(self.component_tree_panel)
        # 代码编辑框
        code_widget = QWidget(self)
        code_layout = QVBoxLayout(code_widget)
        code_layout.setContentsMargins(0, 0, 0, 0)
        self.code_editor = CodeEditorWidget(self, self.package_manager.get_current_python_exe())
        save_layout = QHBoxLayout()
        code_btn = TransparentToolButton(get_icon("代码执行"), parent=self)
        code_btn.setIconSize(QSize(20, 25))
        code_btn.setFixedSize(20, 25)
        save_layout.addWidget(code_btn)
        save_layout.addWidget(BodyLabel("组件代码:"))
        template_dropdown = TransparentDropDownToolButton(FluentIcon.ALIGNMENT, parent=self)
        menu = RoundMenu(parent=template_dropdown)
        for template_name in default_templates.keys():
            action = Action(
                template_name, triggered=lambda checked=False, name=template_name,
                code=default_templates[template_name]: self._switch_template(name, code)
            )
            menu.addAction(action)
        template_dropdown.setMenu(menu)
        save_layout.addWidget(template_dropdown)
        save_layout.addStretch()
        run_btn = TransparentToolButton(FluentIcon.PLAY, parent=self)
        run_btn.clicked.connect(self._run_component_code)
        save_layout.addWidget(run_btn)
        save_btn = TransparentToolButton(FluentIcon.SAVE, parent=self)
        save_btn.clicked.connect(lambda: self._save_component(True))
        cancel_btn = TransparentToolButton(FluentIcon.CLOSE, parent=self)
        cancel_btn.clicked.connect(self._cancel_edit)
        save_layout.addWidget(save_btn)
        save_layout.addWidget(cancel_btn)
        code_layout.addLayout(save_layout)
        code_layout.addWidget(self.code_editor, stretch=1)
        self.splitter.addWidget(code_widget)
        # 右侧：组件属性
        self.side_dock_area = SideDockArea(self, "组件开发")
        self.component_info = self.side_dock_area.get_tool_instance("组件属性面板")
        self.name_edit = self.component_info.name_edit
        self.category_edit = self.component_info.category_edit
        self.description_edit = self.component_info.description_edit
        self.requirements_edit = self.component_info.requirements_edit
        self.input_port_editor = self.component_info.input_port_editor
        self.output_port_editor = self.component_info.output_port_editor
        self.property_editor = self.component_info.property_editor
        self.history_table = self.side_dock_area.get_tool_instance("组件历史管理").history_table
        self.llm_chatter = self.side_dock_area.get_tool_instance("大模型对话")
        self.llm_chatter.set_system_prompt(self.llm_context_provider.system_prompt)
        self.llm_chatter.insertResponse.connect(self._handle_insert_code_from_llm)
        self.llm_chatter.createResponse.connect(self._handle_create_component_from_llm)
        self.history_table.itemDoubleClicked.connect(self._load_history_code)
        self.splitter.addWidget(self.side_dock_area)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        layout.addWidget(self.splitter)
        layout.addWidget(self.side_dock_area.tool_panel)

    @property
    def context_register(self):
        return self.llm_context_provider.context_register

    def hide_splitter(self):
        self.splitter.setSizes(HIDE_SPLITTER_SIZES)
        self.splitter.update()

    def show_splitter(self):
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.splitter.update()

    def _connect_signals(self):
        self.component_tree.component_selected.connect(self._load_component)
        self.component_tree.component_created.connect(self._on_component_created)
        self.component_tree.component_pasted.connect(self._on_component_pasted)
        self.input_port_editor.ports_changed.connect(self._sync_ports_to_code)
        self.output_port_editor.ports_changed.connect(self._sync_ports_to_code)
        self.property_editor.properties_changed.connect(self._on_property_changed)
        self.code_editor.code_changed.connect(self._on_code_text_changed)
        # ✅ 保留 UI → 代码 实时同步（但修复同步逻辑）
        self.name_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.category_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.description_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.requirements_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.requirements_edit.textChanged.connect(self._on_requirements_text_changed)
        self.history_table.itemChanged.connect(self._on_history_description_changed)

    def _on_property_changed(self):
        # 防抖：连续变更时只在停顿后同步
        self._property_sync_timer.start()

    def _handle_insert_code_from_llm(self, code: str):
        editor = self.code_editor.code_editor
        cursor = editor.textCursor()
        cursor.insertText(code)
        editor.setTextCursor(cursor)
        MessageManager.success("已插入代码", "", self)

    def _extract_component_info_from_code_str(self, code: str):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {
                "name": "未命名组件",
                "category": "数据处理",
                "description": "来自大模型生成的组件",
                "requirements": ""
            }
        info = {
            "name": "未命名组件",
            "category": "数据处理",
            "description": "来自大模型生成的组件",
            "requirements": ""
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "name" and isinstance(node.value, ast.Constant):
                            info["name"] = str(node.value.value)
                        elif target.id == "category" and isinstance(node.value, ast.Constant):
                            info["category"] = str(node.value.value)
                        elif target.id == "description" and isinstance(node.value, ast.Constant):
                            info["description"] = str(node.value.value)
                        elif target.id == "requirements" and isinstance(node.value, ast.Constant):
                            info["requirements"] = str(node.value.value)
        return info

    def _handle_create_component_from_llm(self, code: str):
        if not code.strip():
            MessageManager.warning("代码为空，无法创建组件", "", self)
            return
        self.code_editor.set_code(code)
        info = self._extract_component_info_from_code_str(code)
        self._create_new_component(info)
        self.code_editor.suspend_sync()
        try:
            self.code_editor.replace_text_preserving_view(code.strip())
            self._current_component_code = code.strip()
        finally:
            self.code_editor.resume_sync()
        try:
            self._save_component(delete_original_file=False)
            self.side_dock_area.switch_to("组件属性面板")
            MessageManager.success(f"已创建并保存组件：{info['name']}", "", self)
        except Exception as e:
            MessageManager.error(f"保存失败：{str(e)}", "请检查代码语法", self)

    def _switch_template(self, template_name, template_code):
        self.code_editor.replace_text_preserving_view(template_code)
        self._current_component_code = template_code
        MessageManager.success(f"已切换到模板: {template_name}", "", self)

    def _on_component_created(self, component_info):
        self._create_new_component(component_info)
        self._save_component()

    def _on_component_pasted(self, full_path):
        self._load_component(full_path=full_path, component=self.component_tree._copied_component)
        self._save_component(delete_original_file=False)

    def extract_class_source_from_file(self, file_path: Path, class_name: str) -> str:
        try:
            source_code = file_path.read_text(encoding='utf-8')
            source_lines = source_code.splitlines(keepends=True)
            start = len(COMPONENT_IMPORT_CODE.split("\n")) - 1
            return ''.join(source_lines[start:])
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.warning(f"AST extraction failed for {file_path}:{class_name} - {e}")
        return ""

    def _load_component_filepath(self, component_path: Path):
        file_map = {value: key for key, value in ComponentScanner().get_file_maps().items()}
        full_path = file_map.get(Path(component_path))
        QTimer.singleShot(300, lambda: self.update_usage_table(full_path))
        QTimer.singleShot(300, lambda: self._load_component(full_path))

    def _load_component(self, full_path=None, component=None):
        try:
            if full_path is not None:
                self.component_tree.set_current_editing_component(full_path)
            component = component or ComponentScanner().get_component(full_path)
            self.name_edit.setText(getattr(component, 'name', ''))
            self.category_edit.setText(getattr(component, 'category', ''))
            self.description_edit.setText(getattr(component, 'description', ''))
            self.requirements_edit.setText(getattr(component, 'requirements', '').replace(',', '\n'))
            inputs = getattr(component, 'inputs', [])
            self.input_port_editor.set_ports([
                {
                    "name": port.name,
                    "label": port.label,
                    "type": getattr(port, 'type', ArgumentType.TEXT),
                    "connection": getattr(port, 'connection', ConnectionType.SINGLE),
                }
                for port in inputs
            ])
            outputs = getattr(component, 'outputs', [])
            self.output_port_editor.set_ports([
                {"name": port.name, "label": port.label, "type": getattr(port, 'type', 'text')}
                for port in outputs
            ])
            properties = getattr(component, 'properties', {})
            self.property_editor.set_properties(properties)
            try:
                source_file = getattr(component, '_source_file', None)
                source_code = self.extract_class_source_from_file(source_file, component.__name__)
                self._current_component_file = Path(source_file)
                self._current_component_code = source_code
                self.code_editor.set_code(source_code)
            except:
                template = DEFAULT_NODE_TEMPLATE
                template = template.replace("Component", component.__name__)
                template = template.replace("我的组件", getattr(component, 'name', ''))
                template = template.replace("数据处理", getattr(component, 'category', ''))
                template = template.replace("这是一个示例组件", getattr(component, 'description', ''))
                self._current_component_code = template
                self.code_editor.replace_text_preserving_view(template)
                self._current_component_file = None
            # ⚠️ 不再调用 _sync_basic_info_to_code（会覆盖代码！）
            if self._current_component_file:
                self._load_history_list(self._current_component_file)
            else:
                self.history_table.setRowCount(0)
            QTimer.singleShot(300, lambda: self.update_usage_table(full_path))
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"加载组件失败: {str(e)}", "", self)

    def update_usage_table(self, full_path):
        if full_path:
            usage_records = ComponentUsageTracker().get_usage(full_path)
            usage_list = [
                {
                    "canvas_name": str(rec.canvas_path.stem).split(".workflow")[0],
                    "canvas_path": rec.canvas_path,
                    "node_name": rec.node_name,
                    "version": rec.version
                }
                for rec in usage_records
            ]
            history_tool = self.side_dock_area.get_tool_instance("组件历史管理")
            try:
                history_tool.strategy_changed.disconnect(self._on_usage_strategy_changed)
            except TypeError:
                pass
            history_tool.strategy_changed.connect(self._on_usage_strategy_changed)
            if history_tool:
                history_tool.update_usage_table(usage_list)

    def _on_usage_strategy_changed(self, canvas_path: str, node_name: str, strategy: str):
        try:
            canvas_file = Path(canvas_path)
            with open(canvas_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("graph", {}).get("nodes", {})
            target_node_id = None
            runtime = data.get("runtime", {})
            node_id2stable_key = runtime.get("node_id2stable_key", {})
            for node_id, node_data in nodes.items():
                if node_data.get("name") == node_name:
                    stable_key = node_id2stable_key.get(node_id, "")
                    full_path = stable_key.split("||")[0] if "||" in stable_key else ""
                    target_node_id = node_id
                    break
            if not target_node_id:
                MessageManager.warning("未找到对应节点", "", self)
                return
            new_version = "latest" if strategy == "同步" else strategy
            nodes[target_node_id].setdefault("custom", {})["version"] = new_version
            with open(canvas_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            MessageManager.success(f"已更新 {node_name} 的版本策略为 {new_version}", "", self)
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"更新策略失败: {e}", "", self)

    def _create_new_component(self, component_info):
        self.name_edit.setText(component_info["name"])
        self.category_edit.setText(component_info["category"])
        self.description_edit.setText(component_info["description"])
        self.input_port_editor.set_ports([])
        self.output_port_editor.set_ports([])
        self.property_editor.set_properties({})
        template = DEFAULT_NODE_TEMPLATE
        template = template.replace("我的组件", component_info["name"])
        template = template.replace("数据处理", component_info["category"])
        template = template.replace("这是一个示例组件", component_info["description"])
        self._current_component_code = template
        self.code_editor.replace_text_preserving_view(template)
        self._current_component_file = None
        # ⚠️ 不再在此处同步，避免覆盖

    def _run_component_code(self):
        self.side_dock_area.switch_to("多终端调试面板")
        local_import = """# -*- coding: utf-8 -*-
try:
    from app.components.base import *
except:
    from _internal.app.components.base import *
"""
        current_code = local_import + self.code_editor.get_code()
        if not current_code.strip():
            MessageManager.warning("代码编辑器为空，无法运行！", "", self)
            return
        current_console = self.side_dock_area.get_tool_instance("多终端调试面板").get_current_console()
        if current_console:
            current_console.execute_code(current_code)
        else:
            MessageManager.error("当前控制台未启动或无 kernel 客户端！", "", self)

    def _sync_ports_to_code(self):
        try:
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            updated_code = self._update_ports_in_code(
                current_code,
                self.input_port_editor.get_ports(),
                self.output_port_editor.get_ports()
            )
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                    self._current_component_code = updated_code  # ✅ 关键：更新缓存
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            MessageManager.error(f"同步端口到代码失败: {e}", "", self)

    def _sync_properties_to_code(self):
        try:
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            updated_code = self._update_properties_in_code(
                current_code,
                self.property_editor.get_properties()
            )
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                    self._current_component_code = updated_code  # ✅ 关键
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            MessageManager.error(f"同步属性到代码失败: {e}", "", self)

    def _sync_basic_info_to_code(self):
        try:
            current_code = self.code_editor.get_code()
            if not current_code.strip():
                return
            updated_code = self._update_basic_info_in_code(
                current_code,
                self.name_edit.text(),
                self.category_edit.currentText(),
                self.description_edit.toPlainText(),
                self.requirements_edit.toPlainText().replace("\n", ",")
            )
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                    self._current_component_code = updated_code  # ✅ 关键
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            print(f"同步基本信息到代码失败: {e}")

    def _update_ports_in_code(self, code, input_ports, output_ports):
        lines = code.split('\n')
        new_lines = []
        i = 0
        inputs_replaced = False
        outputs_replaced = False
        while i < len(lines):
            line = lines[i]
            if (not inputs_replaced and re.search(r'^\s*inputs\s*=\s*\[', line)):
                new_lines.append("    inputs = [")
                for port in input_ports:
                    new_lines.append(
                        f"        PortDefinition(name=\"{port['name']}\", label=\"{port['label']}\", "
                        f"type=ArgumentType.{port['type'].name}, "
                        f"connection=ConnectionType.{port.get('connection', ConnectionType.SINGLE.value).name}),"
                    )
                new_lines.append("    ]")
                inputs_replaced = True
                bracket_count = line.count('[') - line.count(']')
                j = i + 1
                while j < len(lines) and bracket_count > 0:
                    bracket_count += lines[j].count('[') - lines[j].count(']')
                    j += 1
                i = j
            elif (not outputs_replaced and re.search(r'^\s*outputs\s*=\s*\[', line)):
                new_lines.append("    outputs = [")
                for port in output_ports:
                    new_lines.append(
                        f"        PortDefinition(name=\"{port['name']}\", label=\"{port['label']}\", type=ArgumentType.{port['type'].name}),"
                    )
                new_lines.append("    ]")
                outputs_replaced = True
                bracket_count = line.count('[') - line.count(']')
                j = i + 1
                while j < len(lines) and bracket_count > 0:
                    bracket_count += lines[j].count('[') - lines[j].count(']')
                    j += 1
                i = j
            else:
                new_lines.append(line)
                i += 1
        if not inputs_replaced:
            for idx, l in enumerate(new_lines):
                if l.strip().startswith('class '):
                    new_lines.insert(idx + 1, "    inputs = []")
                    break
        if not outputs_replaced:
            for idx, l in enumerate(new_lines):
                if l.strip().startswith('class ') and (idx + 1 < len(new_lines) and 'inputs' in new_lines[idx + 1]):
                    new_lines.insert(idx + 2, "    outputs = []")
                    break
                elif l.strip().startswith('class '):
                    new_lines.insert(idx + 1, "    outputs = []")
                    break
        return '\n'.join(new_lines)

    def _update_properties_in_code(self, code, properties):
        try:
            lines = code.split('\n')
            new_lines = []
            i = 0
            properties_replaced = False
            while i < len(lines):
                line = lines[i]
                if not properties_replaced and re.search(r'^\s*properties\s*=\s*\{', line):
                    new_lines.append("    properties = {")
                    for prop_name, prop_def in properties.items():
                        if isinstance(prop_def, dict):
                            prop_type = prop_def.get('type', PropertyType.TEXT)
                            default_value = prop_def.get('default', '')
                            label = prop_def.get('label', prop_name)
                            choices = prop_def.get('choices', [])
                            schema = prop_def.get('schema', {})
                            min_val = prop_def.get('min', 0)
                            max_val = prop_def.get('max', 100)
                            step_val = prop_def.get('step', 1)
                        else:
                            prop_type = getattr(prop_def, 'type', PropertyType.TEXT)
                            default_value = getattr(prop_def, 'default', '')
                            label = getattr(prop_def, 'label', prop_name)
                            choices = getattr(prop_def, 'choices', [])
                            schema = getattr(prop_def, 'schema', {})
                            min_val = getattr(prop_def, 'min', 0)
                            max_val = getattr(prop_def, 'max', 100)
                            step_val = getattr(prop_def, 'step', 1)
                        if prop_type == PropertyType.DYNAMICFORM:
                            new_lines.append(f'        "{prop_name}": PropertyDefinition(')
                            new_lines.append(f'            type=PropertyType.DYNAMICFORM,')
                            new_lines.append(f'            label="{label}",')
                            if schema:
                                new_lines.append('            schema={')
                                for field_name, field_def in schema.items():
                                    if not isinstance(field_def, dict):
                                        field_def = field_def.dict()
                                    field_type = field_def.get('type', PropertyType.TEXT)
                                    field_default = field_def.get('default', '')
                                    field_label = field_def.get('label', field_name)
                                    field_choices = field_def.get('choices', [])
                                    new_lines.append(f'                "{field_name}": PropertyDefinition(')
                                    new_lines.append(f'                    type=PropertyType.{field_type.name},')
                                    if field_type == PropertyType.INT:
                                        fv = str(int(field_default)) if field_default else "0"
                                    elif field_type == PropertyType.FLOAT:
                                        fv = str(float(field_default)) if field_default else "0.0"
                                    elif field_type == PropertyType.BOOL:
                                        fv = "True" if str(field_default).lower() in ("true", "1", "yes") else "False"
                                    elif prop_type == PropertyType.LONGTEXT:
                                        if field_default:
                                            safe_text = field_default.replace('"""', '\\"\\"\\"')
                                            fv = '"""' + textwrap.dedent(safe_text) + '"""'
                                        else:
                                            fv = '""""""'
                                    else:
                                        fv = f'"{field_default}"'
                                    new_lines.append(f'                    default={fv},')
                                    new_lines.append(f'                    label="{field_label}",')
                                    if field_type == PropertyType.CHOICE and field_choices:
                                        choices_str = ', '.join([f'"{c}"' for c in field_choices])
                                        new_lines.append(f'                    choices=[{choices_str}]')
                                    elif field_type == PropertyType.RANGE:
                                        new_lines.append(f'                    min={field_def.get("min", 0)},')
                                        new_lines.append(f'                    max={field_def.get("max", 100)},')
                                        new_lines.append(f'                    step={field_def.get("step", 1)}')
                                    new_lines.append('                ),')
                                new_lines.append('            }')
                            new_lines.append('        ),')
                        else:
                            if prop_type == PropertyType.INT:
                                dv = str(int(default_value)) if default_value else "0"
                            elif prop_type == PropertyType.FLOAT:
                                dv = str(float(default_value)) if default_value else "0.0"
                            elif prop_type == PropertyType.BOOL:
                                dv = "True" if str(default_value).lower() in ("true", "1", "yes") else "False"
                            elif prop_type == PropertyType.LONGTEXT:
                                if default_value:
                                    safe_text = default_value.replace('"""', '\\"\\"\\"')
                                    dv = '"""' + textwrap.dedent(safe_text) + '"""'
                                else:
                                    dv = '""""""'
                            else:
                                dv = f'"{default_value}"'
                            new_lines.append(f'        "{prop_name}": PropertyDefinition(')
                            new_lines.append(f'            type=PropertyType.{prop_type.name},')
                            new_lines.append(f'            default={dv},')
                            new_lines.append(f'            label="{label}",')
                            if prop_type == PropertyType.CHOICE and choices:
                                choices_str = ', '.join([f'"{c}"' for c in choices])
                                new_lines.append(f'            choices=[{choices_str}]')
                            if prop_type == PropertyType.RANGE:
                                new_lines.append(f'            min={min_val},')
                                new_lines.append(f'            max={max_val},')
                                new_lines.append(f'            step={step_val},')
                            new_lines.append('        ),')
                    new_lines.append("    }")
                    properties_replaced = True
                    bracket_count = line.count('{') - line.count('}')
                    j = i + 1
                    while j < len(lines) and bracket_count > 0:
                        bracket_count += lines[j].count('{') - lines[j].count('}')
                        j += 1
                    i = j
                else:
                    new_lines.append(line)
                    i += 1
            if not properties_replaced:
                for idx, l in enumerate(new_lines):
                    if l.strip().startswith('class '):
                        new_lines.insert(idx + 3, "    properties = {}")
                        break
            return '\n'.join(new_lines)
        except Exception as e:
            logger.error(f"_update_properties_in_code error: {e}")
            logger.error(traceback.format_exc())
            return code

    def _find_triple_quote_end(self, lines, start_idx):
        line = lines[start_idx]
        if '"""' not in line:
            return start_idx
        if line.count('"""') >= 2:
            return start_idx
        i = start_idx + 1
        while i < len(lines):
            if '"""' in lines[i]:
                return i
            i += 1
        return start_idx

    def _update_basic_info_in_code(self, code, name, category, description, requirements):
        try:
            lines = code.split('\n')
            try:
                tree = ast.parse(code)
            except SyntaxError:
                logger.warning("AST parse failed in _update_basic_info_in_code, fallback to regex")
                return self._fallback_update_basic_info(code, name, category, description, requirements)

            target_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    target_class = node
                    break
            if not target_class:
                return code

            replacements = []
            basic_fields = {"name", "category", "description", "requirements"}
            for stmt in target_class.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name) and target.id in basic_fields:
                            start_line = stmt.lineno - 1  # 0-based index
                            if target.id == "description":
                                end_line = self._find_triple_quote_end(lines, start_line)
                                if '\n' in description or '"""' in description or '"' in description or "'" in description:
                                    safe_desc = description.replace('"""', '\\"\\"\\"')
                                    new_content = [f'    description = """{safe_desc}"""']
                                else:
                                    new_content = [f'    description = "{description}"']
                                replacements.append((start_line, end_line, new_content))
                            else:
                                value_str = None
                                if target.id == "name":
                                    value_str = f'    name = "{name}"'
                                elif target.id == "category":
                                    value_str = f'    category = "{category}"'
                                elif target.id == "requirements":
                                    value_str = f'    requirements = "{requirements}"'
                                if value_str is not None:
                                    replacements.append((start_line, start_line, [value_str]))

            # 从后往前执行替换
            new_lines = lines[:]
            for start, end, new_content in sorted(replacements, reverse=True):
                new_lines = new_lines[:start] + new_content + new_lines[end + 1:]

            # 检查是否缺失字段（仅当完全不存在时才插入）
            final_code = '\n'.join(new_lines)
            missing = []
            if '    name = ' not in final_code:
                missing.append(f'    name = "{name}"')
            if '    category = ' not in final_code:
                missing.append(f'    category = "{category}"')
            if '    description = ' not in final_code:
                if '\n' in description or '"""' in description or '"' in description or "'" in description:
                    safe_desc = description.replace('"""', '\\"\\"\\"')
                    missing.append(f'    description = """{safe_desc}"""')
                else:
                    missing.append(f'    description = "{description}"')
            if requirements and '    requirements = ' not in final_code:
                missing.append(f'    requirements = "{requirements}"')

            if missing:
                class_lineno = target_class.lineno - 1  # 0-based
                new_lines = new_lines[:class_lineno + 1] + missing + new_lines[class_lineno + 1:]

            return '\n'.join(new_lines)
        except Exception as e:
            logger.error(f"Error in _update_basic_info_in_code: {e}")
            logger.error(traceback.format_exc())
            return code

    def _on_code_text_changed(self):
        current_text = self.code_editor.get_code()
        # ✅ 不再依赖 _current_component_code 比较（防止粘贴相同内容不触发）
        if not self._updating_requirements_from_analysis:
            self._analysis_timer.start(2000)
        # ✅ 触发代码 → UI 同步
        self._code_to_ui_sync_timer.start()

    def _sync_code_to_ui(self):
        """从代码解析并更新 UI（安全、防崩溃）"""
        code = self.code_editor.get_code()
        if not code.strip():
            return
        try:
            info = self._extract_component_info_from_code_str(code)
            # 临时阻断信号，防止循环
            self.name_edit.blockSignals(True)
            self.category_edit.blockSignals(True)
            self.description_edit.blockSignals(True)
            self.requirements_edit.blockSignals(True)
            self.name_edit.setText(info["name"])
            self.category_edit.setText(info["category"])
            self.description_edit.setPlainText(info["description"])
            self.requirements_edit.setPlainText(info["requirements"].replace(',', '\n'))
            self.name_edit.blockSignals(False)
            self.category_edit.blockSignals(False)
            self.description_edit.blockSignals(False)
            self.requirements_edit.blockSignals(False)
            # ✅ 更新缓存
            self._current_component_code = code
        except Exception as e:
            logger.warning(f"代码 → UI 同步失败: {e}")

    def _on_requirements_text_changed(self):
        self._analysis_timer.stop()

    def _analyze_code_for_requirements(self):
        code = self.code_editor.get_code()
        if not code.strip():
            return
        try:
            tree = ast.parse(code)
        except SyntaxError:
            logger.error("代码语法错误，无法分析依赖。")
            return
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split('.')[0])
        external_packages = imported_modules - BUILTIN_MODULES
        resolved_packages = {
            MODULE_TO_PACKAGE_MAP.get(mod, mod)
            for mod in external_packages
        }
        current_text = self.requirements_edit.toPlainText()
        if not current_text.strip() and not resolved_packages:
            return
        other_lines, package_lines = self._parse_requirements_lines(current_text)
        current_pkg_names = set(package_lines.keys())
        needed_pkgs = {pkg.lower() for pkg in resolved_packages}
        kept_package_lines = [
            package_lines[pkg] for pkg in needed_pkgs if pkg in package_lines
        ]
        new_pkgs = needed_pkgs - current_pkg_names
        new_package_lines = sorted([pkg for pkg in resolved_packages if pkg.lower() in new_pkgs])
        all_lines = other_lines + kept_package_lines + new_package_lines
        updated_text = '\n'.join(all_lines)
        if updated_text == current_text:
            return
        if not self._updating_requirements_from_analysis:
            self._updating_requirements_from_analysis = True
            code_cursor = self.code_editor.code_editor.textCursor()
            pos = code_cursor.position()
            self.requirements_edit.setPlainText(updated_text)
            code_cursor.setPosition(pos + len(updated_text) - len(current_text))
            self.code_editor.code_editor.setTextCursor(code_cursor)
            self._updating_requirements_from_analysis = False

    def _parse_requirements_lines(self, text):
        lines = []
        package_lines = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                lines.append(line)
                continue
            match = re.match(r'^([a-zA-Z0-9._-]+)', stripped)
            if match:
                pkg_name = match.group(1).lower()
                if pkg_name not in package_lines:
                    package_lines[pkg_name] = line
            else:
                lines.append(line)
        return lines, package_lines

    def _save_component(self, delete_original_file: bool = True):
        if self._saving:
            return
        self._saving = True
        try:
            name = self.name_edit.text().strip()
            category = self.category_edit.currentText().strip()
            if not name or not category:
                MessageManager.warning("请输入组件名称和分类！", "", self)
                return
            code = self.code_editor.get_code()
            if not code.strip():
                MessageManager.warning("请输入组件代码！", "", self)
                return
            try:
                ast.parse(code)
            except SyntaxError as e:
                error_msg = f"代码第 {e.lineno} 行：{e.msg}"
                MessageManager.error(f"代码存在语法错误，无法保存！\n{error_msg}", "语法错误", self)
                return
            except Exception as e:
                MessageManager.error(f"代码解析失败：{e}", "解析错误", self)
                return

            self._save_component_to_file(category, name, code, self._current_component_file, delete_original_file)

            if self._current_component_file:
                current_signature = {
                    "inputs": self.input_port_editor.get_ports(serialize=True),
                    "outputs": self.output_port_editor.get_ports(serialize=True),
                    "properties": self.property_editor.get_properties(serialize=True),
                }
                ComponentHistoryManager.save_history(
                    component_file_path=self._current_component_file,
                    component_name=name,
                    code=code,
                    current_signature=current_signature
                )
                self._load_history_list(self._current_component_file)
                QTimer.singleShot(1000, lambda: self._load_component_filepath(self._current_component_file))

            MessageManager.success("组件保存成功！", "", self)
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"保存组件失败: {str(e)}", "", self)
        finally:
            self._saving = False

    def save_component_by_full_path(self, full_path: str, new_code: str):
        try:
            if full_path not in self.component_tree._components:
                MessageManager.error("组件不存在，无法保存", "", self)
                return
            comp_obj = self.component_tree._components[full_path]
            name = getattr(comp_obj, 'name', '未命名组件')
            category = getattr(comp_obj, 'category', '数据处理')
            source_file = getattr(comp_obj, '_source_file', None)
            if not source_file or not Path(source_file).exists():
                MessageManager.error("组件源文件不存在，无法保存", "", self)
                return
            try:
                ast.parse(new_code)
            except SyntaxError as e:
                error_msg = f"代码第 {e.lineno} 行：{e.msg}"
                MessageManager.error(f"代码存在语法错误，无法保存！\n{error_msg}", "语法错误", self)
                return
            source_file = Path(source_file)
            final_code = new_code
            with open(source_file, 'w', encoding='utf-8') as f:
                f.write(final_code)
            current_signature = {
                "inputs": getattr(comp_obj, 'inputs', []),
                "outputs": getattr(comp_obj, 'outputs', []),
                "properties": getattr(comp_obj, 'properties', {}),
            }
            def serialize_port(p):
                return {
                    "name": p.name,
                    "label": p.label,
                    "type": p.type.name if hasattr(p.type, 'name') else str(p.type),
                    "connection": getattr(p, 'connection', ConnectionType.SINGLE).name
                } if hasattr(p, 'name') else p
            def serialize_property(prop_dict):
                if isinstance(prop_dict, dict):
                    return prop_dict
                return {
                    "type": prop_dict.type.name,
                    "default": prop_dict.default,
                    "label": prop_dict.label,
                    "choices": getattr(prop_dict, 'choices', []),
                    "min": getattr(prop_dict, 'min', 0),
                    "max": getattr(prop_dict, 'max', 100),
                    "step": getattr(prop_dict, 'step', 1),
                    "schema": getattr(prop_dict, 'schema', {}),
                }
            sig = {
                "inputs": [serialize_port(p) for p in current_signature["inputs"]],
                "outputs": [{"name": p.name, "label": p.label, "type": p.type.name} for p in current_signature["outputs"]],
                "properties": {k: serialize_property(v) for k, v in current_signature["properties"].items()}
            }
            ComponentHistoryManager.save_history(
                component_file_path=source_file,
                component_name=name,
                code=new_code,
                current_signature=sig
            )
            QTimer.singleShot(1000, lambda: self._load_component_filepath(source_file))
            MessageManager.success(f"组件已保存：{name}", "", self)
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"保存失败: {str(e)}", "", self)

    def _save_component_to_file(self, category, name, code, original_file_path=None, delete_original_file=True):
        components_dir = Path(resource_path("app")) / "components" / category
        components_dir.mkdir(parents=True, exist_ok=True)
        if delete_original_file and original_file_path and (components_dir / original_file_path.name).exists():
            original_file_path.unlink()
            filepath = original_file_path
        elif delete_original_file and original_file_path and not (components_dir / original_file_path.name).exists():
            shutil.move(str(original_file_path), str(components_dir))
            filepath = components_dir / original_file_path.name
        else:
            filename = f"{str(uuid.uuid4()).replace(' ', '_').lower()}.py"
            filepath = components_dir / filename
        if not code.startswith("try:"):
            code = COMPONENT_IMPORT_CODE + code
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        self._current_component_file = filepath

    def _cancel_edit(self):
        w = MessageBox("确认", "确定要取消编辑吗？未保存的更改将丢失。", self.window())
        if w.exec():
            self.component_info.clear_all()
            self.code_editor.set_code(DEFAULT_NODE_TEMPLATE)
            self._current_component_file = None
            self.component_tree.set_current_editing_component(None)

    def _load_history_list(self, component_file_path: Path):
        self.history_table.setRowCount(0)
        histories = ComponentHistoryManager.load_histories(component_file_path)
        for history in reversed(histories):
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            version_item = QTableWidgetItem(history['version'])
            version_item.setFlags(version_item.flags() & ~Qt.ItemIsEditable)
            self.history_table.setItem(row, 0, version_item)
            time_item = QTableWidgetItem(history['timestamp'])
            time_item.setFlags(time_item.flags() & ~Qt.ItemIsEditable)
            self.history_table.setItem(row, 1, time_item)
            desc = history.get('description', '')
            desc_item = QTableWidgetItem(desc)
            self.history_table.setItem(row, 2, desc_item)

    def _load_history_code(self, item):
        row = item.row()
        if self._current_component_file:
            histories = ComponentHistoryManager.load_histories(self._current_component_file)
            if 0 <= row < len(histories):
                history_data = histories[len(histories) - 1 - row]
                if history_data and 'code' in history_data:
                    code = history_data['code']
                    self.code_editor.replace_text_preserving_view(code)
                    logger.info(f"已加载历史版本: {history_data['version']} - {history_data['timestamp']}")
                else:
                    logger.error("历史记录数据不完整，无法加载代码。")
            else:
                logger.error("无效的历史记录行。")
        else:
            logger.error("当前没有加载的组件文件，无法加载历史代码。")

    def _on_history_description_changed(self, item):
        if not self._current_component_file or item.column() != 2:
            return
        row = item.row()
        new_desc = item.text()
        histories = ComponentHistoryManager.load_histories(self._current_component_file)
        real_index = len(histories) - 1 - row
        if 0 <= real_index < len(histories):
            histories[real_index]['description'] = new_desc
            history_file = ComponentHistoryManager.get_history_file_path(self._current_component_file)
            try:
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(histories, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error(f"保存说明失败: {e}")
                MessageManager.error("保存说明失败", str(e), self)