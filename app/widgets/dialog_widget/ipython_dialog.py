from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt5.QtCore import Qt

class IPythonConsoleDialog(QDialog):
    """IPython Console 对话框"""
    def __init__(self, ipython_console_widget, parent=None):
        super().__init__(parent)
        self.ipython_console = ipython_console_widget
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("IPython 调试控制台")
        # 设置窗口标志，使其可以调整大小、有最大化最小化按钮
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.resize(800, 600) # 初始大小

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 可选：添加一个工具栏或按钮
        toolbar_layout = QHBoxLayout()
        self.close_btn = QPushButton("隐藏")
        self.close_btn.clicked.connect(self.hide) # 注意：是 hide 而不是 close/accept
        toolbar_layout.addWidget(self.close_btn)
        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

        # 添加 Console
        layout.addWidget(self.ipython_console)

    def closeEvent(self, event):
        """重写关闭事件，不真正关闭，而是隐藏"""
        self.hide()
        event.ignore() # 忽略关闭事件，不销毁窗口