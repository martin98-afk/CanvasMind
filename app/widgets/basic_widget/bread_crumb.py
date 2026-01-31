# -*- coding: utf-8 -*-
# -- coding: utf-8 --
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFrame


class BreadcrumbItem(QWidget):
    """内部组件：包含文字按钮和分隔符"""
    clicked = pyqtSignal(str)  # 发送 routeKey

    def __init__(self, text, route_key, is_last=False, parent=None):
        super().__init__(parent)
        self.route_key = route_key
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        # 文字按钮
        self.btn = QPushButton(text)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(lambda: self.clicked.emit(self.route_key))

        # 样式定制
        normal_color = "rgba(255, 255, 255, 180)"
        active_color = "#FFFFFF"  # 最后一级高亮

        qss = f"""
            QPushButton {{
                color: {active_color if is_last else normal_color};
                border: none;
                background: transparent;
                font-size: 13px;
                font-weight: {"bold" if is_last else "normal"};
                padding: 2px 4px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 20);
                color: white;
            }}
        """
        self.btn.setStyleSheet(qss)
        self.layout.addWidget(self.btn)

        # 分隔符 (如果不是最后一级)
        if not is_last:
            self.sep = QLabel(">")
            self.sep.setStyleSheet("color: rgba(255, 255, 255, 80); font-family: 'Consolas'; font-size: 12px;")
            self.layout.addWidget(self.sep)


class Breadcrumb(QFrame):
    """自定义面包屑导航栏"""
    currentItemChanged = pyqtSignal(str)  # 兼容信号名

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items_data = []  # 存储 (text, routeKey)

        self.h_layout = QHBoxLayout(self)
        self.h_layout.setContentsMargins(0, 0, 0, 0)
        self.h_layout.setSpacing(2)
        self.h_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.setStyleSheet("background: transparent; border: none;")

    def addItem(self, routeKey, text):
        """添加一个层级"""
        self.items_data.append((text, routeKey))
        self._refresh_ui()

    def setPath(self, path_list):
        """
        批量设置路径
        path_list: [(routeKey, text), ...]
        """
        self.items_data = path_list
        self._refresh_ui()

    def clear(self):
        """清空"""
        self.items_data = []
        self._refresh_ui()

    def _refresh_ui(self):
        """重新构建 UI 组件"""
        # 清理旧组件
        while self.h_layout.count():
            child = self.h_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 根据数据构建
        count = len(self.items_data)
        for i, (text, key) in enumerate(self.items_data):
            is_last = (i == count - 1)
            item_widget = BreadcrumbItem(text, key, is_last=is_last)
            item_widget.clicked.connect(self._handle_click)
            self.h_layout.addWidget(item_widget)

        # 触发尺寸更新
        self.adjustSize()

    def _handle_click(self, key):
        """点击处理：发送信号"""
        self.currentItemChanged.emit(key)