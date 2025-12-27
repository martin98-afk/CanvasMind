import os
import subprocess
import sys
from functools import lru_cache
from typing import Any, Dict, List
from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QImage, QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QHeaderView, QApplication,
    QWidget, QVBoxLayout
)
from qfluentwidgets import RoundMenu, Action, MessageBoxBase, TextEdit, ImageLabel
from spyder.plugins.variableexplorer.widgets.arrayeditor import ArrayEditor
from spyder.plugins.variableexplorer.widgets.dataframeeditor import DataFrameEditor
from spyder.plugins.variableexplorer.widgets.namespacebrowser import NamespaceBrowser

from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.dialog_widget.excel_viewer import ExcelViewer


# === 构建数据（保持不变，仅补充 Series 支持）===
MAX_NESTING_DEPTH = 5
MAX_DICT_KEYS = 100
MAX_LIST_ITEMS = 100


# === 工具函数（保持不变）===
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


def _is_pandas_series(obj):
    try:
        import pandas as pd
        return isinstance(obj, pd.Series)
    except ImportError:
        return False


def _get_formatted_type_and_value(obj, arg_type=None):
    if obj is None:
        return "(NoneType) None"

    # --- 强制处理 NumPy 标量：转成 Python 原生类型 ---
    if hasattr(obj, 'dtype') and np.isscalar(obj):
        try:
            obj = obj.item()  # np.int64(10) → 10 (Python int)
        except:
            pass  # 转不了就原样用

    # --- 现在 obj 已经是 Python 原生类型（int/float/bool/str）或普通对象 ---
    if isinstance(obj, bool):
        return f"(bool) {str(obj).lower()}"
    elif isinstance(obj, (int, float)):
        return f"({type(obj).__name__}) {obj}"
    elif isinstance(obj, str):
        if _is_image_file(obj):
            return f"(Image) '{os.path.basename(obj)}'"
        elif obj.endswith('.csv') and os.path.isfile(obj):
            return f"(CSV) '{os.path.basename(obj)}'"
        elif obj.lower().endswith(('.xlsx', '.xls')) and os.path.isfile(obj):
            return f"(Excel) '{os.path.basename(obj)}'"
        elif os.path.isfile(obj):  # ← 新增：通用文件
            return f"(File) '{os.path.basename(obj)}'"
        else:
            preview = get_simple_repr(obj, 100)
            return f"(str) '{preview}'"
    elif _is_pil_image(obj):
        return f"(PIL.Image) size={obj.size}"
    elif _is_pandas_series(obj):
        return f"(Series) len={len(obj)}, dtype={obj.dtype}"
    elif hasattr(obj, 'columns') and hasattr(obj, 'shape'):
        return f"(DataFrame) ({obj.shape[0]} x {obj.shape[1]})"
    elif isinstance(obj, dict):
        return f"(dict) len={len(obj)}"
    elif isinstance(obj, (list, tuple)):
        return f"({type(obj).__name__}) len={len(obj)}"
    elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):
        # 此时 obj 一定是真正的 array（因为标量已被转走）
        return f"(ndarray) shape={obj.shape}, dtype={obj.dtype}"
    else:
        return f"({type(obj).__name__}) {get_simple_repr(obj)}"


def build_node_data(obj: Any, name: str = "<root>", depth: int = 0) -> Dict:
    if depth > MAX_NESTING_DEPTH:
        return {
            "name": name,
            "value_preview": "... (max depth)",
            "type": "truncated",
            "has_children": False,
            "raw_obj": None
        }
    try:
        value_repr = _get_formatted_type_and_value(obj)
        has_children = False

        if _is_pandas_series(obj):
            has_children = len(obj) > 0
        elif isinstance(obj, dict):
            has_children = len(obj) > 0
        elif isinstance(obj, (list, tuple)):
            has_children = len(obj) > 0
        elif hasattr(obj, 'columns') and hasattr(obj, 'shape'):
            has_children = True
        # --- 只有非标量、非 Series、且有 shape 的才是可展开 ndarray ---
        elif (hasattr(obj, 'shape') and hasattr(obj, 'dtype')
              and not _is_pandas_series(obj)
              and not np.isscalar(obj)):
            has_children = len(obj.shape) > 0 and obj.size > 0
        else:
            has_children = False

        return {
            "name": name,
            "value_preview": value_repr,
            "type": type(obj).__name__,
            "has_children": has_children,
            "raw_obj": obj
        }
    except Exception as e:
        return {
            "name": name,
            "value_preview": f"<error: {e}>",
            "type": "error",
            "has_children": False,
            "raw_obj": None
        }


