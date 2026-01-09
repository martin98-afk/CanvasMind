# -*- coding: utf-8 -*-
from pathlib import Path

from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
                             QWidget, QStackedWidget, QMessageBox, QGridLayout)
from qfluentwidgets import SearchLineEdit, IndeterminateProgressRing, SmoothScrollArea, CardWidget, \
    PrimaryPushButton, FluentIcon, InfoBar

from app.scan_components import ComponentScanner
from app.server_manager.sheetly.component_cloud_manager import ComponentCloudManager
from app.utils.utils import get_icon
from app.widgets.basic_widget.style_sheet import StyleSheet


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


class ComponentCard(CardWidget):
    """模仿 Dify Tools 样式的卡片"""
    action_signal = pyqtSignal(dict, str)

    def __init__(self, data, mode="market"):
        super().__init__()
        self.setObjectName("ComponentCard")
        self.data = data
        self.mode = mode
        self.setMinimumWidth(340)
        self.setFixedHeight(180)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # 上部分：图标 + 标题信息
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        # 模拟图标 (首字母)
        # icon_text = self.data['name'][0] if self.data['name'] else "?"
        # self.icon_label = QLabel(icon_text.upper())
        # self.icon_label.setFixedSize(44, 44)
        # self.icon_label.setAlignment(Qt.AlignCenter)
        # self.icon_label.setObjectName("CardIcon")
        # top_layout.addWidget(self.icon_label)

        # 标题与ID
        title_v_layout = QVBoxLayout()
        title_v_layout.setSpacing(2)

        name_label = QLabel(self.data['name'])
        name_label.setObjectName("CardTitle")
        title_v_layout.addWidget(name_label)

        uuid_label = QLabel(self.data['uuid'])
        uuid_label.setObjectName("CardUUID")
        title_v_layout.addWidget(uuid_label)

        top_layout.addLayout(title_v_layout)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # 中间部分：描述
        desc_label = QLabel(self.data.get('desc', '暂无描述。'))
        desc_label.setObjectName("CardDesc")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignTop)
        main_layout.addWidget(desc_label, 1)

        # 底部部分：标签 + 按钮
        bottom_layout = QHBoxLayout()

        # 标签 (模仿 Dify 的 Tag)
        tag_container = QHBoxLayout()
        tag_container.setSpacing(6)

        ver_tag = QLabel(f"v{self.data.get('version', '1.0.0')}")
        ver_tag.setObjectName("TagLabel")
        tag_container.addWidget(ver_tag)

        cat_tag = QLabel(self.data.get('category', '常规'))
        cat_tag.setObjectName("TagLabel")
        tag_container.addWidget(cat_tag)

        requirements = self.data.get('requirements', "")
        req_tags = QLabel(requirements)
        req_tags.setObjectName("TagLabel")
        tag_container.addWidget(req_tags)

        bottom_layout.addLayout(tag_container)
        bottom_layout.addStretch()

        # 按钮
        btn_text = "下载" if self.mode == "market" else "上传"
        icon = FluentIcon.DOWNLOAD if self.mode == "market" else get_icon("upload")
        self.action_btn = PrimaryPushButton(icon, btn_text)
        self.action_btn.setObjectName("BtnAction")
        if self.mode == "market":
            self.action_btn.setObjectName("BtnDownload")
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.clicked.connect(lambda: self.action_signal.emit(self.data, self.mode))
        bottom_layout.addWidget(self.action_btn)

        main_layout.addLayout(bottom_layout)


