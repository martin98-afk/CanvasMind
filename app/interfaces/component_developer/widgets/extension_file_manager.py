# -*- coding: utf-8 -*-
import os
import shutil
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QFileSystemModel, QMenu, QInputDialog, QFileDialog)
from qfluentwidgets import (FluentIcon, Action, CommandBar, MessageBox)

from app.interfaces.component_developer.widgets.file_tree_view import DragDropTreeView
from app.utils.utils import get_icon


class ExtensionFileManager(QWidget):
    # 发送文件路径的信号
    file_double_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_path = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # === 工具栏 ===
        self.command_bar = CommandBar(self)
        self.command_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # 将Action逻辑改为基于“当前选中”项，如果未选中则基于根目录
        self.command_bar.addActions([
            Action(FluentIcon.ADD, self.tr("新建"),
                   triggered=lambda: self._show_create_menu_for_index(self.tree.currentIndex())),
            Action(get_icon("upload"), self.tr("上传文件"),
                   triggered=lambda: self._upload_files(self._get_context_path(self.tree.currentIndex()))),
            Action(FluentIcon.FOLDER_ADD, self.tr("上传文件夹"),
                   triggered=lambda: self._upload_folder(self._get_context_path(self.tree.currentIndex()))),
            Action(FluentIcon.SYNC, self.tr("刷新"), triggered=self._refresh_tree),
        ])
        layout.addWidget(self.command_bar)

        # === 文件模型 ===
        self.model = QFileSystemModel()
        self.model.setReadOnly(False)  # 允许重命名/删除

        # === 树视图 ===
        self.tree = DragDropTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)

        # 隐藏 Size, Type, Date 列，只留 Name
        for i in range(1, 4):
            self.tree.hideColumn(i)

        # === 信号连接 ===
        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.tree)

    def set_root_path(self, path_str):
        self.root_path = str(Path(path_str).resolve())
        if not os.path.exists(self.root_path):
            try:
                os.makedirs(self.root_path, exist_ok=True)
            except OSError:
                return

        # QFileSystemModel 需要一点时间加载
        self.model.setRootPath(self.root_path)
        root_index = self.model.index(self.root_path)
        self.tree.setRootIndex(root_index)

    def _refresh_tree(self):
        """强制刷新Model，解决外部变动不更新的问题"""
        # 重新设置一下 root path 可以触发刷新
        self.model.setRootPath(self.root_path)

    def _on_double_click(self, index):
        """
        双击处理逻辑：
        1. 如果是文件 -> 发射信号打开
        2. 如果是文件夹 -> 展开/折叠 (Tree View 默认行为，但为了保险可以手动控制)
        """
        path = self.model.filePath(index)
        if self.model.isDir(index):
            # 文件夹：切换展开/折叠状态
            if self.tree.isExpanded(index):
                self.tree.collapse(index)
            else:
                self.tree.expand(index)
        else:
            # 文件：发射打开信号
            self.file_double_clicked.emit(path)

    def _get_context_path(self, index):
        """
        计算操作的基础路径：
        1. 如果 index 无效，返回根目录
        2. 如果 index 是文件夹，返回该文件夹路径
        3. 如果 index 是文件，返回其父目录
        """
        if not index.isValid():
            return self.root_path

        if self.model.isDir(index):
            return self.model.filePath(index)
        else:
            return os.path.dirname(self.model.filePath(index))

    # ================= 右键菜单 =================
    def _show_context_menu(self, position):
        index = self.tree.indexAt(position)

        # 获取当前点击位置的上下文路径
        context_path = self._get_context_path(index)

        menu = QMenu()

        # 新建子菜单
        new_menu = menu.addMenu(FluentIcon.ADD.icon(), self.tr("新建"))
        self._add_create_actions(new_menu, context_path)

        menu.addSeparator()

        # 上传
        menu.addAction(get_icon("upload"), self.tr("上传文件"), lambda: self._upload_files(context_path))
        menu.addAction(FluentIcon.FOLDER_ADD.icon(), self.tr("上传文件夹"), lambda: self._upload_folder(context_path))

        menu.addSeparator()

        if index.isValid():
            # 针对选中项的操作
            menu.addAction(get_icon("重命名"), self.tr("重命名"), lambda: self.tree.edit(index))  # 调用 Qt 原生编辑接口
            menu.addAction(FluentIcon.DELETE.icon(), self.tr("删除"), lambda: self._delete_item(index))
            menu.addSeparator()
            menu.addAction(FluentIcon.FOLDER.icon(), self.tr("打开系统位置"),
                           lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.model.filePath(index))))

        # 在鼠标位置弹出
        menu.exec_(self.tree.viewport().mapToGlobal(position))

    def _show_create_menu_for_index(self, index):
        """工具栏调用新建菜单"""
        path = self._get_context_path(index)
        menu = QMenu(self)
        self._add_create_actions(menu, path)
        menu.exec_(self.cursor().pos())

    def _add_create_actions(self, menu, base_dir):
        """向菜单添加新建选项"""
        formats = [("Python", "py"), ("Text", "txt"), ("JSON", "json"), ("Markdown", "md")]
        for label, ext in formats:
            menu.addAction(f"{label} (.{ext})", lambda e=ext, p=base_dir: self._create_file(e, p))
        menu.addSeparator()
        menu.addAction(FluentIcon.FOLDER_ADD.icon(), self.tr("文件夹"), lambda: self._create_folder(base_dir))

    # ================= 实际操作逻辑 =================

    def _create_file(self, ext, base_dir):
        if not base_dir: base_dir = self.root_path
        name, ok = QInputDialog.getText(self, self.tr("新建文件"), self.tr(f"文件名 (.{ext}):"))
        if ok and name:
            if not name.endswith(f".{ext}"):
                name += f".{ext}"
            full_path = os.path.join(base_dir, name)
            try:
                with open(full_path, 'w', encoding='utf-8') as f:
                    pass
            except Exception as e:
                MessageBox(self.tr("错误"), str(e), self.window()).exec()

    def _create_folder(self, base_dir):
        if not base_dir: base_dir = self.root_path
        name, ok = QInputDialog.getText(self, self.tr("新建文件夹"), self.tr("文件夹名称:"))
        if ok and name:
            try:
                os.makedirs(os.path.join(base_dir, name), exist_ok=True)
            except Exception as e:
                MessageBox(self.tr("错误"), str(e), self.window()).exec()

    def _delete_item(self, index):
        file_path = self.model.filePath(index)
        name = self.model.fileName(index)

        # 使用 FluentWidgets 的 MessageBox
        w = MessageBox(self.tr("确认删除"), self.tr(f"确定要永久删除 '{name}' 吗？此操作无法撤销。"), self.window())
        if w.exec():
            try:
                if self.model.isDir(index):
                    shutil.rmtree(file_path)
                    self.model.rmdir(index)  # 通知 Model
                else:
                    os.remove(file_path)
                    self.model.remove(index)  # 通知 Model
            except Exception as e:
                MessageBox(self.tr("删除失败"), str(e), self.window()).exec()

    def _upload_files(self, dest_dir):
        if not dest_dir: dest_dir = self.root_path
        files, _ = QFileDialog.getOpenFileNames(self, self.tr("选择文件"), "", "All Files (*)")
        if files:
            for src in files:
                try:
                    shutil.copy2(src, dest_dir)
                except Exception as e:
                    print(f"Upload file error: {e}")

    def _upload_folder(self, dest_dir):
        """新增：上传（复制）文件夹"""
        if not dest_dir: dest_dir = self.root_path
        # QFileDialog 不支持同时选文件和文件夹，所以这是单独的
        src_dir = QFileDialog.getExistingDirectory(self, self.tr("选择文件夹"), "")
        if src_dir:
            try:
                folder_name = os.path.basename(src_dir)
                target_path = os.path.join(dest_dir, folder_name)
                shutil.copytree(src_dir, target_path)
            except Exception as e:
                MessageBox(self.tr("上传失败"), str(e), self.window()).exec()
