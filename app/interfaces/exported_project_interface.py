# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import socket
from datetime import datetime
from typing import Optional

import psutil
from PyQt5.QtCore import QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDialog, QTextEdit
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, PrimaryPushButton,
    ToolButton, FluentIcon, SearchLineEdit, InfoBar,
    MessageBox, StateToolTip, HyperlinkButton
)

from app.utils.utils import ansi_to_html
from app.widgets.service_request_dialog import ServiceRequestDialog

# 全局已用端口集合（避免冲突）
USED_PORTS = set()


def find_available_port(start=8000, end=9000):
    """查找可用端口"""
    for port in range(start, end + 1):
        if port not in USED_PORTS:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("0.0.0.0", port))
                USED_PORTS.add(port)
                return port
            except OSError:
                continue
    raise RuntimeError(f"无法在 {start}-{end} 范围内找到可用端口")


def release_port(port):
    """释放端口"""
    USED_PORTS.discard(port)


class ProjectRunnerThread(QThread):
    """在独立线程中运行项目"""
    finished = pyqtSignal(dict, str)
    error = pyqtSignal(str)

    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        with open(os.path.join(project_path, "model.workflow.json"), 'r', encoding='utf-8') as f:
            self.python_exe = json.load(f).get("runtime").get("environment_exe")

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
                with open(output_file, 'r', encoding='utf-8') as f:
                    outputs = json.load(f)

            log_content = result.stdout + "\n" + result.stderr
            self.finished.emit(outputs, log_content)

        except Exception as e:
            self.error.emit(str(e))


