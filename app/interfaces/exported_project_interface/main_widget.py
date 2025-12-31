# -*- coding: utf-8 -*-
import json
import os
import re
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set

from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QDialog, QTextEdit, QFileDialog, QHBoxLayout, QFrame
from loguru import logger
from qfluentwidgets import (
    PrimaryPushButton,
    InfoBar,
    MessageBox, StateToolTip, SmoothScrollArea,
    PipsPager, PipsScrollButtonDisplayMode, ComboBox, SearchLineEdit,
    TransparentToggleToolButton, themeColor, ToolButton, TransparentToolButton
)
from watchfiles import Change

from app.interfaces.exported_project_interface.utils.threading_utils import (WatchfilesThread, ProjectRunnerThread)
from app.interfaces.exported_project_interface.widgets.project_card import ProjectCard
from app.utils.config import Settings
from app.interfaces.exported_project_interface.constants import *
from app.server_manager.http_server.service_manager import SERVICE_MANAGER
from app.utils.utils import ansi_to_html, get_icon
from app.widgets.dialog_widget.project_export_dialog import ProjectExportFlowDialog
from app.widgets.side_dock_area.side_dock_area import SideDockArea


class ExportedProjectsPage(QWidget):
    exported_projects_changed = pyqtSignal(str, str)
    running_projects_changed = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("exported_projects_page")
        self.config = Settings.get_instance()
        self.parent_window = parent
        self.running_projects = {}
        self._is_loading = False
        self._filter_text = ""
        self.page_size = 10
        self.current_page = 0
        self.total_pages = 1
        self.all_project_paths: List[str] = []
        self._card_map: Dict[str, ProjectCard] = {}
        self._known_projects: Set[str] = set()
        self._project_info_map: Dict[str, dict] = {}
        self._refresh_pending = False
        self._selected_card = None  # 新增：记录当前选中的卡片
        self._setup_ui()
        QTimer.singleShot(50, self._initial_load_and_start_watch)

    def _get_default_export_dir(self):
        default_dir = []
        for path in self.config.project_paths.value:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)
            default_dir.append(path)
        return default_dir

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === 顶部工具栏 ===
        top_bar = QHBoxLayout()
        top_bar.setSpacing(5)  # 增加间距
        top_bar.setContentsMargins(24, 16, 24, 10)  # 优化边距

        self.sort_field_combo = ComboBox(self)
        self.sort_field_combo.addItems(["创建时间", "名称"])
        self.sort_field_combo.setCurrentIndex(0)
        self.sort_field_combo.setFixedWidth(100)
        self.sort_field_combo.currentIndexChanged.connect(self._on_sort_changed)

        self.sort_order_button = TransparentToggleToolButton(self)
        self.sort_order_button.setIconSize(QSize(18, 18))
        self.sort_order_button.setIcon(get_icon("降序"))
        self.sort_order_button.setChecked(False)
        self.sort_order_button.setToolTip("当前：降序（点击切换为升序）")
        self.sort_order_button.clicked.connect(self._on_sort_order_changed)

        self.search_line_edit = SearchLineEdit(self)
        self.search_line_edit.setPlaceholderText("搜索项目名称...")
        self.search_line_edit.setFixedWidth(200)  # 加宽搜索框
        self.search_line_edit.textChanged.connect(self._on_search_changed)

        self.import_btn = TransparentToolButton(get_icon("导入"), self)
        self.import_btn.setIconSize(QSize(24, 24))
        self.import_btn.setToolTip("导入已有项目")
        self.import_btn.clicked.connect(self.import_projects)

        top_bar.addWidget(self.search_line_edit)
        top_bar.addWidget(self.sort_field_combo)
        top_bar.addWidget(self.sort_order_button)
        top_bar.addStretch(1)
        top_bar.addWidget(self.import_btn)

        # --- 左侧：项目列表 ---
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: transparent;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addLayout(top_bar)

        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")
        self.list_layout = QVBoxLayout(self.scroll_widget)
        self.list_layout.setContentsMargins(24, 10, 24, 20)  # 增加两侧边距
        self.list_layout.setSpacing(16)  # 增加卡片间距
        self.list_layout.setAlignment(Qt.AlignTop)  # 顶部对齐
        self.scroll_area.setWidget(self.scroll_widget)

        left_layout.addWidget(self.scroll_area, 1)

        # --- 右侧：详情面板 ---
        self.side_dock_area = SideDockArea(self, "项目管理")
        self.service_test_tool = self.side_dock_area.get_tool_instance("API 调试台")
        self.project_logs_tool = self.side_dock_area.get_tool_instance("项目日志")
        self.project_info_tool = self.side_dock_area.get_tool_instance("项目基本信息")

        # --- 分页器 ---
        self.pips_pager = PipsPager(Qt.Horizontal)
        self.pips_pager.setPageNumber(1)
        self.pips_pager.currentIndexChanged.connect(self._on_page_changed)
        self.pips_pager.setNextButtonDisplayMode(PipsScrollButtonDisplayMode.ALWAYS)
        self.pips_pager.setPreviousButtonDisplayMode(PipsScrollButtonDisplayMode.ALWAYS)
        self.pips_pager.setFixedHeight(40)
        left_layout.addWidget(self.pips_pager)

        # 简单美化一下分页器容器背景，使其与列表有区分（可选）
        pager_container = QWidget()
        pager_layout = QHBoxLayout(pager_container)
        pager_layout.setContentsMargins(0, 0, 0, 5)
        pager_layout.addWidget(self.pips_pager)
        left_layout.addWidget(pager_container)

        main_layout.addWidget(left_widget)
        main_layout.addWidget(self.side_dock_area, 1)
        main_layout.addWidget(self.side_dock_area.tool_panel)

    @property
    def context_register(self):
        return self.llm_context_provider.context_register

    def hide_splitter(self):
        self.splitter.setSizes(HIDE_SPLITTER_SIZES)
        self.splitter.update()

    def show_splitter(self):
        self.splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        self.splitter.update()

    def on_card_clicked(self, card: ProjectCard):
        """处理卡片点击事件，处理视觉选中效果"""
        # 1. 视觉更新
        if self._selected_card and self._selected_card != card:
            self._selected_card.set_selected(False)

        card.set_selected(True)
        self._selected_card = card

        # 2. 数据更新
        self._current_detail_project = str(card.project_path)
        project_path = card.project_path

        # 防止频繁刷新闪烁，这里可以加判断，但为了数据实时性暂时保留
        self.project_info_tool.refresh(project_path)

        if SERVICE_MANAGER.is_running(str(project_path)):
            url = SERVICE_MANAGER.get_url(str(project_path))
            self.service_test_tool.refresh(project_path, url)
            self.project_logs_tool.refresh(project_path)
        else:
            self.service_test_tool.refresh(project_path, None)
            self.project_logs_tool.refresh(project_path)

    # === 加载与监听 ===
    def _initial_load_and_start_watch(self):
        self.load_projects()
        self._start_watching()

    def _start_watching(self):
        watch_dirs = self._get_default_export_dir()
        self._watch_thread = WatchfilesThread(watch_dirs, self)
        self._watch_thread.projects_changed.connect(self._on_projects_file_changed)
        self._watch_thread.start()

    def _on_projects_file_changed(self, changes: List[tuple]):
        if not hasattr(self, '_watch_debounce_timer'):
            self._watch_debounce_timer = QTimer(self)
            self._watch_debounce_timer.setSingleShot(True)
            self._watch_debounce_timer.timeout.connect(self._apply_watch_changes)
            self._pending_watch_changes = []
        self._pending_watch_changes.extend(changes)
        self._watch_debounce_timer.start(300)

    def _apply_watch_changes(self):
        if not self._pending_watch_changes:
            return
        changes = self._pending_watch_changes.copy()
        self._pending_watch_changes.clear()
        projects_to_refresh = set()
        projects_to_remove = set()

        for change_type, path in changes:
            path = self._to_relative_path(path)
            filename = os.path.basename(path)
            project_dir = os.path.dirname(path)

            # 如果是 preview.png 变动，强制标记该项目刷新
            if filename == "model.workflow.json":
                if change_type == Change.deleted:
                    projects_to_remove.add(project_dir)
                else:
                    if os.path.exists(path):
                        projects_to_refresh.add(project_dir)
            elif filename == "preview.png":
                if os.path.exists(project_dir):
                    projects_to_refresh.add(project_dir)

        # 处理删除
        for proj in projects_to_remove:
            self._known_projects.discard(proj)
            self.exported_projects_changed.emit(proj, 'delete')
            self._project_info_map.pop(proj, None)
            if proj in self._card_map:
                card = self._card_map[proj]
                self.list_layout.removeWidget(card)
                card.hide()
                card.deleteLater()
                del self._card_map[proj]
                if self._selected_card == card:
                    self._selected_card = None

        # 处理刷新/新增
        for proj in projects_to_refresh:
            if proj not in self._known_projects:
                if (Path(proj) / "model.workflow.json").exists():
                    self._known_projects.add(proj)
                    self.exported_projects_changed.emit(proj, 'add')
                    try:
                        stat = Path(proj).stat()
                        self._project_info_map[proj] = {
                            'ctime_ts': stat.st_ctime,
                            'ctime': datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                        }
                    except:
                        self._project_info_map[proj] = {'ctime_ts': 0, 'ctime': '未知'}
                    try:
                        self._create_card(proj)
                    except:
                        traceback.print_exc()

            # 调用卡片刷新，确保图片等更新
            if proj in self._card_map:
                self._card_map[proj].refresh()

        self._apply_sort_and_filter_and_refresh()

    def _create_card(self, proj_path):
        """辅助函数：创建卡片"""
        card = ProjectCard(proj_path, self)
        card.run_btn.clicked.connect(lambda _, p=proj_path: self._run_project(p))
        card.edit_btn.clicked.connect(lambda _, p=proj_path: self._edit_project(p))
        card.service_btn.clicked.connect(lambda _, p=proj_path: self._toggle_service(p))
        card.view_log_btn.clicked.connect(lambda _, p=proj_path: self._view_project_log(p))
        card.delete_btn.clicked.connect(lambda _, p=proj_path: self._delete_project(p))
        card.hide()
        self._card_map[proj_path] = card
        return card

    def _to_relative_path(self, abs_path: str) -> str:
        export_root = Path("./")
        try:
            rel = Path(abs_path).resolve().relative_to(export_root.resolve())
            return str(rel).replace("\\", "/")
        except ValueError:
            logger.warning(f"Path {abs_path} is not under export root {export_root}")
            return str(Path(abs_path).resolve()).replace("\\", "/")

    def load_projects(self):
        if self._is_loading:
            return
        self._is_loading = True
        QTimer.singleShot(10, self._scan_projects)

    def _scan_projects(self):
        self.export_dir = self._get_default_export_dir()
        project_dirs = []
        project_info_map = {}
        for path in self.export_dir:
            if not path.exists(): continue
            for item in os.listdir(path):
                item_path = path / item
                if item_path.is_dir() and (item_path / "model.workflow.json").exists():
                    project_dir = self._to_relative_path(str(item_path))
                    project_dirs.append(project_dir)
                    try:
                        stat = item_path.stat()
                        project_info_map[project_dir] = {
                            'ctime_ts': stat.st_ctime,
                            'ctime': datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                        }
                    except:
                        project_info_map[project_dir] = {'ctime_ts': 0, 'ctime': '未知'}
        self._on_scan_finished(project_dirs, project_info_map)

    def _on_scan_finished(self, project_dirs: List[str], project_info_map: dict):
        self._is_loading = False
        self._project_info_map = project_info_map
        self._known_projects = set(project_dirs)

        # 清理旧卡片
        current_map_keys = list(self._card_map.keys())
        for key in current_map_keys:
            if key not in self._known_projects:
                w = self._card_map.pop(key)
                self.list_layout.removeWidget(w)
                w.deleteLater()

        for proj_path in project_dirs:
            if proj_path not in self._card_map:
                try:
                    self._create_card(proj_path)
                except:
                    traceback.print_exc()

        self._ensure_all_cards_in_layout()
        self._apply_sort_and_filter_and_refresh()

    def _ensure_all_cards_in_layout(self):
        # 此时不做具体的 addWidget，交给分页逻辑 _show_page 处理
        pass

    def _show_page(self, page_index: int):
        self.current_page = page_index
        # 隐藏所有
        for card in self._card_map.values():
            card.hide()

        # 移除布局中的所有 Item (但不删除对象)
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        start = page_index * self.page_size
        end = start + self.page_size

        visible_paths = self.all_project_paths[start:end]
        for proj_path in visible_paths:
            card = self._card_map.get(proj_path)
            if card:
                self.list_layout.addWidget(card)
                card.show()
                if self._selected_card is None:
                    self._selected_card = card
                    card.set_selected(True)
                    self.on_card_clicked(card)
                # 保持选中状态
                if self._selected_card == card:
                    card.set_selected(True)
                else:
                    card.set_selected(False)

        self.list_layout.addStretch()

    def _on_page_changed(self, index: int):
        self._show_page(index)

    def _on_search_changed(self, text: str):
        self._filter_text = text.strip().lower()
        self.current_page = 0  # 搜索时重置回第一页
        self._apply_sort_and_filter_and_refresh()

    def _on_sort_changed(self, index=None):
        self._apply_sort_and_filter_and_refresh()

    def _on_sort_order_changed(self):
        is_ascending = self.sort_order_button.isChecked()
        if is_ascending:
            self.sort_order_button.setIcon(get_icon("升序"))
            self.sort_order_button.setToolTip("当前：升序（点击切换为降序）")
        else:
            self.sort_order_button.setIcon(get_icon("降序"))
            self.sort_order_button.setToolTip("当前：降序（点击切换为升序）")
        self._apply_sort_and_filter_and_refresh()

    def _apply_sort_and_filter_and_refresh(self):
        if self._is_loading:
            return
        project_with_info = []
        for proj_path in self._known_projects:
            info = self._project_info_map.get(proj_path, {})
            ctime_ts = info.get('ctime_ts', 0)
            name = Path(proj_path).name
            if self._filter_text and self._filter_text not in name.lower():
                continue
            project_with_info.append((proj_path, ctime_ts, name))

        field_index = self.sort_field_combo.currentIndex()
        # 0: Time, 1: Name
        key_func = (lambda x: x[1]) if field_index == 0 else (lambda x: x[2].lower())
        is_ascending = self.sort_order_button.isChecked()
        project_with_info.sort(key=key_func, reverse=not is_ascending)

        self.all_project_paths = [item[0] for item in project_with_info]

        total = len(self.all_project_paths)
        self.total_pages = max(1, (total + self.page_size - 1) // self.page_size)
        self.pips_pager.setPageNumber(self.total_pages)

        # 防止当前页码超出总页数
        target_page = min(self.current_page, self.total_pages - 1)
        self.pips_pager.setCurrentIndex(target_page)
        self._show_page(target_page)

    # ... (Create/Delete/Run/Edit 业务逻辑保持原样，省略以节省篇幅，功能未变) ...
    # 为了完整性，以下是业务逻辑函数的占位，请保留原代码中的业务逻辑实现
    def import_projects(self):
        # 保持原代码逻辑
        folder = QFileDialog.getExistingDirectory(self, "选择项目文件夹", "", QFileDialog.ShowDirsOnly)
        if not folder: return
        src = Path(folder)
        if not src.is_dir() or not (src / "model.workflow.json").exists():
            self.create_error_info("无效选择", "请选择包含 model.workflow.json 的项目文件夹")
            return
        base = src.name or "imported_project"
        dest = self._get_default_export_dir()[0] / base
        counter = 1
        while dest.exists():
            dest = self._get_default_export_dir()[0] / f"{base}_{counter}"
            counter += 1
        try:
            shutil.copytree(src, dest)
            self.create_success_info("导入成功", f"项目 “{dest.name}” 已导入")
        except Exception as e:
            self.create_error_info("导入失败", str(e))

    def _toggle_service(self, project_path):
        # 保持原代码逻辑
        try:
            if SERVICE_MANAGER.is_running(project_path):
                SERVICE_MANAGER.stop_service(project_path)
                self.service_test_tool.refresh(project_path, None)
                self.running_projects_changed.emit(project_path, "delete")
                self.create_success_info("服务已停止", "微服务已下线")
            else:
                url = SERVICE_MANAGER.start_service(project_path)
                self.running_projects_changed.emit(project_path, "add")
                self.service_test_tool.refresh(project_path, url)
                self.create_success_info("服务已启动", f"访问: {url}")
            self.project_logs_tool.refresh(project_path)
            card = self._card_map.get(project_path)
            if card: card.refresh()
        except Exception as e:
            self.create_error_info("操作失败", str(e))

    def _run_project(self, project_path):
        # 保持原代码逻辑
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
        # 保持原代码逻辑
        state_tooltip.setContent("项目运行完成 ✅")
        state_tooltip.setState(True)
        try:
            with open(os.path.join(project_path, "output.json"), 'w', encoding='utf-8') as f:
                json.dump(outputs, f, indent=2, ensure_ascii=False)
            with open(os.path.join(project_path, "run.log"), 'a', encoding='utf-8') as f:
                f.write(log_content)
        except Exception as e:
            self.create_error_info("保存日志失败", str(e))
        self.create_success_info("运行完成", f"项目 {os.path.basename(project_path)} 执行成功")
        self._cleanup_project_run(project_path)

    def _on_project_error(self, project_path, error, state_tooltip):
        # 保持原代码逻辑
        state_tooltip.setContent(f"运行失败 ❌\n{error}")
        state_tooltip.setState(True)
        self.create_error_info("运行失败", f"项目 {os.path.basename(project_path)} 执行失败:\n{error}")
        logger.error(error)
        self._cleanup_project_run(project_path)

    def _cleanup_project_run(self, project_path):
        self.running_projects.pop(project_path, None)
        self._update_card_status(project_path, False)

    def _update_card_status(self, project_path, is_running):
        card = self._card_map.get(project_path)
        if card:
            card.update_status(is_running)

    def _edit_project(self, project_path: str):
        # 保持原代码逻辑，内容较长，假设未改动...
        # (此处省略中间具体的编辑逻辑代码，直接调用原有的即可)
        super_edit = getattr(self, '_original_edit_project', None)  # 仅示意
        # 您原有的代码逻辑非常完整，不需要修改，直接粘贴回这里即可。
        # 这里为了不截断，我把原代码中的逻辑完整写回：
        workflow_path = os.path.join(project_path, "model.workflow.json")
        spec_path = os.path.join(project_path, "project_spec.json")
        requirements_path = os.path.join(project_path, "requirements.txt")
        readme_path = os.path.join(project_path, "README.md")
        if not os.path.exists(workflow_path) or not os.path.exists(spec_path):
            self.create_error_info("编辑失败", "项目缺少必要文件")
            return
        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
            with open(spec_path, 'r', encoding='utf-8') as f:
                project_spec = json.load(f)
        except Exception as e:
            self.create_error_info("加载失败", str(e))
            return

        requirements_content = ""
        if os.path.exists(requirements_path):
            with open(requirements_path, 'r', encoding='utf-8') as f:
                requirements_content = f.read()
        readme_content = ""
        if os.path.exists(readme_path):
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()

        def generate_markdown(input: list, output: list):
            input_desc = ""
            for i, inp in enumerate(input):
                input_desc += (f"- 参数{i + 1}：{inp['custom_key']}\n   "
                               f"- 参数描述：{inp.get('param_desc') or inp.get('port_desc')}\n   "
                               f"- 参数格式：{inp['format']}\n   "
                               f"- 参数格式描述：{inp['format_desc']}\n   "
                               f"- 参数参考样例输入：{str(inp['current_value'])[:200]}\n   "
                               f"- 所属组件名：{inp['node_name']}\n   "
                               f"- 组件参数类型：{inp['type']}\n\n")
            output_desc = ""
            for i, out in enumerate(output):
                output_desc += (f"- 输出{i + 1}：{out['custom_key']}\n   "
                                f"- 输出描述：{out.get('output_desc')}\n   "
                                f"- 输出格式：{out['format']}\n   "
                                f"- 输出格式描述：{out['format_desc']}\n   "
                                f"- 所属组件名：{out['node_name']}\n   "
                                f"- 组件参数类型：{out['type']}\n\n")

            # 构造完整的区块（注意：这里只是普通字符串）
            input_block = f"## 🧩 输入接口\n\n{input_desc.rstrip()}\n\n---"
            output_block = f"## 📤 输出接口\n\n{output_desc.rstrip()}\n\n---"

            # 定义正则模式（使用原始字符串）
            input_pattern = r"(?s)(##\s*🧩\s*输入接口\s*\n.*?)(?:\n---|$)"
            output_pattern = r"(?s)(##\s*📤\s*输出接口\s*\n.*?)(?:\n---|$)"

            # 使用 lambda 避免 re.sub 解析 repl 中的反斜杠
            updated_readme = re.sub(input_pattern, lambda m: input_block, readme_content, count=1)
            updated_readme = re.sub(output_pattern, lambda m: output_block, updated_readme, count=1)
            return updated_readme

        candidate_items = workflow_data.get("candidate_inputs", []) + workflow_data.get("candidate_outputs", [])
        current_inputs = project_spec.get('inputs', {})
        current_outputs = project_spec.get('outputs', {})
        project_name = project_spec.get('graph_name', os.path.basename(project_path))

        flow_dialog = ProjectExportFlowDialog(
            candidate_items=candidate_items,
            parent=self,
            current_selected_inputs=current_inputs,
            current_selected_outputs=current_outputs,
            project_name=project_name,
            requirements=requirements_content,
            readme_func=generate_markdown
        )
        if flow_dialog.exec() == QDialog.Accepted:
            updated_inputs = {}
            for item in flow_dialog.get_selected_inputs():
                key = item.get("custom_key", f"input_{len(updated_inputs)}")
                updated_inputs[key] = item
            updated_outputs = {}
            for item in flow_dialog.get_selected_outputs():
                key = item.get("custom_key", f"output_{len(updated_outputs)}")
                if 'format' not in item:
                    original_candidate = next(
                        (c for c in workflow_data.get("candidate_outputs", [])
                         if c['node_id'] == item['node_id'] and c['output_name'] == item['output_name']),
                        None
                    )
                    item['format'] = original_candidate.get('format', 'TEXT') if original_candidate else 'TEXT'
                updated_outputs[key] = {
                    "node_id": item["node_id"],
                    "output_name": item["output_name"],
                    "format": item["format"],
                    "custom_key": item.get("custom_key", key)
                }
            final_project_name = flow_dialog.get_project_name()
            final_readme = flow_dialog.get_readme_content()
            final_requirements = flow_dialog.get_requirements()

            project_spec['inputs'] = updated_inputs
            project_spec['outputs'] = updated_outputs
            project_spec['graph_name'] = final_project_name

            try:
                with open(spec_path, 'w', encoding='utf-8') as f:
                    json.dump(project_spec, f, indent=2, ensure_ascii=False)
                with open(requirements_path, 'w', encoding='utf-8') as f:
                    f.write(final_requirements)
                with open(readme_path, 'w', encoding='utf-8') as f:
                    f.write(final_readme)
                self.create_success_info("编辑成功", f"项目 '{final_project_name}' 的接口和信息已更新。")
            except Exception as e:
                self.create_error_info("保存失败", str(e))

    def _view_project_log(self, project_path):
        # 保持原代码逻辑
        all_logs = []
        for name, file in [("项目运行日志", "run.log"), ("微服务日志", "service.log")]:
            path = os.path.join(project_path, file)
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content: all_logs.append((name, content))
                except:
                    pass
        if not all_logs:
            self.create_warning_info("无日志", "项目尚未运行或日志文件不存在")
            return
        combined = "\n".join([f"{'=' * 60}\n{name}\n{'=' * 60}\n{content}" for name, content in all_logs])
        self._show_log_dialog(combined)

    def _show_log_dialog(self, log_content):
        # 保持原代码逻辑
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
        text_edit.setFont(QFont("Consolas", 10))
        close_btn = PrimaryPushButton("关闭", self)
        close_btn.clicked.connect(dialog.accept)
        layout = QVBoxLayout(dialog)
        layout.addWidget(text_edit)
        layout.addWidget(close_btn)
        dialog.exec()

    def _delete_project(self, project_path):
        # 保持原代码逻辑
        w = MessageBox("确认删除", f"确定要删除项目 '{Path(project_path).name}' 吗？\n此操作不可恢复！", self)
        if w.exec():
            try:
                if SERVICE_MANAGER.is_running(project_path):
                    SERVICE_MANAGER.stop_service(project_path)
                    time.sleep(0.5)
                if project_path in self._card_map:
                    card = self._card_map[project_path]
                    self.list_layout.removeWidget(card)
                    card.hide()
                    card.deleteLater()
                    del self._card_map[project_path]
                for _ in range(3):
                    try:
                        shutil.rmtree(project_path)
                        self.create_success_info("删除成功", "项目已删除")
                        self._schedule_refresh()
                        return
                    except PermissionError:
                        time.sleep(0.3)
                        continue
                raise PermissionError(f"无法删除 {project_path}")
            except Exception as e:
                self.create_error_info("删除失败", str(e))

    def create_success_info(self, title, content):
        InfoBar.success(title, content, parent=self, duration=2000)

    def create_warning_info(self, title, content):
        InfoBar.warning(title, content, parent=self, duration=2000)

    def create_error_info(self, title, content):
        InfoBar.error(title, content, parent=self, duration=3000)

    def _schedule_refresh(self):
        if not hasattr(self, '_refresh_timer'):
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._load_projects_safe)
        self._refresh_timer.start(150)

    def _load_projects_safe(self):
        if not self._refresh_pending:
            self._refresh_pending = True
            self.load_projects()
            self._refresh_pending = False

    def closeEvent(self, event):
        if hasattr(self, '_watch_thread'):
            self._watch_thread.stop()
            self._watch_thread.wait()
        super().closeEvent(event)