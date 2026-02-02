from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt, QSize, pyqtSignal


class ModernTableModel(QtCore.QAbstractTableModel):
    """高性能数据模型"""

    def __init__(self, data=None):
        super().__init__()
        self._data = data or []
        self._headers = list(self._data[0].keys()) if self._data else []

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        # 防止越界访问
        if index.row() >= len(self._data) or index.column() >= len(self._headers):
            return None

        value = self._data[index.row()][self._headers[index.column()]]

        if role == Qt.DisplayRole:
            return str(value)

        if role == Qt.TextAlignmentRole:
            if isinstance(value, (int, float)):
                return Qt.AlignRight | Qt.AlignVCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section < len(self._headers):
                return self._headers[section].upper()
        return None

    def update_data(self, new_data):
        self.beginResetModel()
        self._data = new_data
        self._headers = list(new_data[0].keys()) if new_data else []
        self.endResetModel()


class DataTableWidget(QtWidgets.QTableView):
    sizeHintChanged = pyqtSignal()

    def __init__(self, parent=None, node=None):
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        # 1. 基础性能与行为设置
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSortingEnabled(True)

        # 优化滚动体验
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)

        # --- 性能核心设置 (修复点) ---
        v_header = self.verticalHeader()
        v_header.setVisible(False)
        # 设置默认行高，这样TableView就不需要逐行计算高度
        v_header.setDefaultSectionSize(36)
        # 强制所有行使用默认高度，这是 QTableView 的性能开关
        v_header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        # 2. 横向表头设置
        h_header = self.horizontalHeader()
        h_header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        h_header.setHighlightSections(False)
        h_header.setMinimumSectionSize(100)

        # 3. 数据模型
        self._model = ModernTableModel()
        self.setModel(self._model)

        # 4. 应用样式
        self.setStyleSheet(self._get_style_sheet())

    def _get_style_sheet(self):
        return """
            QTableView {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #333333;
                gridline-color: #333333;
                border-radius: 4px;
                font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei";
                font-size: 13px;
                outline: none;
            }

            QTableView::item {
                padding-left: 10px;
                padding-right: 10px;
                border-bottom: 1px solid #252525;
            }

            QTableView::item:hover {
                background-color: #2D2D2D;
            }

            QTableView::item:selected {
                background-color: #094771;
                color: #FFFFFF;
            }

            QTableView {
                alternate-background-color: #252526;
            }

            QHeaderView::section {
                background-color: #252526;
                color: #888888;
                padding: 8px 10px;
                border: none;
                border-bottom: 2px solid #333333;
                font-weight: bold;
                font-size: 11px;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #444444;
                min-height: 30px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

            QScrollBar:horizontal {
                background: transparent;
                height: 8px;
            }
            QScrollBar::handle:horizontal {
                background: #444444;
                border-radius: 4px;
            }
        """

    def set_value(self, data_list):
        # 增加对非列表数据的容错（例如传进来的是 HTML 字符串等）
        if not isinstance(data_list, list) or not data_list:
            self.setVisible(False)
            self._model.update_data([])
            return

        self.setVisible(True)
        self.setUpdatesEnabled(False)

        self._model.update_data(data_list)

        # 如果列数过多，自动切换滚动模式而非拉伸
        if len(data_list[0].keys()) > 6:
            self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        else:
            self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        self.setUpdatesEnabled(True)
        self.sizeHintChanged.emit()

    def sizeHint(self):
        return QSize(600, 400)