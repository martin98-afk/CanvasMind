from PyQt5.QtCore import QSize
from Qt import QtWidgets, QtCore, QtGui


class JsonTreeWidget(QtWidgets.QTreeWidget):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None, node=None):
        super().__init__(parent)

        # 1. 基础配置
        self.setColumnCount(2)
        self.setHeaderLabels(["Key", "Value"])
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(False)  # 树形结构通常不建议隔行变色，靠缩进区分
        self.setAnimated(True)  # 开启展开动画
        self.setIndentation(20)  # 控制缩进宽度
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setUniformRowHeights(True)  # 优化性能
        self._current_size = QSize(200, 150)
        # 2. 列宽控制
        self.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        self.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.header().setDefaultSectionSize(180)

        # 3. 应用 QSS 样式
        self.setStyleSheet(self._get_style_sheet())

    def _get_style_sheet(self):
        return """
            QTreeWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #333333;
                font-family: "Consolas", "Monaco", "PingFang SC";
                font-size: 13px;
                outline: none;
            }

            QTreeWidget::item {
                padding: 4px;
                border-bottom: 1px solid #252525;
            }

            QTreeWidget::item:hover {
                background-color: #2D2D2D;
            }

            QTreeWidget::item:selected {
                background-color: #37373D;
                color: #FFFFFF;
            }

            /* 表头美化 */
            QHeaderView::section {
                background-color: #252526;
                color: #888888;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #333333;
                font-weight: bold;
            }

            /* 展开/折叠 箭头美化 */
            QTreeView::branch:has-children:!has-siblings:closed,
            QTreeView::branch:closed:has-children:has-siblings {
                image: url(none); /* 如果有图标资源可以替换 */
                border-image: none;
            }

            /* 简单的 CSS 绘制三角形代替默认图标 */
            QTreeView::branch:open:has-children {
                image: none;
            }
        """

    def set_value(self, data):
        self.clear()
        if data is None:
            self.setVisible(False)  # 完全隐藏
            self._current_size = QSize(200, 150)
            self.setFixedSize(self._current_size)
            self.sizeHintChanged.emit()
            self.updateGeometry()
            return
        self.setVisible(True)
        self._current_size = QtCore.QSize(500, 400)
        self.setMinimumSize(self._current_size)
        self.sizeHintChanged.emit()
        self.updateGeometry()
        self.setUpdatesEnabled(False)
        self._populate_tree(data, self.invisibleRootItem())
        self.expandToDepth(1)  # 默认展开一两层，不要全部展开以免数据量大时混乱
        self.setUpdatesEnabled(True)

    def _populate_tree(self, data, parent_item):
        """递归构建树，并进行语法高亮"""
        if isinstance(data, dict):
            for key, value in data.items():
                item = QtWidgets.QTreeWidgetItem([str(key)])
                item.setForeground(0, QtGui.QColor("#9CDCFE"))  # 键名：淡蓝色 (VS Code 风格)
                parent_item.addChild(item)
                self._handle_value(item, value)

        elif isinstance(data, list):
            for i, value in enumerate(data):
                item = QtWidgets.QTreeWidgetItem([f"[{i}]"])
                item.setForeground(0, QtGui.QColor("#808080"))  # 索引：灰色
                parent_item.addChild(item)
                self._handle_value(item, value)

    def _handle_value(self, item, value):
        """根据数据类型设置 Value 列的内容和颜色"""
        if isinstance(value, (dict, list)):
            # 如果是容器，Value 列显示摘要
            count = len(value)
            type_str = "Object" if isinstance(value, dict) else "Array"
            item.setText(1, f"{type_str} [{count}]")
            item.setForeground(1, QtGui.QColor("#6A9955"))  # 摘要：绿色注释感
            self._populate_tree(value, item)
        else:
            # 如果是基础值，直接显示在当前行的第二列
            val_str = str(value)
            item.setText(1, val_str)

            # 语法高亮逻辑
            if isinstance(value, str):
                item.setForeground(1, QtGui.QColor("#CE9178"))  # 字符串：橙红色
                item.setText(1, f'"{val_str}"')
            elif isinstance(value, bool):
                item.setForeground(1, QtGui.QColor("#569CD6"))  # 布尔：蓝色
            elif isinstance(value, (int, float)):
                item.setForeground(1, QtGui.QColor("#B5CEA8"))  # 数字：淡绿色
            elif value is None:
                item.setForeground(1, QtGui.QColor("#569CD6"))  # Null
                item.setText(1, "null")

    def sizeHint(self):
        return self._current_size