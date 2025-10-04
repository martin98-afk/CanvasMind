# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, PrimaryPushButton,
    ToolButton, FluentIcon, SearchLineEdit, InfoBar,
    MessageBox, StateToolTip
)


class ProjectRunnerThread(QThread):
    """在独立线程中运行项目"""
    finished = pyqtSignal(dict, str)  # (outputs, log_content)
    error = pyqtSignal(str)

    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path

    def run(self):
        try:
            # 运行项目并捕获输出
            result = subprocess.run(
                [sys.executable, "run.py"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # 尝试读取输出（如果项目生成了 output.json）
            outputs = {}
            output_file = os.path.join(self.project_path, "output.json")
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    outputs = json.load(f)

            log_content = result.stdout + "\n" + result.stderr
            self.finished.emit(outputs, log_content)

        except Exception as e:
            self.error.emit(str(e))


class ProjectCard(CardWidget):
    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.project_name = os.path.basename(project_path)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
                        ProjectCard {
                            background-color: transparent;
                            border: 1px solid #3c3c40;
                            border-radius: 8px;
                        }
                    """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 项目名称
        self.name_label = BodyLabel(self.project_name)
        self.name_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.name_label)

        # 项目信息
        info_text = self._get_project_info()
        self.info_label = BodyLabel(info_text)
        self.info_label.setStyleSheet("color: #666666; font-size: 12px;")
        layout.addWidget(self.info_label)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.run_btn = PrimaryPushButton("▶ 运行", self)
        self.run_btn.setFixedWidth(80)
        self.view_log_btn = ToolButton(FluentIcon.VIEW, self)
        self.view_log_btn.setToolTip("查看日志")
        self.open_folder_btn = ToolButton(FluentIcon.FOLDER, self)
        self.open_folder_btn.setToolTip("打开文件夹")
        self.delete_btn = ToolButton(FluentIcon.DELETE, self)
        self.delete_btn.setToolTip("删除项目")

        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.view_log_btn)
        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _get_project_info(self):
        """获取项目信息"""
        info_lines = []

        # 创建时间
        stat = os.stat(self.project_path)
        create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d")
        info_lines.append(f"创建: {create_time}")

        # 依赖包
        req_file = os.path.join(self.project_path, "requirements.txt")
        if os.path.exists(req_file):
            with open(req_file, 'r', encoding='utf-8') as f:
                packages = [line.strip() for line in f if line.strip()]
                if packages:
                    deps = ", ".join(packages[:2])  # 只显示前2个
                    if len(packages) > 2:
                        deps += f" +{len(packages) - 2} 个"
                    info_lines.append(f"依赖: {deps}")

        # 组件数量
        components_dir = os.path.join(self.project_path, "components")
        if os.path.exists(components_dir):
            comp_count = sum([len(files) for r, d, files in os.walk(components_dir)])
            info_lines.append(f"组件: {comp_count} 个")

        return "\n".join(info_lines)

    def update_status(self, is_running=False):
        """更新运行状态"""
        if is_running:
            self.run_btn.setText("⏹ 停止")
            self.run_btn.setEnabled(False)
        else:
            self.run_btn.setText("▶ 运行")
            self.run_btn.setEnabled(True)


class ExportedProjectsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("exported_projects_page")
        self.parent = parent
        self.export_dir = self._get_default_export_dir()
        self.running_projects = {}  # project_path -> thread
        self._setup_ui()

    def _get_default_export_dir(self):
        """获取默认导出目录"""
        # 从主程序配置获取，或使用默认路径
        default_dir = os.path.expanduser("projects")
        os.makedirs(default_dir, exist_ok=True)
        return default_dir

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 顶部工具栏
        toolbar_layout = QHBoxLayout()

        self.search_line = SearchLineEdit(self)
        self.search_line.setPlaceholderText("搜索项目...")
        self.search_line.setFixedWidth(300)

        self.refresh_btn = ToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setToolTip("刷新项目列表")
        self.refresh_btn.clicked.connect(self.load_projects)

        self.open_export_dir_btn = PrimaryPushButton("📁 打开导出目录", self)
        self.open_export_dir_btn.clicked.connect(self._open_export_directory)

        toolbar_layout.addWidget(self.search_line)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.open_export_dir_btn)
        toolbar_layout.addStretch()

        layout.addLayout(toolbar_layout)

        # 项目列表区域
        self.scroll_area = ScrollArea(self)
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setSpacing(15)
        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_widget)

        layout.addWidget(self.scroll_area)

        # 初始加载
        self.load_projects()

    def _open_export_directory(self):
        """打开导出目录"""
        import subprocess
        if os.name == 'nt':
            os.startfile(self.export_dir)
        else:
            subprocess.call(['xdg-open', self.export_dir])

    def load_projects(self):
        """加载所有导出的项目"""
        # 清空现有项目
        while self.scroll_layout.count() > 1:  # 保留 stretch
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 扫描导出目录
        if not os.path.exists(self.export_dir):
            return

        project_dirs = []
        for item in os.listdir(self.export_dir):
            item_path = os.path.join(self.export_dir, item)
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "model.workflow.json")):
                project_dirs.append(item_path)

        # 按创建时间排序（最新在前）
        project_dirs.sort(key=lambda x: os.path.getctime(x), reverse=True)

        # 创建项目卡片
        for project_path in project_dirs:
            card = ProjectCard(project_path, self)
            card.run_btn.clicked.connect(lambda _, p=project_path: self._run_project(p))
            card.view_log_btn.clicked.connect(lambda _, p=project_path: self._view_project_log(p))
            card.open_folder_btn.clicked.connect(lambda _, p=project_path: self._open_project_folder(p))
            card.delete_btn.clicked.connect(lambda _, p=project_path: self._delete_project(p))
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, card)

    def _run_project(self, project_path):
        """运行项目"""
        if project_path in self.running_projects:
            self.create_warning_info("项目已在运行", "请等待当前运行完成")
            return

        # 显示状态提示
        state_tooltip = StateToolTip("正在运行项目", "请稍候...", self)
        state_tooltip.move(self.width() - state_tooltip.width() - 20, 20)
        state_tooltip.show()

        # 启动运行线程
        thread = ProjectRunnerThread(project_path, self)
        self.running_projects[project_path] = (thread, state_tooltip)

        thread.finished.connect(
            lambda outputs, log: self._on_project_finished(project_path, outputs, log, state_tooltip))
        thread.error.connect(lambda err: self._on_project_error(project_path, err, state_tooltip))
        thread.start()

        # 更新卡片状态
        self._update_card_status(project_path, True)

    def _on_project_finished(self, project_path, outputs, log_content, state_tooltip):
        """项目运行完成"""
        state_tooltip.setContent("项目运行完成 ✅")
        state_tooltip.setState(True)

        # 保存输出（可选）
        output_file = os.path.join(project_path, "output.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(outputs, f, indent=2, ensure_ascii=False)

        # 保存日志
        log_file = os.path.join(project_path, "run.log")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(log_content)

        self.create_success_info("运行完成", f"项目 {os.path.basename(project_path)} 执行成功")
        self._cleanup_project_run(project_path)

    def _on_project_error(self, project_path, error, state_tooltip):
        """项目运行出错"""
        state_tooltip.setContent(f"运行失败 ❌\n{error}")
        state_tooltip.setState(True)
        self.create_error_info("运行失败", f"项目 {os.path.basename(project_path)} 执行失败:\n{error}")
        self._cleanup_project_run(project_path)

    def _cleanup_project_run(self, project_path):
        """清理运行状态"""
        if project_path in self.running_projects:
            del self.running_projects[project_path]
        self._update_card_status(project_path, False)

    def _update_card_status(self, project_path, is_running):
        """更新项目卡片状态"""
        for i in range(self.scroll_layout.count() - 1):  # 跳过 stretch
            card = self.scroll_layout.itemAt(i).widget()
            if isinstance(card, ProjectCard) and card.project_path == project_path:
                card.update_status(is_running)
                break

    def _view_project_log(self, project_path):
        """查看项目日志"""
        log_file = os.path.join(project_path, "run.log")
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            self._show_log_dialog(log_content)
        else:
            self.create_warning_info("无日志", "项目尚未运行或日志文件不存在")

    def _show_log_dialog(self, log_content):
        """显示日志对话框（支持 ANSI 颜色 + 深色主题）"""
        from PyQt5.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QPushButton
        from PyQt5.QtGui import QFont
        from PyQt5.QtCore import Qt

        # 转换 ANSI 为 HTML
        from app.utils.utils import ansi_to_html
        html_content = ansi_to_html(log_content)

        dialog = QDialog(self)
        dialog.setWindowTitle("项目运行日志")
        dialog.resize(800, 600)

        # 使用 QTextEdit 显示 HTML
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(html_content)

        # 深色主题样式
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

        # 等宽字体
        font = QFont("Consolas", 10)
        text_edit.setFont(font)

        # 按钮
        close_btn = PrimaryPushButton("关闭", self)
        close_btn.clicked.connect(dialog.accept)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(text_edit)
        layout.addWidget(close_btn)
        dialog.exec()

    def _open_project_folder(self, project_path):
        """打开项目文件夹"""
        import subprocess
        if os.name == 'nt':
            os.startfile(project_path)
        else:
            subprocess.call(['xdg-open', project_path])

    def _delete_project(self, project_path):
        """删除项目"""
        w = MessageBox(
            "确认删除",
            f"确定要删除项目 '{os.path.basename(project_path)}' 吗？\n此操作不可恢复！",
            self
        )
        if w.exec():
            try:
                import shutil
                shutil.rmtree(project_path)
                self.create_success_info("删除成功", "项目已删除")
                self.load_projects()  # 刷新列表
            except Exception as e:
                self.create_error_info("删除失败", f"错误: {str(e)}")

    def create_success_info(self, title, content):
        InfoBar.success(title, content, parent=self, duration=2000)

    def create_warning_info(self, title, content):
        InfoBar.warning(title, content, parent=self, duration=2000)

    def create_error_info(self, title, content):
        InfoBar.error(title, content, parent=self, duration=3000)