def build_children_data(parent_obj: Any, depth: int) -> List[Dict]:
    children = []
    try:
        if isinstance(parent_obj, dict):
            for k in list(parent_obj.keys())[:MAX_DICT_KEYS]:
                children.append(build_node_data(parent_obj[k], str(k), depth + 1))
        elif isinstance(parent_obj, (list, tuple)):
            for i, v in enumerate(parent_obj[:MAX_LIST_ITEMS]):
                children.append(build_node_data(v, str(i), depth + 1))
        elif _is_pandas_series(parent_obj):
            series = parent_obj
            for i in range(min(len(series), MAX_LIST_ITEMS)):
                key = str(series.index[i]) if hasattr(series, 'index') else str(i)
                # 直接取 iloc[i]，它是标量或普通对象，不会被误认为 array
                children.append(build_node_data(series.iloc[i], key, depth + 1))
        elif hasattr(parent_obj, 'columns') and hasattr(parent_obj, 'shape'):
            import pandas as pd
            df = parent_obj
            for col in list(df.columns)[:20]:
                children.append(build_node_data(df[col], str(col), depth + 1))
        # --- 处理 ndarray：支持任意维度，逐维展开 ---
        elif (hasattr(parent_obj, 'shape') and hasattr(parent_obj, 'dtype')
              and not _is_pandas_series(parent_obj)
              and not np.isscalar(parent_obj)):
            arr = parent_obj
            if arr.ndim >= 1:
                # 只展开第一维，子项会递归处理剩余维度
                for i in range(min(arr.shape[0], MAX_LIST_ITEMS)):
                    children.append(build_node_data(arr[i], f"[{i}]", depth + 1))
    except Exception as e:
        children.append({
            "name": "<error>",
            "value_preview": str(e),
            "type": "error",
            "has_children": False,
            "raw_obj": None
        })
    return children


# === 修复后的图标生成函数：确保文字在 25x25 内完整显示 ===
@lru_cache(maxsize=64)
def _create_icon(symbol: str, color: str = "#888") -> QIcon:
    # 固定 25x25，但调整字体大小和绘制位置，避免裁剪
    pixmap = QPixmap(28, 28)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(1)
    painter.setPen(pen)

    # 关键：使用更小的字体（11pt） + 精确居中
    font = QFont("Consolas", 14, QFont.Bold)
    fm = QFontMetrics(font)
    text_width = fm.horizontalAdvance(symbol)
    text_height = fm.height()

    # 居中计算（避免被裁）
    x = (25 - text_width) // 2
    y = (25 + text_height - fm.descent()) // 2  # 正确垂直对齐

    painter.setFont(font)
    painter.drawText(x, y, symbol)
    painter.end()
    return QIcon(pixmap)


def get_icon_for_type(obj):
    if obj is None:
        return _create_icon("∅", "#9E9E9E")
    elif isinstance(obj, dict):
        return _create_icon("Obj", "#4CAF50")
    elif isinstance(obj, (list, tuple)):
        return _create_icon("Lis", "#2196F3")
    elif _is_pandas_series(obj):
        return _create_icon("Ser", "#FFC107")
    elif isinstance(obj, str):
        if _is_image_file(obj):
            return _create_icon("🖼", "#FF9800")
        elif os.path.isfile(obj):  # ← 图像、CSV、Excel、通用文件都用文件图标
            return _create_icon("📄", "#9E9E9E")
        else:
            return _create_icon('Str', "#FF9800")
    elif isinstance(obj, bool):
        return _create_icon("✓", "#4CAF50")
    elif isinstance(obj, (int, float)):
        return _create_icon("123", "#9C27B0")
    elif _is_pil_image(obj):
        return _create_icon("🖼", "#FF5722")
    elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):
        return _create_icon("Arr", "#795548")
    elif hasattr(obj, 'columns') and hasattr(obj, 'shape'):
        return _create_icon("DF", "#E91E63")
    else:
        return _create_icon("?", "#607D8B")


