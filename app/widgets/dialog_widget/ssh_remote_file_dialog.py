import os
import stat
import posixpath
from datetime import datetime
from pathlib import Path

import paramiko
from Qt import QtWidgets, QtCore, QtGui
from Qt.QtWidgets import QHeaderView, QTableWidgetItem, QMenu, QAction, QFileDialog, QMessageBox, QProgressDialog
from qfluentwidgets import (
    LineEdit, FluentIcon, ToolButton, TableWidget, BodyLabel, PrimaryPushButton,
    PushButton, ListWidget, InfoBar, InfoBarPosition, StateToolTip
)

from app.utils.utils import get_icon


class SSFTSession:
    """管理 SFTP 连接和数据获取 - 增强错误处理和路径兼容性"""

    def __init__(self, env_data):
        self.env_data = env_data
        self.ssh = None
        self.sftp = None
        self.connected = False

    def connect(self):
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.env_data.get('host'),
                port=int(self.env_data.get('port', 22)),
                username=self.env_data.get('user'),
                password=self.env_data.get('pwd'),
                timeout=10
            )
            self.sftp = self.ssh.open_sftp()
            self.connected = True
            return True
        except Exception as e:
            raise ConnectionError(f"SSH 连接失败: {str(e)}")

    def list_dir_info(self, path):
        """获取目录下所有文件的详细信息 - 增强错误处理"""
        if not self.connected:
            raise ConnectionError("SFTP 会话未连接")

        # 标准化路径（确保为 POSIX 格式）
        path = posixpath.normpath(path)
        if not path.startswith('/'):
            path = '/' + path

        results = []
        try:
            for entry in self.sftp.listdir_attr(path):
                # 跳过特殊目录
                if entry.filename in ('.', '..'):
                    continue

                is_dir = stat.S_ISDIR(entry.st_mode)
                results.append({
                    "name": entry.filename,
                    "is_dir": is_dir,
                    "size": entry.st_size if not is_dir else 0,
                    "mtime": datetime.fromtimestamp(entry.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    "path": posixpath.join(path, entry.filename)
                })
            # 排序：文件夹在前，按名称排序（. 开头的文件排最后）
            results.sort(key=lambda x: (
                not x['is_dir'],
                x['name'].startswith('.'),
                x['name'].lower()
            ))
            return results
        except FileNotFoundError:
            raise FileNotFoundError(f"目录不存在: {path}")
        except PermissionError:
            raise PermissionError(f"无权访问目录: {path}")
        except Exception as e:
            raise RuntimeError(f"读取目录失败: {str(e)}")

    def make_dir(self, path):
        """创建远程目录"""
        try:
            self.sftp.mkdir(path)
            return True
        except Exception as e:
            raise RuntimeError(f"创建目录失败: {str(e)}")

    def remove_file(self, path):
        """删除远程文件"""
        try:
            self.sftp.remove(path)
            return True
        except Exception as e:
            raise RuntimeError(f"删除文件失败: {str(e)}")

    def remove_dir(self, path):
        """递归删除远程目录"""
        try:
            # 先删除目录内所有内容
            for entry in self.sftp.listdir_attr(path):
                if entry.filename in ('.', '..'):
                    continue
                full_path = posixpath.join(path, entry.filename)
                if stat.S_ISDIR(entry.st_mode):
                    self.remove_dir(full_path)
                else:
                    self.sftp.remove(full_path)
            self.sftp.rmdir(path)
            return True
        except Exception as e:
            raise RuntimeError(f"删除目录失败: {str(e)}")

    def rename(self, old_path, new_path):
        """重命名/移动文件或目录"""
        try:
            self.sftp.posix_rename(old_path, new_path)
            return True
        except Exception as e:
            raise RuntimeError(f"重命名失败: {str(e)}")

    def upload_file(self, local_path, remote_path, progress_callback=None):
        """上传文件 - 支持进度回调"""
        try:
            self.sftp.put(local_path, remote_path, callback=progress_callback)
            return True
        except Exception as e:
            raise RuntimeError(f"上传失败: {str(e)}")

    def download_file(self, remote_path, local_path, progress_callback=None):
        """下载文件 - 支持进度回调"""
        try:
            self.sftp.get(remote_path, local_path, callback=progress_callback)
            return True
        except Exception as e:
            raise RuntimeError(f"下载失败: {str(e)}")

    def close(self):
        if self.sftp:
            try:
                self.sftp.close()
            except:
                pass
        if self.ssh:
            try:
                self.ssh.close()
            except:
                pass
        self.connected = False


class PathBreadcrumbWidget(QtWidgets.QWidget):
    """面包屑路径导航控件 - MobaXterm 风格"""
    pathClicked = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.path_segments = []

    def setPath(self, path):
        # 清除旧控件
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.path_segments = []
        segments = [p for p in path.split('/') if p]
        current_path = '/'

        # 添加根目录
        self._add_segment('/', '/', is_first=True)

        # 添加各级目录
        for i, seg in enumerate(segments):
            current_path = posixpath.join(current_path, seg)
            is_last = (i == len(segments) - 1)
            self._add_segment(seg, current_path, is_last=is_last)

    def _add_segment(self, text, path, is_first=False, is_last=False):
        if not is_first:
            # 添加分隔符
            sep = QtWidgets.QLabel('>')
            sep.setStyleSheet("color: #666; font-size: 10px;")
            self.layout.addWidget(sep)

        btn = QtWidgets.QPushButton(text)
        btn.setFlat(True)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setProperty('path', path)

        if is_last:
            btn.setStyleSheet("""
                QPushButton {
                    color: #4ec9b0;
                    font-weight: bold;
                    background: transparent;
                    border: none;
                    padding: 2px 4px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    color: #888;
                    background: transparent;
                    border: none;
                    padding: 2px 4px;
                }
                QPushButton:hover {
                    color: #4ec9b0;
                    text-decoration: underline;
                }
            """)

        btn.clicked.connect(lambda: self.pathClicked.emit(path))
        self.layout.addWidget(btn)
        self.path_segments.append((text, path))


class SSHRemoteFileDialog(QtWidgets.QDialog):
    def __init__(self, env_data, selection_mode="file", file_filter="*", parent=None, initial_path=None):
        """
        selection_mode:
            - "file": 只能选择文件
            - "folder": 只能选择文件夹
            - "any": 文件和文件夹都可以选择
        initial_path: 初始路径（可选），如果未提供则使用env_data中的workdir
        """
        super().__init__(parent)
        self.env_data = env_data
        self.selection_mode = selection_mode
        self.session = SSFTSession(env_data)
        self.current_path = (initial_path or env_data.get('workdir', '/')).rstrip('/') or '/'
        self.last_selected_path = None
        self.state_tooltip = None

        self.setWindowTitle(f"远程文件浏览器 - {env_data.get('host', 'unknown')}")
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)

        self.setStyleSheet("""
            QDialog { background-color: #272727; }
            QWidget { background-color: #272727; color: #E0E0E0; font-family: 'Segoe UI', 'Microsoft YaHei', 'PingFang SC'; font-size: 13px; }
            QTableWidget { 
                border: 1px solid #333; 
                background-color: #2d2d2d; 
                gridline-color: #333; 
                alternate-background-color: #2a2a2a;
            }
            QTableWidget::item:selected {
                background-color: #3a5a7a;
                color: #ffffff;
            }
            QHeaderView::section { 
                background-color: #333; 
                color: #AAA; 
                padding: 6px; 
                border: none; 
                border-right: 1px solid #444;
            }
            QListWidget { 
                background-color: #2d2d2d; 
                border: none; 
                border-right: 1px solid #333; 
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #3a5a7a;
                color: #ffffff;
            }
            QProgressBar {
                border: 1px solid #444;
                border-radius: 3px;
                text-align: center;
                background-color: #2a2a2a;
            }
            QProgressBar::chunk {
                background-color: #4ec9b0;
                width: 10px;
            }
        """)

        self._setup_ui()
        self._init_connection()

    def _setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== 侧边栏 =====
        self.side_bar = ListWidget()
        self.side_bar.setFixedWidth(180)
        self.side_bar.setStyleSheet("""
            QListWidget { background-color: #252525; border-right: 1px solid #333; }
            QListWidget::item { padding: 8px 12px; border-radius: 4px; margin: 2px 4px; }
            QListWidget::item:selected { background-color: #3a5a7a; }
        """)
        self._add_shortcut("工作目录", os.path.dirname(self.env_data.get('path', '/').rstrip('/') or '/'), FluentIcon.HOME)
        self._add_shortcut("根目录", "/", FluentIcon.FOLDER)
        self._add_shortcut("用户目录", f"/home/", FluentIcon.PEOPLE)
        self.side_bar.itemClicked.connect(lambda it: self._load_path(it.data(QtCore.Qt.UserRole)))
        main_layout.addWidget(self.side_bar)

        # ===== 右侧主区域 =====
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(12)

        # ----- 顶部工具栏 -----
        top_bar = QtWidgets.QHBoxLayout()

        # 返回/前进/刷新按钮
        self.btn_back = ToolButton(get_icon("返回上级目录"))
        self.btn_back.setToolTip("上一级目录 (Alt+↑)")
        self.btn_back.setShortcut("Alt+Up")
        self.btn_back.clicked.connect(self._go_up)

        self.btn_refresh = ToolButton(get_icon("Sync"))
        self.btn_refresh.setToolTip("刷新 (F5)")
        self.btn_refresh.setShortcut("F5")
        self.btn_refresh.clicked.connect(lambda: self._load_path(self.current_path))

        # 面包屑导航
        self.breadcrumb = PathBreadcrumbWidget()
        self.breadcrumb.pathClicked.connect(self._load_path)

        # 路径输入框（带自动补全）
        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText("输入远程路径或使用面包屑导航...")
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.returnPressed.connect(self._on_path_entered)
        self.path_edit.installEventFilter(self)  # 用于ESC清除

        top_bar.addWidget(self.btn_back)
        top_bar.addWidget(self.btn_refresh)
        top_bar.addWidget(self.breadcrumb)
        top_bar.addWidget(self.path_edit, 1)
        right_layout.addLayout(top_bar)

        # ----- 文件表格 -----
        self.table = TableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["名称", "大小", "修改日期", "权限"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # 支持多选
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.setSortingEnabled(True)  # 启用排序功能

        # 双击/回车打开
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.keyPressEvent = self._table_key_press  # 重写键盘事件

        # 表头设置 - 关键优化：实现表格铺展和排序
        self.header = self.table.horizontalHeader()
        self.header.setHighlightSections(False)
        self.header.setSectionsClickable(True)  # 允许点击排序
        self.header.setSortIndicatorShown(True)  # 显示排序指示器
        self.header.setSortIndicator(0, QtCore.Qt.AscendingOrder)  # 默认按名称升序
        self.header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

        # 列宽策略：名称列自动拉伸填充剩余空间，其他列固定宽度
        self.header.setSectionResizeMode(0, QHeaderView.Stretch)  # 名称列拉伸
        self.header.setSectionResizeMode(1, QHeaderView.Fixed)  # 大小列固定
        self.header.setSectionResizeMode(2, QHeaderView.Fixed)  # 日期列固定
        self.header.setSectionResizeMode(3, QHeaderView.Fixed)  # 权限列固定

        # 设置固定列的宽度
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 100)

        right_layout.addWidget(self.table)

        # ----- 底部状态栏 -----
        bottom_bar = QtWidgets.QHBoxLayout()
        self.status_label = BodyLabel("就绪")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")

        self.selection_label = BodyLabel("未选择")
        self.selection_label.setStyleSheet("color: #4ec9b0; font-size: 12px; font-weight: bold;")

        # 按钮区域
        btn_widget = QtWidgets.QWidget()
        btn_layout = QtWidgets.QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        self.btn_upload = PushButton("上传", self, get_icon("upload"))
        self.btn_upload.clicked.connect(self._upload_files)

        self.btn_new_folder = PushButton("新建文件夹", self, FluentIcon.ADD)
        self.btn_new_folder.clicked.connect(self._create_new_folder)

        self.btn_ok = PrimaryPushButton("确定")
        self.btn_cancel = PushButton("取消")

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_upload)
        btn_layout.addWidget(self.btn_new_folder)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)

        bottom_bar.addWidget(self.status_label)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.selection_label)
        bottom_bar.addWidget(btn_widget)
        right_layout.addLayout(bottom_bar)

        main_layout.addWidget(right_widget)

        # 设置默认焦点到表格
        self.table.setFocus()

    def _add_shortcut(self, name, path, icon):
        item = QtWidgets.QListWidgetItem(icon.icon(), name)
        item.setData(QtCore.Qt.UserRole, path.rstrip('/') or '/')
        item.setSizeHint(QtCore.QSize(160, 32))
        self.side_bar.addItem(item)
        if path.rstrip('/') == self.current_path.rstrip('/'):
            self.side_bar.setCurrentItem(item)

    def _init_connection(self):
        try:
            self.session.connect()
            self._load_path(self.current_path)
            self.status_label.setText(f"✓ 已连接到 {self.env_data.get('host')}")
        except Exception as e:
            InfoBar.error(
                title="连接失败",
                content=str(e),
                orient=QtCore.Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self
            )
            QtCore.QTimer.singleShot(0, self.reject)

    def _load_path(self, path):
        """异步加载目录内容"""
        if not path or not path.startswith('/'):
            path = '/'

        path = posixpath.normpath(path)
        self._show_loading(True, f"加载 {path} ...")

        # 更新UI状态
        self.current_path = path
        self.path_edit.setText(path)
        self.breadcrumb.setPath(path)
        self.setWindowTitle(f"远程文件浏览器 - {path}")

        # 重置选择状态
        if self.selection_mode in ["folder", "any"]:
            self.last_selected_path = self.current_path
            self.selection_label.setText(self.current_path)

        # 异步加载（避免UI卡顿）
        QtCore.QTimer.singleShot(10, lambda: self._async_load_path(path))

    def _async_load_path(self, path):
        try:
            files = self.session.list_dir_info(path)

            # 更新表格
            self.table.setRowCount(0)
            for f in files:
                row = self.table.rowCount()
                self.table.insertRow(row)

                # 图标和名称
                icon = FluentIcon.FOLDER if f['is_dir'] else FluentIcon.DOCUMENT
                name_item = QTableWidgetItem(icon.icon(), f['name'])
                name_item.setData(QtCore.Qt.UserRole, f)
                name_item.setToolTip(f['path'])

                # 大小
                if f['is_dir']:
                    size_item = QTableWidgetItem("📁")
                    size_item.setTextAlignment(QtCore.Qt.AlignCenter)
                else:
                    size = f['size']
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / 1024 / 1024:.1f} MB"
                    size_item = QTableWidgetItem(size_str)
                    size_item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

                # 修改日期
                date_item = QTableWidgetItem(f['mtime'])

                # 权限（简化显示）
                perm_item = QTableWidgetItem("drwxr-xr-x" if f['is_dir'] else "-rw-r--r--")
                perm_item.setFont(QtGui.QFont("Courier New", 9))
                perm_item.setForeground(QtGui.QColor("#6a9955"))

                self.table.setItem(row, 0, name_item)
                self.table.setItem(row, 1, size_item)
                self.table.setItem(row, 2, date_item)
                self.table.setItem(row, 3, perm_item)

            # 更新状态
            item_count = len(files)
            dir_count = sum(1 for f in files if f['is_dir'])
            file_count = item_count - dir_count
            self.status_label.setText(f"📁 {dir_count} 个文件夹, 📄 {file_count} 个文件")

            # 保持侧边栏选中状态
            for i in range(self.side_bar.count()):
                item = self.side_bar.item(i)
                if item.data(QtCore.Qt.UserRole).rstrip('/') == path.rstrip('/'):
                    self.side_bar.setCurrentItem(item)
                    break

        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取目录失败:\n{str(e)}")
            self.status_label.setText(f"✗ 错误: {str(e)}")
        finally:
            self._show_loading(False)

    def _show_loading(self, show, message="加载中..."):
        """显示/隐藏加载状态"""
        if show:
            if self.state_tooltip is None:
                self.state_tooltip = StateToolTip(message, "", self)
                self.state_tooltip.move(self.width() - self.state_tooltip.width() - 30, 30)
            self.state_tooltip.setTitle(message)
            self.state_tooltip.show()
        elif self.state_tooltip:
            self.state_tooltip.close()
            self.state_tooltip = None

    def _on_path_entered(self):
        """路径输入框回车处理"""
        path = self.path_edit.text().strip()
        if path:
            # 支持相对路径
            if not path.startswith('/'):
                path = posixpath.join(self.current_path, path)
            self._load_path(path)

    def eventFilter(self, obj, event):
        """事件过滤器 - 处理ESC清除路径输入"""
        if obj == self.path_edit and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Escape:
                self.path_edit.setText(self.current_path)
                self.path_edit.clearFocus()
                return True
        return super().eventFilter(obj, event)

    def _table_key_press(self, event):
        """表格键盘事件处理"""
        if event.key() == QtCore.Qt.Key_Return or event.key() == QtCore.Qt.Key_Enter:
            current = self.table.currentItem()
            if current:
                self._on_item_double_clicked(current)
        elif event.key() == QtCore.Qt.Key_Backspace:
            self._go_up()
        elif event.key() == QtCore.Qt.Key_F5:
            self._load_path(self.current_path)
        else:
            QtWidgets.QTableWidget.keyPressEvent(self.table, event)

    def _go_up(self):
        """返回上级目录"""
        if self.current_path == '/':
            return
        parent = posixpath.dirname(self.current_path.rstrip('/'))
        if not parent or parent == '.':
            parent = '/'
        self._load_path(parent)

    def _on_item_clicked(self, item):
        """单击选择处理 - 根据选择模式更新状态"""
        row = item.row()
        data = self.table.item(row, 0).data(QtCore.Qt.UserRole)

        if not data:
            return

        # 多选处理
        selected_items = self.table.selectedItems()
        if len(selected_items) > 1:
            # 多选时显示数量
            rows = set(item.row() for item in selected_items)
            self.selection_label.setText(f"已选择 {len(rows)} 项")
            self.last_selected_path = None
            return

        # 单选逻辑
        if self.selection_mode == "any":
            self.last_selected_path = data['path']
            self.selection_label.setText(data['path'])

        elif self.selection_mode == "folder":
            if data['is_dir']:
                self.last_selected_path = data['path']
                self.selection_label.setText(data['path'])
            else:
                self.last_selected_path = self.current_path
                self.selection_label.setText(f"📁 {self.current_path} (文件夹模式)")

        elif self.selection_mode == "file":
            if not data['is_dir']:
                self.last_selected_path = data['path']
                self.selection_label.setText(data['path'])
            else:
                self.last_selected_path = None
                self.selection_label.setText("⚠ 请选择文件")

    def _on_item_double_clicked(self, item):
        """双击处理 - 进入目录或选择文件"""
        row = item.row()
        data = self.table.item(row, 0).data(QtCore.Qt.UserRole)

        if not data:
            return

        if data['is_dir']:
            self._load_path(data['path'])
        else:
            # 文件双击：在 file/any 模式下直接确认
            if self.selection_mode in ["file", "any"]:
                self.last_selected_path = data['path']
                self.accept()

    def _show_context_menu(self, position):
        """显示右键菜单 - 上下文感知"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                border: 1px solid #444;
                padding: 8px;
                font-size: 13px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3a5a7a;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 4px 0;
            }
        """)

        # 获取点击位置的item
        item = self.table.itemAt(position)
        selected_items = self.table.selectedItems()
        rows = set(item.row() for item in selected_items if item) if selected_items else set()

        # 空白区域点击
        if item is None:
            self._build_empty_area_menu(menu)
        # 单个item
        elif len(rows) <= 1:
            data = self.table.item(item.row(), 0).data(QtCore.Qt.UserRole)
            if data:
                self._build_item_menu(menu, data, is_dir=data['is_dir'])
        # 多选
        else:
            self._build_multi_selection_menu(menu, rows)

        # 添加通用操作
        menu.addSeparator()
        refresh_action = QAction(FluentIcon.SYNC.icon(), "刷新 (F5)", self)
        refresh_action.triggered.connect(lambda: self._load_path(self.current_path))
        menu.addAction(refresh_action)

        menu.exec_(self.table.mapToGlobal(position))

    def _build_empty_area_menu(self, menu):
        """构建空白区域菜单"""
        new_folder = QAction(FluentIcon.ADD.icon(), "新建文件夹...", self)
        new_folder.triggered.connect(self._create_new_folder)
        menu.addAction(new_folder)

        upload = QAction(get_icon("upload"), "上传文件...", self)
        upload.triggered.connect(self._upload_files)
        menu.addAction(upload)

        upload_folder = QAction(FluentIcon.FOLDER_ADD.icon(), "上传文件夹...", self)
        upload_folder.triggered.connect(self._upload_folder)
        menu.addAction(upload_folder)

    def _build_item_menu(self, menu, data, is_dir):
        """构建单个item菜单"""
        # 打开/进入
        if is_dir:
            open_action = QAction(FluentIcon.FOLDER.icon(), "打开", self)
            open_action.triggered.connect(lambda: self._load_path(data['path']))
            menu.addAction(open_action)
        else:
            open_action = QAction(FluentIcon.DOCUMENT.icon(), "打开", self)
            # 这里可以集成远程编辑功能（预留）
            menu.addAction(open_action)
            menu.addSeparator()

            download = QAction(FluentIcon.DOWNLOAD.icon(), "下载...", self)
            download.triggered.connect(lambda: self._download_file(data['path']))
            menu.addAction(download)

        menu.addSeparator()

        # 重命名
        rename = QAction(FluentIcon.EDIT.icon(), "重命名...", self)
        rename.triggered.connect(lambda: self._rename_item(data['path'], data['name'], is_dir))
        menu.addAction(rename)

        # 复制路径
        copy_path = QAction(FluentIcon.COPY.icon(), "复制路径", self)
        copy_path.triggered.connect(lambda: self._copy_path(data['path']))
        menu.addAction(copy_path)

        menu.addSeparator()

        # 删除
        delete = QAction(FluentIcon.DELETE.icon(), "删除", self)
        delete.triggered.connect(lambda: self._delete_item(data['path'], data['name'], is_dir))
        delete.setIconVisibleInMenu(True)
        menu.addAction(delete)

    def _build_multi_selection_menu(self, menu, rows):
        """构建多选菜单"""
        menu.addAction("⚠ 多选操作 (开发中)").setEnabled(False)
        menu.addSeparator()

        download = QAction(FluentIcon.DOWNLOAD.icon(), "批量下载...", self)
        download.setEnabled(False)  # 暂未实现
        menu.addAction(download)

        delete = QAction(FluentIcon.DELETE.icon(), "批量删除...", self)
        delete.setEnabled(False)  # 暂未实现
        menu.addAction(delete)

    def _create_new_folder(self):
        """创建新文件夹"""
        folder_name, ok = QtWidgets.QInputDialog.getText(
            self, "新建文件夹", "文件夹名称:",
            QtWidgets.QLineEdit.Normal, "新建文件夹"
        )
        if ok and folder_name.strip():
            try:
                new_path = posixpath.join(self.current_path, folder_name.strip())
                self.session.make_dir(new_path)
                self._load_path(self.current_path)
                InfoBar.success(
                    title="成功",
                    content=f"文件夹创建成功: {folder_name}",
                    orient=QtCore.Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self
                )
            except Exception as e:
                QMessageBox.warning(self, "错误", f"创建文件夹失败:\n{str(e)}")

    def _upload_files(self):
        """上传文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择要上传的文件", "",
            "所有文件 (*);;文本文件 (*.txt);;Python 文件 (*.py);;图像文件 (*.png *.jpg *.jpeg)"
        )
        if files:
            self._perform_upload(files, self.current_path)

    def _upload_folder(self):
        """上传文件夹（递归）"""
        folder = QFileDialog.getExistingDirectory(
            self, "选择要上传的文件夹", "",
            QFileDialog.ShowDirsOnly
        )
        if folder:
            # 获取文件夹内所有文件
            files_to_upload = []
            base_path = Path(folder)
            for file_path in base_path.rglob('*'):
                if file_path.is_file():
                    files_to_upload.append(str(file_path))

            if files_to_upload:
                reply = QMessageBox.question(
                    self, "确认上传",
                    f"将上传 {len(files_to_upload)} 个文件到远程目录:\n{self.current_path}\n\n是否继续?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._perform_upload(files_to_upload, self.current_path, base_local_path=folder)

    def _perform_upload(self, local_paths, remote_dir, base_local_path=None):
        """执行上传操作 - 带进度条"""
        total_size = sum(os.path.getsize(p) for p in local_paths)
        progress = QProgressDialog("上传文件...", "取消", 0, total_size, self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setWindowTitle("文件上传")
        progress.setAutoClose(True)
        progress.setAutoReset(True)

        transferred = 0

        def progress_callback(transferred_bytes, total_bytes):
            nonlocal transferred
            transferred += transferred_bytes
            progress.setValue(transferred)
            progress.setLabelText(f"已上传: {transferred / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB")
            QtCore.QCoreApplication.processEvents()
            if progress.wasCanceled():
                raise Exception("用户取消了上传")

        try:
            for local_path in local_paths:
                # 计算远程路径
                if base_local_path:
                    # 保持目录结构
                    rel_path = os.path.relpath(local_path, base_local_path)
                    remote_path = posixpath.join(remote_dir, rel_path.replace('\\', '/'))
                    # 确保远程目录存在
                    remote_parent = posixpath.dirname(remote_path)
                    if remote_parent != remote_dir:
                        try:
                            self.session.sftp.stat(remote_parent)
                        except:
                            # 递归创建目录
                            parts = remote_parent.strip('/').split('/')
                            current = ''
                            for part in parts:
                                current = posixpath.join(current, part)
                                try:
                                    self.session.sftp.stat(current)
                                except:
                                    self.session.sftp.mkdir(current)
                else:
                    remote_path = posixpath.join(remote_dir, os.path.basename(local_path))

                # 执行上传
                self.session.upload_file(local_path, remote_path, progress_callback)

            progress.close()
            self._load_path(self.current_path)
            InfoBar.success(
                title="上传完成",
                content=f"成功上传 {len(local_paths)} 个文件",
                orient=QtCore.Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )
        except Exception as e:
            progress.close()
            if "用户取消" not in str(e):
                QMessageBox.warning(self, "上传失败", f"上传过程中出错:\n{str(e)}")

    def _download_file(self, remote_path):
        """下载文件"""
        default_name = os.path.basename(remote_path)
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存文件", default_name, "所有文件 (*)"
        )
        if save_path:
            self._perform_download(remote_path, save_path)

    def _perform_download(self, remote_path, local_path):
        """执行下载操作 - 带进度条"""
        # 获取文件大小
        try:
            stat = self.session.sftp.stat(remote_path)
            file_size = stat.st_size
        except:
            file_size = 0

        progress = QProgressDialog("下载文件...", "取消", 0, file_size, self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setWindowTitle("文件下载")

        def progress_callback(transferred, total):
            progress.setValue(transferred)
            progress.setLabelText(f"已下载: {transferred / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB")
            QtCore.QCoreApplication.processEvents()
            if progress.wasCanceled():
                raise Exception("用户取消了下载")

        try:
            self.session.download_file(remote_path, local_path, progress_callback)
            progress.close()
            InfoBar.success(
                title="下载完成",
                content=f"文件已保存到:\n{local_path}",
                orient=QtCore.Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )
        except Exception as e:
            progress.close()
            if "用户取消" not in str(e):
                QMessageBox.warning(self, "下载失败", f"下载过程中出错:\n{str(e)}")

    def _on_sort_indicator_changed(self, logicalIndex, order):
        """处理表头排序指示器变化"""
        self.current_sort_column = logicalIndex
        self.current_sort_order = order
        # 重新应用排序（因为数据可能已变化）
        self.table.sortItems(logicalIndex, order)

    def _rename_item(self, path, current_name, is_dir):
        """重命名文件/文件夹"""
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "重命名", "新名称:",
            QtWidgets.QLineEdit.Normal, current_name
        )
        if ok and new_name.strip() and new_name.strip() != current_name:
            try:
                parent_dir = posixpath.dirname(path)
                new_path = posixpath.join(parent_dir, new_name.strip())
                self.session.rename(path, new_path)
                self._load_path(parent_dir)
                InfoBar.success(
                    title="成功",
                    content=f"已重命名为: {new_name}",
                    orient=QtCore.Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self
                )
            except Exception as e:
                QMessageBox.warning(self, "错误", f"重命名失败:\n{str(e)}")

    def _delete_item(self, path, name, is_dir):
        """删除文件/文件夹"""
        msg = f"确定要删除{'文件夹' if is_dir else '文件'}吗?\n\n{name}"
        if is_dir:
            msg += "\n\n⚠ 此操作将递归删除文件夹内所有内容!"

        reply = QMessageBox.warning(
            self, "确认删除", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                if is_dir:
                    self.session.remove_dir(path)
                else:
                    self.session.remove_file(path)
                self._load_path(self.current_path)
                InfoBar.success(
                    title="已删除",
                    content=f"{'文件夹' if is_dir else '文件'}已删除",
                    orient=QtCore.Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self
                )
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败:\n{str(e)}")

    def _copy_path(self, path):
        """复制路径到剪贴板"""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(path)
        InfoBar.info(
            title="已复制",
            content="路径已复制到剪贴板",
            orient=QtCore.Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
            parent=self
        )

    def get_selected_result(self):
        """获取选择结果 - 兼容各种模式"""
        if self.selection_mode == "folder":
            return self.last_selected_path or self.current_path
        return self.last_selected_path or ""

    def closeEvent(self, event):
        self.session.close()
        if self.state_tooltip:
            self.state_tooltip.close()
        super().closeEvent(event)

    # ===== 拖拽上传支持（可选增强）=====
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        local_files = [url.toLocalFile() for url in urls if os.path.exists(url.toLocalFile())]
        if local_files:
            self._perform_upload(local_files, self.current_path)
        event.acceptProposedAction()