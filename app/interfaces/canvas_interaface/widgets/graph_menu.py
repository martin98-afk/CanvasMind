# -- coding: utf-8 --
from pathlib import Path

import orjson
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from qfluentwidgets import TransparentToolButton, FluentIcon

from app.components.base import ArgumentType
from app.scan_components import ComponentScanner
from app.utils.utils import get_pinyin_search_keys, get_icon
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
        self.label.setStyleSheet("color: white; font-size: 11px; font-weight: bold; border: none;")
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
            f"#FilterCapsule {{ background-color: {color}; border-radius: 13px; border: 1px solid rgba(255, 255, 255, 0.1); }}")


class NodeItemDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        data = index.data(Qt.UserRole)
        if not data or data.get("_is_placeholder", False):
            return

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        display_text = index.data(Qt.DisplayRole)
        category = data.get("category", "")
        item_type = data.get("type", "")  # 'node', 'instance', 'template'

        is_selected = option.state & QtWidgets.QStyle.State_Selected
        is_hovered = option.state & QtWidgets.QStyle.State_MouseOver

        # 颜色配置
        if is_selected:
            bg_color = QtGui.QColor("#007ACC")
            text_color = QtGui.QColor("#FFFFFF")
            sub_text_color = QtGui.QColor("#A0CFFF")
        elif is_hovered:
            bg_color = QtGui.QColor(255, 255, 255, 20)
            text_color = QtGui.QColor("#FFFFFF")
            sub_text_color = QtGui.QColor("#999999")
        else:
            bg_color = QtGui.QColor("transparent")
            text_color = QtGui.QColor("#CCCCCC")
            sub_text_color = QtGui.QColor("#666666")

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        rect = option.rect.adjusted(4, 2, -4, -2)
        painter.drawRoundedRect(rect, 8, 8)

        # 侧边指示条
        if is_selected:
            indicator_color = QtGui.QColor("#4EC9B0") if item_type == "instance" else QtGui.QColor(
                "#CE9178") if item_type == "template" else QtGui.QColor("#007ACC")
            painter.setBrush(indicator_color)
            if item_type != "node":  # 节点库不画条，实例和模板画条区分
                painter.drawRoundedRect(rect.left(), rect.top() + 8, 3, rect.height() - 16, 1, 1)

        font = painter.font()
        font.setPointSize(10)
        font.setBold(is_selected)
        painter.setFont(font)
        painter.setPen(text_color)
        title_rect = option.rect.adjusted(15, 0, -140, 0)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, display_text)

        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(sub_text_color)
        cat_rect = option.rect.adjusted(10, 0, -15, 0)
        painter.drawText(cat_rect, Qt.AlignVCenter | Qt.AlignRight, category)

        painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(0, 42)


