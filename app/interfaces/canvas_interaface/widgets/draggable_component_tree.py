# -*- coding: utf-8 -*-
import json
from datetime import datetime
from pathlib import Path

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QMimeData, QRectF, QPoint
from PyQt5.QtGui import QDrag, QPixmap, QPainter, QColor, QPen, QFont, QPainterPath, QFontMetrics
from PyQt5.QtWidgets import QTreeWidgetItem, QWidget, QVBoxLayout, QHBoxLayout
from loguru import logger
from qfluentwidgets import FluentIcon as FIF, TransparentToggleToolButton, RoundMenu, Action
from qfluentwidgets import TreeWidget, SearchLineEdit, FluentStyleSheet, DropDownPushButton

from app.scan_components import ComponentScanner
from app.utils.utils import get_pinyin_search_keys
from app.widgets.basic_widget.category_filter import CategoryFilterDialog


class DraggableTreePanel(QWidget):
    """带搜索框的组件树面板"""
    filter_changed_signal = QtCore.pyqtSignal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("draggableTree")
        self.parent_window = parent
        self.category_filter_dialog = None
        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumWidth(210)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 4, 3, 4)
        layout.setSpacing(4)

        # 第一行：控制栏
        control_layout = QHBoxLayout()
        control_layout.setSpacing(4)

        # 类别选择按钮
        self.category_button = DropDownPushButton(FIF.BOOK_SHELF, self.tr("类别"), self)
        self.category_button.setFixedHeight(28)
        self.category_button.setToolTip(self.tr("类别筛选"))
        self.category_button.clicked.connect(lambda: self._show_category_dialog())

        # 时间排序按钮
        self.time_toggle = TransparentToggleToolButton(FIF.HISTORY, self)
        self.time_toggle.setFixedSize(24, 28)
        self.time_toggle.setToolTip(self.tr("按最后使用时间排序"))
        self.time_toggle.toggled.connect(self._on_time_toggled)

        # 收藏按钮
        self.favorite_toggle = TransparentToggleToolButton(FIF.EXPRESSIVE_INPUT_ENTRY, self)
        self.favorite_toggle.setFixedSize(24, 28)
        self.favorite_toggle.setToolTip(self.tr("只显示收藏组件"))
        self.favorite_toggle.toggled.connect(self._on_favorite_toggled)

        # 搜索 toggle 按钮
        self.search_toggle = TransparentToggleToolButton(FIF.SEARCH, self)
        self.search_toggle.setFixedSize(24, 28)
        self.search_toggle.setToolTip(self.tr("搜索组件"))
        self.search_toggle.toggled.connect(self._on_search_toggled)

        control_layout.addWidget(self.category_button)
        control_layout.addWidget(self.search_toggle)
        control_layout.addWidget(self.time_toggle)
        control_layout.addWidget(self.favorite_toggle)

        # 搜索框（默认隐藏）
        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText(self.tr("🔍 搜索组件..."))
        self.search_box.setClearButtonEnabled(True)
        FluentStyleSheet.LINE_EDIT.apply(self.search_box)
        self.search_box.textChanged.connect(self._on_search_text_changed)
        self.search_box.searchSignal.connect(self._on_search_text_changed)
        self.search_box.clearSignal.connect(self._on_search_text_changed)
        self.search_box.hide()  # 初始隐藏

        # 组件树
        self.tree = DraggableTreeWidget(self.parent_window)
        self.tree.setHeaderHidden(True)

        layout.addLayout(control_layout)
        layout.addWidget(self.search_box)
        layout.addWidget(self.tree)

        # 初始化类别列表
        self._init_categories()

    def _on_search_toggled(self, checked: bool):
        if checked:
            self.search_box.show()
            self.search_box.setFocus()
        else:
            self.search_box.hide()
            self.search_box.clear()
            self.tree.filter_items("")

    def _init_categories(self):
        """初始化类别列表"""
        self.category_filter_dialog = CategoryFilterDialog(self.parent_window)
        self.category_filter_dialog.categories_changed.connect(self._on_categories_changed)

    def _show_category_dialog(self):
        """显示类别筛选对话框"""
        if self.category_filter_dialog:
            pos = self.category_button.mapToGlobal(QPoint(10, self.category_button.height()))
            self.category_filter_dialog.show_at(pos)

    def _on_categories_changed(self, selected_categories):
        """类别选择变化回调"""
        self.tree._selected_categories = selected_categories
        self.tree.refresh_components()
        self.filter_changed_signal.emit(selected_categories)

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
        self._all_items = []
        self._usage_stats = self._load_usage_stats()
        self._favorites = self._load_favorites()
        self._show_time_sorted = False
        self._show_only_favorites = False
        self._selected_categories = set()

        self._init_components()

    def _load_usage_stats(self):
        stats_file = Path("./canvas_files/nodegraph_usage.json")
        if stats_file.exists():
            try:
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_usage_stats(self):
        stats_file = Path("./canvas_files/nodegraph_usage.json")
        try:
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(self._usage_stats, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _load_favorites(self):
        fav_file = Path("./canvas_files/nodegraph_favorites.json")
        if fav_file.exists():
            try:
                with open(fav_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_favorites(self):
        fav_file = Path("./canvas_files/nodegraph_favorites.json")
        try:
            with open(fav_file, 'w', encoding='utf-8') as f:
                json.dump(self._favorites, f, ensure_ascii=False, indent=2)
        except:
            pass

    def record_usage(self, full_path):
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
        # 使用特定标识符匹配推荐项
        rec_prefix = self.tr("🎯")
        while i < root.childCount():
            item = root.child(i)
            if item.text(0).startswith(rec_prefix):
                root.removeChild(item)
            else:
                i += 1

    def add_recommendations(self, recommendations):
        recommendations = list(reversed(recommendations))
        self.clear_recommendations()
        if not recommendations:
            return

        for port_name, port_label, color, rec_list in recommendations:
            label = port_label or port_name
            title = self.tr("🎯{}推荐").format(label)
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

        comp_map, file_map = ComponentScanner().get_components()
        all_components = []
        for full_path, comp_cls in comp_map.items():
            parts = full_path.split("/")
            category = parts[0]
            name = parts[-1]
            if not isinstance(name, str):
                name = comp_cls.NODE_NAME

            py_keys = get_pinyin_search_keys(name)
            search_metadata = f"{full_path} {py_keys}".lower()

            all_components.append({
                'full_path': full_path,
                'name': name,
                'category': category,
                'last_used': self.get_last_used_time(full_path),
                'is_fav': self.is_favorite(full_path),
                'search_metadata': search_metadata
            })

        filtered = []
        for comp in all_components:
            if self._selected_categories and comp['category'] not in self._selected_categories:
                continue
            if self._show_only_favorites and not comp['is_fav']:
                continue
            filtered.append(comp)

        if self._show_time_sorted:
            filtered.sort(key=lambda x: x['last_used'] or datetime.min, reverse=True)
            # 翻译分组标题
            groups = {
                self.tr('最近使用'): [],
                self.tr('近一周'): [],
                self.tr('近一月'): [],
                self.tr('未使用'): []
            }
            now = datetime.now()
            for comp in filtered:
                last_used = comp['last_used']
                if not last_used:
                    groups[self.tr('未使用')].append(comp)
                elif (now - last_used).days <= 1:
                    groups[self.tr('最近使用')].append(comp)
                elif (now - last_used).days <= 7:
                    groups[self.tr('近一周')].append(comp)
                else:
                    groups[self.tr('近一月')].append(comp)

            for group_name, items in groups.items():
                if items:
                    group_item = QTreeWidgetItem([f"{group_name} ({len(items)})"])
                    group_item.setFlags(group_item.flags() & ~Qt.ItemIsSelectable)
                    self.addTopLevelItem(group_item)
                    self._all_items.append(group_item)
                    for comp in items:
                        display_name = comp['name']
                        if comp['is_fav']:
                            display_name = f"★ {display_name}"
                        comp_item = QTreeWidgetItem([display_name])
                        comp_item.setData(0, Qt.UserRole + 1, comp['full_path'])
                        comp_item.setData(0, Qt.UserRole + 2, comp['search_metadata'])
                        group_item.addChild(comp_item)
                        self._all_items.append(comp_item)
                    group_item.setExpanded(True)
        else:
            filtered.sort(key=lambda x: x['full_path'])
            path_nodes = {}

            for comp in filtered:
                parts = comp['full_path'].split("/")
                current_parent = None
                path_acc = ""

                for i in range(len(parts) - 1):
                    part_name = parts[i]
                    path_acc = "/".join(parts[:i + 1])
                    if path_acc not in path_nodes:
                        folder_item = QTreeWidgetItem([part_name])
                        if current_parent:
                            current_parent.addChild(folder_item)
                        else:
                            self.addTopLevelItem(folder_item)
                        path_nodes[path_acc] = folder_item
                        self._all_items.append(folder_item)
                    current_parent = path_nodes[path_acc]

                display_name = comp['name']
                if comp['is_fav']:
                    display_name = f"★ {display_name}"

                comp_item = QTreeWidgetItem([display_name])
                comp_item.setData(0, Qt.UserRole + 1, comp['full_path'])
                comp_item.setData(0, Qt.UserRole + 2, comp['search_metadata'])

                if current_parent:
                    current_parent.addChild(comp_item)
                else:
                    self.addTopLevelItem(comp_item)
                self._all_items.append(comp_item)

            for i in range(self.topLevelItemCount()):
                self.topLevelItem(i).setExpanded(True)

    def _init_components(self):
        self.build_filtered_tree()

    def refresh_components(self):
        try:
            self.build_filtered_tree()
        except Exception as e:
            logger.error(self.tr("刷新组件失败: {}").format(e))

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item and item.parent():
            full_path = item.data(0, Qt.UserRole + 1)
            if not full_path:
                return

            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(full_path)
            drag.setMimeData(mime_data)
            LOGIC_WIDTH, LOGIC_HEIGHT = 180, 120
            preview = self.create_drag_preview(full_path)
            drag.setPixmap(preview)
            drag.setHotSpot(QPoint(LOGIC_WIDTH // 2 - 12, 3 * LOGIC_HEIGHT // 4))
            drag.exec_(Qt.CopyAction)

    def create_drag_preview(self, full_path):
        comp_map, file_map = ComponentScanner().get_components()
        comp_cls = comp_map.get(full_path)
        if not comp_cls or comp_cls.__name__.startswith("ControlFlow"):
            return self.get_default_preview(full_path)

        try:
            base_width, base_height = 180, 120
            dpr = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0

            pixmap = QPixmap(int(base_width * dpr), int(base_height * dpr))
            pixmap.setDevicePixelRatio(dpr)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

            width, height = base_width, base_height

            path = QPainterPath()
            path.addRoundedRect(0, 0, width - 1, height - 1, 10, 10)
            painter.setPen(QPen(QColor("#4A90E2"), 1.5))
            painter.setBrush(QColor("#2D2D2D"))
            painter.drawPath(path)

            for i, alpha in enumerate([40, 25, 10], 1):
                painter.setPen(QColor(0, 0, 0, alpha))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(i, i, width - 1 - i * 2, height - 1 - i * 2, 10, 10)

            # === 1. 标题 ===
            painter.setPen(Qt.white)
            font = QFont()
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)
            title = getattr(comp_cls, 'name', comp_cls.__name__)
            if len(title) > 14:
                title = title[:14] + "…"
            painter.drawText(QRectF(12, 12, width - 24, 24), Qt.AlignLeft, title)

            # === 2. 类别 ===
            painter.setPen(QColor("#AAAAAA"))
            font.setPointSize(10)
            font.setBold(False)
            painter.setFont(font)
            category = getattr(comp_cls, 'category', self.tr('General'))
            painter.drawText(QRectF(12, 38, width - 24, 20), Qt.AlignLeft, self.tr("📁 {}").format(category))

            # === 3. 描述 ===
            desc_lines = []
            description = getattr(comp_cls, 'description', "")
            if isinstance(description, str) and description.strip():
                desc_text = description.strip()
                font.setPointSize(9)
                font.setItalic(True)
                painter.setFont(font)
                fm = QFontMetrics(font)
                text_width = width - 24
                max_lines = 2
                current_line = ""
                for char in desc_text:
                    test_line = current_line + char
                    w = fm.horizontalAdvance(test_line) if hasattr(fm, 'horizontalAdvance') else fm.width(test_line)
                    if w <= text_width:
                        current_line = test_line
                    else:
                        if current_line:
                            desc_lines.append(current_line)
                            if len(desc_lines) >= max_lines:
                                desc_lines[-1] = desc_lines[-1][:max(0, len(desc_lines[-1]) - 1)] + "…"
                                break
                        current_line = char
                if current_line and len(desc_lines) < max_lines:
                    desc_lines.append(current_line)

            line_height = QFontMetrics(font).height() + 2
            desc_y = 38 + 20 + 4
            painter.setPen(QColor("#CCCCCC"))
            for i, line in enumerate(desc_lines):
                painter.drawText(QRectF(12, desc_y + i * line_height, width - 24, line_height), Qt.AlignLeft, line)

            # === 底部信息 ===
            inputs = getattr(comp_cls, 'get_inputs', lambda: [])()
            outputs = getattr(comp_cls, 'get_outputs', lambda: [])()
            usage_count = len(self._usage_stats.get(full_path, []))
            bottom_y = height - 22
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            if inputs:
                painter.setPen(QColor("#2ECC71"))
                painter.drawText(QRectF(12, bottom_y, 80, 20), Qt.AlignLeft, f"◂ {len(inputs)}")
            if usage_count > 0:
                painter.setPen(QColor("#F39C12"))
                usage_text = self.tr("🕒 {}次").format(usage_count)
                fm = QFontMetrics(font)
                tw = fm.horizontalAdvance(usage_text) if hasattr(fm, 'horizontalAdvance') else fm.width(usage_text)
                painter.drawText(QRectF((width - tw) / 2, bottom_y, tw, 20), Qt.AlignLeft, usage_text)
            if outputs:
                painter.setPen(QColor("#E74C3C"))
                painter.drawText(QRectF(width - 92, bottom_y, 80, 20), Qt.AlignRight, f"{len(outputs)} ▸")

            if self.is_favorite(full_path):
                painter.setPen(QColor("#FFD700"))
                font.setPointSize(14)
                painter.setFont(font)
                painter.drawText(QRectF(width - 24, 10, 20, 20), Qt.AlignCenter, "★")
            painter.end()
            return pixmap
        except Exception as e:
            logger.error(self.tr("预览图渲染失败: {}").format(e))
            return self.get_default_preview(full_path)

    def get_default_preview(self, name):
        pixmap = QPixmap(120, 60)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, 119, 59, 6, 6)
        painter.setPen(QPen(QColor("#4A90E2"), 2))
        painter.setBrush(QColor("#2D2D2D"))
        painter.drawPath(path)
        painter.setPen(Qt.black)
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        display_name = name.split("/")[-1]
        if len(display_name) > 12: display_name = display_name[:12] + "..."
        painter.drawText(QRectF(10, 20, 100, 20), Qt.AlignLeft, display_name)
        painter.end()
        return pixmap

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item and item.parent():
            full_path = item.data(0, Qt.UserRole + 1)
            if not full_path: return
            menu = RoundMenu(parent=self)
            is_fav = self.is_favorite(full_path)

            # 翻译右键菜单动作
            remove_text = self.tr("❌ 移除收藏")
            add_text = self.tr("⭐ 添加收藏")
            action_text = remove_text if is_fav else add_text

            menu.addAction(Action(action_text,
                                  triggered=lambda: self._toggle_favorite(full_path, item, is_fav)))
            menu.exec_(event.globalPos())

    def _toggle_favorite(self, full_path, item, is_currently_fav):
        if is_currently_fav:
            self.remove_from_favorites(full_path)
            text = item.text(0)
            if text.startswith("★ "): item.setText(0, text[2:])
        else:
            if self.add_to_favorites(full_path):
                current_text = item.text(0)
                if not current_text.startswith("★ "): item.setText(0, f"★ {current_text}")
        self.refresh_components()

    def filter_items(self, keyword: str):
        keyword = keyword.strip().lower()
        if not keyword:
            for item in self._all_items:
                item.setHidden(False)
                if item.parent(): item.parent().setExpanded(True)
            return

        for item in self._all_items:
            item.setHidden(True)

        for item in self._all_items:
            search_data = item.data(0, Qt.UserRole + 2)
            if not search_data: continue

            if keyword in search_data:
                item.setHidden(False)
                p = item.parent()
                while p:
                    p.setHidden(False)
                    p.setExpanded(True)
                    p = p.parent()