class PluginManagerCenter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MarketCenter")
        StyleSheet.COMPONENT_MARKET.apply(self)

        self.scanner = ComponentScanner()
        self.cloud_mgr = ComponentCloudManager()
        self._cloud_cache = None

        self.init_ui()
        self.switch_page(0)

    def init_ui(self):
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # --- 侧边栏 ---
        sidebar = QWidget()
        sidebar.setObjectName("SideBar")
        sidebar.setFixedWidth(200)
        side_lay = QVBoxLayout(sidebar)

        logo = QLabel("组件市场")
        logo.setStyleSheet("color: #f0f6fc; font-weight: 700; font-size: 18px; margin: 25px 20px;")
        side_lay.addWidget(logo)

        self.nav_btns = []
        for text, idx in [("🛰️ 云端探索", 0), ("🏠 本地工作站", 1)]:
            btn = QPushButton(text)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda ch, i=idx: self.switch_page(i))
            side_lay.addWidget(btn)
            self.nav_btns.append(btn)

        side_lay.addStretch()

        self.sync_all_btn = QPushButton("同步全部组件")
        self.sync_all_btn.setObjectName("BtnAction")
        self.sync_all_btn.setFixedHeight(40)
        self.sync_all_btn.setCursor(Qt.PointingHandCursor)
        self.sync_all_btn.clicked.connect(self.upload_all_logic)
        side_lay.addWidget(self.sync_all_btn)
        side_lay.addSpacing(20)

        main_lay.addWidget(sidebar)

        # --- 内容区 ---
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(30, 20, 30, 0)

        # 顶栏
        top_bar = QHBoxLayout()
        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("搜索组件...")
        self.search_bar.setFixedHeight(36)
        self.search_bar.textChanged.connect(self.filter_cards)
        top_bar.addWidget(self.search_bar)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("BtnAction")
        self.refresh_btn.setFixedHeight(36)
        self.refresh_btn.clicked.connect(self.force_refresh_cloud)
        top_bar.addWidget(self.refresh_btn)

        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(20, 20)
        self.loading_ring.hide()
        top_bar.addWidget(self.loading_ring)
        content_lay.addLayout(top_bar)

        self.stack = QStackedWidget()
        self.pages = [self._create_grid_page() for _ in range(2)]
        for p in self.pages: self.stack.addWidget(p)
        content_lay.addWidget(self.stack)

        main_lay.addWidget(content)

    def _create_grid_page(self):
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        QVBoxLayout(container).setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        return scroll

    def switch_page(self, index):
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)
        self.refresh_ui()

    def refresh_ui(self):
        curr_idx = self.stack.currentIndex()
        if curr_idx == 0:
            if self._cloud_cache is None:
                self.start_cloud_fetch()
            else:
                self.render_market_page(self._cloud_cache)
        else:
            self.render_local_page()

    def start_cloud_fetch(self):
        self.loading_ring.show()
        self.refresh_btn.setEnabled(False)
        self.worker = GenericWorker(self.cloud_mgr.fetch_all)
        self.worker.finished.connect(self.on_cloud_fetch_done)
        self.worker.error.connect(self.on_worker_error)
        self.worker.start()

    def on_cloud_fetch_done(self, data):
        self._cloud_cache = data
        self.loading_ring.hide()
        self.refresh_btn.setEnabled(True)
        self.render_market_page(data)

    def force_refresh_cloud(self):
        self._cloud_cache = None
        self.refresh_ui()

    def render_market_page(self, data):
        layout = self.pages[0].widget().layout()
        self.clear_layout(layout)
        groups = {}
        for item in data:
            cat = item.get("组件类别", "常规")
            groups.setdefault(cat, []).append(item)
        for cat, items in groups.items():
            layout.addWidget(self._create_category_view(cat, items, "market"))
        layout.addStretch()

    def render_local_page(self):
        layout = self.pages[1].widget().layout()
        self.clear_layout(layout)
        comp_map, _ = self.scanner.get_components()
        groups = {}
        for full_path, cls in comp_map.items():
            cat = getattr(cls, 'category', '常规')
            uuid = getattr(cls, 'uuid', Path(full_path).stem)
            source_file = getattr(cls, '_source_file', full_path)
            groups.setdefault(cat, []).append({
                'uuid': uuid,
                'name': getattr(cls, 'name', uuid),
                'category': cat,
                'desc': getattr(cls, 'description', "本地开发的组件。"),
                'requirements': getattr(cls, 'requirements', "无"),
                'version': getattr(cls, '_version', '1.0.0'),
                'real_path': str(source_file)
            })
        for cat, items in groups.items():
            layout.addWidget(self._create_category_view(cat, items, "local"))
        layout.addStretch()

    def _create_category_view(self, name, items, mode):
        view = QWidget()
        v_lay = QVBoxLayout(view)
        v_lay.setContentsMargins(0, 0, 0, 10)

        title = QLabel(name)
        title.setObjectName("CategoryTitle")
        v_lay.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(20)  # 增大间距
        for i, item in enumerate(items):
            c_data = {
                'uuid': item.get('组件id') or item.get('uuid'),
                'name': item.get('组件名称') or item.get('name'),
                'desc': item.get('组件描述') or item.get('desc'),
                'requirements': item.get('工具包需求') or item.get('requirements'),
                'version': item.get('版本号') or item.get('version'),
                'category': name,
                'source': item.get('组件源码'),
                'path': item.get('real_path')
            }
            card = ComponentCard(c_data, mode)
            card.action_signal.connect(self.handle_action)
            grid.addWidget(card, i // 3, i % 3)

        v_lay.addLayout(grid)
        return view

    def handle_action(self, data, mode):
        if mode == "market":
            target_path = Path("app/components") / data['category'] / f"{data['uuid']}.py"
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(data['source'], encoding="utf-8")
                QMessageBox.information(self, "成功", f"组件已安装")
            except Exception as e:
                QMessageBox.critical(self, "错误", str(e))
        else:
            self.loading_ring.show()
            p = Path(data['path'])
            source = p.read_text(encoding="utf-8")
            self.worker = GenericWorker(self.cloud_mgr.add_component, data['uuid'], data['name'], data['category'],
                                        data['desc'], data["requirements"], data['version'], source)
            self.worker.finished.connect(lambda: self.on_single_sync_done(data['name']))
            self.worker.error.connect(self.on_worker_error)
            self.worker.start()

    def on_single_sync_done(self, name):
        self.loading_ring.hide()
        InfoBar.success( "同步成功", f"组件 [{name}] 已推送到云端。")

    def upload_all_logic(self):
        reply = QMessageBox.question(self, '全量同步', '确认同步所有本地组件到云端吗？',
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return
        self.loading_ring.show()
        self.sync_all_btn.setEnabled(False)
        comp_map, _ = self.scanner.get_components()
        local_list = []
        for _, cls in comp_map.items():
            p = Path(getattr(cls, '_source_file'))
            local_list.append({"组件id": cls.uuid, "组件名称": cls.name, "组件类别": cls.category,
                               "组件描述": getattr(cls, 'description', ""),
                               "工具包需求": getattr(cls, 'requirements', ""),
                               "版本号": getattr(cls, '_version', '1.0.0'), "组件源码": p.read_text(encoding="utf-8")})
        self.worker = GenericWorker(self.cloud_mgr.sync_local_to_cloud, local_list)
        self.worker.finished.connect(self.on_all_sync_done)
        self.worker.error.connect(self.on_worker_error)
        self.worker.start()

    def on_all_sync_done(self, res):
        self.loading_ring.hide()
        self.sync_all_btn.setEnabled(True)
        InfoBar.success("完成", "同步结束")

    def on_worker_error(self, msg):
        self.loading_ring.hide()
        self.refresh_btn.setEnabled(True)
        self.sync_all_btn.setEnabled(True)
        InfoBar.error("异常", msg)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def filter_cards(self, text):
        page_idx = self.stack.currentIndex()
        container = self.pages[page_idx].widget()
        for i in range(container.layout().count()):
            group = container.layout().itemAt(i).widget()
            if not group: continue
            grid = group.layout().itemAt(1).layout()
            group_visible = text.lower() in group.layout().itemAt(0).widget().text().lower()
            cards_visible = False
            for j in range(grid.count()):
                card = grid.itemAt(j).widget()
                match = text.lower() in card.data['name'].lower() or text.lower() in card.data['uuid'].lower()
                card.setVisible(match)
                if match: cards_visible = True
            group.setVisible(group_visible or cards_visible)