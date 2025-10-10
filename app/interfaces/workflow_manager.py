import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List

from PyQt5.QtCore import QEasingCurve, QTimer, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    FlowLayout, InfoBar, FluentIcon, CardWidget, BodyLabel, SmoothScrollArea
)

from app.interfaces.canvas_interface import CanvasPage
from app.utils.utils import get_icon
from app.widgets.card_widget.workflow_card import WorkflowCard
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog


class WorkflowFileInfoScanner(QThread):
    """扫描工作流文件信息的线程"""
    scan_finished = pyqtSignal(list, dict, dict)  # (文件列表, 文件信息, 预览图信息)

    def __init__(self, workflow_dir: Path):
        super().__init__()
        self.workflow_dir = workflow_dir

    def run(self):
        workflow_files = []
        file_info_map = {}
        preview_map = {}
        
        # 收集所有工作流文件
        if self.workflow_dir.exists():
            workflow_files = list(self.workflow_dir.glob("*.workflow.json"))
            workflow_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # 预加载文件信息和预览图
            for wf_path in workflow_files:
                try:
                    stat = wf_path.stat()
                    file_info_map[str(wf_path)] = {
                        'ctime': datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                        'mtime': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        'size_kb': stat.st_size // 1024
                    }
                    
                    # 预加载预览图
                    preview_path = wf_path.parent / f"{wf_path.stem.split('.')[0]}.png"
                    if preview_path.exists():
                        pixmap = QPixmap(str(preview_path))
                        if not pixmap.isNull():
                            preview_map[str(wf_path)] = pixmap.scaled(
                                250, 150, 
                                Qt.KeepAspectRatio, 
                                Qt.SmoothTransformation
                            )
                except Exception:
                    pass  # 忽略单个文件错误
                    
        self.scan_finished.emit(workflow_files, file_info_map, preview_map)


class WorkflowCanvasGalleryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflow_canvas_gallery_page")
        self.parent_window = parent
        self.workflow_dir = self._get_workflow_dir()
        self.opened_workflows = {}
        self._is_loading = False
        self._pending_workflows = []
        self._batch_timer = None
        self._batch_size = 20  # 进一步增加批量大小
        self._file_info_map = {}  # 存储预加载的文件信息
        self._preview_map = {}    # 存储预加载的预览图
        self._setup_ui()
        QTimer.singleShot(50, self.load_workflows)

    def _get_workflow_dir(self):
        wf_dir = Path("workflows")
        wf_dir.mkdir(parents=True, exist_ok=True)
        return wf_dir

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        # 滚动区域
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")
        self.flow_layout = FlowLayout(self.scroll_widget, needAni=True)
        self.flow_layout.setAnimation(250, QEasingCurve.OutQuad)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(30)

        self.scroll_area.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll_area)

    def _open_workflow_dir(self):
        try:
            if os.name == 'nt':
                os.startfile(self.workflow_dir)
            else:
                subprocess.call(['xdg-open', self.workflow_dir])
        except Exception:
            pass

    def load_workflows(self):
        if self._is_loading:
            return
        self._is_loading = True

        # 清空现有内容（包括"新建"卡片）
        self._clear_layout()

        # 启动后台扫描（包含文件信息和预览图）
        self._scanner = WorkflowFileInfoScanner(self.workflow_dir)
        self._thread = QThread()
        self._scanner.moveToThread(self._thread)
        self._thread.started.connect(self._scanner.run)
        self._scanner.scan_finished.connect(self._on_detailed_scan_finished)
        self._scanner.scan_finished.connect(self._thread.quit)
        self._scanner.scan_finished.connect(self._scanner.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _clear_layout(self):
        """清空布局"""
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            item.deleteLater()

    def _create_new_card(self):
        """创建"新建画布"卡片"""
        new_card = CardWidget()
        new_card.setFixedSize(320, 300)
        new_card.setBorderRadius(12)
        layout = QVBoxLayout(new_card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 使用 FluentIcon.FOLDER_ADD 图标
        icon = FluentIcon.ADD.icon()
        plus_label = QLabel()
        plus_label.setPixmap(icon.pixmap(64, 64))  # 64x64 像素图标
        plus_label.setAlignment(Qt.AlignCenter)

        # 文字提示
        text_label = BodyLabel("新建画布")
        text_label.setAlignment(Qt.AlignCenter)

        layout.addStretch()
        layout.addWidget(plus_label)
        layout.addSpacing(40)
        layout.addWidget(text_label)
        layout.addStretch()

        # 点击事件
        new_card.mousePressEvent = lambda e: self.new_canvas()
        new_card.setCursor(Qt.PointingHandCursor)

        return new_card

    def _create_import_card(self):
        """创建"导入画布"卡片（使用 Fluent 图标）"""
        from qfluentwidgets import FluentIcon  # 确保导入

        import_card = CardWidget()
        import_card.setFixedSize(320, 300)
        import_card.setBorderRadius(12)
        layout = QVBoxLayout(import_card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 使用 FluentIcon.FOLDER_ADD 图标
        icon = FluentIcon.FOLDER_ADD.icon()
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(64, 64))  # 64x64 像素图标
        icon_label.setAlignment(Qt.AlignCenter)

        text_label = BodyLabel("导入画布")
        text_label.setAlignment(Qt.AlignCenter)

        layout.addStretch()
        layout.addWidget(icon_label)
        layout.addSpacing(40)
        layout.addWidget(text_label)
        layout.addStretch()

        import_card.mousePressEvent = lambda e: self.import_canvas()
        import_card.setCursor(Qt.PointingHandCursor)
        return import_card

    def _on_detailed_scan_finished(self, workflow_files: List[Path], file_info_map: dict, preview_map: dict):
        """处理详细扫描结果"""
        self._is_loading = False
        self._file_info_map = file_info_map
        self._preview_map = preview_map

        # 先添加"新建"和"导入"卡片（始终在最前面）
        new_card = self._create_new_card()
        import_card = self._create_import_card()
        self.flow_layout.addWidget(new_card)
        self.flow_layout.addWidget(import_card)

        if not workflow_files:
            placeholder = QLabel("暂无模型文件\n将 .workflow.json 文件放入 workflows/ 目录即可显示")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #888888; font-size: 14px; background-color: transparent;")
            placeholder.setWordWrap(True)
            self.flow_layout.addWidget(placeholder)
            return

        # 分批加载真实卡片
        self._pending_workflows = list(workflow_files)
        if self._batch_timer is None:
            self._batch_timer = QTimer(self)
            self._batch_timer.setInterval(10)  # 减少间隔时间
            self._batch_timer.timeout.connect(self._add_next_batch)
        if not self._batch_timer.isActive():
            self._batch_timer.start()

    def _add_next_batch(self):
        if not self._pending_workflows:
            if self._batch_timer and self._batch_timer.isActive():
                self._batch_timer.stop()
            return
        batch = self._pending_workflows[:self._batch_size]
        self._pending_workflows = self._pending_workflows[self._batch_size:]
        for wf_path in batch:
            try:
                # 传递预加载的信息
                file_info = self._file_info_map.get(str(wf_path))
                preview_pixmap = self._preview_map.get(str(wf_path))
                card = WorkflowCard(wf_path, self, file_info, preview_pixmap)
                self.flow_layout.addWidget(card)
            except Exception:
                pass

    # --- 以下方法保持不变（仅微调）---
    def open_canvas(self, file_path: Path):
        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(self.parent_window, object_name=file_path)
            canvas_page.canvas_deleted.connect(lambda: self.opened_workflows.pop(file_path))
            canvas_interface = self.parent_window.addSubInterface(
                canvas_page, get_icon("模型"), file_path.stem.split(".")[0], parent=self
            )
            canvas_interface.clicked.connect(
                lambda: (
                    canvas_page.nav_view.refresh_components(),
                    canvas_page.register_components(),
                    canvas_page._setup_pipeline_style()
                )
            )
            self.opened_workflows[file_path] = canvas_page
            self.opened_workflows[file_path].load_full_workflow(file_path)

        self.parent_window.switchTo(self.opened_workflows[file_path])

    def new_canvas(self):
        name_dialog = CustomInputDialog("新建画布", "请输入画布名称", parent=self)
        if not name_dialog.exec():
            return
        base_name = name_dialog.get_text().strip()
        if not base_name:
            InfoBar.warning("名称无效", "画布名称不能为空", parent=self)
            return

        file_path = self.workflow_dir / f"{base_name}.workflow.json"
        counter = 1
        while file_path.exists():
            file_path = self.workflow_dir / f"{base_name}_{counter}.workflow.json"
            counter += 1

        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(self.parent_window, object_name=file_path)
            canvas_page.save_full_workflow(file_path)
            canvas_interface = self.parent_window.addSubInterface(
                canvas_page, get_icon("模型"), file_path.stem.split(".")[0], parent=self)
            canvas_interface.clicked.connect(
                lambda: (
                    canvas_page.nav_view.refresh_components(),
                    canvas_page.register_components()
                )
            )
            self.opened_workflows[file_path] = canvas_page
        self.parent_window.switchTo(self.opened_workflows[file_path])
        self.load_workflows()  # 刷新列表（会重新插入"新建"卡片）

    def import_canvas(self):
        """导入外部画布文件"""
        # 添加creationflags参数以防止出现白色控制台窗口
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择画布文件",
            "",
            "Workflow Files (*.workflow.json);;All Files (*)"
        )
        if not file_path:
            return

        src_path = Path(file_path)
        if not src_path.exists():
            InfoBar.error("文件不存在", "请选择有效的画布文件", parent=self)
            return

        # 提取原始名称（不含 .workflow.json）
        stem = src_path.stem
        if stem.endswith('.workflow'):
            base_name = stem[:-9]  # 移除 ".workflow"
        else:
            base_name = stem

        if not base_name:
            base_name = "imported_workflow"

        # 生成目标路径（避免重名）
        dest_path = self.workflow_dir / f"{base_name}.workflow.json"
        counter = 1
        while dest_path.exists():
            dest_path = self.workflow_dir / f"{base_name}_{counter}.workflow.json"
            counter += 1

        # 复制主文件
        try:
            shutil.copy2(src_path, dest_path)

            # 尝试复制同名 .png 预览图
            src_png = src_path.parent / f'{base_name}.png'
            if src_png.exists():
                dest_png = dest_path.parent / f'{base_name}.png'
                shutil.copy2(src_png, dest_png)

            InfoBar.success("导入成功", f"已导入 {dest_path.stem}", parent=self)
            self.load_workflows()  # 刷新列表

        except Exception as e:
            InfoBar.error("导入失败", str(e), parent=self)

    def duplicate_workflow(self, src_path: Path):
        dialog = CustomInputDialog("复制画布", "请输入新画布名称", src_path.stem.split(".")[0] + "_copy", self)
        if not dialog.exec():
            return
        new_name = dialog.get_text().strip()
        if not new_name:
            InfoBar.warning("名称无效", "画布名称不能为空", parent=self)
            return

        dest_path = self.workflow_dir / f"{new_name}.workflow.json"
        dest_png = self.workflow_dir / f"{new_name}.png"
        src_png = self.workflow_dir / f"{src_path.stem.split('.')[0]}.png"
        counter = 1
        base_name = new_name
        while dest_path.exists():
            new_name = f"{base_name}_{counter}"
            dest_path = self.workflow_dir / f"{new_name}.workflow.json"
            counter += 1

        try:
            shutil.copy2(src_path, dest_path)
            if src_png.exists():
                shutil.copy2(src_png, dest_png)
            InfoBar.success("复制成功", f"已创建 {new_name}", parent=self)
            self.load_workflows()
        except Exception as e:
            InfoBar.error("复制失败", str(e), parent=self)

    def delete_workflow(self, file_path: Path):
        from qfluentwidgets import MessageBox, InfoBar

        w = MessageBox("确认删除", f"确定要删除画布 \"{file_path.stem}\" 吗？\n此操作不可恢复！", self)
        if not w.exec():
            return

        try:
            file_path.unlink()
            # 同时删除预览图
            preview_path = self.workflow_dir / f"{file_path.stem.split('.')[0]}.png"
            if preview_path.exists():
                preview_path.unlink()
                
            InfoBar.success("删除成功", f"画布 '{file_path.stem}' 已删除", parent=self)
            if file_path in self.opened_workflows:
                self.parent_window.removeInterface(self.opened_workflows[file_path])
                del self.opened_workflows[file_path]
            self.load_workflows()
        except Exception as e:
            InfoBar.error("删除失败", str(e), parent=self)