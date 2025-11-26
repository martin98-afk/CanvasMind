# -*- coding: utf-8 -*-
import copy
import inspect
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtWidgets import (
    QTreeWidgetItem,
    QFileDialog,
    QDialog,
    QTreeWidget
)
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import FluentStyleSheet, SearchLineEdit, TransparentToolButton, DropDownPushButton, FluentIcon
from qfluentwidgets import (
    TreeWidget, RoundMenu, Action, InfoBar, InfoBarPosition, MessageBox
)

from app.scan_components import scan_components
from app.utils.utils import get_icon
from app.widgets.dialog_widget.new_component_dialog import NewComponentDialog
from app.widgets.tree_widget.draggable_component_tree import CategoryFilterDialog


class ComponentTreeWidget(TreeWidget):
    """组件树控件 - 支持右键菜单、搜索、快捷键"""
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
        self._file_map: Dict[str, str] = {}
        self._copied_component = None
        self._all_items = []  # 用于搜索时恢复
        self._current_editing_component = None  # 当前编辑的组件路径
        self.refresh_components()
        self._selected_categories = set()
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

    def show_selected_category(self):
        """根据当前筛选条件构建树"""
        self.clear()
        self._all_items = []

        # 获取所有组件
        all_components = []
        for full_path, comp_cls in self._components.items():
            category = getattr(comp_cls, 'category', 'General')
            name = getattr(comp_cls, 'name', comp_cls.__name__)
            if not isinstance(name, str):
                name = comp_cls.NODE_NAME


            all_components.append({
                'full_path': full_path,
                'name': name,
                'category': category
            })

        # 应用筛选
        filtered = []
        for comp in all_components:
            # 类别筛选
            if self._selected_categories and comp['category'] not in self._selected_categories:
                continue
            filtered.append(comp)

        filtered.sort(key=lambda x: (x['category'], x['name']))

        # 构建树结构
        categories = {}
        for comp in filtered:
            category = comp['category']
            if category not in categories:
                cat_item = QTreeWidgetItem([category])
                self.addTopLevelItem(cat_item)
                categories[category] = cat_item
                self._all_items.append(cat_item)
            else:
                cat_item = categories[category]

            comp_item = QTreeWidgetItem([comp['name']])
            comp_item.setData(0, Qt.UserRole + 1, comp['full_path'])
            cat_item.addChild(comp_item)
            self._all_items.append(comp_item)

        for cat_item in categories.values():
            cat_item.setExpanded(True)

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

    # ==================== 展开折叠功能 ====================
    def expand_all_categories(self):
        """展开所有分类"""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            item.setExpanded(True)

    def collapse_all_categories(self):
        """折叠所有分类"""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            item.setExpanded(False)

    def set_current_editing_component(self, full_path: str):
        """设置当前编辑的组件路径"""
        self._current_editing_component = full_path

    def jump_to_current_component(self):
        """跳转到当前正在编辑的组件"""
        if not self._current_editing_component:
            self._show_warning("没有当前编辑的组件")
            return

        # 遍历所有项目查找匹配的组件
        for item in self._all_items:
            if not item.parent():  # 跳过分类项
                continue
            item_path = item.data(0, Qt.UserRole + 1)
            if item_path == self._current_editing_component:
                # 展开父节点
                parent = item.parent()
                if parent:
                    parent.setExpanded(True)

                # 选中并滚动到该组件
                self.setCurrentItem(item)
                self.scrollToItem(item, hint=QTreeWidget.EnsureVisible)

                # 设置焦点以高亮显示
                item.setSelected(True)
                self.setFocus()
                return

        self._show_warning("未找到当前编辑的组件")

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

        # Ctrl+Shift+加号: 展开所有
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key in [Qt.Key_Plus, Qt.Key_Equal]:
            self.expand_all_categories()
            return

        # Ctrl+Shift+减号: 折叠所有
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key == Qt.Key_Minus:
            self.collapse_all_categories()
            return

        # Ctrl+G: 跳转到当前组件
        if modifiers == Qt.ControlModifier and key == Qt.Key_G:
            self.jump_to_current_component()
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
            # 更新当前编辑的组件
            self.set_current_editing_component(full_path)
            self.component_selected.emit(comp_cls, full_path)
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
    """带搜索框和控制按钮的组件树面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.tree = None  # 预先声明，避免初始化顺序问题
        self._setup_ui()
        self._init_categories()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # 组件树（必须先创建，然后才能连接信号）
        self.tree = ComponentTreeWidget(self.parent_window)
        # 搜索框和控制按钮行
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(5, 5, 5, 2)
        top_layout.setSpacing(5)
        # 控制按钮
        # 类别选择按钮（点击弹出复选框）
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

        # 添加到布局
        top_layout.addWidget(self.category_button)
        top_layout.addStretch()
        top_layout.addWidget(self.jump_to_current_btn)
        top_layout.addWidget(self.expand_all_btn)
        top_layout.addWidget(self.collapse_all_btn)

        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(5, 3, 5, 5)
        self.search_box = SearchLineEdit(self)
        self.search_box.setMinimumWidth(150)
        self.search_box.setPlaceholderText("搜索组件...")
        self.search_box.setClearButtonEnabled(True)
        FluentStyleSheet.LINE_EDIT.apply(self.search_box)
        search_layout.addWidget(self.search_box)

        layout.addLayout(top_layout)
        layout.addLayout(search_layout)
        layout.addWidget(self.tree)

        # 连接搜索事件
        self.search_box.textChanged.connect(self._on_search_text_changed)

    def _init_categories(self):
        """初始化类别列表"""
        categories = set()
        for full_path, comp_cls in self.tree._components.items():
            category = getattr(comp_cls, 'category', 'General')
            categories.add(category)

        # 创建类别筛选对话框
        self.category_filter_dialog = CategoryFilterDialog(sorted(categories), self)

        # 设置默认全选
        self.tree._selected_categories = set(categories)

    def _show_category_dialog(self):
        """显示类别筛选对话框"""
        if self.category_filter_dialog:
            # 计算位置，让对话框出现在按钮下方
            pos = self.category_button.mapToGlobal(QPoint(-10, self.category_button.height() - 10))
            self.category_filter_dialog.show_at(pos)

    def _on_categories_changed(self, selected_categories):
        """类别选择变化回调"""
        self.tree._selected_categories = selected_categories
        self.tree.show_selected_category()

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

    def set_current_editing_component(self, full_path: str):
        """设置当前编辑的组件路径"""
        self.tree.set_current_editing_component(full_path)

    def jump_to_current_component(self):
        """跳转到当前编辑的组件"""
        self.tree.jump_to_current_component()