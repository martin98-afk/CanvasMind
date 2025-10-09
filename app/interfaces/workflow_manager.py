# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
from pathlib import Path
from typing import List

from PyQt5.QtCore import QEasingCurve, QTimer, QThread
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from Qt import Qt
from qfluentwidgets import (
    BodyLabel, ScrollArea, PrimaryPushButton, FluentIcon, FlowLayout, InfoBar
)

from app.interfaces.canvas_interface import CanvasPage
from app.utils.threading_utils import WorkflowScanner
from app.utils.utils import get_icon
from app.widgets.card_widget.workflow_card import WorkflowCard
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog


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
        self._batch_size = 2
        self._setup_ui()
        # 首次加载延迟触发，避免构造函数卡顿
        QTimer.singleShot(50, self.load_workflows)

    def _get_workflow_dir(self):
        wf_dir = Path("workflows")
        wf_dir.mkdir(parents=True, exist_ok=True)
        return wf_dir

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 工具栏
        toolbar = QHBoxLayout()
        self.new_btn = PrimaryPushButton(text="新建画布", icon=FluentIcon.ADD, parent=self)
        self.new_btn.clicked.connect(self.new_canvas)
        self.open_dir_btn = PrimaryPushButton(text="打开目录", parent=self, icon=FluentIcon.FOLDER)
        self.open_dir_btn.clicked.connect(self._open_workflow_dir)
        toolbar.addWidget(self.new_btn)
        toolbar.addWidget(self.open_dir_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 滚动区域
        self.scroll_area = ScrollArea(self)
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

        # 清空现有内容（立即响应）
        self._clear_layout()

        # 启动后台扫描
        self._scanner = WorkflowScanner(self.workflow_dir)
        self._thread = QThread()
        self._scanner.moveToThread(self._thread)
        self._thread.started.connect(self._scanner.scan)
        self._scanner.finished.connect(self._on_scan_finished)
        self._scanner.finished.connect(self._thread.quit)
        self._scanner.finished.connect(self._scanner.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _clear_layout(self):
        """快速清空布局（不 deleteLater，避免卡顿）"""
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            item.deleteLater()

    def _on_scan_finished(self, workflow_files: List[Path]):
        self._is_loading = False

        if not workflow_files:
            placeholder = BodyLabel("暂无模型文件\n将 .workflow.json 文件放入 workflows/ 目录即可显示")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #888888; font-size: 14px;")
            self.flow_layout.addWidget(placeholder)
            return

        # ✅ 关键：分批增量创建卡片，避免一次性大量创建导致 UI 卡顿
        self._pending_workflows = list(workflow_files)
        if self._batch_timer is None:
            self._batch_timer = QTimer(self)
            self._batch_timer.setInterval(0)  # 尽快，但让出事件循环
            self._batch_timer.timeout.connect(self._add_next_batch)
        if not self._batch_timer.isActive():
            self._batch_timer.start()

    def _add_next_batch(self):
        if not self._pending_workflows:
            if self._batch_timer and self._batch_timer.isActive():
                self._batch_timer.stop()
            return
        # 一次添加最多 _batch_size 个
        batch = self._pending_workflows[:self._batch_size]
        self._pending_workflows = self._pending_workflows[self._batch_size:]
        for wf_path in batch:
            try:
                card = WorkflowCard(wf_path, self)
                self.flow_layout.addWidget(card)
            except Exception:
                pass

    # --- 以下方法保持不变 ---
    def open_canvas(self, file_path: Path):
        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(self.parent_window, object_name=file_path)
            canvas_page.load_full_workflow(file_path)
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
        self.load_workflows()  # 刷新列表

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
            shutil.copy2(src_png, dest_png)
            InfoBar.success("复制成功", f"已创建 {new_name}", parent=self)
            self.load_workflows()
        except Exception as e:
            InfoBar.error("复制失败", str(e), parent=self)

    def delete_workflow(self, file_path: Path):
        from qfluentwidgets import MessageBox, InfoBar

        w = MessageBox("确认删除", f"确定要删除画布 “{file_path.stem}” 吗？\n此操作不可恢复！", self)
        if not w.exec():
            return

        try:
            file_path.unlink()
            InfoBar.success("删除成功", f"画布 “{file_path.stem}” 已删除", parent=self)
            if file_path in self.opened_workflows:
                self.parent_window.removeInterface(self.opened_workflows[file_path])
                del self.opened_workflows[file_path]
            self.load_workflows()
        except Exception as e:
            InfoBar.error("删除失败", str(e), parent=self)