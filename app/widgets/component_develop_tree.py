# -*- coding: utf-8 -*-
import copy
import inspect
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QTreeWidgetItem,
    QFileDialog,
    QDialog
)
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import FluentStyleSheet, SearchLineEdit
from qfluentwidgets import (
    TreeWidget, RoundMenu, Action, InfoBar, InfoBarPosition, MessageBox
)

from app.scan_components import scan_components
from app.widgets.new_component_dialog import NewComponentDialog


class ComponentTreeWidget(TreeWidget):
    """组件树控件 - 支持右键菜单、搜索、快捷键"""
    component_selected = pyqtSignal(object)
    component_created = pyqtSignal(dict)
    component_pasted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._components: Dict[str, Any] = {}
        self._file_map: Dict[str, str] = {}
        self._copied_component = None
        self._all_items = []  # 用于搜索时恢复
        self.refresh_components()

        # 启用键盘焦点，以便接收快捷键
        self.setFocusPolicy(Qt.StrongFocus)

    def load_components(self, component_map: Dict[str, Any], file_map: Dict[str, str]):
        """加载组件到树中"""
        self.clear()
        self._components = component_map
        self._file_map = file_map
        self._all_items = []

        categories = {}
        for full_path, comp_cls in component_map.items():
            try:
                category = getattr(comp_cls, 'category', 'General')
                name = getattr(comp_cls, 'name', comp_cls.__name__)
                if category not in categories:
                    cat_item = QTreeWidgetItem([category])
                    self.addTopLevelItem(cat_item)
                    categories[category] = cat_item
                    self._all_items.append(cat_item)
                else:
                    cat_item = categories[category]
                comp_item = QTreeWidgetItem([name])
                comp_item.setData(0, Qt.UserRole + 1, full_path)
                cat_item.addChild(comp_item)
                self._all_items.append(comp_item)
            except Exception as e:
                self._show_error(f"加载组件 {full_path} 失败: {e}")

        self.expandAll()

    def refresh_components(self):
        """刷新组件树"""
        try:
            component_map, file_map = scan_components()
            self.load_components(component_map, file_map)
        except Exception as e:
            self._show_error(f"刷新组件失败: {e}")

    # ==================== 搜索功能 ====================
    def filter_items(self, keyword: str):
        """
        根据关键词过滤树节点（模糊匹配，不区分大小写）
        """
        keyword = keyword.strip().lower()
        if not keyword:
            # 显示所有
            for item in self._all_items:
                item.setHidden(False)
                if item.parent():
                    item.parent().setExpanded(True)
            return

        # 隐藏所有
        for item in self._all_items:
            item.setHidden(True)

        # 显示匹配项及其父节点
        for item in self._all_items:
            if not item.parent():  # 分类项
                continue
            name = item.text(0).lower()
            category = item.parent().text(0).lower()
            full_text = f"{category}/{name}"
            if keyword in name or keyword in category or keyword in full_text:
                item.setHidden(False)
                item.parent().setHidden(False)
                item.parent().setExpanded(True)

    # ==================== 快捷键支持 ====================
    def keyPressEvent(self, event):
        """处理快捷键"""
        key = event.key()
        modifiers = event.modifiers()

        # Ctrl+C: 复制
        if modifiers == Qt.ControlModifier and key == Qt.Key_C:
            self._copy_component()
            return

        # Ctrl+V: 粘贴
        if modifiers == Qt.ControlModifier and key == Qt.Key_V:
            self._paste_component()
            return

        # Delete: 删除
        if key == Qt.Key_Delete:
            self._delete_component()
            return

        # 其他按键交给父类
        super().keyPressEvent(event)

    # ==================== 辅助方法 ====================
    def _get_selected_component_item(self) -> Optional[QTreeWidgetItem]:
        item = self.currentItem()
        return item if item and item.parent() else None

    def _get_selected_category_item(self) -> Optional[QTreeWidgetItem]:
        item = self.currentItem()
        if item:
            return item if not item.parent() else item.parent()
        return None

    # ==================== 右键菜单 ====================
    def _show_context_menu(self, position):
        menu = RoundMenu(parent=self)
        item = self.itemAt(position)

        if item and item.parent():  # 组件项
            menu.addActions([
                Action("✏️ 编辑组件", triggered=self._edit_component),
                Action("📋 复制组件 (Ctrl+C)", triggered=self._copy_component),
                Action("📤 导出组件", triggered=self._export_component),
                Action("🗑️ 删除组件 (Delete)", triggered=self._delete_component),
            ])
        else:
            menu.addAction(Action("🆕 新建组件", triggered=self._create_new_component))
            if self._copied_component:
                menu.addAction(Action("📌 粘贴组件 (Ctrl+V)", triggered=self._paste_component))
            menu.addAction(Action("🔄 刷新组件", triggered=self.refresh_components))

        if menu.actions():
            menu.exec_(self.viewport().mapToGlobal(position))

    # ==================== 操作方法 ====================
    def _edit_component(self):
        item = self._get_selected_component_item()
        if not item:
            return
        full_path = item.data(0, Qt.UserRole + 1)
        comp_cls = self._components.get(full_path)
        if comp_cls:
            self.component_selected.emit(comp_cls)
        else:
            self._show_warning("组件类定义丢失，请刷新组件树。")

    def _create_new_component(self):
        category = ""
        cat_item = self._get_selected_category_item()
        if cat_item:
            category = cat_item.text(0)
        dialog = NewComponentDialog(self.parent_window, default_category=category)
        if dialog.exec_() == QDialog.Accepted:
            self.component_created.emit(dialog.get_component_info())

    def _copy_component(self):
        item = self._get_selected_component_item()
        if not item:
            self._show_warning("请先选中一个组件")
            return
        full_path = item.data(0, Qt.UserRole + 1)
        comp_cls = self._components.get(full_path)
        if comp_cls:
            self._copied_component = copy.deepcopy(comp_cls)
            self._show_success("组件已复制 (Ctrl+C)")
        else:
            self._show_warning("无法复制该组件")

    def _paste_component(self):
        if not self._copied_component:
            self._show_warning("剪贴板中没有可粘贴的组件 (先 Ctrl+C 复制)")
            return

        category = ""
        cat_item = self._get_selected_category_item()
        if cat_item:
            category = cat_item.text(0)

        dialog = NewComponentDialog(
            self.parent_window,
            default_name=self._copied_component.name,
            default_category=category,
            default_description=getattr(self._copied_component, 'description', '')
        )
        dialog.setWindowTitle("粘贴组件 - 设置新组件信息")
        if dialog.exec_() == QDialog.Accepted:
            component_info = dialog.get_component_info()
            # 更新复制的组件信息
            self._copied_component.name = component_info["name"]
            self._copied_component.category = component_info["category"]
            self._copied_component.description = component_info.get("description", "")
            self.component_pasted.emit()

    def _export_component(self):
        item = self._get_selected_component_item()
        if not item:
            self._show_warning("请先选中一个组件")
            return
        full_path = item.data(0, Qt.UserRole + 1)
        comp_cls = self._components.get(full_path)
        if not comp_cls:
            self._show_warning("组件类定义丢失")
            return

        try:
            source = inspect.getsource(comp_cls)
            default_name = f"{comp_cls.name}.py"
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出组件", default_name, "Python Files (*.py)"
            )
            if file_path:
                Path(file_path).write_text(source, encoding='utf-8')
                self._show_success("组件导出成功！")
        except Exception as e:
            self._show_error(f"导出失败: {e}")

    def _delete_component(self):
        item = self._get_selected_component_item()
        if not item:
            self._show_warning("请先选中一个组件")
            return

        full_path = item.data(0, Qt.UserRole + 1)
        category = item.parent().text(0)
        name = item.text(0)

        msg_box = MessageBox("删除组件", f"确定删除 {category}/{name} 吗？此操作不可逆！", self.window())
        if not msg_box.exec():
            return

        try:
            file_name = self._file_map.get(full_path)
            if not file_name:
                raise FileNotFoundError("组件文件映射丢失")

            file_path = Path("app") / "components" / category / file_name
            if file_path.exists():
                file_path.unlink()
                self.refresh_components()
                self._show_success("组件删除成功！")
            else:
                self._show_warning("组件文件不存在")
        except Exception as e:
            self._show_error(f"删除失败: {e}")

    # --- 通知方法 ---
    def _show_warning(self, message: str):
        InfoBar.warning(
            title='警告', content=message,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000, parent=self.parent_window
        )

    def _show_error(self, message: str):
        InfoBar.error(
            title='错误', content=message,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000, parent=self.parent_window
        )

    def _show_success(self, message: str):
        InfoBar.success(
            title='成功', content=message,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000, parent=self.parent_window
        )


class ComponentTreePanel(QWidget):
    """带搜索框的组件树面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 搜索框
        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText("🔍 搜索组件...")
        self.search_box.setClearButtonEnabled(True)
        FluentStyleSheet.LINE_EDIT.apply(self.search_box)  # 可选：应用 Fluent 风格
        self.search_box.textChanged.connect(self._on_search_text_changed)

        # 组件树
        self.tree = ComponentTreeWidget(self.parent_window)

        layout.addWidget(self.search_box)
        layout.addWidget(self.tree)

    def _on_search_text_changed(self, text: str):
        self.tree.filter_items(text)

    # 代理常用信号和方法（方便外部调用）
    @property
    def component_selected(self):
        return self.tree.component_selected

    @property
    def component_created(self):
        return self.tree.component_created

    @property
    def component_pasted(self):
        return self.tree.component_pasted

    def refresh_components(self):
        self.tree.refresh_components()