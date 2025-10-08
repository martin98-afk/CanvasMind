import os
import shutil
import subprocess
from pathlib import Path

from PyQt5.QtCore import QEasingCurve
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from Qt import Qt
from qfluentwidgets import (
    BodyLabel, ScrollArea, PrimaryPushButton, FluentIcon, FlowLayout, InfoBar
)

from app.interfaces.canvas_interface import CanvasPage
from app.utils.utils import get_icon
from app.widgets.custom_messagebox import CustomInputDialog
from app.widgets.workflow_card import WorkflowCard


class WorkflowCanvasGalleryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflow_canvas_gallery_page")
        self.parent_window = parent
        self.workflow_dir = self._get_workflow_dir()
        self.opened_workflows = {}
        self._setup_ui()

    def _get_workflow_dir(self):
        # 建议统一存放 workflow 文件
        wf_dir = Path("workflows")
        wf_dir.mkdir(parents=True, exist_ok=True)
        return wf_dir

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 工具栏
        toolbar = QHBoxLayout()

        # 👇 新增：新建按钮
        self.new_btn = PrimaryPushButton(text="新建画布", icon=FluentIcon.ADD, parent=self)
        self.new_btn.clicked.connect(self.new_canvas)

        self.open_dir_btn = PrimaryPushButton(text="打开目录", parent=self, icon=FluentIcon.FOLDER)
        self.open_dir_btn.clicked.connect(self._open_workflow_dir)

        toolbar.addWidget(self.new_btn)
        toolbar.addWidget(self.open_dir_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 流式布局区域（使用之前定义的 CenterFlowLayout）
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
        # 清空
        while self.flow_layout.count():
            widget = self.flow_layout.takeAt(0)  # 直接就是 QWidget（如 WorkflowCard）
            if widget:
                widget.deleteLater()

        # 查找所有 .workflow.json 文件
        workflow_files = []
        for file in self.workflow_dir.glob("*.workflow.json"):
            workflow_files.append(file)

        # 按修改时间倒序
        workflow_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        if not workflow_files:
            placeholder = BodyLabel("暂无模型文件\n将 .workflow.json 文件放入 workflows/ 目录即可显示")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #888888; font-size: 14px;")
            self.flow_layout.addWidget(placeholder)
            return

        for wf_path in workflow_files:
            card = WorkflowCard(wf_path, self)
            self.flow_layout.addWidget(card)

    def open_canvas(self, file_path: Path):
        """由 WorkflowCard 调用，打开画布"""
        # 方式1：切换主窗口当前页面为 CanvasPage（推荐）
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
        """创建新的空白 workflow 文件并打开"""
        # 打开文本输入信息框
        name_dialog = CustomInputDialog("新建画布", "请输入画布名称", parent=self)
        if name_dialog.exec():
            base_name = name_dialog.get_text()
        else:
            return

        file_path = self.workflow_dir / f"{base_name}.workflow.json"

        # 确保不重名（虽然时间戳基本唯一，但保险起见）
        counter = 1
        while file_path.exists():
            file_path = self.workflow_dir / f"{base_name}_{counter}.workflow.json"
            counter += 1

        # 创建空白 workflow 结构（根据你的 CanvasPage.load_full_workflow 期望的格式）
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

    def duplicate_workflow(self, src_path: Path):
        dialog = CustomInputDialog("复制画布", "请输入新画布名称", src_path.stem + "_copy", self)
        if not dialog.exec():
            return
        new_name = dialog.get_text().strip()
        if not new_name:
            InfoBar.warning("名称无效", "画布名称不能为空", parent=self)
            return

        dest_path = self.workflow_dir / f"{new_name}.workflow.json"
        counter = 1
        base_name = new_name
        while dest_path.exists():
            new_name = f"{base_name}_{counter}"
            dest_path = self.workflow_dir / f"{new_name}.workflow.json"
            counter += 1

        try:
            shutil.copy2(src_path, dest_path)
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
