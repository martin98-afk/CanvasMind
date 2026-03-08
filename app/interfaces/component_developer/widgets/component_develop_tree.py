# -*- coding: utf-8 -*-
import copy
import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List

from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QMimeData
from PyQt5.QtWidgets import (
    QTreeWidgetItem,
    QDialog,
    QTreeWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
)
from PyQt5.QtGui import QDrag
from qfluentwidgets import (
    TreeWidget,
    RoundMenu,
    Action,
    InfoBar,
    MessageBox,
    SearchLineEdit,
    TransparentToolButton,
    DropDownPushButton,
    FluentIcon,
)

from app.scan_components import ComponentScanner
from app.utils.config import Settings
from app.utils.utils import get_icon, resource_path
from app.widgets.dialog_widget.new_component_dialog import NewComponentDialog
from app.widgets.basic_widget.category_filter import CategoryFilterDialog

# 定义角色标识，区分文件夹和组件
ROLE_FULL_PATH = Qt.UserRole + 1
ROLE_IS_FOLDER = Qt.UserRole + 2


class ComponentTreeWidget(TreeWidget):
    """组件树控件 - 支持无限级节点、右键菜单、搜索、快捷键、类别筛选"""

    component_selected = pyqtSignal(str)
    component_created = pyqtSignal(dict)
    component_pasted = pyqtSignal(str)

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
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeWidget.DragOnly)

    def refresh_components(self):
        """刷新组件列表，并保持当前类别筛选状态"""
        try:
            self._components, self._file_map = ComponentScanner().get_components()
            self.show_selected_category()
        except Exception as e:
            self._show_error(f"刷新组件失败: {e}")

    def show_selected_category(self):
        """支持无限级路径构建树（如 A/B/C/组件）"""
        self.clear()
        self._all_items.clear()

        if not self._components:
            return

        # 缓存文件夹节点，避免重复创建
        path_nodes = {}

        # 按路径排序，确保父目录先处理
        sorted_paths = sorted(self._components.keys())

        for full_path in sorted_paths:
            parts = full_path.split("/")

            # 1. 第一级类别过滤
            if self._selected_categories and parts[0] not in self._selected_categories:
                continue

            current_parent = None
            path_acc = ""

            # 2. 递归构建中间目录
            for i in range(len(parts) - 1):
                part_name = parts[i]
                path_acc = "/".join(parts[: i + 1])

                if path_acc not in path_nodes:
                    folder_item = QTreeWidgetItem([part_name])
                    folder_item.setData(0, ROLE_IS_FOLDER, True)
                    folder_item.setIcon(0, FluentIcon.FOLDER.icon())

                    if current_parent:
                        current_parent.addChild(folder_item)
                    else:
                        self.addTopLevelItem(folder_item)

                    path_nodes[path_acc] = folder_item
                    self._all_items.append(folder_item)

                current_parent = path_nodes[path_acc]

            # 3. 创建组件叶子节点
            comp_name = parts[-1]
            comp_item = QTreeWidgetItem([comp_name])
            comp_item.setData(0, ROLE_FULL_PATH, full_path)
            comp_item.setData(0, ROLE_IS_FOLDER, False)

            if current_parent:
                current_parent.addChild(comp_item)
            else:
                self.addTopLevelItem(comp_item)

            self._all_items.append(comp_item)

        self.expandAll()

    def filter_items(self, keyword: str):
        """根据关键词过滤（支持多级展示）"""
        keyword = keyword.strip().lower()

        # 隐藏所有项
        for item in self._all_items:
            item.setHidden(True)

        if not keyword:
            for item in self._all_items:
                item.setHidden(False)
            return

        for item in self._all_items:
            # 只在组件节点上匹配
            if not item.data(0, ROLE_IS_FOLDER):
                name = item.text(0).lower()
                full_path = (item.data(0, ROLE_FULL_PATH) or "").lower()

                if keyword in name or keyword in full_path:
                    # 匹配成功，递归显示并展开父节点
                    curr = item
                    while curr:
                        curr.setHidden(False)
                        curr.setExpanded(True)
                        curr = curr.parent()

    def expand_all_categories(self):
        self.expandAll()

    def collapse_all_categories(self):
        self.collapseAll()

    def set_current_editing_component(self, full_path: str):
        self._current_editing_component = full_path

    def jump_to_current_component(self):
        if not self._current_editing_component:
            self._show_warning("没有当前编辑的组件")
            return

        for item in self._all_items:
            if (
                not item.data(0, ROLE_IS_FOLDER)
                and item.data(0, ROLE_FULL_PATH) == self._current_editing_component
            ):
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
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key in (
            Qt.Key_Plus,
            Qt.Key_Equal,
        ):
            self.expand_all_categories()
            return
        if modifiers == (Qt.ControlModifier | Qt.ShiftModifier) and key == Qt.Key_Minus:
            self.collapse_all_categories()
            return
        if modifiers == Qt.ControlModifier and key == Qt.Key_G:
            self.jump_to_current_component()
            return

        super().keyPressEvent(event)

    def _is_component(self, item: QTreeWidgetItem) -> bool:
        return item is not None and not item.data(0, ROLE_IS_FOLDER)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item or not self._is_component(item):
            return

        full_path = item.data(0, ROLE_FULL_PATH)
        if not full_path:
            return

        file_path = self._file_map.get(full_path)
        component_abs_path = ""
        extension_abs_path = ""
        if file_path:
            uuid = Path(file_path).stem
            component_abs_path = str(Path(resource_path("app")) / file_path)
            extension_abs_path = str(
                Path(resource_path("app/component_extensions")) / uuid
            )

        drag_data = (
            f"{component_abs_path}\n{extension_abs_path}"
            if extension_abs_path
            else component_abs_path
        )

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(drag_data)
        drag.setMimeData(mime_data)
        drag.exec_(Qt.CopyAction)

    def _get_selected_component_item(self) -> Optional[QTreeWidgetItem]:
        item = self.currentItem()
        return item if self._is_component(item) else None

    def _get_selected_category_path(self) -> str:
        """获取选中节点的分类全路径"""
        item = self.currentItem()
        if not item:
            return ""

        # 如果选中的是组件，取它的父节点
        curr = item if item.data(0, ROLE_IS_FOLDER) else item.parent()
        path_parts = []
        while curr:
            path_parts.insert(0, curr.text(0))
            curr = curr.parent()
        return "/".join(path_parts)

    def _show_context_menu(self, position):
        menu = RoundMenu(parent=self)
        item = self.itemAt(position)

        if self._is_component(item):
            menu.addActions(
                [
                    Action("✏️ 编辑组件", triggered=self._edit_component),
                    Action("📋 复制组件 (Ctrl+C)", triggered=self._copy_component),
                    Action("🗑️ 删除组件 (Delete)", triggered=self._delete_component),
                ]
            )
        else:
            menu.addAction(Action("🆕 新建组件", triggered=self._create_new_component))
            if self._copied_component:
                menu.addAction(
                    Action("📌 粘贴组件 (Ctrl+V)", triggered=self._paste_component)
                )

        if menu.actions():
            menu.exec_(self.viewport().mapToGlobal(position))

    def _edit_component(self):
        item = self._get_selected_component_item()
        if not item:
            return
        self.component_selected.emit(item.data(0, ROLE_FULL_PATH))

    def _create_new_component(self):
        category = self._get_selected_category_path()
        dialog = NewComponentDialog(self.parent_window, default_category=category)
        if dialog.exec_() == QDialog.Accepted:
            self.component_created.emit(dialog.get_component_info())

    def _copy_component(self):
        item = self._get_selected_component_item()
        if not item:
            self._show_warning("请先选中一个组件")
            return
        full_path = item.data(0, ROLE_FULL_PATH)
        orig_cls = self._components.get(full_path)
        if not orig_cls:
            return

        new_cls = type(orig_cls.__name__, orig_cls.__bases__, dict(orig_cls.__dict__))
        for attr_name, attr_value in orig_cls.__dict__.items():
            if isinstance(attr_value, (list, dict)):
                setattr(new_cls, attr_name, copy.deepcopy(attr_value))

        self._copied_component = new_cls
        self._show_success("组件已复制 (Ctrl+C)")

    def _paste_component(self):
        if not self._copied_component:
            return
        category = self._get_selected_category_path()
        dialog = NewComponentDialog(
            self.parent_window,
            default_name=self._copied_component.name,
            default_category=category,
            default_description=getattr(self._copied_component, "description", ""),
        )
        if dialog.exec_() == QDialog.Accepted:
            info = dialog.get_component_info()
            self.component_pasted.emit(f"{info['category']}/{info['name']}")

    def _delete_component(self):
        item = self._get_selected_component_item()
        if not item:
            return
        full_path = item.data(0, ROLE_FULL_PATH)
        msg_box = MessageBox("删除组件", f"确定删除 {full_path} 吗？", self.window())
        if not msg_box.exec():
            return

        try:
            file_path = self._file_map.get(full_path)
            uuid = Path(file_path).stem
            if Path(f"app/component_extensions/{uuid}").exists():
                shutil.rmtree(resource_path(f"app/component_extensions/{uuid}"))
            if file_path and Path(file_path).exists():
                Path(file_path).unlink()
                self._show_success("组件删除成功！")
            else:
                self._show_warning("组件文件不存在")
        except Exception as e:
            self._show_error(f"删除失败: {e}")

    def _show_warning(self, message: str):
        InfoBar.warning(
            title="警告", content=message, duration=3000, parent=self.parent_window
        )

    def _show_error(self, message: str):
        InfoBar.error(
            title="错误", content=message, duration=5000, parent=self.parent_window
        )

    def _show_success(self, message: str):
        InfoBar.success(
            title="成功", content=message, duration=2000, parent=self.parent_window
        )


