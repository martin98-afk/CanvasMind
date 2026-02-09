# -*- coding: utf-8 -*-
import ast
import re
import textwrap
import traceback

from PyQt5.QtCore import QObject, QTimer
from loguru import logger

from app.components.base import PropertyType, ArgumentType, ConnectionType
from app.interfaces.component_developer.utils.message_manager import MessageManager


class SyncUItoCode(QObject):

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.editor = parent.code_editor
        self._property_sync_timer = QTimer()
        self._property_sync_timer.setSingleShot(True)
        self._property_sync_timer.setInterval(300)  # 300ms 防抖
        self._property_sync_timer.timeout.connect(self._sync_properties_to_code)

    def _on_property_changed(self):
        # 防抖：连续变更时只在停顿后同步
        self._property_sync_timer.start()

    def apply_component_info_to_code(self, code: str, component_info: dict) -> str:
        """将 component_info 中的基本信息应用到代码中"""
        name = component_info["name"]
        category = component_info["category"]
        description = component_info.get("description", "")
        requirements = component_info.get("requirements", "")
        return self._update_basic_info_in_code(code, name, category, description, requirements)

    def _sync_basic_info_to_code(self):
        try:
            current_code = self.editor.get_code()
            if not current_code.strip():
                return
            updated_code = self._update_basic_info_in_code(
                current_code,
                self.parent.name_edit.text(),
                self.parent.category_edit.currentText(),
                self.parent.description_edit.toPlainText(),
                self.parent.requirements_edit.toPlainText().replace("\n", ",")
            )
            if updated_code != current_code:
                self.editor.replace_text_preserving_view(updated_code)
                self._current_component_code = updated_code
        except Exception as e:
            logger.error(f"同步基本信息失败: {e}")

    def _sync_properties_to_code(self):
        try:
            current_code = self.editor.get_code()
            if not current_code.strip():
                return
            updated_code = self._update_properties_in_code(
                current_code,
                self.parent.property_editor.get_properties()
            )
            if updated_code != current_code:
                self.editor.suspend_sync()
                try:
                    self.editor.replace_text_preserving_view(updated_code)
                    self._current_component_code = updated_code
                finally:
                    self.editor.resume_sync()
        except Exception as e:
            MessageManager.error(f"同步属性到代码失败: {e}", "", self.parent)

    def _sync_ports_to_code(self):
        try:
            current_code = self.editor.get_code()
            if not current_code.strip():
                return
            updated_code = self._update_ports_in_code(
                current_code,
                self.parent.input_port_editor.get_ports(),
                self.parent.output_port_editor.get_ports()
            )
            if updated_code != current_code:
                self.editor.suspend_sync()
                try:
                    self.editor.replace_text_preserving_view(updated_code)
                    self._current_component_code = updated_code
                finally:
                    self.editor.resume_sync()
        except Exception as e:
            traceback.print_exc()
            MessageManager.error(f"同步端口到代码失败: {e}", "", self.parent)

    def _generate_port_def_code(self, port, is_input=True):
        """辅助方法：生成单个端口定义的 Python 代码字符串"""
        if not isinstance(port["type"], ArgumentType):
            return ""

        # 1. 基础字段
        args = [
            f'name="{port["name"]}"',
            f'label="{port["label"]}"',
            f'type=ArgumentType.{port["type"].name}'
        ]

        # 2. sub_type (当类型为 OBJECT 或明确指定了 sub_type 时)
        # 即使不是 OBJECT，如果用户设置了 sub_type，同步进去也无妨，或者你可以加判断:
        # if port["type"] == ArgumentType.OBJECT and port.get("sub_type"):
        if port.get("sub_type"):
            args.append(f'sub_type="{port["sub_type"]}"')

        # 3. connection (仅 Input 有效)
        if is_input:
            conn = port.get('connection', ConnectionType.SINGLE)
            # 兼容处理：conn 可能是 Enum 对象，也可能是默认值
            conn_name = getattr(conn, 'name', ConnectionType.SINGLE.name)
            args.append(f'connection=ConnectionType.{conn_name}')

        # 4. description (如果有且不为空)
        desc = port.get("description", "")
        if desc:
            # 防止描述中包含双引号导致代码语法错误
            safe_desc = desc.replace('"', '\\"')
            args.append(f'description="{safe_desc}"')

        return f"        PortDefinition({', '.join(args)}),"

    def _update_ports_in_code(self, code, input_ports, output_ports):
        """更新代码中的 inputs 和 outputs 列表"""
        lines = code.split('\n')
        new_lines = []
        i = 0
        inputs_replaced = False
        outputs_replaced = False

        while i < len(lines):
            line = lines[i]

            # --- 处理 Inputs ---
            if (not inputs_replaced and re.search(r'^\s*inputs\s*=\s*\[', line)):
                new_lines.append("    inputs = [")
                for port in input_ports:
                    port_code = self._generate_port_def_code(port, is_input=True)
                    if port_code:
                        new_lines.append(port_code)
                new_lines.append("    ]")
                inputs_replaced = True

                # 跳过旧的代码块直到 ']'
                bracket_count = line.count('[') - line.count(']')
                j = i + 1
                while j < len(lines) and bracket_count > 0:
                    bracket_count += lines[j].count('[') - lines[j].count(']')
                    j += 1
                i = j

            # --- 处理 Outputs ---
            elif (not outputs_replaced and re.search(r'^\s*outputs\s*=\s*\[', line)):
                new_lines.append("    outputs = [")
                for port in output_ports:
                    # Output 一般不需要 connection，这里 is_input=False
                    port_code = self._generate_port_def_code(port, is_input=False)
                    if port_code:
                        new_lines.append(port_code)
                new_lines.append("    ]")
                outputs_replaced = True

                # 跳过旧的代码块直到 ']'
                bracket_count = line.count('[') - line.count(']')
                j = i + 1
                while j < len(lines) and bracket_count > 0:
                    bracket_count += lines[j].count('[') - lines[j].count(']')
                    j += 1
                i = j

            else:
                new_lines.append(line)
                i += 1

        # --- 如果代码中原来没有 inputs/outputs 定义，则尝试插入 ---
        # 插入逻辑保持不变：在 class 定义后插入
        if not inputs_replaced:
            for idx, l in enumerate(new_lines):
                if l.strip().startswith('class '):
                    new_lines.insert(idx + 1, "    inputs = []")
                    break
        if not outputs_replaced:
            for idx, l in enumerate(new_lines):
                # 尝试插在 inputs 后面
                if l.strip().startswith('class '):
                    # 简单的启发式查找：如果在 inputs 定义后插入
                    insert_pos = idx + 1
                    if idx + 1 < len(new_lines) and 'inputs' in new_lines[idx + 1]:
                        # 如果下一行就是 inputs，还要算上 inputs 的长度吗？
                        # 原代码这里的逻辑比较简单，假设 inputs 是一行。
                        # 更稳妥的是再次扫描，但这里保持原逻辑微调
                        # 建议直接放在 properties 前面或者 inputs 后面
                        # 这里简单处理：如果没找到 outputs，强行插在 inputs 后面
                        new_lines.insert(insert_pos + 1, "    outputs = []")
                    else:
                        new_lines.insert(insert_pos + 1, "    outputs = []")
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
                        # 兼容 dict 和 对象 两种传参方式
                        if isinstance(prop_def, dict):
                            prop_type = prop_def.get('type', PropertyType.TEXT)
                            default_value = prop_def.get('default', '')
                            label = prop_def.get('label', prop_name)
                            description = prop_def.get('description', '')
                            choices = prop_def.get('choices', [])
                            schema = prop_def.get('schema', {})
                            min_val = prop_def.get('min', 0)
                            max_val = prop_def.get('max', 100)
                            step_val = prop_def.get('step', 1)
                        else:
                            prop_type = getattr(prop_def, 'type', PropertyType.TEXT)
                            default_value = getattr(prop_def, 'default', '')
                            label = getattr(prop_def, 'label', prop_name)
                            description = getattr(prop_def, 'description', '')
                            choices = getattr(prop_def, 'choices', [])
                            schema = getattr(prop_def, 'schema', {})
                            min_val = getattr(prop_def, 'min', 0)
                            max_val = getattr(prop_def, 'max', 100)
                            step_val = getattr(prop_def, 'step', 1)

                        if prop_type == PropertyType.DYNAMICFORM:
                            new_lines.append(f'        "{prop_name}": PropertyDefinition(')
                            new_lines.append(f'            type=PropertyType.DYNAMICFORM,')
                            new_lines.append(f'            label="{label}",')
                            if description:
                                new_lines.append(f'            description="{description}",')
                            if schema:
                                new_lines.append('            schema={')
                                for field_name, field_def in schema.items():
                                    if not isinstance(field_def, dict):
                                        field_def = field_def.dict()
                                    field_type = field_def.get('type', PropertyType.TEXT)
                                    field_default = field_def.get('default', '')
                                    field_label = field_def.get('label', field_name)
                                    field_description = field_def.get('description', '')
                                    field_choices = field_def.get('choices', [])
                                    new_lines.append(f'                "{field_name}": PropertyDefinition(')
                                    new_lines.append(f'                    type=PropertyType.{field_type.name},')

                                    # 处理默认值格式化
                                    if field_type == PropertyType.INT:
                                        fv = str(int(field_default)) if field_default else "0"
                                    elif field_type == PropertyType.FLOAT:
                                        fv = str(float(field_default)) if field_default else "0.0"
                                    elif field_type == PropertyType.BOOL:
                                        fv = "True" if str(field_default).lower() in ("true", "1", "yes") else "False"
                                    elif field_type == PropertyType.LONGTEXT:
                                        if field_default:
                                            safe_text = field_default.replace('"""', '\\"\\"\\"')
                                            fv = '"""' + textwrap.dedent(safe_text) + '"""'
                                        else:
                                            fv = '""""""'
                                    else:
                                        fv = f'"{field_default}"'

                                    new_lines.append(f'                    default={fv},')
                                    new_lines.append(f'                    label="{field_label}",')
                                    if field_description:
                                        new_lines.append(f'                    description="{field_description}",')
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
                            # 处理普通属性默认值
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
                            if description:
                                new_lines.append(f'            description="{description}",')
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
                        # 尝试插在 outputs 后面，如果找不到 outputs 则插在 class 定义后较远位置
                        # 这里简单插在第4行（假设有 name/category/inputs/outputs）
                        # 最好是找到最后一个字段赋值的地方
                        new_lines.insert(idx + 5, "    properties = {}")
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
                return code

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
                            start_line = stmt.lineno - 1
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

            new_lines = lines[:]
            for start, end, new_content in sorted(replacements, reverse=True):
                new_lines = new_lines[:start] + new_content + new_lines[end + 1:]

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
                class_lineno = target_class.lineno - 1
                new_lines = new_lines[:class_lineno + 1] + missing + new_lines[class_lineno + 1:]

            return '\n'.join(new_lines)
        except Exception as e:
            logger.error(f"Error in _update_basic_info_in_code: {e}")
            logger.error(traceback.format_exc())
            return code