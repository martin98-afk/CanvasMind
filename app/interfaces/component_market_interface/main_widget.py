# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QWidget,
                             QStackedWidget, QGridLayout, QPushButton)
from loguru import logger
from pypinyin import lazy_pinyin, Style
from qfluentwidgets import (SearchLineEdit, IndeterminateProgressRing, SmoothScrollArea,
                            CardWidget, PrimaryPushButton, FluentIcon, InfoBar,
                            PushButton, ComboBox, MessageBox, ToolButton,
                            CheckBox, LineEdit, BodyLabel, TitleLabel, SubtitleLabel,
                            PasswordLineEdit, ProgressBar)

from app.interfaces.component_market_interface.utils.utils import GenericWorker, calculate_md5
from app.interfaces.component_market_interface.widgets.component_card import ComponentCard
from app.scan_components import ComponentScanner
from app.server_manager.cloud_bakup.canvas_cloud_manager import CanvasCloudManager
from app.server_manager.cloud_bakup.component_cloud_manager import ComponentCloudManager
from app.utils.utils import get_icon, resource_path
from app.widgets.basic_widget.style_sheet import StyleSheet


class PluginManagerCenter(QWidget):
    """ 组件 & 画布云存储管理主界面 (功能全修复完整版) """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MarketCenter")

        self.scanner = ComponentScanner()
        self.cloud_mgr = ComponentCloudManager()
        self.canvas_mgr = CanvasCloudManager()

        self._cloud_cache = []
        self._local_cache = []
        self._cloud_wf_cache = []
        self._local_wf_cache = []

        self.active_worker = None
        self._batch_workers = []  # 强引用，防止异步任务被 GC 回收导致闪退

        self._render_queue = []
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._process_render_queue)

        self.scanner.register_on_change(self._on_local_directory_changed)

        self.init_ui()
        StyleSheet.COMPONENT_MARKET.apply(self)
        self.switch_page(0)

    def init_ui(self):
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("SideBar")
        sidebar.setFixedWidth(200)
        side_lay = QVBoxLayout(sidebar)

        logo = QLabel("资源管理")
        logo.setStyleSheet("color: #f0f6fc; font-weight: 700; font-size: 20px; margin: 30px 20px;")
        side_lay.addWidget(logo)

        self.nav_btns = []
        nav_items = [("组件云端", 0), ("组件本地", 1), ("画布云端", 2), ("画布本地", 3)]
        for text, idx in nav_items:
            btn = QPushButton(text)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda ch, i=idx: self.switch_page(i))
            side_lay.addWidget(btn)
            self.nav_btns.append(btn)

        side_lay.addStretch()
        self.config_btn = QPushButton("云存储设置")
        self.config_btn.setObjectName("NavBtn")
        self.config_btn.setCheckable(True)
        self.config_btn.clicked.connect(lambda: self.switch_page(4))
        side_lay.addWidget(self.config_btn)
        self.nav_btns.append(self.config_btn)
        side_lay.addSpacing(20)
        main_lay.addWidget(sidebar)

        content_panel = QWidget()
        content_lay = QVBoxLayout(content_panel)
        content_lay.setContentsMargins(30, 20, 30, 0)

        self.toolbar = QHBoxLayout()
        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("检索资源 (支持拼音)...")
        self.search_bar.textChanged.connect(self.on_filter_changed)
        self.toolbar.addWidget(self.search_bar, 1)

        self.creator_filter = ComboBox()
        self.creator_filter.setFixedWidth(130)
        self.creator_filter.currentIndexChanged.connect(self.on_filter_changed)
        self.toolbar.addWidget(self.creator_filter)

        self.status_filter = ComboBox()
        self.status_filter.setFixedWidth(130)
        self.status_filter.currentIndexChanged.connect(self.on_filter_changed)
        self.toolbar.addWidget(self.status_filter)

        self.select_all_check = CheckBox("全选")
        self.select_all_check.stateChanged.connect(self.on_select_all_changed)
        self.toolbar.addWidget(self.select_all_check)

        self.batch_btn = PushButton(FluentIcon.DOWNLOAD, "批量下载")
        self.batch_btn.clicked.connect(self.on_batch_install)
        self.toolbar.addWidget(self.batch_btn)

        self.sync_all_btn = PrimaryPushButton(get_icon("upload"), "备份同步")
        self.sync_all_btn.clicked.connect(self.on_sync_all)
        self.toolbar.addWidget(self.sync_all_btn)

        self.refresh_btn = ToolButton(FluentIcon.SYNC, "")
        self.refresh_btn.clicked.connect(self.force_refresh)
        self.toolbar.addWidget(self.refresh_btn)

        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(20, 20)
        self.loading_ring.hide()
        self.toolbar.addWidget(self.loading_ring)
        content_lay.addLayout(self.toolbar)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        content_lay.addWidget(self.progress_bar)
        content_lay.addSpacing(10)

        self.stack = QStackedWidget()
        self.pages = [self._create_scroll_page() for _ in range(4)]
        self.pages.append(self._create_setting_page())
        for p in self.pages: self.stack.addWidget(p)
        content_lay.addWidget(self.stack)
        main_lay.addWidget(content_panel)

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

    def _on_local_directory_changed(self):
        self.scan_local(silent=True)
        self.scan_local_workflows(silent=True)

    # --- 数据扫描 ---
    def scan_local(self, silent=False):
        if not silent: self._start_task()
        result = self.scanner.get_components()
        comp_map, _ = result
        new_local_data = []
        user_name = self.cloud_mgr.config.user_name.value
        now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for p, cls in comp_map.items():
            cid = str(getattr(cls, 'uuid', Path(p).stem))
            entry_file = str(getattr(cls, '_source_file', p))
            new_local_data.append({
                "组件id": cid, "组件名称": getattr(cls, 'name', '未命名'),
                "组件类别": getattr(cls, 'category', '常规'), "组件描述": getattr(cls, 'description', ''),
                "版本号": getattr(cls, '_version', '1.0.0'),
                "MD5": calculate_md5(entry_file) if Path(entry_file).exists() else "",
                "最后修改人": user_name, "最后修改时间": now_time, "创建人": user_name,
                "entry_file": entry_file, "resource_dir": str(Path(resource_path("app/component_extensions")) / cid)
            })
        self._local_cache = new_local_data
        if not silent: self._stop_task()
        if self.stack.currentIndex() == 1: self.render_local()

    def scan_local_workflows(self, silent=False):
        if not silent: self._start_task()
        new_wf_data = []
        try:
            wf_mgr = getattr(self.parent(), 'workflow_manager', None)
            if not wf_mgr: wf_mgr = getattr(self.window(), 'workflow_manager', None)
            paths = getattr(wf_mgr, 'all_workflow_paths', [])
            user_name = self.cloud_mgr.config.user_name.value
            for wf_path in paths:
                p = Path(wf_path)
                if not p.exists(): continue
                cid = p.stem.replace(".workflow", "")
                img_path = Path(str(wf_path).replace(".workflow.json", ".png"))
                safe_img_path = str(img_path) if img_path.exists() else ""

                new_wf_data.append({
                    "组件id": cid, "组件名称": cid, "组件类别": "画布",
                    "组件描述": f"本地画布文件: {p.name}",
                    "版本号": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y%m%d"),
                    "MD5": calculate_md5(str(p)), "创建人": user_name,
                    "最后修改时间": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_file": str(p), "resource_dir": safe_img_path, "data_type": "workflow"
                })
        except Exception as e:
            logger.exception(f"扫描画布失败: {e}")
        self._local_wf_cache = new_wf_data
        if not silent: self._stop_task()
        if self.stack.currentIndex() == 3: self.render_local_workflows()

    # --- 作者筛选更新 ---
    def update_creator_filter(self, items):
        self.creator_filter.blockSignals(True)
        self.creator_filter.clear()
        creators = set()
        for i in (items or []):
            name = i.get('创建人') or i.get('creator') or i.get('author') or '未知'
            creators.add(str(name))
        self.creator_filter.addItems(["所有创建人"] + sorted(list(creators)))
        self.creator_filter.blockSignals(False)

    # --- 渲染逻辑 ---
    def switch_page(self, index):
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)
        self.status_filter.blockSignals(True)
        self.status_filter.clear()
        if index in [0, 2]:
            self.status_filter.addItems(["全部状态", "隐藏已安装", "仅看更新"])
        else:
            self.status_filter.addItems(["全部状态", "未同步", "已同步"])
        self.status_filter.blockSignals(False)

        self.search_bar.setVisible(index != 4)
        self.creator_filter.setVisible(index in [0, 2])
        self.status_filter.setVisible(index != 4)
        self.batch_btn.setVisible(index in [0, 2])
        self.sync_all_btn.setVisible(index in [1, 3])
        self.refresh_btn.setVisible(index != 4)
        self.select_all_check.setVisible(index != 4)
        if index != 4: self.refresh_ui()

    def refresh_ui(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            self.fetch_cloud()
        elif idx == 1:
            self.scan_local()
        elif idx == 2:
            self.fetch_cloud_workflows()
        elif idx == 3:
            self.scan_local_workflows()

    def _start_streaming_render(self, items, mode, page_idx):
        if self._render_timer.isActive(): self._render_timer.stop()
        self._render_queue = []
        page_widget = self.pages[page_idx].widget()
        self.clear_layout(page_widget.layout())
        groups = {}
        for item in (items or []):
            cat = item.get("组件类别") or item.get("category") or "常规"
            groups.setdefault(cat, []).append(item)
        for cat, group_items in groups.items():
            self._render_queue.append((cat, group_items, mode, page_idx))
        self._render_timer.start(10)

    def _process_render_queue(self):
        if not self._render_queue:
            self._render_timer.stop()
            self.on_filter_changed()
            return
        cat, items, mode, page_idx = self._render_queue.pop(0)
        view = self._create_category_view(cat, items, mode, self.pages[page_idx].widget())
        layout = self.pages[page_idx].widget().layout()
        layout.insertWidget(layout.count() - 1, view)

    def render_market(self):
        self._start_streaming_render(self._cloud_cache, "market", 0)

    def render_local(self):
        self._start_streaming_render(self._local_cache, "local", 1)

    def render_market_workflows(self):
        self._start_streaming_render(self._cloud_wf_cache, "market", 2)

    def render_local_workflows(self):
        self._start_streaming_render(self._local_wf_cache, "local", 3)

    def _create_category_view(self, name, items, mode, parent_container):
        view = QWidget(parent_container)
        v_lay = QVBoxLayout(view)
        cat_check = CheckBox(str(name))
        cat_check.setStyleSheet("color: white; font-weight: bold; font-size: 15px;")
        v_lay.addWidget(cat_check)
        grid = QGridLayout()
        grid.setSpacing(15)
        curr_idx = self.stack.currentIndex()
        is_wf = (curr_idx in [2, 3])
        comp_cache = self._local_wf_cache if curr_idx == 2 else (self._local_cache if curr_idx == 0 else [])
        if mode == "local": comp_cache = self._cloud_wf_cache if curr_idx == 3 else self._cloud_cache

        cards = []
        for i, item in enumerate(items):
            if is_wf and mode == "market":
                item["组件id"] = item.get("unique_id")
                item["组件名称"] = item.get("canvas_name")
                item["创建人"] = item.get("author") or "未知"
                item["最后修改时间"] = item.get("updated_at") or "---"
                item["组件类别"] = item.get("category", "画布")
                item["版本号"] = item.get("version", "1.0.0")

            uuid = str(item.get('组件id') or item.get('unique_id'))
            if mode == "market":
                status_code, is_linked = self._get_comparison_status(item, comp_cache)
            else:
                is_linked = any(str(c.get('组件id') or c.get('unique_id')) == uuid for c in comp_cache)
                status_code = "match" if is_linked else "unsynced"

            card = ComponentCard(item, mode, is_linked, (self.cloud_mgr.config.user_name.value == "martin98-afk"),
                                 status_code, view)
            card.action_signal.connect(self.on_card_action)
            card.check_changed.connect(lambda v=view: self._update_category_check_state(v))
            if mode == "market": card.delete_signal.connect(self.on_delete_cloud_resource)
            grid.addWidget(card, i // 2, i % 2)
            cards.append(card)
        cat_check.stateChanged.connect(lambda st, cs=cards: self._on_category_select_all(st, cs))
        v_lay.addLayout(grid)
        return view

    def _get_comparison_status(self, cloud_item, local_list):
        cid = str(cloud_item.get('组件id') or cloud_item.get('unique_id'))
        local_item = next((i for i in local_list if str(i.get('组件id')) == cid), None)
        if not local_item: return "new", False
        cv, lv = str(cloud_item.get('版本号', '0.0.0')), str(local_item.get('版本号', '0.0.0'))
        if cv == lv: return "match", True
        if cv < lv: return "old", True
        return "diff", True

    # --- 后台任务 ---
    def fetch_cloud(self):
        if self.active_worker and self.active_worker.isRunning(): return
        self._start_task()
        self.active_worker = GenericWorker(self.cloud_mgr.fetch_all)
        self.active_worker.finished.connect(self.on_cloud_loaded)
        self.active_worker.error.connect(self.on_error)
        self.active_worker.start()

    def on_cloud_loaded(self, data):
        self._cloud_cache = data or []
        self.update_creator_filter(self._cloud_cache)
        self._stop_task()
        self.render_market()

    def fetch_cloud_workflows(self):
        self._start_task()
        worker = GenericWorker(self.canvas_mgr.fetch_all)

        def on_wf_done(data):
            self._cloud_wf_cache = data or []
            self.update_creator_filter(self._cloud_wf_cache)
            self._stop_task()
            self.render_market_workflows()

        worker.finished.connect(on_wf_done)
        worker.error.connect(self.on_error)
        self._batch_workers.append(worker)
        worker.start()

    def on_card_action(self, data, mode):
        idx = self.stack.currentIndex()
        if idx < 2:
            if mode == "market":
                self.install_component(data)
            else:
                self.upload_component(data)
        else:
            if mode == "market":
                self.install_workflow(data)
            else:
                self.upload_workflow(data)

    def upload_workflow(self, data):
        self._start_task()
        meta = {"id": data['组件id'], "name": data['组件名称'], "category": data['组件类别'],
                "description": data['组件描述'], "version": data['版本号']}
        worker = GenericWorker(self.canvas_mgr.add_canvas, meta, data['entry_file'], data['resource_dir'])
        worker.finished.connect(lambda: self.on_single_sync_done(data['组件名称']))
        worker.error.connect(self.on_error)
        self._batch_workers.append(worker)
        worker.start()

    def install_workflow(self, data):
        self._start_task()
        wf_mgr = getattr(self.window(), 'workflow_manager', None)
        target_root = Path(wf_mgr.all_workflow_paths[0]).parent if wf_mgr and wf_mgr.all_workflow_paths else Path(
            resource_path("app/workflows"))
        worker = GenericWorker(self.canvas_mgr.download_canvas, data['组件id'] or data['unique_id'], target_root)
        worker.finished.connect(lambda: [self._stop_task(), self.force_refresh(),
                                         InfoBar.success("资源已同步", data.get('组件名称'), parent=self)])
        worker.error.connect(self.on_error)
        self._batch_workers.append(worker)
        worker.start()

    def install_component(self, data):
        self._start_task()
        worker = GenericWorker(self.cloud_mgr.download_component, data['组件id'], resource_path(""))
        worker.finished.connect(lambda: [self._stop_task(), self.force_refresh(),
                                         InfoBar.success("还原成功", data['组件名称'], parent=self)])
        worker.error.connect(self.on_error)
        self._batch_workers.append(worker)
        worker.start()

    def upload_component(self, data):
        self._start_task()
        worker = GenericWorker(self.cloud_mgr.add_component, comp_id=data['组件id'], name=data['组件名称'],
                               category=data['组件类别'], description=data['组件描述'],
                               requirements=data.get('工具包需求', "[]"), version=data['版本号'],
                               entry_file=data['entry_file'], resource_dir=data['resource_dir'],
                               extra_data={'MD5': data.get('MD5', '')})
        worker.finished.connect(lambda: self.on_single_sync_done(data['组件名称']))
        worker.error.connect(self.on_error)
        self._batch_workers.append(worker)
        worker.start()

    # --- 批量安装 (已修复并增强) ---
    def on_batch_install(self):
        if self._render_timer.isActive():
            InfoBar.warning("请稍候", "正在加载列表...", parent=self)
            return
        idx = self.stack.currentIndex()
        page = self.pages[idx].widget()
        all_cards = page.findChildren(ComponentCard)
        selected_data = [c.data for c in all_cards if c.check_box.isChecked() and c.isVisible()]
        if not selected_data:
            InfoBar.warning("提示", "请勾选资源", parent=self)
            return

        self._start_task(total=len(selected_data))
        self.completed_count = 0
        self._batch_workers.clear()

        def step_done(worker_obj):
            self.completed_count += 1
            self.progress_bar.setValue(self.completed_count)
            if self.completed_count >= len(selected_data):
                self._stop_task()
                InfoBar.success("批量成功", f"处理完成", parent=self)
                self.force_refresh()

        for d in selected_data:
            if idx == 0:  # 组件云
                worker = GenericWorker(self.cloud_mgr.download_component, d.get('组件id'), resource_path(""))
            else:  # 画布云
                wf_mgr = getattr(self.window(), 'workflow_manager', None)
                target_root = Path(
                    wf_mgr.all_workflow_paths[0]).parent if wf_mgr and wf_mgr.all_workflow_paths else Path(
                    resource_path("app/workflows"))
                worker = GenericWorker(self.canvas_mgr.download_canvas, d.get('组件id') or d.get('unique_id'),
                                       target_root)

            worker.finished.connect(lambda w=worker: step_done(w))
            worker.error.connect(self.on_error)
            self._batch_workers.append(worker)
            worker.start()

    def on_sync_all(self):
        idx = self.stack.currentIndex()
        cards = self.pages[idx].widget().findChildren(ComponentCard)
        selected = [c.data for c in cards if c.check_box.isChecked() and c.isVisible()]
        if not selected: return
        if MessageBox("确认同步", f"备份 {len(selected)} 个资源？", self).exec():
            self._start_task()
            if idx == 3:
                formatted = [{"meta": {"id": s['组件id'], "name": s['组件名称'], "category": s['组件类别'],
                                       "version": s['版本号'], "description": s['组件描述']},
                              "json_path": s['entry_file'], "image_path": s['resource_dir']} for s in selected]
                worker = GenericWorker(self.canvas_mgr.sync_local_to_cloud, formatted)
            else:
                worker = GenericWorker(self.cloud_mgr.sync_local_to_cloud, selected)
            worker.finished.connect(
                lambda: [self._stop_task(), self.force_refresh(), InfoBar.success("同步完成", "", parent=self)])
            worker.error.connect(self.on_error)
            self._batch_workers.append(worker)
            worker.start()

    def on_delete_cloud_resource(self, data):
        idx = self.stack.currentIndex()
        cid = data.get('组件id') or data.get('unique_id')
        mgr = self.canvas_mgr if idx == 2 else self.cloud_mgr
        if MessageBox("警告", "确定删除？", self).exec():
            self._start_task()
            worker = GenericWorker(mgr.delete_canvas if idx == 2 else mgr.delete_component, cid)
            worker.finished.connect(
                lambda: [self._stop_task(), self.force_refresh(), InfoBar.success("已删除", "", parent=self)])
            worker.error.connect(self.on_error)
            self._batch_workers.append(worker)
            worker.start()

    # --- UI 辅助 ---
    def on_filter_changed(self):
        search_text = self.search_bar.text().strip().lower()
        selected_creator = self.creator_filter.currentText()
        status_mode = self.status_filter.currentText()
        idx = self.stack.currentIndex()
        if idx > 3: return

        container = self.pages[idx].widget()
        cards = container.findChildren(ComponentCard)
        cat_vis = {}
        for card in cards:
            name = str(card.data.get('组件名称') or card.data.get('canvas_name') or '').lower()
            py_full = "".join(lazy_pinyin(name)).lower()
            match_s = search_text in name or search_text in py_full

            match_c = True
            if idx in [0, 2]:
                creator = str(card.data.get('创建人') or card.data.get('creator') or card.data.get('author') or '未知')
                match_c = (selected_creator == "所有创建人" or creator == selected_creator)

            match_st = True
            if idx in [0, 2]:
                if status_mode == "隐藏已安装":
                    match_st = card.status_code != "match"
                elif status_mode == "仅看更新":
                    match_st = card.status_code == "diff"

            vis = match_s and match_c and match_st
            card.setVisible(vis)
            if vis: cat_vis[str(card.data.get('组件类别') or card.data.get('category'))] = True

        for i in range(container.layout().count()):
            w = container.layout().itemAt(i).widget()
            if w:
                chk = w.findChild(CheckBox)
                if chk: w.setVisible(chk.text() in cat_vis)

    def force_refresh(self):
        idx = self.stack.currentIndex()
        if idx in [0, 1]:
            self._cloud_cache = []
        else:
            self._cloud_wf_cache = []
        self.refresh_ui()

    def on_single_sync_done(self, name):
        self._stop_task();
        InfoBar.success("同步成功", name, parent=self);
        self.force_refresh()

    def on_error(self, msg):
        self._stop_task();
        InfoBar.error("异常", str(msg), parent=self)

    def clear_layout(self, layout):
        if not layout: return
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def on_select_all_changed(self, state):
        for card in self.pages[self.stack.currentIndex()].widget().findChildren(ComponentCard):
            if card.isVisible(): card.check_box.setChecked(state == Qt.Checked)

    def _update_category_check_state(self, cat_widget):
        cat_check = cat_widget.findChild(CheckBox)
        cards = [c for c in cat_widget.findChildren(ComponentCard) if c.isVisible()]
        if not cards: return
        checked_num = sum(1 for c in cards if c.check_box.isChecked())
        cat_check.blockSignals(True)
        if checked_num == 0:
            cat_check.setCheckState(Qt.Unchecked)
        elif checked_num == len(cards):
            cat_check.setCheckState(Qt.Checked)
        else:
            cat_check.setCheckState(Qt.PartiallyChecked)
        cat_check.blockSignals(False)

    def _on_category_select_all(self, state, cards):
        if state == Qt.PartiallyChecked: return
        for card in cards:
            if card.isVisible(): card.check_box.setChecked(state == Qt.Checked)

    def _create_scroll_page(self):
        scroll = SmoothScrollArea();
        scroll.setWidgetResizable(True);
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget();
        lay = QVBoxLayout(container);
        lay.setAlignment(Qt.AlignTop);
        lay.addStretch();
        scroll.setWidget(container)
        return scroll

    def _create_setting_page(self):
        page = self._create_scroll_page();
        layout = page.widget().layout()
        layout.insertWidget(0, TitleLabel("Gitee 存储配置"))
        card = CardWidget();
        v = QVBoxLayout(card)
        self.token_edit = PasswordLineEdit();
        self.token_edit.setText(self.cloud_mgr.config.GITEE_TOKEN.value);
        v.addWidget(BodyLabel("Access Token:"));
        v.addWidget(self.token_edit)
        self.owner_edit = LineEdit();
        self.owner_edit.setText(self.cloud_mgr.config.GITEE_OWNER.value);
        v.addWidget(BodyLabel("Owner:"));
        v.addWidget(self.owner_edit)
        self.repo_edit = LineEdit();
        self.repo_edit.setText(self.cloud_mgr.config.GITEE_REPO.value);
        v.addWidget(BodyLabel("Repo:"));
        v.addWidget(self.repo_edit)
        layout.insertWidget(1, card);
        btn = PrimaryPushButton("保存配置");
        btn.clicked.connect(self.on_save_settings);
        layout.insertWidget(2, btn)
        return page

    def on_save_settings(self):
        self.cloud_mgr.config.set(self.cloud_mgr.config.GITEE_TOKEN, self.token_edit.text());
        self.cloud_mgr.config.set(self.cloud_mgr.config.GITEE_OWNER, self.owner_edit.text());
        self.cloud_mgr.config.set(self.cloud_mgr.config.GITEE_REPO, self.repo_edit.text());
        self.cloud_mgr.config.save_config();
        self.cloud_mgr.__init__();
        self.canvas_mgr.__init__();
        InfoBar.success("配置已更新", "重载成功", parent=self)