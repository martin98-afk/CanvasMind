import os
import shutil
import uuid
from pathlib import Path
from enum import Enum

from PyQt5.QtCore import Qt, QSize, QEasingCurve
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy, QWidget, QLabel, QListWidgetItem
)
from qfluentwidgets import InfoBar, InfoBarPosition, TransparentPushButton, PushButton
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, ListWidget, FluentIcon, BodyLabel, SearchLineEdit, ToggleToolButton, ScrollArea,
    FlowLayout
)


class AddQuickComponentDialog(MessageBoxBase):
    def __init__(self, parent, component_map, icons_dir: Path):
        super().__init__(parent)
        self.home = parent
        self.component_map = component_map
        self.icons_dir = icons_dir
        self.icons_dir.mkdir(exist_ok=True)
        self.selected_full_path = None
        self.selected_icon_path = ""  # 空字符串表示“无图标”

        self.widget.setMinimumSize(960, 600)

        self.titleLabel = SubtitleLabel('添加快捷组件', self)
        self.viewLayout.addWidget(self.titleLabel)

        # === 主内容区：左右分栏 ===
        main_layout = QHBoxLayout()
        main_layout.setSpacing(24)

        # --- 左侧：组件列表 ---
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(BodyLabel("选择组件"))

        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText("搜索组件...")
        self.search_box.textChanged.connect(self.filter_components)
        left_layout.addWidget(self.search_box)

        self.comp_list = ListWidget(self)
        self.comp_list.setSelectionMode(self.comp_list.SingleSelection)
        self.comp_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.populate_component_list()
        left_layout.addWidget(self.comp_list)

        # --- 右侧：图标网格区（带滚动 + 名称）---
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 顶部标题
        top_layout = QHBoxLayout()
        top_layout.addWidget(BodyLabel("选择图标"))
        top_layout.addStretch()


        # 新增：图标搜索框（放在上传按钮上方）
        self.icon_search = SearchLineEdit(self)
        self.icon_search.setPlaceholderText("搜索图标...")
        self.icon_search.textChanged.connect(self.filter_icons)
        top_layout.addWidget(self.icon_search)

        self.upload_btn = PushButton("上传图标", self)
        self.upload_btn.setIcon(FluentIcon.UP)
        self.upload_btn.clicked.connect(self._upload_icon)
        top_layout.addWidget(self.upload_btn)
        right_layout.addLayout(top_layout)
        # Scroll Area for icons
        scroll_area = ScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("background: transparent; border: none;")
        right_frame.setStyleSheet("background: transparent;")

        self.icon_container = QWidget()
        self.flow_layout = FlowLayout(self.icon_container, needAni=True)
        self.flow_layout.setAnimation(250, QEasingCurve.OutQuad)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(20)
        scroll_area.setWidget(self.icon_container)
        right_layout.addWidget(scroll_area)

        # 存储所有图标按钮
        self.icon_buttons = []
        self.all_icon_items = []  # [{icon, name, path, is_builtin}, ...]

        self.load_and_display_icons()

        main_layout.addWidget(left_frame, 1)
        main_layout.addWidget(right_frame, 2)
        self.viewLayout.addLayout(main_layout)

        self.yesButton.setText('确定')
        self.cancelButton.setText('取消')

    def populate_component_list(self):
        self.comp_list.clear()
        for full_path in sorted(self.component_map.keys()):
            comp_name = os.path.basename(full_path).replace('.py', '')
            item = QListWidgetItem(comp_name)
            item.setToolTip(full_path)
            item.setData(Qt.UserRole, full_path)
            self.comp_list.addItem(item)

    def load_and_display_icons(self):
        """加载自定义图标 + 所有 FluentIcon 内置图标"""
        # Clear
        for btn in self.icon_buttons:
            btn.deleteLater()
        self.icon_buttons.clear()
        self.all_icon_items.clear()

        while self.flow_layout.count():
            child = self.flow_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 1. "无图标"
        self.all_icon_items.append({
            "icon": FluentIcon.APPLICATION.icon(),
            "name": "无图标",
            "path": "",
            "is_builtin": False
        })

        # 2. 自定义图标（来自 icons_dir）
        icon_files = []
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.svg']:
            icon_files.extend(self.icons_dir.glob(ext))
        icon_files = sorted(icon_files)

        for p in icon_files:
            pixmap = QPixmap(str(p)).scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon = QIcon(pixmap)
            name = p.stem
            self.all_icon_items.append({
                "icon": icon,
                "name": name,
                "path": str(p.resolve()),
                "is_builtin": False
            })

        # 3. 所有内置 FluentIcon（追加到最后）
        for icon_enum in FluentIcon:
            if isinstance(icon_enum, Enum):
                self.all_icon_items.append({
                    "icon": icon_enum.icon(),
                    "name": icon_enum.name,
                    "path": f"builtin:\\{icon_enum.name}",
                    "is_builtin": True
                })

        # 显示全部（后续由 filter_icons 过滤）
        self._refresh_icon_display(self.all_icon_items)

    def _refresh_icon_display(self, items_to_show):
        """根据过滤结果重新构建界面"""
        # 清空布局
        while self.flow_layout.count():
            child = self.flow_layout.takeAt(0)
            child.deleteLater()
        self.icon_buttons.clear()

        for item in items_to_show:
            self._add_icon_item(item["icon"], item["name"], item["path"])

    def _add_icon_item(self, icon, name, path):
        item_widget = QWidget()
        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(6)
        item_layout.setAlignment(Qt.AlignCenter)

        btn = ToggleToolButton(icon)
        btn.setFixedSize(110, 110)
        btn.setIconSize(QSize(96, 96))
        btn.setToolTip(name)
        btn.clicked.connect(lambda _, b=btn, p=path: self.on_icon_selected(b, p))
        item_layout.addWidget(btn, alignment=Qt.AlignCenter)

        label = QLabel(name)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setMaximumWidth(110)
        label.setStyleSheet("font-size: 10pt; color: #666;")
        item_layout.addWidget(label)

        self.flow_layout.addWidget(item_widget)
        self.icon_buttons.append(btn)

    def on_icon_selected(self, clicked_btn, path):
        self.selected_icon_path = path
        for btn in self.icon_buttons:
            btn.setChecked(btn == clicked_btn)

    def filter_components(self, text):
        for i in range(self.comp_list.count()):
            item = self.comp_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def filter_icons(self, text):
        """根据搜索词过滤图标（包括文件名和内置图标名）"""
        if not text:
            self._refresh_icon_display(self.all_icon_items)
            return

        filtered = []
        t = text.lower()
        for item in self.all_icon_items:
            if t in item["name"].lower():
                filtered.append(item)
        self._refresh_icon_display(filtered)

    def _upload_icon(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标", "", "Images (*.png *.jpg *.jpeg *.svg)"
        )
        if not file_path:
            return
        try:
            ext = os.path.splitext(file_path)[1].lower()
            new_name = f"custom_{uuid.uuid4().hex}{ext}"
            dst = self.icons_dir / new_name
            shutil.copy2(file_path, dst)
            self.load_and_display_icons()
            # 可选：自动聚焦到新图标（略复杂，此处省略）
        except Exception as e:
            InfoBar.error("错误", f"上传失败: {e}", parent=self.parent(), position=InfoBarPosition.TOP_RIGHT)

    def validate(self):
        comp_item = self.comp_list.currentItem()
        if not comp_item:
            InfoBar.warning("提示", "请选择一个组件", parent=self.parent(), position=InfoBarPosition.TOP_RIGHT)
            return False
        if comp_item.data(Qt.UserRole) in [
            item["full_path"] for item in self.home.config.get(self.home.config.quick_components)]:
            InfoBar.warning("提示", "已存在同名组件", parent=self.parent(), position=InfoBarPosition.TOP_RIGHT)
            return False

        self.selected_full_path = comp_item.data(Qt.UserRole)
        return True