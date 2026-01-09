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


# --- Dify 风格组件卡片 ---
class ComponentCard(CardWidget):
    action_signal = pyqtSignal(dict, str)
    delete_signal = pyqtSignal(dict)  # 新增：删除信号

    def __init__(self, data, mode="market", is_linked=False, is_admin=False, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ComponentCard")
        self.data = data
        self.mode = mode
        self.is_linked = is_linked
        self.is_admin = is_admin  # 记录是否为管理员
        self.setMinimumWidth(350)
        self.setFixedHeight(210)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 第一行：标题 + 复选框
        header = QHBoxLayout()

        # 模拟 MCP 图标 (用一个彩色方块代替)
        icon_lbl = QLabel(self.data.get('组件名称', 'P')[0].upper())
        icon_lbl.setFixedSize(32, 32)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1f6feb, stop:1 #8144ff);
            color: white; border-radius: 6px; font-weight: bold; font-size: 14px;
        """)
        header.addWidget(icon_lbl)

        title_v = QVBoxLayout()
        title_v.setSpacing(0)
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

        # 状态徽章
        if self.is_linked:
            status_txt = "已安装" if self.mode == "market" else "已同步"
            badge = QLabel(status_txt)
            badge.setObjectName("StatusTag")
            header.addWidget(badge)

        self.check_box = CheckBox(self)
        header.addWidget(self.check_box)
        layout.addLayout(header)

        # 第二行：描述 (限制高度以防撑开)
        desc_val = self.data.get('组件描述') or self.data.get('desc') or '暂无描述.'
        desc = QLabel(desc_val)
        desc.setObjectName("CardDesc")
        desc.setWordWrap(True)
        desc.setFixedHeight(40)  # 保持一致性
        desc.setAlignment(Qt.AlignTop)
        layout.addWidget(desc)

        # 第三行：作者与时间 (微缩文字)
        meta = QHBoxLayout()
        creator = self.data.get('创建人', 'unknown')
        m_time = self.data.get('最后修改时间', '---')[:10]  # 只取日期
        meta_lbl = QLabel(f"by {creator} • {m_time}")
        meta_lbl.setStyleSheet("color: white; font-size: 11px;")
        meta.addWidget(meta_lbl)
        meta.addStretch()
        layout.addLayout(meta)

        # 第四行：标签与动作
        footer = QHBoxLayout()
        footer.setSpacing(6)

        # 类别标签
        cat_val = self.data.get('组件类别') or 'General'
        cat_tag = QLabel(cat_val)
        cat_tag.setObjectName("TagLabel")
        footer.addWidget(cat_tag)

        # 版本标签
        ver_val = self.data.get('版本号') or '1.0.0'
        ver_tag = QLabel(f"v{ver_val}")
        ver_tag.setObjectName("TagLabel")
        footer.addWidget(ver_tag)

        footer.addStretch()
        # --- 新增：如果是云端模式且是管理员，增加删除按钮 ---
        if self.mode == "market" and self.is_admin:
            self.delete_btn = ToolButton(FluentIcon.DELETE, self)
            self.delete_btn.setCursor(Qt.PointingHandCursor)
            # 设置红色警告样式
            self.delete_btn.setStyleSheet("""
                        ToolButton { color: #ff4d4f; }
                        ToolButton:hover { background: rgba(255, 77, 79, 0.1); color: #ff7875; }
                    """)
            self.delete_btn.setToolTip("从云端彻底删除")
            self.delete_btn.clicked.connect(lambda: self.delete_signal.emit(self.data))
            footer.addWidget(self.delete_btn)

        btn_text = "安装" if self.mode == "market" else "上传"
        icon = FluentIcon.DOWNLOAD if self.mode == "market" else get_icon("upload")
        self.action_btn = PrimaryPushButton(icon, btn_text)
        if self.is_linked:
            self.action_btn.setEnabled(False)
        if self.mode == "market":
            self.action_btn.setObjectName("BtnDownload")
        self.action_btn.setCursor(Qt.PointingHandCursor)
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
        # 修复：设置按钮关联到第 3 页 (index 2)
        self.config_btn = QPushButton("云存储设置")
        self.config_btn.setObjectName("NavBtn")
        self.config_btn.setCheckable(True)
        self.config_btn.clicked.connect(lambda: self.switch_page(2))
        side_lay.addWidget(self.config_btn)
        self.nav_btns.append(self.config_btn)  # 加入 nav 组实现状态同步

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

        self.select_all_check = CheckBox("全选")
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
        # 添加设置页
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
        """专业设置页面实装"""
        page = SmoothScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 10, 30)
        layout.setSpacing(25)

        # 标题
        title = TitleLabel("服务配置")
        title.setStyleSheet("color: white; margin-bottom: 10px;")
        layout.addWidget(title)

        # Stein 配置组
        stein_card = CardWidget(container)
        stein_lay = QVBoxLayout(stein_card)

        h1 = QHBoxLayout()
        h1.addWidget(SubtitleLabel("Stein 存储配置"))
        h1.addStretch()
        btn_stein_web = PushButton(FluentIcon.LINK, "前往官网")
        btn_stein_web.clicked.connect(lambda: webbrowser.open("https://steinhq.com/"))
        h1.addWidget(btn_stein_web)
        stein_lay.addLayout(h1)

        stein_lay.addWidget(BodyLabel("主用 API 接口地址，支持批量上传与条件修改。"))
        self.stein_url_edit = LineEdit()
        self.stein_url_edit.setText(self.cloud_mgr.config.STEIN_URL.value)
        self.stein_url_edit.setPlaceholderText("请输入 Stein API URL...")
        stein_lay.addWidget(self.stein_url_edit)
        layout.addWidget(stein_card)

        # Sheety 配置组
        sheety_card = CardWidget(container)
        sheety_lay = QVBoxLayout(sheety_card)

        h2 = QHBoxLayout()
        h2.addWidget(SubtitleLabel("Sheety 备份配置"))
        h2.addStretch()
        btn_sheety_web = PushButton(FluentIcon.LINK, "前往官网")
        btn_sheety_web.clicked.connect(lambda: webbrowser.open("https://sheety.co/"))
        h2.addWidget(btn_sheety_web)
        sheety_lay.addLayout(h2)

        sheety_lay.addWidget(BodyLabel("备用 API 接口地址，当 Stein 无法连接时自动切换。"))
        self.sheety_url_edit = LineEdit()
        self.sheety_url_edit.setText(self.cloud_mgr.config.SHEETY_URL.value)
        self.sheety_url_edit.setPlaceholderText("请输入 Sheety API URL...")
        sheety_lay.addWidget(self.sheety_url_edit)
        layout.addWidget(sheety_card)

        # 用户信息显示
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

        # 保存按钮
        save_btn = PrimaryPushButton(FluentIcon.SAVE, "应用并保存配置")
        save_btn.setFixedWidth(200)
        save_btn.clicked.connect(self.on_save_settings)
        layout.addWidget(save_btn, 0, Qt.AlignLeft)

        layout.addStretch()
        page.setWidget(container)
        return page

    def on_save_settings(self):
        """保存配置到管理器并重置适配器"""
        new_stein = self.stein_url_edit.text().strip()
        new_sheety = self.sheety_url_edit.text().strip()

        if not new_stein or not new_sheety:
            InfoBar.warning("格式错误", "API 地址不能为空", parent=self)
            return

        self.cloud_mgr.update_adapter(new_stein, new_sheety)

        InfoBar.success("配置已应用", "云端适配器地址已成功更新", parent=self)

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
                    card.check_box.setChecked(is_checked)

    def switch_page(self, index):
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)

        # UI 状态切换：设置页隐藏工具栏
        is_setting = (index == 2)
        self.select_all_check.setVisible(not is_setting)
        self.search_bar.setVisible(not is_setting)
        self.creator_filter.setVisible(index == 0)
        self.batch_btn.setVisible(index == 0)
        self.sync_all_btn.setVisible(index == 1)
        self.refresh_btn.setVisible(not is_setting)

        if not is_setting:
            self.refresh_ui()

    def force_refresh(self):
        if self.stack.currentIndex() == 0:
            self._cloud_cache = None
        elif self.stack.currentIndex() == 1:
            self._local_cache = None
        self.refresh_ui()

    def refresh_ui(self):
        idx = self.stack.currentIndex()
        if idx == 0:
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
            self._local_cache.append({
                "组件id": str(getattr(cls, 'uuid', Path(p).stem)),
                "组件名称": getattr(cls, 'name', '未命名'),
                "组件类别": getattr(cls, 'category', '常规'),
                "组件描述": getattr(cls, 'description', ''),
                "工具包需求": getattr(cls, 'requirements', "无需求"),
                "版本号": getattr(cls, '_version', '1.0.0'),
                "最后修改人": user_name, "最后修改时间": now_time,
                "创建人": user_name, "组件源码": getattr(cls, '_source_code', ''),
                "path": str(getattr(cls, '_source_file', p))
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
        is_admin = (user_name == "martin98-afk")
        for i, item in enumerate(items):
            uuid = str(item.get('组件id') or item.get('uuid'))
            is_linked = uuid in linked_set
            c_data = {
                "组件id": uuid, "组件名称": item.get('组件名称') or item.get('name'),
                "组件类别": name, "组件描述": item.get('组件描述') or item.get('desc') or "暂无组件描述。",
                "工具包需求": item.get('工具包需求') or item.get('requirements') or "无需求",
                "最后修改人": user_name, "最后修改时间": item.get('最后修改时间', now_str),
                "创建人": item.get('创建人', user_name), "创建时间": item.get('创建时间', now_str),
                "版本号": item.get('版本号') or item.get('version'),
                "组件源码": item.get('组件源码') or item.get("source_code"),
                "path": item.get('path') or item.get('real_path')
            }
            card = ComponentCard(c_data, mode, is_linked, is_admin=is_admin, parent=view)
            card.action_signal.connect(self.on_card_action)

            # 连接删除信号
            if mode == "market":
                card.delete_signal.connect(self.on_delete_cloud_component)
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
            InfoBar.warning("提示", "请勾选组件", parent=self)
            return
        for d in selected: self.install_component(d, True)
        InfoBar.success("批量成功", f"安装 {len(selected)} 个组件", parent=self)
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
            InfoBar.warning("提示", "无组件可同步", parent=self)
            return
        msg = MessageBox("确认备份同步", f"确认要同步 {mode_desc} 到云端库吗？", self)
        if msg.exec():
            self.loading_ring.show()
            self.active_worker = GenericWorker(self.cloud_mgr.sync_local_to_cloud, sync_target)
            self.active_worker.finished.connect(lambda: [self.loading_ring.hide(), self.force_refresh(),
                                                         InfoBar.success("同步完成", f"{mode_desc} 已同步",
                                                                         parent=self)])
            self.active_worker.error.connect(self.on_error)
            self.active_worker.start()

    def on_error(self, msg):
        self.loading_ring.hide()
        InfoBar.error("异常", msg, parent=self)

    def on_delete_cloud_component(self, data):
        """处理云端组件删除"""
        comp_name = data.get('组件名称', '未知组件')
        comp_id = data.get('组件id')

        # 1. 弹出强提醒确认框
        title = "危险操作"
        content = f"确认要从云端数据库彻底删除组件 [{comp_name}] 吗？\n该操作无法撤销，所有用户将无法再看到此组件。"
        msg = MessageBox(title, content, self)
        msg.yesButton.setText("确定删除")
        msg.cancelButton.setText("取消")

        if msg.exec():
            self.loading_ring.show()
            # 2. 调用管理器 delete_component
            self.active_worker = GenericWorker(self.cloud_mgr.delete_component, comp_id)

            # 3. 连接成功后的回调
            def on_done(success):
                self.loading_ring.hide()
                if success:
                    InfoBar.success("删除成功", f"组件 {comp_name} 已从云端移除", parent=self)
                    self.force_refresh()  # 刷新 UI 缓存
                else:
                    InfoBar.error("删除失败", "服务器拒绝了请求，请检查网络或权限", parent=self)

            self.active_worker.finished.connect(on_done)
            self.active_worker.error.connect(self.on_error)
            self.active_worker.start()

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
        if current_page_idx > 1: return
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