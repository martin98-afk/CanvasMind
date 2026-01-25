# -*- coding: utf-8 -*-
import os
import shutil
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QFileSystemModel, QInputDialog, QFileDialog)
# 核心改动：引入 RoundMenu
from qfluentwidgets import (FluentIcon, Action, CommandBar, MessageBox, RoundMenu, MenuAnimationType)

from app.interfaces.component_developer.widgets.file_tree_view import DragDropTreeView
from app.utils.utils import get_icon


class ExtensionFileManager(QWidget):
    file_double_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_path = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.command_bar = CommandBar(self)
        self.command_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.command_bar.addActions([
            Action(get_icon("upload"), self.tr("上传文件"),
                   triggered=lambda: self._upload_files(self._get_context_path(self.tree.currentIndex()))),
            Action(FluentIcon.ADD, self.tr("新建"),
                   triggered=lambda: self._show_create_menu_for_index(self.tree.currentIndex())),
            Action(FluentIcon.FOLDER_ADD, self.tr("上传文件夹"),
                   triggered=lambda: self._upload_folder(self._get_context_path(self.tree.currentIndex()))),
            Action(FluentIcon.SYNC, self.tr("刷新"), triggered=self._refresh_tree),
        ])
        layout.addWidget(self.command_bar)

        self.model = QFileSystemModel()
        self.model.setReadOnly(False)

        self.tree = DragDropTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)

        for i in range(1, 4):
            self.tree.hideColumn(i)

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

        self.model.setRootPath(self.root_path)
        root_index = self.model.index(self.root_path)
        self.tree.setRootIndex(root_index)

    def _refresh_tree(self):
        self.model.setRootPath(self.root_path)

    def _on_double_click(self, index):
        path = self.model.filePath(index)
        if self.model.isDir(index):
            if self.tree.isExpanded(index):
                self.tree.collapse(index)
            else:
                self.tree.expand(index)
        else:
            self.file_double_clicked.emit(path)

    def _get_context_path(self, index):
        if not index.isValid():
            return self.root_path
        if self.model.isDir(index):
            return self.model.filePath(index)
        else:
            return os.path.dirname(self.model.filePath(index))

    # ================= 修改后的右键菜单 =================
    def _show_context_menu(self, position):
        index = self.tree.indexAt(position)
        context_path = self._get_context_path(index)

        # 1. 创建 RoundMenu
        menu = RoundMenu(parent=self)

        # 2. 新建子菜单 (在 FluentWidgets 中，子菜单也是一个 RoundMenu)
        new_submenu = RoundMenu(title=self.tr("新建"), parent=menu)
        new_submenu.setIcon(FluentIcon.ADD)
        self._add_create_actions(new_submenu, context_path)
        menu.addMenu(new_submenu)

        menu.addSeparator()

        # 3. 使用 Action 添加菜单项
        menu.addAction(Action(get_icon("upload"), self.tr("上传文件"),
                              triggered=lambda: self._upload_files(context_path)))
        menu.addAction(Action(FluentIcon.FOLDER_ADD, self.tr("上传文件夹"),
                              triggered=lambda: self._upload_folder(context_path)))

        if index.isValid():
            menu.addSeparator()
            menu.addAction(Action(get_icon("重命名"), self.tr("重命名"),
                                  triggered=lambda: self.tree.edit(index)))
            menu.addAction(Action(FluentIcon.DELETE, self.tr("删除"),
                                  triggered=lambda: self._delete_item(index)))
            menu.addSeparator()
            menu.addAction(
                Action(
                    FluentIcon.COPY, "复制路径",
                    triggered=lambda: self.tree._copy_path_to_clipboard(self.model.filePath(index))
                )
            )
            menu.addAction(Action(FluentIcon.FOLDER, self.tr("打开系统位置"),
                                  triggered=lambda: QDesktopServices.openUrl(
                                      QUrl.fromLocalFile(context_path))))

        # 4. 弹出菜单，建议使用 exec 而非 exec_，并传入动画类型
        menu.exec(self.tree.viewport().mapToGlobal(position), aniType=MenuAnimationType.DROP_DOWN)

    def _show_create_menu_for_index(self, index):
        """工具栏调用新建菜单"""
        path = self._get_context_path(index)
        menu = RoundMenu(parent=self)
        self._add_create_actions(menu, path)
        # 在按钮下方弹出（这里简单处理为鼠标位置）
        menu.exec(self.cursor().pos(), aniType=MenuAnimationType.DROP_DOWN)

    def _add_create_actions(self, menu, base_dir):
        """向 RoundMenu 添加新建选项"""
        formats = [
            ("Python", "py", FluentIcon.CODE),
            ("Text", "txt", FluentIcon.DOCUMENT),
            ("JSON", "json", FluentIcon.DEVELOPER_TOOLS),
            ("Markdown", "md", FluentIcon.LABEL)
        ]

        for label, ext, icon in formats:
            # 使用 Action 对象
            action = Action(icon, f"{label} (.{ext})", self)
            action.triggered.connect(lambda checked, e=ext, p=base_dir: self._create_file(e, p))
            menu.addAction(action)

        menu.addSeparator()
        menu.addAction(Action(FluentIcon.FOLDER_ADD, self.tr("文件夹"),
                              triggered=lambda: self._create_folder(base_dir)))

    # ================= 实际操作逻辑 (保持不变) =================

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
        w = MessageBox(self.tr("确认删除"), self.tr(f"确定要永久删除 '{name}' 吗？此操作无法撤销。"), self.window())
        if w.exec():
            try:
                if self.model.isDir(index):
                    shutil.rmtree(file_path)
                else:
                    os.remove(file_path)
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
        if not dest_dir: dest_dir = self.root_path
        src_dir = QFileDialog.getExistingDirectory(self, self.tr("选择文件夹"), "")
        if src_dir:
            try:
                folder_name = os.path.basename(src_dir)
                target_path = os.path.join(dest_dir, folder_name)
                shutil.copytree(src_dir, target_path)
            except Exception as e:
                MessageBox(self.tr("上传失败"), str(e), self.window()).exec()