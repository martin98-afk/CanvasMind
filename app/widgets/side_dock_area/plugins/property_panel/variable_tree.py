import os
import sys
import subprocess
from functools import lru_cache
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QMimeData
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QClipboard, QImage
from PyQt5.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QHeaderView, QApplication,
    QWidget, QVBoxLayout, QMenu, QAction, QFileDialog
)

# === 导入你项目中的依赖（按需启用）===
# 假设你有这些模块（若无，可先注释预览相关功能）
try:
    from app.components.base import ArgumentType  # 如果你用 ArgumentType
except ImportError:
    class ArgumentType:
        @staticmethod
        def is_image(): return False
        @staticmethod
        def is_array(): return False
        @staticmethod
        def is_bool(): return False
        @staticmethod
        def is_number(): return False
        JSON = "json"
        TEXT = "text"
        FILE = "file"
        CSV = "csv"
        EXCEL = "excel"
        def __eq__(self, other): return False

# === 工具函数（从你原始文件提取）===
def get_simple_repr(obj, max_len=400):
    s = str(obj)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s

def _is_image_file(obj):
    if isinstance(obj, str) and os.path.isfile(obj):
        ext = os.path.splitext(obj.lower())[1]
        return ext in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
    return False

def _is_pil_image(obj):
    try:
        from PIL import Image
        return isinstance(obj, Image.Image)
    except ImportError:
        return False

def _get_formatted_type_and_value(obj, arg_type=None):
    # 完整复用你原始逻辑（简化版，不含 ArgumentType 依赖）
    if obj is None:
        return "(NoneType) None"
    if isinstance(obj, bool):
        return f"(bool) {str(obj).lower()}"
    elif isinstance(obj, str):
        if _is_image_file(obj):
            return f"(Image) '{os.path.basename(obj)}'"
        elif obj.endswith('.csv') and os.path.isfile(obj):
            return f"(CSV) '{os.path.basename(obj)}'"
        elif obj.lower().endswith(('.xlsx', '.xls')) and os.path.isfile(obj):
            return f"(Excel) '{os.path.basename(obj)}'"
        else:
            preview = get_simple_repr(obj, 100)
            return f"(str) '{preview}'"
    elif isinstance(obj, (int, float)):
        return f"({type(obj).__name__}) {obj}"
    elif _is_pil_image(obj):
        return f"(PIL.Image) size={obj.size}"
    elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):  # numpy
        return f"(ndarray) shape={obj.shape}, dtype={obj.dtype}"
    elif hasattr(obj, 'columns') and hasattr(obj, 'shape'):  # pandas
        return f"(DataFrame) ({obj.shape[0]} x {obj.shape[1]})"
    elif isinstance(obj, dict):
        return f"(dict) len={len(obj)}"
    elif isinstance(obj, (list, tuple)):
        return f"({type(obj).__name__}) len={len(obj)}"
    else:
        return f"({type(obj).__name__}) {get_simple_repr(obj)}"

# === 图标缓存 ===
@lru_cache(maxsize=32)
def _create_icon(symbol: str, color: str = "#888") -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(1)
    painter.setPen(pen)
    font = painter.font()
    font.setPointSize(10)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, symbol)
    painter.end()
    return QIcon(pixmap)

def get_icon_for_type(obj):
    if obj is None:
        return _create_icon("∅", "#9E9E9E")
    elif isinstance(obj, dict):
        return _create_icon("{...}", "#4CAF50")
    elif isinstance(obj, (list, tuple)):
        return _create_icon("[...]", "#2196F3")
    elif isinstance(obj, str):
        if _is_image_file(obj):
            return _create_icon("🖼", "#FF9800")
        else:
            return _create_icon('".."', "#FF9800")
    elif isinstance(obj, bool):
        return _create_icon("✓", "#4CAF50")
    elif isinstance(obj, (int, float)):
        return _create_icon("123", "#9C27B0")
    elif _is_pil_image(obj):
        return _create_icon("🖼", "#FF5722")
    elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):
        return _create_icon("[arr]", "#795548")
    elif hasattr(obj, 'columns') and hasattr(obj, 'shape'):
        return _create_icon("DF", "#E91E63")
    else:
        return _create_icon("?", "#607D8B")

# === 构建数据节点 ===
MAX_NESTING_DEPTH = 5
MAX_DICT_KEYS = 100
MAX_LIST_ITEMS = 100
STR_MAX_SHOW_LENGTH = 400