class CustomGraphMenu(QtWidgets.QWidget):
    source_port_item = None

    def __init__(self, graph, left_panel, parent):
        super(CustomGraphMenu, self).__init__(parent)
        self._graph = graph
        self._left_panel = left_panel
        self.parent = parent
        self._cached_data = []
        self._selected_categories = set()
        self._current_mode = MenuMode.CREATE
        self._is_upward_mode = False
        self._spawn_pos = QtCore.QPoint(0, 0)
        self._visible_items = []
        self._ignore_connection_filter = False

        # 模板目录
        self._template_dir = Path("canvas_files") / "subgraph_templates"

        # --- 状态锁定变量 ---
        self._locked_target_dir = None
        self._locked_req_type = None

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)

        self.container = QtWidgets.QFrame()
        self.container.setObjectName("SearchContainer")
        self.container.setStyleSheet(
            "#SearchContainer { background: #252526; border: 1px solid #454545; border-radius: 12px; }")

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
        self.mode_button.setToolTip("切换模式 (Tab)")

        self.filter_button = TransparentToolButton(FluentIcon.FILTER, self)
        self.filter_button.setFixedSize(35, 35)
        self.filter_button.clicked.connect(self.show_category_filter)

        self.capsule_container = QtWidgets.QWidget()
        self.capsule_layout = QtWidgets.QHBoxLayout(self.capsule_container)
        self.capsule_layout.setContentsMargins(0, 0, 0, 0)
        self.capsule_layout.setSpacing(4)

        self.search_line = QtWidgets.QLineEdit()
        self.search_line.setPlaceholderText("🔍 搜索库节点...")
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
        self.list_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        StyleSheet.QLIST.apply(self.list_widget)

        self.container_layout.addWidget(self.header_widget)
        self.container_layout.addWidget(self.list_widget)
        self.main_layout.addWidget(self.container)

        self.search_line.textChanged.connect(self.filter_list)
        self.list_widget.itemClicked.connect(self.on_item_confirmed)
        self.search_line.returnPressed.connect(self.on_return_pressed)
        self.search_line.installEventFilter(self)

        self.setFixedSize(460, 480)

    def toggle_mode(self):
        # 循环切换模式: 节点库 -> 画布定位 -> 模板库
        self._current_mode = (self._current_mode + 1) % 3

        if self._current_mode == MenuMode.CREATE:
            self.search_line.setPlaceholderText("🔍 搜索库节点...")
            self.filter_button.setEnabled(True)
            self.mode_button.setIcon(get_icon("节点库"))
            self._update_filter_capsule()
        elif self._current_mode == MenuMode.NAVIGATE:
            self.search_line.setPlaceholderText("📍 定位当前图中节点...")
            self.filter_button.setEnabled(False)
            self.mode_button.setIcon(get_icon("location"))
            self.capsule_container.hide()
        elif self._current_mode == MenuMode.TEMPLATE:
            self.search_line.setPlaceholderText("🎨 搜索子图模板...")
            self.filter_button.setEnabled(False)
            self.mode_button.setIcon(FluentIcon.TILES)  # 使用 FluentIcon 作为模板图标
            self.capsule_container.hide()

        self.update_cache()
        self.populate_ui()
        self.search_line.setText("")
        self.search_line.setFocus()

    def _update_filter_capsule(self):
        while self.capsule_layout.count():
            item = self.capsule_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if self._current_mode != MenuMode.CREATE or self._ignore_connection_filter:
            self.capsule_container.hide()
            return

        if self._locked_req_type:
            capsule = FilterCapsule(f"{self._locked_req_type.upper()}", color="#007ACC")
            capsule.closed.connect(self._clear_extra_filter)
            self.capsule_layout.addWidget(capsule)
            self.capsule_container.show()
        else:
            self.capsule_container.hide()

    def _clear_extra_filter(self):
        self._ignore_connection_filter = True
        self.capsule_container.hide()
        self.filter_list(self.search_line.text())

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
            node_type = "/".join(getattr(node, 'FULL_PATH', "Node").split("/")[:-1])
            py_keys = get_pinyin_search_keys(name)
            self._cached_data.append({
                "type": "instance",
                "node_ptr": node,
                "name": name,
                "category": node_type,
                "search_keys": f"{name} {node_type} {py_keys}".lower()
            })

    def _update_create_cache(self):
        self._cached_data = []
        tree_widget = self._left_panel.draggable_tree.tree
        root = tree_widget.invisibleRootItem()
        scanner = ComponentScanner()
        node_factory_nodes = self._graph._node_factory.nodes
        node_type_map = self._graph.parent().node_type_map

        def collect_nodes(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                node_id = item.data(0, Qt.UserRole + 1)
                if node_id:
                    node_type = node_type_map.get(node_id)
                    node_class = node_factory_nodes.get(node_type)
                    if not node_class: continue

                    node_uuid = node_class.__name__.split("StatusDynamicNode_")[1]
                    comp = scanner.get_component_by_uuid(node_uuid)
                    node_inputs = comp.get_inputs()
                    node_outputs = comp.get_outputs()

                    path_parts = []
                    p = item.parent()
                    while p and p != root:
                        path_parts.insert(0, p.text(0))
                        p = p.parent()
                    cat_full_str = "/".join(path_parts)
                    node_name = item.text(0).replace("★ ", "")
                    py_keys = get_pinyin_search_keys(node_name)

                    self._cached_data.append({
                        "type": "node",
                        "id": node_type,
                        "name": node_name,
                        "category": cat_full_str,
                        "search_keys": f"{node_name} {cat_full_str} {node_id} {py_keys}".lower(),
                        "in_port_count": len(node_inputs),
                        "out_port_count": len(node_outputs),
                        "in_port_types": {port_type for _, _, _, port_type, _ in node_inputs},
                        "out_port_types": {port_type for _, _, port_type, _ in node_outputs},
                    })
                else:
                    collect_nodes(item)

        collect_nodes(root)

    def _update_template_cache(self):
        """新增：加载磁盘模板"""
        self._cached_data = []
        if not self._template_dir.exists():
            return

        for tid_dir in self._template_dir.iterdir():
            if not tid_dir.is_dir(): continue
            meta_file = tid_dir / "meta.json"
            if meta_file.exists():
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = orjson.loads(f.read())
                    name = meta.get("name", tid_dir.name)
                    tags = meta.get("tags", [])
                    tag_str = " ".join(tags)
                    py_keys = get_pinyin_search_keys(name)

                    self._cached_data.append({
                        "type": "template",
                        "id": meta.get("id", tid_dir.name),
                        "name": name,
                        "category": "子图模板",
                        "tags": tags,
                        "search_keys": f"{name} {tag_str} {py_keys}".lower()
                    })
                except Exception:
                    continue

    def populate_ui(self):
        self.filter_list(self.search_line.text())

    def _get_max_visible_items(self):
        return 9

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
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            first_real_index = max(0, self.list_widget.count() - len(items_to_show)) if is_upward else 0
            self.list_widget.setCurrentRow(first_real_index)

    def filter_list(self, text):
        search_text = text.lower().strip()
        self._visible_items = []

        target_dir = None if self._ignore_connection_filter else self._locked_target_dir
        req_type = self._locked_req_type
        curr_mode = self._current_mode
        sel_cats = self._selected_categories
        ignore_types = [ArgumentType.UPLOAD, ArgumentType.FILE]

        for data in self._cached_data:
            # 模式特定的前置过滤
            if curr_mode == MenuMode.CREATE:
                if sel_cats and data["category"].split("/")[0] not in sel_cats: continue
                if target_dir:
                    if target_dir == 'in':
                        if data["in_port_count"] == 0: continue
                        if req_type and req_type not in data["in_port_types"] and req_type not in ignore_types: continue
                    else:
                        if data["out_port_count"] == 0: continue
                        if req_type and req_type not in data[
                            "out_port_types"] and req_type not in ignore_types: continue

            # 搜索文本过滤
            if search_text in data["search_keys"]:
                self._visible_items.append(data)

        self._update_list_widget()

    def on_item_confirmed(self, item):
        data = item.data(Qt.UserRole)
        if not data or data.get("_is_placeholder"): return

        viewer = self._graph.viewer()
        scene_viewer = viewer.get_scene_viewer() if hasattr(viewer, 'get_scene_viewer') else viewer
        scene_pos = scene_viewer.mapToScene(self._spawn_pos)

        if self._current_mode == MenuMode.CREATE:
            self._graph.begin_undo("Create Node")
            new_node = self._graph.create_node(data["id"], pos=[scene_pos.x(), scene_pos.y()])
            # 自动连接逻辑... (保持不变)
            if self.source_port_item and hasattr(self.source_port_item, 'original_node'):
                source_node = self.source_port_item.original_node
                if not self._ignore_connection_filter:
                    if self.source_port_item.port_type == 'out':
                        source_ports = source_node.output_ports()
                        source_port = next((p for p in source_ports if p.name() == self.source_port_item.name), None)
                        if source_port: QTimer.singleShot(0, lambda: new_node.set_input(0, source_port))
                    else:
                        port_index = [p.name() for p in source_node.input_ports()].index(self.source_port_item.name)
                        QTimer.singleShot(0, lambda: source_node.set_input(port_index, new_node.output_ports()[0]))
                self.source_port_item = None
            self.parent.on_selection_changed()
            self._graph.end_undo()

        elif self._current_mode == MenuMode.TEMPLATE:
            # 新增：应用子图模板逻辑
            self.parent.ui_manager.nav_panel.template_container.apply_template(data["id"], scene_pos)

        else:  # NAVIGATE 模式
            node = data.get("node_ptr")
            if node:
                self._graph.clear_selection()
                node.set_selected(True)
                self._graph.fit_to_selection()

        self.close()

    def show_at_cursor(self, pos):
        self._ignore_connection_filter = False
        self._locked_target_dir, self._locked_req_type = self._get_connection_filter()

        # 初始打开时，如果是连线弹出的，强制回到创建模式
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

        target_x = max(screen_rect.left(), min(target_x, screen_rect.right() - menu_width))

        self.populate_ui()
        viewer = self._graph.viewer()
        scene_viewer = viewer.get_scene_viewer() if hasattr(viewer, 'get_scene_viewer') else viewer
        self._spawn_pos = scene_viewer.mapFromGlobal(pos)
        self.search_line.setText("")
        self.filter_list("")

        # 布局重排（上弹出/下弹出）
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

    def set_category_filter(self, categories):
        """处理来自左侧面板筛选器的信号"""
        self._selected_categories = set(categories)
        if self._current_mode == MenuMode.CREATE:
            # 只有在节点库模式下，分类筛选才生效
            self.update_cache()
            self.populate_ui()

    def on_return_pressed(self):
        current_item = self.list_widget.currentItem()
        if current_item and not current_item.isHidden():
            self.on_item_confirmed(current_item)

    def show_category_filter(self):
        pos = self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft())
        self._left_panel.draggable_tree.category_filter_dialog.show_at(pos)

    def _get_connection_filter(self):
        viewer = self._graph.viewer()
        self.source_port_item = getattr(viewer, '_temp_connection_source', None)
        if not self.source_port_item or not hasattr(self.source_port_item, 'original_node'):
            return None, None

        source_node = self.source_port_item.original_node
        if not hasattr(source_node, 'uuid'): return None, None
        node_uuid = source_node.uuid
        port_name = self.source_port_item.name
        scanner = ComponentScanner()

        if self.source_port_item.port_type == 'out':
            node_outputs = scanner.get_component_by_uuid(node_uuid).get_outputs()
            for pname, _, port_type, _ in node_outputs:
                if pname == port_name: return 'in', port_type
        else:
            node_inputs = scanner.get_component_by_uuid(node_uuid).get_inputs()
            for pname, _, _, port_type, _ in node_inputs:
                if pname == port_name: return 'out', port_type
        return None, None

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == Qt.Key_Tab:
                self.toggle_mode()
                return True
            if event.key() == Qt.Key_Escape:
                self.close()
                return True
            if source is self.search_line and event.key() in (Qt.Key_Down, Qt.Key_Up):
                self.list_widget.setFocus()
                return True
        return super(CustomGraphMenu, self).eventFilter(source, event)