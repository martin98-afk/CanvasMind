# -*- coding: utf-8 -*-
import importlib
import inspect
import shutil
import sys
from pathlib import Path

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QWidget, QLineEdit, QStackedWidget, \
    QScrollArea, QMessageBox
from qfluentwidgets import SearchLineEdit

from app.components.base import COMPONENT_IMPORT_CODE
from app.scan_components import ComponentScanner
from app.widgets.basic_widget.style_sheet import StyleSheet

# --- 现代极简深色主题 ---
MODERN_DARK = """

"""


class PluginCard(QFrame):
    """组件包卡片项"""
    clicked_action = pyqtSignal(dict, str)

    def __init__(self, data):
        super().__init__()
        self.setObjectName("PluginCard")
        self.data = data
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # 1. 状态指示条
        status_line = QFrame()
        status_line.setFixedWidth(4)
        status_line.setObjectName(f"Status_{self.data['status']}")
        layout.addWidget(status_line)

        # 2. 核心信息
        info_lay = QVBoxLayout()
        info_lay.setSpacing(4)

        title_lay = QHBoxLayout()
        title = QLabel(self.data.get('name', 'Unknown'))
        title.setObjectName("Title")
        title_lay.addWidget(title)

        ver_tag = QLabel(f"v{self.data.get('version', '1.0')}")
        ver_tag.setObjectName("Tag")
        title_lay.addWidget(ver_tag)
        title_lay.addStretch()
        info_lay.addLayout(title_lay)

        desc = QLabel(self.data.get('desc', 'No description provided.'))
        desc.setObjectName("Desc")
        desc.setWordWrap(True)
        info_lay.addWidget(desc)

        path_info = QLabel(f"📍 {self.data.get('rel_path')}")
        path_info.setStyleSheet("color: #484f58; font-size: 11px;")
        info_lay.addWidget(path_info)

        layout.addLayout(info_lay, 5)

        # 3. 操作按钮
        btn_lay = QVBoxLayout()
        btn_lay.setSpacing(8)

        if self.data['status'] != 'market':
            toggle_btn = QPushButton("禁用" if self.data['status'] == 'active' else "启用")
            toggle_btn.setObjectName("BtnAction")
            toggle_btn.clicked.connect(lambda: self.clicked_action.emit(self.data, "toggle"))
            btn_lay.addWidget(toggle_btn)

            del_btn = QPushButton("卸载")
            del_btn.setObjectName("BtnAction")
            del_btn.setProperty("danger", "true")
            del_btn.clicked.connect(lambda: self.clicked_action.emit(self.data, "uninstall"))
            btn_lay.addWidget(del_btn)
        else:
            get_btn = QPushButton("下载并安装")
            get_btn.setObjectName("BtnAction")
            get_btn.setStyleSheet("background-color: #238636; color: white; border: none;")
            btn_lay.addWidget(get_btn)

        layout.addLayout(btn_lay, 1)


class CategoryGroup(QWidget):
    """分类容器"""
    action_bubble = pyqtSignal(dict, str)  # 向上传递卡片信号

    def __init__(self, category_name, items, status):
        super().__init__()
        self.category_name = category_name
        self.items = items
        self.status = status
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 10)
        layout.setSpacing(5)

        # 分类头
        header = QWidget()
        header.setObjectName("CategoryHeader")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(0, 5, 0, 5)

        title = QLabel(self.category_name)
        title.setObjectName("CategoryTitle")
        h_lay.addWidget(title)
        h_lay.addStretch()

        batch_btn = QPushButton("全部禁用" if self.status == 'active' else "全部启用")
        batch_btn.setObjectName("BtnAction")
        batch_btn.clicked.connect(self.on_batch_click)
        h_lay.addWidget(batch_btn)

        layout.addWidget(header)

        # 组件列表
        for item_data in self.items:
            card = PluginCard(item_data)
            # 关键：信号转发，不再使用 parent().parent()
            card.clicked_action.connect(self.action_bubble.emit)
            layout.addWidget(card)

    def on_batch_click(self):
        # 批量操作也模拟单卡片操作发送信号
        for item in self.items:
            self.action_bubble.emit(item, "toggle")


