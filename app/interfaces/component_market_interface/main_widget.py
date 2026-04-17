# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QWidget,
    QStackedWidget,
    QGridLayout,
    QPushButton,
    QTabWidget,
)
from loguru import logger
from pypinyin import lazy_pinyin, Style
from qfluentwidgets import (
    IndeterminateProgressRing,
    SmoothScrollArea,
    CardWidget,
    PrimaryPushButton,
    FluentIcon,
    InfoBar,
    PushButton,
    ComboBox,
    MessageBox,
    ToolButton,
    CheckBox,
    LineEdit,
    BodyLabel,
    TitleLabel,
    SubtitleLabel,
    PasswordLineEdit,
    ProgressBar,
)

from app.interfaces.component_market_interface.utils.utils import (
    GenericWorker,
    calculate_md5,
)
from app.interfaces.component_market_interface.widgets.component_card import (
    ComponentCard,
)
from app.interfaces.component_market_interface.ui.search_bar import (
    SearchBarWithHistory,
)
from app.interfaces.component_market_interface.ui.search_history import (
    SearchHistoryManager,
)
from app.scan_components import ComponentScanner
from app.server_manager.cloud_bakup.canvas_cloud_manager import CanvasCloudManager
from app.server_manager.cloud_bakup.component_cloud_manager import ComponentCloudManager
from app.utils.utils import get_icon, resource_path
from app.widgets.basic_widget.style_sheet import StyleSheet


