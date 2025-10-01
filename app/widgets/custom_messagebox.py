from qfluentwidgets import MessageBoxBase, SubtitleLabel, LineEdit, ComboBox


class CustomInputDialog(MessageBoxBase):
    """自定义输入对话框"""

    def __init__(self, title: str, placeholder: str = "", currenttext: str = None, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title)
        self.lineEdit = LineEdit()

        self.lineEdit.setPlaceholderText(placeholder)
        if currenttext:
            self.lineEdit.setText(currenttext)
        self.lineEdit.setClearButtonEnabled(True)

        # 将组件添加到布局中
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.lineEdit)
        self.lineEdit.returnPressed.connect(self.accept)

        # 设置对话框的最小宽度
        self.widget.setMinimumWidth(350)

    def get_text(self):
        return self.lineEdit.text()


class CustomComboDialog(MessageBoxBase):
    """自定义组合框对话框"""

    def __init__(self, title: str, items: list, current_index: int = 0, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title)
        self.comboBox = ComboBox()
        self.comboBox.addItems(items)
        self.comboBox.setCurrentIndex(current_index)

        # 将组件添加到布局中
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.comboBox)

        # 设置对话框的最小宽度
        self.widget.setMinimumWidth(350)

    def get_text(self):
        return self.comboBox.currentText()