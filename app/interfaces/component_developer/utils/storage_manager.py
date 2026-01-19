# -*- coding: utf-8 -*-
import ast
import shutil
import traceback
import uuid
from pathlib import Path

from PyQt5.QtCore import QTimer
from loguru import logger

from app.components.base import COMPONENT_IMPORT_CODE, ConnectionType, ArgumentType
from app.interfaces.component_developer.utils.component_history_manager import ComponentHistoryManager
from app.interfaces.component_developer.utils.message_manager import MessageManager
from app.scan_components import resource_path, ComponentScanner


# =================================================================
# 存储管理核心 (ComponentStorageManager)
# 负责：多级目录映射、物理保存、克隆迁移、旧文件清理
# =================================================================
class ComponentStorageManager:
    _saving = False

    def __init__(self, parent):
        self.parent = parent
        self.editor = self.parent.code_editor
        self._current_component_file = None
        self._current_component_code = ""  # 存储当前加载的代码
        self.base_dir = Path(resource_path("app/components/custom"))
        self.scanner = ComponentScanner()

    def _on_component_created(self, component_info):
        self.parent.requirements_edit.setText("")
        self._create_new_component(component_info)
        self._save_component()

    def _on_component_pasted(self, full_path):
        self._load_component(full_path=full_path, component=self.parent.component_tree._copied_component)
        # 源码路径修改
        source_file = f"{str(uuid.uuid4())}.py"
        self._current_component_file = self._current_component_file.parent / source_file
        self._save_component(delete_original_file=False)

    def _create_new_component(self, component_info):
        self.parent.name_edit.setText(component_info["name"])
        self.parent.category_edit.setText(component_info["category"])
        self.parent.description_edit.setText(component_info["description"])
        self.parent.input_port_editor.set_ports([])
        self.parent.output_port_editor.set_ports([])
        self.parent.property_editor.set_properties({})
        template = self.parent.apply_component_info_to_code(self.parent.current_template_code, component_info)
        self._current_component_code = template
        self.editor.replace_text_preserving_view(template)
        self._current_component_file = None

    def _load_component_filepath(self, component_path: Path):
        file_map = {value: key for key, value in self.scanner.get_file_maps().items()}
        full_path = file_map.get(Path(component_path))
        QTimer.singleShot(300, lambda: self.parent.update_usage_table(self.scanner.get_component(full_path).uuid))
        QTimer.singleShot(300, lambda: self._load_component(full_path))

    def _load_component(self, full_path=None, component=None, uuid=None):
        try:
            if uuid is not None:
                component = self.scanner.get_component_by_uuid(uuid)
            component = component or self.scanner.get_component(full_path)
            full_path = full_path or f"{component.category}/{component.name}"
            if full_path:
                category = "/".join(full_path.split("/")[:-1])
            else:
                category = getattr(component, 'category', '')
            self.parent.component_tree.set_current_editing_component(full_path)
            self.parent.name_edit.setText(getattr(component, 'name', ''))
            self.parent.category_edit.setText(category)
            self.parent.description_edit.setText(getattr(component, 'description', ''))
            self.parent.requirements_edit.setText(getattr(component, 'requirements', '').replace(',', '\n'))
            inputs = getattr(component, 'inputs', [])
            self.parent.input_port_editor.set_ports([
                {
                    "name": port.name,
                    "label": port.label,
                    "type": getattr(port, 'type', ArgumentType.TEXT),
                    "connection": getattr(port, 'connection', ConnectionType.SINGLE),
                }
                for port in inputs
            ])
            outputs = getattr(component, 'outputs', [])
            self.parent.output_port_editor.set_ports([
                {"name": port.name, "label": port.label, "type": getattr(port, 'type', 'text')}
                for port in outputs
            ])
            properties = getattr(component, 'properties', {})
            self.parent.property_editor.set_properties(properties)

            source_file = getattr(component, '_source_file', None)
            source_code = self.extract_class_source_from_file(source_file, component.__name__)
            source_code = self.parent.apply_component_info_to_code(
                source_code, {
                    "name": getattr(component, 'name', ''),
                    "category": getattr(component, 'category', ''),
                    "description": getattr(component, 'description', ''),
                    "requirements": getattr(component, 'requirements', '')
                }
            )
            self._current_component_file = Path(source_file)
            self._current_component_code = source_code
            self.parent.code_editor.set_code(source_code)

            # ⚠️ 不再调用 _sync_basic_info_to_code（会覆盖代码！）
            if self._current_component_file:
                self.parent._load_history_list(self._current_component_file)
            else:
                self.parent.history_table.setRowCount(0)
            QTimer.singleShot(300, lambda: self.parent.update_usage_table(component.uuid))
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"加载组件失败: {str(e)}", "", self.parent)


    def _save_component(self, delete_original_file: bool = True):
        if self._saving:
            return
        self._saving = True
        try:
            self.parent.analyze_code_for_requirements()
            self.parent.sync_basic_info_to_code()
            name = self.parent.name_edit.text().strip()
            category = self.parent.category_edit.currentText().strip()
            if not name or not category:
                MessageManager.warning("请输入组件名称和分类！", "", self.parent)
                return
            code = self.parent.code_editor.get_code()
            if not code.strip():
                MessageManager.warning("请输入组件代码！", "", self.parent)
                return
            try:
                ast.parse(code)
            except SyntaxError as e:
                error_msg = f"代码第 {e.lineno} 行：{e.msg}"
                MessageManager.error(f"代码存在语法错误，无法保存！\n{error_msg}", "语法错误", self.parent)
                return
            except Exception as e:
                MessageManager.error(f"代码解析失败：{e}", "解析错误", self.parent)
                return

            self._save_component_to_file(category, name, code, self._current_component_file, delete_original_file)
            if self._current_component_file:
                current_signature = {
                    "inputs": self.parent.input_port_editor.get_ports(serialize=True),
                    "outputs": self.parent.output_port_editor.get_ports(serialize=True),
                    "properties": self.parent.property_editor.get_properties(serialize=True),
                }
                ComponentHistoryManager.save_history(
                    component_file_path=self._current_component_file,
                    component_name=name,
                    code=code,
                    current_signature=current_signature
                )
                self.parent._load_history_list(self._current_component_file)
            QTimer.singleShot(
                1000, lambda: self._load_component(full_path=f"{category}/{name}", uuid=self._current_component_file.stem)
            )
            MessageManager.success("组件保存成功！", "", self.parent)
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"保存组件失败: {str(e)}", "", self.parent)
        finally:
            self._saving = False

    def save_component_by_full_path(self, full_path: str, new_code: str):
        try:
            if full_path not in self.parent.component_tree._components:
                MessageManager.error("组件不存在，无法保存", "", self.parent)
                return
            comp_obj = self.parent.component_tree._components[full_path]
            name = getattr(comp_obj, 'name', '未命名组件')
            source_file = getattr(comp_obj, '_source_file', None)
            if not source_file or not Path(source_file).exists():
                MessageManager.error("组件源文件不存在，无法保存", "", self.parent)
                return
            try:
                ast.parse(new_code)
            except SyntaxError as e:
                error_msg = f"代码第 {e.lineno} 行：{e.msg}"
                MessageManager.error(f"代码存在语法错误，无法保存！\n{error_msg}", "语法错误", self.parent)
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
                "outputs": [{"name": p.name, "label": p.label, "type": p.type.name} for p in
                            current_signature["outputs"]],
                "properties": {k: serialize_property(v) for k, v in current_signature["properties"].items()}
            }
            ComponentHistoryManager.save_history(
                component_file_path=source_file,
                component_name=name,
                code=new_code,
                current_signature=sig
            )
            MessageManager.success(f"组件已保存：{name}", "", self.parent)
        except Exception as e:
            logger.error(traceback.format_exc())
            MessageManager.error(f"保存失败: {str(e)}", "", self.parent)

    def _save_component_to_file(self, category, name, code, original_file_path=None, delete_original_file=True):
        # 代码增加导入前缀
        if not code.startswith("try:"):
            code = COMPONENT_IMPORT_CODE + code
        # 判断是否为组件修改
        components_dir = Path(resource_path("app")) / "components" / category
        components_dir.mkdir(parents=True, exist_ok=True)
        if original_file_path and components_dir / original_file_path.name == original_file_path:
            with open(original_file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            return
        # 判断是否为组件移动
        if delete_original_file and original_file_path and (components_dir / original_file_path.name).exists():
            original_file_path.unlink()
            filepath = original_file_path
        elif delete_original_file and original_file_path and not (components_dir / original_file_path.name).exists():
            shutil.move(str(original_file_path), str(components_dir))
            filepath = components_dir / original_file_path.name
        else:
            filename = f"{str(uuid.uuid4()).replace(' ', '_').lower()}.py"
            filepath = components_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        self._current_component_file = filepath

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