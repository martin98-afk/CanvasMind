# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPixmap
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QWidget
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from qfluentwidgets import CardWidget, BodyLabel, PrimaryPushButton, FluentIcon, ToolButton, ImageLabel


class ImageLoader(QObject):
    """异步加载图片的辅助类"""
    image_loaded = pyqtSignal(QPixmap)

    def __init__(self, image_path: str):
        super().__init__()
        self.image_path = image_path

    def load_image(self):
        """在单独线程中加载原图（不缩放）"""
        try:
            pixmap = QPixmap(self.image_path)
            if pixmap.isNull():
                self.image_loaded.emit(QPixmap())
            else:
                # ✅ 关键：不缩放，发送原始高清 pixmap
                self.image_loaded.emit(pixmap)
        except Exception:
            self.image_loaded.emit(QPixmap())


class WorkflowCard(CardWidget):
    def __init__(
        self,
        file_path: Path,
        parent: Optional[QWidget] = None,
        file_info: Optional[Dict[str, Any]] = None,
        preview_pixmap: Optional[QPixmap] = None
    ):
        """
        :param file_path: 工作流文件路径 (.workflow.json)
        :param parent: 父控件
        :param file_info: 预加载的文件信息，格式: {'ctime': str, 'mtime': str, 'size_kb': int}
        :param preview_pixmap: 预加载的预览图 QPixmap（可选）
        """
        super().__init__(parent)
        self.home = parent
        self.file_path = file_path
        self.workflow_name = file_path.stem.split(".")[0]  # 保留原有逻辑
        self._file_info = file_info
        self._preview_pixmap = preview_pixmap
        self._img_label = None
        self._image_loader = None
        self._image_thread = None

        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(300)
        self.setFixedWidth(320)
        self.setBorderRadius(12)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 样式表
        self.setStyleSheet("""
            QWidget#WorkflowCardTitle { font-size: 14px; font-weight: 600; }
            QLabel.workflowMetaKey { color: #666; }
            QLabel.workflowMetaVal { color: #333; }
        """)

        # === 预览图区域 ===
        self._img_label = None
        preview_path = self._get_preview_path()

        if preview_path.exists():
            self._img_label = ImageLabel(str(preview_path), self)
            self._img_label.setFixedSize(250, 150)
            self._img_label.setBorderRadius(8, 8, 8, 8)
        else:
            # 占位符
            placeholder = BodyLabel("无预览图")
            placeholder.setFixedSize(250, 150)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #aaa; background-color: #f5f5f5; border-radius: 8px;")
            layout.addWidget(placeholder, 0, Qt.AlignCenter)

        if self._img_label:
            layout.addWidget(self._img_label, 0, Qt.AlignCenter)

        # 标题
        name_label = BodyLabel(self.workflow_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        name_label.setObjectName("WorkflowCardTitle")
        layout.addWidget(name_label)

        # 信息（网格布局）
        meta_grid = QGridLayout()
        meta_grid.setVerticalSpacing(4)
        meta_grid.setHorizontalSpacing(8)

        if self._file_info:
            # 使用预加载信息
            create_time = self._file_info.get('ctime', '未知')
            change_time = self._file_info.get('mtime', '未知')
        else:
            # 同步读取（性能差，仅作兜底）
            try:
                stat = self.file_path.stat()
                create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
                change_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                create_time = change_time = "未知"

        k1 = BodyLabel("创建")
        k1.setProperty("class", "workflowMetaKey")
        v1 = BodyLabel(create_time)
        v1.setProperty("class", "workflowMetaVal")

        k2 = BodyLabel("修改")
        k2.setProperty("class", "workflowMetaKey")
        v2 = BodyLabel(change_time)
        v2.setProperty("class", "workflowMetaVal")

        meta_grid.addWidget(k1, 0, 0)
        meta_grid.addWidget(v1, 0, 1)
        meta_grid.addWidget(k2, 1, 0)
        meta_grid.addWidget(v2, 1, 1)

        layout.addLayout(meta_grid)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        open_btn = PrimaryPushButton("打开画布", self, FluentIcon.EDIT)
        open_btn.setFixedHeight(28)
        open_btn.setFixedWidth(140)
        open_btn.clicked.connect(self._on_open_clicked)

        copy_btn = ToolButton(FluentIcon.COPY, self)
        copy_btn.setToolTip("复制画布")
        copy_btn.clicked.connect(self._on_copy_clicked)
        copy_btn.setFixedSize(28, 28)

        delete_btn = ToolButton(FluentIcon.DELETE, self)
        delete_btn.setToolTip("删除画布")
        delete_btn.clicked.connect(self._on_delete_clicked)
        delete_btn.setFixedSize(28, 28)

        tool_layout = QHBoxLayout()
        tool_layout.setSpacing(4)
        tool_layout.addWidget(copy_btn)
        tool_layout.addWidget(delete_btn)

        btn_layout.addWidget(open_btn)
        btn_layout.addStretch()
        btn_layout.addLayout(tool_layout)

        layout.addLayout(btn_layout)

        # === 阴影效果（始终存在，通过颜色控制显隐）===
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(22)
        self._shadow.setXOffset(0)
        self._shadow.setYOffset(4)
        self._shadow.setColor(Qt.transparent)  # 初始透明
        self.setGraphicsEffect(self._shadow)

    def _load_preview_image_async(self, preview_path: Path):
        """异步加载预览图"""
        # 创建线程和加载器
        self._image_loader = ImageLoader(str(preview_path))
        self._image_thread = QThread()
        
        # 移动到线程并连接信号
        self._image_loader.moveToThread(self._image_thread)
        self._image_thread.started.connect(self._image_loader.load_image)
        self._image_loader.image_loaded.connect(self._on_image_loaded)
        self._image_loader.image_loaded.connect(self._image_thread.quit)
        self._image_loader.image_loaded.connect(self._image_loader.deleteLater)
        self._image_thread.finished.connect(self._image_thread.deleteLater)
        
        # 启动线程
        self._image_thread.start()

    def _on_image_loaded(self, pixmap: QPixmap):
        """图片加载完成的回调（高质量缩放）"""
        if pixmap.isNull() or not self._img_label:
            return

        # ✅ 关键1: 禁用自动缩放
        self._img_label.setScaledContents(False)

        # ✅ 关键2: 手动高质量缩放
        scaled_pixmap = pixmap.scaled(
            self._img_label.width(),
            self._img_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation  # 启用双线性/双三次插值
        )

        # ✅ 关键3: 居中显示（因为 KeepAspectRatio 可能留空）
        self._img_label.setPixmap(scaled_pixmap)
        self._img_label.setAlignment(Qt.AlignCenter)  # 确保居中

    def enterEvent(self, event):
        self._shadow.setColor(QColor(0, 0, 0, 60))  # 半透明黑色阴影
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow.setColor(Qt.transparent)
        super().leaveEvent(event)

    def _get_preview_path(self) -> Path:
        """返回对应的预览图路径（xxx.workflow.json → xxx.png）"""
        base_name = self.file_path.parent / self.file_path.stem.split(".")[0]
        return base_name.with_suffix(".png")

    def _on_open_clicked(self):
        if hasattr(self.home, 'open_canvas'):
            self.home.open_canvas(self.file_path)

    def _on_copy_clicked(self):
        if hasattr(self.home, 'duplicate_workflow'):
            self.home.duplicate_workflow(self.file_path)

    def _on_delete_clicked(self):
        if hasattr(self.home, 'delete_workflow'):
            self.home.delete_workflow(self.file_path)

    def closeEvent(self, event):
        """清理线程资源"""
        if self._image_thread and self._image_thread.isRunning():
            self._image_thread.quit()
            self._image_thread.wait()
        super().closeEvent(event)