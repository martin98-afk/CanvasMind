# -*- coding: utf-8 -*-
from NodeGraphQt import BaseNode
from PyQt5.QtCore import Qt, QMimeData, QRectF
from PyQt5.QtGui import QDrag, QPixmap, QPainter, QColor, QPen, QFont
from PyQt5.QtWidgets import QTreeWidgetItem, QWidget, QVBoxLayout
from qfluentwidgets import TreeWidget, SearchLineEdit, FluentStyleSheet

from app.components.base import BaseComponent
from app.scan_components import scan_components


class DraggableTreeWidget(TreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setDragDropMode(TreeWidget.DragOnly)
        self._all_items = []  # 用于搜索
        self.refresh_components()

    def build_component_tree(self):
        self.clear()
        self._all_items = []
        categories = {}
        for full_path, comp_cls in self.parent.component_map.items():
            try:
                category = getattr(comp_cls, 'category', 'General')
                name = getattr(comp_cls, 'name', comp_cls.__name__)
                if not isinstance(name, str):
                    name = comp_cls.NODE_NAME

                display_path = f"{category}/{name}"

                if category not in categories:
                    cat_item = QTreeWidgetItem([category])
                    self.addTopLevelItem(cat_item)
                    categories[category] = cat_item
                    self._all_items.append(cat_item)
                else:
                    cat_item = categories[category]

                comp_item = QTreeWidgetItem([name])
                # 存储完整路径用于拖拽和预览
                comp_item.setData(0, Qt.UserRole + 1, display_path)
                cat_item.addChild(comp_item)
                self._all_items.append(comp_item)
            except Exception as e:
                import traceback
                traceback.print_exc()

        self.expandAll()

    def refresh_components(self):
        """刷新组件树"""
        try:
            self.build_component_tree()
        except Exception as e:
            print(f"刷新组件失败: {e}")

    def startDrag(self, supportedActions):
        """开始拖拽操作，带预览"""
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

    def get_default_preview(self, name):
        pixmap = QPixmap(120, 60)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#4A90E2"), 2))
        painter.drawRect(0, 0, 119, 59)
        painter.setPen(Qt.black)
        painter.drawText(QRectF(10, 20, 100, 20), Qt.AlignLeft, name)
        painter.end()
        return pixmap

    def create_drag_preview(self, full_path):
        """创建拖拽预览 pixmap"""
        comp_cls = self.parent.component_map.get(full_path)
        if not comp_cls or comp_cls.__name__.startswith("ControlFlow"):
            return self.get_default_preview(full_path)
        try:
            pixmap = QPixmap(150, 90)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)

            painter.setPen(QPen(QColor("#4A90E2"), 2))
            painter.setBrush(QColor("#2D2D2D"))
            painter.drawRect(0, 0, 149, 89)

            painter.setPen(Qt.white)
            font = QFont()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(10, 10, 130, 20), Qt.AlignLeft, comp_cls.name)

            painter.setPen(QColor("#888888"))
            font.setBold(False)
            painter.setFont(font)
            painter.drawText(QRectF(10, 35, 130, 15), Qt.AlignLeft, f"类别: {comp_cls.category}")

            inputs = getattr(comp_cls, 'get_inputs', lambda: [])()
            outputs = getattr(comp_cls, 'get_outputs', lambda: [])()
            if inputs:
                painter.setPen(QColor("#2ECC71"))
                painter.drawText(QRectF(10, 55, 130, 15), Qt.AlignLeft, f"输入: {len(inputs)}")
            if outputs:
                painter.setPen(QColor("#E74C3C"))
                painter.drawText(QRectF(10, 70, 130, 15), Qt.AlignLeft, f"输出: {len(outputs)}")

            painter.end()
            return pixmap
        except:
            return self.get_default_preview(full_path)

    # ==================== 搜索功能 ====================
    def filter_items(self, keyword: str):
        """
        根据关键词过滤树节点（模糊匹配，不区分大小写）
        """
        keyword = keyword.strip().lower()
        if not keyword:
            for item in self._all_items:
                item.setHidden(False)
                if item.parent():
                    item.parent().setExpanded(True)
            return

        # 先隐藏所有
        for item in self._all_items:
            item.setHidden(True)

        # 显示匹配项
        for item in self._all_items:
            if not item.parent():  # 分类项
                continue
            name = item.text(0).lower()
            category = item.parent().text(0).lower()
            if keyword in name or keyword in category:
                item.setHidden(False)
                item.parent().setHidden(False)
                item.parent().setExpanded(True)


class DraggableTreePanel(QWidget):
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
        self.tree = DraggableTreeWidget(self.parent_window)
        self.tree.setHeaderHidden(True)
        self.tree.setFixedWidth(200)
        layout.addWidget(self.search_box)
        layout.addWidget(self.tree)

    def _on_search_text_changed(self, text: str):
        self.tree.filter_items(text)
