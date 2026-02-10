# -- coding: utf-8 --
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
    # ... (保持原有代码不变) ...
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

        if is_selected:
            indicator_color = QtGui.QColor("#4EC9B0") if item_type == "instance" else QtGui.QColor(
                "#CE9178") if item_type == "template" else QtGui.QColor("#007ACC")
            painter.setBrush(indicator_color)
            if item_type != "node":
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

        self._template_dir = Path("canvas_files") / "subgraph_templates"

        # --- 状态锁定变量 ---
        self._locked_target_dir = None
        self._locked_req_type = None
        self._locked_req_sub_type = None  # 【新增】锁定子类型

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
        self.list_widget.itemActivated.connect(self.on_item_confirmed)
        self.search_line.returnPressed.connect(self.on_return_pressed)
        self.search_line.installEventFilter(self)
        self.list_widget.viewport().installEventFilter(self)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self.setFixedSize(460, 480)

    def toggle_mode(self):
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
            if item.widget(): item.widget().deleteLater()

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
        self.filter_list(self.search_line.text())  # 刷新列表（显示更多主类型匹配的节点）

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
                        "in_port_types": [port_type for _, _, _, port_type, _ in node_inputs],
                        "out_port_types": [port_type for _, _, port_type, _ in node_outputs],
                        "in_port_sub_types": comp.get_input_sub_types(),
                        "out_port_sub_types": comp.get_output_sub_types()
                    })
                else:
                    collect_nodes(item)

        collect_nodes(root)

    def _update_template_cache(self):
        self._cached_data = []
        if not self._template_dir.exists():
            return

        for tid_dir in self._template_dir.iterdir():
            if not tid_dir.is_dir(): continue
            meta_file = tid_dir / "meta.json"
            # 【新增】获取图片路径
            preview_file = tid_dir / "preview.png"

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
                        "preview_path": str(preview_file) if preview_file.exists() else None,
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
        req_sub_type = self._locked_req_sub_type  # 获取锁定的子类型
        curr_mode = self._current_mode
        sel_cats = self._selected_categories
        ignore_types = [ArgumentType.UPLOAD, ArgumentType.FILE]

        for data in self._cached_data:
            # 模式特定的前置过滤
            if curr_mode == MenuMode.CREATE:
                if sel_cats and data["category"].split("/")[0] not in sel_cats: continue
                if target_dir:
                    if target_dir == 'in':
                        # 如果需要连到输入端
                        if data["in_port_count"] == 0: continue

                        # 1. 检查主类型
                        if req_type and req_type not in data["in_port_types"] and req_type not in ignore_types: continue

                        # 2. 【新增】检查子类型
                        if req_sub_type and req_sub_type not in data.get("in_port_sub_types", []): continue

                    else:
                        # 如果需要连到输出端
                        if data["out_port_count"] == 0: continue

                        # 1. 检查主类型
                        if req_type and req_type not in data[
                            "out_port_types"] and req_type not in ignore_types: continue

                        # 2. 【新增】检查子类型
                        if req_sub_type and req_sub_type not in data.get("out_port_sub_types", []): continue

            # 搜索文本过滤
            if search_text in data["search_keys"]:
                self._visible_items.append(data)

        self._update_list_widget()
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self._hide_preview()

    def on_item_confirmed(self, item):
        data = item.data(Qt.UserRole)
        if not data or data.get("_is_placeholder"): return

        viewer = self._graph.viewer()
        scene_viewer = viewer.get_scene_viewer() if hasattr(viewer, 'get_scene_viewer') else viewer
        scene_pos = scene_viewer.mapToScene(self._spawn_pos)

        if self._current_mode == MenuMode.CREATE:
            self._graph.begin_undo("Create Node")
            new_node = self._graph.create_node(data["id"], pos=[scene_pos.x(), scene_pos.y()])

            if self.source_port_item and hasattr(self.source_port_item, 'original_node'):
                source_node = self.source_port_item.original_node
                req_type = self._locked_req_type
                req_sub_type = self._locked_req_sub_type  # 获取需要的子类型

                if not self._ignore_connection_filter:
                    if self.source_port_item.port_type == 'out':
                        # 已有节点(出) -> 新节点(入)
                        source_ports = source_node.output_ports()
                        source_port = next((p for p in source_ports if p.name() == self.source_port_item.name), None)

                        if source_port:
                            # 逻辑：如果有子类型，优先找匹配子类型的第一个端口；否则按主类型找；否则找第0个
                            target_idx = 0

                            # 【新增】子类型优先匹配
                            if req_sub_type:
                                try:
                                    target_idx = data["in_port_sub_types"].index(req_sub_type)
                                except (ValueError, KeyError, IndexError):
                                    # 如果找不到子类型匹配，回退到主类型匹配
                                    try:
                                        target_idx = data["in_port_types"].index(req_type)
                                    except (ValueError, KeyError):
                                        target_idx = 0
                            else:
                                # 原有逻辑
                                try:
                                    target_idx = data["in_port_types"].index(req_type)
                                except (ValueError, KeyError):
                                    target_idx = 0

                            QTimer.singleShot(0, lambda: new_node.set_input(target_idx, source_port))

                    else:
                        # 新节点(出) -> 已有节点(入)
                        input_ports = source_node.input_ports()
                        try:
                            port_index = [p.name() for p in input_ports].index(self.source_port_item.name)

                            target_out_idx = 0
                            # 【新增】子类型优先匹配
                            if req_sub_type:
                                try:
                                    target_out_idx = data["out_port_sub_types"].index(req_sub_type)
                                except (ValueError, KeyError, IndexError):
                                    try:
                                        target_out_idx = data["out_port_types"].index(req_type)
                                    except (ValueError, KeyError):
                                        target_out_idx = 0
                            else:
                                try:
                                    target_out_idx = data["out_port_types"].index(req_type)
                                except (ValueError, KeyError):
                                    target_out_idx = 0

                            QTimer.singleShot(0, lambda: source_node.set_input(port_index,
                                                                               new_node.output_ports()[target_out_idx]))
                        except ValueError:
                            pass

                self.source_port_item = None

            self.parent.on_selection_changed()
            self._graph.end_undo()

        elif self._current_mode == MenuMode.TEMPLATE:
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
        # 【修改】这里同时获取子类型
        self._locked_target_dir, self._locked_req_type, self._locked_req_sub_type = self._get_connection_filter()

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
        self._selected_categories = set(categories)
        if self._current_mode == MenuMode.CREATE:
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
        """
        获取拖拽连线的上下文信息
        返回: (连接方向: 'in'/'out', 主类型, 子类型)
        """
        viewer = self._graph.viewer()
        self.source_port_item = getattr(viewer, '_temp_connection_source', None)
        if not self.source_port_item or not hasattr(self.source_port_item, 'original_node'):
            return None, None, None  # 【修改】返回三个None

        source_node = self.source_port_item.original_node
        if not hasattr(source_node, 'uuid'): return None, None, None
        node_uuid = source_node.uuid
        port_name = self.source_port_item.name
        scanner = ComponentScanner()
        comp = scanner.get_component_by_uuid(node_uuid)

        if self.source_port_item.port_type == 'out':
            node_outputs = comp.get_outputs()
            # 【新增】获取子类型列表
            node_sub_types = comp.get_output_sub_types()
            # 使用 enumerate 以便通过索引获取 sub_type
            for i, (pname, _, port_type, _) in enumerate(node_outputs):
                if pname == port_name:
                    # 安全获取子类型
                    sub_type = node_sub_types[i] if i < len(node_sub_types) else None
                    return 'in', port_type, sub_type
        else:
            node_inputs = comp.get_inputs()
            # 【新增】获取子类型列表
            node_sub_types = comp.get_input_sub_types()

            for i, (pname, _, _, port_type, _) in enumerate(node_inputs):
                if pname == port_name:
                    sub_type = node_sub_types[i] if i < len(node_sub_types) else None
                    return 'out', port_type, sub_type

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
                self.list_widget.setFocus()
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
            preview_data,
            preview_pos,
            self,
            delay=delay
        )

    def _build_preview_data(self, data):
        """构建预览所需数据（区分节点和模板）"""
        try:
            # 1. 如果是模板类型
            if data.get('type') == 'template':
                # 如果没有图片路径，返回 None，这样就不会弹出预览窗
                if not data.get('preview_path'):
                    return None

                # 返回符合 ImagePreviewCard 要求的数据结构
                return {
                    'name': data.get('name'),
                    'image_path': data.get('preview_path')
                }

            # 2. 如果是节点类型 (CREATE 模式)
            elif data.get('type') == 'node':
                return {
                    'name': data['name'],
                    'category': data['category'],
                    'description': self._get_node_description(data['id']),
                    'inputs': [(ptype, pname) for pname, _, _, ptype, _ in data.get('in_ports_raw', [])]
                    if 'in_ports_raw' in data else
                    [(ptype, f"input_{i}") for i, ptype in enumerate(data.get('in_port_types', []))],
                    'outputs': [(ptype, pname) for pname, _, ptype, _ in data.get('out_ports_raw', [])]
                    if 'out_ports_raw' in data else
                    [(ptype, f"output_{i}") for i, ptype in enumerate(data.get('out_port_types', []))],
                    'input_sub_types': data.get('in_port_sub_types', []),
                    'output_sub_types': data.get('out_port_sub_types', [])
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
            return getattr(comp, 'description', 'No description available.')[:200]
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
