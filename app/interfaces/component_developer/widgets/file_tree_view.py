import os
import shutil

from PyQt5.QtCore import Qt, QUrl, QMimeData, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QMessageBox)
from loguru import logger
# 引入 FluentWidgets 组件
from qfluentwidgets import TreeView


class DragDropTreeView(TreeView):
    """
    【PyCharm 级体验】文件树视图 (Fluent 风格版)
    已优化：双击灵敏度、防误触拖拽
    """

    fileClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_drag_drop()

        # --- 新增：用于防抖的变量 ---
        self._start_pos = None

    def _setup_ui(self):
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setAnimated(True)
        self.setIndentation(20)

        # 连接双击信号（虽然重写了 doubleClickEvent，保留这个是个好习惯）
        self.doubleClicked.connect(self._on_double_clicked)

    def _setup_drag_drop(self):
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)

    # ==============================
    # 核心优化：鼠标事件防抖处理
    # ==============================
    def mousePressEvent(self, event):
        """记录按下时的坐标，用于后续计算移动距离"""
        if event.button() == Qt.LeftButton:
            self._start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """只有移动距离超过系统阈值时，才触发拖拽"""
        if not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return

        if not self._start_pos:
            return

        # 计算曼哈顿长度（比勾股定理快，足以判断距离）
        distance = (event.pos() - self._start_pos).manhattanLength()

        if distance >= QApplication.startDragDistance():
            super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """显式处理双击事件，确保优先级"""
        idx = self.indexAt(event.pos())
        if idx.isValid():
            # 这里调用原本的逻辑
            self._on_double_clicked(idx)

        super().mouseDoubleClickEvent(event)

    def _on_double_clicked(self, index):
        """统一处理双击逻辑"""
        if not index.isValid(): return

        if self.model().isDir(index):
            # 如果是文件夹，展开/收起（TreeView默认行为其实已有，这里可加强控制）
            if self.isExpanded(index):
                self.collapse(index)
            else:
                self.expand(index)
        else:
            # 如果是文件，发送信号
            path = self.model().filePath(index)
            self.fileClicked.emit(path)

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
        name = os.path.basename(paths[0]) if paths else ""
        msg = f"确定要永久删除这 {count} 个项目吗？" if count > 1 else f"确定要删除 '{name}' 吗？"
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
        self._on_double_clicked(idx)  # 复用逻辑

    def _rename_selected(self):
        if self.currentIndex().isValid(): self.edit(self.currentIndex())

    # ==============================
    # 拖拽逻辑 (微调)
    # ==============================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction if event.source() != self else Qt.MoveAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        model = self.model()
        idx = self.indexAt(event.pos())

        # 确定目标文件夹
        if not idx.isValid():
            dest_dir = model.rootPath()
        else:
            dest_dir = model.filePath(idx) if model.isDir(idx) else os.path.dirname(model.filePath(idx))

        if event.mimeData().hasUrls():
            # 外部拖入或内部移动
            urls = event.mimeData().urls()
            is_internal_move = (event.source() == self)

            for url in urls:
                src = url.toLocalFile()
                if not os.path.exists(src): continue

                # 防呆设计：源路径和目标路径相同时跳过
                if os.path.dirname(src) == dest_dir:
                    continue
                # 防呆设计：不能把文件夹移动到自己内部
                if os.path.isdir(src) and dest_dir.startswith(src):
                    continue

                if is_internal_move:
                    self._move_file_or_dir(src, dest_dir)
                else:
                    self._copy_file_or_dir(src, dest_dir)

            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _copy_file_or_dir(self, src, dst_dir):
        try:
            name = os.path.basename(src)
            dst = os.path.join(dst_dir, name)
            # 简单的重名处理
            if os.path.exists(dst):
                self._remove_path_safely(dst)

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
            shutil.move(src, dst)
            logger.info(f"移动: {src} -> {dst}")
        except Exception as e:
            logger.exception(f"移动失败: {e}")
            QMessageBox.critical(self, "移动失败", str(e))