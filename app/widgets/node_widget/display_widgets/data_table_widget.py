from PyQt5.QtCore import QSize
from Qt import QtWidgets, QtCore, QtGui


class DataTableWidget(QtWidgets.QTableWidget):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 1. 基础行为设置
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)  # 只读
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)  # 整行选中
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)  # 单选
        self.setAlternatingRowColors(True)  # 开启隔行变色
        self.setShowGrid(False)  # 隐藏网格线，靠背景色区分，更现代
        self.setFocusPolicy(QtCore.Qt.NoFocus)  # 去除选中时的虚线框
        self.verticalHeader().setVisible(False)  # 隐藏行号
        self._current_size = QSize(200, 150)

        # 2. 列宽自适应设置
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)  # 均匀拉伸
        self.horizontalHeader().setHighlightSections(False)  # 点击表头不高亮
        self.horizontalHeader().setMinimumSectionSize(80)

        # 3. 应用深色专业样式 (QSS)
        self.setStyleSheet(self._get_style_sheet())

    def _get_style_sheet(self):
        return """
            QTableWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                gridline-color: #333333;
                border: 1px solid #333333;
                border-radius: 4px;
                font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei";
                font-size: 13px;
            }

            /* 隔行变色 */
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #2A2A2A;
            }

            QTableWidget::item:selected {
                background-color: #37373D;
                color: #00A6FF;  /* 选中文字高亮蓝色 */
            }

            QTableWidget::item:hover {
                background-color: #2D2D2D;
            }

            /* 表头样式 */
            QHeaderView::section {
                background-color: #252526;
                color: #AAAAAA;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #333333;
                font-weight: bold;
                font-size: 12px;
                text-align: left;
            }

            /* 滚动条美化 */
            QScrollBar:vertical {
                background: #1E1E1E;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                min-height: 20px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #505050;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar:horizontal {
                background: #1E1E1E;
                height: 10px;
            }
            QScrollBar::handle:horizontal {
                background: #424242;
                border-radius: 5px;
            }
        """

    def set_value(self, data_list):
        """输入格式: [{"name": "A", "val": 1}, {"name": "B", "val": 2}]"""
        if data_list is None or not data_list or not isinstance(data_list, list):
            self.setVisible(False)  # 完全隐藏
            self.setRowCount(0)
            self._current_size = QSize(200, 150)
            self.sizeHintChanged.emit()
            self.update()
            return
        self.setVisible(True)
        # 禁用更新以提高大数据量时的性能
        self.setUpdatesEnabled(False)
        self._current_size = QtCore.QSize(600, 400)
        self.setFixedSize(self._current_size)
        self.sizeHintChanged.emit()
        self.updateGeometry()
        # 提取表头
        headers = list(data_list[0].keys())
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels([h.upper() for h in headers])  # 表头大写化更显专业
        self.setRowCount(len(data_list))

        for r, row_data in enumerate(data_list):
            # 设置行高，增加呼吸感
            self.setRowHeight(r, 35)
            for c, header in enumerate(headers):
                val = row_data.get(header, "")
                item = QtWidgets.QTableWidgetItem(str(val))

                # 文本对齐：数字右对齐，文字左对齐
                if isinstance(val, (int, float)):
                    item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                else:
                    item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

                self.setItem(r, c, item)

        self.setUpdatesEnabled(True)

    def sizeHint(self):
        # 返回一个更合理的默认尺寸
        return QtCore.QSize(600, 400)