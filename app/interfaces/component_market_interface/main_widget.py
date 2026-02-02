# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QWidget,
                             QStackedWidget, QGridLayout, QPushButton)
# 导入拼音库
from pypinyin import lazy_pinyin, Style
from qfluentwidgets import (SearchLineEdit, IndeterminateProgressRing, SmoothScrollArea,
                            CardWidget, PrimaryPushButton, FluentIcon, InfoBar,
                            PushButton, ComboBox, MessageBox, ToolButton,
                            CheckBox, LineEdit, BodyLabel, TitleLabel, SubtitleLabel,
                            PasswordLineEdit, ProgressBar)

from app.interfaces.component_market_interface.utils.utils import GenericWorker, calculate_md5
from app.interfaces.component_market_interface.widgets.component_card import ComponentCard
from app.scan_components import ComponentScanner
from app.server_manager.cloud_bakup.component_cloud_manager import ComponentCloudManager
from app.utils.utils import get_icon, resource_path
from app.widgets.basic_widget.style_sheet import StyleSheet


class PluginManagerCenter(QWidget):
    """ 组件云存储管理主界面 (流式渲染平滑版) """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MarketCenter")

        self.scanner = ComponentScanner()
        self.cloud_mgr = ComponentCloudManager()

        self._cloud_cache = []
        self._local_cache = []
        self.active_worker = None
        self._batch_workers = []  # 存储批量任务，防止 GC 闪退

        # --- 流式渲染控制 ---
        self._render_queue = []
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._process_render_queue)

        # 注册扫描器监听：当本地文件变化时，触发后台数据更新
        self.scanner.register_on_change(self._on_local_directory_changed)

        self.init_ui()
        StyleSheet.COMPONENT_MARKET.apply(self)
        self.switch_page(0)

    def init_ui(self):
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # 侧边栏
        sidebar = QWidget()
        sidebar.setObjectName("SideBar")
        sidebar.setFixedWidth(200)
        side_lay = QVBoxLayout(sidebar)

        logo = QLabel("组件市场")
        logo.setStyleSheet("color: #f0f6fc; font-weight: 700; font-size: 20px; margin: 30px 20px;")
        side_lay.addWidget(logo)

        self.nav_btns = []
        for text, idx in [("云端库", 0), ("本地站", 1)]:
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
        self.config_btn.clicked.connect(lambda: self.switch_page(2))
        side_lay.addWidget(self.config_btn)
        self.nav_btns.append(self.config_btn)
        side_lay.addSpacing(20)
        main_lay.addWidget(sidebar)

        # 内容区
        content_panel = QWidget()
        content_lay = QVBoxLayout(content_panel)
        content_lay.setContentsMargins(30, 20, 30, 0)

        # 工具栏
        self.toolbar = QHBoxLayout()
        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("检索组件 (支持拼音/首字母)...")
        self.search_bar.textChanged.connect(self.on_filter_changed)
        self.toolbar.addWidget(self.search_bar, 1)

        self.creator_filter = ComboBox()
        self.creator_filter.setFixedWidth(130)
        self.creator_filter.currentIndexChanged.connect(self.on_filter_changed)
        self.toolbar.addWidget(self.creator_filter)

        self.status_filter = ComboBox()
        self.status_filter.setFixedWidth(130)
        # 初始填充云端状态
        self.status_filter.addItems(["全部状态", "隐藏已安装", "仅看更新"])
        self.status_filter.currentIndexChanged.connect(self.on_filter_changed)
        self.toolbar.addWidget(self.status_filter)

        self.select_all_check = CheckBox("全选所有")
        self.select_all_check.stateChanged.connect(self.on_select_all_changed)
        self.toolbar.addWidget(self.select_all_check)

        self.batch_btn = PushButton(FluentIcon.DOWNLOAD, "批量安装")
        self.batch_btn.clicked.connect(self.on_batch_install)
        self.toolbar.addWidget(self.batch_btn)

        self.sync_all_btn = PrimaryPushButton(get_icon("upload"), "备份同步")
        self.sync_all_btn.clicked.connect(self.on_sync_all)
        self.toolbar.addWidget(self.sync_all_btn)

        self.refresh_btn = ToolButton(FluentIcon.SYNC, "")
        self.refresh_btn.setFixedWidth(40)
        self.refresh_btn.clicked.connect(self.force_refresh)
        self.toolbar.addWidget(self.refresh_btn)

        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(20, 20)
        self.loading_ring.hide()
        self.toolbar.addWidget(self.loading_ring)
        content_lay.addLayout(self.toolbar)

        # 进度条 (Header下方)
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        content_lay.addWidget(self.progress_bar)
        content_lay.addSpacing(10)

        self.stack = QStackedWidget()
        self.pages = [self._create_scroll_page() for _ in range(2)]
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
            self.progress_bar.setRange(0, 0)  # 忙碌状态

    def _stop_task(self):
        self.loading_ring.hide()
        self.progress_bar.hide()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

    def _on_local_directory_changed(self):
        """ 后台静默更新数据结构 """
        self.scan_local(silent=True)

    def scan_local(self, silent=False):
        if not silent: self._start_task()
        result = self.scanner.get_components()
        self.on_local_loaded(result, silent)

    def on_local_loaded(self, result, silent=False):
        comp_map, _ = result
        new_local_data = []
        user_name = self.cloud_mgr.config.user_name.value
        now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for p, cls in comp_map.items():
            cid = str(getattr(cls, 'uuid', Path(p).stem))
            entry_file = str(getattr(cls, '_source_file', p))
            md5_val = calculate_md5(entry_file) if Path(entry_file).exists() else ""

            new_local_data.append({
                "组件id": cid,
                "组件名称": getattr(cls, 'name', '未命名'),
                "组件类别": getattr(cls, 'category', '常规'),
                "组件描述": getattr(cls, 'description', ''),
                "工具包需求": getattr(cls, 'requirements', "[]"),
                "版本号": getattr(cls, '_version', '1.0.0'),
                "MD5": md5_val,
                "最后修改人": user_name, "最后修改时间": now_time,
                "创建人": user_name,
                "entry_file": entry_file,
                "resource_dir": str(Path(resource_path("app/component_extensions")) / cid)
            })
        self._local_cache = new_local_data

        if not silent: self._stop_task()

        if not silent or self.stack.currentIndex() == 1:
            if self.stack.currentIndex() == 0:
                self.render_market()
            elif self.stack.currentIndex() == 1:
                self.render_local()

    def _get_comparison_status(self, cloud_item):
        """ 增强版更新判断：版本号 + MD5 """
        if not cloud_item: return "new", False
        cid = str(cloud_item.get('组件id') or cloud_item.get('unique_id'))
        cloud_ver = str(cloud_item.get('版本号') or cloud_item.get('version', ''))
        cloud_md5 = cloud_item.get('MD5', '')

        local_item = next((i for i in self._local_cache if str(i.get('组件id')) == cid), None)
        if not local_item: return "new", False

        if cloud_ver != str(local_item.get('版本号')):
            return "diff", True
        if cloud_md5 and local_item.get('MD5') and cloud_md5 != local_item.get('MD5'):
            return "diff", True

        return "match", True

    def switch_page(self, index):
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)

        self.status_filter.blockSignals(True)
        self.status_filter.clear()
        if index == 0:
            self.status_filter.addItems(["全部状态", "隐藏已安装", "仅看更新"])
        elif index == 1:
            self.status_filter.addItems(["全部状态", "未同步", "已同步"])
        self.status_filter.blockSignals(False)

        is_setting = (index == 2)
        self.select_all_check.setVisible(not is_setting)
        self.search_bar.setVisible(not is_setting)
        self.creator_filter.setVisible(index == 0)
        self.status_filter.setVisible(not is_setting)
        self.batch_btn.setVisible(index == 0)
        self.sync_all_btn.setVisible(index == 1)
        self.refresh_btn.setVisible(not is_setting)
        if not is_setting: self.refresh_ui()

    def on_filter_changed(self):
        """ 增强过滤：拼音支持 + 本地同步状态过滤 """
        search_text = self.search_bar.text().strip().lower()
        selected_creator = self.creator_filter.currentText()
        status_mode = self.status_filter.currentText()
        idx = self.stack.currentIndex()
        if idx > 1: return

        container = self.pages[idx].widget()
        # 优化可见性查找，防止布局错误
        cards = container.findChildren(ComponentCard)

        # 记录每个大类容器里是否有可见卡片
        category_vis = {}

        for card in cards:
            name = str(card.data.get('组件名称', '')).lower()
            cid = str(card.data.get('组件id', '')).lower()
            cat = str(card.data.get('组件类别', '常规'))

            py_full = "".join(lazy_pinyin(name)).lower()
            py_first = "".join(lazy_pinyin(name, style=Style.FIRST_LETTER)).lower()
            match_s = search_text in name or search_text in cid or search_text in py_full or search_text in py_first

            match_st = True
            if idx == 0:
                if status_mode == "隐藏已安装":
                    match_st = card.status_code != "match"
                elif status_mode == "仅看更新":
                    match_st = card.status_code == "diff"
            elif idx == 1:
                is_linked = any(str(c.get('组件id') or c.get('unique_id')) == str(card.data.get('组件id')) for c in
                                self._cloud_cache)
                if status_mode == "未同步":
                    match_st = not is_linked
                elif status_mode == "已同步":
                    match_st = is_linked

            match_c = (idx == 1) or (
                        selected_creator == "所有创建人" or str(card.data.get('创建人')) == selected_creator)

            vis = match_s and match_c and match_st
            card.setVisible(vis)
            if vis:
                category_vis[cat] = True

        # 更新大类容器的可见性
        for i in range(container.layout().count()):
            item = container.layout().itemAt(i)
            if item and item.widget():
                widget = item.widget()
                title_item = widget.layout().itemAt(0)
                if title_item and title_item.layout():
                    check = title_item.layout().itemAt(0).widget()
                    if isinstance(check, CheckBox):
                        widget.setVisible(check.text() in category_vis)

    def _start_streaming_render(self, items: List[Dict], mode: str, page_idx: int):
        """ 启动流式渲染队列 """
        if self._render_timer.isActive():
            self._render_timer.stop()

        self._render_queue = []
        page_widget = self.pages[page_idx].widget()
        self.clear_layout(page_widget.layout())

        groups = {}
        for item in (items or []):
            cat = item.get("组件类别") or "常规"
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
        page_widget = self.pages[page_idx].widget()

        view = self._create_category_view(cat, items, mode, page_widget)
        layout = page_widget.layout()
        layout.insertWidget(layout.count() - 1, view)

    def render_market(self):
        self._start_streaming_render(self._cloud_cache, "market", 0)

    def render_local(self):
        self._start_streaming_render(self._local_cache, "local", 1)

    def _create_category_view(self, name, items, mode, parent_container):
        view = QWidget(parent_container)
        v_lay = QVBoxLayout(view)
        v_lay.setContentsMargins(0, 10, 0, 10)
        h_lay = QHBoxLayout()
        cat_check = CheckBox(str(name))
        cat_check.setStyleSheet("color: white; font-weight: bold; font-size: 15px;")
        h_lay.addWidget(cat_check)
        h_lay.addStretch()
        v_lay.addLayout(h_lay)
        grid = QGridLayout()
        grid.setSpacing(15)
        user_name = self.cloud_mgr.config.user_name.value
        is_admin = (user_name == "martin98-afk")
        cards = []
        for i, item in enumerate(items):
            uuid = str(item.get('组件id') or item.get('unique_id'))
            if mode == "market":
                status_code, is_linked = self._get_comparison_status(item)
            else:
                is_linked = any(str(c.get('组件id') or c.get('unique_id')) == uuid for c in self._cloud_cache)
                status_code = "match" if is_linked else "unsynced"

            card = ComponentCard(item, mode, is_linked, is_admin, status_code, view)
            card.action_signal.connect(self.on_card_action)
            card.check_changed.connect(lambda v=view: self._update_category_check_state(v))
            if mode == "market": card.delete_signal.connect(self.on_delete_cloud_component)
            grid.addWidget(card, i // 2, i % 2)
            cards.append(card)
        cat_check.stateChanged.connect(lambda st, cs=cards: self._on_category_select_all(st, cs))
        v_lay.addLayout(grid)
        return view

    def install_component(self, data, silent=False):
        if not silent: self._start_task()
        cid = data.get('组件id') or data.get('unique_id')
        # 创建局部 Worker 存储，防止内存回收
        worker = GenericWorker(self.cloud_mgr.download_component, cid, resource_path(""))

        def on_done():
            if not silent:
                self._stop_task()
                InfoBar.success("安装成功", f"组件 [{data.get('组件名称')}] 已还原", parent=self)
            self.force_refresh()
            if worker in self._batch_workers: self._batch_workers.remove(worker)

        worker.finished.connect(on_done)
        worker.error.connect(self.on_error)
        self._batch_workers.append(worker)  # 维持引用
        worker.start()

    def on_batch_install(self):
        """ 彻底重构：通过 findChildren 查找卡片，安全、可靠、不闪退 """
        if self._render_timer.isActive():
            InfoBar.warning("请稍候", "正在加载组件列表，请加载完成后再操作", parent=self)
            return

        page = self.pages[0].widget()
        # 直接查找所有 ComponentCard，不走 layout 遍历，避开 NoneType 报错
        all_cards = page.findChildren(ComponentCard)
        selected_data = [c.data for c in all_cards if c.check_box.isChecked() and c.isVisible()]

        if not selected_data:
            InfoBar.warning("提示", "请勾选需要安装的组件", parent=self)
            return

        self._start_task(total=len(selected_data))
        self.completed_count = 0

        # 清理旧任务引用
        self._batch_workers.clear()

        def step_done(worker_obj):
            self.completed_count += 1
            self.progress_bar.setValue(self.completed_count)
            if worker_obj in self._batch_workers:
                self._batch_workers.remove(worker_obj)

            if self.completed_count >= len(selected_data):
                self._stop_task()
                InfoBar.success("批量成功", f"已成功处理 {len(selected_data)} 个任务", parent=self)
                self.force_refresh()

        for d in selected_data:
            cid = d.get('组件id') or d.get('unique_id')
            worker = GenericWorker(self.cloud_mgr.download_component, cid, resource_path(""))
            # 使用 lambda 闭包保持 worker 引用
            worker.finished.connect(lambda w=worker: step_done(w))
            worker.error.connect(self.on_error)
            self._batch_workers.append(worker)
            worker.start()

    def upload_component(self, data):
        self._start_task()
        worker = GenericWorker(
            self.cloud_mgr.add_component,
            comp_id=data['组件id'], name=data['组件名称'], category=data['组件类别'],
            version=data['版本号'], entry_file=data['entry_file'], resource_dir=data['resource_dir'],
            extra_data={'MD5': data.get('MD5', '')}
        )
        worker.finished.connect(lambda: self.on_single_sync_done(data['组件名称']))
        worker.error.connect(self.on_worker_error)
        self._batch_workers.append(worker)
        worker.start()

    def on_sync_all(self):
        if self._render_timer.isActive(): return

        page = self.pages[1].widget()
        all_cards = page.findChildren(ComponentCard)
        selected_data = [c.data for c in all_cards if c.check_box.isChecked() and c.isVisible()]

        sync_target = selected_data if selected_data else self._local_cache
        if not sync_target: return

        if MessageBox("确认备份同步", f"同步 {len(sync_target)} 个组件至 Gitee？", self).exec():
            self._start_task()
            worker = GenericWorker(self.cloud_mgr.sync_local_to_cloud, sync_target)
            worker.finished.connect(lambda: [
                self._stop_task(), self.force_refresh(),
                InfoBar.success("同步完成", "云端库已更新", parent=self)
            ])
            worker.error.connect(self.on_error)
            self._batch_workers.append(worker)
            worker.start()

    def _create_scroll_page(self):
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setAlignment(Qt.AlignTop)
        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _create_setting_page(self):
        page = SmoothScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 10, 30)
        layout.setSpacing(25)
        title = TitleLabel("Gitee 存储配置")
        title.setStyleSheet("color: white; margin-bottom: 10px;")
        layout.addWidget(title)

        gitee_card = CardWidget(container)
        gitee_lay = QVBoxLayout(gitee_card)
        gitee_lay.addWidget(SubtitleLabel("Gitee 仓库信息"))
        gitee_lay.addWidget(BodyLabel("配置用于备份组件 ZIP 资源的仓库。"))

        self.token_edit = PasswordLineEdit()
        self.token_edit.setText(self.cloud_mgr.config.GITEE_TOKEN.value)
        self.token_edit.setPlaceholderText("Gitee Access Token...")
        gitee_lay.addWidget(BodyLabel("Access Token:"))
        gitee_lay.addWidget(self.token_edit)

        self.owner_edit = LineEdit()
        self.owner_edit.setText(self.cloud_mgr.config.GITEE_OWNER.value)
        self.owner_edit.setPlaceholderText("仓库所有者 (Owner)...")
        gitee_lay.addWidget(BodyLabel("Owner:"))
        gitee_lay.addWidget(self.owner_edit)

        self.repo_edit = LineEdit()
        self.repo_edit.setText(self.cloud_mgr.config.GITEE_REPO.value)
        self.repo_edit.setPlaceholderText("仓库名 (Repo Name)...")
        gitee_lay.addWidget(BodyLabel("Repo:"))
        gitee_lay.addWidget(self.repo_edit)
        layout.addWidget(gitee_card)

        user_card = CardWidget(container)
        user_lay = QHBoxLayout(user_card)
        user_name = self.cloud_mgr.config.user_name.value
        user_lay.addWidget(BodyLabel(f"当前同步身份: <b>{user_name}</b>"))
        user_lay.addStretch()
        if user_name == "martin98-afk":
            badge = QLabel("管理员模式")
            badge.setObjectName("TagLabel")
            user_lay.addWidget(badge)
        layout.addWidget(user_card)

        save_btn = PrimaryPushButton(FluentIcon.SAVE, "应用并保存配置")
        save_btn.setFixedWidth(200)
        save_btn.clicked.connect(self.on_save_settings)
        layout.addWidget(save_btn, 0, Qt.AlignLeft)

        layout.addStretch()
        page.setWidget(container)
        return page

    def on_save_settings(self):
        token = self.token_edit.text().strip()
        owner = self.owner_edit.text().strip()
        repo = self.repo_edit.text().strip()
        if not token or not owner or not repo:
            InfoBar.warning("格式错误", "配置信息不能为空", parent=self)
            return
        self.cloud_mgr.config.set(self.cloud_mgr.config.GITEE_TOKEN, token)
        self.cloud_mgr.config.set(self.cloud_mgr.config.GITEE_OWNER, owner)
        self.cloud_mgr.config.set(self.cloud_mgr.config.GITEE_REPO, repo)
        self.cloud_mgr.config.save_config()
        self.cloud_mgr.__init__()
        InfoBar.success("配置已更新", "Gitee 适配器重连成功", parent=self)

    def fetch_cloud(self):
        if self.active_worker and self.active_worker.isRunning(): return
        self._start_task()
        self.active_worker = GenericWorker(self.cloud_mgr.fetch_all)
        self.active_worker.finished.connect(self.on_cloud_loaded)
        self.active_worker.error.connect(self.on_error)
        self.active_worker.start()

    def on_cloud_loaded(self, data):
        self._cloud_cache = data or []
        creators = sorted(list(set([str(i.get('创建人') or i.get('creator') or '未知') for i in self._cloud_cache])))
        self.creator_filter.blockSignals(True)
        self.creator_filter.clear()
        self.creator_filter.addItems(["所有创建人"] + creators)
        self.creator_filter.blockSignals(False)
        self._stop_task()
        self.render_market()

    def on_card_action(self, data, mode):
        if mode == "market":
            self.install_component(data)
        else:
            self.upload_component(data)

    def on_delete_cloud_component(self, data):
        cid = data.get('组件id') or data.get('unique_id')
        comp_name = data.get('组件名称') or '未知'
        if MessageBox("危险操作", f"从云端彻底删除 [{comp_name}] ？", self).exec():
            self._start_task()
            worker = GenericWorker(self.cloud_mgr.delete_component, cid)
            worker.finished.connect(
                lambda: [self._stop_task(), self.force_refresh(), InfoBar.success("已删除", comp_name, parent=self)])
            worker.error.connect(self.on_error)
            self._batch_workers.append(worker)
            worker.start()

    def force_refresh(self):
        if self.stack.currentIndex() == 0:
            self._cloud_cache = []
        elif self.stack.currentIndex() == 1:
            self._local_cache = []
        self.refresh_ui()

    def refresh_ui(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            if not self._local_cache: self.scan_local(silent=True)
            if not self._cloud_cache:
                self.fetch_cloud()
            else:
                self.render_market()
        elif idx == 1:
            self.scan_local()

    def on_single_sync_done(self, name):
        self._stop_task()
        InfoBar.success("同步成功", f"组件 [{name}] 已推送至 Gitee", parent=self)
        self.force_refresh()

    def on_error(self, msg):
        self._stop_task()
        InfoBar.error("异常", str(msg), parent=self)

    def on_worker_error(self, msg):
        self.on_error(msg)

    def clear_layout(self, layout):
        if not layout: return
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())

    def on_select_all_changed(self, state):
        is_checked = (state == Qt.Checked)
        container = self.pages[self.stack.currentIndex()].widget()
        cards = container.findChildren(ComponentCard)
        for card in cards:
            if card.isVisible():
                card.check_box.blockSignals(True)
                card.check_box.setChecked(is_checked)
                card.check_box.blockSignals(False)

    def _update_category_check_state(self, cat_widget):
        # 通过查找子卡片更新大类复选框，安全稳定
        cat_check = cat_widget.findChild(CheckBox)
        cards = cat_widget.findChildren(ComponentCard)
        visible_cards = [c for c in cards if c.isVisible()]

        if not visible_cards: return
        checked_num = sum(1 for c in visible_cards if c.check_box.isChecked())

        cat_check.blockSignals(True)
        if checked_num == 0:
            cat_check.setCheckState(Qt.Unchecked)
        elif checked_num == len(visible_cards):
            cat_check.setCheckState(Qt.Checked)
        else:
            cat_check.setCheckState(Qt.PartiallyChecked)
        cat_check.blockSignals(False)

    def _on_category_select_all(self, state, cards):
        if state == Qt.PartiallyChecked: return
        is_checked = (state == Qt.Checked)
        for card in cards:
            if card.isVisible():
                card.check_box.blockSignals(True)
                card.check_box.setChecked(is_checked)
                card.check_box.blockSignals(False)