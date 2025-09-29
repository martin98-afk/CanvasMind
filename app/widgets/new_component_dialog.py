from PyQt5.QtWidgets import QFormLayout, QWidget
from qfluentwidgets import LineEdit, BodyLabel, PrimaryPushButton, Dialog, PushButton


class NewComponentDialog(Dialog): # 继承自 qfluentwidgets.Dialog
    """新建组件对话框"""

    def __init__(self, parent=None):
        # 调用父类 Dialog 的初始化，传入标题和内容
        super().__init__("新建组件", "", parent) # 标题, 内容(这里为空，因为我们要自定义布局)
        self.setModal(True)

        # 创建一个 QWidget 作为内容区域来放置表单
        self.content_widget = QWidget()
        self.content_layout = QFormLayout(self.content_widget)

        self._setup_ui()

        # 将自定义内容添加到 Dialog 的滚动区域
        self.viewLayout.addWidget(self.content_widget)

        # 重新设置按钮，因为父类 Dialog 默认按钮是 Yes/No
        # 我们需要移除旧按钮，添加新的 Ok/Cancel 按钮
        self.yesButton.setParent(None) # 移除默认的 Yes 按钮
        self.cancelButton.setParent(None) # 移除默认的 Cancel 按钮

        # 创建新的按钮并添加到按钮布局
        self.ok_button = PrimaryPushButton("确认")
        self.cancel_button = PushButton("取消")
        self.buttonLayout.addWidget(self.cancel_button)
        self.buttonLayout.addWidget(self.ok_button)

        # 连接按钮信号到 QDialog 的 accept/reject 槽
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def _setup_ui(self):
        # 使用 qfluentwidgets 的 LineEdit
        self.name_edit = LineEdit()
        self.category_edit = LineEdit()
        self.description_edit = LineEdit()

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