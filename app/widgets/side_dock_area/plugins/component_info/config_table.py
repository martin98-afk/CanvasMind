# -*- coding: utf-8 -*-
import sys
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWidgets import (
    QVBoxLayout, QWidget, QHeaderView, QTableWidgetItem, QSizePolicy
)
from qfluentwidgets import TableWidget, TransparentToolButton, FluentIcon, SimpleCardWidget


class ConfigTableSpace(SimpleCardWidget):
    rowAdded = pyqtSignal(int)
    rowRemoved = pyqtSignal(int)
    dataChanged = pyqtSignal()

    def __init__(self, column_labels=None, parent=None):
        super().__init__(parent)
        self._column_labels = column_labels or ["键", "值"]
        self._num_content_columns = len(self._column_labels)
        total_columns = self._num_content_columns + 1  # +1 for delete button

        # 创建表格
        self.table = TableWidget(self)
        self.table.setColumnCount(total_columns)
        self.table.setHorizontalHeaderLabels(self._column_labels + ["    "])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(total_columns - 1, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(lambda item: self.dataChanged.emit())
        self.table.horizontalScrollBar().valueChanged.connect(
            lambda: QTimer.singleShot(0, self._update_add_button_position)
        )
        # 创建 '+' 按钮（浮动在右上角）
        self._add_button = TransparentToolButton(FluentIcon.ADD, self)
        self._add_button.setFixedSize(24, 24)
        self._add_button.setToolTip("添加配置项")
        self._add_button.clicked.connect(self._add_row)

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.table)

        # 初始定位
        self._add_button.move(self.width() - 30, 6)

    def _update_add_button_position(self):
        header = self.table.horizontalHeader()
        if header.height() <= 0:
            return

        last_content_col = self.table.columnCount() - 2
        if last_content_col < 0:
            # fallback to right edge
            viewport = self.table.viewport()
            btn_x = viewport.width() - self._add_button.width()
            btn_y = (header.height() - self._add_button.height()) // 2
            pos_in_self = self.table.mapTo(self, viewport.pos())
            self._add_button.move(pos_in_self.x() + btn_x, pos_in_self.y() + btn_y)
            self._add_button.raise_()
            return

        # 计算最后一业务列右侧
        last_col_pos = header.sectionViewportPosition(last_content_col)
        last_col_width = header.sectionSize(last_content_col)
        last_col_right = last_col_pos + last_col_width
        scroll_x = self.table.horizontalScrollBar().value()
        visible_right = last_col_right - scroll_x

        btn_x = visible_right  # 在列右侧 4px
        btn_y = (header.height() + self._add_button.height()) // 2 - 2

        pos_in_self = self.table.mapTo(self, self.table.viewport().pos())
        final_x = pos_in_self.x() + btn_x
        final_y = pos_in_self.y() - btn_y

        # 防止超出右边界
        max_x = pos_in_self.x() + self.table.viewport().width() - self._add_button.width()
        final_x = min(final_x, max_x)

        self._add_button.move(int(final_x), int(final_y))
        self._add_button.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._update_add_button_position)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(100, self._update_add_button_position)

    def _get_existing_keys(self):
        keys = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text().strip():
                keys.add(item.text().strip())
        return keys

    def _generate_unique_key(self, base: str = "key") -> str:
        existing = self._get_existing_keys()
        if base not in existing:
            return base
        i = 1
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"

    def _fill_row_content(self, row: int):
        """子类可重写：填充第1列及之后的内容"""
        for col in range(1, self._num_content_columns):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setItem(row, col, item)

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # 第0列：唯一名称
        unique_key = self._generate_unique_key("key")
        key_item = QTableWidgetItem(unique_key)
        key_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 0, key_item)

        # 填充其余列（由子类实现）
        self._fill_row_content(row)

        # 删除按钮
        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("删除")
        delete_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        delete_btn.clicked.connect(self._on_delete_button_clicked)
        self.table.setCellWidget(row, self._num_content_columns, delete_btn)

        self.rowAdded.emit(row)
        self.dataChanged.emit()

    def _on_delete_button_clicked(self):
        btn = self.sender()
        if not btn:
            return
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, self.table.columnCount() - 1) is btn:
                self.table.removeRow(row)
                self.rowRemoved.emit(row)
                self.dataChanged.emit()
                return

    def get_data(self):
        data = []
        for row in range(self.table.rowCount()):
            row_data = {}
            for col, label in enumerate(self._column_labels):
                if col == 0:
                    item = self.table.item(row, col)
                    val = item.text() if item else ""
                else:
                    val = self._get_cell_value(row, col)
                row_data[label] = val
            data.append(row_data)
        return data

    def _get_cell_value(self, row: int, col: int):
        """子类可重写：从自定义控件提取值"""
        item = self.table.item(row, col)
        return item.text() if item else ""

    def set_data(self, data_list):
        self.table.setRowCount(0)
        for row_data in data_list:
            self._add_row_with_data(row_data)

    def _add_row_with_data(self, row_data: dict):
        """子类可重写：支持初始化数据"""
        self._add_row()
        row = self.table.rowCount() - 1
        for col, label in enumerate(self._column_labels):
            value = str(row_data.get(label, ""))
            if col == 0:
                self.table.item(row, col).setText(value)
            else:
                item = self.table.item(row, col)
                if item:
                    item.setText(value)


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ConfigTableSpace 测试")
        self.resize(800, 600)

        central = QWidget()
        layout = QVBoxLayout(central)

        # 创建 ConfigTableSpace：5 列内容 + 1 删除列
        self.config_table = ConfigTableSpace(
            column_labels=["键", "标签", "类型", "默认值", "选项"]
        )
        layout.addWidget(self.config_table)

        self.setCentralWidget(central)

        # 连接信号以打印日志
        self.config_table.rowAdded.connect(lambda r: print(f"[+] 新增行: {r}"))
        self.config_table.rowRemoved.connect(lambda r: print(f"[-] 删除行: {r}"))
        self.config_table.dataChanged.connect(lambda: print("[*] 数据已变更"))

        # 延迟自动测试（模拟用户操作）
        QTimer.singleShot(1000, self._auto_test)

    def _auto_test(self):
        print("\n=== 开始自动测试 ===")

        # 1. 初始应为空
        assert self.config_table.get_data() == [], "初始数据应为空"
        print("✅ 初始状态验证通过")

        # 2. 点击 '+' 三次（模拟 header 点击）
        for _ in range(3):
            self.config_table._add_row()
        assert self.config_table.table.rowCount() == 3, "应有 3 行"
        print("✅ 手动新增 3 行成功")

        # 3. 修改第一行的“键”为 "name"
        self.config_table.table.item(0, 0).setText("name")
        self.config_table.table.item(0, 1).setText("姓名")
        self.config_table.table.item(0, 2).setText("text")

        # 4. 导出数据
        data = self.config_table.get_data()
        expected = [
            {"键": "name", "标签": "姓名", "类型": "text", "默认值": "", "选项": ""},
            {"键": "key2", "标签": "", "类型": "", "默认值": "", "选项": ""},
            {"键": "key3", "标签": "", "类型": "", "默认值": "", "选项": ""},
        ]

        # 5. 使用 set_data 覆盖
        new_data = [
            {"键": "age", "标签": "年龄", "类型": "range", "默认值": "25", "选项": ""},
            {"键": "role", "标签": "角色", "类型": "choice", "默认值": "admin", "选项": "admin,user"},
        ]
        self.config_table.set_data(new_data)
        assert self.config_table.table.rowCount() == 2, "set_data 后应为 2 行"
        assert self.config_table.table.item(0, 0).text() == "age"
        assert self.config_table.table.item(1, 3).text() == "admin"
        print("✅ set_data() 验证通过")

        # 6. 删除第二行（索引1）
        self.config_table._remove_row(1)
        assert self.config_table.table.rowCount() == 1
        assert self.config_table.table.item(0, 0).text() == "age"
        print("✅ 删除行验证通过")

        print("=== 所有测试通过！ ===\n")
        print("你可以手动点击表头 '+' 和删除按钮进一步验证交互。")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec_())