# -*- coding: utf-8 -*-
import json
import uuid
import shutil
import traceback
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, QPoint, QRectF, QTimer, QMimeData, pyqtSignal
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

from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager
from app.utils.utils import get_icon
from app.widgets.basic_widget.resizable_image_label import ResizableImageLabel
from app.widgets.basic_widget.category_filter import CategoryFilterDialog
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog, CustomEditableComboDialog


class TemplateCard(CardWidget):
    """自定义卡片类：处理拖拽逻辑并解决点击冲突"""

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

        img_label = self.findChild(ResizableImageLabel)
        if img_label and img_label.pixmap():
            pixmap = img_label.pixmap().scaled(180, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        drag.exec_(Qt.CopyAction)


class SubgraphTemplatePanel(QWidget):
    """子图模板面板 - 支持局部更新 Tag、图片预览、标签筛选、拖拽应用"""

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

    def _clear_layout(self, layout: QVBoxLayout):
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
                            meta = json.load(f)
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
        card = TemplateCard(tid, img_path, self)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        btn_layout = QHBoxLayout()
        name_label = StrongBodyLabel(name)
        name_label.setWordWrap(True)
        btn_layout.addWidget(name_label, 1)
        btn_layout.addStretch()

        apply_btn = TransparentToolButton(get_icon("导入"), self)
        apply_btn.setFixedSize(28, 28)
        apply_btn.clicked.connect(lambda _, t=tid: self.apply_template(t))

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(28, 28)
        delete_btn.clicked.connect(lambda _, t=tid: self.delete_template(t))

        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        img_label = ResizableImageLabel(self)
        img_label.setMaxHeight(200)
        img_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        pixmap = QPixmap(img_path)
        img_label.setOriginalPixmap(pixmap if not pixmap.isNull() else QPixmap())
        layout.addWidget(img_label, 1)

        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
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
        add_tag_btn.setFixedSize(20, 20)
        add_tag_btn.clicked.connect(lambda: self._on_add_tag_click(tid))
        bottom_layout.addWidget(add_tag_btn)
        layout.addWidget(bottom_container)

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos: self._show_context_menu(tid, card, pos))
        return card

    def _on_add_tag_click(self, tid):
        dialog = CustomEditableComboDialog(self.tr("添加标签"), self.tr("标签名"), items=self._get_all_tags(),
                                           parent=self.parent)
        if dialog.exec():
            new_tag = dialog.get_text().strip()
            if new_tag:
                current_tags = self._get_template_tags(tid)
                if new_tag not in current_tags:
                    current_tags.append(new_tag)
                    self._save_template_tags(tid, current_tags)
                    if tid in self._template_cache: self._template_cache[tid]["tags"] = current_tags
                    self._update_tag_container(tid, current_tags)

    def _show_context_menu(self, tid, card, pos):
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FluentIcon.ACCEPT_MEDIUM, self.tr("应用"), triggered=lambda: self.apply_template(tid)))
        menu.addAction(Action(FluentIcon.DELETE, self.tr("删除"), triggered=lambda: self.delete_template(tid)))
        menu.exec_(card.mapToGlobal(pos))

    def _update_tag_container(self, tid: str, tags: list):
        if tid not in self._tag_containers: return
        container, layout = self._tag_containers[tid]
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for tag in tags:
            tag_label = BodyLabel(f"#{tag}")
            tag_label.setStyleSheet(
                "QLabel { background-color: rgba(100, 100, 255, 30); border: 1px solid rgba(100, 100, 255, 80); border-radius: 8px; padding: 2px 6px; font-size: 11px; color: white; }")
            tag_label.setCursor(Qt.PointingHandCursor)
            tag_label.mousePressEvent = lambda e, t=tag: self._remove_tag_from_card(tid, t)
            layout.addWidget(tag_label)

    def _save_template_tags(self, tid, tags):
        meta_file = self._template_dir / tid / "meta.json"
        if not meta_file.exists(): return
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            meta['tags'] = list(dict.fromkeys(tags))
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(e)

    def _remove_tag_from_card(self, tid, tag_to_remove):
        current_tags = self._get_template_tags(tid)
        if tag_to_remove in current_tags:
            current_tags.remove(tag_to_remove)
            self._save_template_tags(tid, current_tags)
            if tid in self._template_cache: self._template_cache[tid]["tags"] = current_tags
            self._update_tag_container(tid, current_tags)

    def _get_all_tags(self):
        all_tags = set()
        for info in self._template_cache.values(): all_tags.update(info["tags"])
        return sorted(all_tags)

    def _show_tag_filter(self):
        all_tags = self._get_all_tags()
        if not all_tags: return
        dialog = CategoryFilterDialog(categories=all_tags, parent=self, selected_categories=self._selected_tags.copy(),
                                      direction="down")
        dialog.categories_changed.connect(self._on_tags_selected)
        dialog.show_at(self.filter_btn.mapToGlobal(QPoint(0, self.filter_btn.height())))

    def _on_tags_selected(self, selected_tags):
        self._selected_tags = selected_tags
        self._debounce_timer.start(100)

    # ========================== 核心优化部分：应用模板 ==========================
    def apply_template(self, tid: str, pos: QPoint = None):
        """应用模板。pos 是画布上的场景坐标"""
        graph = getattr(self.parent, 'graph', None)
        if not graph: return

        nodes_file = self._template_dir / tid / "nodes.json"
        if not nodes_file.exists(): return
        with open(nodes_file, "r", encoding="utf-8") as f:
            nodes_data = json.load(f)

        # 1. 禁用画布更新，防止每插入一个节点都重绘导致的卡顿
        viewer = graph.viewer()
        viewer.setUpdatesEnabled(False)

        try:
            graph._undo_stack.beginMacro('Apply Subgraph Template')
            graph.clear_selection()

            # 2. 反序列化
            pasted_nodes = graph._deserialize(nodes_data, relative_pos=True, adjust_graph_style=True)

            if pasted_nodes:
                # 3. 计算位置偏移
                # 找到当前这批新节点最左上角的坐标
                min_x = min(n.pos()[0] for n in pasted_nodes)
                min_y = min(n.pos()[1] for n in pasted_nodes)

                # 确定目标点 (target_x, target_y)
                if pos:
                    # 如果是拖拽生成的，pos 已经是 scenePos，直接使用
                    target_x, target_y = pos.x(), pos.y()
                else:
                    # 点击生成的，放在视图中心
                    center = viewer.mapToScene(viewer.rect().center())
                    target_x, target_y = center.x(), center.y()

                # 4. 批量移动并生成新 ID
                for node in pasted_nodes:
                    node.set_property("persistent_id", str(uuid.uuid4()))
                    # 计算相对于原本左上角的偏移量，并应用到目标点
                    dx = node.pos()[0] - min_x
                    dy = node.pos()[1] - min_y
                    node.set_pos(target_x + dx, target_y + dy)
                    node.set_selected(True)

                if hasattr(self.parent, '_invalidate_node_cache'):
                    self.parent._invalidate_node_cache()

            graph._undo_stack.endMacro()

        finally:
            # 5. 恢复重绘并强制刷新一次
            viewer.setUpdatesEnabled(True)
            viewer.viewport().update()
            graph.fit_to_selection()
            MessageManager.success("应用成功", f"插入了 {len(pasted_nodes)} 个节点", self.parent)

    # =========================================================================

    def add_template(self):
        graph = getattr(self.parent, 'graph', None)
        if not graph: return
        selected_nodes = graph.selected_nodes()
        if not selected_nodes:
            MessageManager.warning(self.tr("提示"), self.tr("请先选择节点"), self.parent)
            return
        dialog = CustomInputDialog("请输入模板名称", self.tr("模板名称"), "新子图模板", parent=self.parent)
        if not dialog.exec(): return
        template_name = dialog.get_text().strip()
        if not template_name: return

        nodes_data = graph._serialize(selected_nodes)
        preview_pixmap = self._capture_selected_nodes(selected_nodes)
        tid = str(uuid.uuid4())
        template_path = self._template_dir / tid
        template_path.mkdir(exist_ok=True)
        with open(template_path / "nodes.json", "w", encoding="utf-8") as f:
            json.dump(nodes_data, f, indent=2)
        preview_pixmap.save(str(template_path / "preview.png"))
        with open(template_path / "meta.json", "w", encoding="utf-8") as f:
            json.dump({"id": tid, "name": template_name, "tags": []}, f)
        self._template_cache[tid] = {"name": template_name, "tags": [],
                                     "preview_path": str(template_path / "preview.png")}
        self._refresh_content()

    def _capture_selected_nodes(self, nodes):
        scene = self.parent.graph.viewer().scene()
        rect = QRectF()
        for node in nodes: rect = rect.united(node.view.sceneBoundingRect())
        rect.adjust(-25, -25, 25, 25)
        image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        scene.render(painter, target=QRectF(image.rect()), source=rect)
        painter.end()
        return QPixmap.fromImage(image)

    def _show_preview_dialog(self, img_path):
        dialog = QDialog(self);
        dialog.resize(800, 600);
        dialog.setStyleSheet("background-color: #1e1e1e;")
        layout = QVBoxLayout(dialog)
        label = QLabel();
        label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(img_path)
        if not pixmap.isNull(): label.setPixmap(
            pixmap.scaled(QApplication.primaryScreen().availableGeometry().size() * 0.8, Qt.KeepAspectRatio,
                          Qt.SmoothTransformation))
        label.mousePressEvent = lambda e: dialog.accept()
        layout.addWidget(label);
        dialog.exec_()

    def delete_template(self, tid):
        if (self._template_dir / tid).exists(): shutil.rmtree(self._template_dir / tid)
        self._template_cache.pop(tid, None);
        self._refresh_content()