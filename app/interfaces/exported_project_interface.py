# -*- coding: utf-8 -*-
import errno
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal, QEasingCurve, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QDialog, QTextEdit, QLabel, QFileDialog
from qfluentwidgets import (
    ScrollArea, PrimaryPushButton,
    InfoBar,
    MessageBox, StateToolTip, FlowLayout, CardWidget, BodyLabel
)

from app.utils.service_manager import SERVICE_MANAGER
from app.utils.utils import ansi_to_html
from app.widgets.card_widget.project_card import ProjectCard


class ProjectRunnerThread(QThread):
    """在独立线程中运行项目"""
    finished = pyqtSignal(dict, str)
    error = pyqtSignal(str)

    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        workflow_path = os.path.join(project_path, "model.workflow.json")
        if not os.path.exists(workflow_path):
            raise FileNotFoundError(f"未找到 model.workflow.json: {workflow_path}")
        with open(workflow_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.python_exe = data.get("runtime", {}).get("environment_exe")
            if not self.python_exe:
                raise ValueError("model.workflow.json 中未指定 environment_exe")

    def run(self):
        try:
            result = subprocess.run(
                [self.python_exe, "run.py"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            outputs = {}
            output_file = os.path.join(self.project_path, "output.json")
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        outputs = json.load(f)
                except Exception:
                    pass  # 忽略 output.json 解析错误

            log_content = (result.stdout or "") + "\n" + (result.stderr or "")
            self.finished.emit(outputs, log_content)

        except Exception as e:
            self.error.emit(str(e))


class ExportedProjectsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("exported_projects_page")
        self.parent = parent
        self.export_dir = self._get_default_export_dir()
        self.running_projects = {}
        self._setup_ui()

    def _get_default_export_dir(self):
        default_dir = "projects"
        os.makedirs(default_dir, exist_ok=True)
        return default_dir

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 流式布局区域
        self.scroll_area = ScrollArea(self)
        self.scroll_area.setViewportMargins(0, 0, 0, 0)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")
        self.flow_layout = FlowLayout(self.scroll_widget, needAni=True)
        self.flow_layout.setAnimation(250, QEasingCurve.OutQuad)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(50)

        self.scroll_area.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll_area)

        self.load_projects()

    def _create_import_card(self):
        """创建“导入画布”卡片（使用 Fluent 图标）"""
        from qfluentwidgets import FluentIcon  # 确保导入

        import_card = CardWidget()
        import_card.setBorderRadius(12)
        import_card.setFixedSize(400, 320)
        layout = QVBoxLayout(import_card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 使用 FluentIcon.FOLDER_ADD 图标
        icon = FluentIcon.FOLDER_ADD.icon()
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(64, 64))  # 64x64 像素图标
        icon_label.setAlignment(Qt.AlignCenter)

        text_label = BodyLabel("导入项目")
        text_label.setAlignment(Qt.AlignCenter)

        layout.addStretch()
        layout.addWidget(icon_label)
        layout.addSpacing(40)
        layout.addWidget(text_label)
        layout.addStretch()

        import_card.mousePressEvent = lambda e: self.import_projects()
        import_card.setCursor(Qt.PointingHandCursor)
        return import_card

    def _open_export_directory(self):
        try:
            if os.name == 'nt':
                os.startfile(self.export_dir)
            else:
                subprocess.call(['xdg-open', self.export_dir])
        except Exception as e:
            self.create_error_info("打开失败", str(e))

    def import_projects(self):
        """导入外部项目文件夹"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "选择项目文件夹",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not folder_path:
            return

        src_path = Path(folder_path)
        if not src_path.is_dir():
            self.create_error_info("无效选择", "请选择一个有效的项目文件夹")
            return

        # 检查是否包含必需的 model.workflow.json
        workflow_file = src_path / "model.workflow.json"
        if not workflow_file.exists():
            self.create_error_info("导入失败", "所选文件夹中缺少 model.workflow.json")
            return

        # 获取项目名称（文件夹名）
        base_name = src_path.name
        if not base_name.strip():
            base_name = "imported_project"

        # 生成目标路径（避免重名）
        dest_path = Path(self.export_dir) / base_name
        counter = 1
        while dest_path.exists():
            dest_path = Path(self.export_dir) / f"{base_name}_{counter}"
            counter += 1

        try:
            # 复制整个文件夹
            shutil.copytree(src_path, dest_path)

            self.create_success_info("导入成功", f"项目 “{dest_path.name}” 已导入")
            self.load_projects()  # 刷新列表
        except Exception as e:
            self.create_error_info("导入失败", f"错误: {str(e)}")

    def load_projects(self):
        # 清空所有卡片
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            item.deleteLater()

        self.flow_layout.addWidget(self._create_import_card())

        project_dirs = []
        for item in os.listdir(self.export_dir):
            item_path = os.path.join(self.export_dir, item)
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "model.workflow.json")):
                project_dirs.append(item_path)

        # 按创建时间倒序
        try:
            project_dirs.sort(key=lambda x: os.path.getctime(x), reverse=True)
        except Exception:
            pass  # 忽略排序错误

        for project_path in project_dirs:
            card = ProjectCard(project_path, self)
            card.run_btn.clicked.connect(lambda _, p=project_path: self._run_project(p))
            card.service_btn.clicked.connect(lambda _, p=project_path: self._toggle_service(p))
            card.view_log_btn.clicked.connect(lambda _, p=project_path: self._view_project_log(p))
            card.open_folder_btn.clicked.connect(lambda _, p=project_path: self._open_project_folder(p))
            card.delete_btn.clicked.connect(lambda _, p=project_path: self._delete_project(p))
            self.flow_layout.addWidget(card)

    def _toggle_service(self, project_path):
        try:
            if SERVICE_MANAGER.is_running(project_path):
                SERVICE_MANAGER.stop_service(project_path)
                self.create_success_info("服务已停止", "微服务已下线")
            else:
                url = SERVICE_MANAGER.start_service(project_path)
                self.create_success_info("服务已启动", f"访问: {url}")
            self._update_service_status(project_path)
        except Exception as e:
            self.create_error_info("操作失败", str(e))

    def _update_service_status(self, project_path):
        for i in range(self.flow_layout.count()):
            card = self.flow_layout.itemAt(i).widget()
            if isinstance(card, ProjectCard) and card.project_path == project_path:
                card._update_service_button()
                break

    def _run_project(self, project_path):
        if project_path in self.running_projects:
            self.create_warning_info("项目已在运行", "请等待当前运行完成")
            return

        state_tooltip = StateToolTip("正在运行项目", "请稍候...", self)
        state_tooltip.move(self.width() - state_tooltip.width() - 20, 20)
        state_tooltip.show()

        try:
            thread = ProjectRunnerThread(project_path, self)
        except Exception as e:
            state_tooltip.setContent(f"启动失败 ❌\n{e}")
            state_tooltip.setState(True)
            self.create_error_info("启动失败", str(e))
            return

        self.running_projects[project_path] = (thread, state_tooltip)

        thread.finished.connect(
            lambda outputs, log: self._on_project_finished(project_path, outputs, log, state_tooltip))
        thread.error.connect(lambda err: self._on_project_error(project_path, err, state_tooltip))
        thread.start()

        self._update_card_status(project_path, True)

    def _on_project_finished(self, project_path, outputs, log_content, state_tooltip):
        state_tooltip.setContent("项目运行完成 ✅")
        state_tooltip.setState(True)

        try:
            output_file = os.path.join(project_path, "output.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(outputs, f, indent=2, ensure_ascii=False)

            log_file = os.path.join(project_path, "run.log")
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(log_content)
        except Exception as e:
            self.create_error_info("保存日志失败", str(e))

        self.create_success_info("运行完成", f"项目 {os.path.basename(project_path)} 执行成功")
        self._cleanup_project_run(project_path)

    def _on_project_error(self, project_path, error, state_tooltip):
        state_tooltip.setContent(f"运行失败 ❌\n{error}")
        state_tooltip.setState(True)
        self.create_error_info("运行失败", f"项目 {os.path.basename(project_path)} 执行失败:\n{error}")
        self._cleanup_project_run(project_path)

    def _cleanup_project_run(self, project_path):
        self.running_projects.pop(project_path, None)
        self._update_card_status(project_path, False)

    def _update_card_status(self, project_path, is_running):
        for i in range(self.flow_layout.count()):
            card = self.flow_layout.itemAt(i).widget()
            if isinstance(card, ProjectCard) and card.project_path == project_path:
                card.update_status(is_running)
                break

    def _view_project_log(self, project_path):
        all_logs = []

        run_log = os.path.join(project_path, "run.log")
        if os.path.exists(run_log):
            try:
                with open(run_log, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        all_logs.append(("项目运行日志", content))
            except Exception:
                pass

        service_log = os.path.join(project_path, "service.log")
        if os.path.exists(service_log):
            try:
                with open(service_log, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        all_logs.append(("微服务日志", content))
            except Exception:
                pass

        if not all_logs:
            self.create_warning_info("无日志", "项目尚未运行或日志文件不存在")
            return

        combined_content = ""
        for title, content in all_logs:
            combined_content += f"\n{'=' * 60}\n{title}\n{'=' * 60}\n\n"
            combined_content += content + "\n"

        self._show_log_dialog(combined_content)

    def _show_log_dialog(self, log_content):
        html_content = ansi_to_html(log_content)
        dialog = QDialog(self)
        dialog.setWindowTitle("项目运行日志")
        dialog.resize(800, 600)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(html_content)
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: none;
                padding: 10px;
            }
        """)
        font = QFont("Consolas", 10)
        text_edit.setFont(font)

        close_btn = PrimaryPushButton("关闭", self)
        close_btn.clicked.connect(dialog.accept)

        layout = QVBoxLayout(dialog)
        layout.addWidget(text_edit)
        layout.addWidget(close_btn)
        dialog.exec()

    def _open_project_folder(self, project_path):
        try:
            if os.name == 'nt':
                os.startfile(project_path)
            else:
                subprocess.call(['xdg-open', project_path])
        except Exception as e:
            self.create_error_info("打开失败", str(e))

    def _delete_project(self, project_path):
        w = MessageBox(
            "确认删除",
            f"确定要删除项目 '{os.path.basename(project_path)}' 吗？\n此操作不可恢复！",
            self
        )
        if w.exec():
            try:
                # 先停止服务
                if SERVICE_MANAGER.is_running(project_path):
                    SERVICE_MANAGER.stop_service(project_path)
                    # 等待 0.5 秒让文件句柄释放（Windows 需要）
                    time.sleep(0.5)

                # 尝试删除，最多重试 3 次
                for _ in range(3):
                    try:
                        shutil.rmtree(project_path)
                        self.create_success_info("删除成功", "项目已删除")
                        self.load_projects()
                        return
                    except PermissionError as e:
                        if e.errno == errno.EACCES:  # 文件被占用
                            time.sleep(0.3)
                            continue
                        else:
                            raise
                raise PermissionError(f"无法删除 {project_path}：文件仍被占用")
            except Exception as e:
                self.create_error_info("删除失败", f"错误: {str(e)}")

    def create_success_info(self, title, content):
        InfoBar.success(title, content, parent=self, duration=2000)

    def create_warning_info(self, title, content):
        InfoBar.warning(title, content, parent=self, duration=2000)

    def create_error_info(self, title, content):
        InfoBar.error(title, content, parent=self, duration=3000)