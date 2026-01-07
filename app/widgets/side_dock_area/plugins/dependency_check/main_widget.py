# -*- coding: utf-8 -*-
import json
import platform
import re
from urllib.parse import urlparse

# 依赖校验核心库
try:
    from packaging.specifiers import SpecifierSet, InvalidSpecifier
    from packaging.version import Version, InvalidVersion
except ImportError:
    SpecifierSet = None
    Version = None

from PyQt5.QtCore import Qt, QTimer, QProcess, QSize
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QHeaderView, QAbstractItemView, QTableWidgetItem, QFrame
from qfluentwidgets import (
    TableWidget, PrimaryPushButton, TransparentToolButton,
    StrongBodyLabel, FluentIcon, InfoBar, InfoBarPosition,
    StateToolTip, CaptionLabel, IndeterminateProgressRing, InfoBadgePosition, InfoBadge
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
        self.mgr = self.homepage.parent.package_manager.mgr
        self.config = Settings.get_instance()
        self._process = None
        self.installed_pkgs = {}
        self.badge = None

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
        self.loading_ring.setFixedSize(16, 16)
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
        self.table.setMinimumWidth(350)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["包名", "需求汇总", "当前版本", "状态", "操作"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 80)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, 90)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, 40)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setBorderVisible(False)
        self.table.setShowGrid(False)
        self.main_layout.addWidget(self.table)

        QTimer.singleShot(500, self.run_check)
        if hasattr(self.homepage, 'env_changed'):
            self.homepage.env_changed.connect(self.run_check)

    def get_current_python_exe(self):
        return self.homepage.get_current_python_exe()

    def run_check(self):
        if self.loading_ring.isVisible(): return
        self.loading_ring.show()
        self.refresh_btn.setEnabled(False)
        self.thread = PackageListThread(self.get_current_python_exe())
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

    def _analyze_conflict_sources(self, node_data_list):
        """分析并找出导致死锁的冲突节点"""
        if not SpecifierSet: return []
        conflicting_nodes = []
        try:
            # 1. 检查互斥的 ==
            exact_map = {}
            for d in node_data_list:
                s_set = SpecifierSet(d['spec'])
                for s in s_set:
                    if s.operator == "==":
                        v = Version(s.version)
                        if v not in exact_map: exact_map[v] = []
                        exact_map[v].append(d)

            if len(exact_map) > 1:
                for nodes in exact_map.values(): conflicting_nodes.extend(nodes)
                return conflicting_nodes

            # 2. 检查边界死锁 (Lower > Upper)
            h_val, l_val, h_data, l_data = None, None, None, None
            for d in node_data_list:
                s_set = SpecifierSet(d['spec'])
                for s in s_set:
                    v = Version(s.version)
                    if s.operator in (">", ">="):
                        if h_val is None or v > h_val: h_val, h_data = v, d
                    elif s.operator in ("<", "<="):
                        if l_val is None or v < l_val: l_val, l_data = v, d
            if h_val and l_val and h_val > l_val:
                return [h_data, l_data]

            # 3. 检查单点与范围冲突
            if exact_map:
                ev = list(exact_map.keys())[0]
                for d in node_data_list:
                    if Version(ev.public) not in SpecifierSet(d['spec']):
                        conflicting_nodes.append(d)
                        conflicting_nodes.extend(exact_map[ev])
                return conflicting_nodes
        except:
            pass
        return []

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
                    if name not in req_summary:
                        req_summary[name] = {"node_data": []}
                    # 记录节点对象以便跳转
                    req_summary[name]["node_data"].append({
                        "node_name": node.name(),
                        "spec": spec,
                        "node_obj": node
                    })

        fix_list = []
        error_count = 0

        for row, (name, info) in enumerate(req_summary.items()):
            self.table.insertRow(row)
            current_v_str = self.installed_pkgs.get(name)

            # --- 【修复】去重汇总逻辑 ---
            # 提取所有非空的 spec，并使用 set 去重
            raw_specs = [d['spec'] for d in info['node_data'] if d['spec']]
            unique_specs = sorted(list(set(raw_specs)))  # 排序保证显示稳定
            combined_spec_str = ",".join(unique_specs)

            status_text = "就绪"
            status_color = Qt.darkGreen
            action_widget = None

            if SpecifierSet and Version:
                try:
                    c_spec = SpecifierSet(combined_spec_str)
                    conflict_sources = self._analyze_conflict_sources(info['node_data'])

                    if conflict_sources:
                        status_text = "冲突"
                        status_color = Qt.red
                        # 生成带跳转功能的按钮
                        action_widget = self._make_info_btn(name, conflict_sources, "发现逻辑冲突(点击跳转)")
                    elif not current_v_str:
                        status_text = "缺失"
                        status_color = Qt.red
                        fix_list.append(f"{name}{combined_spec_str}")
                        action_widget = self._make_btn(FluentIcon.DOWNLOAD, "安装", name, combined_spec_str)
                    else:
                        if Version(current_v_str) in c_spec:
                            status_text = "就绪"
                            action_widget = self._make_ok_icon()
                        else:
                            status_text = "不匹配"
                            status_color = QColor("#D83B01")
                            fix_list.append(f"{name}{combined_spec_str}")
                            action_widget = self._make_btn(FluentIcon.SYNC, "修复", name, combined_spec_str)
                except:
                    status_text = "格式错误"
                    status_color = Qt.red

            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(combined_spec_str or "无限制"))

            v_item = QTableWidgetItem(current_v_str or "未安装")
            v_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, v_item)

            s_item = QTableWidgetItem(status_text)
            s_item.setForeground(status_color)
            s_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, s_item)

            if action_widget:
                self.table.setCellWidget(row, 4, action_widget)

            if status_text != "就绪": error_count += 1

        self.table.setUpdatesEnabled(True)
        self._update_ui_state(error_count, fix_list)

    def _make_btn(self, icon, tip, name, spec):
        btn = TransparentToolButton(icon, self)
        btn.setIconSize(QSize(14, 14))
        btn.setToolTip(f"{tip}: {name}{spec}")
        btn.clicked.connect(lambda: self.install_packages([f"{name}{spec}"]))
        return btn

    def _make_ok_icon(self):
        btn = TransparentToolButton(FluentIcon.COMPLETED, self)
        btn.setIconSize(QSize(14, 14))
        btn.setEnabled(False)
        return btn

    def _make_info_btn(self, name, conflict_sources, title=""):
        """【增强】带跳转功能的冲突详情按钮"""
        btn = TransparentToolButton(FluentIcon.INFO, self)
        btn.setIconSize(QSize(14, 14))

        # 1. 构建 ToolTip 信息
        msg = f"{title}\n以下节点的要求互斥：\n"
        seen = set()
        conflict_nodes = []
        for src in conflict_sources:
            line = f" • {src['node_name']} (需求: {src['spec'] or '任意'})"
            if line not in seen:
                msg += line + "\n"
                seen.add(line)
            # 2. 收集节点视图用于跳转
            node_obj = src.get('node_obj')
            if node_obj and hasattr(node_obj, '_view'):
                conflict_nodes.append(node_obj)

        btn.setToolTip(msg)

        # 3. 绑定点击跳转事件
        if conflict_nodes:
            btn.clicked.connect(lambda: self.homepage.center_to(conflict_nodes))

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

        if self.button:
            if error_count > 0:
                InfoBar.error(
                    "环境异常", f"请修复 {error_count} 项异常", duration=-1, parent=self.homepage,
                )

    def install_packages(self, pkg_specs):
        python_exe = self.get_current_python_exe()
        cmd = ["-m", "pip", "install"] + pkg_specs + ["--upgrade"]
        mirrors = self.config.mirrors.value
        if mirrors:
            for m in mirrors:
                cmd.extend(["--extra-index-url", m, "--trusted-host", urlparse(m).hostname])

        self.tip = StateToolTip("正在修复...", "同步 Python 环境", self.homepage)
        self.tip.move(self.homepage.width() - self.tip.width() - 30, 50)
        self.tip.show()
        self.setEnabled(False)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.finished.connect(self._on_install_finished)
        self._process.start(str(python_exe), cmd)

    def _on_install_finished(self):
        self.setEnabled(True)
        if hasattr(self, 'tip'): self.tip.setState(True)
        QTimer.singleShot(1000, self.run_check)

    def install_all_missing(self):
        if hasattr(self, '_temp_fix_list') and self._temp_fix_list:
            self.install_packages(self._temp_fix_list)