class PluginMarketplace(QWidget):
    """专业级社区插件管理界面"""

    plugin_installed = pyqtSignal(str, str)
    plugin_uninstalled = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PluginMarketplace")

        self.scanner = ComponentScanner()
        self.cloud_mgr = ComponentCloudManager()
        self.canvas_mgr = CanvasCloudManager()

        self._cloud_plugins = []
        self._local_plugins = []
        self._my_uploads = []

        self.active_worker = None
        self._workers = []

        self._render_queue = []
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._process_render_queue)

        self.scanner.register_on_change(self._on_local_changed)
        self.current_type = "component"

        self._search_history_mgr = SearchHistoryManager()
        self._search_bar = None

        self.init_ui()
        StyleSheet.COMPONENT_MARKET.apply(self)
        self.switch_tab(0)

        self._fetch_cloud_plugins()
        self._scan_local_plugins()

    def init_ui(self):
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("SideBar")
        self.sidebar.setFixedWidth(200)
        side_lay = QVBoxLayout(self.sidebar)

        logo = QLabel("插件市场")
        logo.setStyleSheet(
            "color: #f0f6fc; font-weight: 700; font-size: 20px; margin: 30px 20px;"
        )
        side_lay.addWidget(logo)

        self.nav_btns = []
        nav_items = [
            ("插件市场", "market", 0),
            ("已安装", "installed", 1),
            ("我的上传", "uploads", 2),
        ]
        for text, mode, idx in nav_items:
            btn = QPushButton(text)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn._nav_mode = mode
            btn._nav_idx = idx
            btn.clicked.connect(
                lambda ch, b=btn: self.switch_tab(b._nav_idx, b._nav_mode)
            )
            side_lay.addWidget(btn)
            self.nav_btns.append(btn)

        side_lay.addStretch()

        type_section = QLabel("资源类型")
        type_section.setStyleSheet(
            "color: #8b949e; font-size: 12px; margin: 10px 20px;"
        )
        side_lay.addWidget(type_section)

        self.type_btns = []
        for text, ptype in [("组件", "component"), ("画布", "canvas")]:
            btn = PushButton(text)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn._type = ptype
            btn.clicked.connect(lambda ch, t=ptype: self.switch_type(t))
            side_lay.addWidget(btn)
            self.type_btns.append(btn)

        self.type_btns[0].setChecked(True)

        side_lay.addSpacing(20)
        self.config_btn = QPushButton("存储设置")
        self.config_btn.setObjectName("NavBtn")
        self.config_btn.setCheckable(True)
        self.config_btn.clicked.connect(lambda: self.switch_tab(3, "settings"))
        side_lay.addWidget(self.config_btn)
        self.nav_btns.append(self.config_btn)
        side_lay.addSpacing(20)
        main_lay.addWidget(self.sidebar)

        content_panel = QWidget()
        content_lay = QVBoxLayout(content_panel)
        content_lay.setContentsMargins(30, 20, 30, 0)

        self._create_toolbar(content_lay)

        self.stack = QStackedWidget()
        self.pages = {
            "market": self._create_scroll_page(),
            "installed": self._create_scroll_page(),
            "uploads": self._create_scroll_page(),
            "settings": self._create_setting_page(),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)
        content_lay.addWidget(self.stack)
        main_lay.addWidget(content_panel)

    def _create_toolbar(self, parent_lay):
        toolbar = QHBoxLayout()

        self.search_bar = SearchBarWithHistory()
        self.search_bar.search_signal.connect(self._on_filter_changed)
        self.search_bar.history_changed.connect(self._on_history_changed)
        toolbar.addWidget(self.search_bar, 1)

        self.creator_filter = ComboBox()
        self.creator_filter.setFixedWidth(150)
        self.creator_filter.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.creator_filter)

        self.category_filter = ComboBox()
        self.category_filter.setFixedWidth(130)
        self.category_filter.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.category_filter)

        self.sort_combo = ComboBox()
        self.sort_combo.setFixedWidth(130)
        self.sort_combo.addItems(["最新发布", "最近更新", "名称排序", "下载量"])
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        toolbar.addWidget(self.sort_combo)

        self.select_all_check = CheckBox("全选")
        self.select_all_check.stateChanged.connect(self._on_select_all_changed)
        toolbar.addWidget(self.select_all_check)

        self.batch_btn = PrimaryPushButton(FluentIcon.DOWNLOAD, "批量安装")
        self.batch_btn.clicked.connect(self._on_batch_install)
        toolbar.addWidget(self.batch_btn)

        self.upload_btn = PushButton(get_icon("upload"), "批量上传")
        self.upload_btn.clicked.connect(self._on_batch_upload)
        toolbar.addWidget(self.upload_btn)

        self.refresh_btn = ToolButton(FluentIcon.SYNC, "")
        self.refresh_btn.clicked.connect(self.force_refresh)
        toolbar.addWidget(self.refresh_btn)

        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(20, 20)
        self.loading_ring.hide()
        toolbar.addWidget(self.loading_ring)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        parent_lay.addWidget(self.progress_bar)
        parent_lay.addSpacing(10)
        parent_lay.addLayout(toolbar)

    def _create_scroll_page(self):
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setAlignment(Qt.AlignTop)
        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _create_setting_page(self):
        page = self._create_scroll_page()
        layout = page.widget().layout()
        layout.insertWidget(0, TitleLabel("Gitee 存储配置"))
        card = CardWidget()
        v = QVBoxLayout(card)

        self.token_edit = PasswordLineEdit()
        self.token_edit.setText(self.cloud_mgr.config.GITEE_TOKEN.value)
        v.addWidget(BodyLabel("Access Token:"))
        v.addWidget(self.token_edit)

        self.owner_edit = LineEdit()
        self.owner_edit.setText(self.cloud_mgr.config.GITEE_OWNER.value)
        v.addWidget(BodyLabel("Owner:"))
        v.addWidget(self.owner_edit)

        self.repo_edit = LineEdit()
        self.repo_edit.setText(self.cloud_mgr.config.GITEE_REPO.value)
        v.addWidget(BodyLabel("Repo:"))
        v.addWidget(self.repo_edit)

        self.user_name_edit = LineEdit()
        self.user_name_edit.setText(self.cloud_mgr.config.user_name.value)
        v.addWidget(BodyLabel("用户名:"))
        v.addWidget(self.user_name_edit)

        layout.insertWidget(1, card)
        btn = PrimaryPushButton("保存配置")
        btn.clicked.connect(self._on_save_settings)
        layout.insertWidget(2, btn)
        return page

    def switch_type(self, ptype):
        for btn in self.type_btns:
            btn.setChecked(btn._type == ptype)
        self.current_type = ptype
        self.force_refresh()

    def switch_tab(self, index, mode=None):
        mode = mode or ["market", "installed", "uploads", "settings"][index]

        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)

        self.stack.setCurrentWidget(self.pages[mode])

        is_settings = mode == "settings"
        self.search_bar.setVisible(not is_settings)
        self.creator_filter.setVisible(not is_settings)
        self.category_filter.setVisible(not is_settings)
        self.sort_combo.setVisible(not is_settings)
        self.batch_btn.setVisible(mode in ["market", "installed"])
        if mode == "market":
            self.batch_btn.setText("批量安装")
            self.batch_btn.setIcon(FluentIcon.DOWNLOAD)
        elif mode == "installed":
            self.batch_btn.setText("批量上传")
            self.batch_btn.setIcon(get_icon("upload"))
        self.upload_btn.setVisible(mode in ["installed", "uploads"])
        self.refresh_btn.setVisible(not is_settings)
        self.select_all_check.setVisible(not is_settings)

        if not is_settings:
            self._refresh_current_view()

    def _cleanup_worker(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def _on_history_changed(self):
        if self._search_bar is not None:
            self._search_history_mgr._history = self._search_bar.get_history()
            self._search_history_mgr._save_history()

    def _refresh_current_view(self):
        idx = self.stack.currentIndex()
        mode = ["market", "installed", "uploads", "settings"][idx]

        if mode == "market":
            self._fetch_cloud_plugins()
        elif mode == "installed":
            self._scan_local_plugins()
        elif mode == "uploads":
            self._scan_local_plugins()
            if not self._cloud_plugins:
                self._fetch_cloud_plugins()
            else:
                self._render_uploads()

    def _start_task(self, total=0):
        self.loading_ring.show()
        self.progress_bar.show()
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(0)
        else:
            self.progress_bar.setRange(0, 0)

    def _stop_task(self):
        self.loading_ring.hide()
        self.progress_bar.hide()

    def _on_local_changed(self):
        self._scan_local_plugins(silent=True)

    def _scan_local_plugins(self, silent=False):
        if not silent:
            self._start_task()

        if self.current_type == "component":
            result = self.scanner.get_components()
            comp_map, _ = result
            user_name = self.cloud_mgr.config.user_name.value
            now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self._local_plugins = []
            for p, cls in comp_map.items():
                cid = str(getattr(cls, "uuid", Path(p).stem))
                entry_file = str(getattr(cls, "_source_file", p))
                self._local_plugins.append(
                    {
                        "unique_id": cid,
                        "plugin_id": cid,
                        "name": getattr(cls, "name", "未命名"),
                        "category": getattr(cls, "category", "常规"),
                        "description": getattr(cls, "description", ""),
                        "version": getattr(cls, "_version", "1.0.0"),
                        "author": user_name,
                        "updated_at": now_time,
                        "created_at": now_time,
                        "entry_file": entry_file,
                        "resource_dir": str(
                            Path(resource_path("app/component_extensions")) / cid
                        ),
                        "is_installed": True,
                        "data_type": "component",
                    }
                )
        else:
            self._local_plugins = []
            try:
                wf_mgr = getattr(self.parent(), "workflow_manager", None) or getattr(
                    self.window(), "workflow_manager", None
                )
                paths = getattr(wf_mgr, "all_workflow_paths", [])
                user_name = self.cloud_mgr.config.user_name.value

                for wf_path in paths:
                    p = Path(wf_path)
                    if not p.exists():
                        continue
                    cid = p.stem.replace(".workflow", "")
                    img_path = Path(str(wf_path).replace(".workflow.json", ".png"))

                    self._local_plugins.append(
                        {
                            "unique_id": cid,
                            "plugin_id": cid,
                            "name": cid,
                            "category": "画布",
                            "description": f"本地画布: {p.name}",
                            "version": datetime.fromtimestamp(
                                p.stat().st_mtime
                            ).strftime("%Y%m%d"),
                            "author": user_name,
                            "updated_at": datetime.fromtimestamp(
                                p.stat().st_mtime
                            ).strftime("%Y-%m-%d %H:%M:%S"),
                            "created_at": datetime.fromtimestamp(
                                p.stat().st_mtime
                            ).strftime("%Y-%m-%d %H:%M:%S"),
                            "entry_file": str(p),
                            "resource_dir": str(img_path) if img_path.exists() else "",
                            "is_installed": True,
                            "data_type": "canvas",
                        }
                    )
            except Exception as e:
                logger.exception(f"扫描画布失败: {e}")

        if not silent:
            self._stop_task()
            self._render_installed()

    def _fetch_cloud_plugins(self):
        if self.active_worker and self.active_worker.isRunning():
            return
        self._start_task()

        manager = self.canvas_mgr if self.current_type == "canvas" else self.cloud_mgr
        self.active_worker = GenericWorker(manager.fetch_all)

        def on_done(data):
            self._cleanup_worker(self.active_worker)
            self._on_cloud_loaded(data)

        def on_error(msg):
            self._cleanup_worker(self.active_worker)
            self._on_error(msg)

        self.active_worker.finished.connect(on_done)
        self.active_worker.error.connect(on_error)
        self.active_worker.start()

    def _on_cloud_loaded(self, data):
        self._cloud_plugins = data or []
        self._update_filters()
        self._stop_task()
        self._render_market()

    def _update_filters(self):
        self.creator_filter.blockSignals(True)
        self.creator_filter.clear()

        self.category_filter.blockSignals(True)
        self.category_filter.clear()

        creators = set()
        categories = set()

        for item in self._cloud_plugins or []:
            author = (
                item.get("author")
                or item.get("创建人")
                or item.get("creator")
                or "未知"
            )
            creators.add(str(author))

            cat = item.get("category") or item.get("组件类别") or "常规"
            categories.add(str(cat))

        self.creator_filter.addItems(["所有作者"] + sorted(list(creators)))
        self.category_filter.addItems(["全部分类"] + sorted(list(categories)))

        self.creator_filter.blockSignals(False)
        self.category_filter.blockSignals(False)

    def _sort_items(self, items):
        if not items:
            return items
        sort_mode = self.sort_combo.currentText()
        sorted_items = list(items)

        if sort_mode == "最新发布":
            sorted_items.sort(
                key=lambda x: x.get("created_at") or x.get("创建时间") or "",
                reverse=True,
            )
        elif sort_mode == "最近更新":
            sorted_items.sort(
                key=lambda x: x.get("updated_at") or x.get("最后修改时间") or "",
                reverse=True,
            )
        elif sort_mode == "名称排序":
            sorted_items.sort(
                key=lambda x: (
                    x.get("name") or x.get("组件名称") or x.get("canvas_name") or ""
                ).lower()
            )

        return sorted_items

    def _render_market(self):
        sorted_plugins = self._sort_items(self._cloud_plugins)
        self._start_streaming_render(sorted_plugins, "market", self.pages["market"])

    def _render_installed(self):
        sorted_plugins = self._sort_items(self._local_plugins)
        self._start_streaming_render(
            sorted_plugins, "installed", self.pages["installed"]
        )

    def _render_uploads(self):
        my_uploads = [
            p
            for p in self._cloud_plugins
            if p.get("author") == self.cloud_mgr.config.user_name.value
        ]
        sorted_uploads = self._sort_items(my_uploads)
        self._start_streaming_render(sorted_uploads, "uploads", self.pages["uploads"])

    def _start_streaming_render(self, items, mode, page):
        if self._render_timer.isActive():
            self._render_timer.stop()

        self._render_queue = []
        page_widget = page.widget()
        self.clear_layout(page_widget.layout())

        groups = {}
        for item in items or []:
            cat = item.get("category") or item.get("组件类别") or "常规"
            groups.setdefault(cat, []).append(item)

        for cat, group_items in groups.items():
            self._render_queue.append((cat, group_items, mode, page))

        self._render_timer.start(10)

    def _process_render_queue(self):
        if not self._render_queue:
            self._render_timer.stop()
            self._on_filter_changed()
            return

        cat, items, mode, page = self._render_queue.pop(0)
        view = self._create_category_view(cat, items, mode, page.widget())
        layout = page.widget().layout()
        layout.insertWidget(layout.count() - 1, view)

    def _create_category_view(self, name, items, mode, parent_container):
        view = QWidget(parent_container)
        v_lay = QVBoxLayout(view)

        cat_check = CheckBox(str(name))
        cat_check.setStyleSheet("color: white; font-weight: bold; font-size: 15px;")
        v_lay.addWidget(cat_check)

        grid = QGridLayout()
        grid.setSpacing(15)

        local_ids = {
            p.get("plugin_id") or p.get("unique_id"): p for p in self._local_plugins
        }

        cards = []
        for i, item in enumerate(items):
            plugin_id = str(
                item.get("plugin_id") or item.get("unique_id") or item.get("组件id")
            )

            if mode == "market":
                is_linked = plugin_id in local_ids
                status = self._get_comparison_status(item)

                local_item = local_ids.get(plugin_id)
                if local_item:
                    item["cloud_updated_at"] = (
                        item.get("updated_at") or item.get("最后修改时间") or ""
                    )
                    item["local_updated_at"] = (
                        local_item.get("updated_at")
                        or local_item.get("最后修改时间")
                        or ""
                    )
            else:
                is_linked = True
                status = "match"

            is_mine = item.get("author") == self.cloud_mgr.config.user_name.value
            admin_list = (
                getattr(self.cloud_mgr.config, "admin_list", []).value
                if hasattr(self.cloud_mgr.config, "admin_list")
                else []
            )
            if isinstance(admin_list, str):
                admin_list = [u.strip() for u in admin_list.split(",") if u.strip()]
            is_admin = (
                self.cloud_mgr.config.user_name.value in admin_list
                if admin_list
                else False
            )

            card = ComponentCard(
                item, mode, is_linked, is_admin or is_mine, status, view
            )
            card.action_signal.connect(self._on_card_action)
            card.check_changed.connect(
                lambda v=view: self._update_category_check_state(v)
            )

            if mode == "market":
                card.delete_signal.connect(self._on_delete_plugin)

            grid.addWidget(card, i // 2, i % 2)
            cards.append(cat_check)

        cat_check.stateChanged.connect(
            lambda st, cs=items: self._on_category_select_all(st, cs, mode)
        )
        v_lay.addLayout(grid)
        return view

    def _get_comparison_status(self, cloud_item):
        cid = str(
            cloud_item.get("plugin_id")
            or cloud_item.get("unique_id")
            or cloud_item.get("组件id")
        )
        local_item = next(
            (
                i
                for i in self._local_plugins
                if str(i.get("plugin_id") or i.get("unique_id")) == cid
            ),
            None,
        )

        if not local_item:
            return "new"

        cv = str(cloud_item.get("version") or cloud_item.get("版本号", "0.0.0"))
        lv = str(local_item.get("version") or local_item.get("版本号", "0.0.0"))

        def parse_version(v):
            v = v.strip()
            parts = []
            for p in v.replace("-", ".").split("."):
                try:
                    parts.append(int(p))
                except:
                    pass
            return tuple(parts) if parts else (0,)

        cv_parsed = parse_version(cv)
        lv_parsed = parse_version(lv)

        if cv_parsed == lv_parsed:
            return "match"
        if cv_parsed < lv_parsed:
            return "old"
        return "diff"

    def _on_card_action(self, data, mode):
        if mode == "market":
            self._install_plugin(data)
        elif mode == "installed":
            self._upload_plugin(data)
        elif mode == "uploads":
            self._update_plugin(data)

    def _install_plugin(self, data):
        self._start_task()

        manager = self.canvas_mgr if self.current_type == "canvas" else self.cloud_mgr
        plugin_id = data.get("plugin_id") or data.get("unique_id")

        if self.current_type == "canvas":
            wf_mgr = getattr(self.window(), "workflow_manager", None)
            target_root = (
                Path(wf_mgr.workflow_dir[0])
                if wf_mgr
                else Path(resource_path("app/workflows"))
            )
            worker = GenericWorker(manager.download_canvas, plugin_id, target_root)
        else:
            worker = GenericWorker(
                manager.download_component, plugin_id, resource_path("")
            )

        def on_done():
            self._cleanup_worker(worker)
            self._stop_task()
            self.force_refresh()

        def on_error(msg):
            self._cleanup_worker(worker)
            self._on_error(msg)

        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _upload_plugin(self, data):
        self._start_task()

        manager = self.canvas_mgr if self.current_type == "canvas" else self.cloud_mgr
        plugin_id = data.get("plugin_id") or data.get("unique_id")

        if self.current_type == "canvas":
            meta = {
                "id": plugin_id,
                "name": data.get("name"),
                "category": data.get("category"),
                "description": data.get("description"),
                "version": data.get("version"),
            }
            worker = GenericWorker(
                manager.add_canvas, meta, data["entry_file"], data["resource_dir"]
            )
        else:
            worker = GenericWorker(
                manager.add_component,
                comp_id=plugin_id,
                name=data.get("name"),
                category=data.get("category"),
                description=data.get("description"),
                requirements=data.get("requirements", "[]"),
                version=data.get("version"),
                entry_file=data["entry_file"],
                resource_dir=data["resource_dir"],
            )

        def on_done():
            self._cleanup_worker(worker)
            self._stop_task()
            self.force_refresh()

        def on_error(msg):
            self._cleanup_worker(worker)
            self._on_error(msg)

        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _update_plugin(self, data):
        self._upload_plugin(data)

    def _on_batch_install(self):
        idx = self.stack.currentIndex()
        if idx == 1:
            self._on_batch_upload()
            return

        if self._render_timer.isActive():
            InfoBar.warning("请稍候", "正在加载...", parent=self)
            return

        page = list(self.pages.values())[idx]
        all_cards = page.widget().findChildren(ComponentCard)
        selected = [
            c.data for c in all_cards if c.check_box.isChecked() and c.isVisible()
        ]

        if not selected:
            InfoBar.warning("提示", "请选择要安装的插件", parent=self)
            return

        self._start_task(total=len(selected))
        completed = 0

        manager = self.canvas_mgr if self.current_type == "canvas" else self.cloud_mgr

        def step_done(w):
            self._cleanup_worker(w)
            nonlocal completed
            completed += 1
            self.progress_bar.setValue(completed)
            if completed >= len(selected):
                self._stop_task()
                InfoBar.success(
                    "批量安装完成", f"成功安装 {completed} 个插件", parent=self
                )
                self.force_refresh()

        def step_error(w, msg):
            self._cleanup_worker(w)
            self._on_error(msg)

        for item in selected:
            plugin_id = item.get("plugin_id") or item.get("unique_id")

            if self.current_type == "canvas":
                wf_mgr = getattr(self.window(), "workflow_manager", None)
                target_root = (
                    Path(wf_mgr.workflow_dir[0])
                    if wf_mgr and wf_mgr.workflow_dir
                    else Path(resource_path("app/workflows"))
                )
                worker = GenericWorker(manager.download_canvas, plugin_id, target_root)
            else:
                worker = GenericWorker(
                    manager.download_component, plugin_id, resource_path("")
                )

            worker.finished.connect(lambda w=worker: step_done(w))
            worker.error.connect(lambda msg, w=worker: step_error(w, msg))
            self._workers.append(worker)
            worker.start()

    def _on_batch_upload(self):
        page = self.pages["installed"].widget()
        all_cards = page.findChildren(ComponentCard)
        selected = [
            c.data for c in all_cards if c.check_box.isChecked() and c.isVisible()
        ]

        if not selected:
            InfoBar.warning("提示", "请选择要上传的插件", parent=self)
            return

        if MessageBox("确认上传", f"上传 {len(selected)} 个插件到云端？", self).exec():
            self._start_task(total=len(selected))
            completed = 0

            manager = (
                self.canvas_mgr if self.current_type == "canvas" else self.cloud_mgr
            )

            def step_done(w):
                self._cleanup_worker(w)
                nonlocal completed
                completed += 1
                self.progress_bar.setValue(completed)
                if completed >= len(selected):
                    self._stop_task()
                    self.force_refresh()
                    InfoBar.success(
                        "上传完成", f"成功上传 {completed} 个插件", parent=self
                    )

            def step_error(w, msg):
                self._cleanup_worker(w)
                self._on_error(msg)

            for item in selected:
                plugin_id = item.get("plugin_id") or item.get("unique_id")

                if self.current_type == "canvas":
                    meta = {
                        "id": plugin_id,
                        "name": item.get("name"),
                        "category": item.get("category"),
                        "description": item.get("description"),
                        "version": item.get("version"),
                    }
                    worker = GenericWorker(
                        manager.add_canvas,
                        meta,
                        item["entry_file"],
                        item["resource_dir"],
                    )
                else:
                    worker = GenericWorker(
                        manager.add_component,
                        comp_id=plugin_id,
                        name=item.get("name"),
                        category=item.get("category"),
                        description=item.get("description"),
                        requirements=item.get("requirements", "[]"),
                        version=item.get("version"),
                        entry_file=item["entry_file"],
                        resource_dir=item["resource_dir"],
                    )

                worker.finished.connect(lambda w=worker: step_done(w))
                worker.error.connect(lambda msg, w=worker: step_error(w, msg))
                self._workers.append(worker)
                worker.start()

    def _on_delete_plugin(self, data):
        plugin_id = data.get("plugin_id") or data.get("unique_id")
        manager = self.canvas_mgr if self.current_type == "canvas" else self.cloud_mgr
        delete_method = (
            manager.delete_canvas
            if self.current_type == "canvas"
            else manager.delete_component
        )

        if MessageBox(
            "确认删除",
            f"删除插件: {data.get('name') or data.get('组件名称') or data.get('canvas_name') or '插件'}？",
            self,
        ).exec():
            self._start_task()
            worker = GenericWorker(delete_method, plugin_id)

            def on_done():
                self._cleanup_worker(worker)
                self._stop_task()
                self.force_refresh()

            def on_error(msg):
                self._cleanup_worker(worker)
                self._on_error(msg)

            worker.finished.connect(on_done)
            worker.error.connect(on_error)
            self._workers.append(worker)
            worker.start()

    def _on_sort_changed(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            self._render_market()
        elif idx == 1:
            self._render_installed()
        elif idx == 2:
            self._render_uploads()

    def _on_filter_changed(self):
        search_text = self.search_bar.text().strip().lower()
        selected_creator = self.creator_filter.currentText()
        selected_category = self.category_filter.currentText()

        idx = self.stack.currentIndex()
        if idx > 2:
            return

        page = list(self.pages.values())[idx]
        cards = page.widget().findChildren(ComponentCard)

        cat_vis = {}
        for card in cards:
            name = str(
                card.data.get("name")
                or card.data.get("组件名称")
                or card.data.get("canvas_name")
                or ""
            ).lower()
            py_full = "".join(lazy_pinyin(name)).lower()
            match_s = search_text in name or search_text in py_full

            author = str(card.data.get("author") or card.data.get("创建人") or "未知")
            match_c = selected_creator == "所有作者" or author == selected_creator

            cat = str(card.data.get("category") or card.data.get("组件类别") or "常规")
            match_cat = selected_category == "全部分类" or cat == selected_category

            vis = match_s and match_c and match_cat
            card.setVisible(vis)
            if vis:
                cat_vis[cat] = True

        container = page.widget()
        for i in range(container.layout().count()):
            w = container.layout().itemAt(i).widget()
            if w:
                chk = w.findChild(CheckBox)
                if chk:
                    w.setVisible(chk.text() in cat_vis)

    def force_refresh(self):
        self._refresh_current_view()

    def _on_error(self, msg):
        self._stop_task()
        InfoBar.error("操作失败", str(msg), parent=self)

    def clear_layout(self, layout):
        if not layout:
            return
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_select_all_changed(self, state):
        page = list(self.pages.values())[self.stack.currentIndex()]
        for card in page.widget().findChildren(ComponentCard):
            if card.isVisible():
                card.check_box.setChecked(state == Qt.Checked)

    def _update_category_check_state(self, cat_widget):
        cat_check = cat_widget.findChild(CheckBox)
        cards = [c for c in cat_widget.findChildren(ComponentCard) if c.isVisible()]
        if not cards:
            return

        checked_num = sum(1 for c in cards if c.check_box.isChecked())
        cat_check.blockSignals(True)

        if checked_num == 0:
            cat_check.setCheckState(Qt.Unchecked)
        elif checked_num == len(cards):
            cat_check.setCheckState(Qt.Checked)
        else:
            cat_check.setCheckState(Qt.PartiallyChecked)

        cat_check.blockSignals(False)

    def _on_category_select_all(self, state, cards, mode):
        if state == Qt.PartiallyChecked:
            return

        page = self.pages[mode].widget()
        for card in page.findChildren(ComponentCard):
            if card.isVisible():
                card.check_box.setChecked(state == Qt.Checked)

    def _on_save_settings(self):
        self.cloud_mgr.config.set(
            self.cloud_mgr.config.GITEE_TOKEN, self.token_edit.text()
        )
        self.cloud_mgr.config.set(
            self.cloud_mgr.config.GITEE_OWNER, self.owner_edit.text()
        )
        self.cloud_mgr.config.set(
            self.cloud_mgr.config.GITEE_REPO, self.repo_edit.text()
        )
        self.cloud_mgr.config.set(
            self.cloud_mgr.config.user_name, self.user_name_edit.text()
        )
        self.cloud_mgr.config.save_config()
        self.cloud_mgr.__init__()
        self.canvas_mgr.__init__()
        InfoBar.success("配置已更新", "重启后生效", parent=self)


PluginManagerCenter = PluginMarketplace
