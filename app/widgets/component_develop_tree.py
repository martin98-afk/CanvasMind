import inspect
from pathlib import Path
from typing import Dict, Any

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QTreeWidgetItem,
    QMessageBox, QFileDialog,
    QDialog
)
from qfluentwidgets import (
    TreeWidget, RoundMenu, Action
)

from app.scan_components import scan_components
from app.widgets.new_component_dialog import NewComponentDialog


# --- 组件树控件 (未改动) ---
class ComponentTreeWidget(TreeWidget):
    """组件树控件 - 支持右键菜单"""
    component_selected = pyqtSignal(object)  # 选中组件信号
    component_created = pyqtSignal(dict)  # 创建组件信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._components = {}  # {full_path: component_class}
        self._copied_component = None

    def load_components(self, component_map: Dict[str, Any]):
        """加载组件到树中"""
        self.clear()
        self._components = component_map
        categories = {}
        # 按分类组织组件
        for full_path, comp_cls in component_map.items():
            try:
                category = getattr(comp_cls, 'category', 'General')
                name = getattr(comp_cls, 'name', comp_cls.__name__)
                display_path = f"{category}/{name}"
                if category not in categories:
                    cat_item = QTreeWidgetItem([category])
                    self.addTopLevelItem(cat_item)
                    categories[category] = cat_item
                else:
                    cat_item = categories[category]
                comp_item = QTreeWidgetItem([name])
                comp_item.setData(0, Qt.UserRole, display_path)
                comp_item.setData(1, Qt.UserRole, full_path)  # 原始路径
                cat_item.addChild(comp_item)
            except Exception as e:
                print(f"加载组件 {full_path} 失败: {e}")
        self.expandAll()

    def refresh_components(self):
        """刷新组件树"""
        # 重新扫描组件目录
        component_map = scan_components()
        self.load_components(component_map)

    def _show_context_menu(self, position):
        """显示右键菜单"""
        menu = RoundMenu(parent=self)

        # 获取右键点击的项
        item = self.itemAt(position)

        if item:
            # 如果点击的是子项（组件项）
            if item.parent():
                # 菜单用于编辑现有组件
                menu.addActions([
                    Action(text="✏️ 编辑组件", triggered=self._edit_component),
                    Action(text="📋 复制组件", triggered=self._copy_component),
                    Action(text="📌 粘贴组件", triggered=self._paste_component),
                    Action(text="📤 导出组件", triggered=self._export_component),
                    Action(text="🗑️ 删除组件", triggered=self._delete_component),
                    Action(text="🔄 刷新组件", triggered=self.refresh_components),
                ])
            else:
                # 如果点击的是父项（分类项）
                # 菜单用于在该分类下新建组件
                menu.addActions([
                    Action(text="🆕 新建组件", triggered=self._create_new_component),
                    Action(text="📋 复制组件", triggered=self._copy_component),
                    Action(text="📌 粘贴组件", triggered=self._paste_component),
                    Action(text="📤 导出组件", triggered=self._export_component),
                    Action(text="🗑️ 删除组件", triggered=self._delete_component),
                    Action(text="🔄 刷新组件", triggered=self.refresh_components),
                ])
        else:
            # 如果点击的是空白区域
            # 菜单用于新建组件（分类需要手动输入）
            menu.addActions([
                Action(text="🆕 新建组件", triggered=self._create_new_component),
                Action(text="📋 复制组件", triggered=self._copy_component),
                Action(text="📌 粘贴组件", triggered=self._paste_component),
                Action(text="📤 导出组件", triggered=self._export_component),
                Action(text="🗑️ 删除组件", triggered=self._delete_component),
                Action(text="🔄 刷新组件", triggered=self.refresh_components),
            ])

        menu.exec_(self.viewport().mapToGlobal(position))

    def _edit_component(self):
        """编辑组件 - 发射选中信号"""
        current_item = self.currentItem()
        if current_item and current_item.parent():  # 确保是子项（组件项）
            full_path = current_item.data(1, Qt.UserRole)
            if full_path in self._components:
                comp_cls = self._components[full_path]
                self.component_selected.emit(comp_cls)  # 发射信号，让主界面加载
            else:
                QMessageBox.warning(self, "警告", "无法找到该组件的类定义。")

    def _create_new_component(self):
        """创建新组件"""
        current_item = self.currentItem()
        # 获取当前选中项的父项（分类项）的文本
        default_category = ""
        if current_item:
            if current_item.parent():  # 如果选中的是组件项
                default_category = current_item.parent().text(0)
            elif not current_item.childCount():  # 如果选中的是一个没有子项的分类项
                default_category = current_item.text(0)
            # 如果选中的是有子项的分类项，default_category 保持为空字符串

        dialog = NewComponentDialog(self, default_category=default_category)
        if dialog.exec_() == QDialog.Accepted:
            component_info = dialog.get_component_info()
            self.component_created.emit(component_info)

    def _copy_component(self):
        """复制组件"""
        current_item = self.currentItem()
        if current_item and current_item.parent():
            full_path = current_item.data(1, Qt.UserRole)
            if full_path in self._components:
                self._copied_component = self._components[full_path]
                QMessageBox.information(self, "复制成功", "组件已复制到剪贴板")

    def _paste_component(self):
        """粘贴组件"""
        if self._copied_component:
            dialog = NewComponentDialog(self)
            dialog.setWindowTitle("粘贴组件 - 设置新组件信息")
            if dialog.exec_() == QDialog.Accepted:
                component_info = dialog.get_component_info()
                # 实现粘贴逻辑
                self._paste_component_impl(component_info)

    def _paste_component_impl(self, component_info):
        """实现组件粘贴"""
        try:
            # 生成新组件代码
            new_name = component_info["name"]
            new_category = component_info["category"]
            # 获取原组件源码
            source_code = inspect.getsource(self._copied_component)
            # 替换类名和基本信息
            new_code = source_code.replace(
                f"class {self._copied_component.__name__}",
                f"class {new_name.replace(' ', '')}"
            )
            # 更新基本信息
            lines = new_code.split('\n')
            for i, line in enumerate(lines):
                if 'name =' in line:
                    lines[i] = f'    name = "{new_name}"'
                elif 'category =' in line:
                    lines[i] = f'    category = "{new_category}"'
                elif 'description =' in line:
                    lines[i] = f'    description = "{component_info.get("description", "")}"'
            new_code = '\n'.join(lines)
            # 保存到文件
            self._save_component_code(new_category, new_name, new_code)
            self.refresh_components()
            QMessageBox.information(self, "成功", "组件粘贴成功！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"粘贴组件失败: {str(e)}")

    def _export_component(self):
        """导出组件"""
        current_item = self.currentItem()
        if current_item and current_item.parent():
            full_path = current_item.data(1, Qt.UserRole)
            if full_path in self._components:
                comp_cls = self._components[full_path]
                try:
                    # 获取组件源码
                    source_code = inspect.getsource(comp_cls)
                    # 选择保存位置
                    file_path, _ = QFileDialog.getSaveFileName(
                        self, "导出组件", f"{comp_cls.name}.py", "Python Files (*.py)"
                    )
                    if file_path:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(source_code)
                        QMessageBox.information(self, "成功", "组件导出成功！")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"导出组件失败: {str(e)}")

    def _delete_component(self):
        """删除组件"""
        current_item = self.currentItem()
        if current_item and current_item.parent():
            full_path = current_item.data(1, Qt.UserRole)
            category = current_item.parent().text(0)
            name = current_item.text(0)
            reply = QMessageBox.question(
                self, "删除组件", f"确定要删除组件 {category}/{name} 吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    # 删除对应的Python文件
                    component_dir = Path("app") / Path("components") / category
                    file_name = f"{name.replace(' ', '_').lower()}.py"
                    file_path = component_dir / file_name
                    if file_path.exists():
                        file_path.unlink()
                        self.refresh_components()
                        QMessageBox.information(self, "成功", "组件删除成功！")
                    else:
                        QMessageBox.warning(self, "警告", "组件文件不存在")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"删除组件失败: {str(e)}")

    def _save_component_code(self, category, name, code):
        """保存组件代码到文件"""
        components_dir = Path("app") / Path("components") / category
        components_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{name.replace(' ', '_').lower()}.py"
        filepath = components_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)