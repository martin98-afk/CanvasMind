# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QSplitter, QWidget
from qfluentwidgets import MessageBoxBase, SubtitleLabel, LineEdit, ComboBox, BodyLabel, PlainTextEdit, TextEdit


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


class CustomTwoInputDialog(MessageBoxBase):
    """自定义输入对话框"""

    def __init__(
            self,
            title1: str="", placeholder1: str = "", text1=None,
            title2: str="", placeholder2: str = "", text2=None,
            parent=None
    ):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title1)
        self.lineEdit = LineEdit()
        if text1:
            self.lineEdit.setText(text1)
        self.lineEdit.setPlaceholderText(placeholder1)
        self.lineEdit.setClearButtonEnabled(True)

        self.titleLabel2 = SubtitleLabel(title2)

        self.lineEdit2 = LineEdit()
        if text2:
            self.lineEdit2.setText(text2)

        self.lineEdit2.setPlaceholderText(placeholder2)
        self.lineEdit2.setClearButtonEnabled(True)

        # 将组件添加到布局中
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.lineEdit)
        self.viewLayout.addWidget(self.titleLabel2)
        self.viewLayout.addWidget(self.lineEdit2)
        self.lineEdit.returnPressed.connect(self.accept)

        # 设置对话框的最小宽度
        self.widget.setMinimumWidth(350)

    def get_text(self):
        return self.lineEdit.text(), self.lineEdit2.text()



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