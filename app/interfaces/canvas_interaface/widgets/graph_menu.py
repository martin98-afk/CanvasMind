# -- coding: utf-8 --
import json
from datetime import datetime
from pathlib import Path

import orjson
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import TransparentToolButton, FluentIcon

from app.components.base import ArgumentType
from app.interfaces.canvas_interaface.widgets.preview_manager import PreviewManager
from app.scan_components import ComponentScanner
from app.utils.utils import get_pinyin_search_keys, get_icon
from app.widgets.basic_widget.category_filter import CategoryFilterDialog
from app.widgets.basic_widget.style_sheet import StyleSheet


class MenuMode:
    CREATE = 0  # 节点库
    NAVIGATE = 2  # 画布节点
    TEMPLATE = 1  # 模板库


# --- 胶囊筛选小部件 (保持不变) ---
class FilterCapsule(QtWidgets.QFrame):
    closed = pyqtSignal()

    def __init__(self, text, color="#007ACC", parent=None):
        super().__init__(parent)
        self.setObjectName("FilterCapsule")
        self.setFixedHeight(26)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)
        self.label = QtWidgets.QLabel(text)
        self.label.setStyleSheet(
            "color: white; font-size: 11px; font-weight: bold; border: none;"
        )
        self.close_btn = QtWidgets.QPushButton("×")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton { color: rgba(255, 255, 255, 0.8); background: transparent; border: none; font-size: 14px; font-weight: bold; margin-bottom: 1px; }
            QPushButton:hover { color: white; background: rgba(255,255,255,0.2); border-radius: 8px; }
        """)
        self.close_btn.clicked.connect(self.closed.emit)
        layout.addWidget(self.label)
        layout.addWidget(self.close_btn)
        self.setStyleSheet(
            f"#FilterCapsule {{ background-color: {color}; border-radius: 13px; border: 1px solid rgba(255, 255, 255, 0.1); }}"
        )


class NodeItemDelegate(QtWidgets.QStyledItemDelegate):
    # 预定义的深色调调色板（克制、专业、不刺眼）
    CATEGORY_COLORS = [
        "#2D4A3E",  # 森林绿
        "#3E4A5E",  # 钢青蓝
        "#5E4A3E",  # 粘土褐
        "#4A3E5E",  # 灰紫
        "#3E5E5E",  # 深青墨
        "#5E5E3E",  # 橄榄金
        "#424242",  # 深灰
        "#2D5A5A",  # 瓦松蓝
    ]

    def get_color_for_category(self, category):
        if not category or category == "未分类":
            return QtGui.QColor("#424242")
        # 通过哈希确保同一个类别永远是同一个颜色
        hash_val = sum(ord(c) for c in category)
        color_hex = self.CATEGORY_COLORS[hash_val % len(self.CATEGORY_COLORS)]
        return QtGui.QColor(color_hex)

    def paint(self, painter, option, index):
        data = index.data(Qt.UserRole)
        if not data or data.get("_is_placeholder", False):
            return

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        display_text = index.data(Qt.DisplayRole)
        category = data.get("category", "")
        item_type = data.get("type", "")

        is_selected = option.state & QtWidgets.QStyle.State_Selected
        is_hovered = option.state & QtWidgets.QStyle.State_MouseOver

        # --- 1. 背景绘制 ---
        if is_selected:
            bg_color = QtGui.QColor("#007ACC")
            text_color = QtGui.QColor("#FFFFFF")
        elif is_hovered:
            bg_color = QtGui.QColor(255, 255, 255, 20)
            text_color = QtGui.QColor("#FFFFFF")
        else:
            bg_color = QtGui.QColor("transparent")
            text_color = QtGui.QColor("#CCCCCC")

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        rect = option.rect.adjusted(4, 2, -4, -2)
        painter.drawRoundedRect(rect, 8, 8)

        # --- 2. 左侧指示条 (针对不同模式) ---
        if is_selected and item_type != "node":
            indicator_color = (
                QtGui.QColor("#4EC9B0")
                if item_type == "instance"
                else QtGui.QColor("#CE9178")
            )
            painter.setBrush(indicator_color)
            painter.drawRoundedRect(
                rect.left(), rect.top() + 10, 3, rect.height() - 20, 1, 1
            )

        # --- 3. 绘制标题文字 ---
        font = painter.font()
        font.setPointSize(10)
        font.setBold(is_selected)
        painter.setFont(font)
        painter.setPen(text_color)
        title_rect = option.rect.adjusted(18, 0, -160, 0)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, display_text)

        # --- 4. 绘制右侧类别标签 (一类一色) ---
        if category:
            cat_color = self.get_color_for_category(category)

            # 动态计算标签宽度
            font.setPointSize(8)
            font.setBold(False)
            painter.setFont(font)
            metrics = QtGui.QFontMetrics(font)
            text_w = metrics.width(category)
            text_h = metrics.height()

            # 标签外框位置 (右对齐)
            padding_h = 8
            padding_v = 3
            tag_w = text_w + padding_h * 2
            tag_h = text_h + padding_v * 2
            tag_rect = QtCore.QRect(
                option.rect.right() - tag_w - 15,
                option.rect.top() + (option.rect.height() - tag_h) // 2,
                tag_w,
                tag_h,
            )

            # 绘制标签背景 (如果是选中状态，颜色调淡一点避免冲突)
            if is_selected:
                painter.setBrush(QtGui.QColor(255, 255, 255, 40))  # 选中时用半透明白
            else:
                painter.setBrush(cat_color)

            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(tag_rect, 4, 4)

            # 绘制标签文字
            if is_selected:
                painter.setPen(QtGui.QColor("#FFFFFF"))
            else:
                # 文字颜色：如果背景太深，用浅灰色
                painter.setPen(QtGui.QColor("#EEEEEE"))

            painter.drawText(tag_rect, Qt.AlignCenter, category)

        painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(0, 44)


class CustomGraphMenu(QtWidgets.QWidget):
    source_port_item = None

    def __init__(self, graph, left_panel, parent):
        super(CustomGraphMenu, self).__init__(parent)
        self._graph = graph
        self._left_panel = left_panel
        self.parent = parent
        self._cached_data = []
        self._selected_component_categories = set()
        self._selected_template_categories = set()
        self._current_mode = MenuMode.CREATE
        self._is_upward_mode = False
        self._spawn_pos = QtCore.QPoint(0, 0)
        self._spawn_pos_scene = None
        self._spawn_pos_set = False
        self._visible_items = []
        self._ignore_connection_filter = False
        self._usage_stats_file = Path("./canvas_files/nodegraph_usage.json")
        self._favorites_file = Path("./canvas_files/nodegraph_favorites.json")
        self._usage_stats = self._load_usage_stats()
        self._favorites = set(self._load_favorites())

        self._template_dir = Path("canvas_files") / "subgraph_templates"

        # --- 状态锁定变量 ---
        self._locked_target_dir = None
        self._locked_req_type = None
        self._locked_req_sub_type = None  # 【新增】锁定子类型

        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)

        self.container = QtWidgets.QFrame()
        self.container.setObjectName("SearchContainer")
        self.container.setStyleSheet(
            "#SearchContainer { background: #252526; border: 1px solid #454545; border-radius: 12px; }"
        )

        self.shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(25)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(8)
        self.shadow.setColor(QtGui.QColor(0, 0, 0, 180))
        self.container.setGraphicsEffect(self.shadow)

        self.container_layout = QtWidgets.QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(6, 6, 6, 6)
        self.container_layout.setSpacing(4)

        self.header_widget = QtWidgets.QWidget()
        self.header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(4)

        self.mode_button = TransparentToolButton(get_icon("节点库"), self)
        self.mode_button.setFixedSize(35, 35)
        self.mode_button.clicked.connect(self.toggle_mode)
        self.mode_button.setToolTip(self.tr("切换模式 (Tab)"))

        self.filter_button = TransparentToolButton(FluentIcon.FILTER, self)
        self.filter_button.setFixedSize(35, 35)
        self.filter_button.clicked.connect(self.show_category_filter)

        self.capsule_container = QtWidgets.QWidget()
        self.capsule_layout = QtWidgets.QHBoxLayout(self.capsule_container)
        self.capsule_layout.setContentsMargins(0, 0, 0, 0)
        self.capsule_layout.setSpacing(4)

        self.search_line = QtWidgets.QLineEdit()
        self.search_line.setPlaceholderText(self.tr("🔍 搜索库节点..."))
        self.search_line.setStyleSheet("""
            QLineEdit { background: #323233; color: #FFFFFF; border: 1px solid #3C3C3C; border-radius: 6px; padding: 8px 12px; font-size: 13px; }
            QLineEdit:focus { border: 1px solid #007ACC; background: #3c3c3c; }
        """)

        self.header_layout.addWidget(self.mode_button)
        self.header_layout.addWidget(self.filter_button)
        self.header_layout.addWidget(self.capsule_container)
        self.header_layout.addWidget(self.search_line, 1)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setItemDelegate(NodeItemDelegate())
        self.list_widget.setMouseTracking(True)
        self.list_widget.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollPerPixel
        )
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        StyleSheet.QLIST.apply(self.list_widget)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet(
            "color: #8A8A8A; font-size: 11px; padding: 2px 8px 4px 8px;"
        )

        self.container_layout.addWidget(self.header_widget)
        self.container_layout.addWidget(self.list_widget)
        self.container_layout.addWidget(self.status_label)
        self.main_layout.addWidget(self.container)

        self.search_line.textChanged.connect(self.filter_list)
        self.list_widget.itemClicked.connect(self.on_item_confirmed)
        self.list_widget.itemActivated.connect(self.on_item_confirmed)
        self.search_line.returnPressed.connect(self.on_return_pressed)
        self.search_line.installEventFilter(self)
        self.list_widget.installEventFilter(self)
        self.list_widget.viewport().installEventFilter(self)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self.setFixedSize(460, 480)

    def _load_usage_stats(self):
        if self._usage_stats_file.exists():
            try:
                with open(self._usage_stats_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_usage_stats(self):
        try:
            self._usage_stats_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._usage_stats_file, "w", encoding="utf-8") as f:
                json.dump(self._usage_stats, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_favorites(self):
        if self._favorites_file.exists():
            try:
                with open(self._favorites_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _record_usage(self, full_path):
        if not full_path:
            return
        timestamps = self._usage_stats.setdefault(full_path, [])
        timestamps.append(datetime.now().isoformat())
        self._usage_stats[full_path] = timestamps[-20:]
        self._save_usage_stats()

    def _get_usage_count(self, full_path):
        return len(self._usage_stats.get(full_path, []))

    def _get_last_used_dt(self, full_path):
        timestamps = self._usage_stats.get(full_path, [])
        if not timestamps:
            return None
        try:
            return datetime.fromisoformat(timestamps[-1])
        except (TypeError, ValueError):
            return None

    def _score_item(self, data, search_text):
        score = 0
        if data.get("_is_empty"):
            return score

        name = data.get("name", "").lower()
        category = data.get("category", "").lower()
        full_path = data.get("full_path", "")
        search_keys = data.get("search_keys", "")

        if search_text:
            if name == search_text:
                score += 1200
            elif name.startswith(search_text):
                score += 900
            elif search_text in name:
                score += 650
            elif category.startswith(search_text):
                score += 480
            elif search_text in category:
                score += 320
            elif full_path.lower().startswith(search_text):
                score += 260
            elif search_text in search_keys:
                score += 150
        else:
            score += 50

        if self._current_mode == MenuMode.CREATE and full_path:
            if full_path in self._favorites:
                score += 300

            usage_count = self._get_usage_count(full_path)
            score += min(usage_count, 20) * 12

            last_used = self._get_last_used_dt(full_path)
            if last_used:
                days = max((datetime.now() - last_used).days, 0)
                if days == 0:
                    score += 180
                elif days <= 3:
                    score += 120
                elif days <= 7:
                    score += 80
                elif days <= 30:
                    score += 40

        return score

    def _get_active_category_filter(self):
        if self._current_mode == MenuMode.TEMPLATE:
            return self._selected_template_categories
        return self._selected_component_categories

    def _set_active_category_filter(self, categories):
        categories = set(categories)
        if self._current_mode == MenuMode.TEMPLATE:
            self._selected_template_categories = categories
        else:
            self._selected_component_categories = categories

    def toggle_mode(self):
        self._current_mode = (self._current_mode + 1) % 3

        if self._current_mode == MenuMode.CREATE:
            self.search_line.setPlaceholderText(self.tr("🔍 搜索库节点..."))
            self.filter_button.setEnabled(True)
            self.mode_button.setIcon(get_icon("节点库"))
            self._update_filter_capsule()
        elif self._current_mode == MenuMode.NAVIGATE:
            self.search_line.setPlaceholderText(self.tr("📍 定位当前图中节点..."))
            self.filter_button.setEnabled(False)
            self.mode_button.setIcon(get_icon("location"))
            self.capsule_container.hide()
        elif self._current_mode == MenuMode.TEMPLATE:
            self.search_line.setPlaceholderText(self.tr("🎨 搜索子图模板..."))
            self.filter_button.setEnabled(True)
            self.mode_button.setIcon(FluentIcon.TILES)
            self.capsule_container.hide()

        self.update_cache()
        self.populate_ui()
        self.search_line.setText("")
        self.search_line.setFocus()

    def _update_filter_capsule(self):
        # 清空旧的胶囊
        while self.capsule_layout.count():
            item = self.capsule_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 如果没有处于连线模式，或者是完全忽略过滤的状态，则隐藏容器
        if self._current_mode != MenuMode.CREATE or self._ignore_connection_filter:
            self.capsule_container.hide()
            return

        has_capsule = False

        # 1. 主类型胶囊 (例如: IMAGE)
        if self._locked_req_type:
            capsule = FilterCapsule(f"{self._locked_req_type.upper()}", color="#007ACC")
            # 【关键修改】关闭主类型胶囊 -> 清除所有过滤并停止自动连线
            capsule.closed.connect(self._clear_all_filters)
            self.capsule_layout.addWidget(capsule)
            has_capsule = True

        # 2. 子类型胶囊 (例如: MASK)
        if self._locked_req_sub_type:
            sub_capsule = FilterCapsule(f"{self._locked_req_sub_type}", color="#2D8C5A")
            # 【关键修改】关闭子类型胶囊 -> 只清除子类型条件，保留自动连线
            sub_capsule.closed.connect(self._clear_sub_type_filter)
            self.capsule_layout.addWidget(sub_capsule)
            has_capsule = True

        if has_capsule:
            self.capsule_container.show()
        else:
            self.capsule_container.hide()

    def _clear_sub_type_filter(self):
        """新增：只清除子类型过滤，但保持连线意图"""
        self._locked_req_sub_type = None  # 清空子类型锁定
        # 注意：这里不要设置 _ignore_connection_filter = True
        # 这样 on_item_confirmed 里依然会尝试通过 _locked_req_type 进行连线

        self._update_filter_capsule()  # 刷新胶囊显示（去掉子类型胶囊）
        self.filter_list(
            self.search_line.text()
        )  # 刷新列表（显示更多主类型匹配的节点）

    def _clear_all_filters(self):
        """原 _clear_extra_filter：清除所有过滤，放弃自动连线"""
        self._ignore_connection_filter = True
        self._locked_req_sub_type = None  # 顺便清理状态
        self.capsule_container.hide()
        self.filter_list(self.search_line.text())

    def _clear_extra_filter(self):
        self._ignore_connection_filter = True
        self.capsule_container.hide()
        self.filter_list(self.search_line.text())

    # ... (update_cache 系列函数保持不变，假设 _update_create_cache 已经正确填充了 cachedata) ...
    def update_cache(self):
        if self._current_mode == MenuMode.CREATE:
            self._update_create_cache()
        elif self._current_mode == MenuMode.NAVIGATE:
            self._update_navigate_cache()
        elif self._current_mode == MenuMode.TEMPLATE:
            self._update_template_cache()

    def _update_navigate_cache(self):
        self._cached_data = []
        for node in self._graph.all_nodes():
            name = node.name()
            node_type = "/".join(getattr(node, "FULL_PATH", "Node").split("/")[:-1])
            py_keys = get_pinyin_search_keys(name)
            self._cached_data.append(
                {
                    "type": "instance",
                    "node_ptr": node,
                    "name": name,
                    "category": node_type,
                    "search_keys": f"{name} {node_type} {py_keys}".lower(),
                }
            )

    def _update_create_cache(self):
        self._cached_data = []
        scanner = ComponentScanner()
        component_map, _ = scanner.get_components()
        node_factory_nodes = self._graph._node_factory.nodes
        node_type_map = self._graph.parent().node_type_map

        for full_path, comp in component_map.items():
            node_type = node_type_map.get(full_path)
            if not node_type:
                continue

            node_class = node_factory_nodes.get(node_type)
            if not node_class:
                continue

            node_name = getattr(comp, "name", full_path.split("/")[-1])
            category = "/".join(full_path.split("/")[:-1])
            py_keys = get_pinyin_search_keys(node_name)
            node_inputs = comp.get_inputs()
            node_outputs = comp.get_outputs()

            self._cached_data.append(
                {
                    "type": "node",
                    "id": node_type,
                    "name": node_name,
                    "category": category,
                    "full_path": full_path,
                    "search_keys": f"{node_name} {category} {full_path} {py_keys}".lower(),
                    "in_port_count": len(node_inputs),
                    "out_port_count": len(node_outputs),
                    "input_ports_raw": node_inputs,
                    "output_ports_raw": node_outputs,
                    "in_port_types": [
                        port_type for _, _, _, port_type, _ in node_inputs
                    ],
                    "out_port_types": [
                        port_type for _, _, port_type, _ in node_outputs
                    ],
                    "in_port_sub_types": comp.get_input_sub_types(),
                    "out_port_sub_types": comp.get_output_sub_types(),
                }
            )

    def _update_template_cache(self):
        self._cached_data = []
        if not self._template_dir.exists():
            return

        for tid_dir in self._template_dir.iterdir():
            if not tid_dir.is_dir():
                continue
            meta_file = tid_dir / "meta.json"
            preview_file = tid_dir / "preview.png"

            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = orjson.loads(f.read())

                    name = meta.get("name", tid_dir.name)
                    tags = meta.get("tags", [])

                    # --- 优化点 1: 格式化标签显示 ---
                    # 将标签转为 #Tag1 #Tag2 的格式显示在右侧
                    display_tags = (
                        " ".join([f"#{t}" for t in tags]) if tags else "未分类"
                    )

                    tag_str = " ".join(tags)
                    py_keys = get_pinyin_search_keys(name)

                    self._cached_data.append(
                        {
                            "type": "template",
                            "id": meta.get("id", tid_dir.name),
                            "name": name,
                            "category": display_tags,
                            "tags": tags,  # 保留原始列表用于过滤
                            "preview_path": str(preview_file)
                            if preview_file.exists()
                            else None,
                            "search_keys": f"{name} {tag_str} {py_keys}".lower(),
                        }
                    )
                except Exception:
                    continue

    def populate_ui(self):
        self.filter_list(self.search_line.text())

    def _get_max_visible_items(self):
        return 8

    def _update_list_widget(self):
        self.list_widget.clear()
        items_to_show = self._visible_items
        is_upward = self._is_upward_mode

        if is_upward:
            max_items = self._get_max_visible_items()
            actual_count = len(items_to_show)
            if actual_count < max_items:
                for _ in range(max_items - actual_count):
                    placeholder = QtWidgets.QListWidgetItem()
                    placeholder.setData(Qt.UserRole, {"_is_placeholder": True})
                    self.list_widget.addItem(placeholder)

        for data in items_to_show:
            item = QtWidgets.QListWidgetItem(data["name"])
            item.setData(Qt.UserRole, data)
            if data.get("_is_empty"):
                item.setFlags(Qt.NoItemFlags)
                item.setForeground(QtGui.QColor("#8A8A8A"))
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0 and not items_to_show[0].get("_is_empty"):
            first_real_index = (
                max(0, self.list_widget.count() - len(items_to_show))
                if is_upward
                else 0
            )
            self.list_widget.setCurrentRow(first_real_index)

    def _update_status_label(self, search_text):
        count = len(
            [item for item in self._visible_items if not item.get("_is_empty", False)]
        )
        if self._current_mode == MenuMode.CREATE:
            mode_text = self.tr("创建节点")
        elif self._current_mode == MenuMode.NAVIGATE:
            mode_text = self.tr("定位节点")
        else:
            mode_text = self.tr("插入模板")

        if search_text:
            self.status_label.setText(
                self.tr("{}  ·  {} 个结果  ·  Enter确认 / Tab切模式 / Esc关闭").format(
                    mode_text, count
                )
            )
        else:
            self.status_label.setText(
                self.tr("{}  ·  {} 个结果  ·  已优先显示收藏与最近使用").format(
                    mode_text, count
                )
            )

    def filter_list(self, text):
        search_text = text.lower().strip()
        self._visible_items = []

        target_dir = None if self._ignore_connection_filter else self._locked_target_dir
        req_type = self._locked_req_type
        req_sub_type = self._locked_req_sub_type
        curr_mode = self._current_mode
        sel_cats = self._get_active_category_filter()
        ignore_types = [ArgumentType.UPLOAD, ArgumentType.FILE]

        for data in self._cached_data:
            # 模式特定的前置过滤
            if curr_mode == MenuMode.TEMPLATE:
                # 如果开启了标签过滤
                if sel_cats:
                    item_tags = set(data.get("tags", []))
                    # 如果当前模板的标签与选中的标签没有交集，则跳过
                    if not (sel_cats & item_tags):
                        continue
            if curr_mode == MenuMode.CREATE:
                if sel_cats and data["category"].split("/")[0] not in sel_cats:
                    continue
                if target_dir:
                    if target_dir == "in":
                        # 如果需要连到输入端
                        if data["in_port_count"] == 0:
                            continue

                        # 1. 检查主类型
                        if (
                            req_type
                            and req_type not in data["in_port_types"]
                            and req_type not in ignore_types
                        ):
                            continue

                        # 2. 【新增】检查子类型
                        if req_sub_type and req_sub_type not in data.get(
                            "in_port_sub_types", []
                        ):
                            continue

                    else:
                        # 如果需要连到输出端
                        if data["out_port_count"] == 0:
                            continue

                        # 1. 检查主类型
                        if (
                            req_type
                            and req_type not in data["out_port_types"]
                            and req_type not in ignore_types
                        ):
                            continue

                        # 2. 【新增】检查子类型
                        if req_sub_type and req_sub_type not in data.get(
                            "out_port_sub_types", []
                        ):
                            continue

            # 搜索文本过滤
            if search_text in data["search_keys"]:
                self._visible_items.append(data)

        self._visible_items.sort(
            key=lambda item: (
                -self._score_item(item, search_text),
                item.get("name", "").lower(),
            )
        )

        if not self._visible_items:
            empty_text = (
                self.tr("没有匹配结果，试试更短的关键词")
                if search_text
                else self.tr("当前没有可用项目")
            )
            self._visible_items = [
                {
                    "_is_empty": True,
                    "name": empty_text,
                    "category": "",
                    "type": "empty",
                    "search_keys": "",
                }
            ]

        self._update_list_widget()
        self._update_status_label(search_text)
        if self.list_widget.count() > 0 and not self._visible_items[0].get("_is_empty"):
            self.list_widget.setCurrentRow(0)
        else:
            self._hide_preview()

    def on_item_confirmed(self, item):
        data = item.data(Qt.UserRole)
        if not data or data.get("_is_placeholder"):
            return

        viewer = self._graph.viewer()
        scene_viewer = (
            viewer.get_scene_viewer() if hasattr(viewer, "get_scene_viewer") else viewer
        )
        spawn_pos_scene = getattr(self, "_spawn_pos_scene", None)
        if spawn_pos_scene is not None:
            scene_pos = spawn_pos_scene
        else:
            scene_pos = scene_viewer.mapToScene(self._spawn_pos)

        if self._current_mode == MenuMode.CREATE:
            self._graph.begin_undo("Create Node")
            new_node = self._graph.create_node(
                data["id"], pos=[scene_pos.x(), scene_pos.y()]
            )
            self._record_usage(data.get("full_path"))

            if self.source_port_item and hasattr(
                self.source_port_item, "original_node"
            ):
                source_node = self.source_port_item.original_node
                req_type = self._locked_req_type
                req_sub_type = self._locked_req_sub_type  # 获取需要的子类型

                if not self._ignore_connection_filter:
                    if self.source_port_item.port_type == "out":
                        # 已有节点(出) -> 新节点(入)
                        source_ports = source_node.output_ports()
                        source_port = next(
                            (
                                p
                                for p in source_ports
                                if p.name() == self.source_port_item.name
                            ),
                            None,
                        )

                        if source_port:
                            # 逻辑：如果有子类型，优先找匹配子类型的第一个端口；否则按主类型找；否则找第0个
                            target_idx = 0

                            # 【新增】子类型优先匹配
                            if req_sub_type:
                                try:
                                    target_idx = data["in_port_sub_types"].index(
                                        req_sub_type
                                    )
                                except (ValueError, KeyError, IndexError):
                                    # 如果找不到子类型匹配，回退到主类型匹配
                                    try:
                                        target_idx = data["in_port_types"].index(
                                            req_type
                                        )
                                    except (ValueError, KeyError):
                                        target_idx = 0
                            else:
                                # 原有逻辑
                                try:
                                    target_idx = data["in_port_types"].index(req_type)
                                except (ValueError, KeyError):
                                    target_idx = 0

                            QTimer.singleShot(
                                0, lambda: new_node.set_input(target_idx, source_port)
                            )

                    else:
                        # 新节点(出) -> 已有节点(入)
                        input_ports = source_node.input_ports()
                        try:
                            port_index = [p.name() for p in input_ports].index(
                                self.source_port_item.name
                            )

                            target_out_idx = 0
                            # 子类型优先匹配
                            if req_sub_type:
                                try:
                                    target_out_idx = data["out_port_sub_types"].index(
                                        req_sub_type
                                    )
                                except (ValueError, KeyError, IndexError):
                                    try:
                                        target_out_idx = data["out_port_types"].index(
                                            req_type
                                        )
                                    except (ValueError, KeyError):
                                        target_out_idx = 0
                            else:
                                try:
                                    target_out_idx = data["out_port_types"].index(
                                        req_type
                                    )
                                except (ValueError, KeyError):
                                    target_out_idx = 0

                            QTimer.singleShot(
                                0,
                                lambda: source_node.set_input(
                                    port_index, new_node.output_ports()[target_out_idx]
                                ),
                            )
                        except ValueError:
                            pass

                self.source_port_item = None

            self.parent.on_selection_changed()
            self._graph.end_undo()

        elif self._current_mode == MenuMode.TEMPLATE:
            self.parent.ui_manager.nav_panel.template_container.apply_template(
                data["id"], scene_pos
            )

        else:  # NAVIGATE 模式
            node = data.get("node_ptr")
            if node:
                self._graph.clear_selection()
                node.set_selected(True)
                self._graph.fit_to_selection()

        self.close()

    def show_at_cursor(self, pos):
        self._ignore_connection_filter = False
        # 【修改】这里同时获取子类型
        self._locked_target_dir, self._locked_req_type, self._locked_req_sub_type = (
            self._get_connection_filter()
        )

        if self._locked_target_dir:
            self._current_mode = MenuMode.CREATE
            self.mode_button.setIcon(get_icon("节点库"))
            self.filter_button.setEnabled(True)

        self.update_cache()
        self._update_filter_capsule()

        screen_rect = QtWidgets.QApplication.desktop().availableGeometry(pos)
        menu_width, menu_height = self.width(), self.height()
        target_x, target_y = pos.x() - 20, pos.y() + 10

        if target_y - menu_height < screen_rect.top():
            self._is_upward_mode = False
        else:
            self._is_upward_mode = True
            target_y = pos.y() - menu_height - 10

        target_x = max(
            screen_rect.left(), min(target_x, screen_rect.right() - menu_width)
        )

        self.populate_ui()
        viewer = self._graph.viewer()
        scene_viewer = (
            viewer.get_scene_viewer() if hasattr(viewer, "get_scene_viewer") else viewer
        )
        spawn_pos_set = getattr(self, "_spawn_pos_set", False)
        if not spawn_pos_set:
            self._spawn_pos = scene_viewer.mapFromGlobal(pos)
        self._spawn_pos_set = False
        self.search_line.setText("")
        self.filter_list("")

        self.container_layout.removeWidget(self.header_widget)
        self.container_layout.removeWidget(self.list_widget)
        if self._is_upward_mode:
            self.container_layout.addWidget(self.list_widget)
            self.container_layout.addWidget(self.header_widget)
        else:
            self.container_layout.addWidget(self.header_widget)
            self.container_layout.addWidget(self.list_widget)

        self.move(target_x, target_y)
        self.show()
        self.search_line.setFocus()

    def on_return_pressed(self):
        current_item = self.list_widget.currentItem()
        if current_item and not current_item.isHidden():
            self.on_item_confirmed(current_item)

    def show_category_filter(self):
        if self._current_mode == MenuMode.CREATE:
            pos = self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft())
            # 这里需要连接信号
            dialog = CategoryFilterDialog(
                parent=self,
                selected_categories=self._get_active_category_filter().copy(),
                direction="down",
            )
            dialog.categories_changed.connect(self.set_category_filter)
            dialog.show_at(pos)

        elif self._current_mode == MenuMode.TEMPLATE:
            # 获取所有可用标签
            all_tags = self._left_panel.template_container._get_all_tags()
            if not all_tags:
                return

            # 创建一个临时的过滤对话框
            dialog = CategoryFilterDialog(
                categories=all_tags,
                parent=self,
                selected_categories=self._get_active_category_filter().copy(),
                direction="down",
            )

            # --- 关键：当标签改变时，更新菜单的过滤状态 ---
            dialog.categories_changed.connect(self.set_category_filter)

            pos = self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft())
            dialog.show_at(pos)

    def set_category_filter(self, categories):
        """更新过滤条件并重刷列表"""
        self._set_active_category_filter(categories)
        self.filter_list(self.search_line.text())

    def _get_connection_filter(self):
        """
        获取拖拽连线的上下文信息
        返回: (连接方向: 'in'/'out', 主类型, 子类型)
        """
        viewer = self._graph.viewer()
        self.source_port_item = getattr(viewer, "_temp_connection_source", None)
        if not self.source_port_item or not hasattr(
            self.source_port_item, "original_node"
        ):
            return None, None, None  # 【修改】返回三个None

        source_node = self.source_port_item.original_node
        if not hasattr(source_node, "uuid"):
            return None, None, None
        node_uuid = source_node.uuid
        port_name = self.source_port_item.name
        scanner = ComponentScanner()
        comp = scanner.get_component_by_uuid(node_uuid)

        if self.source_port_item.port_type == "out":
            node_outputs = comp.get_outputs()
            # 【新增】获取子类型列表
            node_sub_types = comp.get_output_sub_types()
            # 使用 enumerate 以便通过索引获取 sub_type
            for i, (pname, _, port_type, _) in enumerate(node_outputs):
                if pname == port_name:
                    # 安全获取子类型
                    sub_type = node_sub_types[i] if i < len(node_sub_types) else None
                    return "in", port_type, sub_type
        else:
            node_inputs = comp.get_inputs()
            # 【新增】获取子类型列表
            node_sub_types = comp.get_input_sub_types()

            for i, (pname, _, _, port_type, _) in enumerate(node_inputs):
                if pname == port_name:
                    sub_type = node_sub_types[i] if i < len(node_sub_types) else None
                    return "out", port_type, sub_type

        return None, None, None

    def focusOutEvent(self, event):
        """阻止因预览卡片显示导致的自动关闭"""
        # 检查新获得焦点的窗口是否是预览卡片
        active_window = QApplication.activeWindow()
        preview_card = PreviewManager.get_instance()._card

        if active_window and preview_card and preview_card.isAncestorOf(active_window):
            # 预览卡片获得焦点 → 忽略
            event.ignore()
            return

        # 其他情况：正常处理（如点击画布等）
        super().focusOutEvent(event)

    def eventFilter(self, obj, event):
        # 修复：只保留一个 eventFilter，处理所有事件
        if obj == self.list_widget.viewport():
            if event.type() == QtCore.QEvent.MouseMove:
                self._handle_preview_on_mouse_move(event.pos())
                return False

            elif event.type() == QtCore.QEvent.Leave:
                self._hide_preview()
                return False

            elif event.type() == QtCore.QEvent.Wheel:
                self._hide_preview()
                return False

        elif obj == self.search_line and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == Qt.Key_Tab:
                self.toggle_mode()
                return True
            if event.key() == Qt.Key_Escape:
                self.close()
                return True
            if event.key() in (Qt.Key_Down, Qt.Key_Up):
                if self.list_widget.count() > 0:
                    current_row = self.list_widget.currentRow()
                    if current_row < 0:
                        current_row = 0
                    step = 1 if event.key() == Qt.Key_Down else -1
                    next_row = max(
                        0, min(self.list_widget.count() - 1, current_row + step)
                    )
                    self.list_widget.setCurrentRow(next_row)
                self.list_widget.setFocus()
                return True

        elif obj == self.list_widget and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == Qt.Key_Tab:
                self.toggle_mode()
                return True
            if event.key() == Qt.Key_Escape:
                self.close()
                return True
            if event.key() == Qt.Key_Slash:
                self.search_line.setFocus()
                self.search_line.selectAll()
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.on_return_pressed()
                return True

        return super(CustomGraphMenu, self).eventFilter(obj, event)

    def _on_current_item_changed(self, current, previous):
        # 【核心修复】如果菜单还没显示（例如正在后台构建列表），直接忽略，防止预览乱飘
        if not self.isVisible():
            return

        if current:
            # 键盘操作响应快一点
            self._show_preview_for_item(current, delay=50)
        else:
            self._hide_preview()

    def _handle_preview_on_mouse_move(self, pos):
        """处理鼠标悬浮预览"""
        if not self.isVisible():
            return

        item = self.list_widget.itemAt(pos)
        # 鼠标悬浮时延迟稍长（200ms），避免划过时闪烁
        self._show_preview_for_item(item, delay=200)

    def _show_preview_for_item(self, item, delay=200):
        """通用的显示预览方法，基于 Item 的位置而不是鼠标位置"""
        if not item:
            self._hide_preview()
            return

        # 【核心修改】允许 CREATE (节点) 和 TEMPLATE (模板) 模式显示预览
        # NAVIGATE 模式通常不需要预览
        if self._current_mode == MenuMode.NAVIGATE:
            self._hide_preview()
            return

        data = item.data(Qt.UserRole)
        if not data or data.get("_is_placeholder"):
            self._hide_preview()
            return

        # 构造数据
        preview_data = self._build_preview_data(data)
        # 如果没有数据（比如模板没有图片，或者节点解析失败），则不显示
        if not preview_data:
            self._hide_preview()
            return

        # === 基于 Item 的几何位置计算预览位置 ===
        screen_geo = QApplication.primaryScreen().availableGeometry()
        item_rect = self.list_widget.visualItemRect(item)
        global_item_pos = self.list_widget.viewport().mapToGlobal(item_rect.topLeft())

        item_width = item_rect.width()

        # 默认显示在左侧
        preview_width = 350  # 如果是图片，管理器会自动调整宽度，这里只是估算位移
        preview_x = global_item_pos.x() - preview_width - 10

        if preview_x < screen_geo.left() + 10:
            preview_x = global_item_pos.x() + item_width + 10
            if preview_x + preview_width > screen_geo.right() - 10:
                preview_x = screen_geo.left() + 10

        preview_y = global_item_pos.y()
        estimated_h = 250
        if preview_y + estimated_h > screen_geo.bottom():
            preview_y = screen_geo.bottom() - estimated_h - 10
        if preview_y < screen_geo.top():
            preview_y = screen_geo.top() + 10

        preview_pos = QPoint(int(preview_x), int(preview_y))

        PreviewManager.get_instance().show_preview(
            preview_data, preview_pos, self, delay=delay
        )

    def _build_preview_data(self, data):
        """构建预览所需数据（区分节点和模板）"""
        try:
            # 1. 如果是模板类型
            if data.get("type") == "template":
                # 如果没有图片路径，返回 None，这样就不会弹出预览窗
                if not data.get("preview_path"):
                    return None

                # 返回符合 ImagePreviewCard 要求的数据结构
                return {
                    "name": data.get("name"),
                    "image_path": data.get("preview_path"),
                }

            # 2. 如果是节点类型 (CREATE 模式)
            elif data.get("type") == "node":
                return {
                    "name": data["name"],
                    "category": data["category"],
                    "description": self._get_node_description(data["id"]),
                    "inputs": data["input_ports_raw"],
                    "outputs": data["output_ports_raw"],
                    "input_sub_types": data.get("in_port_sub_types", []),
                    "output_sub_types": data.get("out_port_sub_types", []),
                }

            return None
        except Exception:
            return None

    def _get_node_description(self, node_id):
        """从组件扫描器获取节点描述（缓存优化）"""
        try:
            scanner = ComponentScanner()
            node_factory = self._graph._node_factory.nodes
            node_class = node_factory.get(node_id)
            if not node_class:
                return ""

            node_uuid = node_class.__name__.split("StatusDynamicNode_")[1]
            comp = scanner.get_component_by_uuid(node_uuid)
            return getattr(comp, "description", "No description available.")[:200]
        except Exception:
            return "No description available."

    def _hide_preview(self):
        """统一隐藏预览的入口"""
        PreviewManager.get_instance().hide_preview()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._hide_preview()  # 确保菜单关闭时预览也隐藏

    def closeEvent(self, event):
        super().closeEvent(event)
        self._hide_preview()