class MicroserviceManager:
    def __init__(self):
        self.services = {}
        self._restore_services()  # 启动时尝试恢复

    def start_service(self, project_path: str) -> str:
        """启动微服务，返回 URL"""
        if project_path in self.services:
            return self.services[project_path]["url"]

        # 检查是否存在 api_server.py
        service_script = os.path.join(project_path, "api_server.py")
        if not os.path.exists(service_script):
            raise FileNotFoundError("未找到微服务代码 (api_server.py)")

        # 分配端口
        port = find_available_port()
        url = f"http://0.0.0.0:{port}/run"

        # 日志文件路径
        log_file = os.path.join(project_path, "service.log")
        # 获取项目python_exe
        with open(os.path.join(project_path, "model.workflow.json"), 'r', encoding='utf-8') as f:
            python_exe = json.load(f).get("runtime").get("environment_exe")
        cmd = [python_exe, "api_server.py", "--port", str(port)]
        with open(log_file, 'w', encoding='utf-8') as log_f:
            process = subprocess.Popen(
                cmd,
                cwd=project_path,
                stdout=log_f,
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                encoding='utf-8'
            )

        self.services[project_path] = {
            "process": process,
            "port": port,
            "url": url,
            "log_file": log_file  # 记录日志路径
        }
        return url

    def _restore_services(self):
        """启动时尝试恢复已存在的服务"""
        if not os.path.exists("projects"):
            return

        for item in os.listdir("projects"):
            project_path = os.path.join("projects", item)
            if not os.path.isdir(project_path):
                continue

            log_file = os.path.join(project_path, "service.log")
            spec_file = os.path.join(project_path, "project_spec.json")
            if not (os.path.exists(log_file) and os.path.exists(spec_file)):
                continue

            # 检查日志中是否有启动成功的记录
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read()
                if "Uvicorn running on" not in log_content:
                    continue

                # 从日志中提取端口（简单正则）
                import re
                port_match = re.search(r"Uvicorn running on http://[^:]+:(\d+)", log_content)
                if not port_match:
                    continue
                port = int(port_match.group(1))

                # 检查端口是否仍在被占用
                if not self._is_port_in_use(port):
                    continue

                # 检查是否是我们的服务（通过命令行参数）
                is_our_service = False
                for proc in psutil.process_iter(['pid', 'cmdline']):
                    try:
                        cmdline = proc.info['cmdline']
                        if (cmdline and
                            'api_server.py' in ' '.join(cmdline) and
                            f'--port {port}' in ' '.join(cmdline) and
                            project_path in ' '.join(cmdline)):
                            is_our_service = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                if is_our_service:
                    url = f"http://0.0.0.0:{port}/run"
                    self.services[project_path] = {
                        "process": None,  # 无法获取原进程对象
                        "port": port,
                        "url": url,
                        "log_file": log_file
                    }
                    USED_PORTS.add(port)
            except Exception as e:
                print(f"恢复服务失败 {project_path}: {e}")

    def _is_port_in_use(self, port):
        """检查端口是否被占用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('0.0.0.0', port)) == 0

    def stop_service(self, project_path: str):
        """停止微服务"""
        if project_path not in self.services:
            return

        service = self.services[project_path]
        process = service["process"]
        port = service["port"]

        try:
            if os.name == 'nt':
                process.terminate()
                process.wait(timeout=5)
            else:
                process.kill()
        except:
            pass

        release_port(port)
        del self.services[project_path]

    def is_running(self, project_path: str) -> bool:
        return project_path in self.services

    def get_url(self, project_path: str) -> Optional[str]:
        return self.services.get(project_path, {}).get("url")


# 全局服务管理器
SERVICE_MANAGER = MicroserviceManager()


class ProjectCard(CardWidget):
    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.project_name = os.path.basename(project_path)
        self.service_url_label = None  # 用于显示服务链接
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

        # 服务 URL（初始隐藏）
        self.service_url_label = HyperlinkButton("", "服务地址")
        self.service_url_label.setVisible(False)
        self.service_url_label.setHidden(True)
        layout.addWidget(self.service_url_label)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.run_btn = PrimaryPushButton(text="运行", icon=FluentIcon.PLAY, parent=self)
        self.run_btn.setFixedWidth(80)

        self.service_btn = PrimaryPushButton(text="上线", icon=FluentIcon.LINK, parent=self)
        self.service_btn.setFixedWidth(80)

        self.request_btn = PrimaryPushButton(text="请求", icon=FluentIcon.SEND, parent=self)
        self.request_btn.setFixedWidth(80)
        self.request_btn.setEnabled(False)  # 初始禁用
        self.request_btn.clicked.connect(lambda: self._open_request_dialog())

        self.view_log_btn = ToolButton(FluentIcon.VIEW, self)
        self.view_log_btn.setToolTip("查看日志")
        self.open_folder_btn = ToolButton(FluentIcon.FOLDER, self)
        self.open_folder_btn.setToolTip("打开文件夹")
        self.delete_btn = ToolButton(FluentIcon.DELETE, self)
        self.delete_btn.setToolTip("删除项目")

        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.service_btn)
        btn_layout.addWidget(self.request_btn)  # 添加请求按钮
        btn_layout.addWidget(self.view_log_btn)
        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 检查是否有微服务
        self._update_service_button()

    def _update_service_button(self):
        if SERVICE_MANAGER.is_running(self.project_path):
            self.service_btn.setText("下线")
            self.service_btn.setIcon(FluentIcon.PAUSE)
            self.request_btn.setEnabled(True)  # 启用请求按钮
            url = SERVICE_MANAGER.get_url(self.project_path)
            if url:
                self.service_url_label.setUrl(QUrl(url))
                self.service_url_label.setText(url)
                self.service_url_label.setVisible(True)
        else:
            self.service_btn.setText("上线")
            self.service_btn.setIcon(FluentIcon.LINK)
            self.request_btn.setEnabled(False)  # 禁用请求按钮
            self.service_url_label.setVisible(False)

    def _get_project_info(self):
        info_lines = []
        stat = os.stat(self.project_path)
        create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d")
        info_lines.append(f"创建: {create_time}")

        req_file = os.path.join(self.project_path, "requirements.txt")
        if os.path.exists(req_file):
            with open(req_file, 'r', encoding='utf-8') as f:
                packages = [line.strip() for line in f if line.strip()]
                if packages:
                    deps = ", ".join(packages[:5])
                    if len(packages) > 5:
                        deps += f" +{len(packages) - 5} 个"
                    info_lines.append(f"依赖: {deps}")

        components_dir = os.path.join(self.project_path, "components")
        if os.path.exists(components_dir):
            comp_count = sum([len(files) for r, d, files in os.walk(components_dir)])
            info_lines.append(f"组件: {comp_count} 个")

        # 检查是否有微服务
        if os.path.exists(os.path.join(self.project_path, "api_server.py")):
            info_lines.append("支持微服务")

        return "\n".join(info_lines)

    def _open_request_dialog(self):
        """打开服务请求对话框"""
        if not SERVICE_MANAGER.is_running(self.project_path):
            InfoBar.warning("服务未运行", "请先点击'上线'启动服务", parent=self.parent())
            return

        url = SERVICE_MANAGER.get_url(self.project_path)
        if not url:
            return

        dialog = ServiceRequestDialog(self.project_path, url, self.parent())
        dialog.exec()

    def update_status(self, is_running=False):
        if is_running:
            self.run_btn.setText("停止")
            self.run_btn.setIcon(FluentIcon.PAUSE)
            self.run_btn.setEnabled(False)
        else:
            self.run_btn.setText("运行")
            self.run_btn.setIcon(FluentIcon.PLAY)
            self.run_btn.setEnabled(True)


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

        self.load_projects()

    def _open_export_directory(self):
        if os.name == 'nt':
            os.startfile(self.export_dir)
        else:
            subprocess.call(['xdg-open', self.export_dir])

    def load_projects(self):
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not os.path.exists(self.export_dir):
            return

        project_dirs = []
        for item in os.listdir(self.export_dir):
            item_path = os.path.join(self.export_dir, item)
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "model.workflow.json")):
                project_dirs.append(item_path)

        project_dirs.sort(key=lambda x: os.path.getctime(x), reverse=True)

        for project_path in project_dirs:
            card = ProjectCard(project_path, self)
            card.run_btn.clicked.connect(lambda _, p=project_path: self._run_project(p))
            card.service_btn.clicked.connect(lambda _, p=project_path: self._toggle_service(p))
            card.view_log_btn.clicked.connect(lambda _, p=project_path: self._view_project_log(p))
            card.open_folder_btn.clicked.connect(lambda _, p=project_path: self._open_project_folder(p))
            card.delete_btn.clicked.connect(lambda _, p=project_path: self._delete_project(p))
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, card)

    def _toggle_service(self, project_path):
        """切换微服务状态"""
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
        """更新卡片服务状态"""
        for i in range(self.scroll_layout.count() - 1):
            card = self.scroll_layout.itemAt(i).widget()
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

        thread = ProjectRunnerThread(project_path, self)
        self.running_projects[project_path] = (thread, state_tooltip)

        thread.finished.connect(
            lambda outputs, log: self._on_project_finished(project_path, outputs, log, state_tooltip))
        thread.error.connect(lambda err: self._on_project_error(project_path, err, state_tooltip))
        thread.start()

        self._update_card_status(project_path, True)

    def _on_project_finished(self, project_path, outputs, log_content, state_tooltip):
        state_tooltip.setContent("项目运行完成 ✅")
        state_tooltip.setState(True)

        output_file = os.path.join(project_path, "output.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(outputs, f, indent=2, ensure_ascii=False)

        log_file = os.path.join(project_path, "run.log")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(log_content)

        self.create_success_info("运行完成", f"项目 {os.path.basename(project_path)} 执行成功")
        self._cleanup_project_run(project_path)

    def _on_project_error(self, project_path, error, state_tooltip):
        state_tooltip.setContent(f"运行失败 ❌\n{error}")
        state_tooltip.setState(True)
        self.create_error_info("运行失败", f"项目 {os.path.basename(project_path)} 执行失败:\n{error}")
        self._cleanup_project_run(project_path)

    def _cleanup_project_run(self, project_path):
        if project_path in self.running_projects:
            del self.running_projects[project_path]
        self._update_card_status(project_path, False)

    def _update_card_status(self, project_path, is_running):
        for i in range(self.scroll_layout.count() - 1):
            card = self.scroll_layout.itemAt(i).widget()
            if isinstance(card, ProjectCard) and card.project_path == project_path:
                card.update_status(is_running)
                break

    def _view_project_log(self, project_path):
        """查看项目日志（合并运行日志 + 服务日志）"""
        all_logs = []

        # 1. 读取项目运行日志 (run.log)
        run_log = os.path.join(project_path, "run.log")
        if os.path.exists(run_log):
            with open(run_log, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    all_logs.append(("项目运行日志", content))

        # 2. 读取微服务日志 (service.log)
        service_log = os.path.join(project_path, "service.log")
        if os.path.exists(service_log):
            with open(service_log, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    all_logs.append(("微服务日志", content))

        if not all_logs:
            self.create_warning_info("无日志", "项目尚未运行或日志文件不存在")
            return

        # 合并日志内容（带标题分隔）
        combined_content = ""
        for title, content in all_logs:
            combined_content += f"\n{'=' * 60}\n{title}\n{'=' * 60}\n\n"
            combined_content += content + "\n"

        self._show_log_dialog(combined_content)

    def _show_log_dialog(self, log_content):
        html_content = ansi_to_html(log_content)
        # 简化：直接显示文本（如需 ANSI 支持再加）
        dialog = QDialog(self)
        dialog.setWindowTitle("项目运行日志")
        dialog.resize(800, 600)

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
        font = QFont("Consolas", 10)
        text_edit.setFont(font)

        close_btn = PrimaryPushButton("关闭", self)
        close_btn.clicked.connect(dialog.accept)

        layout = QVBoxLayout(dialog)
        layout.addWidget(text_edit)
        layout.addWidget(close_btn)
        dialog.exec()

    def _open_project_folder(self, project_path):
        if os.name == 'nt':
            os.startfile(project_path)
        else:
            subprocess.call(['xdg-open', project_path])

    def _delete_project(self, project_path):
        w = MessageBox(
            "确认删除",
            f"确定要删除项目 '{os.path.basename(project_path)}' 吗？\n此操作不可恢复！",
            self
        )
        if w.exec():
            try:
                # 如果服务在运行，先停止
                if SERVICE_MANAGER.is_running(project_path):
                    SERVICE_MANAGER.stop_service(project_path)

                import shutil
                shutil.rmtree(project_path)
                self.create_success_info("删除成功", "项目已删除")
                self.load_projects()
            except Exception as e:
                self.create_error_info("删除失败", f"错误: {str(e)}")

    def create_success_info(self, title, content):
        InfoBar.success(title, content, parent=self, duration=2000)

    def create_warning_info(self, title, content):
        InfoBar.warning(title, content, parent=self, duration=2000)

    def create_error_info(self, title, content):
        InfoBar.error(title, content, parent=self, duration=3000)