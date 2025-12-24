# -*- coding: utf-8 -*-
import json
import uuid
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, QPoint, QRectF, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QImage
from PyQt5.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QSizePolicy, QHBoxLayout,
    QSpacerItem, QApplication, QDialog
)
from qfluentwidgets import (
    CardWidget, TransparentToolButton, FluentIcon, BodyLabel,
    StrongBodyLabel, RoundMenu, Action, SmoothScrollArea,
    TransparentPushButton, FlowLayout
)

from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager
from app.utils.utils import get_icon
from app.widgets.basic_widget.resizable_image_label import ResizableImageLabel
from app.widgets.category_filter import CategoryFilterDialog
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog, CustomEditableComboDialog


class SubgraphTemplatePanel(QWidget):
    """子图模板面板 - 支持局部更新 Tag、图片预览、标签筛选（带缓存与防抖）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("templateManager")
        self._template_cards = {}      # {tid: card_widget}
        self._tag_containers = {}      # {tid: (container_widget, layout)}
        self._built = False
        self._selected_tags = set()

        # === 新增：缓存与防抖 ===
        self._template_cache = {}      # {tid: {"name": str, "tags": list, "preview_path": str}}
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

        # === 顶部：添加 + 筛选 ===
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addStretch()

        self.filter_btn = TransparentPushButton("筛选标签", self, FluentIcon.FILTER)
        self.filter_btn.setIconSize(QSize(16, 16))
        self.filter_btn.setFixedHeight(36)
        self.filter_btn.clicked.connect(self._show_tag_filter)
        top_layout.addWidget(self.filter_btn)

        add_env_btn = TransparentPushButton(text="添加为模板", parent=self, icon=FluentIcon.ADD)
        add_env_btn.setIconSize(QSize(16, 16))
        add_env_btn.setFixedHeight(36)
        add_env_btn.clicked.connect(self.add_template)
        top_layout.addWidget(add_env_btn)

        layout.addLayout(top_layout)

        # === 滚动内容区 ===
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
        """仅在结构变化时调用：新增/删除模板、筛选标签"""
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
            label = BodyLabel("暂无子图模板")
            label.setAlignment(Qt.AlignCenter)
            self.container_layout.addWidget(label)
        else:
            for tid, name, img_path, tags in templates:
                card = self._create_template_card(tid, name, img_path, tags)
                self.container_layout.addWidget(card)
                self._template_cards[tid] = card

        self.container_layout.addStretch(1)

    def _load_templates(self):
        """使用缓存加载模板元数据，避免重复 I/O"""
        current_tids = {d.name for d in self._template_dir.iterdir() if d.is_dir()}

        # 清理已删除模板的缓存
        stale_tids = set(self._template_cache.keys()) - current_tids
        for tid in stale_tids:
            self._template_cache.pop(tid, None)

        # 加载新增或未缓存的模板
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

        # 构建返回列表
        templates = []
        for tid, info in self._template_cache.items():
            templates.append((tid, info["name"], info["preview_path"], info["tags"]))
        return templates

    def _get_template_tags(self, tid: str) -> list:
        """从缓存获取标签（若无则 fallback 到文件）"""
        if tid in self._template_cache:
            return self._template_cache[tid]["tags"]
        # fallback（理论上不应发生）
        meta_file = self._template_dir / tid / "meta.json"
        if meta_file.exists():
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    return meta.get("tags", [])
            except:
                pass
        return []

    def _create_template_card(self, tid: str, name: str, img_path: str, tags: list):
        card = CardWidget(self)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # 名称 + 操作按钮
        btn_layout = QHBoxLayout()
        name_label = StrongBodyLabel(name)
        name_label.setWordWrap(True)
        btn_layout.addWidget(name_label, 1)
        btn_layout.addSpacing(2)

        apply_btn = TransparentToolButton(get_icon("导入"), self)
        apply_btn.setIconSize(QSize(16, 16))
        apply_btn.setFixedSize(32, 32)
        apply_btn.setToolTip("应用模板")
        apply_btn.clicked.connect(lambda _, t=tid: self.apply_template(t))

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setIconSize(QSize(16, 16))
        delete_btn.setFixedSize(32, 32)
        delete_btn.setToolTip("删除模板")
        delete_btn.clicked.connect(lambda _, t=tid: self.delete_template(t))

        btn_layout.addWidget(delete_btn)
        btn_layout.addSpacing(1)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        # 图片
        img_label = ResizableImageLabel(self)
        img_label.setMaxHeight(200)
        img_label.setCursor(Qt.PointingHandCursor)
        img_label.clicked.connect(lambda: self._show_preview_dialog(img_path))

        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            img_label.setOriginalPixmap(pixmap)
        else:
            placeholder = QPixmap(300, 180)
            placeholder.fill(Qt.transparent)
            painter = QPainter(placeholder)
            painter.setPen(Qt.gray)
            painter.drawText(placeholder.rect(), Qt.AlignCenter, "预览图丢失")
            painter.end()
            img_label.setOriginalPixmap(placeholder)

        layout.addWidget(img_label, 1)

        # === 可局部更新的 Tag 容器 ===
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

        # 添加 + 按钮
        add_tag_btn = TransparentToolButton(FluentIcon.ADD, self)
        add_tag_btn.setIconSize(QSize(12, 12))
        add_tag_btn.setFixedSize(20, 20)
        add_tag_btn.setToolTip("添加标签")

        def on_add_tag():
            dialog = CustomEditableComboDialog(
                "添加标签", "标签名（如：预处理、检测）",
                items=self._get_all_tags(), parent=self.parent
            )
            if dialog.exec():
                new_tag = dialog.get_text().strip()
                if new_tag:
                    current_tags = self._get_template_tags(tid)
                    if new_tag not in current_tags:
                        current_tags.append(new_tag)
                        self._save_template_tags(tid, current_tags)
                        # 更新缓存
                        if tid in self._template_cache:
                            self._template_cache[tid]["tags"] = current_tags
                        # 局部更新 UI
                        self._update_tag_container(tid, current_tags)

        add_tag_btn.clicked.connect(on_add_tag)
        bottom_layout.addWidget(add_tag_btn)
        layout.addWidget(bottom_container)

        # 右键菜单
        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(Action(FluentIcon.ACCEPT_MEDIUM, "应用", triggered=lambda: self.apply_template(tid)))
            menu.addAction(Action(FluentIcon.DELETE, "删除", triggered=lambda: self.delete_template(tid)))
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    def _update_tag_container(self, tid: str, tags: list):
        """局部更新指定卡片的 tag 栏"""
        if tid not in self._tag_containers:
            return
        container, layout = self._tag_containers[tid]
        # 清空
        while layout.count():
            item = layout.takeAt(0)
            item.deleteLater()
        # 重新添加 tag
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
            tag_label.mousePressEvent = lambda e, t=tag: self._remove_tag_from_card(tid, t)
            layout.addWidget(tag_label)

    def _save_template_tags(self, tid: str, tags: list):
        meta_file = self._template_dir / tid / "meta.json"
        if not meta_file.exists():
            return
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            meta['tags'] = list(dict.fromkeys(tags))
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存 tag 失败: {e}")

    def _remove_tag_from_card(self, tid: str, tag_to_remove: str):
        current_tags = self._get_template_tags(tid)
        if tag_to_remove in current_tags:
            current_tags.remove(tag_to_remove)
            self._save_template_tags(tid, current_tags)
            # 更新缓存
            if tid in self._template_cache:
                self._template_cache[tid]["tags"] = current_tags
            # 局部更新
            self._update_tag_container(tid, current_tags)

    def _get_all_tags(self):
        all_tags = set()
        for info in self._template_cache.values():
            all_tags.update(info["tags"])
        return sorted(all_tags)

    def _show_tag_filter(self):
        all_tags = self._get_all_tags()
        if not all_tags:
            MessageManager.info("提示", "暂无可用标签", self.parent)
            return

        dialog = CategoryFilterDialog(
            categories=all_tags,
            parent=self,
            selected_categories=self._selected_tags.copy(),
            direction="down",
            max_visible=8
        )
        dialog.categories_changed.connect(self._on_tags_selected)
        pos = self.filter_btn.mapToGlobal(QPoint(0, self.filter_btn.height()))
        dialog.show_at(pos)

    def _on_tags_selected(self, selected_tags: set):
        self._selected_tags = selected_tags
        # ✅ 防抖：100ms 内多次筛选只刷新一次
        self._debounce_timer.start(100)

    # ========== 原有功能（无需改动）==========
    def add_template(self):
        graph = getattr(self.parent, 'graph', None)
        if not graph:
            MessageManager.error("错误", "无法获取画布", self.parent)
            return

        selected_nodes = graph.selected_nodes()
        if not selected_nodes:
            MessageManager.warning("提示", "请先选择节点", self.parent)
            return

        default_name = f"{getattr(self.parent, 'workflow_name', '未命名')}子图"
        template_name_dialog = CustomInputDialog("请输入模板名称", "模板名称", default_name, parent=self.parent)
        if not template_name_dialog.exec():
            return
        template_name = template_name_dialog.get_text().strip()
        if not template_name:
            return

        nodes_data = graph._serialize(selected_nodes)

        try:
            preview_pixmap = self._capture_selected_nodes(selected_nodes)
        except Exception as e:
            preview_pixmap = QPixmap(300, 180)
            preview_pixmap.fill(Qt.transparent)

        tid = str(uuid.uuid4())
        template_path = self._template_dir / tid
        template_path.mkdir(exist_ok=True)

        with open(template_path / "nodes.json", "w", encoding="utf-8") as f:
            json.dump(nodes_data, f, ensure_ascii=False, indent=2)
        preview_pixmap.save(str(template_path / "preview.png"))
        with open(template_path / "meta.json", "w", encoding="utf-8") as f:
            json.dump({"id": tid, "name": template_name, "tags": []}, f, ensure_ascii=False)

        # ✅ 更新缓存
        self._template_cache[tid] = {
            "name": template_name,
            "tags": [],
            "preview_path": str(template_path / "preview.png")
        }

        self._refresh_content()  # 新增模板需立即刷新

    def _capture_selected_nodes(self, nodes):
        selected = self.parent.graph.selected_nodes()
        if not selected:
            return
        scene = self.parent.graph.viewer().scene()
        rect = QRectF()
        for node in selected:
            item_rect = node.view.sceneBoundingRect()
            rect = rect.united(item_rect)
        if rect.isEmpty():
            return
        rect.adjust(-25, -25, 25, 25)
        image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        scene.render(painter, target=QRectF(image.rect()), source=rect)
        painter.end()
        return image

    def _show_preview_dialog(self, img_path: str):
        dialog = QDialog(self)
        dialog.setWindowTitle("模板预览")
        dialog.setModal(True)
        dialog.resize(800, 600)
        dialog.setStyleSheet("background-color: #1e1e1e;")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("background-color: transparent;")

        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            screen = QApplication.primaryScreen()
            screen_size = screen.availableGeometry().size() * 0.8
            scaled_pixmap = pixmap.scaled(screen_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(scaled_pixmap)
        else:
            label.setText("无法加载预览图")
            label.setStyleSheet("color: gray; font-size: 14px;")

        label.setCursor(Qt.PointingHandCursor)
        label.mousePressEvent = lambda e: dialog.accept()

        layout.addWidget(label)
        dialog.exec_()

    def apply_template(self, tid: str):
        graph = getattr(self.parent, 'graph', None)
        if not graph:
            return

        template_path = self._template_dir / tid
        nodes_file = template_path / "nodes.json"
        if not nodes_file.exists():
            return

        with open(nodes_file, "r", encoding="utf-8") as f:
            nodes_data = json.load(f)

        selected_nodes = graph.selected_nodes()
        if selected_nodes:
            avg_x = sum(n.pos()[0] for n in selected_nodes) / len(selected_nodes)
            avg_y = sum(n.pos()[1] for n in selected_nodes) / len(selected_nodes)
            offset = (50, 50)
        else:
            viewer = graph.viewer()
            center = viewer.mapToScene(viewer.rect().center())
            avg_x, avg_y = center.x(), center.y()
            offset = (0, 0)

        graph._undo_stack.beginMacro('pasted nodes')
        graph.clear_selection()
        pasted_nodes = graph._deserialize(nodes_data, relative_pos=True, adjust_graph_style=True)
        [n.set_selected(True) for n in pasted_nodes]
        graph._undo_stack.endMacro()

        if pasted_nodes:
            min_x = min(n.pos()[0] for n in pasted_nodes)
            min_y = min(n.pos()[1] for n in pasted_nodes)
            for node in pasted_nodes:
                node.set_property("persistent_id", str(uuid.uuid4()))
                x, y = node.pos()
                new_x = x - min_x + avg_x + offset[0]
                new_y = y - min_y + avg_y + offset[1]
                node.set_pos(new_x, new_y)

            MessageManager.info("应用模板", f"已插入 {len(pasted_nodes)} 个节点", self.parent)
            if hasattr(self.parent, '_invalidate_node_cache'):
                self.parent._invalidate_node_cache()
        self.parent.graph.fit_to_selection()

    def delete_template(self, tid: str):
        import shutil
        template_path = self._template_dir / tid
        if template_path.exists():
            shutil.rmtree(template_path)
        # ✅ 清理缓存
        self._template_cache.pop(tid, None)
        self._refresh_content()  # 删除模板需立即刷新