def build_node_data(obj: Any, name: str = "<root>", depth: int = 0) -> Dict:
    if depth > MAX_NESTING_DEPTH:
        return {"name": name, "value_preview": "... (max depth)", "type": "truncated", "has_children": False, "raw_obj": None}
    try:
        value_repr = _get_formatted_type_and_value(obj)
        has_children = False
        if isinstance(obj, dict) and len(obj) > 0 and depth < MAX_NESTING_DEPTH:
            has_children = True
        elif isinstance(obj, (list, tuple)) and len(obj) > 0 and depth < MAX_NESTING_DEPTH:
            has_children = True
        elif _is_pil_image(obj):
            has_children = False
        elif hasattr(obj, 'columns') and hasattr(obj, 'shape') and depth < MAX_NESTING_DEPTH:
            has_children = True
        elif hasattr(obj, 'shape') and hasattr(obj, 'dtype') and len(obj.shape) > 0 and depth < MAX_NESTING_DEPTH:
            has_children = True
        return {"name": name, "value_preview": value_repr, "type": type(obj).__name__, "has_children": has_children, "raw_obj": obj}
    except Exception as e:
        return {"name": name, "value_preview": f"<error: {e}>", "type": "error", "has_children": False, "raw_obj": None}

def build_children_data(parent_obj: Any, depth: int) -> List[Dict]:
    children = []
    try:
        if isinstance(parent_obj, dict):
            for k in list(parent_obj.keys())[:MAX_DICT_KEYS]:
                children.append(build_node_data(parent_obj[k], str(k), depth + 1))
        elif isinstance(parent_obj, (list, tuple)):
            for i, v in enumerate(parent_obj[:MAX_LIST_ITEMS]):
                children.append(build_node_data(v, str(i), depth + 1))
        elif hasattr(parent_obj, 'columns') and hasattr(parent_obj, 'shape'):  # DataFrame
            import pandas as pd
            df = parent_obj
            for col in list(df.columns)[:20]:
                children.append(build_node_data(df[col], str(col), depth + 1))
        elif hasattr(parent_obj, 'shape') and hasattr(parent_obj, 'dtype'):  # ndarray
            arr = parent_obj
            if arr.ndim == 1:
                for i in range(min(arr.shape[0], MAX_LIST_ITEMS)):
                    children.append(build_node_data(arr[i], f"[{i}]", depth + 1))
            elif arr.ndim == 2:
                for i in range(min(arr.shape[0], 20)):
                    children.append(build_node_data(arr[i], f"[{i}]", depth + 1))
    except Exception as e:
        children.append({"name": "<error>", "value_preview": str(e), "type": "error", "has_children": False, "raw_obj": None})
    return children

