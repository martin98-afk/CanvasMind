# -*- coding: utf-8 -*-
import errno
import json
import os
import shutil
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
from watchfiles import watch, Change
from PyQt5.QtCore import QThread, pyqtSignal, QEasingCurve, Qt, QTimer, QSize
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QDialog, QTextEdit, QLabel, QFileDialog, QHBoxLayout, QFrame
from loguru import logger
from qfluentwidgets import (
    PrimaryPushButton,
    InfoBar,
    MessageBox, StateToolTip, FlowLayout, CardWidget, BodyLabel, SmoothScrollArea,
    PipsPager, PipsScrollButtonDisplayMode, ComboBox, CaptionLabel, SearchLineEdit,
    TransparentToggleToolButton
)

from app.utils.config import Settings
from app.utils.service_manager import SERVICE_MANAGER
from app.utils.utils import ansi_to_html, get_icon
from app.widgets.card_widget.project_card import ProjectCard
from app.widgets.dialog_widget.project_export_dialog import ProjectExportFlowDialog


# --- 新增：Watchfiles 监听线程 ---
class WatchfilesThread(QThread):
    projects_changed = pyqtSignal(list)  # [(change_type, path_str), ...]

    def __init__(self, watch_dirs: List[Path], parent=None):
        super().__init__(parent)
        self.watch_dirs = [str(p.resolve()) for p in watch_dirs]
        self._stop = False

    def run(self):
        try:
            for changes in watch(*self.watch_dirs, stop_event=None):
                if self._stop:
                    break
                # 只关注 model.workflow.json
                filtered = []
                for change_type, path in changes:
                    if os.path.basename(path) in ("model.workflow.json", "preview.png"):
                        print(f"[Watchfiles] {change_type}: {path}")
                        filtered.append((change_type, path))
                if filtered:
                    self.projects_changed.emit(filtered)
        except Exception as e:
            logger.error(f"Watchfiles error: {e}")

    def stop(self):
        self._stop = True


class ProjectRunnerThread(QThread):
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
                    pass

            log_content = (result.stdout or "") + "\n" + (result.stderr or "")
            self.finished.emit(outputs, log_content)

        except Exception as e:
            self.error.emit(traceback.format_exc())

class ExportedProjectsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("exported_projects_page")
        self.config = Settings.get_instance()
        self.parent_window = parent
        self.running_projects = {}
        self._is_loading = False
        self._filter_text = ""
        self.page_size = 12
        self.fixed_card_count = 1
        self.current_page = 0
        self.total_pages = 1
        self.all_project_paths: List[str] = []

        self._card_map: Dict[str, ProjectCard] = {}
        self._known_projects: Set[str] = set()
        self._project_info_map: Dict[str, dict] = {}
        self._fixed_cards: List[CardWidget] = []
        self._refresh_pending = False

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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # === 顶部：排序 + 方向 + 搜索 ===
        top_bar = QHBoxLayout()
        top_bar.setSpacing(16)
        top_bar.setContentsMargins(50, 0, 70, 0)
        sort_label = CaptionLabel("排序字段：", self)
        self.sort_field_combo = ComboBox(self)
        self.sort_field_combo.addItems(["创建时间", "名称"])
        self.sort_field_combo.setCurrentIndex(0)
        self.sort_field_combo.setFixedWidth(100)
        self.sort_field_combo.currentIndexChanged.connect(self._on_sort_changed)

        self.sort_order_button = TransparentToggleToolButton(self)
        self.sort_order_button.setIconSize(QSize(20, 20))
        self.sort_order_button.setIcon(get_icon("降序"))
        self.sort_order_button.setChecked(False)
        self.sort_order_button.setToolTip("当前：降序（点击切换为升序）")
        self.sort_order_button.clicked.connect(self._on_sort_order_changed)

        self.search_line_edit = SearchLineEdit(self)
        self.search_line_edit.setPlaceholderText("搜索项目名称...")
        self.search_line_edit.setFixedWidth(220)
        self.search_line_edit.textChanged.connect(self._on_search_changed)

        top_bar.addWidget(self.search_line_edit)
        top_bar.addStretch()
        top_bar.addWidget(sort_label)
        top_bar.addWidget(self.sort_field_combo)
        top_bar.addWidget(self.sort_order_button)

        # === 主体：卡片 + 分页器 ===
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")

        self.flow_layout = FlowLayout(self.scroll_widget, needAni=True)
        self.flow_layout.setAnimation(250, QEasingCurve.OutQuad)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(30)

        self.scroll_area.setWidget(self.scroll_widget)

        self.pips_pager = PipsPager(Qt.Vertical)
        self.pips_pager.setPageNumber(1)
        self.pips_pager.currentIndexChanged.connect(self._on_page_changed)
        self.pips_pager.setNextButtonDisplayMode(PipsScrollButtonDisplayMode.ALWAYS)
        self.pips_pager.setPreviousButtonDisplayMode(PipsScrollButtonDisplayMode.ALWAYS)
        self.pips_pager.setFixedWidth(10)

        content_layout.addWidget(self.scroll_area, 1)
        content_layout.addWidget(self.pips_pager, 0)

        main_layout.addLayout(top_bar)
        main_layout.addLayout(content_layout)

    def _calculate_cards_per_page(self) -> int:
        if not self.scroll_area or self.scroll_area.viewport().width() <= 0:
            return 12
        card_width = 400
        if self._card_map:
            sample_card = next(iter(self._card_map.values()))
            if sample_card.width() > 50:
                card_width = sample_card.width()
        elif self._fixed_cards and self._fixed_cards[0].width() > 50:
            card_width = self._fixed_cards[0].width()
        margins = self.flow_layout.contentsMargins()
        spacing = self.flow_layout.horizontalSpacing()
        available_width = self.scroll_area.viewport().width() - margins.left() - margins.right()
        if available_width <= card_width:
            cards_per_row = 1
        else:
            cards_per_row = max(1, int((available_width + spacing) / (card_width + spacing)))
        return cards_per_row * 3

    # --- 新增：初始加载 + 启动监听 ---
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

        # 用于记录哪些项目需要刷新（去重）
        projects_to_refresh = set()
        projects_to_remove = set()

        for change_type, path in changes:
            filename = os.path.basename(path)
            project_dir = os.path.dirname(path)

            if filename == "model.workflow.json":
                if change_type == Change.deleted:
                    projects_to_remove.add(project_dir)
                else:
                    if os.path.exists(path):
                        projects_to_refresh.add(project_dir)
            elif filename == "preview.png":
                # preview.png 变化只影响刷新，不影响项目存在性
                if os.path.exists(project_dir):  # 确保项目还存在
                    projects_to_refresh.add(project_dir)
        print(projects_to_refresh)
        # 删除项目（仅由 workflow.json deleted 触发）
        for proj in projects_to_remove:
            self._known_projects.discard(proj)
            self._project_info_map.pop(proj, None)
            if proj in self._card_map:
                card = self._card_map[proj]
                self.flow_layout.removeWidget(card)
                card.hide()
                card.deleteLater()
                del self._card_map[proj]

        # 新增/刷新项目
        for proj in projects_to_refresh:
            # 如果是新项目（由 workflow.json 新增触发）
            if proj not in self._known_projects:
                if (Path(proj) / "model.workflow.json").exists():
                    self._known_projects.add(proj)
                    try:
                        stat = Path(proj).stat()
                        self._project_info_map[proj] = {
                            'ctime_ts': stat.st_ctime,
                            'ctime': datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                        }
                    except Exception:
                        self._project_info_map[proj] = {'ctime_ts': 0, 'ctime': '未知'}

                    # 创建新卡片
                    try:
                        card = ProjectCard(proj, self)
                        card.run_btn.clicked.connect(lambda _, p=proj: self._run_project(p))
                        card.edit_btn.clicked.connect(lambda _, p=proj: self._edit_project(p))
                        card.service_btn.clicked.connect(lambda _, p=proj: self._toggle_service(p))
                        card.view_log_btn.clicked.connect(lambda _, p=proj: self._view_project_log(p))
                        card.delete_btn.clicked.connect(lambda _, p=proj: self._delete_project(p))
                        card.hide()
                        self._card_map[proj] = card
                    except Exception:
                        traceback.print_exc()
                else:
                    continue  # 不是有效项目，跳过

            # 无论新旧，只要在 projects_to_refresh 中，就刷新
            if proj in self._card_map:
                self._card_map[proj].refresh()

        self._apply_sort_and_filter_and_refresh()

    # --- 原有逻辑：首次全量扫描 ---
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
            for item in os.listdir(path):
                item_path = path / item
                if item_path.is_dir() and (item_path / "model.workflow.json").exists():
                    project_dirs.append(str(item_path))
                    try:
                        stat = item_path.stat()
                        project_info_map[str(item_path)] = {
                            'ctime_ts': stat.st_ctime,
                            'ctime': datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                        }
                    except Exception:
                        project_info_map[str(item_path)] = {'ctime_ts': 0, 'ctime': '未知'}
        self._on_scan_finished(project_dirs, project_info_map)

    def _on_scan_finished(self, project_dirs: List[str], project_info_map: dict):
        self._is_loading = False
        self._project_info_map = project_info_map
        self._known_projects = set(project_dirs)

        for proj_path in project_dirs:
            if proj_path not in self._card_map:
                try:
                    card = ProjectCard(proj_path, self)
                    card.run_btn.clicked.connect(lambda _, p=proj_path: self._run_project(p))
                    card.edit_btn.clicked.connect(lambda _, p=proj_path: self._edit_project(p))
                    card.service_btn.clicked.connect(lambda _, p=proj_path: self._toggle_service(p))
                    card.view_log_btn.clicked.connect(lambda _, p=proj_path: self._view_project_log(p))
                    card.delete_btn.clicked.connect(lambda _, p=proj_path: self._delete_project(p))
                    card.hide()
                    self._card_map[proj_path] = card
                except Exception:
                    traceback.print_exc()

        if not self._fixed_cards:
            self._fixed_cards = [self._create_import_card()]
            for card in self._fixed_cards:
                card.hide()

        self._ensure_all_cards_in_layout()
        self._apply_sort_and_filter_and_refresh()

    def _create_import_card(self):
        from qfluentwidgets import FluentIcon
        import_card = CardWidget()
        import_card.setBorderRadius(12)
        import_card.setFixedSize(400, 330)
        layout = QVBoxLayout(import_card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        icon = FluentIcon.FOLDER_ADD.icon()
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(64, 64))
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

    def _ensure_all_cards_in_layout(self):
        for card in self._fixed_cards:
            if card.parent() != self.scroll_widget:
                self.flow_layout.addWidget(card)
        for card in self._card_map.values():
            if card.parent() != self.scroll_widget:
                self.flow_layout.addWidget(card)

    def _show_page(self, page_index: int):
        self.current_page = page_index
        for card in self._fixed_cards:
            card.hide()
        for card in self._card_map.values():
            card.hide()
        while self.flow_layout.count():
            self.flow_layout.takeAt(0)
        if page_index == 0:
            for card in self._fixed_cards:
                self.flow_layout.addWidget(card)
                card.show()
            workflow_slots = self.page_size - self.fixed_card_count
            workflow_to_show = self.all_project_paths[:workflow_slots]
            for proj_path in workflow_to_show:
                card = self._card_map.get(proj_path)
                if card:
                    self.flow_layout.addWidget(card)
                    card.show()
        else:
            first_page_count = max(0, self.page_size - self.fixed_card_count)
            start = first_page_count + (page_index - 1) * self.page_size
            end = start + self.page_size
            workflow_to_show = self.all_project_paths[start:end]
            for proj_path in workflow_to_show:
                card = self._card_map.get(proj_path)
                if card:
                    self.flow_layout.addWidget(card)
                    card.show()
        self.scroll_widget.adjustSize()

    def _on_page_changed(self, index: int):
        self._show_page(index)

    def _on_search_changed(self, text: str):
        self._filter_text = text.strip().lower()
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
        if not self._known_projects:
            self.all_project_paths = []
        else:
            field_index = self.sort_field_combo.currentIndex()
            is_ascending = self.sort_order_button.isChecked()
            project_with_info = []
            for proj_path in self._known_projects:
                info = self._project_info_map.get(proj_path, {})
                ctime_ts = info.get('ctime_ts', 0)
                name = Path(proj_path).name
                if self._filter_text and self._filter_text not in name.lower():
                    continue
                project_with_info.append((proj_path, ctime_ts, name))
            if field_index == 0:
                key_func = lambda x: x[1]
            else:
                key_func = lambda x: x[2].lower()
            project_with_info.sort(key=key_func, reverse=not is_ascending)
            self.all_project_paths = [item[0] for item in project_with_info]
        self.page_size = self._calculate_cards_per_page()
        total_projects = len(self.all_project_paths)
        if total_projects == 0:
            self.total_pages = 1
        else:
            first_page_slots = max(0, self.page_size - self.fixed_card_count)
            if first_page_slots <= 0:
                self.total_pages = 1
            else:
                remaining = total_projects - first_page_slots
                if remaining <= 0:
                    self.total_pages = 1
                else:
                    self.total_pages = 1 + ((remaining + self.page_size - 1) // self.page_size)
        self.pips_pager.setPageNumber(self.total_pages)
        target_page = min(self.current_page, self.total_pages - 1)
        self._show_page(target_page)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(100, self._on_resize)

    def _on_resize(self):
        if self._is_loading:
            return
        new_page_size = self._calculate_cards_per_page()
        if new_page_size != self.page_size:
            self.page_size = new_page_size
            self._apply_sort_and_filter_and_refresh()

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

    # ================== 业务逻辑 ==================

    def import_projects(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, "选择项目文件夹", "", QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not folder_path:
            return
        src_path = Path(folder_path)
        if not src_path.is_dir() or not (src_path / "model.workflow.json").exists():
            self.create_error_info("无效选择", "请选择包含 model.workflow.json 的项目文件夹")
            return
        base_name = src_path.name or "imported_project"
        dest_path = self.export_dir[0] / base_name
        counter = 1
        while dest_path.exists():
            dest_path = self.export_dir[0] / f"{base_name}_{counter}"
            counter += 1
        try:
            shutil.copytree(src_path, dest_path)
            self.create_success_info("导入成功", f"项目 “{dest_path.name}” 已导入")
            # 不再手动刷新，watchfiles 会自动捕获
        except Exception as e:
            self.create_error_info("导入失败", str(e))

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
        card = self._card_map.get(project_path)
        if card:
            card._update_service_button()

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
            with open(os.path.join(project_path, "output.json"), 'w', encoding='utf-8') as f:
                json.dump(outputs, f, indent=2, ensure_ascii=False)
            with open(os.path.join(project_path, "run.log"), 'a', encoding='utf-8') as f:
                f.write(log_content)
        except Exception as e:
            self.create_error_info("保存日志失败", str(e))
        self.create_success_info("运行完成", f"项目 {os.path.basename(project_path)} 执行成功")
        self._cleanup_project_run(project_path)

    def _on_project_error(self, project_path, error, state_tooltip):
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
        """
        Edits the project's input and output specifications and project info by using the
        integrated ProjectExportFlowDialog, pre-filling it with current values from
        project_spec.json, requirements.txt, and README.md.
        Uses candidate_inputs and candidate_outputs from model.workflow.json.
        """
        workflow_path = os.path.join(project_path, "model.workflow.json")
        spec_path = os.path.join(project_path, "project_spec.json")
        requirements_path = os.path.join(project_path, "requirements.txt")
        readme_path = os.path.join(project_path, "README.md")

        if not os.path.exists(workflow_path):
            self.create_error_info("编辑失败",
                                   f"项目 '{os.path.basename(project_path)}' 缺少 model.workflow.json 文件。")
            return
        if not os.path.exists(spec_path):
            self.create_error_info("编辑失败", f"项目 '{os.path.basename(project_path)}' 缺少 project_spec.json 文件。")
            return

        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
        except Exception as e:
            self.create_error_info("加载失败", f"无法读取 model.workflow.json: {e}")
            return

        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                project_spec = json.load(f)
        except Exception as e:
            self.create_error_info("加载失败", f"无法读取 project_spec.json: {e}")
            return

        # 读取 requirements 和 README
        requirements_content = ""
        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, 'r', encoding='utf-8') as f:
                    requirements_content = f.read()
            except Exception as e:
                self.logger.warning(f"无法读取 requirements.txt: {e}")

        readme_content = ""
        if os.path.exists(readme_path):
            try:
                with open(readme_path, 'r', encoding='utf-8') as f:
                    readme_content = f.read()
            except Exception as e:
                self.logger.warning(f"无法读取 README.md: {e}")

        # 获取候选人选和当前选择
        candidate_items = workflow_data.get("candidate_inputs", []) + workflow_data.get("candidate_outputs", [])
        current_inputs = project_spec.get('inputs', {})
        current_outputs = project_spec.get('outputs', {})
        project_name = project_spec.get('graph_name', os.path.basename(project_path))  # 从 spec 或路径获取项目名

        # 创建集成流程对话框
        flow_dialog = ProjectExportFlowDialog(
            candidate_items=candidate_items,
            parent=self,
            current_selected_inputs=current_inputs,
            current_selected_outputs=current_outputs,
            project_name=project_name,
            requirements=requirements_content,
            readme=readme_content
        )

        if flow_dialog.exec() == QDialog.Accepted:
            # 获取用户最终选择
            updated_inputs = {}
            for item in flow_dialog.get_selected_inputs():
                key = item.get("custom_key", f"input_{len(updated_inputs)}")
                updated_inputs[key] = item

            updated_outputs = {}
            for item in flow_dialog.get_selected_outputs():
                key = item.get("custom_key", f"output_{len(updated_outputs)}")
                # 确保输出项包含必要的格式信息
                if 'format' not in item:
                    # 尝试从候选人选中恢复格式
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
                    "custom_key": item.get("custom_key", key)  # 确保 custom_key 存在
                }

            final_project_name = flow_dialog.get_project_name()
            final_readme = flow_dialog.get_readme_content()
            final_requirements = flow_dialog.get_requirements()

            # 更新 spec 数据
            project_spec['inputs'] = updated_inputs
            project_spec['outputs'] = updated_outputs
            project_spec['graph_name'] = final_project_name  # 更新 spec 中的项目名

            # 保存更新后的 spec
            try:
                with open(spec_path, 'w', encoding='utf-8') as f:
                    json.dump(project_spec, f, indent=2, ensure_ascii=False)
            except Exception as e:
                self.create_error_info("保存失败", f"无法保存 project_spec.json: {e}")
                return

            # 保存更新后的 requirements 和 README
            try:
                with open(requirements_path, 'w', encoding='utf-8') as f:
                    f.write(final_requirements)
            except Exception as e:
                self.create_error_info("保存失败", f"无法保存 requirements.txt: {e}")
                # 注意：即使这里失败，spec 已经保存了，所以不直接返回

            try:
                with open(readme_path, 'w', encoding='utf-8') as f:
                    f.write(final_readme)
            except Exception as e:
                self.create_error_info("保存失败", f"无法保存 README.md: {e}")
                # 注意：即使这里失败，spec 已经保存了，所以不直接返回

            self.create_success_info("编辑成功", f"项目 '{final_project_name}' 的接口和信息已更新。")
        else:
            print("项目编辑流程被用户取消。")
            # 用户取消，不做任何更改
            return

    def _view_project_log(self, project_path):
        all_logs = []
        for name, file in [("项目运行日志", "run.log"), ("微服务日志", "service.log")]:
            path = os.path.join(project_path, file)
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            all_logs.append((name, content))
                except Exception:
                    pass

        if not all_logs:
            self.create_warning_info("无日志", "项目尚未运行或日志文件不存在")
            return

        combined = "\n".join([f"{'='*60}\n{title}\n{'='*60}\n\n{content}" for title, content in all_logs])
        self._show_log_dialog(combined)

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
        text_edit.setFont(QFont("Consolas", 10))

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
        w = MessageBox("确认删除", f"确定要删除项目 '{Path(project_path).name}' 吗？\n此操作不可恢复！", self)
        if w.exec():
            try:
                if SERVICE_MANAGER.is_running(project_path):
                    SERVICE_MANAGER.stop_service(project_path)
                    time.sleep(0.5)

                # ✅ 安全删除卡片
                if project_path in self._card_map:
                    card = self._card_map[project_path]
                    self.flow_layout.removeWidget(card)
                    card.hide()
                    card.deleteLater()
                    del self._card_map[project_path]

                for _ in range(3):
                    try:
                        shutil.rmtree(project_path)
                        self.create_success_info("删除成功", "项目已删除")
                        self._schedule_refresh()
                        return
                    except PermissionError as e:
                        if e.errno == errno.EACCES:
                            time.sleep(0.3)
                            continue
                        else:
                            raise
                raise PermissionError(f"无法删除 {project_path}")
            except Exception as e:
                self.create_error_info("删除失败", str(e))

    def create_success_info(self, title, content):
        InfoBar.success(title, content, parent=self, duration=2000)

    def create_warning_info(self, title, content):
        InfoBar.warning(title, content, parent=self, duration=2000)

    def create_error_info(self, title, content):
        InfoBar.error(title, content, parent=self, duration=3000)

    def closeEvent(self, event):
        if hasattr(self, '_watch_thread'):
            self._watch_thread.stop()
            self._watch_thread.wait()
        super().closeEvent(event)