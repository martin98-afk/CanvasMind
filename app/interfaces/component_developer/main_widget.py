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
from app.interfaces.component_developer.component_history_manager import ComponentHistoryManager
from app.interfaces.component_developer.constants import *
from app.interfaces.component_developer.message_manager import MessageManager
from app.scan_components import ComponentUsageTracker
from app.scan_components import resource_path
from app.templates.component_templates import default_templates
from app.templates.component_templates.base import DEFAULT_NODE_TEMPLATE
from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.code_editor.code_editer import CodeEditorWidget
from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextRegistry
from app.widgets.side_dock_area.side_dock_area import SideDockArea
from app.widgets.tree_widget.component_develop_tree import ComponentTreePanel


class ComponentDeveloperPage(QWidget):
    """组件开发主界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.home = parent
        self.package_manager = self.home.package_manager
        self.setObjectName("ComponentDeveloperWidget")
        self._current_component_file = None
        self._current_component_code = ""  # 存储当前加载的代码
        self.context_register = ContextRegistry()
        self.context_register.register("当前代码", self.extract_current_code, lambda *args, **kwargs: None)
        self.context_register.register("当前选中区域", self.extract_selected_code, lambda *args, **kwargs: None)
        self._setup_ui()
        self._connect_signals()
        # --- 添加一个定时器用于延迟分析 ---
        self._analysis_timer = QTimer()
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.timeout.connect(self._analyze_code_for_requirements)
        # --- 添加一个标志，防止循环更新 ---
        self._updating_requirements_from_analysis = False

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 左侧：组件树和开发区域
        self.splitter = ModernSplitter(Qt.Horizontal)
        # --- 修改：左侧：组件树 ---
        self.component_tree_panel = ComponentTreePanel(self)
        self.component_tree = self.component_tree_panel.tree  # 保留对 tree 的直接引用（如果已有代码依赖）
        self.splitter.addWidget(self.component_tree_panel)  # 将新的左侧容器添加到    主分割器
        # --- 修改结束 ---
        # 代码编辑框
        code_widget = QWidget(self)
        code_layout = QVBoxLayout(code_widget)
        code_layout.setContentsMargins(0, 0, 0, 0)
        # 代码编辑器
        self.code_editor = CodeEditorWidget(self, self.package_manager.get_current_python_exe())
        # 保存按钮
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
        self.name_edit = self.component_info.name_edit  # Fixed expression
        self.category_edit = self.component_info.category_edit  # Fixed expression
        self.description_edit = self.component_info.description_edit  # Fixed expression
        self.requirements_edit = self.component_info.requirements_edit  # Fixed expression
        self.input_port_editor = self.component_info.input_port_editor
        self.output_port_editor = self.component_info.output_port_editor
        self.property_editor = self.component_info.property_editor
        self.history_table = self.side_dock_area.get_tool_instance("组件历史管理").history_table
        self.llm_chatter = self.side_dock_area.get_tool_instance("大模型对话")
        self.llm_chatter.set_system_prompt(LLM_CODE_CONTEXT)
        self.history_table.itemDoubleClicked.connect(self._load_history_code)
        self.splitter.addWidget(self.side_dock_area)
        # 先设置 stretch，让左侧可收缩
        self.splitter.setStretchFactor(0, 0)  # 左侧不拉伸
        self.splitter.setStretchFactor(1, 1)  # 中间拉伸
        self.splitter.setStretchFactor(2, 0)  # 右侧拉伸
        # 再设置一个“合理但小”的初始尺寸（避免 10 太小被忽略）
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)  # 50 比 10 更可能生效
        layout.addWidget(self.splitter)
        layout.addWidget(self.side_dock_area.tool_panel)
        
    def hide_splitter(self):
        """强制 splitter 回到默认尺寸，无视用户拖动历史"""
        self.splitter.setSizes(HIDE_SPLITTER_SIZES)
        self.splitter.update()

    def show_splitter(self):
        """强制 splitter 恢复到默认尺寸"""
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.splitter.update()

    def _connect_signals(self):
        """连接信号"""
        self.component_tree.component_selected.connect(self._load_component)
        self.component_tree.component_created.connect(self._on_component_created)
        self.component_tree.component_pasted.connect(self._on_component_pasted)
        # 连接编辑器改变信号
        self.input_port_editor.ports_changed.connect(self._sync_ports_to_code)
        self.output_port_editor.ports_changed.connect(self._sync_ports_to_code)  # 修复：连接输出端口信号
        self.property_editor.properties_changed.connect(self._sync_properties_to_code)
        self.code_editor.code_changed.connect(self._on_code_text_changed)
        # 连接基本信息改变信号
        self.name_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.category_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.description_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.requirements_edit.textChanged.connect(self._sync_basic_info_to_code)
        self.requirements_edit.textChanged.connect(self._on_requirements_text_changed)
        self.history_table.itemChanged.connect(self._on_history_description_changed)

    def extract_current_code(self) -> str:
        """返回带组件名称和完整代码的上下文字符串"""
        name = self.name_edit.text().strip() or "未命名组件"
        code = self.code_editor.get_code()
        if not code.strip():
            return f"{name} 全部代码", "代码为空", None
        return f"{name} 全部代码", code, None

    def extract_selected_code(self) -> str:
        """返回带组件名称、行号范围和选中代码的上下文字符串"""
        name = self.name_edit.text().strip() or "未命名组件"
        editor = self.code_editor.code_editor  # 假设这是 QPlainTextEdit 或类似
        cursor = editor.textCursor()

        if cursor.hasSelection():
            # 获取选中范围的起始/结束行号（从1开始）
            start_line = cursor.selectionStart()
            end_line = cursor.selectionEnd()
            doc = editor.document()
            start_block = doc.findBlock(start_line)
            end_block = doc.findBlock(end_line - 1)  # selectionEnd 是下一个字符位置
            start_line_num = start_block.blockNumber() + 1
            end_line_num = end_block.blockNumber() + 1

            selected_text = cursor.selectedText().replace('\u2029', '\n')  # PyQt5 用 \u2029 表示换行
            return f"{name} {start_line_num}~{end_line_num}行代码", selected_text, None
        else:
            # 未选中则返回完整代码（与 extract_current_code_for_llm 一致）
            code = self.code_editor.get_code()
            if not code.strip():
                return f"{name} 全部代码", "代码为空", None
            return f"{name} 全部代码", code, None

    def _switch_template(self, template_name, template_code):
        """根据选择的模板名称和代码更新编辑器"""
        self.code_editor.replace_text_preserving_view(template_code)
        self._current_component_code = template_code
        MessageManager.success(f"已切换到模板: {template_name}", "", self)

    def _load_existing_components(self):
        """加载现有组件"""
        try:
            self.component_tree.refresh_components()
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"加载组件失败: {e}", "", self)

    def _on_component_created(self, component_info):
        """组件创建回调"""
        self._create_new_component(component_info)
        self._save_component()

    def _on_component_pasted(self):
        """组件粘贴回调"""
        self._load_component(self.component_tree._copied_component)
        self._save_component(delete_original_file=False)

    def extract_class_source_from_file(self, file_path: Path, class_name: str) -> str:
        """从文件中提取指定类的源码（使用 ast）"""
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
        """根据文件路径重载组件"""
        file_map = {value: key for key, value in self.component_tree._file_map.items()}
        full_path = file_map.get(component_path)
        QTimer.singleShot(300, lambda: self.update_usage_table(full_path))
        self._load_component(full_path)

    def _load_component(self, full_path=None):
        """加载组件到编辑器"""
        try:
            self.component_tree.set_current_editing_component(full_path)
            component = self.component_tree._components[full_path]
            # 基本信息
            self.name_edit.setText(getattr(component, 'name', ''))
            self.category_edit.setText(getattr(component, 'category', ''))
            self.description_edit.setText(getattr(component, 'description', ''))
            self.requirements_edit.setText(getattr(component, 'requirements', '').replace(',', '\n'))
            # 加载输入端口
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
                source_file = getattr(component, '_source_file', None)
                source_code = self.extract_class_source_from_file(source_file, component.__name__)
                self._current_component_file = Path(source_file)
                self._current_component_code = source_code  # 存储当前加载的代码
                self.code_editor.set_code(source_code)
            except:
                # 如果无法获取源码，使用默认模板
                template = DEFAULT_NODE_TEMPLATE
                template = template.replace("Component", component.__name__)
                template = template.replace("我的组件", getattr(component, 'name', ''))
                template = template.replace("数据处理", getattr(component, 'category', ''))
                template = template.replace("这是一个示例组件", getattr(component, 'description', ''))
                self._current_component_code = template  # 存储当前加载的代码
                self.code_editor.replace_text_preserving_view(template)
                # 对于新建的，原始文件路径为 None
                self._current_component_file = None
            self._sync_basic_info_to_code()
            # --- 新增：加载历史记录列表 ---
            if self._current_component_file:
                self._load_history_list(self._current_component_file)
            else:
                self.history_table.setRowCount(0)  # 如果没有文件路径，清空历史列表
            # --- 新增结束 ---
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

            # ✅ 关键修复：断开旧连接，避免重复绑定
            try:
                history_tool.strategy_changed.disconnect(self._on_usage_strategy_changed)
            except TypeError:
                # 未连接过，忽略
                pass

            # 再连接
            history_tool.strategy_changed.connect(self._on_usage_strategy_changed)

            if history_tool:
                history_tool.update_usage_table(usage_list)

    def _on_usage_strategy_changed(self, canvas_path: str, node_name: str, strategy: str):
        """处理使用策略变更"""
        try:
            canvas_file = Path(canvas_path)
            # 1. 加载画布文件
            with open(canvas_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 2. 找到对应节点
            nodes = data.get("graph", {}).get("nodes", {})
            target_node_id = None
            for node_id, node_data in nodes.items():
                if node_data.get("name") == node_name:
                    # 更精确：用 full_path + node_name 判断（避免重名）
                    stable_key = data.get("runtime", {}).get("node_id2stable_key", {}).get(node_id, "")
                    full_path = stable_key.split("||")[0] if "||" in stable_key else ""
                    target_node_id = node_id
                    break

            if not target_node_id:
                MessageManager.warning("未找到对应节点", "", self)
                return

            # 3. 确定新版本
            if strategy == "同步":
                new_version = "latest"
            else:
                new_version = strategy  # 如 "V2"

            # 4. 更新节点 custom.version
            nodes[target_node_id].setdefault("custom", {})["version"] = new_version

            # 5. 保存回文件
            with open(canvas_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            MessageManager.success(f"已更新 {node_name} 的版本策略为 {new_version}", "", self)

        except Exception as e:
            import traceback
            logger.error(traceback.format_exc())
            MessageManager.error(f"更新策略失败: {e}", "", self)

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
        template = DEFAULT_NODE_TEMPLATE
        template = template.replace("我的组件", component_info["name"])
        template = template.replace("数据处理", component_info["category"])
        template = template.replace("这是一个示例组件", component_info["description"])
        self._current_component_code = template  # 存储当前加载的代码
        self.code_editor.replace_text_preserving_view(template)
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
            self.description_edit.text(),
            self.requirements_edit.toPlainText().replace("\n", ",")
        )
        if updated_code != current_code:
            self.code_editor.suspend_sync()
            try:
                self.code_editor.replace_text_preserving_view(updated_code)
            finally:
                self.code_editor.resume_sync()

    def _run_component_code(self):
        """运行当前编辑器中的组件代码"""
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
            # 更新代码编辑器（非破坏式，保持撤销/选择）
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            MessageManager.error(f"同步端口到代码失败: {e}", "", self)

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
            # 更新代码编辑器（非破坏式，保持撤销/选择）
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            MessageManager.error(f"同步属性到代码失败: {e}", "", self)

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
                self.description_edit.text(),
                self.requirements_edit.toPlainText().replace("\n", ",")
            )
            # 更新代码编辑器（非破坏式，保持撤销/选择）
            if updated_code != current_code:
                self.code_editor.suspend_sync()
                try:
                    self.code_editor.replace_text_preserving_view(updated_code)
                finally:
                    self.code_editor.resume_sync()
        except Exception as e:
            print(f"同步基本信息到代码失败: {e}")

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
                        f"        PortDefinition(name=\"{port['name']}\", label=\"{port['label']}\", "
                        f"type=ArgumentType.{port['type'].name}, "
                        f"connection=ConnectionType.{port.get('connection', ConnectionType.SINGLE.value).name}),")
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
                        f"        PortDefinition(name=\"{port['name']}\", label=\"{port['label']}\", type=ArgumentType.{port['type'].name}),")
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
        """更新代码中的属性定义（兼容 dict 和 PropertyDefinition 对象，支持 RANGE / LONGTEXT）"""
        try:
            lines = code.split('\n')
            new_lines = []
            i = 0
            properties_replaced = False
            while i < len(lines):
                line = lines[i]
                if not properties_replaced and re.search(r'^\s*properties\s*=\s*', line) and (
                        '{' in line or '{}' in line):
                    new_lines.append("    properties = {")
                    for prop_name, prop_def in properties.items():
                        # ✅ 统一提取字段：兼容 dict 和对象
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
                        # 处理 DYNAMICFORM
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
                            # 普通类型（包括 RANGE / LONGTEXT）
                            if prop_type == PropertyType.INT:
                                dv = str(int(default_value)) if default_value else "0"
                            elif prop_type == PropertyType.FLOAT:
                                dv = str(float(default_value)) if default_value else "0.0"
                            elif prop_type == PropertyType.BOOL:
                                dv = "True" if str(default_value).lower() in ("true", "1", "yes") else "False"
                            elif prop_type == PropertyType.LONGTEXT:
                                # ✅ 使用三引号包裹长文本
                                if default_value:
                                    # 转义三引号（简单处理）
                                    safe_text = default_value.replace('"""', '\\"\\"\\"')
                                    # 使用 textwrap.dedent 保持缩进整洁
                                    dv = '"""' + textwrap.dedent(safe_text) + '"""'
                                else:
                                    dv = '""""""'  # 空三引号
                            else:
                                dv = f'"{default_value}"'
                            new_lines.append(f'        "{prop_name}": PropertyDefinition(')
                            new_lines.append(f'            type=PropertyType.{prop_type.name},')
                            new_lines.append(f'            default={dv},')
                            new_lines.append(f'            label="{label}",')
                            # CHOICE 的 choices
                            if prop_type == PropertyType.CHOICE and choices:
                                choices_str = ', '.join([f'"{c}"' for c in choices])
                                new_lines.append(f'            choices=[{choices_str}]')
                            # RANGE 的 min, max, step
                            if prop_type == PropertyType.RANGE:
                                new_lines.append(f'            min={min_val},')
                                new_lines.append(f'            max={max_val},')
                                new_lines.append(f'            step={step_val},')
                            new_lines.append('        ),')
                    new_lines.append("    }")
                    properties_replaced = True
                    # 跳过原 properties 块（略）
                    if '{}' not in line:
                        bracket_count = line.count('{') - line.count('}')
                        j = i + 1
                        while j < len(lines) and bracket_count > 0:
                            bracket_count += lines[j].count('{') - lines[j].count('}')
                            j += 1
                        i = j
                    else:
                        j = i + 1
                        while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#')):
                            j += 1
                        if j < len(lines) and lines[j].strip() == '}':
                            i = j + 1
                        else:
                            i += 1
                else:
                    new_lines.append(line)
                    i += 1
            # 如果未找到 properties，插入默认（略）
            if not properties_replaced:
                for idx, l in enumerate(new_lines):
                    if l.strip().startswith('class ') and not any(
                            re.search(r'^\s*properties\s*=\s*', ll) for ll in new_lines[idx:]):
                        new_lines.insert(idx + 3, "    properties = {}")
                        break
            return '\n'.join(new_lines)
        except Exception as e:
            logger.error(f"_update_properties_in_code error: {e}")
            logger.error(traceback.format_exc())
            return code

    def _update_basic_info_in_code(self, code, name, category, description, requirements):
        """更新代码中的基本信息"""
        try:
            lines = code.split('\n')
            new_lines = []
            for i, line in enumerate(lines):
                if re.search(r'^\s*name\s*=\s*', line):
                    new_lines.append(f'    name = "{name}"')
                elif re.search(r'^\s*category\s*=\s*', line):
                    new_lines.append(f'    category = "{category}"')
                elif re.search(r'^\s*description\s*=\s*', line):
                    new_lines.append(f'    description = "{description}"')
                elif re.search(r'^\s*requirements\s*=\s*', line):
                    new_lines.append(f'    requirements = "{requirements}"')
                else:
                    new_lines.append(line)
                if ("requirements" not in code and len(requirements) > 0 and i > 1 and
                        re.search(r'^\s*description\s*=\s*', line)):
                    new_lines.append(f'    requirements = "{requirements}"')
            return '\n'.join(new_lines)
        except:
            return code

    # --- 新增：代码文本改变时启动分析定时器 ---
    def _on_code_text_changed(self):
        # 如果当前正在根据分析更新 requirements，不要再次触发分析
        if not self._updating_requirements_from_analysis:
            self._analysis_timer.start(2000)  # 2秒后分析

    # --- 新增：requirements 文本改变时停止分析定时器 ---
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
            return  # 空代码 + 空依赖，无需更新

        # 解析当前依赖
        other_lines, package_lines = self._parse_requirements_lines(current_text)
        current_pkg_names = set(package_lines.keys())

        # 代码中需要的包（标准化）
        needed_pkgs = {pkg.lower() for pkg in resolved_packages}

        # 要保留的包行：代码中仍需要的
        kept_package_lines = [
            package_lines[pkg] for pkg in needed_pkgs if pkg in package_lines
        ]
        # 新增的包（无版本）
        new_pkgs = needed_pkgs - current_pkg_names
        new_package_lines = sorted([pkg for pkg in resolved_packages if pkg.lower() in new_pkgs])

        # 重建内容：其他行 + 保留的包 + 新包
        all_lines = other_lines + kept_package_lines + new_package_lines
        updated_text = '\n'.join(all_lines)

        # 避免无意义更新
        if updated_text == current_text:
            return

        # 更新 UI（保留你的光标逻辑）
        if not self._updating_requirements_from_analysis:
            self._updating_requirements_from_analysis = True
            code_cursor = self.code_editor.code_editor.textCursor()
            pos = code_cursor.position()
            self.requirements_edit.setPlainText(updated_text)
            code_cursor.setPosition(pos + len(updated_text) - len(current_text))
            self.code_editor.code_editor.setTextCursor(code_cursor)
            self._updating_requirements_from_analysis = False

    def _parse_requirements_lines(self, text):
        """
        返回 (保留的行列表, 包名集合)
        保留用户原始行（含版本、注释等），但记录其包名用于比对
        """
        lines = []
        package_lines = {}  # pkg_name_lower -> original_line
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                lines.append(line)  # 保留空行和注释
                continue
            # 提取包名
            match = re.match(r'^([a-zA-Z0-9._-]+)', stripped)
            if match:
                pkg_name = match.group(1).lower()
                # 如果同一个包出现多次，保留第一个（或最后一个，按需）
                if pkg_name not in package_lines:
                    package_lines[pkg_name] = line
                # 不立即加入 lines，稍后按需保留
            else:
                # 无法识别的行（如 -e .），保留
                lines.append(line)
        return lines, package_lines

    def _save_component(self, delete_original_file: bool = True):
        """保存组件（带 AST 语法校验）"""
        try:
            # 验证基本信息
            name = self.name_edit.text().strip()
            category = self.category_edit.text().strip()
            if not name or not category:
                MessageManager.warning("请输入组件名称和分类！", "", self)
                return

            # 获取当前代码
            code = self.code_editor.get_code()
            if not code.strip():
                MessageManager.warning("请输入组件代码！", "", self)
                return

            # ✅ 新增：AST 语法校验
            try:
                ast.parse(code)
            except SyntaxError as e:
                # 提取错误信息（行号、错误描述）
                error_msg = f"代码第 {e.lineno} 行：{e.msg}"
                MessageManager.error(f"代码存在语法错误，无法保存！\n{error_msg}", "语法错误", self)
                return  # ⛔ 阻止保存
            except Exception as e:
                # 其他 AST 错误（理论上不会发生）
                MessageManager.error(f"代码解析失败：{e}", "解析错误", self)
                return

            # 保存到文件
            self._save_component_to_file(category, name, code, self._current_component_file, delete_original_file)

            # 保存历史记录
            if self._current_component_file:
                # ✅ 构建当前接口签名
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

            # 刷新组件树
            self.component_tree.refresh_components()
            MessageManager.success("组件保存成功！", "", self)

            # 重新加载当前组件
            self._load_component_filepath(self._current_component_file)

        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"保存组件失败: {str(e)}", "", self)

    def _save_component_to_file(self, category, name, code, original_file_path=None, delete_original_file=True):
        """保存组件到文件，可选择性地删除原始文件"""
        # 确保目录存在
        components_dir = Path(resource_path("app")) / "components" / category
        components_dir.mkdir(parents=True, exist_ok=True)
        # --- 删除原始文件 ---
        if delete_original_file and original_file_path and (components_dir / original_file_path.name).exists():
            # 删除原文件
            original_file_path.unlink()
            filepath = original_file_path
        elif delete_original_file and original_file_path and not (components_dir / original_file_path.name).exists():
            # 使用shutil将源文件移到新的组件目录
            shutil.move(str(original_file_path), str(components_dir))
            filepath = components_dir / original_file_path.name
        else:
            filename = f"{str(uuid.uuid4()).replace(' ', '_').lower()}.py"
            filepath = components_dir / filename

        # --- 检查并添加必要的导入语句 (仅保存到文件时) ---
        if not code.startswith("try:"):
            # 简单的检查，如果开头不是预期的导入，就添加
            code = COMPONENT_IMPORT_CODE + code

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
            self.requirements_edit.clear()
            self.input_port_editor.set_ports([])
            self.output_port_editor.set_ports([])
            self.property_editor.set_properties({})
            self.code_editor.set_code(DEFAULT_NODE_TEMPLATE)
            self._current_component_file = None
            self.component_tree.set_current_editing_component(None)

    # --- 新增：加载历史记录列表 ---
    def _load_history_list(self, component_file_path: Path):
        self.history_table.setRowCount(0)
        histories = ComponentHistoryManager.load_histories(component_file_path)
        for history in reversed(histories):
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            # 版本（只读）
            version_item = QTableWidgetItem(history['version'])
            version_item.setFlags(version_item.flags() & ~Qt.ItemIsEditable)
            self.history_table.setItem(row, 0, version_item)

            # 时间（只读）
            time_item = QTableWidgetItem(history['timestamp'])
            time_item.setFlags(time_item.flags() & ~Qt.ItemIsEditable)
            self.history_table.setItem(row, 1, time_item)

            # ✅ 说明（可编辑）
            desc = history.get('description', '')  # 默认空
            desc_item = QTableWidgetItem(desc)
            # 保持可编辑（默认 flags 包含 ItemIsEditable）
            self.history_table.setItem(row, 2, desc_item)

    def _load_history_code(self, item):
        """从历史记录列表项加载代码"""
        row = item.row()
        if self._current_component_file:
            histories = ComponentHistoryManager.load_histories(self._current_component_file)
            if 0 <= row < len(histories):
                history_data = histories[len(histories) - 1 - row]  # 因为列表是反向的
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
        """当历史记录的“说明”列被编辑时保存"""
        if not self._current_component_file:
            return

        # 只处理第 2 列（说明列）
        if item.column() != 2:
            return

        row = item.row()
        new_desc = item.text()

        # 获取历史记录（注意：表格是 reversed 的）
        histories = ComponentHistoryManager.load_histories(self._current_component_file)
        real_index = len(histories) - 1 - row  # 转换为原始索引
        if 0 <= real_index < len(histories):
            histories[real_index]['description'] = new_desc
            # 保存回文件
            history_file = ComponentHistoryManager.get_history_file_path(self._current_component_file)
            try:
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(histories, f, ensure_ascii=False, indent=4)
                logger.info(f"已更新版本 {histories[real_index]['version']} 的说明")
            except Exception as e:
                logger.error(f"保存说明失败: {e}")
                MessageManager.error("保存说明失败", str(e), self)