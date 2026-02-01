# -*- coding: utf-8 -*-
import webbrowser
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QWidget,
                             QStackedWidget, QGridLayout, QPushButton)
from qfluentwidgets import (SearchLineEdit, IndeterminateProgressRing, SmoothScrollArea,
                            CardWidget, PrimaryPushButton, FluentIcon, InfoBar,
                            PushButton, ComboBox, MessageBox, ToolButton,
                            CheckBox, LineEdit, BodyLabel, TitleLabel, SubtitleLabel)

from app.interfaces.component_market_interface.utils.utils import GenericWorker, calculate_md5
from app.interfaces.component_market_interface.widgets.component_card import ComponentCard
from app.scan_components import ComponentScanner
from app.server_manager.cloud_bakup.component_cloud_manager import ComponentCloudManager
from app.utils.utils import get_icon, resource_path
from app.widgets.basic_widget.style_sheet import StyleSheet


# --- 主界面 ---
class PluginManagerCenter(QWidget):
    """ 组件云存储管理主界面 (Gitee 完全重构版) """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MarketCenter")

        self.scanner = ComponentScanner()
        self.cloud_mgr = ComponentCloudManager()

        self._cloud_cache = []
        self._local_cache = []
        self.active_worker = None

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

        self.toolbar = QHBoxLayout()
        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("检索组件...")
        self.search_bar.textChanged.connect(self.on_filter_changed)
        self.toolbar.addWidget(self.search_bar, 1)

        self.creator_filter = ComboBox()
        self.creator_filter.setFixedWidth(130)
        self.creator_filter.currentIndexChanged.connect(self.on_filter_changed)
        self.toolbar.addWidget(self.creator_filter)

        # 状态过滤器
        self.status_filter = ComboBox()
        self.status_filter.setFixedWidth(130)
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

        self.stack = QStackedWidget()
        self.pages = [self._create_scroll_page() for _ in range(2)]
        self.pages.append(self._create_setting_page())

        for p in self.pages: self.stack.addWidget(p)
        content_lay.addWidget(self.stack)
        main_lay.addWidget(content_panel)

    def _create_scroll_page(self):
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        QVBoxLayout(container).setAlignment(Qt.AlignTop)
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

        self.token_edit = LineEdit()
        self.token_edit.setText(self.cloud_mgr.config.GITEE_TOKEN.value)
        self.token_edit.setPlaceholderText("Gitee Access Token...")
        gitee_lay.addWidget(QLabel("Access Token:"))
        gitee_lay.addWidget(self.token_edit)

        self.owner_edit = LineEdit()
        self.owner_edit.setText(self.cloud_mgr.config.GITEE_OWNER.value)
        self.owner_edit.setPlaceholderText("仓库所有者 (Owner)...")
        gitee_lay.addWidget(QLabel("Owner:"))
        gitee_lay.addWidget(self.owner_edit)

        self.repo_edit = LineEdit()
        self.repo_edit.setText(self.cloud_mgr.config.GITEE_REPO.value)
        self.repo_edit.setPlaceholderText("仓库名 (Repo Name)...")
        gitee_lay.addWidget(QLabel("Repo:"))
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

    def on_select_all_changed(self, state):
        is_checked = (state == Qt.Checked)
        container = self.pages[self.stack.currentIndex()].widget()
        for i in range(container.layout().count()):
            cat_widget = container.layout().itemAt(i).widget()
            if not cat_widget or not cat_widget.isVisible(): continue
            grid_item = cat_widget.layout().itemAt(1)
            if not grid_item or not grid_item.layout(): continue
            grid = grid_item.layout()
            for j in range(grid.count()):
                card = grid.itemAt(j).widget()
                if isinstance(card, ComponentCard) and card.isVisible():
                    card.check_box.blockSignals(True)
                    card.check_box.setChecked(is_checked)
                    card.check_box.blockSignals(False)

            title_lay = cat_widget.layout().itemAt(0).layout()
            cat_check = title_lay.itemAt(0).widget()
            if isinstance(cat_check, CheckBox):
                cat_check.blockSignals(True)
                cat_check.setChecked(is_checked)
                cat_check.blockSignals(False)

    def switch_page(self, index):
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)
        is_setting = (index == 2)
        self.select_all_check.setVisible(not is_setting)
        self.search_bar.setVisible(not is_setting)
        self.creator_filter.setVisible(index == 0)
        self.status_filter.setVisible(index == 0)
        self.batch_btn.setVisible(index == 0)
        self.sync_all_btn.setVisible(index == 1)
        self.refresh_btn.setVisible(not is_setting)
        if not is_setting: self.refresh_ui()

    def force_refresh(self):
        if self.stack.currentIndex() == 0:
            self._cloud_cache = []
        elif self.stack.currentIndex() == 1:
            self._local_cache = []
        self.refresh_ui()

    def refresh_ui(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            if not self._local_cache:
                self.scan_local(silent=True)
            if not self._cloud_cache:
                self.fetch_cloud()
            else:
                self.render_market()
        elif idx == 1:
            if not self._local_cache:
                self.scan_local()
            else:
                self.render_local()

    def fetch_cloud(self):
        if self.active_worker and self.active_worker.isRunning(): return
        self.loading_ring.show()
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
        self.loading_ring.hide()
        self.render_market()

    def scan_local(self, silent=False):
        if not silent: self.loading_ring.show()
        result = self.scanner.get_components()
        self.on_local_loaded(result, silent)

    def on_local_loaded(self, result, silent=False):
        comp_map, _ = result
        self._local_cache = []
        user_name = self.cloud_mgr.config.user_name.value
        now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for p, cls in comp_map.items():
            cid = str(getattr(cls, 'uuid', Path(p).stem))
            res_dir = Path(resource_path("app/component_extensions")) / cid
            self._local_cache.append({
                "组件id": cid,
                "组件名称": getattr(cls, 'name', '未命名'),
                "组件类别": getattr(cls, 'category', '常规'),
                "组件描述": getattr(cls, 'description', ''),
                "工具包需求": getattr(cls, 'requirements', "[]"),
                "版本号": getattr(cls, '_version', '1.0.0'),
                "最后修改人": user_name, "最后修改时间": now_time,
                "创建人": user_name,
                "entry_file": str(getattr(cls, '_source_file', p)),
                "resource_dir": str(res_dir) if res_dir.exists() else ""
            })
        if not silent: self.loading_ring.hide()
        idx = self.stack.currentIndex()
        if idx == 0:
            self.render_market()
        elif idx == 1:
            self.render_local()

    def _get_comparison_status(self, cloud_item):
        if not cloud_item: return "new", False
        cid = str(cloud_item.get('组件id') or cloud_item.get('unique_id'))
        cloud_ver = cloud_item.get('版本号') or cloud_item.get('version')
        local_item = next((i for i in (self._local_cache or []) if str(i.get('组件id')) == cid), None)
        if not local_item: return "new", False
        return ("match", True) if str(cloud_ver) == str(local_item.get('版本号')) else ("diff", True)

    def render_market(self):
        page_widget = self.pages[0].widget()
        layout = page_widget.layout()
        self.clear_layout(layout)
        groups = {}
        for item in (self._cloud_cache or []):
            if not item: continue
            cat = item.get("组件类别") or "常规"
            groups.setdefault(cat, []).append(item)
        for cat, items in groups.items():
            layout.addWidget(self._create_category_view(cat, items, "market", page_widget))
        layout.addStretch()
        self.on_filter_changed()

    def render_local(self):
        page_widget = self.pages[1].widget()
        layout = page_widget.layout()
        self.clear_layout(layout)
        groups = {}
        for item in (self._local_cache or []):
            if not item: continue
            cat = item.get('组件类别') or '常规'
            groups.setdefault(cat, []).append(item)
        for cat, items in groups.items():
            layout.addWidget(self._create_category_view(cat, items, "local", page_widget))
        layout.addStretch()
        self.on_filter_changed()

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
            if not item: continue
            uuid = str(item.get('组件id') or item.get('unique_id'))
            status_code, is_linked = ("new", False)
            if mode == "market":
                status_code, is_linked = self._get_comparison_status(item)
            else:
                is_linked = any(str(c.get('组件id') or c.get('unique_id')) == uuid for c in (self._cloud_cache or []))
            card = ComponentCard(item, mode, is_linked, is_admin, status_code, view)
            card.action_signal.connect(self.on_card_action)
            card.check_changed.connect(lambda v=view: self._update_category_check_state(v))
            if mode == "market": card.delete_signal.connect(self.on_delete_cloud_component)
            grid.addWidget(card, i // 2, i % 2)
            cards.append(card)
        cat_check.stateChanged.connect(lambda st, cs=cards: self._on_category_select_all(st, cs))
        v_lay.addLayout(grid)
        return view

    def _update_category_check_state(self, cat_widget):
        title_lay = cat_widget.layout().itemAt(0).layout()
        cat_check = title_lay.itemAt(0).widget()
        grid = cat_widget.layout().itemAt(1).layout()
        visible_cards = [grid.itemAt(i).widget() for i in range(grid.count())
                         if isinstance(grid.itemAt(i).widget(), ComponentCard) and grid.itemAt(i).widget().isVisible()]
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

    def on_card_action(self, data, mode):
        if mode == "market":
            self.install_component(data)
        else:
            self.upload_component(data)

    def upload_component(self, data):
        self.loading_ring.show()
        self.active_worker = GenericWorker(
            self.cloud_mgr.add_component,
            comp_id=data['组件id'], name=data['组件名称'], category=data['组件类别'],
            description=data['组件描述'], requirements=data['工具包需求'],
            version=data['版本号'], entry_file=data['entry_file'], resource_dir=data['resource_dir']
        )
        self.active_worker.finished.connect(lambda: self.on_single_sync_done(data['组件名称']))
        self.active_worker.error.connect(self.on_worker_error)
        self.active_worker.start()

    def install_component(self, data, silent=False):
        """ 修正后的安装逻辑 """
        if not silent:
            self.loading_ring.show()

        # 获取 UUID
        cid = data.get('组件id') or data.get('unique_id')
        if not cid:
            self.on_error("无法识别组件 ID")
            return

        # 调用上面修正后的精准还原逻辑，传入程序根目录
        self.active_worker = GenericWorker(
            self.cloud_mgr.download_component,
            cid,
            resource_path("")
        )

        def on_install_finished():
            if not silent:
                self.loading_ring.hide()
                InfoBar.success(
                    "安装成功",
                    f"组件 [{data.get('组件名称', '未命名')}] 已还原至本地目录",
                    parent=self
                )
            self.force_refresh()

        self.active_worker.finished.connect(on_install_finished)
        self.active_worker.error.connect(self.on_error)
        self.active_worker.start()

    def on_batch_install(self):
        page = self.pages[0].widget()
        selected = []
        for i in range(page.layout().count()):
            group = page.layout().itemAt(i).widget()
            if not group: continue
            grid_item = group.layout().itemAt(1)
            if grid_item and grid_item.layout():
                grid = grid_item.layout()
                for j in range(grid.count()):
                    card = grid.itemAt(j).widget()
                    if isinstance(card, ComponentCard) and card.check_box.isChecked():
                        selected.append(card.data)
        if not selected:
            InfoBar.warning("提示", "请勾选组件", parent=self)
            return
        for d in selected: self.install_component(d, True)
        InfoBar.success("批量成功", f"正在后台处理 {len(selected)} 个组件", parent=self)

    def on_sync_all(self):
        page = self.pages[1].widget()
        selected_data = []
        for i in range(page.layout().count()):
            group = page.layout().itemAt(i).widget()
            if not group: continue
            grid_item = group.layout().itemAt(1)
            if grid_item and grid_item.layout():
                grid = grid_item.layout()
                for j in range(grid.count()):
                    card = grid.itemAt(j).widget()
                    if isinstance(card, ComponentCard) and card.check_box.isChecked():
                        selected_data.append(card.data)
        sync_target = selected_data if selected_data else self._local_cache
        if not sync_target:
            InfoBar.warning("提示", "无组件可同步", parent=self)
            return
        msg = MessageBox("确认备份同步", f"确认要将选中的组件同步至 Gitee 仓库吗？", self)
        if msg.exec():
            self.loading_ring.show()
            self.active_worker = GenericWorker(self.cloud_mgr.sync_local_to_cloud, sync_target)
            self.active_worker.finished.connect(lambda: [
                self.loading_ring.hide(), self.force_refresh(),
                InfoBar.success("同步完成", "组件已全部处理并上传", parent=self)
            ])
            self.active_worker.error.connect(self.on_error)
            self.active_worker.start()

    def on_delete_cloud_component(self, data):
        cid = data.get('组件id') or data.get('unique_id')
        comp_name = data.get('组件名称') or '未知'
        msg = MessageBox("危险操作", f"确认从 Gitee 云端彻底删除 [{comp_name}] 吗？", self)
        if msg.exec():
            self.loading_ring.show()
            self.active_worker = GenericWorker(self.cloud_mgr.delete_component, cid)
            self.active_worker.finished.connect(lambda: [self.loading_ring.hide(), self.force_refresh(),
                                                         InfoBar.success("已删除", comp_name, parent=self)])
            self.active_worker.error.connect(self.on_error)
            self.active_worker.start()

    def on_filter_changed(self):
        search_text = self.search_bar.text().strip().lower()
        selected_creator = self.creator_filter.currentText()
        status_mode = self.status_filter.currentText()
        idx = self.stack.currentIndex()
        if idx > 1: return
        container = self.pages[idx].widget()
        layout = container.layout()
        if not layout: return
        for i in range(layout.count()):
            cat_widget = layout.itemAt(i).widget()
            if not cat_widget: continue
            cat_layout = cat_widget.layout()
            if not cat_layout or cat_layout.count() < 2: continue
            grid = cat_layout.itemAt(1).layout()
            any_vis = False
            for j in range(grid.count()):
                card = grid.itemAt(j).widget()
                if not isinstance(card, ComponentCard): continue
                match_s = search_text in str(card.data.get('组件名称', '')).lower() or search_text in str(
                    card.data.get('组件id', '')).lower()
                match_c = selected_creator == "所有创建人" or str(card.data.get('创建人')) == selected_creator
                match_st = True
                if idx == 0:
                    if status_mode == "隐藏已安装":
                        match_st = card.status_code != "match"
                    elif status_mode == "仅看更新":
                        match_st = card.status_code == "diff"
                vis = match_s and match_c and match_st
                card.setVisible(vis)
                if vis: any_vis = True
            cat_widget.setVisible(any_vis)
            if any_vis: self._update_category_check_state(cat_widget)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                self.clear_layout(item.layout())

    def on_error(self, msg):
        self.loading_ring.hide()
        InfoBar.error("异常", msg, parent=self)

    def on_worker_error(self, msg):
        self.loading_ring.hide()
        InfoBar.error("操作异常", msg, parent=self)

    def on_single_sync_done(self, name):
        self.loading_ring.hide()
        InfoBar.success("同步成功", f"组件 [{name}] 已推送至 Gitee", parent=self)
        self._cloud_cache = []
        self.force_refresh()