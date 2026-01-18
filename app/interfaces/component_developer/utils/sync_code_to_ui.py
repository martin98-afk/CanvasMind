# -*- coding: utf-8 -*-
import ast
import re

from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from loguru import logger

# 导入业务基础组件
from app.interfaces.component_developer.constants import MODULE_TO_PACKAGE_MAP, BUILTIN_MODULES


# =================================================================
# 同步引擎核心 (ComponentSyncEngine)
# 负责：代码与UI双向转换、正则替换、AST解析
# =================================================================
class SyncCodeToUI(QObject):
    """
    同步引擎核心 (ComponentSyncEngine)
    负责：代码与UI双向转换、正则替换、AST解析
    """
    _updating_requirements_from_analysis = False

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.code_editor = parent.code_editor
        # --- 添加一个定时器用于延迟分析 ---
        self._analysis_timer = QTimer()
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.timeout.connect(self._analyze_code_for_requirements)

        self._code_to_ui_sync_timer = QTimer()
        self._code_to_ui_sync_timer.setSingleShot(True)
        self._code_to_ui_sync_timer.setInterval(300)
        self._code_to_ui_sync_timer.timeout.connect(self._sync_code_to_ui)

    def _on_code_text_changed(self):
        current_text = self.code_editor.get_code()
        # ✅ 触发代码 → UI 同步
        self._code_to_ui_sync_timer.start()

    def _extract_component_info_from_code_str(self, code: str):
        """
        从代码中提取组件基本信息。
        如果 AST 解析失败或未找到有效字段，返回 None。
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return None  # ✅ 不返回默认值

        info = {}
        found_any = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "name" and isinstance(node.value, ast.Constant):
                            info["name"] = str(node.value.value)
                            found_any = True
                        elif target.id == "category" and isinstance(node.value, ast.Constant):
                            info["category"] = str(node.value.value)
                            found_any = True
                        elif target.id == "description" and isinstance(node.value, ast.Constant):
                            info["description"] = str(node.value.value)
                            found_any = True
                        elif target.id == "requirements" and isinstance(node.value, ast.Constant):
                            info["requirements"] = str(node.value.value)
                            found_any = True

        # 只有至少找到一个字段，才认为有效
        if found_any:
            return info
        else:
            return None  # ✅ 未找到任何有效字段，也视为失败

    def _sync_code_to_ui(self):
        """从代码解析并更新 UI（安全、防崩溃）"""
        code = self.code_editor.get_code()
        if not code.strip():
            return
        try:
            info = self._extract_component_info_from_code_str(code)
            if info is None:
                # ✅ AST 解析失败或无有效字段，不更新 UI
                return

            # 设置默认值（仅用于缺失字段，而不是整体失败）
            name = info.get("name", "")
            category = info.get("category", "")
            description = info.get("description", "")
            requirements = info.get("requirements", "")

            # 临时阻断信号，防止循环
            self.parent.name_edit.blockSignals(True)
            self.parent.category_edit.blockSignals(True)
            self.parent.description_edit.blockSignals(True)
            self.parent.requirements_edit.blockSignals(True)

            self.parent.name_edit.setText(name)
            self.parent.category_edit.setText(category)
            self.parent.description_edit.setPlainText(description)
            self.parent.requirements_edit.setPlainText(requirements.replace(',', '\n'))

            self.parent.name_edit.blockSignals(False)
            self.parent.category_edit.blockSignals(False)
            self.parent.description_edit.blockSignals(False)
            self.parent.requirements_edit.blockSignals(False)

            # ✅ 更新缓存
            self._current_component_code = code
        except Exception as e:
            logger.warning(f"代码 → UI 同步失败: {e}")

    def _analyze_code_for_requirements(self):
        """优化后的依赖分析：只增不减，保留手动添加的项和版本号"""
        code = self.code_editor.get_code()
        if not code.strip():
            return

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return

        # 1. 提取代码中所有的 import
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split('.')[0])

        # 2. 转换为实际包名并过滤标准库
        external_packages = {
            MODULE_TO_PACKAGE_MAP.get(mod, mod)
            for mod in imported_modules
            if mod not in BUILTIN_MODULES and mod != "app"  # 排除自身应用包
        }

        # 3. 获取 UI 现有的依赖（解析为字典 {包名: 原始行内容}）
        current_text = self.parent.requirements_edit.toPlainText()
        existing_reqs_map = {}  # key: lowercase_pkg_name, value: full_line

        lines = current_text.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            # 提取包名（支持 requests==2.0, requests>=2.0 等格式）
            match = re.match(r'^([a-zA-Z0-9._-]+)', stripped)
            if match:
                pkg_name = match.group(1).lower()
                existing_reqs_map[pkg_name] = line

        # 4. 合并逻辑：保留旧的，添加新的
        has_changed = False
        final_lines = list(lines)  # 先拷贝一份现有的

        for pkg in external_packages:
            pkg_lower = pkg.lower()
            if pkg_lower not in existing_reqs_map:
                # 发现新包，添加
                final_lines.append(pkg)
                existing_reqs_map[pkg_lower] = pkg  # 防止重复添加
                has_changed = True
                logger.info(f"检测到新依赖并添加: {pkg}")
            else:
                # 包已存在，不做任何操作（保留用户原有的版本号和格式）
                pass

        # 5. 更新 UI
        if has_changed:
            updated_text = '\n'.join(final_lines)
            # 避免正在编辑时刷新
            if not self._updating_requirements_from_analysis:
                self._updating_requirements_from_analysis = True
                self.parent.requirements_edit.setPlainText(updated_text)
                self._updating_requirements_from_analysis = False
                # 触发同步到代码
                self.parent.sync_basic_info_to_code()
