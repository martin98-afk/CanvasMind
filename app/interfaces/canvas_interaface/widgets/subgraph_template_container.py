# -*- coding: utf-8 -*-
import orjson
import shutil
import uuid
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, QPoint, QRectF, QTimer, QMimeData
from PyQt5.QtGui import QPixmap, QPainter, QImage, QDrag
from PyQt5.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QSizePolicy, QHBoxLayout,
    QApplication, QDialog
)

from qfluentwidgets import (
    CardWidget, TransparentToolButton, FluentIcon, BodyLabel,
    StrongBodyLabel, RoundMenu, Action, SmoothScrollArea,
    TransparentPushButton, FlowLayout
)

from app.interfaces.canvas_interaface.utils.message_manager import MessageManager
from app.utils.utils import get_icon, serialize_for_json, deserialize_from_json
from app.widgets.basic_widget.category_filter import CategoryFilterDialog
from app.widgets.basic_widget.resizable_image_label import ResizableImageLabel
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog, CustomEditableComboDialog


class TemplateCard(CardWidget):
    """支持区分点击和拖拽的卡片包装类"""

    def __init__(self, tid, img_path, parent=None):
        super().__init__(parent)
        self.tid = tid
        self.img_path = img_path
        self._drag_start_pos = None
        self._is_dragging = False
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or self._drag_start_pos is None:
            return

        distance = (event.pos() - self._drag_start_pos).manhattanLength()
        if distance > QApplication.startDragDistance():
            self._is_dragging = True
            self._start_drag()
            self._drag_start_pos = None
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_dragging:
            # 这里的 window() 寻找面板实例并触发你原本的预览逻辑
            panel = self.window().findChild(SubgraphTemplatePanel)
            if panel:
                panel._show_preview_dialog(self.img_path)
        self._drag_start_pos = None
        self._is_dragging = False
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData("application/x-subgraph-template", self.tid.encode('utf-8'))
        drag.setMimeData(mime_data)

        # 拖拽时的预览图标
        img_label = self.findChild(ResizableImageLabel)
        if img_label and img_label.pixmap():
            pixmap = img_label.pixmap().scaled(180, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        drag.exec_(Qt.CopyAction)


class SubgraphTemplatePanel(QWidget):
    """子图模板面板 - 完整恢复版"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("templateManager")
        self._template_cards = {}
        self._tag_containers = {}
        self._built = False
        self._selected_tags = set()

        self._template_cache = {}
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._refresh_content)

        self._template_dir = Path("canvas_files") / "subgraph_templates"
        self._template_dir.mkdir(parents=True, exist_ok=True)

        self.setup_ui()

    def setup_ui(self):
        if self._built:
            self._refresh_content()
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addStretch()

        self.filter_btn = TransparentPushButton(self.tr("筛选标签"), self, FluentIcon.FILTER)
        self.filter_btn.setIconSize(QSize(16, 16))
        self.filter_btn.setFixedHeight(36)
        self.filter_btn.clicked.connect(self._show_tag_filter)
        top_layout.addWidget(self.filter_btn)

        add_env_btn = TransparentPushButton(text=self.tr("添加为模板"), parent=self, icon=FluentIcon.ADD)
        add_env_btn.setIconSize(QSize(16, 16))
        add_env_btn.setFixedHeight(36)
        add_env_btn.clicked.connect(self.add_template)
        top_layout.addWidget(add_env_btn)

        layout.addLayout(top_layout)

        self.container = QWidget(self)
        self.container.setObjectName("templateContainer")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(5, 2, 5, 5)
        self.container_layout.setSpacing(6)

        scroll = self.set_scroll(self.container)
        layout.addWidget(scroll, 1)

        QTimer.singleShot(100, self._refresh_content)
        self._built = True

    def set_scroll(self, widget):
        scroll = SmoothScrollArea(self)
        scroll.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background-color: transparent; border: none;")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        scroll.setWidget(widget)
        return scroll

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                del item

    def _refresh_content(self):
        self._clear_layout(self.container_layout)
        for card in self._template_cards.values():
            card.deleteLater()
        for container, _ in self._tag_containers.values():
            container.deleteLater()
        self._template_cards.clear()
        self._tag_containers.clear()

        all_templates = self._load_templates()
        if self._selected_tags:
            templates = [
                (tid, name, img, tags) for tid, name, img, tags in all_templates
                if self._selected_tags & set(tags)
            ]
        else:
            templates = all_templates

        if not templates:
            label = BodyLabel(self.tr("暂无子图模板"))
            label.setAlignment(Qt.AlignCenter)
            self.container_layout.addWidget(label)
        else:
            for tid, name, img_path, tags in templates:
                card = self._create_template_card(tid, name, img_path, tags)
                self.container_layout.addWidget(card)
                self._template_cards[tid] = card

        self.container_layout.addStretch(1)

    def _load_templates(self):
        current_tids = {d.name for d in self._template_dir.iterdir() if d.is_dir()}
        stale_tids = set(self._template_cache.keys()) - current_tids
        for tid in stale_tids:
            self._template_cache.pop(tid, None)

        for tid in current_tids:
            if tid not in self._template_cache:
                meta_file = self._template_dir / tid / "meta.json"
                preview_file = self._template_dir / tid / "preview.png"
                if meta_file.exists() and preview_file.exists():
                    try:
                        with open(meta_file, 'r', encoding='utf-8') as f:
                            meta = orjson.loads(f.read())
                        self._template_cache[tid] = {
                            "name": meta.get("name", tid),
                            "tags": meta.get("tags", []),
                            "preview_path": str(preview_file)
                        }
                    except Exception:
                        continue
        return [(tid, info["name"], info["preview_path"], info["tags"]) for tid, info in self._template_cache.items()]

    def _get_template_tags(self, tid: str) -> list:
        if tid in self._template_cache:
            return self._template_cache[tid]["tags"]
        return []

    def _create_template_card(self, tid: str, name: str, img_path: str, tags: list):
        # 包装卡片，使其支持拖拽
        card = TemplateCard(tid, img_path, self)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(0)
        name_label = StrongBodyLabel(name)
        name_label.setWordWrap(True)
        btn_layout.addWidget(name_label, 1)
        btn_layout.addStretch()

        apply_btn = TransparentToolButton(get_icon("导入"), self)
        apply_btn.setIconSize(QSize(16, 16))
        apply_btn.setFixedSize(28, 28)
        apply_btn.setToolTip(self.tr("应用模板"))
        apply_btn.clicked.connect(lambda _, t=tid: self.apply_template(t))

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setIconSize(QSize(16, 16))
        delete_btn.setFixedSize(28, 28)
        delete_btn.setToolTip(self.tr("删除模板"))
        delete_btn.clicked.connect(lambda _, t=tid: self.delete_template(t))

        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        img_label = ResizableImageLabel(self)
        img_label.setMaxHeight(200)
        # 穿透鼠标，由 Card 统一处理拖拽和预览逻辑
        img_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            img_label.setOriginalPixmap(pixmap)
        else:
            placeholder = QPixmap(300, 180)
            placeholder.fill(Qt.transparent)
            painter = QPainter(placeholder)
            painter.setPen(Qt.gray)
            painter.drawText(placeholder.rect(), Qt.AlignCenter, self.tr("预览图丢失"))
            painter.end()
            img_label.setOriginalPixmap(placeholder)
        layout.addWidget(img_label, 1)

        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        tag_container = QWidget()
        tag_layout = FlowLayout()
        tag_container.setLayout(tag_layout)
        tag_container.setLayoutDirection(Qt.RightToLeft)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setSpacing(2)
        self._tag_containers[tid] = (tag_container, tag_layout)
        self._update_tag_container(tid, tags)
        bottom_layout.addWidget(tag_container, 1)

        add_tag_btn = TransparentToolButton(FluentIcon.ADD, self)
        add_tag_btn.setIconSize(QSize(12, 12))
        add_tag_btn.setFixedSize(20, 20)
        add_tag_btn.setToolTip(self.tr("添加标签"))
        add_tag_btn.clicked.connect(lambda: self._on_add_tag_click(tid))
        bottom_layout.addWidget(add_tag_btn)
        layout.addWidget(bottom_container)

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos: self._show_context_menu(tid, card, pos))
        return card

    def _on_add_tag_click(self, tid):
        dialog = CustomEditableComboDialog(
            self.tr("添加标签"), self.tr("标签名（如：预处理、检测）"),
            items=self._get_all_tags(), parent=self.parent
        )
        if dialog.exec():
            new_tag = dialog.get_text().strip()
            if new_tag:
                current_tags = self._get_template_tags(tid)
                if new_tag not in current_tags:
                    current_tags.append(new_tag)
                    self._save_template_tags(tid, current_tags)
                    if tid in self._template_cache:
                        self._template_cache[tid]["tags"] = current_tags
                    self._update_tag_container(tid, current_tags)

    def _show_context_menu(self, tid, card, pos):
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FluentIcon.ACCEPT_MEDIUM, self.tr("应用"), triggered=lambda: self.apply_template(tid)))
        menu.addAction(Action(FluentIcon.DELETE, self.tr("删除"), triggered=lambda: self.delete_template(tid)))
        menu.exec_(card.mapToGlobal(pos))

    def _update_tag_container(self, tid: str, tags: list):
        if tid not in self._tag_containers: return
        container, layout = self._tag_containers[tid]
        # 修复 deleteLater 报错：彻底清理 FlowLayout
        while layout.count():
            item = layout.takeAt(0)
            item.deleteLater()
            del item

        for tag in tags:
            tag_label = BodyLabel(f"#{tag}")
            tag_label.setStyleSheet("""
                QLabel {
                    background-color: rgba(100, 100, 255, 30);
                    border: 1px solid rgba(100, 100, 255, 80);
                    border-radius: 8px;
                    padding: 2px 6px;
                    font-size: 11px;
                    color: white;
                }
            """)
            tag_label.setCursor(Qt.PointingHandCursor)
            # 恢复原有的点击删除逻辑
            tag_label.mousePressEvent = lambda e, t=tag: self._remove_tag_from_card(tid, t)
            layout.addWidget(tag_label)

    def _save_template_tags(self, tid, tags):
        meta_file = self._template_dir / tid / "meta.json"
        if not meta_file.exists(): return
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = orjson.loads(f.read())
            meta['tags'] = list(dict.fromkeys(tags))
            with open(meta_file, 'wb') as f:
                f.write(orjson.dumps(meta, option=orjson.OPT_INDENT_2))
        except Exception:
            pass

    def _remove_tag_from_card(self, tid, tag_to_remove):
        current_tags = self._get_template_tags(tid)
        if tag_to_remove in current_tags:
            current_tags.remove(tag_to_remove)
            self._save_template_tags(tid, current_tags)
            if tid in self._template_cache:
                self._template_cache[tid]["tags"] = current_tags
            self._update_tag_container(tid, current_tags)

    def _get_all_tags(self):
        all_tags = set()
        for info in self._template_cache.values():
            all_tags.update(info["tags"])
        return sorted(all_tags)

    def _show_tag_filter(self):
        all_tags = self._get_all_tags()
        if not all_tags:
            MessageManager.info(self.tr("提示"), self.tr("暂无可用标签"), self.parent)
            return
        # 修复 TypeError: 恢复原始参数名 categories
        dialog = CategoryFilterDialog(
            categories=all_tags,
            parent=self,
            selected_categories=self._selected_tags.copy(),
            direction="down",
            max_visible=8
        )
        dialog.categories_changed.connect(self._on_tags_selected)
        dialog.show_at(self.filter_btn.mapToGlobal(QPoint(0, self.filter_btn.height())))

    def _on_tags_selected(self, selected_tags: set):
        self._selected_tags = selected_tags
        self._debounce_timer.start(100)

    def apply_template(self, tid: str, pos: QPoint = None):
        """应用模板。pos 应为场景坐标(ScenePos)"""
        graph = getattr(self.parent, 'graph', None)
        if not graph: return

        nodes_file = self._template_dir / tid / "nodes.json"
        if not nodes_file.exists(): return
        with open(nodes_file, "r", encoding="utf-8") as f:
            nodes_data = deserialize_from_json(orjson.loads(f.read()))

        # 性能优化：暂停更新
        viewer = graph.viewer()
        viewer.setUpdatesEnabled(False)

        try:
            graph._undo_stack.beginMacro('Apply Subgraph Template')
            graph.clear_selection()
            pasted_nodes, _ = graph._deserialize(nodes_data, relative_pos=True, adjust_graph_style=False)

            if pasted_nodes:
                # 寻找中心点用于偏移
                min_x = min(n.pos()[0] for n in pasted_nodes)
                min_y = min(n.pos()[1] for n in pasted_nodes)

                # 坐标修正核心逻辑
                if pos:
                    # 拖拽时：直接使用传入的场景坐标
                    target_x, target_y = pos.x(), pos.y()
                else:
                    # 按钮点击时：放在视图中心
                    center = viewer.mapToScene(viewer.rect().center())
                    target_x, target_y = center.x(), center.y()

                for node in pasted_nodes:
                    node.set_property("persistent_id", str(uuid.uuid4()))
                    dx = node.pos()[0] - min_x
                    dy = node.pos()[1] - min_y
                    node.set_pos(target_x + dx, target_y + dy)
                    node.set_selected(True)

                if hasattr(self.parent, '_invalidate_node_cache'):
                    self.parent._invalidate_node_cache()

            graph._undo_stack.endMacro()
        finally:
            viewer.setUpdatesEnabled(True)
            viewer.viewport().update()
            MessageManager.info("应用模板", f"已插入 {len(pasted_nodes)} 个节点", self.parent)

    def add_template(self):
        graph = getattr(self.parent, 'graph', None)
        if not graph:
            MessageManager.error(self.tr("错误"), self.tr("无法获取画布"), self.parent)
            return
        selected_nodes = graph.selected_nodes()
        if not selected_nodes:
            MessageManager.warning(self.tr("提示"), self.tr("请先选择节点"), self.parent)
            return

        default_name = f"{getattr(self.parent, 'workflow_name', '未命名')}子图"
        dialog = CustomInputDialog("请输入模板名称", self.tr("模板名称"), default_name, parent=self.parent)
        if not dialog.exec(): return
        template_name = dialog.get_text().strip()
        if not template_name: return

        nodes_data = graph._serialize(selected_nodes)
        try:
            preview_pixmap = self._capture_selected_nodes(selected_nodes)
        except Exception:
            preview_pixmap = QPixmap(300, 180)
            preview_pixmap.fill(Qt.transparent)

        tid = str(uuid.uuid4())
        template_path = self._template_dir / tid
        template_path.mkdir(exist_ok=True)

        with open(template_path / "nodes.json", "wb") as f:
            f.write(orjson.dumps(serialize_for_json(nodes_data), option=orjson.OPT_INDENT_2))
        preview_pixmap.save(str(template_path / "preview.png"))
        with open(template_path / "meta.json", "wb") as f:
            f.write(orjson.dumps({"id": tid, "name": template_name, "tags": []}, option=orjson.OPT_INDENT_2))

        self._template_cache[tid] = {"name": template_name, "tags": [],
                                     "preview_path": str(template_path / "preview.png")}
        self._refresh_content()

    def _capture_selected_nodes(self, nodes):
        scene = self.parent.graph.viewer().scene()
        rect = QRectF()
        for node in nodes:
            rect = rect.united(node.view.sceneBoundingRect())
        if rect.isEmpty(): return QPixmap()
        rect.adjust(-25, -25, 25, 25)
        image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        scene.render(painter, target=QRectF(image.rect()), source=rect)
        painter.end()
        return QPixmap.fromImage(image)

    def _show_preview_dialog(self, img_path: str):
        dialog = QDialog(self)
        dialog.setWindowTitle("模板预览")
        dialog.resize(800, 600)
        dialog.setStyleSheet("background-color: #1e1e1e;")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            screen_size = QApplication.primaryScreen().availableGeometry().size() * 0.8
            label.setPixmap(pixmap.scaled(screen_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        label.mousePressEvent = lambda e: dialog.accept()
        layout.addWidget(label)
        dialog.exec_()

    def delete_template(self, tid: str):
        template_path = self._template_dir / tid
        if template_path.exists(): shutil.rmtree(template_path)
        self._template_cache.pop(tid, None)
        self._refresh_content()