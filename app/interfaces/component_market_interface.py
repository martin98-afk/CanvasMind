# -*- coding: utf-8 -*-
from pathlib import Path
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
                             QWidget, QStackedWidget, QScrollArea, QMessageBox, QGridLayout)
from qfluentwidgets import SearchLineEdit, IndeterminateProgressRing

from app.scan_components import ComponentScanner
from app.server_manager.sheetly.component_cloud_manager import ComponentCloudManager
from app.widgets.basic_widget.style_sheet import StyleSheet


class GenericWorker(QThread):
    """通用后台任务执行器，防止阻塞主进程"""
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


class ComponentCard(QFrame):
    """带明显边界的高科技组件卡片"""
    action_signal = pyqtSignal(dict, str)

    def __init__(self, data, mode="market"):
        super().__init__()
        self.setObjectName("ComponentCard")
        self.data = data
        self.mode = mode
        self.setFixedSize(310, 195)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        # UUID
        uuid_label = QLabel(f"ID: {self.data['uuid']}")
        uuid_label.setObjectName("CardUUID")
        layout.addWidget(uuid_label)

        # 名称
        title = QLabel(self.data['name'])
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        # 描述
        desc = QLabel(self.data.get('desc', '暂无描述。'))
        desc.setObjectName("CardDesc")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignTop)
        layout.addWidget(desc, 1)

        # 底部栏
        footer = QHBoxLayout()
        ver = QLabel(f"v{self.data.get('version', '1.0.0')}")
        ver.setStyleSheet("color: #484f58; font-size: 11px;")
        footer.addWidget(ver)
        footer.addStretch()

        btn_text = "下载组件" if self.mode == "market" else "上传同步"
        self.action_btn = QPushButton(btn_text)
        self.action_btn.setObjectName("BtnAction")
        if self.mode == "market":
            self.action_btn.setObjectName("BtnDownload")
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.clicked.connect(lambda: self.action_signal.emit(self.data, self.mode))
        footer.addWidget(self.action_btn)

        layout.addLayout(footer)


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
        sidebar.setFixedWidth(180)
        side_lay = QVBoxLayout(sidebar)

        logo = QLabel("组件控制中心")
        logo.setStyleSheet("color: #58a6ff; font-weight: 900; font-size: 20px; margin: 25px 15px;")
        side_lay.addWidget(logo)

        self.nav_btns = []
        for text, idx in [("🌐 云端市场", 0), ("📦 本地库", 1)]:
            btn = QPushButton(text)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda ch, i=idx: self.switch_page(i))
            side_lay.addWidget(btn)
            self.nav_btns.append(btn)

        side_lay.addStretch()

        self.sync_all_btn = QPushButton("🚀 全量同步")
        self.sync_all_btn.setObjectName("BtnAction")
        self.sync_all_btn.setFixedHeight(40)
        self.sync_all_btn.clicked.connect(self.upload_all_logic)
        side_lay.addWidget(self.sync_all_btn)
        side_lay.addSpacing(20)

        main_lay.addWidget(sidebar)

        # --- 内容区 ---
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(25, 20, 25, 0)

        # 工具栏
        top_bar = QHBoxLayout()
        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("根据ID或名称检索...")
        self.search_bar.textChanged.connect(self.filter_cards)
        top_bar.addWidget(self.search_bar)

        self.refresh_btn = QPushButton("刷新数据")
        self.refresh_btn.setObjectName("BtnAction")
        self.refresh_btn.clicked.connect(self.force_refresh_cloud)
        top_bar.addWidget(self.refresh_btn)

        # 加载环 (高科技感)
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
        scroll = QScrollArea()
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
        """异步获取云端数据"""
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
        v_lay.setContentsMargins(0, 0, 0, 0)

        title = QLabel(f"📁 {name}")
        title.setObjectName("CategoryTitle")
        v_lay.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(15)
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
        """组件操作逻辑：下载或上传"""
        if mode == "market":
            # 下载逻辑：本地 IO 不耗时，直接主线程处理
            target_path = Path("app/components") / data['category'] / f"{data['uuid']}.py"
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(data['source'], encoding="utf-8")
                QMessageBox.information(self, "成功", f"组件已部署至：\n{target_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", str(e))
        else:
            # 上传逻辑：涉及网络请求，开启异步
            self.loading_ring.show()
            p = Path(data['path'])
            source = p.read_text(encoding="utf-8")

            # 开启异步同步
            self.worker = GenericWorker(
                self.cloud_mgr.add_component,
                data['uuid'], data['name'], data['category'],
                data['desc'], data["requirements"], data['version'], source
            )
            self.worker.finished.connect(lambda: self.on_single_sync_done(data['name']))
            self.worker.error.connect(self.on_worker_error)
            self.worker.start()

    def on_single_sync_done(self, name):
        self.loading_ring.hide()
        QMessageBox.information(self, "同步成功", f"组件 [{name}] 已推送到云端。")

    def upload_all_logic(self):
        """异步全量同步"""
        reply = QMessageBox.question(self, '全量同步', '确定同步所有本地组件到云端吗？',
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return

        self.loading_ring.show()
        self.sync_all_btn.setEnabled(False)

        comp_map, _ = self.scanner.get_components()
        local_list = []
        for _, cls in comp_map.items():
            p = Path(getattr(cls, '_source_file'))
            local_list.append({
                "组件id": cls.uuid, "组件名称": cls.name, "组件类别": cls.category,
                "组件描述": getattr(cls, 'description', ""), "工具包需求": getattr(cls, 'requirements', ""),
                "版本号": getattr(cls, '_version', '1.0.0'), "组件源码": p.read_text(encoding="utf-8")
            })

        # 批量同步逻辑
        self.worker = GenericWorker(self.cloud_mgr.sync_local_to_cloud, local_list)
        self.worker.finished.connect(self.on_all_sync_done)
        self.worker.error.connect(self.on_worker_error)
        self.worker.start()

    def on_all_sync_done(self, res):
        self.loading_ring.hide()
        self.sync_all_btn.setEnabled(True)
        QMessageBox.information(self, "完成", "所有本地组件同步尝试已结束。")

    def on_worker_error(self, msg):
        self.loading_ring.hide()
        self.refresh_btn.setEnabled(True)
        self.sync_all_btn.setEnabled(True)
        QMessageBox.critical(self, "网络异常", f"云端操作失败：\n{msg}")

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def filter_cards(self, text):
        """实时过滤搜索"""
        page_idx = self.stack.currentIndex()
        container = self.pages[page_idx].widget()
        for i in range(container.layout().count()):
            group = container.layout().itemAt(i).widget()
            if not group: continue

            # 搜索类别和卡片
            grid = group.layout().itemAt(1).layout()
            group_visible = text.lower() in group.layout().itemAt(0).widget().text().lower()

            cards_visible = False
            for j in range(grid.count()):
                card = grid.itemAt(j).widget()
                match = text.lower() in card.data['name'].lower() or text.lower() in card.data['uuid'].lower()
                card.setVisible(match)
                if match: cards_visible = True

            group.setVisible(group_visible or cards_visible)