# === 核心控件（完全保持你原始设置，不加滚动、不改列宽）===
class VariableTreeWidget(QTreeWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.parent_widget = parent
        self.setHeaderLabels(["Name", "Value"])
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setAnimated(False)
        self.setIndentation(12)
        self.setExpandsOnDoubleClick(True)
        # 注意：以下两行完全按你最初代码，不启用横向滚动，不设最小宽度
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        self.itemExpanded.connect(self.on_item_expanded)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

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
        menu = RoundMenu(parent=self)

        # 文件操作
        if isinstance(obj, str) and os.path.isfile(obj):
            menu.addAction(Action("📂 在资源管理器中打开", triggered=lambda: self._open_file_in_explorer(obj)))
            if _is_image_file(obj):
                menu.addAction(Action("🖼️ 预览图像", triggered=lambda: self._preview_image(obj)))
            elif obj.endswith('.csv'):
                menu.addAction(Action("📊 预览 CSV", triggered=lambda: self._preview_csv_full(obj)))
            elif obj.lower().endswith(('.xlsx', '.xls')):
                menu.addAction(Action("📊 预览 Excel", triggered=lambda: self._preview_excel(obj)))
            else:
                # 通用文件：也可以预览文本（如果可读）
                menu.addAction(Action("🔍 预览文本", triggered=lambda: self._preview_text_file(obj)))

        # ← 新增：普通字符串（非文件）也能预览
        elif isinstance(obj, str):
            menu.addAction(Action("🔍 预览文本", triggered=lambda: self._preview_text(obj)))

        # 数据结构预览
        if isinstance(obj, (list, tuple, dict)):
            menu.addAction(Action("🔍 预览结构", triggered=lambda: self._preview_nested(obj)))
        elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):
            menu.addAction(Action("🔍 预览数组", triggered=lambda: self._preview_array(obj)))
        elif hasattr(obj, 'columns') and hasattr(obj, 'shape'):
            menu.addAction(
                Action("🔍 预览 DataFrame", triggered=lambda: self._preview_dataframe_full(obj, title="数据表")))
        elif _is_pandas_series(obj):
            menu.addAction(Action("🔍 预览 Series", triggered=lambda: self._preview_series(obj)))

        menu.addAction(Action("📋 复制值", triggered=lambda: self._copy_value(str(obj))))
        menu.exec_(self.viewport().mapToGlobal(pos))

    def _copy_value(self, text):
        QApplication.clipboard().setText(text)

    def _open_file_in_explorer(self, filepath):
        if not os.path.isfile(filepath):
            return
        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", filepath], check=False)
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", filepath], check=False)
            else:
                subprocess.run(["xdg-open", os.path.dirname(filepath)], check=False)
        except:
            pass

    # === 预览方法（保持不变）===
    def _preview_text_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read(10000)  # 限制大小
            self._preview_text(content)
        except Exception as e:
            try:
                # 尝试二进制或其它编码
                with open(filepath, 'r', encoding='gbk') as f:
                    content = f.read(10000)
                self._preview_text(content)
            except:
                self._preview_text(f"[无法预览文件内容]\n{str(e)}")

    def _preview_dataframe_full(self, df, title="csv表格"):
        editor = DataFrameEditor(parent=self.parent_widget, namespacebrowser=NamespaceBrowser(self), readonly=True)
        StyleSheet.VARIABLE_EXPLORER.apply(editor)
        if editor.setup_and_check(df, title=title):
            editor.exec_()
            return editor.get_value()

    def _preview_csv_full(self, filepath):
        try:
            import pandas as pd
            df = pd.read_csv(filepath)
            self._preview_dataframe_full(df)
        except Exception as e:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(title="CSV 加载失败", content=str(e), parent=self, duration=3000)

    def _preview_excel(self, filepath):
        try:
            viewer = ExcelViewer(self)
            if viewer.setup_and_check(filepath):
                viewer.show()
        except Exception as e:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(title="Excel 加载失败", content=str(e), parent=self, duration=3000)

    def _preview_series(self, series):
        try:
            import pandas as pd
            df = series.to_frame()
            self._preview_dataframe_full(df, title="Series")
        except:
            self._preview_text(str(series))

    def _preview_text(self, text):
        w = MessageBoxBase(parent=self.parent_widget)
        w.yesButton.hide()
        w.cancelButton.setText("关闭")
        edit = TextEdit()
        edit.setPlainText(text)
        edit.setReadOnly(True)
        edit.setMinimumSize(700, 500)
        w.viewLayout.addWidget(edit)
        w.exec_()

    def _preview_array(self, array, title="数组预览"):
        editor = ArrayEditor(self.parent_widget)
        StyleSheet.VARIABLE_EXPLORER.apply(editor)
        if editor.setup_and_check(array, title=title):
            editor.exec_()
            return editor.get_value()

    def _preview_image(self, image_data):
        pixmap = None
        if isinstance(image_data, str) and os.path.isfile(image_data):
            pixmap = QPixmap(image_data)
        elif _is_pil_image(image_data):
            try:
                from PIL import Image
                if image_data.mode not in ('RGB', 'RGBA'):
                    image_data = image_data.convert('RGBA' if image_data.mode == 'P' else 'RGB')
                data = image_data.tobytes('raw', image_data.mode)
                fmt = QImage.Format_RGBA8888 if image_data.mode == 'RGBA' else QImage.Format_RGB8888
                qimg = QImage(data, *image_data.size, fmt)
                pixmap = QPixmap.fromImage(qimg)
            except Exception as e:
                print(f"PIL 转换失败: {e}")
        if pixmap is None or pixmap.isNull():
            return
        if pixmap.width() > 700 or pixmap.height() > 700:
            pixmap = pixmap.scaled(700, 700, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        w = MessageBoxBase(parent=self.parent_widget)
        w.yesButton.hide()
        w.cancelButton.setText("关闭")
        label = ImageLabel()
        label.setImage(pixmap)
        w.viewLayout.addWidget(label)
        w.exec_()

    def _preview_nested(self, obj):
        self._preview_text(str(obj))  # 或用嵌套树（可后续扩展）


# === 示例（保持不变）===
if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    test_data = {
        "img": "D:/test.png",
        "csv": "data.csv",
        "arr": [1, 2, {"a": 3}],
        "text": "Hello" * 20,
    }

    w = QWidget()
    layout = QVBoxLayout(w)
    tree = VariableTreeWidget(parent=w)
    layout.addWidget(tree)
    w.resize(800, 600)
    w.show()
    tree.set_data(test_data, "test_var")
    sys.exit(app.exec_())