# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QFormLayout, QWidget
from qfluentwidgets import LineEdit, BodyLabel, MessageBoxBase, TextEdit, EditableComboBox

from app.scan_components import ComponentScanner


class NewComponentDialog(MessageBoxBase):
    def __init__(self, parent=None, default_name="", default_category="", default_description=""):
        super().__init__(parent)
        self._default_category = default_category
        self._default_name = default_name
        self._default_description = default_description

        # 创建 QWidget 作为内容区域
        self.content_widget = QWidget()
        self.content_layout = QFormLayout(self.content_widget)
        self._setup_ui()

        # ✅ MessageBoxBase 有 viewLayout
        self.viewLayout.addWidget(self.content_widget)

        # 替换按钮
        self.buttonLayout.itemAt(0).widget().deleteLater()
        self.buttonLayout.itemAt(0).widget().deleteLater()

    def _setup_ui(self):
        # 组件名定义
        self.name_edit = LineEdit()
        self.name_edit.setMinimumWidth(300)
        if self._default_name:
            self.name_edit.setText(self._default_name)
        # 组件类别定义
        self.category_edit = EditableComboBox()
        self.category_edit.setMaxVisibleItems(12)
        compoent_map, _ = ComponentScanner().get_components()
        categories = {getattr(cls, 'category', 'General') for cls in compoent_map.values()}
        self.category_edit.addItems(sorted(categories))
        self.category_edit.setText(self._default_category)

        # 组件描述定义
        self.description_edit = TextEdit()
        if self._default_description:
            self.description_edit.setText(self._default_description)
        # 添加到表单布局
        self.content_layout.addRow(BodyLabel("组件名称:"), self.name_edit) # 使用 BodyLabel 确保样式一致
        self.content_layout.addRow(BodyLabel("组件分类:"), self.category_edit)
        self.content_layout.addRow(BodyLabel("组件描述:"), self.description_edit)

    def get_component_info(self):
        """获取组件信息"""
        return {
            "name": self.name_edit.text().strip(),
            "category": self.category_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip()
        }