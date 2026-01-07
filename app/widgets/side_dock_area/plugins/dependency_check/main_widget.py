# -*- coding: utf-8 -*-
import json
import platform
import re
from urllib.parse import urlparse
from loguru import logger
from PyQt5.QtCore import Qt, QTimer, QProcess, QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QHeaderView, QAbstractItemView, QTableWidgetItem, QFrame
from qfluentwidgets import (
    TableWidget, PrimaryPushButton, TransparentToolButton,
    BodyLabel, StrongBodyLabel, FluentIcon, InfoBar, InfoBarPosition,
    StateToolTip, CaptionLabel, IndeterminateProgressRing
)

from app.interfaces.package_manager_interface import PackageListThread
from app.scan_components import ComponentScanner
from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class DependencyToolWindow(ToolWindow):
    name = "依赖检查"
    icon = get_icon("依赖包")
    default_position = DockPosition.TOP

    def setup_ui(self):
        # 1. 基础管理类初始化
        self.mgr = self.homepage.parent.package_manager.mgr
        self.config = Settings.get_instance()
        self._process = None
        self.installed_pkgs = {}

        # 2. 整体布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(8)

        # --- 顶部标题栏 ---
        header_layout = QHBoxLayout()
        title_v_layout = QVBoxLayout()
        self.title_label = StrongBodyLabel("流程依赖分析")
        self.status_label = CaptionLabel("正在初始化...")
        self.status_label.setStyleSheet("color: #808080;")
        title_v_layout.addWidget(self.title_label)
        title_v_layout.addWidget(self.status_label)

        # 加载动画
        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(16, 16)
        self.loading_ring.setStrokeWidth(2)
        self.loading_ring.hide()

        header_layout.addLayout(title_v_layout)
        header_layout.addWidget(self.loading_ring)
        header_layout.addStretch()

        self.refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setToolTip("重新扫描环境")
        self.refresh_btn.clicked.connect(self.run_check)

        self.install_all_btn = PrimaryPushButton(FluentIcon.DOWNLOAD, "修复", self)
        self.install_all_btn.setFixedSize(90, 30)
        self.install_all_btn.hide()
        self.install_all_btn.clicked.connect(self.install_all_missing)

        header_layout.addWidget(self.refresh_btn)
        header_layout.addWidget(self.install_all_btn)
        self.main_layout.addLayout(header_layout)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: rgba(0, 0, 0, 0.08);")
        self.main_layout.addWidget(line)

        # --- 依赖表格 (4列版) ---
        self.table = TableWidget(self)
        self.table.setMinimumWidth(350)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["包名", "当前环境", "状态", "操作"])

        # 严格控制列宽逻辑，防止刷新抖动
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 包名：自动填充剩余空间
        header.setSectionResizeMode(1, QHeaderView.Fixed)  # 当前版本：固定
        header.resizeSection(1, 100)
        header.setSectionResizeMode(2, QHeaderView.Fixed)  # 状态：固定
        header.resizeSection(2, 80)
        header.setSectionResizeMode(3, QHeaderView.Fixed)  # 操作：固定
        header.resizeSection(3, 60)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setBorderVisible(False)
        self.table.setShowGrid(False)  # 隐藏网格线，更符合现代 IDE 审美
        self.main_layout.addWidget(self.table)

        # 3. 信号与初始化
        QTimer.singleShot(500, self.run_check)
        self.homepage.env_changed.connect(self.run_check)

    def get_current_python_exe(self):
        return self.homepage.get_current_python_exe()

    def run_check(self):
        """执行检查流程"""
        if self.loading_ring.isVisible(): return

        self.loading_ring.show()
        self.status_label.setText("正在对比环境依赖...")
        self.refresh_btn.setEnabled(False)

        python_exe = self.get_current_python_exe()
        self.thread = PackageListThread(python_exe)
        self.thread.packages_loaded.connect(self._on_env_loaded)
        self.thread.error_occurred.connect(self._on_env_error)
        self.thread.start()

    def _on_env_loaded(self, stdout):
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
        self.status_label.setText("读取失败")
        InfoBar.error("环境异常", f"无法获取包列表: {str(e)}", duration=3000, position=InfoBarPosition.TOP,
                      parent=self.homepage)

    def compare_dependencies(self):
        """对比并渲染表格"""
        self.table.setUpdatesEnabled(False)  # 停止 UI 更新，消除刷新时的闪烁感
        self.table.setRowCount(0)

        req_summary = {}
        nodes = self.homepage.graph.all_nodes()

        # 1. 汇总逻辑 (在后台判断要求，但 UI 不显示)
        for node in nodes:
            if "StatusDynamicNode_" not in node.model.type_: continue
            comp_cls = ComponentScanner().get_component_by_uuid(node.uuid)
            if not comp_cls or not hasattr(comp_cls, 'requirements'): continue

            reqs = [r.strip() for r in comp_cls.requirements.split(",") if r.strip()]
            for req_str in reqs:
                match = re.match(r"^([a-zA-Z0-9\-_]+)(.*)$", req_str)
                if match:
                    name = match.group(1).lower().replace('_', '-')
                    spec = match.group(2).strip() or "*"
                    if name not in req_summary:
                        req_summary[name] = {"specs": set(), "nodes": set()}
                    req_summary[name]["specs"].add(spec)
                    req_summary[name]["nodes"].add(node.name)

        # 2. 渲染逻辑
        missing_list = []
        for row, (name, info) in enumerate(req_summary.items()):
            self.table.insertRow(row)

            current_v = self.installed_pkgs.get(name)

            # --- 列0：包名 ---
            self.table.setItem(row, 0, QTableWidgetItem(name))

            # --- 列1：当前版本 ---
            curr_item = QTableWidgetItem(current_v or "Not Found")
            curr_item.setTextAlignment(Qt.AlignCenter)
            if not current_v:
                curr_item.setForeground(Qt.gray)
            self.table.setItem(row, 1, curr_item)

            # --- 列2：状态 ---
            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignCenter)

            if not current_v:
                status_item.setText("缺失")
                status_item.setForeground(Qt.red)
                # 操作列按钮
                btn = TransparentToolButton(FluentIcon.DOWNLOAD, self)
                btn.setIconSize(QSize(12, 12))
                btn.setToolTip("安装此包")
                btn.clicked.connect(lambda chk, n=name: self.install_packages([n]))
                self.table.setCellWidget(row, 3, btn)
                missing_list.append(name)
            elif len(info["specs"]) > 1:
                status_item.setText("冲突")
                status_item.setForeground(Qt.darkYellow)
                # 操作列信息按钮
                info_btn = TransparentToolButton(FluentIcon.INFO, self)
                info_btn.setIconSize(QSize(12, 12))
                info_btn.setToolTip(
                    f"多个节点需求版本不一致: {', '.join(info['specs'])}\n涉及节点: {', '.join(info['nodes'])}")
                self.table.setCellWidget(row, 3, info_btn)
            else:
                status_item.setText("就绪")
                status_item.setForeground(Qt.darkGreen)
                ok_icon = TransparentToolButton(FluentIcon.COMPLETED, self)
                ok_icon.setIconSize(QSize(12, 12))
                ok_icon.setEnabled(False)
                self.table.setCellWidget(row, 3, ok_icon)

            self.table.setItem(row, 2, status_item)

        self.table.setUpdatesEnabled(True)  # 恢复 UI 更新

        # 底部状态条美化
        if missing_list:
            self.status_label.setText(f"发现 {len(missing_list)} 个缺失依赖，建议点击一键修复")
            self.status_label.setStyleSheet("color: #E81123; font-weight: 500;")
            self.install_all_btn.show()
        else:
            self.status_label.setText("当前环境与流程依赖完全匹配")
            self.status_label.setStyleSheet("color: #107C10;")
            self.install_all_btn.hide()

        self._temp_missing_list = missing_list

    def install_packages(self, pkg_names):
        """执行安装任务"""
        python_exe = self.get_current_python_exe()

        cmd = ["-m", "pip", "install"]
        cmd.extend(pkg_names)

        # 镜像源处理
        mirrors = self.config.mirrors.value
        if mirrors:
            for m in mirrors:
                cmd.extend(["--extra-index-url", m, "--trusted-host", urlparse(m).hostname])

        # 显示全局进度条（IDE样式）
        self.tip = StateToolTip("正在安装依赖...", "正在调用 pip 进行部署", self.homepage)
        self.tip.move(self.homepage.width() - self.tip.width() - 30, 50)
        self.tip.show()

        self.setEnabled(False)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self.mgr._get_hidden_window_environment())

        self._process.finished.connect(self._on_install_finished)
        self._process.start(str(python_exe), cmd)

    def _on_install_finished(self):
        exit_code = self._process.exitCode()
        self.setEnabled(True)
        self.tip.setState(True)

        if exit_code == 0:
            self.tip.setContent("安装成功！正在刷新环境...")
            InfoBar.success("任务完成", "依赖包已成功部署到当前环境",
                            duration=2500, position=InfoBarPosition.TOP, parent=self.homepage)
            # 延时刷新，给文件系统一点索引时间
            QTimer.singleShot(1500, self.run_check)
        else:
            self.tip.setContent("操作失败")
            InfoBar.error("安装失败", "PIP 返回了非零状态码，请检查网络或日志",
                          duration=5000, position=InfoBarPosition.TOP, parent=self.homepage)

    def install_all_missing(self):
        if hasattr(self, '_temp_missing_list') and self._temp_missing_list:
            self.install_packages(self._temp_missing_list)