# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import numpy as np
import pandas as pd
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QFont
from PyQt5.QtWidgets import (
    QTreeWidgetItem, QAction, QApplication, QTableWidget, QTableWidgetItem, QHeaderView
)
from qfluentwidgets import TreeWidget, RoundMenu, MessageBoxBase, TextEdit, SegmentedWidget, TableWidget, ImageLabel
from qtpy import QtCore
from spyder.plugins.variableexplorer.widgets.arrayeditor import ArrayEditor
from spyder.plugins.variableexplorer.widgets.dataframeeditor import DataFrameEditor
from spyder.plugins.variableexplorer.widgets.namespacebrowser import NamespaceBrowser
from app.components.base import ArgumentType
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.dialog_widget.excel_viewer import ExcelViewer


STR_MAX_SHOW_LENGTH = 400


def _resolve_json_content(obj, arg_type):
    """
    根据 arg_type 解析 JSON 内容。
    如果 arg_type 是 JSON 且 obj 是字符串，则尝试解析它。
    否则，返回原始 obj。
    """
    if arg_type == ArgumentType.JSON and isinstance(obj, str):
        try:
            return json.loads(obj)
        except (json.JSONDecodeError, TypeError):
            # 解析失败，返回原始字符串
            pass
    return obj


def _get_formatted_type_and_value(obj, arg_type=None):
    """
    根据 obj 的实际类型和可选的 arg_type，返回格式化的类型和值字符串。
    这个函数统一了 _format_value 的逻辑。
    """
    if obj is None:
        return "(NoneType) None"

    # 优先使用 arg_type
    if arg_type is not None and isinstance(arg_type, ArgumentType):
        if arg_type.is_image():
            if isinstance(obj, str) and os.path.isfile(obj):
                return f"(Image) '{os.path.basename(obj)}'"
            elif _is_pil_image(obj):
                return f"(PIL.Image) size={obj.size}"
            else:
                return "(Image) <invalid>"
        elif arg_type == ArgumentType.CSV:
            if isinstance(obj, str) and os.path.isfile(obj):
                return f"(CSV) '{os.path.basename(obj)}'"
            elif isinstance(obj, pd.DataFrame):
                return f"(DataFrame) ({obj.shape[0]} x {obj.shape[1]})"
        elif arg_type == ArgumentType.EXCEL:
            if isinstance(obj, str) and os.path.isfile(obj):
                return f"(Excel) '{os.path.basename(obj)}'"
            elif isinstance(obj, pd.DataFrame):
                return f"(DataFrame) ({obj.shape[0]} x {obj.shape[1]})"
        elif arg_type == ArgumentType.JSON:
            # 首先尝试解析 JSON
            parsed_obj = _resolve_json_content(obj, arg_type)
            if isinstance(parsed_obj, (dict, list, tuple, set)):
                length = len(parsed_obj) if hasattr(parsed_obj, '__len__') else '?'
                type_name = type(parsed_obj).__name__
                return f"(JSON/{type_name}) (len={length})"
            elif isinstance(parsed_obj, (str, bytes)):
                # 如果解析后仍是字符串或 bytes，说明原字符串不是 JSON，或者解析后是字符串
                # 但原 obj 是字符串，尝试解析失败，所以显示为 JSON 字符串
                # 或者原 obj 不是字符串，直接显示为 JSON
                if isinstance(obj, (str, bytes)):
                    # 原始 obj 是字符串，但解析失败 -> JSON 字符串
                    return f"(JSON) {get_simple_repr(obj)}"
                else:
                    # 原始 obj 不是字符串 -> 作为 JSON 的通用格式化
                    return f"(JSON) {get_simple_repr(obj)}"
            else:
                # 解析后是其他类型，按 JSON 规则格式化
                return f"(JSON) {get_simple_repr(parsed_obj)}"
        elif arg_type == ArgumentType.FILE:
            if isinstance(obj, str) and os.path.isfile(obj):
                return f"(File) '{os.path.basename(obj)}'"
            else:
                return f"(File) {str(obj)}"
        elif arg_type in (ArgumentType.SKLEARNMODEL, ArgumentType.TORCHMODEL):
            return f"(Model: {arg_type.value})"
        elif arg_type.is_array():
            if isinstance(obj, np.ndarray):
                shape_str = str(obj.shape).replace(" ", "")
                return f"(Array/ndarray) {shape_str}"
            elif isinstance(obj, (list, tuple)):
                return f"(Array/list) len={len(obj)}"
            else:
                return f"(Array) {str(obj)}"
        elif arg_type.is_bool():
            return f"(bool) {str(bool(obj)).lower()}"
        elif arg_type.is_number():
            try:
                val = float(obj)
                if arg_type == ArgumentType.INT:
                    return f"(int) {int(val)}"
                else:
                    return f"(float) {val}"
            except (TypeError, ValueError):
                return f"(Number) {str(obj)}"
        elif arg_type == ArgumentType.TEXT:
            if isinstance(obj, str):
                if len(obj) <= STR_MAX_SHOW_LENGTH:
                    return f"(str) '{obj}'"
                else:
                    return f"(str) '{obj[:STR_MAX_SHOW_LENGTH]}...‘"
            else:
                return f"(str) '{str(obj)}'"

    # 如果没有指定 arg_type，根据对象的实际类型进行推断
    if isinstance(obj, bool):
        return f"(bool) {str(obj).lower()}"
    elif isinstance(obj, str):
        if os.path.isfile(obj):
            ext = os.path.splitext(obj)[1].lower()
            if ext in {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}:
                return f"(Image) '{os.path.basename(obj)}'"
            elif ext in {'.csv', '.xlsx', '.xls'}:
                return f"(File) '{os.path.basename(obj)}'"
            elif ext in {'.txt', '.log', '.md', '.py', '.json'}:
                return f"(Text) '{os.path.basename(obj)}'"
            else:
                return f"(File) '{os.path.basename(obj)}'"
        else:
            if len(obj) <= STR_MAX_SHOW_LENGTH:
                return f"(str) '{obj}'"
            else:
                return f"(str) '{obj[:STR_MAX_SHOW_LENGTH]}...'"
    elif isinstance(obj, (int, float)):
        return f"({type(obj).__name__}) {obj}"
    elif isinstance(obj, np.number):
        return f"({type(obj).__name__}) {obj}"
    elif isinstance(obj, np.ndarray):
        shape_str = str(obj.shape).replace(" ", "")
        return f"(ndarray) {shape_str}"
    elif isinstance(obj, pd.DataFrame):
        return f"(DataFrame) ({obj.shape[0]} x {obj.shape[1]})"
    elif isinstance(obj, pd.Series):
        return f"(Series) len={len(obj)}"
    elif isinstance(obj, dict):
        return f"(dict) len={len(obj)}"
    elif isinstance(obj, list):
        return f"(list) len={len(obj)}"
    elif isinstance(obj, tuple):
        return f"(tuple) len={len(obj)}"
    elif isinstance(obj, set):
        return f"(set) len={len(obj)}"
    elif _is_image_file(obj):
        return f"(Image) '{os.path.basename(str(obj))}'"
    elif _is_pil_image(obj):
        return f"(PIL.Image) size={obj.size}"
    elif hasattr(obj, '__class__'):
        cls = obj.__class__
        mod = cls.__module__
        name = cls.__name__
        if mod == 'builtins':
            return f"({name}) {obj}"
        else:
            return f"({mod}.{name}) {obj}"
    else:
        return f"({type(obj).__name__}) {str(obj)}"