# === 核心控件 ===
class VariableTreeWidget(QTreeWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setHeaderLabels(["Name", "Value"])
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setIndentation(12)
        self.setExpandsOnDoubleClick(True)
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        self.itemExpanded.connect(self.on_item_expanded)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self._original_data = None
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #2d2d30;
                color: #d4d4d4;
                border: none;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QTreeWidget::item {
                padding: 2px;
            }
            QTreeWidget::item:hover {
                background-color: #3e3e42;
            }
            QTreeWidget::item:selected {
                background-color: #37373d;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #d4d4d4;
                padding: 4px;
                border: none;
            }
        """)

    def set_data(self, data: Any, name: str = "variable"):
        self._original_data = data
        self.clear()
        root_node = build_node_data(data, name, depth=0)
        root_item = QTreeWidgetItem([root_node["name"], root_node["value_preview"]])
        root_item.setData(0, Qt.UserRole, root_node)
        if root_node["has_children"]:
            root_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        self.addTopLevelItem(root_item)
        root_item.setIcon(0, get_icon_for_type(root_node["raw_obj"]))

    def on_item_expanded(self, item: QTreeWidgetItem):
        node_data = item.data(0, Qt.UserRole)
        if not node_data or item.childCount() > 0:
            return
        raw_obj = node_data["raw_obj"]
        depth = 0
        p = item
        while p.parent():
            p = p.parent()
            depth += 1
        children_data = build_children_data(raw_obj, depth)
        for child in children_data:
            child_item = QTreeWidgetItem([child["name"], child["value_preview"]])
            child_item.setData(0, Qt.UserRole, child)
            if child["has_children"]:
                child_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            item.addChild(child_item)
            child_item.setIcon(0, get_icon_for_type(child["raw_obj"]))

    def show_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        node_data = item.data(0, Qt.UserRole)
        if not node_data:
            return
        obj = node_data["raw_obj"]
        menu = QMenu(self)

        # === 复制值 ===
        copy_action = QAction("📋 复制值", self)
        copy_action.triggered.connect(lambda: self._copy_value(str(obj)))
        menu.addAction(copy_action)

        # === 文件操作 ===
        if isinstance(obj, str) and os.path.isfile(obj):
            open_action = QAction("📂 在资源管理器中打开", self)
            open_action.triggered.connect(lambda: self._open_file_in_explorer(obj))
            menu.addAction(open_action)

            if _is_image_file(obj):
                preview_action = QAction("🖼️ 预览图像", self)
                preview_action.triggered.connect(lambda: self._preview_image(obj))
                menu.addAction(preview_action)
            elif obj.endswith('.csv'):
                preview_action = QAction("📊 预览 CSV", self)
                preview_action.triggered.connect(lambda: self._preview_csv(obj))
                menu.addAction(preview_action)
            elif obj.lower().endswith(('.xlsx', '.xls')):
                preview_action = QAction("📊 预览 Excel", self)
                preview_action.triggered.connect(lambda: self._preview_excel(obj))
                menu.addAction(preview_action)

        # === 数据结构预览 ===
        if isinstance(obj, (list, tuple, dict)):
            preview_action = QAction("🔍 预览完整结构", self)
            preview_action.triggered.connect(lambda: self._preview_nested(obj))
            menu.addAction(preview_action)
        elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):  # numpy
            preview_action = QAction("🔍 预览数组", self)
            preview_action.triggered.connect(lambda: self._preview_array(obj))
            menu.addAction(preview_action)
        elif hasattr(obj, 'columns') and hasattr(obj, 'shape'):  # pandas
            preview_action = QAction("🔍 预览 DataFrame", self)
            preview_action.triggered.connect(lambda: self._preview_dataframe(obj))
            menu.addAction(preview_action)

        menu.exec_(self.viewport().mapToGlobal(pos))

    def _copy_value(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def _open_file_in_explorer(self, filepath):
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", filepath], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", filepath], check=False)
        else:
            subprocess.run(["xdg-open", os.path.dirname(filepath)], check=False)

    # === 以下是占位预览函数（你可替换为真实实现）===
    def _preview_image(self, obj): print(f"[Preview] Image: {obj}")
    def _preview_csv(self, obj): print(f"[Preview] CSV: {obj}")
    def _preview_excel(self, obj): print(f"[Preview] Excel: {obj}")
    def _preview_nested(self, obj): print(f"[Preview] Nested: {type(obj)}")
    def _preview_array(self, obj): print(f"[Preview] Array shape={obj.shape}")
    def _preview_dataframe(self, obj): print(f"[Preview] DataFrame {obj.shape}")

# === 示例 ===
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    dark_palette = app.palette()
    dark_palette.setColor(dark_palette.Window, QColor(45, 45, 48))
    dark_palette.setColor(dark_palette.WindowText, QColor(212, 212, 214))
    dark_palette.setColor(dark_palette.Base, QColor(30, 30, 32))
    dark_palette.setColor(dark_palette.AlternateBase, QColor(45, 45, 48))
    dark_palette.setColor(dark_palette.ToolTipBase, QColor(212, 212, 214))
    dark_palette.setColor(dark_palette.ToolTipText, QColor(212, 212, 214))
    dark_palette.setColor(dark_palette.Text, QColor(212, 212, 214))
    dark_palette.setColor(dark_palette.Button, QColor(45, 45, 48))
    dark_palette.setColor(dark_palette.ButtonText, QColor(212, 212, 214))
    dark_palette.setColor(dark_palette.BrightText, QColor(255, 255, 255))
    dark_palette.setColor(dark_palette.Highlight, QColor(70, 70, 75))
    dark_palette.setColor(dark_palette.HighlightedText, QColor(212, 212, 214))
    app.setPalette(dark_palette)

    test_data = {
        "image_path": "D:/test.png",  # 不存在会显示为普通字符串
        "csv_file": "data.csv",
        "number": 42,
        "text": "Hello " * 50,
        "nested": {"a": [1, 2, {"deep": True}]}
    }

    w = QWidget()
    layout = QVBoxLayout(w)
    tree = VariableTreeWidget()
    layout.addWidget(tree)
    w.resize(800, 600)
    w.show()
    tree.set_data(test_data, "test_var")

    sys.exit(app.exec_())