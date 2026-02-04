# -*- coding: utf-8 -*-
from qtpy import QtWidgets, QtCore


class MarkdownWidget(QtWidgets.QTextBrowser):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None, node=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        # 设置深色模式样式，符合节点编辑器的风格
        self.setStyleSheet("""
            QTextBrowser {
                background-color: rgb(35, 35, 35);
                color: rgb(200, 200, 200);
                border: none;
                padding: 10px;
            }
        """)
        self._value = ""

    def set_value(self, value):
        self._value = str(value) if value else ""
        # 如果 PyQt 版本低于 5.14，可以使用 self.setHtml()
        if hasattr(self, 'setMarkdown'):
            self.setMarkdown(self._value)
        else:
            self.setPlainText(self._value)

        self.sizeHintChanged.emit()

    def get_value(self):
        return self._value

    def sizeHint(self):
        return QtCore.QSize(300, 200)