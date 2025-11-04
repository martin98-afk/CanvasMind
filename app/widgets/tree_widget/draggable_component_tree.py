# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime

from PyQt5.QtCore import Qt, QMimeData, QRectF, QPoint
from PyQt5.QtGui import QDrag, QPixmap, QPainter, QColor, QPen, QFont, QPainterPath
from PyQt5.QtWidgets import QTreeWidgetItem, QWidget, QVBoxLayout, QHBoxLayout, QMenu, QCheckBox, QFrame
from qfluentwidgets import FluentIcon as FIF, TransparentToggleToolButton
from qfluentwidgets import TreeWidget, SearchLineEdit, FluentStyleSheet, ToggleToolButton, PushButton, \
    DropDownPushButton

from app.widgets.basic_widget.style_sheet import StyleSheet


class CategoryFilterDialog(QWidget):
    """类别筛选对话框，用作下拉弹窗"""

    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.categories = categories
        self.selected_categories = set(categories)  # 默认全选
        self.checkboxes = []
        self.parent_widget = parent
        self._setup_ui()

        # 应用样式表
        StyleSheet.CATEGORY_FILTER.apply(self)

    def _setup_ui(self):
        # 主框架
        main_frame = QFrame(self)

        layout = QVBoxLayout(main_frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # 全选/取消全选按钮
        button_layout = QHBoxLayout()
        select_all_btn = PushButton("全选", self)
        select_all_btn.clicked.connect(self._select_all)
        button_layout.addWidget(select_all_btn)

        select_none_btn = PushButton("取消全选", self)
        select_none_btn.clicked.connect(self._select_none)
        button_layout.addWidget(select_none_btn)

        layout.addLayout(button_layout)

        # 复选框列表
        for category in self.categories:
            checkbox = QCheckBox(category)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(lambda state, cat=category: self._on_category_toggled(cat, state))
            self.checkboxes.append(checkbox)
            layout.addWidget(checkbox)

        # 设置主框架大小
        main_frame.resize(200, min(300, len(self.categories) * 30 + 60))

        # 将主框架添加到窗口
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(main_frame)

    def _on_category_toggled(self, category, state):
        if state == Qt.Checked:
            self.selected_categories.add(category)
        else:
            self.selected_categories.discard(category)
        if self.parent_widget:
            self.parent_widget._on_categories_changed(self.selected_categories)

    def _select_all(self):
        for checkbox in self.checkboxes:
            checkbox.setChecked(True)
        self.selected_categories = set(self.categories)
        if self.parent_widget:
            self.parent_widget._on_categories_changed(self.selected_categories)

    def _select_none(self):
        for checkbox in self.checkboxes:
            checkbox.setChecked(False)
        self.selected_categories = set()
        if self.parent_widget:
            self.parent_widget._on_categories_changed(self.selected_categories)

    def get_selected_categories(self):
        return self.selected_categories.copy()

    def show_at(self, pos):
        self.move(pos)
        self.show()


class DraggableTreePanel(QWidget):
    """带搜索框的组件树面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.category_filter_dialog = None
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedWidth(210)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(8)

        # 第一行：控制栏
        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)

        # 类别选择按钮（点击弹出复选框）
        self.category_button = DropDownPushButton(FIF.BOOK_SHELF, "组件类别", self)
        self.category_button.setToolTip("类别筛选")
        self.category_button.clicked.connect(self._show_category_dialog)

        # 时间排序按钮
        self.time_toggle = TransparentToggleToolButton(FIF.HISTORY, self)
        self.time_toggle.setFixedSize(22, 22)
        self.time_toggle.setToolTip("按最后使用时间排序")
        self.time_toggle.toggled.connect(self._on_time_toggled)

        # 收藏按钮
        self.favorite_toggle = TransparentToggleToolButton(FIF.EXPRESSIVE_INPUT_ENTRY, self)
        self.favorite_toggle.setFixedSize(22, 22)
        self.favorite_toggle.setToolTip("只显示收藏组件")
        self.favorite_toggle.toggled.connect(self._on_favorite_toggled)

        control_layout.addWidget(self.category_button)
        control_layout.addWidget(self.time_toggle)
        control_layout.addWidget(self.favorite_toggle)

        # 第二行：搜索框
        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText("🔍 搜索组件...")
        self.search_box.setClearButtonEnabled(True)
        FluentStyleSheet.LINE_EDIT.apply(self.search_box)
        self.search_box.textChanged.connect(self._on_search_text_changed)

        # 组件树
        self.tree = DraggableTreeWidget(self.parent_window)
        self.tree.setHeaderHidden(True)
        self.tree.setFixedWidth(210)

        layout.addLayout(control_layout)
        layout.addWidget(self.search_box)
        layout.addWidget(self.tree)

        # 初始化类别列表
        self._init_categories()

    def _init_categories(self):
        """初始化类别列表"""
        categories = set()
        for full_path, comp_cls in self.parent_window.component_map.items():
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
            pos = self.category_button.mapToGlobal(QPoint(0, self.category_button.height()))
            self.category_filter_dialog.show_at(pos)

    def _on_categories_changed(self, selected_categories):
        """类别选择变化回调"""
        self.tree._selected_categories = selected_categories
        self.tree.refresh_components()

    def _on_time_toggled(self, checked):
        """时间排序切换"""
        self.tree._show_time_sorted = checked
        self.tree.refresh_components()

    def _on_favorite_toggled(self, checked):
        """收藏过滤切换"""
        self.tree._show_only_favorites = checked
        self.tree.refresh_components()

    def _on_search_text_changed(self, text: str):
        self.tree.filter_items(text)


class DraggableTreeWidget(TreeWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setDragDropMode(TreeWidget.DragOnly)
        self._all_items = []  # 用于搜索
        self._usage_stats = self._load_usage_stats()  # 使用统计
        self._favorites = self._load_favorites()  # 收藏夹

        # 筛选状态
        self._show_time_sorted = False
        self._show_only_favorites = False
        self._selected_categories = set()  # 当前选中的类别

        self.refresh_components()

    def _load_usage_stats(self):
        stats_file = os.path.join(os.path.expanduser("~"), ".nodegraph_usage.json")
        if os.path.exists(stats_file):
            try:
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_usage_stats(self):
        stats_file = os.path.join(os.path.expanduser("~"), ".nodegraph_usage.json")
        try:
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(self._usage_stats, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _load_favorites(self):
        fav_file = os.path.join(os.path.expanduser("~"), ".nodegraph_favorites.json")
        if os.path.exists(fav_file):
            try:
                with open(fav_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_favorites(self):
        fav_file = os.path.join(os.path.expanduser("~"), ".nodegraph_favorites.json")
        try:
            with open(fav_file, 'w', encoding='utf-8') as f:
                json.dump(self._favorites, f, ensure_ascii=False, indent=2)
        except:
            pass

    def record_usage(self, full_path):
        """仅当组件被添加到画布时才记录使用"""
        timestamp = datetime.now().isoformat()
        if full_path not in self._usage_stats:
            self._usage_stats[full_path] = []
        self._usage_stats[full_path].append(timestamp)
        self._save_usage_stats()

    def get_last_used_time(self, full_path):
        timestamps = self._usage_stats.get(full_path, [])
        if timestamps:
            return datetime.fromisoformat(timestamps[-1])
        return None

    def is_favorite(self, full_path):
        return full_path in self._favorites

    def add_to_favorites(self, full_path):
        if full_path not in self._favorites:
            self._favorites.append(full_path)
            self._save_favorites()
            return True
        return False

    def remove_from_favorites(self, full_path):
        if full_path in self._favorites:
            self._favorites.remove(full_path)
            self._save_favorites()
            return True
        return False

    def clear_recommendations(self):
        root = self.invisibleRootItem()
        i = 0
        while i < root.childCount():
            item = root.child(i)
            if item.text(0).startswith("🎯"):
                root.removeChild(item)
            else:
                i += 1

    def add_recommendations(self, recommendations):
        recommendations = list(reversed(recommendations))
        self.clear_recommendations()
        if not recommendations:
            return

        for port_name, port_label, color, rec_list in recommendations:
            title = f"🎯{port_label or port_name}推荐"
            rec_item = QTreeWidgetItem([title])
            rec_item.setFlags(rec_item.flags() & ~Qt.ItemIsSelectable)
            self.insertTopLevelItem(0, rec_item)

            for name, full_path in rec_list:
                comp_item = QTreeWidgetItem([name])
                comp_item.setData(0, Qt.UserRole + 1, full_path)
                comp_item.setForeground(0, QColor(color))
                rec_item.addChild(comp_item)

            rec_item.setExpanded(True)

    def build_filtered_tree(self):
        """根据当前筛选条件构建树"""
        self.clear()
        self._all_items = []

        # 获取所有组件
        all_components = []
        for full_path, comp_cls in self.parent.component_map.items():
            category = getattr(comp_cls, 'category', 'General')
            name = getattr(comp_cls, 'name', comp_cls.__name__)
            if not isinstance(name, str):
                name = comp_cls.NODE_NAME

            last_used = self.get_last_used_time(full_path)
            is_fav = self.is_favorite(full_path)

            all_components.append({
                'full_path': full_path,
                'name': name,
                'category': category,
                'last_used': last_used,
                'is_fav': is_fav
            })

        # 应用筛选
        filtered = []
        for comp in all_components:
            # 类别筛选
            if self._selected_categories and comp['category'] not in self._selected_categories:
                continue
            # 收藏筛选
            if self._show_only_favorites and not comp['is_fav']:
                continue
            filtered.append(comp)

        # 排序
        if self._show_time_sorted:
            # 按最后使用时间倒序
            filtered.sort(key=lambda x: x['last_used'] or datetime.min, reverse=True)
        else:
            # 按类别分组
            filtered.sort(key=lambda x: (x['category'], x['name']))

        # 构建树结构
        if self._show_time_sorted:
            # 按时间分组
            groups = {
                '最近使用': [],
                '近一周': [],
                '近一月': [],
                '10月': [],
                '9月': [],
                '今年其他月份': [],
                '去年': [],
                '更早': [],
                '未使用': []
            }

            now = datetime.now()
            for comp in filtered:
                last_used = comp['last_used']
                if last_used:
                    days_diff = (now - last_used).days
                    if days_diff <= 1:
                        groups['最近使用'].append(comp)
                    elif days_diff <= 7:
                        groups['近一周'].append(comp)
                    elif days_diff <= 30:
                        groups['近一月'].append(comp)
                    else:
                        month = last_used.month
                        year = last_used.year
                        if year == now.year:
                            if month == 10:
                                groups['10月'].append(comp)
                            elif month == 9:
                                groups['9月'].append(comp)
                            else:
                                groups['今年其他月份'].append(comp)
                        elif year == now.year - 1:
                            groups['去年'].append(comp)
                        else:
                            groups['更早'].append(comp)
                else:
                    groups['未使用'].append(comp)

            # 创建分组项
            for group_name, items in groups.items():
                if items:  # 只显示有内容的分组
                    group_item = QTreeWidgetItem([f"{group_name} ({len(items)})"])
                    group_item.setFlags(group_item.flags() & ~Qt.ItemIsSelectable)
                    self.addTopLevelItem(group_item)
                    self._all_items.append(group_item)

                    for comp in items:
                        comp_item = QTreeWidgetItem([comp['name']])
                        comp_item.setData(0, Qt.UserRole + 1, comp['full_path'])
                        if comp['is_fav']:
                            comp_item.setText(0, f"★ {comp_item.text(0)}")
                        group_item.addChild(comp_item)
                        self._all_items.append(comp_item)

                    group_item.setExpanded(True)

        else:
            # 按类别分组
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
                if comp['is_fav']:
                    comp_item.setText(0, f"★ {comp_item.text(0)}")
                cat_item.addChild(comp_item)
                self._all_items.append(comp_item)

            for cat_item in categories.values():
                cat_item.setExpanded(True)

    def refresh_components(self):
        try:
            self.build_filtered_tree()
        except Exception as e:
            print(f"刷新组件失败: {e}")

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item and item.parent():  # 确保是叶子节点（组件）
            full_path = item.data(0, Qt.UserRole + 1)
            if not full_path:
                return

            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(full_path)
            drag.setMimeData(mime_data)

            preview = self.create_drag_preview(full_path)
            drag.setPixmap(preview)
            drag.setHotSpot(preview.rect().center())
            drag.exec_(Qt.CopyAction)

    def create_drag_preview(self, full_path):
        """创建拖拽预览 pixmap（圆角阴影）"""
        comp_cls = self.parent.component_map.get(full_path)
        if not comp_cls or comp_cls.__name__.startswith("ControlFlow"):
            return self.get_default_preview(full_path)

        try:
            # 创建带阴影和圆角的预览图
            size = (180, 120)
            pixmap = QPixmap(size[0], size[1])
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)

            # 绘制圆角背景
            path = QPainterPath()
            path.addRoundedRect(0, 0, size[0] - 1, size[1] - 1, 8, 8)
            painter.setPen(QPen(QColor("#4A90E2"), 2))
            painter.setBrush(QColor("#2D2D2D"))
            painter.drawPath(path)

            # 添加阴影
            shadow_color = QColor(0, 0, 0, 80)
            for i in range(1, 5):
                painter.setPen(shadow_color)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(i, i, size[0] - 1 - i * 2, size[1] - 1 - i * 2, 8, 8)

            # 标题
            painter.setPen(Qt.white)
            font = QFont()
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            title = comp_cls.name
            if len(title) > 15:
                title = title[:15] + "..."
            painter.drawText(QRectF(15, 15, size[0] - 30, 25), Qt.AlignLeft, title)

            # 类别
            painter.setPen(QColor("#888888"))
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            category = getattr(comp_cls, 'category', 'General')
            painter.drawText(QRectF(15, 45, size[0] - 30, 18), Qt.AlignLeft, f"类别: {category}")

            # 输入输出信息
            inputs = getattr(comp_cls, 'get_inputs', lambda: [])()
            outputs = getattr(comp_cls, 'get_outputs', lambda: [])()

            y_pos = 65
            if inputs:
                painter.setPen(QColor("#2ECC71"))
                painter.drawText(QRectF(15, y_pos, size[0] - 30, 15), Qt.AlignLeft, f"输入: {len(inputs)}")
                y_pos += 18
            if outputs:
                painter.setPen(QColor("#E74C3C"))
                painter.drawText(QRectF(15, y_pos, size[0] - 30, 15), Qt.AlignLeft, f"输出: {len(outputs)}")
                y_pos += 18

            # 使用统计
            usage_count = len(self._usage_stats.get(full_path, []))
            if usage_count > 0:
                painter.setPen(QColor("#F39C12"))
                painter.drawText(QRectF(15, y_pos, size[0] - 30, 15), Qt.AlignLeft, f"使用: {usage_count}次")

            # 收藏标记
            if self.is_favorite(full_path):
                painter.setPen(QColor("#FFD700"))
                painter.drawText(QRectF(size[0] - 30, 15, 25, 25), Qt.AlignCenter, "★")

            painter.end()
            return pixmap
        except:
            return self.get_default_preview(full_path)

    def get_default_preview(self, name):
        pixmap = QPixmap(120, 60)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 圆角背景
        path = QPainterPath()
        path.addRoundedRect(0, 0, 119, 59, 6, 6)
        painter.setPen(QPen(QColor("#4A90E2"), 2))
        painter.setBrush(QColor("#2D2D2D"))
        painter.drawPath(path)

        # 文本
        painter.setPen(Qt.black)
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        display_name = name
        if len(display_name) > 12:
            display_name = display_name[:12] + "..."
        painter.drawText(QRectF(10, 20, 100, 20), Qt.AlignLeft, display_name)

        painter.end()
        return pixmap

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item and item.parent():  # 叶子节点
            menu = QMenu(self)
            full_path = item.data(0, Qt.UserRole + 1)
            is_fav = self.is_favorite(full_path)

            if is_fav:
                action = menu.addAction("❌ 移除收藏")
            else:
                action = menu.addAction("⭐ 添加收藏")

            action.triggered.connect(lambda: self._toggle_favorite(full_path, item, is_fav))
            menu.exec_(event.globalPos())

    def _toggle_favorite(self, full_path, item, is_currently_fav):
        if is_currently_fav:
            self.remove_from_favorites(full_path)
            text = item.text(0)
            if text.startswith("★ "):
                item.setText(0, text[2:])
        else:
            if self.add_to_favorites(full_path):
                current_text = item.text(0)
                if not current_text.startswith("★ "):
                    item.setText(0, f"★ {current_text}")
        self.refresh_components()

    def filter_items(self, keyword: str):
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
            if not item.parent():
                continue
            name = item.text(0).lower()
            if keyword in name:
                item.setHidden(False)
                parent = item.parent()
                if parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)