# -*- coding: utf-8 -*-
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QDialog,
    QLabel,
    QPushButton,
    QListWidgetItem,
    QMenu,
    QApplication,
)
from qfluentwidgets import (
    LineEdit,
    ToolButton,
    PrimaryToolButton,
    InfoBar,
    InfoBarPosition,
    isDarkTheme,
    CaptionLabel,
    FluentIcon,
    ComboBox,
    PushButton,
    ScrollArea,
    PrimaryPushButton,
    TransparentToolButton, CommandBar, Action,
)

from app.utils.utils import get_icon
from app.tool_window import (
    ToolWindow,
    DockPosition,
    DockCategory,
)
from .db_manager import DatabaseManager


class TableLabel(QLabel):
    clicked = pyqtSignal(str)
    double_clicked = pyqtSignal(str)

    LONG_PRESS_TIMEOUT = 500

    def __init__(self, table_name, parent=None):
        super().__init__(table_name, parent)
        self._table_name = table_name
        self._selected = False
        self._dark = isDarkTheme()
        self._update_style()
        self._long_press_timer = None
        self._drag_started = False

    def setSelected(self, selected):
        self._selected = selected
        self._update_style()

    def _update_style(self):
        if self._dark:
            bg = "rgba(64,158,255,25%)" if self._selected else "transparent"
            color = "#E0E0E0"
            hover_bg = "rgba(255,255,255,8%)"
        else:
            bg = "rgba(0,122,204,15%)" if self._selected else "transparent"
            color = "#333333"
            hover_bg = "rgba(0,0,0,5%)"

        self.setStyleSheet(f"""
            QLabel {{
                padding: 4px 8px;
                border-radius: 4px;
                background: {bg};
                color: {color};
                font-size: 13px;
            }}
            QLabel:hover {{
                background: {hover_bg};
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_started = False
            self._long_press_timer = QtCore.QTimer(self)
            self._long_press_timer.setSingleShot(True)
            self._long_press_timer.timeout.connect(lambda: self._start_drag(event))
            self._long_press_timer.start(self.LONG_PRESS_TIMEOUT)
            self.clicked.emit(self._table_name)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self._long_press_timer and self._long_press_timer.isActive():
                self._long_press_timer.stop()
            if not self._drag_started:
                self._start_drag(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._long_press_timer and self._long_press_timer.isActive():
                self._long_press_timer.stop()
                self._drag_started = True
        super().mouseReleaseEvent(event)

    def _start_drag(self, event):
        if self._drag_started:
            return
        self._drag_started = True

        mime_data = QtCore.QMimeData()
        drag_data = {
            "table_name": self._table_name,
        }
        import orjson

        mime_data.setData("application/x-sqlite-table", orjson.dumps(drag_data))

        drag = QtGui.QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec_(Qt.CopyAction | Qt.MoveAction)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self._table_name)
        super().mouseDoubleClickEvent(event)


class SQLiteDatabaseWindow(ToolWindow):
    name = "SQLite数据库"
    icon = get_icon("数据库操作")
    default_position = DockPosition.BOTTOM
    CATEGORIES = [DockCategory.CANVAS]
    display_order = 100

    def setup_ui(self):
        self.db_manager = DatabaseManager()
        self.current_table = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_connection_bar()
        self.setup_content()
        self._auto_connect_default_db()

    def _auto_connect_default_db(self):
        import os

        db_dir = "canvas_files"
        db_path = os.path.join(db_dir, "default.db")
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self.path_edit.setText(db_path)
        try:
            self.db_manager.connect(db_path)
            self.close_btn.setEnabled(True)
            self.new_table_btn.setEnabled(True)
            self._refresh_tables()
        except Exception as e:
            self._show_status(f"连接失败: {e}")

    def _show_status(self, msg):
        InfoBar.info("数据库", msg, position=InfoBarPosition.TOP, parent=self).show()

    def showEvent(self, event):
        super().showEvent(event)
        self._register_drag_handler()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._unregister_drag_handler()

    def _register_drag_handler(self):
        homepage = getattr(self, "homepage", None)
        if not homepage:
            return
        graph = getattr(homepage, "graph", None)
        if not graph:
            return
        viewer = getattr(graph, "graph_splitter", None)
        if not viewer:
            return
        active_viewer = viewer.get_active_viewer()
        if not active_viewer:
            return
        if not hasattr(active_viewer, "register_drag_handler"):
            return
        if "application/x-sqlite-table" in active_viewer._drag_handlers:
            return
        active_viewer.register_drag_handler(
            "application/x-sqlite-table", self._handle_table_drag
        )

    def _unregister_drag_handler(self):
        homepage = getattr(self, "homepage", None)
        if not homepage:
            return
        graph = getattr(homepage, "graph", None)
        if not graph:
            return
        viewer = getattr(graph, "graph_splitter", None)
        if not viewer:
            return
        active_viewer = viewer.get_active_viewer()
        if not active_viewer:
            return
        if not hasattr(active_viewer, "unregister_drag_handler"):
            return
        active_viewer.unregister_drag_handler("application/x-sqlite-table")

    def _handle_table_drag(self, viewer, drag_data, scene_pos):
        table_name = drag_data.get("table_name", "")
        if not table_name:
            return
        homepage = getattr(self, "homepage", None)
        if not homepage:
            return
        db_path = ""
        if self.db_manager and self.db_manager.is_connected:
            db_path = self.db_manager.db_path or ""
        viewer._create_node_with_properties(
            "sqlite套件/查询数据",
            {"database_path": db_path, "table_name": table_name},
            scene_pos,
        )

    def _setup_title_bar(self):
        title_bar = self.get_title_bar()
        title_bar.set_title("SQLite数据库")

    def setup_connection_bar(self):
        bar_widget = QWidget()
        bar_layout = QHBoxLayout(bar_widget)
        bar_layout.setContentsMargins(8, 4, 8, 4)
        bar_layout.setSpacing(8)

        self.path_edit = LineEdit(self)
        self.path_edit.setPlaceholderText("数据库路径...")
        self.path_edit.setFixedHeight(28)
        self.path_edit.returnPressed.connect(self._on_connect)

        self.open_btn = ToolButton(FluentIcon.FOLDER, self)
        self.open_btn.setFixedSize(28, 28)
        self.open_btn.setToolTip("选择数据库文件")
        self.open_btn.clicked.connect(self._on_open_file)

        self.connect_btn = PrimaryToolButton(FluentIcon.PLAY, self)
        self.connect_btn.setFixedSize(28, 28)
        self.connect_btn.setToolTip("连接/创建数据库")
        self.connect_btn.clicked.connect(self._on_connect)

        self.close_btn = ToolButton(FluentIcon.CLOSE, self)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("关闭连接")
        self.close_btn.clicked.connect(self._on_close)
        self.close_btn.setEnabled(False)

        bar_layout.addWidget(self.path_edit, 1)
        bar_layout.addWidget(self.open_btn)
        bar_layout.addWidget(self.connect_btn)
        bar_layout.addWidget(self.close_btn)

        self.main_layout.addWidget(bar_widget)

    def setup_content(self):
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(1)

        self.table_list_widget = self._create_table_list()
        content_layout.addWidget(self.table_list_widget, 1)

        self.data_panel = self._create_data_panel()
        content_layout.addWidget(self.data_panel, 4)

        self.main_layout.addWidget(content_widget, 1)

    def _create_table_list(self):
        widget = QWidget()
        widget.setMinimumWidth(180)
        dark = isDarkTheme()

        bg_color = "#1E1E1E" if dark else "#F5F5F5"
        border_color = "#3A3A3A" if dark else "#E0E0E0"
        text_color = "#E0E0E0" if dark else "#333333"
        hover_bg = "rgba(255,255,255,8%)" if dark else "rgba(0,0,0,5%)"
        selected_bg = "rgba(64,158,255,25%)" if dark else "rgba(0,122,204,15%)"

        widget.setStyleSheet(f"""
            QWidget {{
                background: {bg_color};
                border-right: 1px solid {border_color};
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QLabel {{
                padding: 4px 8px;
                border-radius: 4px;
                color: {text_color};
            }}
            QLabel:hover {{
                background: {hover_bg};
            }}
            QLabel[selected="true"] {{
                background: {selected_bg};
            }}
        """)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(4)

        self.table_count_label = CaptionLabel("表 (0)")
        self.table_count_label.setStyleSheet(f"font-weight: bold; color: {text_color};")

        self.refresh_btn = ToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setFixedSize(24, 24)
        self.refresh_btn.setToolTip("刷新 (F5)")
        self.refresh_btn.clicked.connect(self._refresh_tables)

        self.new_table_btn = ToolButton(FluentIcon.ADD, self)
        self.new_table_btn.setFixedSize(24, 24)
        self.new_table_btn.setToolTip("新建表")
        self.new_table_btn.clicked.connect(self._on_create_table)
        self.new_table_btn.setEnabled(False)

        self.drop_table_btn = ToolButton(FluentIcon.DELETE, self)
        self.drop_table_btn.setFixedSize(24, 24)
        self.drop_table_btn.setToolTip("删除选中表")
        self.drop_table_btn.clicked.connect(self._on_drop_table)
        self.drop_table_btn.setEnabled(False)

        header.addWidget(self.table_count_label, 1)
        header.addWidget(self.refresh_btn)
        header.addWidget(self.new_table_btn)
        header.addWidget(self.drop_table_btn)
        layout.addLayout(header)

        self.search_edit = LineEdit(self)
        self.search_edit.setPlaceholderText("搜索表...")
        self.search_edit.setFixedHeight(26)
        self.search_edit.textChanged.connect(self._on_table_search)
        layout.addWidget(self.search_edit)

        self.table_list_container = QWidget()
        self.table_list_layout = QVBoxLayout(self.table_list_container)
        self.table_list_layout.setContentsMargins(0, 0, 0, 0)
        self.table_list_layout.setSpacing(2)
        self.table_list_layout.addStretch()

        scroll = ScrollArea(self)
        scroll.setWidget(self.table_list_container)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(scroll, 1)

        self.empty_table_label = CaptionLabel("暂无表\n\n点击 + 新建")
        self.empty_table_label.setAlignment(Qt.AlignCenter)
        self.empty_table_label.setStyleSheet(
            f"color: {'rgba(255,255,255,0.4)' if dark else 'rgba(0,0,0,0.4)'}; padding: 20px;"
        )
        layout.addWidget(self.empty_table_label)

        return widget

    def _create_data_panel(self):
        widget = QWidget()
        dark = isDarkTheme()

        bg_color = "#1E1E1E" if dark else "#FFFFFF"
        header_bg = "#2D2D2D" if dark else "#F0F0F0"
        border_color = "#3A3A3A" if dark else "#E0E0E0"
        text_color = "#E0E0E0" if dark else "#333333"
        alt_row = "#252525" if dark else "#F9F9F9"

        widget.setStyleSheet(f"""
            QWidget {{
                background: {bg_color};
            }}
            QLabel {{
                color: {text_color};
            }}
        """)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.data_header = CaptionLabel("请选择表")
        self.data_header.setStyleSheet(
            f"font-weight: bold; font-size: 14px; color: {text_color};"
        )
        layout.addWidget(self.data_header)

        self.command_bar = CommandBar()

        self.insert_action = Action(FluentIcon.ADD, "新增行", self)
        self.insert_action.triggered.connect(self._on_insert_data)
        self.insert_action.setEnabled(False)
        self.command_bar.addAction(self.insert_action)

        self.create_node_action = Action(get_icon("创建节点"), "创建插入节点", self)
        self.create_node_action.triggered.connect(self._on_create_insert_node)
        self.create_node_action.setEnabled(False)
        self.command_bar.addAction(self.create_node_action)
        self.command_bar.addSeparator()
        
        self.sql_action = Action(FluentIcon.CODE, "执行SQL", self)
        self.sql_action.triggered.connect(self._on_execute_sql)
        self.command_bar.addAction(self.sql_action)

        self.delete_action = Action(FluentIcon.DELETE, "删除行", self)
        self.delete_action.triggered.connect(self._on_delete_row)
        self.delete_action.setEnabled(False)
        self.command_bar.addAction(self.delete_action)

        self.export_action = Action(get_icon("导入"), "导出CSV", self)
        self.export_action.triggered.connect(self._on_export_csv)
        self.export_action.setEnabled(False)
        self.command_bar.addAction(self.export_action)

        self.refresh_action = Action(FluentIcon.SYNC, "刷新", self)
        self.refresh_action.triggered.connect(self._load_table_data)
        self.command_bar.addAction(self.refresh_action)

        self.insert_action.setVisible(False)
        self.create_node_action.setVisible(False)
        self.delete_action.setVisible(False)
        self.export_action.setVisible(False)

        layout.addWidget(self.command_bar)

        self.data_table = QTableWidget(self)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.data_table.verticalHeader().setVisible(True)
        self.data_table.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {border_color};
                background: {bg_color};
                alternate-background-color: {alt_row};
                color: {text_color};
                gridline-color: {border_color};
            }}
            QTableWidget::item {{
                padding: 4px;
                border-bottom: 1px solid {border_color};
            }}
            QTableWidget::item:selected {{
                background: rgba(64, 158, 255, 30%);
            }}
            QHeaderView::section {{
                background: {header_bg};
                color: {text_color};
                padding: 6px;
                border: 1px solid {border_color};
                font-weight: bold;
            }}
            QHeaderView::section:hover {{
                background: {"#3D3D3D" if dark else "#E5E5E5"};
            }}
            QScrollBar:vertical {{
                width: 8px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {"#555" if dark else "#BBB"};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {"#666" if dark else "#AAA"};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                height: 8px;
                background: transparent;
            }}
            QScrollBar::handle:horizontal {{
                background: {"#555" if dark else "#BBB"};
                border-radius: 4px;
                min-width: 20px;
            }}
        """)
        layout.addWidget(self.data_table, 1)

        self.row_count_label = CaptionLabel("")
        self.row_count_label.setStyleSheet(
            f"color: {'rgba(255,255,255,0.5)' if dark else 'rgba(0,0,0,0.5)'}; font-size: 12px;"
        )
        self.row_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.row_count_label)

        return widget

    def _refresh_tables(self):
        if not self.db_manager.is_connected:
            return
        tables = self.db_manager.get_tables()
        while self.table_list_layout.count() > 1:
            item = self.table_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.table_count_label.setText(f"表 ({len(tables)})")
        self.empty_table_label.setVisible(len(tables) == 0)

        dark = isDarkTheme()
        search_text = self.search_edit.text().lower()
        for table in tables:
            if search_text and search_text not in table.lower():
                continue
            btn = TableLabel(table, self)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda t=table: self._on_table_selected(t))
            btn.double_clicked.connect(lambda t=table: self._on_table_double_click(t))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, t=table: self._show_table_context_menu(pos, t)
            )
            self.table_list_layout.insertWidget(self.table_list_layout.count() - 1, btn)

    def _on_table_search(self, text):
        self._refresh_tables()

    def _on_table_double_click(self, table_name):
        self._on_table_selected(table_name)

    def _show_table_context_menu(self, pos, table_name):
        menu = QMenu(self)
        view_action = menu.addAction("查看数据")
        view_action.triggered.connect(lambda: self._on_table_selected(table_name))

        copy_action = menu.addAction("复制表名")
        copy_action.triggered.connect(
            lambda: QApplication.clipboard().setText(table_name)
        )

        menu.addSeparator()

        drop_action = menu.addAction("删除表")
        drop_action.triggered.connect(lambda: self._drop_table_by_name(table_name))

        menu.exec_(QCursor.pos())

    def _drop_table_by_name(self, table_name):
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除表 '{table_name}' 吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            success, msg = self.db_manager.drop_table(table_name)
            if success:
                InfoBar.success(
                    "删除成功", msg, position=InfoBarPosition.TOP, parent=self
                ).show()
                if self.current_table == table_name:
                    self.current_table = None
                    self.data_table.setRowCount(0)
                    self.data_table.setColumnCount(0)
                    self.data_header.setText("请选择表")
                self._refresh_tables()
            else:
                InfoBar.error(
                    "删除失败", msg, position=InfoBarPosition.TOP, parent=self
                ).show()

    def _on_table_selected(self, table_name):
        self.current_table = table_name
        self.drop_table_btn.setEnabled(True)
        self.insert_action.setVisible(True)
        self.create_node_action.setVisible(True)
        self.export_action.setVisible(True)
        self.insert_action.setEnabled(True)
        self.create_node_action.setEnabled(True)
        self.export_action.setEnabled(True)
        self._load_table_data()

        for i in range(self.table_list_layout.count() - 1):
            item = self.table_list_layout.itemAt(i)
            if item and item.widget():
                btn = item.widget()
                if isinstance(btn, TableLabel):
                    btn.setSelected(btn._table_name == table_name)

    def _load_table_data(self):
        if not self.current_table:
            return

        table_info = self.db_manager.get_table_info(self.current_table)
        col_count = len(table_info)

        # limit = self.limit_spin.value()
        columns, rows = self.db_manager.get_table_data(self.current_table, limit=500)
        total = self.db_manager.get_table_count(self.current_table)

        self.data_header.setText(f"表: {self.current_table}  ({col_count} 列)")
        self.row_count_label.setText(f"{len(rows)} / {total} 行")

        self.data_table.setColumnCount(len(columns))
        self.data_table.setRowCount(len(rows))
        self.data_table.setHorizontalHeaderLabels(columns)

        dark = isDarkTheme()
        null_color = "#888888" if dark else "#999999"

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                if val is None:
                    item = QTableWidgetItem("NULL")
                    item.setForeground(Qt.gray)
                else:
                    item = QTableWidgetItem(str(val))
                self.data_table.setItem(r, c, item)

        self.data_table.resizeColumnsToContents()
        self.delete_action.setEnabled(len(rows) > 0)
        self.delete_action.setVisible(len(rows) > 0)

    def _on_limit_changed(self):
        if self.current_table:
            self._load_table_data()

    def _on_export_csv(self):
        if not self.current_table:
            return

        columns, rows = self.db_manager.get_table_data(self.current_table, limit=999999)
        if not columns:
            InfoBar.warning(
                "导出失败", "没有数据可导出", position=InfoBarPosition.TOP, parent=self
            ).show()
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出CSV",
            f"{self.current_table}.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            import csv

            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            InfoBar.success(
                "导出成功",
                f"已导出到: {path}",
                position=InfoBarPosition.TOP,
                parent=self,
            ).show()
        except Exception as e:
            InfoBar.error(
                "导出失败", str(e), position=InfoBarPosition.TOP, parent=self
            ).show()

    def _on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择SQLite数据库",
            "",
            "SQLite Database (*.db *.sqlite *.sqlite3);;All Files (*)",
        )
        if path:
            self.path_edit.setText(path)

    def _on_connect(self):
        path = self.path_edit.text().strip()
        if not path:
            InfoBar.warning(
                "提示", "请输入数据库路径", position=InfoBarPosition.TOP, parent=self
            ).show()
            return

        try:
            self.db_manager.connect(path)
            self.close_btn.setEnabled(True)
            self.new_table_btn.setEnabled(True)
            self.refresh_btn.click()
            InfoBar.success(
                "连接成功", f"已连接: {path}", position=InfoBarPosition.TOP, parent=self
            ).show()
        except Exception as e:
            InfoBar.error(
                "连接失败", str(e), position=InfoBarPosition.TOP, parent=self
            ).show()

    def _on_close(self):
        self.db_manager.close()
        self.close_btn.setEnabled(False)
        self.new_table_btn.setEnabled(False)
        self.drop_table_btn.setEnabled(False)
        self.insert_action.setEnabled(False)
        self.create_node_action.setEnabled(False)
        self.delete_action.setEnabled(False)
        self.export_action.setEnabled(False)
        self.insert_action.setVisible(False)
        self.create_node_action.setVisible(False)
        self.delete_action.setVisible(False)
        self.export_action.setVisible(False)
        self.current_table = None
        self.data_header.setText("请选择表")
        self.data_table.setRowCount(0)
        self.data_table.setColumnCount(0)
        self.row_count_label.setText("")
        self.table_count_label.setText("表 (0)")
        while self.table_list_layout.count() > 1:
            item = self.table_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_create_table(self):
        dialog = CreateTableDialog(self.db_manager, self)
        dialog.exec()
        if dialog.accepted:
            self._refresh_tables()

    def _on_drop_table(self):
        if not self.current_table:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除表 '{self.current_table}' 吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            success, msg = self.db_manager.drop_table(self.current_table)
            if success:
                InfoBar.success(
                    "删除成功", msg, position=InfoBarPosition.TOP, parent=self
                ).show()
                self.current_table = None
                self.data_table.setRowCount(0)
                self.data_table.setColumnCount(0)
                self.data_header.setText("请选择表")
                self._refresh_tables()
            else:
                InfoBar.error(
                    "删除失败", msg, position=InfoBarPosition.TOP, parent=self
                ).show()

    def _on_insert_data(self):
        if not self.current_table:
            return
        dialog = InsertDataDialog(self.db_manager, self.current_table, self)
        dialog.exec()
        if dialog.accepted:
            self._load_table_data()

    def _on_create_insert_node(self):
        if not self.current_table:
            return
        self._create_sqlite_node(
            "sqlite套件/插入数据",
            {
                "database_path": self.db_manager.db_path,
                "table_name": self.current_table,
            },
        )

    def _create_sqlite_node(self, node_path, properties):
        homepage = getattr(self, "homepage", None)
        if not homepage:
            return
        graph = getattr(homepage, "graph", None)
        if not graph:
            return
        viewer = getattr(graph, "graph_splitter", None)
        if not viewer:
            return
        active_viewer = viewer.get_active_viewer()
        if not active_viewer:
            return
        scene_pos = active_viewer.mapToScene(active_viewer.viewport().rect().center())
        node = active_viewer._create_node_with_properties(
            node_path, properties, scene_pos
        )
        if node:
            InfoBar.success(
                "创建成功",
                f"已创建 {node_path.split('/')[-1]} 节点",
                position=InfoBarPosition.TOP,
                parent=self,
            ).show()

    def _on_delete_row(self):
        if not self.current_table:
            return
        selected_rows = self.data_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_rows)} 行吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            primary_cols = [
                col
                for col in self.db_manager.get_table_info(self.current_table)
                if col["pk"]
            ]
            if not primary_cols:
                InfoBar.warning(
                    "无法删除",
                    "表没有主键，无法确定删除行",
                    position=InfoBarPosition.TOP,
                    parent=self,
                ).show()
                return

            pk_col = primary_cols[0]["name"]
            pk_idx = self._get_column_index(pk_col)
            if pk_idx < 0:
                InfoBar.error(
                    "错误",
                    f"找不到主键列 '{pk_col}'",
                    position=InfoBarPosition.TOP,
                    parent=self,
                ).show()
                return

            deleted_count = 0
            for index_row in sorted(selected_rows, key=lambda x: x.row(), reverse=True):
                row = index_row.row()
                item = self.data_table.item(row, pk_idx)
                if item is None:
                    continue
                pk_val = item.text()
                success, msg = self.db_manager.delete_data(
                    self.current_table, f'"{pk_col}" = ?', (pk_val,)
                )
                if success:
                    deleted_count += 1

            self._load_table_data()
            if deleted_count > 0:
                InfoBar.success(
                    "删除成功",
                    f"已删除 {deleted_count} 行",
                    position=InfoBarPosition.TOP,
                    parent=self,
                ).show()
            else:
                InfoBar.warning(
                    "删除失败",
                    "未能删除任何行",
                    position=InfoBarPosition.TOP,
                    parent=self,
                ).show()

    def _get_column_index(self, col_name):
        for i in range(self.data_table.columnCount()):
            if self.data_table.horizontalHeaderItem(i).text() == col_name:
                return i
        return -1

    def _on_execute_sql(self):
        dialog = ExecuteSqlDialog(self.db_manager, self)
        dialog.exec()


class CreateTableDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.accepted = False
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("创建表")
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)

        dark = isDarkTheme()
        bg_color = "#2D2D2D" if dark else "#FFFFFF"
        text_color = "#E0E0E0" if dark else "#333333"
        border_color = "#3A3A3A" if dark else "#E0E0E0"
        input_bg = "#1E1E1E" if dark else "#FFFFFF"
        list_bg = "#252525" if dark else "#F8F8F8"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
            }}
            QLabel {{
                color: {text_color};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("表名:"))
        self.table_name_edit = LineEdit(self)
        self.table_name_edit.setPlaceholderText("输入表名")
        name_layout.addWidget(self.table_name_edit, 1)
        layout.addLayout(name_layout)

        col_label = QLabel("列定义:")
        layout.addWidget(col_label)

        from qfluentwidgets import ListWidget

        self.columns_list = ListWidget(self)
        self.columns_list.setMinimumHeight(280)
        self.columns_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {list_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
            QListWidget::item {{
                padding: 0px;
                border: none;
            }}
        """)
        layout.addWidget(self.columns_list, 1)

        btn_row = QHBoxLayout()
        add_btn = PushButton("+ 添加列", self)
        add_btn.clicked.connect(lambda: self._add_column_row())
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        action_btn_row = QHBoxLayout()
        self.create_btn = PrimaryPushButton("创建表", self)
        self.create_btn.clicked.connect(self._on_create)
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        action_btn_row.addStretch()
        action_btn_row.addWidget(self.create_btn)
        action_btn_row.addWidget(cancel_btn)
        layout.addLayout(action_btn_row)

        self._add_column_row()

    def _add_column_row(self, name="", col_type="TEXT", is_pk=False, is_nn=False):
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(8, 6, 8, 6)
        item_layout.setSpacing(10)

        dark = isDarkTheme()
        input_bg = "#1E1E1E" if dark else "#FFFFFF"
        text_color = "#E0E0E0" if dark else "#333333"
        border_color = "#3A3A3A" if dark else "#E0E0E0"

        name_edit = LineEdit(self.columns_list)
        name_edit.setText(name)
        name_edit.setPlaceholderText("列名")
        name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)

        type_combo = ComboBox(self.columns_list)
        type_combo.addItems(["TEXT", "INTEGER", "REAL", "BLOB"])
        type_combo.setCurrentText(col_type)
        type_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)

        pk_btn = QPushButton("主键", self.columns_list)
        pk_btn.setCheckable(True)
        pk_btn.setChecked(is_pk)
        pk_btn.setFixedWidth(60)
        pk_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {"#4095ff" if is_pk else "#3A3A3A"};
                color: white if {is_pk} else {text_color};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QPushButton:checked {{
                background-color: #4095ff;
                color: white;
            }}
        """)
        pk_btn.clicked.connect(lambda: self._update_pk_style(pk_btn))

        nn_btn = QPushButton("非空", self.columns_list)
        nn_btn.setCheckable(True)
        nn_btn.setChecked(is_nn)
        nn_btn.setFixedWidth(60)
        nn_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {"#4095ff" if is_nn else "#3A3A3A"};
                color: white if {is_nn} else {text_color};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QPushButton:checked {{
                background-color: #4095ff;
                color: white;
            }}
        """)
        nn_btn.clicked.connect(lambda: self._update_nn_style(nn_btn))

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self.columns_list)
        delete_btn.clicked.connect(lambda: self._remove_column_row(item_widget))

        item_layout.addWidget(name_edit, 1)
        item_layout.addWidget(type_combo, 0)
        item_layout.addWidget(pk_btn, 0)
        item_layout.addWidget(nn_btn, 0)
        item_layout.addWidget(delete_btn, 0)

        list_item = QListWidgetItem(self.columns_list)
        list_item.setSizeHint(item_widget.sizeHint())
        self.columns_list.setItemWidget(list_item, item_widget)
        item_widget._list_item = list_item

    def _update_pk_style(self, btn):
        dark = isDarkTheme()
        if btn.isChecked():
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #4095ff;
                    color: white;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
            """)
        else:
            text_color = "#E0E0E0" if dark else "#333333"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #3A3A3A;
                    color: {text_color};
                    border-radius: 4px;
                    padding: 4px 8px;
                }}
            """)

    def _update_nn_style(self, btn):
        dark = isDarkTheme()
        if btn.isChecked():
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #4095ff;
                    color: white;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
            """)
        else:
            text_color = "#E0E0E0" if dark else "#333333"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #3A3A3A;
                    color: {text_color};
                    border-radius: 4px;
                    padding: 4px 8px;
                }}
            """)

    def _remove_column_row(self, item_widget):
        if self.columns_list.count() <= 1:
            return
        list_item = item_widget._list_item
        row = self.columns_list.row(list_item)
        self.columns_list.takeItem(row)
        item_widget.deleteLater()

    def _get_column_data(self, item_widget):
        layout = item_widget.layout()
        name_edit = layout.itemAt(0).widget()
        type_combo = layout.itemAt(1).widget()
        pk_btn = layout.itemAt(2).widget()
        nn_btn = layout.itemAt(3).widget()
        return {
            "name": name_edit.text().strip(),
            "type": type_combo.currentText(),
            "primary_key": pk_btn.isChecked(),
            "not_null": nn_btn.isChecked(),
        }

    def _on_create(self):
        table_name = self.table_name_edit.text().strip()
        if not table_name or not table_name.isidentifier():
            InfoBar.warning(
                "错误", "请输入有效的表名", position=InfoBarPosition.TOP, parent=self
            ).show()
            return

        columns = []
        for i in range(self.columns_list.count()):
            item_widget = self.columns_list.itemWidget(self.columns_list.item(i))
            if item_widget:
                col_data = self._get_column_data(item_widget)
                if col_data["name"]:
                    columns.append(col_data)

        if not columns:
            InfoBar.warning(
                "错误", "至少需要定义一个列", position=InfoBarPosition.TOP, parent=self
            ).show()
            return

        success, msg = self.db_manager.create_table(table_name, columns)
        if not success:
            InfoBar.error(
                "创建失败", msg, position=InfoBarPosition.TOP, parent=self
            ).show()
            return

        InfoBar.success(
            "成功",
            f"表 '{table_name}' 已创建",
            position=InfoBarPosition.TOP,
            parent=self,
        ).show()
        self.accepted = True
        self.accept()


class InsertDataDialog(QDialog):
    def __init__(self, db_manager, table_name, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.table_name = table_name
        self.accepted = False
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(f"插入数据 - {self.table_name}")
        self.setMinimumWidth(450)

        dark = isDarkTheme()
        bg_color = "#2D2D2D" if dark else "#FFFFFF"
        text_color = "#E0E0E0" if dark else "#333333"
        border_color = "#3A3A3A" if dark else "#E0E0E0"
        input_bg = "#1E1E1E" if dark else "#FFFFFF"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
            }}
            QLabel {{
                color: {text_color};
                padding: 4px 0;
            }}
            QLineEdit {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 6px 10px;
            }}
            QLineEdit:focus {{
                border: 1px solid #4095ff;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.columns_info = self.db_manager.get_table_info(self.table_name)
        self.edits = {}

        for col in self.columns_info:
            row_layout = QHBoxLayout()
            label = QLabel(col["name"])
            label.setFixedWidth(100)
            label.setStyleSheet(f"color: {text_color};")
            edit = LineEdit(self)
            placeholder = col["type"]
            if col["pk"]:
                placeholder += " (主键)"
            elif col["notnull"]:
                placeholder += " (必填)"
            edit.setPlaceholderText(placeholder)
            self.edits[col["name"]] = edit
            row_layout.addWidget(label)
            row_layout.addWidget(edit, 1)
            layout.addLayout(row_layout)

        btn_layout = QHBoxLayout()
        self.insert_btn = PrimaryPushButton("插入", self)
        self.insert_btn.setFixedWidth(100)
        self.insert_btn.clicked.connect(self._on_insert)
        cancel_btn = PushButton("取消", self)
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.insert_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_insert(self):
        data = {}
        for col in self.columns_info:
            val = self.edits[col["name"]].text().strip()
            if col["pk"] and not val:
                InfoBar.warning(
                    "错误",
                    f"主键 '{col['name']}' 不能为空",
                    position=InfoBarPosition.TOP,
                    parent=self,
                ).show()
                return
            if val:
                if col["type"] == "INTEGER":
                    try:
                        data[col["name"]] = int(val)
                    except:
                        data[col["name"]] = val
                elif col["type"] == "REAL":
                    try:
                        data[col["name"]] = float(val)
                    except:
                        data[col["name"]] = val
                else:
                    data[col["name"]] = val

        success, msg = self.db_manager.insert_data(self.table_name, data)
        if not success:
            InfoBar.error(
                "插入失败", msg, position=InfoBarPosition.TOP, parent=self
            ).show()
            return

        InfoBar.success(
            "成功", "数据已插入", position=InfoBarPosition.TOP, parent=self
        ).show()
        self.accepted = True
        self.accept()


class ExecuteSqlDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("执行 SQL")
        self.setMinimumWidth(550)
        self.setMinimumHeight(350)

        dark = isDarkTheme()
        bg_color = "#2D2D2D" if dark else "#FFFFFF"
        text_color = "#E0E0E0" if dark else "#333333"
        border_color = "#3A3A3A" if dark else "#E0E0E0"
        input_bg = "#1E1E1E" if dark else "#FFFFFF"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
            }}
            QLabel {{
                color: {text_color};
            }}
            QTextEdit {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 8px;
            }}
        """)

        from qfluentwidgets import TextEdit

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.sql_edit = TextEdit(self)
        self.sql_edit.setPlaceholderText(
            "输入 SQL 语句，如: SELECT * FROM users LIMIT 10"
        )
        self.sql_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 8px;
                font-family: Consolas, monospace;
            }}
        """)
        layout.addWidget(self.sql_edit, 1)

        self.result_edit = TextEdit(self)
        self.result_edit.setReadOnly(True)
        self.result_edit.setMaximumHeight(120)
        self.result_edit.setPlaceholderText("执行结果...")
        self.result_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 8px;
                font-family: Consolas, monospace;
            }}
        """)
        layout.addWidget(self.result_edit)

        btn_layout = QHBoxLayout()
        self.exec_btn = PrimaryPushButton("执行", self)
        self.exec_btn.setFixedWidth(100)
        self.exec_btn.clicked.connect(self._on_execute)
        close_btn = PushButton("关闭", self)
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.exec_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _on_execute(self):
        sql = self.sql_edit.toPlainText().strip()
        if not sql:
            return

        success, result = self.db_manager.execute_sql(sql)
        if success:
            if isinstance(result, list):
                self.result_edit.setPlainText(f"成功: 返回 {len(result)} 行")
            else:
                self.result_edit.setPlainText(f"成功: {result}")
        else:
            self.result_edit.setPlainText(f"错误: {result}")
