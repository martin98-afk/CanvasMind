# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import os

from PyQt5.QtWidgets import QTreeWidgetItem, QMenu, QAction, QDialog, QLabel, QVBoxLayout, QScrollArea
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QImage
from qfluentwidgets import TreeWidget, RoundMenu


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

    def _format_value(self, obj):
        """返回用于显示的字符串，格式：{Type: info} value..."""
        if obj is None:
            return "None"
        elif isinstance(obj, bool):
            return str(obj).lower()
        elif isinstance(obj, str):
            if len(obj) <= 50:
                return f"'{obj}'"
            else:
                return f"'{obj[:47]}...'"
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

    def _build_tree(self, obj, parent_item, key, max_depth, current_depth=0):
        if current_depth > max_depth:
            item = QTreeWidgetItem(parent_item, ["<max recursion depth>"])
            item.setForeground(0, Qt.gray)
            return

        # 构建显示文本
        if key == "":
            display_text = self._format_value(obj)
        else:
            display_text = f"{key}: {self._format_value(obj)}"

        item = QTreeWidgetItem(parent_item, [display_text])

        # 图像缩略图（保持不变）
        if self._is_image_file(obj) or self._is_pil_image(obj):
            pixmap = self._get_thumbnail_pixmap(obj)
            if pixmap:
                item.setIcon(0, QIcon(pixmap))

        # ========== 根据类型决定是否展开子项 ==========
        if isinstance(obj, dict):
            for k, v in obj.items():
                self._build_tree(v, item, str(k), max_depth, current_depth + 1)

        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                self._build_tree(v, item, str(i), max_depth, current_depth + 1)

        elif isinstance(obj, set):
            for i, v in enumerate(obj):
                self._build_tree(v, item, f"[{i}]", max_depth, current_depth + 1)

        elif isinstance(obj, np.ndarray):
            # 添加 ndarray 的常用属性（像 PyCharm 一样）
            attrs = {
                'shape': obj.shape,
                'dtype': str(obj.dtype),
                'size': obj.size,
                'ndim': obj.ndim,
            }
            for attr_name, attr_val in attrs.items():
                self._build_tree(attr_val, item, attr_name, max_depth, current_depth + 1)

            # 如果是小数组，也允许展开元素（可选）
            if obj.size <= 20:
                if obj.ndim == 1:
                    for i in range(obj.shape[0]):
                        self._build_tree(obj[i], item, f"[{i}]", max_depth, current_depth + 1)
                elif obj.ndim == 2:
                    for i in range(obj.shape[0]):
                        row_item = QTreeWidgetItem(item, [f"[{i}]"])
                        for j in range(obj.shape[1]):
                            self._build_tree(obj[i, j], row_item, str(j), max_depth, current_depth + 1)

        elif isinstance(obj, pd.DataFrame):
            # 展开列名
            for col in obj.columns:
                self._build_tree(obj[col], item, str(col), max_depth, current_depth + 1)

        elif isinstance(obj, pd.Series):
            # 展开索引和值
            for idx in obj.index[:20]:  # 限制数量
                self._build_tree(obj[idx], item, str(idx), max_depth, current_depth + 1)

        elif hasattr(obj, '__dict__') and obj.__dict__:
            for attr_name, attr_value in obj.__dict__.items():
                if not attr_name.startswith('_'):  # 隐藏私有属性（可选）
                    self._build_tree(attr_value, item, attr_name, max_depth, current_depth + 1)

        elif hasattr(obj, '__slots__'):
            for slot in getattr(obj, '__slots__', []):
                if hasattr(obj, slot):
                    attr_value = getattr(obj, slot)
                    if not slot.startswith('_'):
                        self._build_tree(attr_value, item, slot, max_depth, current_depth + 1)

    def _is_image_file(self, obj):
        """检查是否为图像文件路径"""
        if isinstance(obj, str) and os.path.isfile(obj):
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
            return os.path.splitext(obj.lower())[1] in image_extensions
        return False

    def _is_pil_image(self, obj):
        """检查是否为PIL图像对象"""
        try:
            from PIL import Image
            return isinstance(obj, Image.Image)
        except ImportError:
            return False

    def _get_thumbnail_pixmap(self, obj, max_size=150):
        """获取缩略图pixmap"""
        if isinstance(obj, str) and os.path.isfile(obj):
            # 文件路径
            pixmap = QPixmap(obj)
        elif self._is_pil_image(obj):
            # PIL图像对象 - 使用手动转换方法
            try:
                from PIL import Image
                # 转换为RGB或RGBA格式
                if obj.mode not in ('RGB', 'RGBA'):
                    if obj.mode == 'P':
                        obj = obj.convert('RGBA')
                    else:
                        obj = obj.convert('RGB')

                # 获取图像数据
                width, height = obj.size
                data = obj.tobytes('raw', obj.mode)

                # 创建QImage
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
            # 缩放到指定大小，保持宽高比
            scaled_pixmap = pixmap.scaled(
                max_size, max_size,  # 从80增加到120
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            return scaled_pixmap
        return None

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if not item or self._original_data is None:
            return

        menu = RoundMenu()

        # 检查是否为图像数据
        if self._is_image_file(self._original_data) or self._is_pil_image(self._original_data):
            image_action = QAction("🖼️ 预览原图", self)
            image_action.triggered.connect(lambda: self._preview_image(self._original_data))
            menu.addAction(image_action)
            menu.addSeparator()
        elif isinstance(self._original_data, pd.DataFrame):
            action = QAction("🔍 预览完整数据表", self)
            action.triggered.connect(lambda: self.previewRequested.emit(self._original_data))
            menu.addAction(action)
            menu.addSeparator()

        # PyCharm 风格：复制值
        copy_action = QAction("📋 Copy Value", self)
        copy_action.triggered.connect(lambda: self._copy_value(str(self._original_data)))
        menu.addAction(copy_action)

        menu.exec_(event.globalPos())

    def _preview_image(self, image_data):
        """预览图像"""
        dialog = QDialog(self)
        dialog.setWindowTitle("图像预览")

        layout = QVBoxLayout(dialog)
        scroll_area = QScrollArea(dialog)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)

        if isinstance(image_data, str) and os.path.isfile(image_data):
            # 文件路径
            pixmap = QPixmap(image_data)
        elif self._is_pil_image(image_data):
            # PIL图像对象 - 使用手动转换方法
            try:
                from PIL import Image
                # 转换为RGB或RGBA格式
                if image_data.mode not in ('RGB', 'RGBA'):
                    if image_data.mode == 'P':
                        image_data = image_data.convert('RGBA')
                    else:
                        image_data = image_data.convert('RGB')

                # 获取图像数据
                width, height = image_data.size
                data = image_data.tobytes('raw', image_data.mode)

                # 创建QImage
                if image_data.mode == 'RGBA':
                    qimage = QImage(data, width, height, QImage.Format_RGBA8888)
                else:
                    qimage = QImage(data, width, height, QImage.Format_RGB888)

                pixmap = QPixmap.fromImage(qimage)
            except Exception as e:
                print(f"转换PIL图像失败: {e}")
                pixmap = None
        else:
            pixmap = None

        if pixmap and not pixmap.isNull():
            # 设置图像到标签
            label.setPixmap(pixmap)

            # 根据图像大小设置对话框大小，但不超过屏幕大小
            screen_size = dialog.screen().size()
            max_width = min(pixmap.width(), int(screen_size.width() * 0.8))
            max_height = min(pixmap.height(), int(screen_size.height() * 0.8))

            # 设置对话框大小
            dialog.resize(max_width, max_height)

            # 设置滚动区域的最小大小
            scroll_area.setMinimumSize(max_width, max_height)
        else:
            label.setText("无法加载图像")
            dialog.resize(400, 300)

        scroll_area.setWidget(label)
        scroll_area.setWidgetResizable(True)  # 允许标签随滚动区域大小调整
        layout.addWidget(scroll_area)

        dialog.exec_()

    def _copy_value(self, text):
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)