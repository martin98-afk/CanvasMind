# -*- coding: utf-8 -*-
import copy
from pathlib import Path
from typing import Dict, Any, Optional, List

from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtWidgets import (
    QTreeWidgetItem,
    QDialog,
    QTreeWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout
)
from qfluentwidgets import (
    TreeWidget, RoundMenu, Action, InfoBar, MessageBox, SearchLineEdit, TransparentToolButton,
    DropDownPushButton, FluentIcon
)

from app.scan_components import ComponentScanner
from app.utils.utils import get_icon
from app.widgets.dialog_widget.new_component_dialog import NewComponentDialog
from app.widgets.tree_widget.category_filter import CategoryFilterDialog


class ComponentTreeWidget(TreeWidget):
    """组件树控件 - 支持右键菜单、搜索、快捷键、类别筛选"""
    component_selected = pyqtSignal(object, str)
    component_created = pyqtSignal(dict)
    component_pasted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._components: Dict[str, Any] = {}
        self._file_map: Dict[str, Path] = {}
        self._copied_component = None
        self._all_items: List[QTreeWidgetItem] = []
        self._current_editing_component = None
        self._selected_categories = set()
        self.setFocusPolicy(Qt.StrongFocus)

    def set_components(self, component_map: Dict[str, Any], file_map: Dict[str, Path]):
        """设置组件数据（外部调用，不自动刷新 UI）"""
        self._components = component_map
        self._file_map = file_map

    def show_selected_category(self):
        """根据当前筛选条件构建树（统一入口）"""
        self.clear()
        self._all_items.clear()

        if not self._components:
            return

        # 预构建分类 → 组件列表映射（避免多次遍历）
        category_to_comps = {}
        for full_path, comp_cls in self._components.items():
            category = getattr(comp_cls, 'category', 'General')
            name = getattr(comp_cls, 'name', comp_cls.__name__) or comp_cls.__name__
            if not isinstance(name, str):
                name = str(name)

            if self._selected_categories and category not in self._selected_categories:
                continue

            if category not in category_to_comps:
                category_to_comps[category] = []
            category_to_comps[category].append((full_path, name))

        # 按分类名排序
        for category in sorted(category_to_comps.keys()):
            cat_item = QTreeWidgetItem([category])
            self.addTopLevelItem(cat_item)
            self._all_items.append(cat_item)

            # 组件按名称排序
            comps = sorted(category_to_comps[category], key=lambda x: x[1])
            for full_path, name in comps:
                comp_item = QTreeWidgetItem([name])
                comp_item.setData(0, Qt.UserRole + 1, full_path)
                cat_item.addChild(comp_item)
                self._all_items.append(comp_item)

            cat_item.setExpanded(True)

    def refresh_components(self):
        """刷新组件列表，并保持当前类别筛选状态"""
        try:
            component_map, file_map = ComponentScanner().refresh()
            self.set_components(component_map, file_map)
            self.show_selected_category()  # 👈 保留筛选状态
        except Exception as e:
            self._show_error(f"刷新组件失败: {e}")

    def filter_items(self, keyword: str):
        """根据关键词过滤树节点（模糊匹配）"""
        keyword = keyword.strip().lower()
        if not keyword:
            for item in self._all_items:
                item.setHidden(False)
                if item.parent():
                    item.parent().setExpanded(True)
            return

        for item in self._all_items:
            item.setHidden(True)

        for item in self._all_items:
            if not item.parent():  # 分类项
                continue
            name = item.text(0).lower()
            category = item.parent().text(0).lower()
            if keyword in name or keyword in category or keyword in f"{category}/{name}":
                item.setHidden(False)
                parent = item.parent()
                if parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)

    def expand_all_categories(self):
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).setExpanded(True)

    def collapse_all_categories(self):
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).setExpanded(False)

    def set_current_editing_component(self, full_path: str):
        self._current_editing_component = full_path

    def jump_to_current_component(self):
        if not self._current_editing_component:
            self._show_warning("没有当前编辑的组件")
            return

        for item in self._all_items:
            if not item.parent():
                continue
            if item.data(0, Qt.UserRole + 1) == self._current_editing_component:
                parent = item.parent()
                if parent:
                    parent.setExpanded(True)
                self.setCurrentItem(item)
                self.scrollToItem(item, QTreeWidget.EnsureVisible)
                item.setSelected(True)
                self.setFocus()
                return
        self._show_warning("未找到当前编辑的组件")

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        if modifiers == Qt.ControlModifier and key == Qt.Key_C:
            self._copy_component()
            return
        if modifiers == Qt.ControlModifier and key == Qt.Key_V:
            self._paste_component()
            return
        if key == Qt.Key_Delete:
            self._delete_component()
            return
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key in (Qt.Key_Plus, Qt.Key_Equal):
            self.expand_all_categories()
            return
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key == Qt.Key_Minus:
            self.collapse_all_categories()
            return
        if modifiers == Qt.ControlModifier and key == Qt.Key_G:
            self.jump_to_current_component()
            return

        super().keyPressEvent(event)

    def _get_selected_component_item(self) -> Optional[QTreeWidgetItem]:
        item = self.currentItem()
        return item if item and item.parent() else None

    def _get_selected_category_item(self) -> Optional[QTreeWidgetItem]:
        item = self.currentItem()
        return item if item and not item.parent() else (item.parent() if item else None)

    def _show_context_menu(self, position):
        menu = RoundMenu(parent=self)
        item = self.itemAt(position)

        if item and item.parent():  # 组件
            menu.addActions([
                Action("✏️ 编辑组件", triggered=self._edit_component),
                Action("📋 复制组件 (Ctrl+C)", triggered=self._copy_component),
                Action("🗑️ 删除组件 (Delete)", triggered=self._delete_component),
            ])
        else:  # 空白或分类
            menu.addAction(Action("🆕 新建组件", triggered=self._create_new_component))
            if self._copied_component:
                menu.addAction(Action("📌 粘贴组件 (Ctrl+V)", triggered=self._paste_component))
            menu.addAction(Action("🔄 刷新组件", triggered=self.refresh_components))

        if menu.actions():
            menu.exec_(self.viewport().mapToGlobal(position))

    def _edit_component(self):
        item = self._get_selected_component_item()
        if not item:
            return
        full_path = item.data(0, Qt.UserRole + 1)
        self.set_current_editing_component(full_path)
        self.component_selected.emit(full_path)

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
            self._show_warning("剪贴板中没有可粘贴的组件")
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
            info = dialog.get_component_info()
            self._copied_component.name = info["name"]
            self._copied_component.category = info["category"]
            self._copied_component.description = info.get("description", "")
            self.component_pasted.emit()

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
            file_path = self._file_map.get(full_path)
            if file_path and Path(file_path).exists():
                Path(file_path).unlink()
                self.refresh_components()
                self._show_success("组件删除成功！")
            else:
                self._show_warning("组件文件不存在")
        except Exception as e:
            self._show_error(f"删除失败: {e}")

    def _show_warning(self, message: str):
        InfoBar.warning(title='警告', content=message, duration=3000, parent=self.parent_window)

    def _show_error(self, message: str):
        InfoBar.error(title='错误', content=message, duration=5000, parent=self.parent_window)

    def _show_success(self, message: str):
        InfoBar.success(title='成功', content=message, duration=2000, parent=self.parent_window)


