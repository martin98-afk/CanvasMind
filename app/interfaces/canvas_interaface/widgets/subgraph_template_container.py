# -*- coding: utf-8 -*-
import os
import json
import uuid
from pathlib import Path
from PyQt5.QtCore import Qt, QSize, QPoint, QRectF, QTimer
from PyQt5.QtWidgets import QLabel, QWidget, QVBoxLayout, QSizePolicy, QHBoxLayout, QSpacerItem, QLayoutItem, QApplication
from PyQt5.QtGui import QPixmap, QPainter, QImage
from qfluentwidgets import (
    CardWidget, TransparentToolButton, FluentIcon, BodyLabel, SmoothScrollArea,
    TransparentPushButton, StrongBodyLabel, RoundMenu, Action, ImageLabel
)

from app.interfaces.canvas_interaface.widgets.message_manager import MessageManager
from app.widgets.basic_widget.resizable_image_label import ResizableImageLabel
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog


class SubgraphTemplatePanel(QWidget):
    """子图模板面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("templateManager")
        self._template_cards = {}  # {template_id: card_widget}
        self._built = False

        # ✅ 模板存储目录
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

        add_env_btn = TransparentPushButton(text="添加为模板", parent=self, icon=FluentIcon.ADD)
        add_env_btn.clicked.connect(self.add_template)

        # 内容容器
        self.container = QWidget(self)
        self.container.setObjectName("templateContainer")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(5, 2, 5, 5)
        self.container_layout.setSpacing(6)

        scroll = self.set_scroll(self.container)
        layout.addWidget(add_env_btn)
        layout.addWidget(scroll, 1)

        QTimer.singleShot(100, self._refresh_content)
        self._built = True

    def set_scroll(self, widget):
        scroll = SmoothScrollArea(self)
        scroll.setStyleSheet("""
            SmoothScrollArea {
                background: transparent;
                border: none;
            }
        """)
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
        self._template_cards.clear()

        templates = self._load_templates()
        if not templates:
            label = BodyLabel("暂无子图模板")
            label.setAlignment(Qt.AlignCenter)
            self.container_layout.addWidget(label)
        else:
            for tid, name, img_path in templates:
                card = self._create_template_card(tid, name, img_path)
                self.container_layout.addWidget(card)
                self._template_cards[tid] = card

        self.container_layout.addStretch(1)

    def _load_templates(self):
        """从磁盘加载所有模板"""
        templates = []
        for tid_dir in self._template_dir.iterdir():
            if not tid_dir.is_dir():
                continue
            meta_file = tid_dir / "meta.json"
            preview_file = tid_dir / "preview.png"
            if meta_file.exists() and preview_file.exists():
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    templates.append((meta['id'], meta['name'], str(preview_file)))
                except Exception:
                    continue
        return templates

    def _create_template_card(self, tid: str, name: str, img_path: str):
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
        btn_layout.addStretch()
        apply_btn = TransparentToolButton(FluentIcon.ADD, self)
        apply_btn.setFixedSize(28, 28)
        apply_btn.setToolTip("应用模板")
        apply_btn.clicked.connect(lambda _, t=tid: self.apply_template(t))
        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(28, 28)
        delete_btn.setToolTip("删除模板")
        delete_btn.clicked.connect(lambda _, t=tid: self.delete_template(t))
        btn_layout.addWidget(apply_btn)
        btn_layout.addWidget(delete_btn)
        layout.addLayout(btn_layout)

        # 图片
        img_label = ResizableImageLabel(self)
        img_label.setMaxHeight(200)  # 可调
        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            img_label.setOriginalPixmap(pixmap)
        else:
            img_label.setOriginalPixmap(QPixmap())  # 触发 fallback
        layout.addWidget(img_label)

        # 右键菜单
        def show_context_menu(pos):
            menu = RoundMenu(parent=self)
            menu.addAction(Action(FluentIcon.ACCEPT_MEDIUM, "应用", triggered=lambda: self.apply_template(tid)))
            menu.addAction(Action(FluentIcon.DELETE, "删除", triggered=lambda: self.delete_template(tid)))
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    def add_template(self):
        # 获取 graph（假设通过 parent.graph 或 parent.graph_controller）
        graph = getattr(self.parent, 'graph', None)
        if not graph:
            MessageManager.error("错误", "无法获取画布", self)
            return

        selected_nodes = graph.selected_nodes()
        if not selected_nodes:
            MessageManager.warning("提示", "请先选择节点", self)
            return

        # 弹出输入框
        default_name = f"{getattr(self.parent, 'workflow_name', '未命名')}子图"
        template_name_dialog = CustomInputDialog("请输入模板名称", "模板名称", default_name, parent=self.parent)
        if not template_name_dialog.exec():
            return
        template_name = template_name_dialog.get_text().strip()
        if not template_name:
            return

        # 复制节点数据
        nodes_data = graph._serialize(selected_nodes)  # 应为 dict 或 JSON-serializable

        # 生成截图
        try:
            preview_pixmap = self._capture_selected_nodes(selected_nodes)
        except Exception as e:
            preview_pixmap = QPixmap(300, 180)
            preview_pixmap.fill(Qt.transparent)

        # 保存到磁盘
        tid = str(uuid.uuid4())
        template_path = self._template_dir / tid
        template_path.mkdir(exist_ok=True)

        # 保存节点数据
        with open(template_path / "nodes.json", "w", encoding="utf-8") as f:
            json.dump(nodes_data, f, ensure_ascii=False, indent=2)

        # 保存预览图
        preview_pixmap.save(str(template_path / "preview.png"))

        # 保存元信息
        with open(template_path / "meta.json", "w", encoding="utf-8") as f:
            json.dump({"id": tid, "name": template_name}, f, ensure_ascii=False)

        self._refresh_content()

    def _capture_selected_nodes(self, nodes):
        """生成选中节点的截图"""
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
        # 扩展边距
        rect.adjust(-25, -25, 25, 25)
        # 创建图像
        image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        # 渲染选中区域
        scene.render(painter, target=QRectF(image.rect()), source=rect)
        painter.end()

        return image

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

        # ===== 复用你原有的粘贴逻辑 =====
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
            # 如果你有缓存失效逻辑
            if hasattr(self.parent, '_invalidate_node_cache'):
                self.parent._invalidate_node_cache()

    def delete_template(self, tid: str):
        import shutil
        template_path = self._template_dir / tid
        if template_path.exists():
            shutil.rmtree(template_path)
        self._refresh_content()