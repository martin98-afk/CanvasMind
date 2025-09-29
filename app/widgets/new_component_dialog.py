from PyQt5.QtWidgets import QFormLayout, QWidget
from qfluentwidgets import LineEdit, BodyLabel, PrimaryPushButton, PushButton, MessageBoxBase


class NewComponentDialog(MessageBoxBase):
    def __init__(self, parent=None, default_category=""):
        super().__init__(parent)
        self._default_category = default_category

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
        # 使用 qfluentwidgets 的 LineEdit
        self.name_edit = LineEdit()
        self.category_edit = LineEdit()
        self.description_edit = LineEdit()
        if self._default_category:
            self.category_edit.setText(self._default_category)
        # 添加到表单布局
        self.content_layout.addRow(BodyLabel("组件名称:"), self.name_edit) # 使用 BodyLabel 确保样式一致
        self.content_layout.addRow(BodyLabel("组件分类:"), self.category_edit)
        self.content_layout.addRow(BodyLabel("组件描述:"), self.description_edit)

    def get_component_info(self):
        """获取组件信息"""
        return {
            "name": self.name_edit.text().strip(),
            "category": self.category_edit.text().strip(),
            "description": self.description_edit.text().strip()
        }