def get_simple_repr(obj, max_len=STR_MAX_SHOW_LENGTH):
    """获取对象的简单字符串表示，用于格式化输出，避免过长."""
    s = str(obj)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


def _is_image_file(obj):
    if isinstance(obj, str) and os.path.isfile(obj):
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
        return os.path.splitext(obj.lower())[1] in image_extensions
    return False


def _is_pil_image(obj):
    try:
        from PIL import Image
        return isinstance(obj, Image.Image)
    except ImportError:
        return False


class BuildTreeWorker(QThread):
    """
    后台线程工作类，用于构建树形结构数据
    """
    finished = pyqtSignal(object)  # 信号，传递构建好的根节点列表
    error = pyqtSignal(str)  # 信号，传递错误信息

    def __init__(self, data, arg_type, max_depth, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.data = data
        self.arg_type = arg_type
        self.max_depth = max_depth

    def run(self):
        try:
            root_items = []
            self._build_items(self.data, "", self.max_depth, 0, self.arg_type, root_items)
            self.finished.emit(root_items)
        except Exception as e:
            import traceback
            full_error_msg = f"{type(e).__name__}: {str(e)}\nTraceback:\n{traceback.format_exc()}"
            self.error.emit(full_error_msg)

    def _build_items(self, obj, key, max_depth, current_depth, arg_type, parent_list):
        """构建单个树形项，并递归处理其子项"""
        current_depth += 1
        if current_depth > max_depth:
            trunc_item_data = {
                "text": ["<max recursion depth>"],
                "data": None,
                "children": [],
                "icon": None
            }
            parent_list.append(trunc_item_data)
            return

        # 1. 解析内容 (如果需要)
        actual_obj = _resolve_json_content(obj, arg_type)
        # 2. 格式化显示文本
        formatted_value = _get_formatted_type_and_value(actual_obj, arg_type)

        item_data = {
            "text": [f"{key}: {formatted_value}"],
            "data": obj,  # 保存原始数据
            "children": [],
            "icon": self.parent._get_icon_for_item(actual_obj) # 使用解析后的对象获取图标
        }

        # 3. 递归构建子节点 (基于解析后的 actual_obj)
        self._build_recursive_content_items(actual_obj, max_depth, current_depth, arg_type, item_data["children"])

        parent_list.append(item_data)

    def _build_recursive_content_items(self, obj, max_depth, current_depth, arg_type, children_list):
        """递归构建内容项，现在逻辑与 _format_value 同步"""
        current_depth += 1
        if current_depth > max_depth:
            return

        # 重要：对于子项，arg_type 应该是 None 或基于子项自身的类型推断
        # 因为 arg_type 主要影响当前层级 obj 的处理方式。
        # 例如，一个 JSON 字符串解析后是一个 dict，其子项（键值对）应按其自身类型处理，而非 JSON。
        sub_arg_type = None

        if isinstance(obj, dict):
            for k, v in obj.items():
                self._build_items(v, str(k), max_depth, current_depth, sub_arg_type, children_list)
                if children_list:
                    last_added_item_data = children_list[-1]
                    last_added_item_data['is_dict_item'] = True
                    last_added_item_data['dict_key'] = str(k)
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                self._build_items(v, str(i), max_depth, current_depth, sub_arg_type, children_list)
        elif isinstance(obj, set):
            for i, v in enumerate(obj):
                self._build_items(v, f"[{i}]", max_depth, current_depth, sub_arg_type, children_list)
        elif isinstance(obj, np.ndarray):
            attrs = {
                'shape': obj.shape,
                'dtype': str(obj.dtype),
                'size': obj.size,
                'ndim': obj.ndim,
            }
            for attr_name, attr_val in attrs.items():
                attr_children = []
                # 属性值也按其自身类型处理
                self._build_recursive_content_items(attr_val, max_depth, current_depth, sub_arg_type, attr_children)
                attr_item_data = {
                    "text": [f"{attr_name}", _get_formatted_type_and_value(attr_val)],
                    "data": attr_val,
                    "children": attr_children,
                    "icon": None
                }
                children_list.append(attr_item_data)

            MAX_PER_DIM = 300
            if obj.ndim == 1:
                slice_obj = slice(0, min(obj.shape[0], MAX_PER_DIM))
                for i in range(slice_obj.start, min(slice_obj.stop, obj.shape[0])):
                    self._build_items(obj[i], f"[{i}]", max_depth, current_depth, sub_arg_type, children_list)
                if obj.shape[0] > MAX_PER_DIM:
                    trunc_item_data = {
                        "text": [f"... ({obj.shape[0] - MAX_PER_DIM} more items truncated ...)"],
                        "data": None,
                        "children": [],
                        "icon": None
                    }
                    children_list.append(trunc_item_data)
            elif obj.ndim == 2:
                max_rows = min(obj.shape[0], MAX_PER_DIM)
                max_cols = min(obj.shape[1], MAX_PER_DIM)
                for i in range(max_rows):
                    row_children = []
                    for j in range(max_cols):
                        self._build_items(obj[i, j], str(j), max_depth, current_depth, sub_arg_type, row_children)
                    if obj.shape[1] > MAX_PER_DIM:
                        trunc_col_item_data = {
                            "text": [f"... ({obj.shape[1] - MAX_PER_DIM} more items truncated ...)"],
                            "data": None,
                            "children": [],
                            "icon": None
                        }
                        row_children.append(trunc_col_item_data)
                    row_item_data = {
                        "text": [f"[{i}]"],
                        "data": obj[i],
                        "children": row_children,
                        "icon": None
                    }
                    children_list.append(row_item_data)
                if obj.shape[0] > MAX_PER_DIM:
                    trunc_row_item_data = {
                        "text": [f"... ({obj.shape[0] - MAX_PER_DIM} more rows truncated ...)"],
                        "data": None,
                        "children": [],
                        "icon": None
                    }
                    children_list.append(trunc_row_item_data)
            elif obj.ndim > 2:
                max_first_dim = min(obj.shape[0], MAX_PER_DIM)
                for i in range(max_first_dim):
                    sub_obj = obj[i]
                    sub_children = []
                    self._build_recursive_content_items(sub_obj, max_depth, current_depth, sub_arg_type, sub_children)
                    sub_item_data = {
                        "text": [f"[{i}]"],
                        "data": sub_obj,
                        "children": sub_children,
                        "icon": None
                    }
                    children_list.append(sub_item_data)
                if obj.shape[0] > MAX_PER_DIM:
                    trunc_high_dim_item_data = {
                        "text": [f"... ({obj.shape[0] - MAX_PER_DIM} more items in first dimension truncated ...)"],
                        "data": None,
                        "children": [],
                        "icon": None
                    }
                    children_list.append(trunc_high_dim_item_data)
        elif isinstance(obj, pd.DataFrame):
            for col in obj.columns[:20]:
                self._build_items(obj[col], str(col), max_depth, current_depth, sub_arg_type, children_list)
                if children_list:
                    last_added_item_data = children_list[-1]
                    last_added_item_data['is_dict_item'] = True
                    last_added_item_data['dict_key'] = str(col)
        elif isinstance(obj, pd.Series):
            for idx in obj.index[:20]:
                self._build_items(obj[idx], str(idx), max_depth, current_depth, sub_arg_type, children_list)
                if children_list:
                    last_added_item_data = children_list[-1]
                    last_added_item_data['is_dict_item'] = True
                    last_added_item_data['dict_key'] = str(idx)
        elif hasattr(obj, '__dict__') and obj.__dict__:
            for attr_name, attr_value in obj.__dict__.items():
                if not attr_name.startswith('_'):
                    self._build_items(attr_value, attr_name, max_depth, current_depth, sub_arg_type, children_list)
                    if children_list:
                        last_added_item_data = children_list[-1]
                        last_added_item_data['is_dict_item'] = True
                        last_added_item_data['dict_key'] = str(attr_name)
        else:
            # 非容器类型，直接添加
            pass


class VariableTreeWidget(TreeWidget):
    """用于展示单个变量的详细树状结构"""
    def  __init__(self, data=None, port_type=None, max_depth=5, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.setHeaderHidden(True)
        self.setEditTriggers(self.NoEditTriggers)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(False)
        self.setFixedHeight(150)
        self.setStyleSheet("""
            TreeWidget {
                background-color: transparent; /* 设置背景为透明 */
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                show-decoration-selected: 1;
            }
            QTreeView::item {
                padding: 1px 0 1px 5px; /* 上 右 下 左 边距，增加左边距为展开箭头和图标留空间 */
                border: none;
            }
            QTreeView::item:hover {
                background-color: rgba(200, 200, 200, 50);
            }
            /* 可选：调整展开箭头的大小 */
            QTreeView::branch {
                icon-size: 14px; /* 调整展开箭头大小 */
            }
            /* 可选：调整图标与文本的间距 */
            QTreeView::item {
                icon-spacing: 1px; /* 图标与文本之间的间距 */
            }
        """)
        self._original_data = None
        self._arg_type = None
        self._current_worker = None
        if data is not None:
            self.set_data(data, arg_type=port_type, max_depth=max_depth)

    def set_data(self, data, arg_type=None, max_depth=5):
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.quit()
            self._current_worker.wait()
        self._original_data = data
        self._arg_type = arg_type
        self.clear()
        self._current_worker = BuildTreeWorker(data, arg_type, max_depth, parent=self)
        self._current_worker.finished.connect(self._on_build_finished)
        self._current_worker.error.connect(self._on_build_error)
        self._current_worker.start()

    def _on_build_finished(self, root_items_data):
        self.clear()
        for item_data in root_items_data:
            self._add_item_from_data(self.invisibleRootItem(), item_data)
        if self.topLevelItemCount() > 0:
            top_item = self.topLevelItem(0)
            if top_item.childCount() > 0:
                self.expandItem(top_item)

    def _on_build_error(self, error_message):
        print(f"构建树形结构时出错: {error_message}")
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.error(
            title="数据结构解析失败",
            content=f"解析变量时出错: {type(self._original_data).__name__}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
            parent=self
        )
        error_item = QTreeWidgetItem(self.invisibleRootItem(), [f"Error: {type(self._original_data).__name__}"])
        error_item.setForeground(0, Qt.red)

    def _add_item_from_data(self, parent_item, item_data):
        item = QTreeWidgetItem(parent_item, item_data["text"])
        if item_data["data"] is not None:
            item.setData(0, Qt.UserRole, item_data["data"])
        if 'is_dict_item' in item_data:
            item.setData(0, Qt.UserRole + 1, item_data['is_dict_item'])
            item.setData(0, Qt.UserRole + 2, item_data['dict_key'])
        icon = self._get_icon_for_item(item_data["data"])
        if icon:
            item.setIcon(0, icon)
        for child_data in item_data["children"]:
            self._add_item_from_data(item, child_data)

    def _get_icon_for_item(self, obj):
        from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
        if obj is None:
            return None
        pixmap = QPixmap(25, 25)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 165, 0))
        font = QFont('Arial', 12)
        font.setBold(True)
        painter.setFont(font)

        if isinstance(obj, dict):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "{...}")
        elif isinstance(obj, (list, tuple)):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "[...]")
        elif isinstance(obj, set):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "{...}")
        elif isinstance(obj, np.ndarray):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "[...]")
        elif isinstance(obj, pd.DataFrame):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "DF")
        elif isinstance(obj, pd.Series):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "S")
        elif isinstance(obj, str) and os.path.isfile(obj):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "📄")
        elif isinstance(obj, str):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "\"...\"")
        elif isinstance(obj, (int, float, bool, np.int8, np.int32, np.int64, np.float32, np.float64)):
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "123")
        elif hasattr(obj, '__class__'):
            cls = obj.__class__
            mod = cls.__module__
            if mod == 'builtins':
                painter.drawText(pixmap.rect(), Qt.AlignCenter, "C")
            else:
                painter.drawText(pixmap.rect(), Qt.AlignCenter, "M")
        else:
            return None
        painter.end()
        return QIcon(pixmap)

    # --- 其他方法保持不变 ---
    def show_detail(self):
        obj = self._original_data
        has_file_preview = False
        if isinstance(obj, str) and not os.path.isfile(obj):
            self._preview_text(obj)
        elif isinstance(obj, str) and os.path.isfile(obj):
            filepath = obj
            ext = os.path.splitext(filepath.lower())[1]
            if ext in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp'}:
                self._preview_image(filepath)
                has_file_preview = True
            elif ext == '.csv':
                self._preview_csv_full(filepath)
                has_file_preview = True
            elif ext in {'.xlsx', '.xls'}:
                self._preview_excel(filepath)
                has_file_preview = True
            elif ext in {'.txt', '.log', '.md', '.py', '.json', '.xml', '.yaml', '.yml', '.ini'}:
                self._preview_text_file(filepath)
                has_file_preview = True
            else:
                self._open_file_in_explorer(filepath)
        elif isinstance(obj, list):
            try:
                obj = np.array(obj)
                self._preview_array(obj, f"NumPy 数组 (shape: {obj.shape}, dtype: {obj.dtype}) 预览")
            except Exception as e:
                self._preview_nested_structure(obj, f"列表数据 (len: {len(obj)})预览")
        elif isinstance(obj, tuple):
            self._preview_nested_structure(obj, f"元组数据 (len: {len(obj)}) 预览")
        elif isinstance(obj, dict):
            self._preview_nested_structure(obj, "字典数据预览")
        elif isinstance(obj, set):
            self._preview_array(obj, "集合数据预览") # Note: 用array viewer显示set可能不理想
        elif isinstance(obj, np.ndarray):
            self._preview_array(obj,f"NumPy 数组 (shape: {obj.shape}, dtype: {obj.dtype}) 预览")
        elif isinstance(obj, pd.DataFrame):
            self._preview_dataframe_full(obj)
        elif isinstance(obj, pd.Series):
            obj = obj.to_frame()
            self._preview_dataframe_full(obj)
        elif _is_pil_image(obj):
            self._preview_image(obj)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if not item:
            return
        obj = item.data(0, Qt.UserRole)
        if obj is None:
            return

        menu = RoundMenu(parent=self)
        is_dict_item = item.data(0, Qt.UserRole + 1)
        dict_key = item.data(0, Qt.UserRole + 2)

        open_in_explorer_action = None
        if isinstance(obj, str) and os.path.isfile(obj):
            filepath = obj
            open_in_explorer_action = QAction("📂 在资源管理器中打开", self)
            open_in_explorer_action.triggered.connect(lambda: self._open_file_in_explorer(filepath))
            menu.addAction(open_in_explorer_action)

        if isinstance(obj, str) and not os.path.isfile(obj):
            action = QAction("🔍 预览完整文本", self)
            action.triggered.connect(lambda: self._preview_text(obj))
            menu.addAction(action)
        elif isinstance(obj, str) and os.path.isfile(obj):
            filepath = obj
            ext = os.path.splitext(filepath.lower())[1]
            if ext in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp'}:
                action = QAction("🖼️ 预览原图", self)
                action.triggered.connect(lambda: self._preview_image(filepath))
                menu.addAction(action)
            elif ext == '.csv':
                preview_full = QAction("🔍 预览完整数据", self)
                preview_full.triggered.connect(lambda: self._preview_csv_full(filepath))
                menu.addAction(preview_full)
            elif ext in {'.xlsx', '.xls'}:
                preview_limited = QAction("📊 预览所有工作表", self)
                preview_limited.triggered.connect(lambda: self._preview_excel(filepath))
                menu.addAction(preview_limited)
            elif ext in {'.txt', '.log', '.md', '.py', '.json', '.xml', '.yaml', '.yml', '.ini'}:
                action = QAction("🔍 预览文本内容", self)
                action.triggered.connect(lambda: self._preview_text_file(filepath))
                menu.addAction(action)
        elif isinstance(obj, (list, tuple)):
            action = QAction("🔍 预览完整列表", self)
            action.triggered.connect(
                lambda: self._preview_nested_structure(obj, f"{'列表' if isinstance(obj, list) else '元组'}数据预览"))
            menu.addAction(action)
        elif isinstance(obj, dict):
            action = QAction("🔍 预览完整字典", self)
            action.triggered.connect(lambda: self._preview_nested_structure(obj, "字典数据预览"))
            menu.addAction(action)
        elif isinstance(obj, set):
            action = QAction("🔍 预览完整集合", self)
            action.triggered.connect(lambda: self._preview_nested_structure(obj, "集合数据预览"))
            menu.addAction(action)
        elif isinstance(obj, np.ndarray):
            action = QAction("🔍 预览数组内容", self)
            action.triggered.connect(lambda: self._preview_array(obj,f"NumPy 数组 (shape: {obj.shape}, dtype: {obj.dtype}) 预览"))
            menu.addAction(action)
        elif isinstance(obj, pd.DataFrame):
            action = QAction("🔍 预览完整数据表", self)
            action.triggered.connect(lambda: self._preview_dataframe_full(obj))
            menu.addAction(action)
        elif isinstance(obj, pd.Series):
            obj = obj.to_frame()
            action = QAction("🔍 预览完整数据表", self)
            action.triggered.connect(lambda: self._preview_dataframe_full(obj))
            menu.addAction(action)
        elif _is_pil_image(obj):
            action = QAction("🖼️ 预览原图", self)
            action.triggered.connect(lambda: self._preview_image(obj))
            menu.addAction(action)

        if is_dict_item and dict_key:
            copy_key_action = QAction("📋 复制字典键", self)
            copy_key_action.triggered.connect(lambda: self._copy_value(dict_key))
            menu.addAction(copy_key_action)

        copy_action = QAction("📋 复制值", self)
        copy_action.triggered.connect(lambda: self._copy_value(str(obj)))
        menu.addAction(copy_action)

        menu.exec_(event.globalPos())

    def _preview_nested_structure(self, data, title="嵌套结构预览"):
        dialog = MessageBoxBase(parent=self.parent_widget)
        dialog.yesButton.hide()
        dialog.cancelButton.setText("关闭")
        tree_widget = TreeWidget()
        tree_widget.setHeaderLabels(["Key", "Value"])
        tree_widget.setAlternatingRowColors(False)
        tree_widget.setSortingEnabled(False)
        tree_widget.setMinimumSize(800, 500)
        tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # Use the same logic as the main widget for consistency
        self._build_nested_tree(data, tree_widget.invisibleRootItem(), "", is_root=True)
        tree_widget.expandAll()
        dialog.viewLayout.addWidget(tree_widget)
        dialog.exec_()

    def _build_nested_tree(self, obj, parent_item, key, is_root=False, max_depth=10, current_depth=0):
        if current_depth > max_depth:
            item = QTreeWidgetItem(parent_item, ["<max recursion depth>", ""])
            item.setForeground(0, Qt.gray)
            return

        display_key = key if not is_root else "root"
        # Use the unified formatting function
        display_value = _get_formatted_type_and_value(obj)
        item = QTreeWidgetItem(parent_item, [display_key, display_value])

        if obj is not None:
            item.setData(0, Qt.UserRole, obj)

        # Use the same recursive logic, but adapted for two-column tree
        self._build_recursive_content_nested(obj, item, max_depth, current_depth)

    def _build_recursive_content_nested(self, obj, parent_item, max_depth, current_depth):
        current_depth += 1
        if current_depth > max_depth:
            return

        sub_arg_type = None

        if isinstance(obj, dict):
            for k, v in obj.items():
                self._build_nested_tree(v, parent_item, str(k), max_depth=max_depth, current_depth=current_depth)
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                self._build_nested_tree(v, parent_item, str(i), max_depth=max_depth, current_depth=current_depth)
        elif isinstance(obj, set):
            for i, v in enumerate(obj):
                self._build_nested_tree(v, parent_item, f"[{i}]", max_depth=max_depth, current_depth=current_depth)
        elif isinstance(obj, np.ndarray):
            attrs = {
                'shape': obj.shape,
                'dtype': str(obj.dtype),
                'size': obj.size,
                'ndim': obj.ndim,
            }
            for attr_name, attr_val in attrs.items():
                attr_item = QTreeWidgetItem(parent_item, [f"{attr_name}", _get_formatted_type_and_value(attr_val)])
                self._build_recursive_content_nested(attr_val, attr_item, max_depth, current_depth)

            MAX_PER_DIM = 300
            if obj.ndim == 1:
                max_items = min(obj.shape[0], MAX_PER_DIM)
                for i in range(max_items):
                    self._build_nested_tree(obj[i], parent_item, f"[{i}]", max_depth, current_depth)
                if obj.shape[0] > MAX_PER_DIM:
                    trunc_item = QTreeWidgetItem(parent_item,
                                                 [f"... ({obj.shape[0] - MAX_PER_DIM} more items truncated ...)", ""])
                    trunc_item.setForeground(0, Qt.gray)
            elif obj.ndim == 2:
                max_rows = min(obj.shape[0], MAX_PER_DIM)
                max_cols = min(obj.shape[1], MAX_PER_DIM)
                for i in range(max_rows):
                    row_item = QTreeWidgetItem(parent_item, [f"[{i}]", ""])
                    for j in range(max_cols):
                        self._build_nested_tree(obj[i, j], row_item, str(j), max_depth, current_depth)
                    if obj.shape[1] > MAX_PER_DIM:
                        trunc_col_item = QTreeWidgetItem(row_item,
                                                         [f"... ({obj.shape[1] - MAX_PER_DIM} more items truncated ...)",
                                                          ""])
                        trunc_col_item.setForeground(0, Qt.gray)
                if obj.shape[0] > MAX_PER_DIM:
                    trunc_row_item = QTreeWidgetItem(parent_item,
                                                     [f"... ({obj.shape[0] - MAX_PER_DIM} more rows truncated ...)",
                                                      ""])
                    trunc_row_item.setForeground(0, Qt.gray)
            elif obj.ndim > 2:
                max_first_dim = min(obj.shape[0], MAX_PER_DIM)
                for i in range(max_first_dim):
                    sub_obj = obj[i]
                    sub_item = QTreeWidgetItem(parent_item, [f"[{i}]", f"ndarray{obj.shape[1:]}"])
                    self._build_recursive_content_nested(sub_obj, sub_item, max_depth, current_depth)
                if obj.shape[0] > MAX_PER_DIM:
                    trunc_high_dim_item = QTreeWidgetItem(parent_item,
                                                          [f"... ({obj.shape[0] - MAX_PER_DIM} more items in first dimension truncated ...)",
                                                           ""])
                    trunc_high_dim_item.setForeground(0, Qt.gray)
        elif isinstance(obj, pd.DataFrame):
            for col in obj.columns:
                self._build_nested_tree(obj[col], parent_item, str(col), max_depth, current_depth)
        elif isinstance(obj, pd.Series):
            for idx in obj.index[:20]:
                self._build_nested_tree(obj[idx], parent_item, str(idx), max_depth, current_depth)
        elif hasattr(obj, '__dict__') and obj.__dict__:
            for attr_name, attr_value in obj.__dict__.items():
                if not attr_name.startswith('_'):
                    self._build_nested_tree(attr_value, parent_item, attr_name, max_depth, current_depth)
        elif hasattr(obj, '__slots__'):
            for slot in getattr(obj, '__slots__', []):
                if hasattr(obj, slot):
                    attr_value = getattr(obj, slot)
                    if not slot.startswith('_'):
                        self._build_nested_tree(attr_value, parent_item, slot, max_depth, current_depth)

    def _preview_dataframe_full(self, df: pd.DataFrame, title: str= "csv表格"):
        editor = DataFrameEditor(
            parent=self.parent_widget,
            namespacebrowser=NamespaceBrowser(self),
            readonly=True
        )
        StyleSheet.VARIABLE_EXPLORER.apply(editor)
        if editor.setup_and_check(df, title=title):
            editor.exec_()
            return editor.get_value()

    def _preview_csv_full(self, filepath):
        try:
            df = pd.read_csv(filepath)
            self._preview_dataframe_full(df)
        except Exception as e:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(
                title="CSV 完整加载失败",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )

    def _preview_excel(self, filepath):
        try:
            viewer = ExcelViewer(self)
            if viewer.setup_and_check(filepath):
                viewer.show()
        except Exception as e:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(
                title="Excel 加载失败",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )

    def _preview_text(self, text):
        w = MessageBoxBase(parent=self.parent_widget)
        w.yesButton.hide()
        w.cancelButton.setText("关闭")
        text_edit = TextEdit()
        text_edit.setPlainText(text)
        text_edit.setReadOnly(True)
        text_edit.setMinimumSize(700, 500)
        w.viewLayout.addWidget(text_edit)
        w.exec_()

    def _preview_array(self, array, title="列表数据"):
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
                    if image_data.mode == 'P':
                        image_data = image_data.convert('RGBA')
                    else:
                        image_data = image_data.convert('RGB')
                width, height = image_data.size
                data = image_data.tobytes('raw', image_data.mode)
                if image_data.mode == 'RGBA':
                    qimage = QImage(data, width, height, QImage.Format_RGBA8888)
                else:
                    qimage = QImage(data, width, height, QImage.Format_RGB8888)
                pixmap = QPixmap.fromImage(qimage)
            except Exception as e:
                print(f"转换PIL图像失败: {e}")
                pixmap = None
        else:
            pixmap = None

        if pixmap is None or pixmap.isNull():
            return

        max_width = 700
        max_height = 700
        original_width = pixmap.width()
        original_height = pixmap.height()

        if original_width > max_width or original_height > max_height:
            scaled_pixmap = pixmap.scaled(
                max_width,
                max_height,
                aspectRatioMode=QtCore.Qt.KeepAspectRatio,
                transformMode=QtCore.Qt.SmoothTransformation
            )
        else:
            scaled_pixmap = pixmap

        w = MessageBoxBase(parent=self.parent_widget)
        w.yesButton.hide()
        w.cancelButton.setText("关闭")
        image_view = ImageLabel()
        image_view.setImage(scaled_pixmap)
        w.viewLayout.addWidget(image_view)
        w.exec_()

    def _fill_native_table(self, table: QTableWidget, df: pd.DataFrame):
        table.clear()
        if df.empty:
            table.setRowCount(1)
            table.setColumnCount(1)
            table.setHorizontalHeaderLabels(["空数据"])
            item = QTableWidgetItem("DataFrame 为空")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(0, 0, item)
            return

        table.setRowCount(df.shape[0])
        table.setColumnCount(df.shape[1])
        table.setHorizontalHeaderLabels(df.columns.astype(str).tolist())
        table.setVerticalHeaderLabels(df.index.astype(str).tolist())

        for i in range(df.shape[0]):
            for j in range(df.shape[1]):
                val = df.iloc[i, j]
                text = "NaN" if pd.isna(val) else str(val)
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setForeground(Qt.black)
                table.setItem(i, j, item)

    def _copy_value(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def _open_file_in_explorer(self, filepath):
        if not os.path.isfile(filepath):
            return
        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", filepath], check=True)
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", filepath], check=True)
            elif sys.platform.startswith("linux"):
                directory = os.path.dirname(filepath)
                subprocess.run(["xdg-open", directory], check=True)
            else:
                print(f"Unsupported platform: {sys.platform}")
        except subprocess.CalledProcessError as e:
            print(f"Error opening file in explorer: {e}")
        except FileNotFoundError:
            print("File or directory not found.")

    def _preview_text_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read(10000)
            self._preview_text(content)
        except Exception as e:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(
                title="文本加载失败",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )

    def _create_styled_table(self):
        table = TableWidget()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectItems)
        table.setSelectionMode(QTableWidget.ContiguousSelection)
        return table