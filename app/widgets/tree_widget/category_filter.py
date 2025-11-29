# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QFrame
from qfluentwidgets import PushButton

from app.widgets.basic_widget.style_sheet import StyleSheet


class CategoryFilterDialog(QWidget):
    """类别筛选对话框，用作下拉弹窗"""
    categories_changed = pyqtSignal(set)

    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.categories = categories
        self.selected_categories = set(categories)  # 默认全选
        self.checkboxes = []
        self._setup_ui()

        # 应用样式表
        StyleSheet.CATEGORY_FILTER.apply(self)

    def _setup_ui(self):
        # 主框架
        main_frame = QFrame(self)

        layout = QVBoxLayout(main_frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # 全选/取消全选按钮
        button_layout = QHBoxLayout()
        select_all_btn = PushButton("全选", self)
        select_all_btn.clicked.connect(self._select_all)
        button_layout.addWidget(select_all_btn)

        select_none_btn = PushButton("取消全选", self)
        select_none_btn.clicked.connect(self._select_none)
        button_layout.addWidget(select_none_btn)

        layout.addLayout(button_layout)

        # 复选框列表
        for category in self.categories:
            checkbox = QCheckBox(category)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(lambda state, cat=category: self._on_category_toggled(cat, state))
            self.checkboxes.append(checkbox)
            layout.addWidget(checkbox)

        # 设置主框架大小
        main_frame.resize(200, min(300, len(self.categories) * 30 + 60))

        # 将主框架添加到窗口
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(main_frame)

    def _on_category_toggled(self, category, state):
        if state == Qt.Checked:
            self.selected_categories.add(category)
        else:
            self.selected_categories.discard(category)
        self.categories_changed.emit(self.selected_categories)

    def _select_all(self):
        for checkbox in self.checkboxes:
            checkbox.setChecked(True)
        self.selected_categories = set(self.categories)
        self.categories_changed.emit(self.selected_categories)

    def _select_none(self):
        for checkbox in self.checkboxes:
            checkbox.setChecked(False)
        self.selected_categories = set()
        self.categories_changed.emit(self.selected_categories)

    def get_selected_categories(self):
        return self.selected_categories.copy()

    def show_at(self, pos):
        self.move(pos)
        self.show()