class PluginManagerCenter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MarketCenter")
        self.scanner = ComponentScanner()

        # 物理路径配置 (根据你的逻辑)
        self.ROOTS = {
            'active': Path("app/components"),
            'disabled': Path("app/disabled_components"),
            'deleted': Path("app/deleted_components")
        }

        self.setStyleSheet(MODERN_DARK)
        if hasattr(self.scanner, 'register_on_change'):
            self.scanner.register_on_change(self.refresh_ui)

        self.init_ui()
        self.refresh_ui()

    def init_ui(self):
        StyleSheet.COMPONENT_MARKET.apply(self)
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # 侧边栏
        sidebar = QWidget()
        sidebar.setObjectName("SideBar")
        side_lay = QVBoxLayout(sidebar)

        logo = QLabel("组件市场")
        logo.setStyleSheet("font-weight: 900; font-size: 18px; margin: 25px 15px; color: #f0f6fc;")
        side_lay.addWidget(logo)

        self.nav_btns = []
        nav_config = [("🌐 市场", 0), ("✅ 已启用", 1), ("🚫 已禁用", 2)]
        for text, idx in nav_config:
            btn = QPushButton(text)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda ch, i=idx: self.switch_page(i))
            side_lay.addWidget(btn)
            self.nav_btns.append(btn)

        side_lay.addStretch()
        self.nav_btns[1].setChecked(True)
        main_lay.addWidget(sidebar)

        # 内容区
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)

        self.search_bar = SearchLineEdit()
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText("🔍 搜索组件名称或分类...")
        self.search_bar.textChanged.connect(self.on_search)
        self.search_bar.searchSignal.connect(self.on_search)
        self.search_bar.clearSignal.connect(self.on_search)
        content_lay.addWidget(self.search_bar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")
        self.pages = [self._create_scroll_page() for _ in range(3)]
        for p in self.pages: self.stack.addWidget(p)
        self.stack.setCurrentIndex(1)

        content_lay.addWidget(self.stack)
        main_lay.addWidget(content)

    def _create_scroll_page(self):
        scroll = QScrollArea()
        scroll.setObjectName("ScrollArea")
        scroll.setWidgetResizable(True)
        container = QWidget()
        QVBoxLayout(container).setAlignment(Qt.AlignTop)
        container.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
        return scroll

    def switch_page(self, index):
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)
        self.refresh_ui()

    def refresh_ui(self):
        """刷新当前页面数据"""
        curr_idx = self.stack.currentIndex()
        page_widget = self.pages[curr_idx].widget()
        layout = page_widget.layout()

        # 清理旧组件
        while layout.count():
            w = layout.takeAt(0).widget()
            if w: w.deleteLater()

        # 数据分类处理
        groups = {}
        if curr_idx == 1:  # 已启用
            comp_map, _ = self.scanner.get_components()
            for full_path, cls in comp_map.items():
                cat = getattr(cls, 'category', 'General')
                groups.setdefault(cat, []).append({
                    'name': getattr(cls, 'name', cls.uuid), 'category': cat,
                    'uuid': cls.uuid, 'desc': cls.__doc__ or "No docstring found.",
                    'status': 'active', 'path': cls._source_file, 'rel_path': Path(cat) / cls._source_file.name,
                    'version': getattr(cls, '_version', '1.0.0')
                })
        elif curr_idx == 2:  # 已禁用
            groups = self._scan_physical_dir(self.ROOTS['disabled'])

        # 渲染分类组
        for cat_name, items in groups.items():
            group = CategoryGroup(cat_name, items, 'active' if curr_idx == 1 else 'disabled')
            # 信号连接：Card -> CategoryGroup -> Manager
            group.action_bubble.connect(self.handle_action)
            layout.addWidget(group)

        layout.addStretch()

    def _scan_physical_dir(self, root_path):
        """扫描禁用目录并保持镜像结构"""
        results = {}
        for py_path in root_path.rglob("*.py"):
            if py_path.name in ("__init__.py", "base.py"): continue
            code = py_path.read_text(encoding="utf-8")
            source_lines = code.splitlines(keepends=True)
            start = len(COMPONENT_IMPORT_CODE.split("\n")) - 1
            code = ''.join(source_lines[start:])
            unique_id = f"{hash(code)}_{py_path.stem}"
            module_name = f"dynamic_component_{unique_id}"
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, py_path)
            if spec is None:
                raise RuntimeError("无法创建模块 spec")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            comp_cls = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if getattr(obj, 'category', ""):
                    comp_cls = obj
                    cat = getattr(obj, 'category', 'General')
                    results.setdefault(cat, []).append({
                        'name': comp_cls.name, 'uuid': py_path.stem, 'status': 'disabled', 'category': cat,
                        'path': py_path, 'rel_path': f"{cat}/{py_path.name}", 'version': 'N/A'
                    })
        return results

    def handle_action(self, data, action_type):
        """处理所有组件行为的终点"""
        if action_type == "toggle":
            target = self.ROOTS['disabled'] if data['status'] == 'active' else self.ROOTS['active']
            self._move_physical(data['path'], data, target)
        elif action_type == "uninstall":
            if QMessageBox.question(self, "确认卸载", f"确定要卸载组件 {data['name']} 吗？") == QMessageBox.Yes:
                self._move_physical(data['path'], data, self.ROOTS['deleted'])

    def _move_physical(self, src_path, data, target_root):
        """物理镜像移动核心逻辑"""
        src = Path(src_path)
        dest = target_root / data["category"] / f"{data['uuid']}.py"
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)  # 创建分类目录
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(src), str(dest))
            # 移动后 watchfiles 自动感应，这里如果 scanner 刷新，UI 也会刷新
        except Exception as e:
            QMessageBox.critical(self, "IO Error", f"无法操作文件: {e}")

    def on_search(self, text):
        """搜索增强"""
        page = self.stack.currentWidget().widget()
        for i in range(page.layout().count()):
            group = page.layout().itemAt(i).widget()
            if isinstance(group, CategoryGroup):
                match_cat = text.lower() in group.category_name.lower()
                child_visible = False
                for j in range(group.layout().count()):
                    card = group.layout().itemAt(j).widget()
                    if isinstance(card, PluginCard):
                        match_card = text.lower() in card.data['name'].lower()
                        card.setVisible(match_card or match_cat)
                        if match_card: child_visible = True
                group.setVisible(match_cat or child_visible)