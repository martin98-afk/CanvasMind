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


class ProjectExportDialog(MessageBoxBase):
    """项目导出配置对话框：项目名 + requirements 预览 + README 编辑"""

    def __init__(self, project_name: str = "", requirements: str = "", readme: str = "", parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("导出为独立项目")
        self.project_name_edit = LineEdit()
        self.project_name_edit.setText(project_name)
        self.project_name_edit.setPlaceholderText("请输入项目名称")
        self.project_name_edit.setClearButtonEnabled(True)

        # 左侧：requirements 预览（只读）
        self.req_label = BodyLabel("依赖包 (requirements.txt)")
        self.req_edit = TextEdit()
        self.req_edit.setPlainText(requirements)

        # 右侧：README 编辑
        self.readme_label = BodyLabel("项目说明 (README.md)")
        self.readme_edit = TextEdit()
        self.readme_edit.setPlainText(readme)

        # 布局
        top_layout = QVBoxLayout()
        top_layout.addWidget(self.titleLabel)
        top_layout.addWidget(self.project_name_edit)

        # 中间区域：左右分栏
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.req_label)
        left_layout.addWidget(self.req_edit)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.readme_label)
        right_layout.addWidget(self.readme_edit)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([200, 300])  # 默认比例

        self.viewLayout.addLayout(top_layout)
        self.viewLayout.addWidget(splitter, stretch=1)

        # 按钮
        self.yesButton.setText("导出")
        self.cancelButton.setText("取消")

        # 回车提交
        self.project_name_edit.returnPressed.connect(self.accept)
        self.widget.setMinimumWidth(850)
        self.widget.setMinimumHeight(650)

    def get_project_name(self):
        return self.project_name_edit.text().strip()

    def get_readme_content(self):
        return self.readme_edit.toPlainText()

    def get_requirements(self):
        return self.req_edit.toPlainText()