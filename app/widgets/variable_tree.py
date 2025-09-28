# app/widgets/variable_tree.py
from PyQt5.QtWidgets import QTreeWidgetItem, QMenu, QAction
from PyQt5.QtCore import Qt, pyqtSignal
from qfluentwidgets import TreeWidget
import pandas as pd
import numpy as np


class VariableTreeWidget(TreeWidget):
    """PyCharm 风格变量展示树"""
    previewRequested = pyqtSignal(object)

    def __init__(self, data=None, max_depth=5, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setEditTriggers(self.NoEditTriggers)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(False)  # 关闭交替色
        self.setFixedHeight(150)

        # ✅ PyCharm 风格：紧凑、对齐、无干扰
        self.setStyleSheet("""
            TreeWidget {
                font-family: "Consolas", "Courier New", monospace;
                font-size: 12px;
                show-decoration-selected: 1;
            }
            QTreeView::item {
                padding: 2px 0 2px 0;
                border: none;
            }
        """)

        self._original_data = None
        if data is not None:
            self.set_data(data, max_depth)

    def set_data(self, data, max_depth=5):
        self._original_data = data
        self.clear()
        self._build_tree(data, self.invisibleRootItem(), "", max_depth)
        if self.topLevelItemCount() > 0:
            # PyCharm 行为：顶层如果是容器，默认展开
            top_item = self.topLevelItem(0)
            if top_item.childCount() > 0:
                self.expandItem(top_item)

    def _build_tree(self, obj, parent_item, key, max_depth, current_depth=0):
        if current_depth > max_depth:
            item = QTreeWidgetItem(parent_item, ["<max recursion depth>"])
            item.setForeground(0, Qt.gray)
            return

        # 根据是否有 key 决定显示格式
        if key == "":
            # 顶层对象
            display_text = self._format_value(obj)
        else:
            display_text = f"{key}: {self._format_value(obj)}"

        item = QTreeWidgetItem(parent_item, [display_text])

        # 只有容器类型才添加子项（PyCharm 行为）
        if isinstance(obj, dict):
            for k, v in obj.items():
                self._build_tree(v, item, str(k), max_depth, current_depth + 1)
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                self._build_tree(v, item, str(i), max_depth, current_depth + 1)
        elif isinstance(obj, set):
            for i, v in enumerate(obj):
                self._build_tree(v, item, f"[{i}]", max_depth, current_depth + 1)
        elif hasattr(obj, '__dict__') and obj.__dict__:
            for attr_name, attr_value in obj.__dict__.items():
                self._build_tree(attr_value, item, attr_name, max_depth, current_depth + 1)
        elif hasattr(obj, '__slots__'):
            for slot in getattr(obj, '__slots__', []):
                if hasattr(obj, slot):
                    attr_value = getattr(obj, slot)
                    self._build_tree(attr_value, item, slot, max_depth, current_depth + 1)

    def _format_value(self, obj):
        """PyCharm 风格的值格式化"""
        if obj is None:
            return "None"
        elif isinstance(obj, bool):
            return str(obj).lower()
        elif isinstance(obj, str):
            if len(obj) <= 50:
                return f"'{obj}'"
            else:
                return f"'{obj[:47]}...'"
        elif isinstance(obj, (int, float, np.number)):
            return str(obj)
        elif isinstance(obj, pd.DataFrame):
            return f"<DataFrame({obj.shape[0]}, {obj.shape[1]})>"
        elif isinstance(obj, pd.Series):
            return f"<Series({len(obj)})>"
        elif isinstance(obj, dict):
            return f"dict({len(obj)})"
        elif isinstance(obj, list):
            return f"list({len(obj)})"
        elif isinstance(obj, tuple):
            return f"tuple({len(obj)})"
        elif isinstance(obj, set):
            return f"set({len(obj)})"
        elif hasattr(obj, '__class__'):
            return f"<{obj.__class__.__module__}.{obj.__class__.__name__}>"
        else:
            return str(obj)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if not item or self._original_data is None:
            return

        menu = QMenu(self)
        if isinstance(self._original_data, pd.DataFrame):
            action = QAction("🔍 预览完整数据表", self)
            action.triggered.connect(lambda: self.previewRequested.emit(self._original_data))
            menu.addAction(action)
            menu.addSeparator()

        # PyCharm 风格：复制值
        copy_action = QAction("📋 Copy Value", self)
        copy_action.triggered.connect(lambda: self._copy_value(str(self._original_data)))
        menu.addAction(copy_action)

        menu.exec_(event.globalPos())

    def _copy_value(self, text):
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)