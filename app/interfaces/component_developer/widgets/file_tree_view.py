import os
import shutil
import subprocess
import sys

from PyQt5.QtCore import Qt, QUrl, QMimeData, pyqtSignal
from PyQt5.QtGui import QKeySequence, QDesktopServices
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QMessageBox, QFileSystemModel)

# 引入 FluentWidgets 组件
from qfluentwidgets import TreeView, RoundMenu, Action, FluentIcon as FIF
from loguru import logger


class DragDropTreeView(TreeView):
    """
    【PyCharm 级体验】文件树视图 (Fluent 风格版)
    """

    fileClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_drag_drop()

    def _setup_ui(self):
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setAnimated(True)
        self.setIndentation(20)

        # 开启右键菜单
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _setup_drag_drop(self):
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)

    # ==============================
    # 核心：Fluent 风格右键菜单 (RoundMenu)
    # ==============================
    def _show_context_menu(self, position):
        index = self.indexAt(position)
        if not index.isValid():
            return

        model = self.model()
        file_path = model.filePath(index)

        # 使用 RoundMenu
        menu = RoundMenu(parent=self)

        # 1. 打开
        action_open = Action(FIF.edit, "打开 (Enter)", self)
        action_open.triggered.connect(lambda: self._on_enter_pressed())

        # 2. 在资源管理器显示 (使用 Folder 图标)
        action_reveal = Action(FIF.FOLDER, "在资源管理器中显示", self)
        action_reveal.triggered.connect(lambda: self._reveal_in_explorer(file_path))

        # 3. 复制路径 (使用 Copy 图标)
        action_copy_path = Action(FIF.COPY, "复制路径", self)
        action_copy_path.triggered.connect(lambda: self._copy_path_to_clipboard(file_path))

        # 4. 重命名 (使用 Edit 图标)
        action_rename = Action(FIF.edit, "重命名 (F2)", self)
        action_rename.triggered.connect(self._rename_selected)

        # 5. 删除 (使用 Delete 图标)
        action_delete = Action(FIF.DELETE, "删除 (Delete)", self)
        action_delete.triggered.connect(self._delete_selected)

        # 组装菜单
        menu.addAction(action_open)
        menu.addSeparator()
        menu.addAction(action_rename)
        menu.addAction(action_delete)
        menu.addSeparator()
        menu.addAction(action_copy_path)
        menu.addAction(action_reveal)

        # 显示菜单
        menu.exec(self.viewport().mapToGlobal(position))

    # ==============================
    # 快捷键处理
    # ==============================
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self._delete_selected()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self._on_enter_pressed()
        elif event.key() == Qt.Key_F2:
            self._rename_selected()
        elif event.matches(QKeySequence.Copy):
            self._copy_selection_to_clipboard()
        elif event.matches(QKeySequence.Paste):
            self._paste_from_clipboard()
        else:
            super().keyPressEvent(event)

    # ==============================
    # 功能逻辑实现
    # ==============================
    def _copy_path_to_clipboard(self, path):
        QApplication.clipboard().setText(path)
        logger.info(f"路径已复制: {path}")

    def _delete_selected(self):
        paths = self._get_selected_paths()
        if not paths: return

        count = len(paths)
        msg = f"确定要永久删除这 {count} 个项目吗？" if count > 1 else f"确定要删除 '{os.path.basename(paths[0])}' 吗？"
        reply = QMessageBox.question(self, "删除确认", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            for path in paths:
                self._remove_path_safely(path)

    def _remove_path_safely(self, path):
        try:
            logger.info(f"正在删除: {path}")
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception as e:
            logger.error(f"删除失败: {e}")
            QMessageBox.critical(self, "错误", f"无法删除: {e}")

    def _copy_selection_to_clipboard(self):
        paths = self._get_selected_paths()
        if not paths: return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        QApplication.clipboard().setMimeData(mime)
        logger.info(f"已复制 {len(paths)} 个文件")

    def _paste_from_clipboard(self):
        mime = QApplication.clipboard().mimeData()
        if not mime.hasUrls(): return
        dest_dir = self._get_current_target_dir()
        for url in mime.urls():
            src = url.toLocalFile()
            if os.path.exists(src):
                self._copy_file_or_dir(src, dest_dir)

    def _get_selected_paths(self):
        return [self.model().filePath(idx) for idx in self.selectedIndexes() if idx.column() == 0]

    def _get_current_target_dir(self):
        idx = self.currentIndex()
        if not idx.isValid(): return self.model().rootPath()
        return self.model().filePath(idx) if self.model().isDir(idx) else os.path.dirname(self.model().filePath(idx))

    def _on_enter_pressed(self):
        idx = self.currentIndex()
        if not idx.isValid(): return
        if self.model().isDir(idx):
            self.collapse(idx) if self.isExpanded(idx) else self.expand(idx)
        else:
            self.fileClicked.emit(self.model().filePath(idx))

    def _rename_selected(self):
        if self.currentIndex().isValid(): self.edit(self.currentIndex())

    def _reveal_in_explorer(self, path):
        try:
            if os.name == 'nt':
                subprocess.run(['explorer', '/select,', os.path.normpath(path)])
            elif sys.platform == 'darwin':
                subprocess.run(['open', '-R', path])
            else:
                subprocess.run(['xdg-open', os.path.dirname(path)])
        except Exception as e:
            logger.error(f"无法打开文件浏览器: {e}")

    # ==============================
    # 拖拽逻辑
    # ==============================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or self.model():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        model = self.model()
        idx = self.indexAt(event.pos())
        dest_dir = model.rootPath() if not idx.isValid() else (
            model.filePath(idx) if model.isDir(idx) else os.path.dirname(model.filePath(idx)))

        if event.mimeData().hasUrls() and event.source() != self:
            for url in event.mimeData().urls():
                src = url.toLocalFile()
                if os.path.exists(src): self._copy_file_or_dir(src, dest_dir)
            event.acceptProposedAction()
        elif event.source() == self:
            for src in self._get_selected_paths():
                if os.path.dirname(src) != dest_dir and src != dest_dir:
                    self._move_file_or_dir(src, dest_dir)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _copy_file_or_dir(self, src, dst_dir):
        try:
            name = os.path.basename(src)
            dst = os.path.join(dst_dir, name)
            if os.path.abspath(src) == os.path.abspath(dst):
                dst = os.path.join(dst_dir, f"{os.path.splitext(name)[0]}_copy{os.path.splitext(name)[1]}")
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            logger.info(f"复制: {src} -> {dst}")
        except Exception as e:
            logger.exception(f"复制失败: {e}")

    def _move_file_or_dir(self, src, dst_dir):
        try:
            dst = os.path.join(dst_dir, os.path.basename(src))
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)
            logger.info(f"移动: {src} -> {dst}")
        except Exception as e:
            logger.exception(f"移动失败: {e}")