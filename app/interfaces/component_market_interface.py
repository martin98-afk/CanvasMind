# -*- coding: utf-8 -*-
import json
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QWidget,
                             QStackedWidget, QGridLayout, QCheckBox, QPushButton)
from qfluentwidgets import (SearchLineEdit, IndeterminateProgressRing, SmoothScrollArea,
                            CardWidget, PrimaryPushButton, FluentIcon, InfoBar,
                            PushButton, ComboBox, CaptionLabel, TransparentPushButton, MessageBox, ToolButton, CheckBox)

from app.scan_components import ComponentScanner
from app.server_manager.cloud_bakup.component_cloud_manager import ComponentCloudManager
from app.utils.utils import get_icon
from app.widgets.basic_widget.style_sheet import StyleSheet


# --- 异步工作线程 ---
class GenericWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# --- Dify 风格组件卡片 (同步标准化键名显示) ---
class ComponentCard(CardWidget):
    action_signal = pyqtSignal(dict, str)

    def __init__(self, data, mode="market", is_linked=False, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ComponentCard")
        self.data = data
        self.mode = mode
        self.is_linked = is_linked
        self.setMinimumWidth(350)
        self.setFixedHeight(210)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)
        # 同步：读取标准化键名
        name_val = self.data.get('组件名称') or self.data.get('name', '未命名')
        name_lbl = QLabel(name_val)
        name_lbl.setObjectName("CardTitle")
        title_v.addWidget(name_lbl)

        uuid_val = self.data.get('组件id') or self.data.get('uuid', '---')
        uuid_lbl = QLabel(str(uuid_val))
        uuid_lbl.setObjectName("CardUUID")
        title_v.addWidget(uuid_lbl)
        header.addLayout(title_v)
        header.addStretch()

        if self.is_linked:
            status_txt = "已安装" if self.mode == "market" else "已同步"
            badge = QLabel(status_txt)
            badge.setObjectName("TagLabel")
            header.addWidget(badge)

        self.check_box = CheckBox(self)
        header.addWidget(self.check_box)
        layout.addLayout(header)

        desc_val = self.data.get('组件描述') or self.data.get('desc') or '暂无组件描述。'
        desc = QLabel(desc_val)
        desc.setObjectName("CardDesc")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignTop)
        layout.addWidget(desc, 1)

        # 仅在云端市场模式下显示元数据
        if self.mode == "market":
            meta = QHBoxLayout()
            creator = QLabel(f"👤 {self.data.get('创建人', '未知')}")
            creator.setStyleSheet("color: white; font-size: 11px;")
            meta.addWidget(creator)
            meta.addStretch()
            m_time = QLabel(f"🕒 {self.data.get('最后修改时间', '未知')}")
            m_time.setStyleSheet("color: white; font-size: 11px;")
            meta.addWidget(m_time)
            layout.addLayout(meta)

        footer = QHBoxLayout()
        ver_val = self.data.get('版本号') or self.data.get('version', '1.0.0')
        ver_tag = QLabel(f"v{ver_val}")
        ver_tag.setObjectName("TagLabel")
        footer.addWidget(ver_tag)

        cat_val = self.data.get('组件类别') or self.data.get('category') or '常规'
        cat_tag = QLabel(cat_val)
        cat_tag.setObjectName("TagLabel")
        footer.addWidget(cat_tag)

        # 同步：处理 requirements 渲染
        reqs = self.data.get('工具包需求') or self.data.get('requirements') or '无需求'
        if isinstance(reqs, list):
            reqs = ",".join(map(str, reqs)) if reqs else "无需求"
        req_tag = QLabel(str(reqs))
        req_tag.setObjectName("TagLabel")
        footer.addWidget(req_tag)

        footer.addStretch()

        btn_text = "保存" if self.mode == "market" else "上传"
        self.action_btn = PushButton(btn_text)
        self.action_btn.setObjectName("BtnAction")
        if self.mode == "market":
            self.action_btn.setObjectName("BtnDownload")
        self.action_btn.clicked.connect(lambda: self.action_signal.emit(self.data, self.mode))
        footer.addWidget(self.action_btn)

        layout.addLayout(footer)


