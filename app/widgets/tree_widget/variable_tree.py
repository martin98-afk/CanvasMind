# -*- coding: utf-8 -*-
import json
import os
import shutil

import numpy as np
import pandas as pd
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon, QImage
from PyQt5.QtWidgets import (
    QTreeWidgetItem, QAction, QDialog, QLabel, QVBoxLayout, QScrollArea,
    QApplication, QTableWidget, QTableWidgetItem, QWidget, QHeaderView, QFileDialog
)
from qfluentwidgets import TreeWidget, RoundMenu, MessageBoxBase, TextEdit, SegmentedWidget, TableWidget, ImageLabel
from qtpy import QtCore

from app.components.base import ArgumentType


class VariableTreeWidget(TreeWidget):
    """用于展示单个变量的详细树状结构"""

    def __init__(self, data=None, port_type=None, max_depth=5, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.setHeaderHidden(True)
        self.setEditTriggers(self.NoEditTriggers)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(False)
        self.setFixedHeight(150)

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
        self._arg_type = None
        if data is not None:
            self.set_data(data, arg_type=port_type, max_depth=max_depth)

    def set_data(self, data, arg_type=None, max_depth=5):
        self._original_data = data
        self._arg_type = arg_type
        self.clear()
        self._build_tree(data, self.invisibleRootItem(), "", max_depth, arg_type=arg_type)
        if self.topLevelItemCount() > 0:
            top_item = self.topLevelItem(0)
            if top_item.childCount() > 0:
                self.expandItem(top_item)

    def _format_value(self, obj, arg_type=None):
        if obj is None:
            return "None"

        if arg_type is not None and isinstance(arg_type, ArgumentType):
            if arg_type.is_image():
                if isinstance(obj, str) and os.path.isfile(obj):
                    return f"{{Image}} '{os.path.basename(obj)}'"
                elif self._is_pil_image(obj):
                    return f"{{PIL.Image}} size={obj.size}"
                else:
                    return "{Image} <invalid>"

            elif arg_type == ArgumentType.CSV:
                if isinstance(obj, str) and os.path.isfile(obj):
                    return f"{{CSV}} '{os.path.basename(obj)}'"
                elif isinstance(obj, pd.DataFrame):
                    return f"{{CSV/DataFrame: ({obj.shape[0]}, {obj.shape[1]})}}"

            elif arg_type == ArgumentType.EXCEL:
                if isinstance(obj, str) and os.path.isfile(obj):
                    return f"{{Excel}} '{os.path.basename(obj)}'"
                elif isinstance(obj, pd.DataFrame):
                    return f"{{Excel/DataFrame: ({obj.shape[0]}, {obj.shape[1]})}}"

            elif arg_type == ArgumentType.JSON:
                # --- 增强 JSON 类型处理 ---
                if isinstance(obj, (dict, list, tuple, set)):
                    length = len(obj) if hasattr(obj, '__len__') else '?'
                    type_name = type(obj).__name__
                    return f"{{JSON/{type_name}: (len={length})}}"
                elif isinstance(obj, (str, bytes)):
                    try:
                        obj = json.loads(obj)
                        return f"{{JSON}} {obj}"
                    except json.JSONDecodeError:
                        return f"{{JSON}} {self._format_value(obj)}"
                else:
                    # 对于非容器的 JSON 兼容类型，也进行格式化
                    return f"{{JSON}} {self._format_value(obj)}"
                # --- 结束增强 ---

            elif arg_type == ArgumentType.FILE:
                if isinstance(obj, str) and os.path.isfile(obj):
                    return f"{{File}} '{os.path.basename(obj)}'"
                else:
                    return f"{{File}} {str(obj)}"

            elif arg_type in (ArgumentType.SKLEARNMODEL, ArgumentType.TORCHMODEL):
                return f"{{Model: {arg_type.value}}}"

            elif arg_type.is_array():
                if isinstance(obj, np.ndarray):
                    shape_str = str(obj.shape).replace(" ", "")
                    return f"{{Array/ndarray: {shape_str}}}"
                elif isinstance(obj, (list, tuple)):
                    return f"{{Array/list: {len(obj)}}}"
                else:
                    return f"{{Array}} {str(obj)}"

            elif arg_type.is_bool():
                return str(bool(obj)).lower()

            elif arg_type.is_number():
                try:
                    val = float(obj)
                    if arg_type == ArgumentType.INT:
                        return str(int(val))
                    else:
                        return str(val)
                except (TypeError, ValueError):
                    return f"{{Number}} {str(obj)}"

            elif arg_type == ArgumentType.TEXT:
                if isinstance(obj, str):
                    if len(obj) <= 50:
                        return f"'{obj}'"
                    else:
                        return f"'{obj[:200]}...' (右键预览)"
                else:
                    return f"'{str(obj)}'"

        if isinstance(obj, bool):
            return str(obj).lower()
        elif isinstance(obj, str):
            if len(obj) <= 50:
                return f"'{obj}'"
            else:
                if os.path.isfile(obj):
                    ext = os.path.splitext(obj)[1].lower()
                    if ext in {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}:
                        return f"🖼️ '{os.path.basename(obj)}'"
                    elif ext in {'.csv', '.xlsx', '.xls'}:
                        return f"📊 '{os.path.basename(obj)}'"
                    elif ext in {'.txt', '.log', '.md', '.py', '.json'}:
                        return f"📄 '{os.path.basename(obj)}'"
                    else:
                        return f"📁 '{os.path.basename(obj)}'"
                else:
                    return f"'{obj[:200]}...' (右键预览)"
        elif isinstance(obj, (int, float)):
            return str(obj)
        elif isinstance(obj, np.number):
            return str(obj)
        elif isinstance(obj, np.ndarray):
            shape_str = str(obj.shape).replace(" ", "")
            total = obj.size
            if total <= 20 and obj.ndim <= 2:
                try:
                    s = np.array2string(obj, separator=' ', threshold=20, edgeitems=3)
                    if s.startswith('array(') and s.endswith(')'):
                        s = s[6:-1]
                    return f"{{ndarray: {shape_str}}} [{s}]"
                except:
                    return f"{{ndarray: {shape_str}}}"
            else:
                return f"{{ndarray: {shape_str}}} <dtype={obj.dtype}> ..."
        elif isinstance(obj, pd.DataFrame):
            return f"{{DataFrame: ({obj.shape[0]}, {obj.shape[1]})}}"
        elif isinstance(obj, pd.Series):
            return f"{{Series: ({len(obj)})}}"
        elif isinstance(obj, dict):
            return f"{{dict: {len(obj)}}}"
        elif isinstance(obj, list):
            return f"{{list: {len(obj)}}}"
        elif isinstance(obj, tuple):
            return f"{{tuple: {len(obj)}}}"
        elif isinstance(obj, set):
            return f"{{set: {len(obj)}}}"
        elif self._is_image_file(obj):
            return f"{{Image}} '{os.path.basename(str(obj))}'"
        elif self._is_pil_image(obj):
            return f"{{PIL.Image}} size={obj.size}"
        elif hasattr(obj, '__class__'):
            cls = obj.__class__
            mod = cls.__module__
            name = cls.__name__
            if mod == 'builtins':
                return f"{{{name}}}"
            else:
                return f"{{{mod}.{name}}}"
        else:
            return str(obj)

    def _build_tree(self, obj, parent_item, key, max_depth, current_depth=0, arg_type=None):
        if current_depth > max_depth:
            item = QTreeWidgetItem(parent_item, ["<max recursion depth>"])
            item.setForeground(0, Qt.gray)
            return

        if key == "":
            display_text = self._format_value(obj, arg_type)
        else:
            display_text = f"{key}: {self._format_value(obj, arg_type)}"

        item = QTreeWidgetItem(parent_item, [display_text])
        item.setData(0, Qt.UserRole, obj)

        if (self._is_image_file(obj) or self._is_pil_image(obj) or
                (arg_type is not None and isinstance(arg_type, ArgumentType) and arg_type.is_image())):
            pixmap = self._get_thumbnail_pixmap(obj)
            if pixmap:
                item.setIcon(0, QIcon(pixmap))

        # --- 增强的递归逻辑 ---
        self._build_recursive_content(obj, item, max_depth, current_depth)

    def _build_recursive_content(self, obj, parent_item, max_depth, current_depth):
        """
        专门用于递归构建子项内容的函数，可以被 _build_tree 和 _build_nested_tree 复用
        """
        current_depth += 1
        if current_depth > max_depth:
            return

        if isinstance(obj, dict):
            for k, v in obj.items():
                self._build_tree(v, parent_item, str(k), max_depth, current_depth)

        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                self._build_tree(v, parent_item, str(i), max_depth, current_depth)

        elif isinstance(obj, set):
            for i, v in enumerate(obj):
                self._build_tree(v, parent_item, f"[{i}]", max_depth, current_depth)

        elif isinstance(obj, np.ndarray):
            # 对于 ndarray，展示属性和可展开的内容
            attrs = {
                'shape': obj.shape,
                'dtype': str(obj.dtype),
                'size': obj.size,
                'ndim': obj.ndim,
            }
            for attr_name, attr_val in attrs.items():
                # 为属性创建子节点，但不继续递归展开属性值（如 shape 元组）
                attr_item = QTreeWidgetItem(parent_item, [f"{attr_name}", self._format_value(attr_val)])
                # 如果属性值本身是容器，可以考虑展开，但要严格控制深度
                self._build_recursive_content(attr_val, attr_item, max_depth, current_depth)

            # 如果数组元素较少，展开内容
            if obj.size <= 20:
                if obj.ndim == 1:
                    for i in range(obj.shape[0]):
                        self._build_tree(obj[i], parent_item, f"[{i}]", max_depth, current_depth)
                elif obj.ndim == 2:
                    for i in range(obj.shape[0]):
                        row_item = QTreeWidgetItem(parent_item, [f"[{i}]"])
                        for j in range(obj.shape[1]):
                            self._build_tree(obj[i, j], row_item, str(j), max_depth, current_depth)

        elif isinstance(obj, pd.DataFrame):
            # 对于 DataFrame，展开列
            for col in obj.columns:
                self._build_tree(obj[col], parent_item, str(col), max_depth, current_depth)

        elif isinstance(obj, pd.Series):
            # 对于 Series，展开索引
            for idx in obj.index[:20]: # 限制展开数量
                self._build_tree(obj[idx], parent_item, str(idx), max_depth, current_depth)

        elif hasattr(obj, '__dict__') and obj.__dict__:
            for attr_name, attr_value in obj.__dict__.items():
                if not attr_name.startswith('_'):
                    self._build_tree(attr_value, parent_item, attr_name, max_depth, current_depth)

        elif hasattr(obj, '__slots__'):
            for slot in getattr(obj, '__slots__', []):
                if hasattr(obj, slot):
                    attr_value = getattr(obj, slot)
                    if not slot.startswith('_'):
                        self._build_tree(attr_value, parent_item, slot, max_depth, current_depth)

    def _is_image_file(self, obj):
        if isinstance(obj, str) and os.path.isfile(obj):
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
            return os.path.splitext(obj.lower())[1] in image_extensions
        return False

    def _is_pil_image(self, obj):
        try:
            from PIL import Image
            return isinstance(obj, Image.Image)
        except ImportError:
            return False

    def _get_thumbnail_pixmap(self, obj, max_size=150):
        if isinstance(obj, str) and os.path.isfile(obj):
            pixmap = QPixmap(obj)
        elif self._is_pil_image(obj):
            try:
                from PIL import Image
                if obj.mode not in ('RGB', 'RGBA'):
                    if obj.mode == 'P':
                        obj = obj.convert('RGBA')
                    else:
                        obj = obj.convert('RGB')
                width, height = obj.size
                data = obj.tobytes('raw', obj.mode)
                if obj.mode == 'RGBA':
                    qimage = QImage(data, width, height, QImage.Format_RGBA8888)
                else:
                    qimage = QImage(data, width, height, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimage)
            except Exception as e:
                print(f"转换PIL图像失败: {e}")
                return None
        else:
            return None

        if pixmap and not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                max_size, max_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            return scaled_pixmap
        return None

    def show_detail(self):
        obj = self._original_data
        if isinstance(obj, str) and not os.path.isfile(obj):
            self._preview_text(obj)

        elif isinstance(obj, str) and os.path.isfile(obj):
            filepath = obj
            ext = os.path.splitext(filepath.lower())[1]

            if ext in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp'}:
                self._preview_image(filepath)

            elif ext == '.csv':
                self._preview_csv_full(filepath)

            elif ext in {'.xlsx', '.xls'}:
                self._preview_excel(filepath) # 调用优化后的方法

            elif ext in {'.txt', '.log', '.md', '.py', '.json', '.xml', '.yaml', '.yml', '.ini'}:
                self._preview_text_file(filepath)

        elif isinstance(obj, (list, tuple)):
            self._preview_nested_structure(obj, "列表数据预览")

        elif isinstance(obj, dict):
            self._preview_nested_structure(obj, "字典数据预览")

        elif isinstance(obj, set):
            self._preview_nested_structure(obj, "元组数据预览")

        elif isinstance(obj, pd.DataFrame):
            self._preview_dataframe_full(obj)

        elif self._is_pil_image(obj):
            self._preview_image(obj)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if not item:
            return

        obj = item.data(0, Qt.UserRole)
        if obj is None:
            return

        menu = RoundMenu(parent=self)

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
                # 移除旧的预览动作，使用新的优化后方法
                preview_limited = QAction("📊 预览所有工作表", self)
                preview_limited.triggered.connect(lambda: self._preview_excel(filepath))
                menu.addAction(preview_limited)

                # preview_full = QAction("🔍 预览完整数据", self)
                # preview_full.triggered.connect(lambda: self._preview_excel_full(filepath))
                # menu.addAction(preview_full)

            elif ext in {'.txt', '.log', '.md', '.py', '.json', '.xml', '.yaml', '.yml', '.ini'}:
                action = QAction("🔍 预览文本内容", self)
                action.triggered.connect(lambda: self._preview_text_file(filepath))
                menu.addAction(action)

            save_action = QAction("💾 另存为...", self)
            save_action.triggered.connect(lambda: self._save_file(filepath))
            menu.addAction(save_action)

        elif isinstance(obj, (list, tuple)):
            action = QAction("🔍 预览完整列表", self)
            action.triggered.connect(lambda: self._preview_nested_structure(obj, "列表数据预览"))
            menu.addAction(action)

        elif isinstance(obj, dict):
            action = QAction("🔍 预览完整字典", self)
            action.triggered.connect(lambda: self._preview_nested_structure(obj, "字典数据预览"))
            menu.addAction(action)

        elif isinstance(obj, set):
            action = QAction("🔍 预览完整集合", self)
            action.triggered.connect(lambda: self._preview_nested_structure(obj, "元组数据预览"))
            menu.addAction(action)

        elif isinstance(obj, pd.DataFrame):
            action = QAction("🔍 预览完整数据表", self)
            action.triggered.connect(lambda: self._preview_dataframe_full(obj))
            menu.addAction(action)

        elif self._is_pil_image(obj):
            action = QAction("🖼️ 预览原图", self)
            action.triggered.connect(lambda: self._preview_image(obj))
            menu.addAction(action)

        copy_action = QAction("📋 Copy Value", self)
        copy_action.triggered.connect(lambda: self._copy_value(str(obj)))
        menu.addAction(copy_action)

        menu.exec_(event.globalPos())

    def _preview_nested_structure(self, data, title="嵌套结构预览"):
        """
        为嵌套容器（list, dict, tuple, set）创建一个树状预览窗口
        """
        dialog = MessageBoxBase(parent=self.parent_widget)
        dialog.yesButton.hide()
        dialog.cancelButton.setText("关闭")

        # 创建一个 TreeWidget 用于展示嵌套结构
        tree_widget = TreeWidget()
        tree_widget.setHeaderLabels(["Key", "Value"])

        tree_widget.setAlternatingRowColors(False)
        tree_widget.setSortingEnabled(False)
        tree_widget.setMinimumSize(800, 600)

        # 构建树
        self._build_nested_tree(data, tree_widget.invisibleRootItem(), "", is_root=True)

        # 展开所有节点
        tree_widget.expandAll()

        dialog.viewLayout.addWidget(tree_widget)
        dialog.exec_()

    def _build_nested_tree(self, obj, parent_item, key, is_root=False, max_depth=10, current_depth=0):
        """
        递归构建嵌套结构的树
        与 _build_tree 逻辑类似，但使用两列显示
        """
        if current_depth > max_depth:
            item = QTreeWidgetItem(parent_item, ["<max recursion depth>", ""])
            item.setForeground(0, Qt.gray)
            return

        display_key = key if not is_root else "root"
        display_value = self._format_value(obj)

        item = QTreeWidgetItem(parent_item, [display_key, display_value])
        item.setData(0, Qt.UserRole, obj)

        # 使用复用的递归逻辑
        self._build_recursive_content_nested(obj, item, max_depth, current_depth)

    def _build_recursive_content_nested(self, obj, parent_item, max_depth, current_depth):
        """
        专门用于递归构建预览窗口中子项内容的函数，对应两列的 TreeWidget
        """
        current_depth += 1
        if current_depth > max_depth:
            return

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
            # 对于 ndarray，展示属性和可展开的内容
            attrs = {
                'shape': obj.shape,
                'dtype': str(obj.dtype),
                'size': obj.size,
                'ndim': obj.ndim,
            }
            for attr_name, attr_val in attrs.items():
                # 为属性创建子节点，但不继续递归展开属性值（如 shape 元组）
                attr_item = QTreeWidgetItem(parent_item, [f"{attr_name}", self._format_value(attr_val)])
                # 如果属性值本身是容器，可以考虑展开，但要严格控制深度
                self._build_recursive_content_nested(attr_val, attr_item, max_depth, current_depth)

            # 如果数组元素较少，展开内容
            if obj.size <= 20:
                if obj.ndim == 1:
                    for i in range(obj.shape[0]):
                        self._build_nested_tree(obj[i], parent_item, f"[{i}]", max_depth, current_depth)
                elif obj.ndim == 2:
                    for i in range(obj.shape[0]):
                        row_item = QTreeWidgetItem(parent_item, [f"[{i}]", ""])
                        for j in range(obj.shape[1]):
                            self._build_nested_tree(obj[i, j], row_item, str(j), max_depth, current_depth)

        elif isinstance(obj, pd.DataFrame):
            # 对于 DataFrame，展开列
            for col in obj.columns:
                self._build_nested_tree(obj[col], parent_item, str(col), max_depth, current_depth)

        elif isinstance(obj, pd.Series):
            # 对于 Series，展开索引
            for idx in obj.index[:20]: # 限制展开数量
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

    def _preview_dataframe_full(self, df: pd.DataFrame):
        dialog = MessageBoxBase(parent=self.parent_widget)
        dialog.yesButton.hide()
        dialog.cancelButton.setText("关闭")

        table = self._create_styled_table()
        table.setMinimumSize(800, 600)
        table.verticalHeader().hide()
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
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
                table.setItem(i, j, item)

        dialog.viewLayout.addWidget(table)
        dialog.exec_()

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
        """
        优化：使用 SegmentedWidget 预览 Excel 文件的所有工作表
        """
        try:
            # 使用 pd.ExcelFile 获取所有 sheet 名称
            xls = pd.ExcelFile(filepath)
            sheet_names = xls.sheet_names
            if not sheet_names:
                raise ValueError("Excel 文件无有效工作表")

            dialog = QDialog(self)
            dialog.setWindowTitle(f"Excel 预览 - {os.path.basename(filepath)}")
            dialog.resize(900, 600)
            layout = QVBoxLayout(dialog)

            # 创建 SegmentedWidget 用于切换工作表
            seg_widget = SegmentedWidget()
            table = self._create_styled_table()

            def load_sheet(name):
                """加载指定工作表到表格"""
                try:
                    # 从 ExcelFile 对象读取指定 sheet，避免重复打开文件
                    df = pd.read_excel(xls, sheet_name=name, nrows=1000) # 限制行数
                    self._fill_native_table(table, df)
                except Exception as e:
                    table.clear()
                    table.setRowCount(1)
                    table.setColumnCount(1)
                    item = QTableWidgetItem(f"加载失败: {e}")
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setForeground(Qt.black)
                    table.setItem(0, 0, item)

            # 添加所有工作表到 SegmentedWidget
            for name in sheet_names:
                seg_widget.addItem(name, text=name) # 使用 sheet_name 作为 key 和 text

            # 连接切换事件
            seg_widget.currentItemChanged.connect(load_sheet)

            # 默认加载第一个工作表
            load_sheet(sheet_names[0])

            layout.addWidget(seg_widget)
            layout.addWidget(table)
            dialog.exec_()

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

    def _preview_image(self, image_data):
        pixmap = None

        if isinstance(image_data, str) and os.path.isfile(image_data):
            pixmap = QPixmap(image_data)
        elif self._is_pil_image(image_data):
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

        # === 智能缩放逻辑 ===
        max_width = 700
        max_height = 700
        original_width = pixmap.width()
        original_height = pixmap.height()

        # 仅当图像太大时才缩放
        if original_width > max_width or original_height > max_height:
            scaled_pixmap = pixmap.scaled(
                max_width,
                max_height,
                aspectRatioMode=QtCore.Qt.KeepAspectRatio,
                transformMode=QtCore.Qt.SmoothTransformation
            )
        else:
            scaled_pixmap = pixmap  # 小图保持原尺寸

        # === 显示对话框 ===
        w = MessageBoxBase(parent=self.parent_widget)
        w.yesButton.hide()
        w.cancelButton.setText("关闭")
        image_view = ImageLabel()
        image_view.setImage(scaled_pixmap)  # 使用缩放后的 pixmap
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
            item.setForeground(Qt.black)
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

    def _save_file(self, filepath):
        name = os.path.basename(filepath)
        save_path, _ = QFileDialog.getSaveFileName(self, "另存为", name)
        if save_path:
            try:
                shutil.copy2(filepath, save_path)
                from qfluentwidgets import InfoBar, InfoBarPosition
                InfoBar.success(
                    title="保存成功",
                    content=f"文件已保存至：{os.path.basename(save_path)}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self
                )
            except Exception as e:
                from qfluentwidgets import InfoBar, InfoBarPosition
                InfoBar.error(
                    title="保存失败",
                    content=str(e),
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3000,
                    parent=self
                )

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
        table.setAlternatingRowColors(True)

        return table


# ============ 示例使用 ============
if __name__ == "__main__":
    # 示例：嵌套数据结构
    sample_data = {
        "name": "Alice",
        "age": 30,
        "scores": [95, 88, 100],
        "profile": {
            "hobbies": ["reading", "cycling"],
            "address": {
                "city": "Beijing",
                "details": {
                    "street": "Zhongguancun",
                    "number": 100
                }
            }
        },
        "metadata": np.array([1.0, 2.0, 3.0]),
        "df": pd.DataFrame({"col1": [1, 2], "col2": [3, 4]})
    }

    app = QApplication([])
    tree = VariableTreeWidget(data=sample_data)
    tree.show()
    app.exec_()