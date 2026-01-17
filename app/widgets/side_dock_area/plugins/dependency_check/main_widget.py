# -*- coding: utf-8 -*-
import json
import re
import uuid
from urllib.parse import urlparse

try:
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
except ImportError:
    SpecifierSet = None
    Version = None

from PyQt5.QtCore import Qt, QTimer, QProcess, QSize
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QHeaderView, QAbstractItemView, QTableWidgetItem
from qfluentwidgets import (
    TableWidget, PrimaryPushButton, TransparentToolButton,
    StrongBodyLabel, FluentIcon, InfoBar, CaptionLabel, IndeterminateProgressRing, InfoBarPosition
)

from app.interfaces.package_manager_interface import PackageListThread
from app.scan_components import ComponentScanner
from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition
from app.widgets.side_dock_area.plugins.dependency_check.remote_install_thread import RemoteInstallThread


class DependencyToolWindow(ToolWindow):
    name = "依赖检查"
    icon = get_icon("依赖包")
    default_position = DockPosition.TOP

    def setup_ui(self):
        self.config = Settings.get_instance()
        self._process = None
        self._remote_thread = None
        self.installed_pkgs = {}
        self.current_run_id = None  # 记录当前日志会话 ID

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(8)

        # --- 顶部标题栏 ---
        header_layout = QHBoxLayout()
        title_v_layout = QVBoxLayout()
        self.title_label = StrongBodyLabel("流程依赖分析")
        self.status_label = CaptionLabel("正在初始化...")
        title_v_layout.addWidget(self.title_label)
        title_v_layout.addWidget(self.status_label)

        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(28, 28)
        self.loading_ring.hide()

        header_layout.addLayout(title_v_layout)
        header_layout.addWidget(self.loading_ring)
        header_layout.addStretch()

        self.refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setToolTip("重新扫描环境")
        self.refresh_btn.clicked.connect(self.run_check)

        self.install_all_btn = PrimaryPushButton(FluentIcon.DOWNLOAD, "修复", self)
        self.install_all_btn.setFixedSize(120, 30)
        self.install_all_btn.hide()
        self.install_all_btn.clicked.connect(self.install_all_missing)

        header_layout.addWidget(self.refresh_btn)
        header_layout.addWidget(self.install_all_btn)
        self.main_layout.addLayout(header_layout)

        # --- 表格配置 ---
        self.table = TableWidget(self)
        self.table.setMinimumWidth(400)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["包名", "需求汇总", "当前版本", "状态", "操作"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 80)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 50)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setBorderVisible(False)
        self.table.setShowGrid(False)
        self.main_layout.addWidget(self.table)

        QTimer.singleShot(500, self.run_check)

    def _get_log_window(self):
        """安全获取 LogToolWindow 实例"""
        return getattr(self.homepage, 'log_window', None)

    def get_current_python_exe(self):
        return self.homepage.env_data

    def run_check(self):
        if self.loading_ring.isVisible(): return
        env_data = self.get_current_python_exe()
        if not env_data:
            self.status_label.setText("未选择环境")
            return

        self.loading_ring.show()
        self.refresh_btn.setEnabled(False)
        self.thread = PackageListThread(env_data)
        self.thread.packages_loaded.connect(self._on_env_loaded)
        self.thread.error_occurred.connect(self._on_env_error)
        self.thread.start()

    def _on_env_loaded(self, python_version, stdout):
        try:
            match = re.search(r"\[.*\]", stdout, re.S)
            data = json.loads(match.group(0)) if match else []
            self.installed_pkgs = {p['name'].lower().replace('_', '-'): p['version'] for p in data}
            self.compare_dependencies()
        finally:
            self.loading_ring.hide()
            self.refresh_btn.setEnabled(True)

    def _on_env_error(self, e):
        self.loading_ring.hide()
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(f"环境加载失败: {str(e)}")

    def compare_dependencies(self):
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        req_summary = {}
        nodes = self.homepage.graph.all_nodes()

        for node in nodes:
            if "StatusDynamicNode_" not in node.model.type_: continue
            comp_cls = ComponentScanner().get_component_by_uuid(node.uuid)
            if not comp_cls or not hasattr(comp_cls, 'requirements'): continue

            reqs = [r.strip() for r in comp_cls.requirements.split(",") if r.strip()]
            for req_str in reqs:
                match = re.match(r"^([a-zA-Z0-9\-_\.]+)(.*)$", req_str)
                if match:
                    name = match.group(1).lower().replace('_', '-')
                    spec = match.group(2).strip()
                    if name not in req_summary: req_summary[name] = {"node_data": []}
                    req_summary[name]["node_data"].append({"node_name": node.name(), "spec": spec, "node_obj": node})

        fix_list = []
        error_count = 0

        for row, (name, info) in enumerate(req_summary.items()):
            self.table.insertRow(row)
            current_v_str = self.installed_pkgs.get(name)
            combined_spec_str = ",".join(sorted(list(set(d['spec'] for d in info['node_data'] if d['spec']))))

            status_text, status_color, action_widget = "就绪", Qt.darkGreen, None

            if SpecifierSet and Version:
                try:
                    c_spec = SpecifierSet(combined_spec_str)
                    if not current_v_str:
                        status_text, status_color = "缺失", Qt.red
                        fix_list.append(f"{name}{combined_spec_str}")
                        action_widget = self._make_btn(FluentIcon.DOWNLOAD, "安装", name, combined_spec_str)
                    elif not c_spec.contains(current_v_str, prereleases=True):
                        status_text, status_color = "不匹配", QColor("#D83B01")
                        fix_list.append(f"{name}{combined_spec_str}")
                        action_widget = self._make_btn(FluentIcon.SYNC, "修复", name, combined_spec_str)
                    else:
                        action_widget = self._make_ok_icon()
                except:
                    status_text, status_color = "格式错误", Qt.red

            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(combined_spec_str or "无限制"))
            self.table.setItem(row, 2, QTableWidgetItem(current_v_str or "未安装"))
            s_item = QTableWidgetItem(status_text)
            s_item.setForeground(status_color)
            self.table.setItem(row, 3, s_item)
            if action_widget: self.table.setCellWidget(row, 4, action_widget)
            if status_text != "就绪": error_count += 1

        self.table.setUpdatesEnabled(True)
        self._update_ui_state(error_count, fix_list)

    def _make_btn(self, icon, tip, name, spec):
        btn = TransparentToolButton(icon, self)
        btn.setIconSize(QSize(14, 14))
        btn.clicked.connect(lambda: self.install_packages([f"{name}{spec}"]))
        return btn

    def _make_ok_icon(self):
        btn = TransparentToolButton(FluentIcon.COMPLETED, self)
        btn.setIconSize(QSize(14, 14))
        btn.setEnabled(False)
        return btn

    def _update_ui_state(self, error_count, fix_list):
        self._temp_fix_list = fix_list
        if error_count > 0:
            self.status_label.setText(f"环境异常: {error_count} 项")
            self.status_label.setStyleSheet("color: #E81123;")
            self.install_all_btn.setVisible(len(fix_list) > 0)
        else:
            self.status_label.setText("环境依赖检查通过")
            self.status_label.setStyleSheet("color: #107C10;")
            self.install_all_btn.hide()

    # --- 安装逻辑核心 ---

    def install_packages(self, pkg_specs):
        env_data = self.get_current_python_exe()
        if not env_data: return

        # 1. 构造 Pip 命令 (禁用进度条以防乱码)
        cmd = ["-m", "pip", "install"] + pkg_specs + ["--upgrade", "--progress-bar", "off"]
        mirrors = self.config.mirrors.value
        if mirrors:
            for m in mirrors:
                cmd.extend(["--extra-index-url", m, "--trusted-host", urlparse(m).hostname])

        # 2. 初始化日志
        self.current_run_id = f"依赖修复@{uuid.uuid4().hex[:8]}"
        log_win = self._get_log_window()
        if log_win:
            log_win.start_run(self.current_run_id)
            log_win.push_log(self.current_run_id, f">>> 开始安装: {' '.join(pkg_specs)}")

        self.loading_ring.show()
        self.status_label.setText("正在执行安装，详情请查看日志窗口...")
        self.setEnabled(False)

        if isinstance(env_data, dict) and env_data.get('type') == 'ssh':
            self._remote_thread = RemoteInstallThread(env_data, cmd)
            self._remote_thread.line_received.connect(self._on_log_received)
            self._remote_thread.finished_signal.connect(self._on_remote_install_finished)
            self._remote_thread.start()
        else:
            self._process = QProcess(self)
            # 1. 强制设置环境变量，禁用缓冲
            env = self._process.processEnvironment()
            env.insert("PYTHONUNBUFFERED", "1")
            self._process.setProcessEnvironment(env)
            self._process.setProcessChannelMode(QProcess.MergedChannels)
            # 2. 增加启动失败的监听
            self._process.errorOccurred.connect(lambda err: self._on_log_received(f"进程错误: {err}\n"))
            self._process.readyReadStandardOutput.connect(self._handle_local_stdout)
            self._process.finished.connect(self._on_install_finished)

            self._process.start(str(env_data.get("path")), cmd)

    def _handle_local_stdout(self):
        """处理本地进程输出"""
        data = self._process.readAllStandardOutput().data().decode('utf-8', 'ignore')
        for line in data.splitlines():
            self._on_log_received(line + "\n")

    def _on_log_received(self, line):
        """统一日志分发"""
        if not line.strip(): return
        log_win = self._get_log_window()
        if log_win:
            log_win.push_log(self.current_run_id, line)

    def _on_remote_install_finished(self, success, message):
        self.setEnabled(True)
        self.loading_ring.hide()
        log_win = self._get_log_window()
        if not success:
            if log_win: log_win.on_error(self.current_run_id)
            self.status_label.setText("远程安装失败")
        else:
            if log_win: log_win.on_finished(self.current_run_id)
            self.status_label.setText("安装完成，正在刷新...")
            QTimer.singleShot(1000, self.run_check)

    def _on_install_finished(self):
        self.setEnabled(True)
        self.loading_ring.hide()
        log_win = self._get_log_window()
        if self._process.exitCode() != 0:
            if log_win: log_win.on_error(self.current_run_id)
            self.status_label.setText("本地安装失败")
        else:
            if log_win: log_win.on_finished(self.current_run_id)
            self.status_label.setText("安装完成，正在刷新...")
            QTimer.singleShot(1000, self.run_check)

    def install_all_missing(self):
        if hasattr(self, '_temp_fix_list') and self._temp_fix_list:
            self.install_packages(self._temp_fix_list)