# --- 主界面 ---
class PluginManagerCenter(QWidget):
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
        self.config_btn = TransparentPushButton(FluentIcon.SETTING, "设置")
        side_lay.addWidget(self.config_btn)
        side_lay.addSpacing(20)
        main_lay.addWidget(sidebar)

        # 内容区
        content_panel = QWidget()
        content_lay = QVBoxLayout(content_panel)
        content_lay.setContentsMargins(30, 20, 30, 0)

        toolbar = QHBoxLayout()

        # 全选功能
        self.select_all_check = CheckBox("全选")
        self.select_all_check.stateChanged.connect(self.on_select_all_changed)
        toolbar.addWidget(self.select_all_check)

        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("检索组件...")
        self.search_bar.textChanged.connect(self.on_filter_changed)
        toolbar.addWidget(self.search_bar, 1)

        self.creator_filter = ComboBox()
        self.creator_filter.setFixedWidth(130)
        self.creator_filter.currentIndexChanged.connect(self.on_filter_changed)
        toolbar.addWidget(self.creator_filter)

        self.batch_btn = PushButton(FluentIcon.DOWNLOAD, "批量安装")
        self.batch_btn.clicked.connect(self.on_batch_install)
        toolbar.addWidget(self.batch_btn)

        self.sync_all_btn = PrimaryPushButton(get_icon("upload"), "备份同步")
        self.sync_all_btn.clicked.connect(self.on_sync_all)
        toolbar.addWidget(self.sync_all_btn)

        self.refresh_btn = ToolButton(FluentIcon.SYNC, "")
        self.refresh_btn.setFixedWidth(40)
        self.refresh_btn.clicked.connect(self.force_refresh)
        toolbar.addWidget(self.refresh_btn)

        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(20, 20)
        self.loading_ring.hide()
        toolbar.addWidget(self.loading_ring)
        content_lay.addLayout(toolbar)

        self.stack = QStackedWidget()
        self.pages = [self._create_scroll_page() for _ in range(2)]
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

    def on_select_all_changed(self, state):
        is_checked = (state == Qt.Checked)
        container = self.pages[self.stack.currentIndex()].widget()
        for i in range(container.layout().count()):
            cat_widget = container.layout().itemAt(i).widget()
            if not cat_widget or not cat_widget.isVisible(): continue
            grid = cat_widget.layout().itemAt(1).layout()
            for j in range(grid.count()):
                card = grid.itemAt(j).widget()
                if isinstance(card, ComponentCard) and card.isVisible():
                    card.check_box.setChecked(is_checked)

    def switch_page(self, index):
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)
        self.creator_filter.setVisible(index == 0)
        self.batch_btn.setVisible(index == 0)
        self.sync_all_btn.setVisible(index == 1)
        self.select_all_check.setChecked(False)
        self.refresh_ui()

    def force_refresh(self):
        if self.stack.currentIndex() == 0:
            self._cloud_cache = None
        else:
            self._local_cache = None
        self.refresh_ui()

    def refresh_ui(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            if not self._cloud_cache:
                self.fetch_cloud()
            else:
                self.render_market()
        else:
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
        creators = sorted(list(set([str(i.get('创建人', '未知')) for i in self._cloud_cache])))
        self.creator_filter.clear()
        self.creator_filter.addItems(["所有创建人"] + creators)
        self.loading_ring.hide()
        self.render_market()

    def scan_local(self):
        if self.active_worker and self.active_worker.isRunning(): return
        self.loading_ring.show()
        self.active_worker = GenericWorker(self.scanner.get_components)
        self.active_worker.finished.connect(self.on_local_loaded)
        self.active_worker.error.connect(self.on_error)
        self.active_worker.start()

    def on_local_loaded(self, result):
        comp_map, _ = result
        self._local_cache = []
        user_name = self.cloud_mgr.config.user_name.value
        now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for p, cls in comp_map.items():
            # 同步：将本地扫描结果包装成标准化字典
            self._local_cache.append({
                "组件id": str(getattr(cls, 'uuid', Path(p).stem)),
                "组件名称": getattr(cls, 'name', '未命名'),
                "组件类别": getattr(cls, 'category', '常规'),
                "组件描述": getattr(cls, 'description', ''),
                "工具包需求": getattr(cls, 'requirements', "无需求"),
                "版本号": getattr(cls, '_version', '1.0.0'),
                "最后修改人": user_name,
                "最后修改时间": now_time,
                "创建人": user_name,
                "组件源码": getattr(cls, '_source_code', ''),
                "path": str(getattr(cls, '_source_file', p))  # 仅本地有
            })
        self.loading_ring.hide()
        self.render_local()

    def render_market(self):
        page_widget = self.pages[0].widget()
        layout = page_widget.layout()
        self.clear_layout(layout)
        local_uuids = {str(i['组件id']) for i in self._local_cache} if self._local_cache else set()
        groups = {}
        for item in self._cloud_cache:
            cat = item.get("组件类别", "常规")
            groups.setdefault(cat, []).append(item)
        for cat, items in groups.items():
            layout.addWidget(self._create_category_view(cat, items, "market", local_uuids, page_widget))
        layout.addStretch()

    def render_local(self):
        page_widget = self.pages[1].widget()
        layout = page_widget.layout()
        self.clear_layout(layout)
        cloud_uuids = {str(i.get('组件id')) for i in self._cloud_cache} if self._cloud_cache else set()
        groups = {}
        for item in self._local_cache:
            cat = item.get('组件类别', '常规')
            groups.setdefault(cat, []).append(item)
        for cat, items in groups.items():
            layout.addWidget(self._create_category_view(cat, items, "local", cloud_uuids, page_widget))
        layout.addStretch()

    def _create_category_view(self, name, items, mode, linked_set, parent_container):
        view = QWidget(parent_container)
        v_lay = QVBoxLayout(view)
        title = QLabel(name)
        title.setObjectName("CategoryTitle")
        v_lay.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(15)

        user_name = self.cloud_mgr.config.user_name.value
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for i, item in enumerate(items):
            uuid = str(item.get('组件id') or item.get('uuid'))
            is_linked = uuid in linked_set
            # 同步：标准化数据传输字典，包含新旧键名兼容
            c_data = {
                "组件id": uuid,
                "组件名称": item.get('组件名称') or item.get('name'),
                "组件类别": name,
                "组件描述": item.get('组件描述') or item.get('desc') or "暂无组件描述。",
                "工具包需求": item.get('工具包需求') or item.get('requirements') or "无需求",
                "最后修改人": user_name,
                "最后修改时间": item.get('最后修改时间', now_str),
                "创建人": item.get('创建人', user_name),
                "创建时间": item.get('创建时间', now_str),
                "版本号": item.get('版本号') or item.get('version'),
                "组件源码": item.get('组件源码') or item.get("source_code"),
                "path": item.get('path') or item.get('real_path')
            }
            card = ComponentCard(c_data, mode, is_linked, parent=view)
            card.action_signal.connect(self.on_card_action)
            grid.addWidget(card, i // 2, i % 2)
        v_lay.addLayout(grid)
        return view

    def on_card_action(self, data, mode):
        if mode == "market":
            self.install_component(data)
        else:
            self.upload_component(data)

    def upload_component(self, data):
        self.loading_ring.show()
        try:
            p = Path(data['path'])
            source = p.read_text(encoding="utf-8")
            # 同步：调用云端管理器的 add_component，使用标准化键名
            self.active_worker = GenericWorker(
                self.cloud_mgr.add_component,
                data['组件id'], data['组件名称'], data['组件类别'],
                data['组件描述'], data["工具包需求"], data['版本号'], source
            )
            self.active_worker.finished.connect(lambda: self.on_single_sync_done(data['组件名称']))
            self.active_worker.error.connect(self.on_worker_error)
            self.active_worker.start()
        except Exception as e:
            self.on_worker_error(str(e))

    def on_single_sync_done(self, name):
        self.loading_ring.hide()
        InfoBar.success("同步成功", f"组件 [{name}] 已推送到云端", parent=self)
        self._cloud_cache = None

    def on_worker_error(self, msg):
        self.loading_ring.hide()
        InfoBar.error("同步异常", msg, parent=self)

    def install_component(self, data, silent=False):
        source = data.get('组件源码')
        if not source: return
        target = Path("app/components") / data['组件类别'] / f"{data['组件id']}.py"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
            if not silent: InfoBar.success("安装成功", f"{data['组件名称']} 就绪", parent=self)
            self._local_cache = None
        except Exception as e:
            if not silent: InfoBar.error("安装失败", str(e), parent=self)

    def on_batch_install(self):
        page = self.pages[0].widget()
        selected = []
        for i in range(page.layout().count()):
            group = page.layout().itemAt(i).widget()
            if not group: continue
            layout_item = group.layout().itemAt(1)
            if layout_item and layout_item.layout():
                grid = layout_item.layout()
                for j in range(grid.count()):
                    card = grid.itemAt(j).widget()
                    if isinstance(card, ComponentCard) and card.check_box.isChecked():
                        selected.append(card.data)
        if not selected:
            InfoBar.warning("提示", "请勾选需要安装的组件", parent=self)
            return
        for d in selected: self.install_component(d, True)
        InfoBar.success("批量成功", f"成功安装 {len(selected)} 个组件", parent=self)
        self.force_refresh()

    def on_sync_all(self):
        page = self.pages[1].widget()
        selected_data = []
        for i in range(page.layout().count()):
            group = page.layout().itemAt(i).widget()
            if not group: continue
            layout_item = group.layout().itemAt(1)
            if layout_item and layout_item.layout():
                grid = layout_item.layout()
                for j in range(grid.count()):
                    card = grid.itemAt(j).widget()
                    if isinstance(card, ComponentCard) and card.check_box.isChecked():
                        selected_data.append(card.data)

        sync_target = selected_data if selected_data else self._local_cache
        mode_desc = f"选中的 {len(selected_data)} 个组件" if selected_data else "全部本地组件"

        if not sync_target:
            InfoBar.warning("提示", "本地没有可同步的组件", parent=self)
            return

        msg = MessageBox("确认备份同步", f"确认要同步 {mode_desc} 到云端库吗？", self)
        if msg.exec():
            self.loading_ring.show()
            self.active_worker = GenericWorker(self.cloud_mgr.sync_local_to_cloud, sync_target)
            self.active_worker.finished.connect(lambda: [self.loading_ring.hide(), self.force_refresh(),
                                                         InfoBar.success("同步完成", f"{mode_desc} 已更新",
                                                                         parent=self)])
            self.active_worker.error.connect(self.on_error)
            self.active_worker.start()

    def on_error(self, msg):
        self.loading_ring.hide()
        InfoBar.error("异常", msg, parent=self)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                self.clear_layout(item.layout())

    def on_filter_changed(self):
        search_text = self.search_bar.text().strip().lower()
        selected_creator = self.creator_filter.currentText()
        current_page_idx = self.stack.currentIndex()
        container = self.pages[current_page_idx].widget()
        layout = container.layout()
        if not layout: return
        for i in range(layout.count()):
            cat_widget = layout.itemAt(i).widget()
            if not cat_widget: continue
            cat_layout = cat_widget.layout()
            if not cat_layout or cat_layout.count() < 2: continue
            grid = cat_layout.itemAt(1).layout()
            category_any_visible = False
            for j in range(grid.count()):
                card = grid.itemAt(j).widget()
                if not isinstance(card, ComponentCard): continue
                # 同步：检索标准化键名
                name = str(card.data.get('组件名称', '')).lower()
                cid = str(card.data.get('组件id', '')).lower()
                match_search = (search_text in name or search_text in cid)

                match_creator = True
                if current_page_idx == 0 and selected_creator != "所有创建人":
                    match_creator = (str(card.data.get('创建人')) == selected_creator)

                is_card_visible = match_search and match_creator
                card.setVisible(is_card_visible)
                if is_card_visible: category_any_visible = True
            cat_widget.setVisible(category_any_visible)