class ComponentTreePanel(QWidget):
    """带搜索框和控制按钮的组件树面板 - 完整保留所有 UI 按钮"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.tree = ComponentTreeWidget(self.parent_window)
        self.category_filter_dialog = None
        self._setup_ui()
        self._init_unified_font()
        self._init_components_and_categories()

    def _init_unified_font(self):
        """
        在基类中统一配置字体
        """
        # 1. 获取字体名称 (这里替换为你实际获取配置的代码)
        try:
            font_name = Settings.get_instance().canvas_font_type.value
        except Exception:
            font_name = "Microsoft YaHei"  # 默认字体

        # 2. 方案 A：使用 setFont (基础设置)
        font = self.font()
        font.setFamily(font_name)
        self.setFont(font)

        # 3. 方案 B：使用 StyleSheet (强制穿透解决嵌套控件无效问题)
        self.setStyleSheet(f"""
            LeftPanel, QWidget {{
                font-family: "{font_name}";
            }}
            /* 针对某些特殊控件的补充（如按钮、标签） */
            QLabel, QPushButton, QLineEdit, QComboBox, QTreeWidget, QTableWidget TreeWidget{{
                font-family: "{font_name}";
            }}
        """)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ✅ 完整保留你的控制栏
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(5, 5, 5, 2)

        self.category_button = DropDownPushButton(FluentIcon.BOOK_SHELF, "类别", self)
        self.category_button.setToolTip("类别筛选")
        self.category_button.clicked.connect(self._show_category_dialog)

        # 展开/折叠/跳转按钮
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

        top_layout.addWidget(self.category_button, 1)
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
        self.tree.refresh_components()
        ComponentScanner.register_on_change(self._on_scanner_updated)
        # 取第一段路径作为筛选大类

        self.category_filter_dialog = CategoryFilterDialog(self)
        self.category_filter_dialog.categories_changed.connect(
            self._on_categories_changed
        )

    def _on_scanner_updated(self):
        self.tree.refresh_components()
        self.tree.expand_all_categories()

    def _show_category_dialog(self):
        if self.category_filter_dialog:
            pos = self.category_button.mapToGlobal(
                QPoint(-10, self.category_button.height() - 10)
            )
            self.category_filter_dialog.show_at(pos)

    def _on_categories_changed(self, selected_categories):
        self.tree._selected_categories = selected_categories
        self.tree.show_selected_category()

    @property
    def component_selected(self):
        return self.tree.component_selected

    @property
    def component_created(self):
        return self.tree.component_created

    @property
    def component_pasted(self):
        return self.tree.component_pasted

    def set_current_editing_component(self, full_path: str):
        self.tree.set_current_editing_component(full_path)

    def jump_to_current_component(self):
        self.tree.jump_to_current_component()
