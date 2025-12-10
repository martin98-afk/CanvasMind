# -*- coding: utf-8 -*-
import os

import numpy as np
import pandas as pd
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QApplication, QHeaderView,
    QTreeWidgetItem, QLabel
)
from qfluentwidgets import TreeWidget, BodyLabel, TextEdit as FluentTextEdit

from app.widgets.side_dock_area.plugins.property_panel.variable_tree import (
    _get_formatted_type_and_value, _is_pil_image, _is_image_file
)


class VariableDetailPopup(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._setup_ui()

    def _setup_ui(self):
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("popupFrame")
        self.main_frame.setStyleSheet("""
            QFrame#popupFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 8px;
                padding: 12px;
            }
            QLabel, BodyLabel { color: white; }
            QTextEdit, TreeWidget {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
            }
            TreeWidget {
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                alternate-background-color: #3a3a3a;
            }
            QHeaderView::section {
                background-color: #444;
                color: white;
                padding: 4px;
                border: none;
            }
        """)

        self.layout = QVBoxLayout(self.main_frame)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        # 内容容器（可切换）
        self.content_area = QWidget(self)
        self.content_area.setStyleSheet("background: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)

        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.main_frame)

        self.layout.addWidget(self.content_area)

    def set_data(self, obj, title="变量详情"):
        # 清空旧内容
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 标题
        title_label = BodyLabel(title, self)
        title_label.setStyleSheet("color: #FFA500; font-weight: bold; font-size: 13px;")
        self.content_layout.addWidget(title_label)

        # 判断类型并展示
        if self._is_image_like(obj):
            self._show_image(obj)
        elif self._is_text_like(obj):
            self._show_text(obj)
        else:
            # 默认：树形结构
            tree = TreeWidget()
            tree.setHeaderLabels(["Key", "Value"])
            tree.setAlternatingRowColors(True)
            tree.setSortingEnabled(False)
            tree.setMinimumSize(500, 300)
            tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            tree.header().setSectionResizeMode(1, QHeaderView.Stretch)

            self._build_nested_tree(obj, tree.invisibleRootItem(), "root", is_root=True)
            tree.expandAll()
            self.content_layout.addWidget(tree)

        self.main_frame.adjustSize()
        self.adjustSize()

    def _is_image_like(self, obj):
        return _is_image_file(obj) or _is_pil_image(obj)

    def _is_text_like(self, obj):
        if isinstance(obj, str):
            if os.path.isfile(obj):
                ext = os.path.splitext(obj.lower())[1]
                return ext in {'.txt', '.log', '.md', '.py', '.json', '.xml', '.yaml', '.yml', '.ini', '.csv'}
            else:
                return True
        return False

    def _show_image(self, obj):
        pixmap = None
        if isinstance(obj, str):
            pixmap = QPixmap(obj)
        elif _is_pil_image(obj):
            try:
                from PIL import Image
                img = obj
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGBA' if 'A' in img.mode else 'RGB')
                data = img.tobytes()
                qim = QImage(data, img.width, img.height,
                             QImage.Format_RGBA8888 if img.mode == 'RGBA' else QImage.Format_RGB8888)
                pixmap = QPixmap.fromImage(qim)
            except Exception:
                pass

        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(500, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_label = QLabel()
            img_label.setPixmap(scaled)
            img_label.setAlignment(Qt.AlignCenter)
            self.content_layout.addWidget(img_label)
        else:
            label = BodyLabel("⚠️ 图像加载失败", self)
            self.content_layout.addWidget(label)

    def _show_text(self, obj):
        content = ""
        if isinstance(obj, str) and os.path.isfile(obj):
            try:
                with open(obj, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(5000)  # 限制长度
            except Exception as e:
                content = f"⚠️ 读取文件失败: {e}"
        else:
            content = str(obj)

        text_edit = FluentTextEdit()
        text_edit.setPlainText(content)
        text_edit.setReadOnly(True)
        text_edit.setMinimumHeight(200)
        text_edit.setMaximumHeight(400)
        self.content_layout.addWidget(text_edit)

    def _build_nested_tree(self, obj, parent_item, key, is_root=False, max_depth=10, current_depth=0):
        if current_depth > max_depth:
            item = QTreeWidgetItem(parent_item, ["<递归深度超限>", ""])
            item.setForeground(0, Qt.gray)
            return

        display_key = key if not is_root else ""
        display_value = _get_formatted_type_and_value(obj)
        item = QTreeWidgetItem(parent_item, [display_key, display_value])
        if obj is not None:
            item.setData(0, Qt.UserRole, obj)

        self._build_recursive_content_nested(obj, item, max_depth, current_depth)

    def _build_recursive_content_nested(self, obj, parent_item, max_depth, current_depth):
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
            attrs = {'shape': obj.shape, 'dtype': str(obj.dtype), 'size': obj.size, 'ndim': obj.ndim}
            for attr_name, attr_val in attrs.items():
                attr_item = QTreeWidgetItem(parent_item, [f"{attr_name}", _get_formatted_type_and_value(attr_val)])
                self._build_recursive_content_nested(attr_val, attr_item, max_depth, current_depth)
        elif isinstance(obj, pd.DataFrame):
            for col in obj.columns[:20]:
                self._build_nested_tree(obj[col], parent_item, str(col), max_depth, current_depth)
        elif isinstance(obj, pd.Series):
            for idx in obj.index[:20]:
                self._build_nested_tree(obj[idx], parent_item, str(idx), max_depth, current_depth)
        elif hasattr(obj, '__dict__') and obj.__dict__:
            for attr_name, attr_value in obj.__dict__.items():
                if not attr_name.startswith('_'):
                    self._build_nested_tree(attr_value, parent_item, attr_name, max_depth, current_depth)

    def show_at_left_of(self, reference_widget: QWidget):
        self.adjustSize()
        self.main_frame.adjustSize()

        ref_rect = reference_widget.rect()
        ref_global = reference_widget.mapToGlobal(ref_rect.topLeft())
        popup_w = self.width()
        popup_h = self.height()

        x = ref_global.x() - popup_w - 4
        y = ref_global.y()

        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = max(x, geom.left())
            if x + popup_w > geom.right():
                x = ref_global.x() + ref_rect.width() + 4
            if y + popup_h > geom.bottom():
                y = geom.bottom() - popup_h
            y = max(y, geom.top())

        self.move(x, y)
        self.show()
        self.setFocus()