class ComponentTreePanel(QWidget):
    """带搜索框和控制按钮的组件树面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.tree = ComponentTreeWidget(self.parent_window)
        self.category_filter_dialog = None
        self._setup_ui()
        self._init_components_and_categories()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 控制栏
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(5, 5, 5, 2)
        self.category_button = DropDownPushButton(FluentIcon.BOOK_SHELF, "类别", self)
        self.category_button.setToolTip("类别筛选")
        self.category_button.clicked.connect(self._show_category_dialog)
        self.expand_all_btn = TransparentToolButton(get_icon("expand_all"), self)
        self.expand_all_btn.setToolTip("展开所有分类")
        self.expand_all_btn.setFixedSize(25, 32)
        self.expand_all_btn.clicked.connect(self.tree.expand_all_categories)
        self.collapse_all_btn = TransparentToolButton(get_icon("collapse_all"), self)
        self.collapse_all_btn.setToolTip("折叠所有分类")
        self.collapse_all_btn.setFixedSize(25, 32)
        self.collapse_all_btn.clicked.connect(self.tree.collapse_all_categories)
        self.jump_to_current_btn = TransparentToolButton(get_icon("location"), self)
        self.jump_to_current_btn.setToolTip("跳转到当前编辑的组件")
        self.jump_to_current_btn.setFixedSize(25, 32)
        self.jump_to_current_btn.clicked.connect(self.tree.jump_to_current_component)

        top_layout.addWidget(self.category_button)
        top_layout.addStretch()
        top_layout.addWidget(self.jump_to_current_btn)
        top_layout.addWidget(self.expand_all_btn)
        top_layout.addWidget(self.collapse_all_btn)

        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(5, 3, 5, 5)
        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText("搜索组件...")
        self.search_box.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_box)

        layout.addLayout(top_layout)
        layout.addLayout(search_layout)
        layout.addWidget(self.tree)

        self.search_box.textChanged.connect(self.tree.filter_items)

    def _init_components_and_categories(self):
        """初始化组件和类别（仅一次）"""
        comp_map, file_map = ComponentScanner().get_components()  # 使用缓存，不强制刷新
        self.tree.set_components(comp_map, file_map)
        self.tree.show_selected_category()  # 👈 保留筛选状态
        # 提取类别
        categories = {getattr(cls, 'category', 'General') for cls in comp_map.values()}
        self.category_filter_dialog = CategoryFilterDialog(sorted(categories), self)
        self.category_filter_dialog.categories_changed.connect(self._on_categories_changed)

    def _show_category_dialog(self):
        if self.category_filter_dialog:
            pos = self.category_button.mapToGlobal(QPoint(-10, self.category_button.height() - 10))
            self.category_filter_dialog.show_at(pos)

    def _on_categories_changed(self, selected_categories):
        self.tree._selected_categories = selected_categories
        self.tree.show_selected_category()

    # 代理常用接口
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

    def set_current_editing_component(self, full_path: str):
        self.tree.set_current_editing_component(full_path)

    def jump_to_current_component(self):
        self.tree.jump_to_current_component()