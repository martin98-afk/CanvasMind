import os
import shutil

from PyQt5.QtWidgets import QAbstractItemView
from qfluentwidgets import TreeView


class DragDropTreeView(TreeView):
    """
    专业级文件树视图
    特性：
    1. 支持外部文件拖入上传 (Copy)
    2. 支持内部文件拖拽移动 (Move)
    3. 优化双击行为：文件夹展开/折叠，文件打开
    4. 禁用双击重命名，改为 F2 或右键
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # 开启拖拽
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)

        # 【关键优化】设置选择模式为扩展选择（支持多选）
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # 【关键优化】禁用双击编辑（防止双击打开文件时触发重命名）
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)

        # 优化动画
        self.setAnimated(True)
        self.setIndentation(20)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            # 允许内部拖拽（默认行为通常是移动）
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        # 确保拖拽时高亮目标文件夹
        if event.mimeData().hasUrls() or self.model():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        """处理文件放置逻辑"""
        model = self.model()
        # 获取目标索引
        index = self.indexAt(event.pos())

        # 计算目标路径
        if not index.isValid():
            # 如果拖到了空白处，目标是根目录
            dest_dir = model.rootPath()
        elif model.isDir(index):
            # 如果拖到了文件夹上，目标是该文件夹
            dest_dir = model.filePath(index)
        else:
            # 如果拖到了文件上，目标是该文件所在的父目录
            dest_dir = os.path.dirname(model.filePath(index))

        # === 情况1：外部文件拖入 (复制操作) ===
        if event.mimeData().hasUrls() and not (event.source() == self):
            for url in event.mimeData().urls():
                src_path = url.toLocalFile()
                if os.path.exists(src_path):
                    self._copy_file_or_dir(src_path, dest_dir)
            event.acceptProposedAction()

        # === 情况2：内部文件拖拽 (移动操作) ===
        elif event.source() == self:
            # 获取选中的所有行
            selected_indexes = self.selectedIndexes()
            # 过滤掉非第一列的索引（QFileSystemModel每一行有4列，我们只需要处理一次）
            paths_to_move = []
            for idx in selected_indexes:
                if idx.column() == 0:
                    paths_to_move.append(model.filePath(idx))

            for src_path in paths_to_move:
                # 防止移动到自己里面，或者移动到当前所在目录
                if os.path.dirname(src_path) == dest_dir:
                    continue
                if src_path == dest_dir:
                    continue

                self._move_file_or_dir(src_path, dest_dir)

            # 通知视图更新（有时Model反应慢）
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _copy_file_or_dir(self, src, dst_dir):
        """辅助函数：复制"""
        try:
            name = os.path.basename(src)
            dst_path = os.path.join(dst_dir, name)
            if os.path.exists(dst_path):
                # 简单处理重名：跳过 (实际项目中可以改为弹窗询问)
                print(f"Skipped {name}, already exists.")
                return

            if os.path.isdir(src):
                shutil.copytree(src, dst_path)
            else:
                shutil.copy2(src, dst_path)
        except Exception as e:
            print(f"Copy error: {e}")

    def _move_file_or_dir(self, src, dst_dir):
        """辅助函数：移动"""
        try:
            name = os.path.basename(src)
            dst_path = os.path.join(dst_dir, name)
            shutil.move(src, dst_path)
        except Exception as e:
            print(f"Move error: {e}")