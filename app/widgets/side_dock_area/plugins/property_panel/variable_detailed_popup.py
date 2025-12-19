# -*- coding: utf-8 -*-
import os

import numpy as np
import pandas as pd
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QPixmap, QImage, QFont, QCursor
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QApplication, QHeaderView,
    QTreeWidgetItem, QLabel, QAbstractItemView
)
from qfluentwidgets import (
    TreeWidget, BodyLabel, TextEdit as FluentTextEdit,
    IconWidget, FluentIcon as FIF, isDarkTheme
)


from app.widgets.side_dock_area.plugins.property_panel.variable_tree import (
    _get_formatted_type_and_value, _is_pil_image, _is_image_file
)


class VariableDetailPopup(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._setup_ui()
        self.installEventFilter(self)

    def _setup_ui(self):
        self.setFixedSize(580, 440)
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("popupFrame")
        self._apply_stylesheet()

        self.layout = QVBoxLayout(self.main_frame)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)

        # 内容容器（可切换）
        self.content_area = QWidget(self)
        self.content_area.setStyleSheet("background: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)

        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.main_frame)

        self.layout.addWidget(self.content_area)

    def _apply_stylesheet(self):
        # 支持深色/浅色（虽然你偏好深色，但保留扩展性）
        bg_color = "#252526" if isDarkTheme() else "#ffffff"
        border_color = "#555" if isDarkTheme() else "#ccc"
        text_color = "#d4d4d4" if isDarkTheme() else "#000000"
        alt_bg = "#2a2d2e" if isDarkTheme() else "#f5f5f5"
        header_bg = "#333337" if isDarkTheme() else "#e0e0e0"
        header_text = "#cccccc" if isDarkTheme() else "#000000"
        edit_bg = "#2d2d30" if isDarkTheme() else "#fafafa"
        scrollbar_handle = "#555" if isDarkTheme() else "#aaa"
        scrollbar_handle_hover = "#666" if isDarkTheme() else "#999"

        self.main_frame.setStyleSheet(f"""
            QFrame#popupFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 10px;
                padding: 14px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
            }}
            QLabel, BodyLabel {{
                color: {text_color};
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
            }}
            QTextEdit, TreeWidget {{
                background-color: {edit_bg};
                color: {text_color};
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 6px;
                selection-background-color: #3794ff;
                selection-color: white;
            }}
            TreeWidget {{
                font-family: "Consolas", "Courier New", monospace;
                font-size: 12px;
                alternate-background-color: {alt_bg};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_text};
                padding: 6px;
                border: none;
                font-weight: bold;
            }}
            QScrollBar:vertical {{
                background: #2a2a2e;
                width: 10px;
                margin: 2px 0 2px 0;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {scrollbar_handle};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {scrollbar_handle_hover};
            }}
        """)

    def set_data(self, obj, title="变量详情"):
        # 清空旧内容
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # === 标题区域（图标 + 标题 + 分隔线） ===
        title_label = BodyLabel(title, self)
        title_label.setStyleSheet("color: #FFA500; font-weight: bold; font-size: 14px; padding-left: 4px;")
        icon = IconWidget(FIF.INFO, self)
        icon.setFixedSize(16, 16)
        icon.setStyleSheet("color: #FFA500;")

        title_hbox = QHBoxLayout()
        title_hbox.addWidget(icon)
        title_hbox.addWidget(title_label)
        title_hbox.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444; margin-top: 6px; margin-bottom: 6px;")

        self.content_layout.addLayout(title_hbox)
        self.content_layout.addWidget(sep)

        # === 内容区域 ===
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
            tree.setIndentation(16)
            tree.setSelectionMode(QAbstractItemView.NoSelection)
            tree.setMinimumSize(520, 320)
            tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
            tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
            tree.header().resizeSection(0, 200)
            tree.header().setStretchLastSection(False)

            self._build_nested_tree(obj, tree.invisibleRootItem(), "root", is_root=True)
            tree.expandAll()
            self.content_layout.addWidget(tree)

        self.setMaximumHeight(int(QApplication.primaryScreen().availableGeometry().height() * 0.7))
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
            scaled = pixmap.scaled(500, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_label = QLabel()
            img_label.setPixmap(scaled)
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setStyleSheet("background: #1e1e1e; border-radius: 6px; padding: 8px;")
            self.content_layout.addWidget(img_label)
        else:
            label = BodyLabel("⚠️ 图像加载失败", self)
            label.setStyleSheet("color: #ff6b6b;")
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
        text_edit.setMinimumHeight(220)
        text_edit.setMaximumHeight(400)
        text_edit.setFont(QFont("Consolas", 11))
        text_edit.setLineWrapMode(FluentTextEdit.NoWrap)
        text_edit.moveCursor(text_edit.textCursor().Start)
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        # 点击外部自动关闭（可选）
        if event.type() == QEvent.MouseButtonPress:
            if not self.geometry().contains(event.globalPos()):
                self.close()
                return True
        return super().eventFilter(obj, event)