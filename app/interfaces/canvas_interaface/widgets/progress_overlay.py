from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication, QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class ModernProgressOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 设置窗口属性：工具窗口、无边框、置顶
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.fixed_width = 340
        self.fixed_height = 110
        self.setFixedSize(self.fixed_width, self.fixed_height)

        # 1. 布局
        self.main_layout = QVBoxLayout(self)
        self.container = QWidget()
        self.container.setObjectName("MainContainer")

        # 2. 现代深色样式
        self.container.setStyleSheet("""
            QWidget#MainContainer {
                background-color: #2D2D2D;
                border-radius: 12px;
                border: 1px solid #454545;
            }
            QLabel {
                color: #E0E0E0;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 13px;
                background: transparent;
            }
            QProgressBar {
                border: none;
                background-color: #1A1A1A;
                height: 6px;
                text-align: center;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #0078D4;
                border-radius: 3px;
            }
        """)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(25, 20, 25, 20)

        self.label = QLabel("正在准备加载...")
        self.label.setAlignment(Qt.AlignCenter)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)

        container_layout.addWidget(self.label)
        container_layout.addSpacing(12)
        container_layout.addWidget(self.bar)

        self.main_layout.addWidget(self.container)

        # 3. 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

    def set_text(self, text):
        """更新显示的文字"""
        self.label.setText(text)

    def set_value(self, val):
        """更新进度条值"""
        self.bar.setValue(val)

    # ────────────── 新增/修改的方法 ──────────────

    def set_maximum(self, max_val):
        """
        设置进度条的最大值。
        例如：有 500 个节点，就调用 set_maximum(500)
        """
        self.bar.setRange(0, max_val)
        self.bar.setValue(0)

    def set_mode_indeterminate(self):
        """
        设置为不确定模式（左右来回滚动/转圈），用于不知道进度的场景（如保存文件时）
        """
        self.bar.setRange(0, 0)

    def set_mode_determinate(self, max_val=100):
        """
        恢复为确定模式（0-max_val）
        """
        self.bar.setRange(0, max_val)
        self.bar.setValue(0)

    # ───────────────────────────────────────────

    def center_to_parent(self):
        """将窗口移动到父窗口的几何中心"""
        p = self.parent()
        if p:
            target = p.window()
            rect = target.geometry()
            x = rect.x() + (rect.width() - self.fixed_width) // 2
            y = rect.y() + (rect.height() - self.fixed_height) // 2
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - self.fixed_width) // 2,
                      (screen.height() - self.fixed_height) // 2)

    def showEvent(self, event):
        super().showEvent(event)
        self.center_to_parent()