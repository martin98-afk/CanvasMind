import os
import shutil
import uuid
from pathlib import Path
from enum import Enum

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy, QWidget, QLabel, QListWidgetItem
)
from qfluentwidgets import InfoBar, InfoBarPosition, PushButton
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, ListWidget, FluentIcon, BodyLabel, SearchLineEdit,
    ToggleToolButton, ScrollArea, FlowLayout
)

from app.utils.icon_name_map import ICON_NAME_TO_FILE


class LazyIconLoader:
    """懒加载图标管理器"""

    def __init__(self):
        self.builtin_icons_cache = None
        self.builtin_icons_loaded = False

    def get_builtin_icons(self):
        """懒加载内置图标"""
        if not self.builtin_icons_loaded:
            self.builtin_icons_cache = []
            for icon_enum in FluentIcon:
                if isinstance(icon_enum, Enum):
                    self.builtin_icons_cache.append({
                        "icon": icon_enum.icon(),
                        "name": icon_enum.name,
                        "path": f"builtin:\\{icon_enum.name}",
                        "is_builtin": True
                    })
            self.builtin_icons_loaded = True
        return self.builtin_icons_cache


class AddQuickComponentDialog(MessageBoxBase):
    def __init__(self, parent, component_map):
        super().__init__(parent)
        self.home = parent
        self.component_map = component_map
        self.selected_full_path = None
        self.selected_icon_path = ""

        self.widget.setMinimumSize(960, 600)

        # 添加懒加载管理器
        self.icon_loader = LazyIconLoader()

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
        # 使用防抖优化搜索性能
        self.icon_search_timer = QTimer()
        self.icon_search_timer.setSingleShot(True)
        self.icon_search_timer.timeout.connect(self._perform_icon_search)
        self.icon_search.textChanged.connect(self._on_icon_search_text_changed)
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
        self.flow_layout = FlowLayout(self.icon_container)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(20)
        scroll_area.setWidget(self.icon_container)
        right_layout.addWidget(scroll_area)

        # 存储所有图标信息和按钮映射
        self.all_icon_items = []  # [{icon, name, path, is_builtin}, ...]
        self.visible_icon_items = []  # 当前显示的图标项目
        self.icon_widgets = []  # 当前显示的图标widgets
        self.icon_buttons = {}  # 按钮到路径的映射，用于快速查找

        # 延迟加载图标，避免初始化时卡顿
        QTimer.singleShot(0, self.load_and_display_icons)  # 延迟100ms加载

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
        # 清理现有图标
        self._clear_icon_layout()
        self.all_icon_items.clear()
        self.visible_icon_items.clear()
        self.icon_widgets.clear()
        self.icon_buttons.clear()

        # 1. "无图标"
        self.all_icon_items.append({
            "icon": FluentIcon.APPLICATION.icon(),
            "name": "无图标",
            "path": "",
            "is_builtin": False
        })

        # 2. 自定义图标（来自 icons_dir）
        icon_files = [(name, f":/icons/{icon}") for name, icon in ICON_NAME_TO_FILE.items()]
        for i, (name, p) in enumerate(icon_files):
            pixmap = QPixmap(str(p)).scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon = QIcon(pixmap)
            self.all_icon_items.append({
                "icon": icon,
                "name": name,
                "path": p,
                "is_builtin": False
            })

        # 3. 所有内置 FluentIcon - 使用懒加载
        builtin_icons = self.icon_loader.get_builtin_icons()
        self.all_icon_items.extend(builtin_icons)

        # 显示所有图标
        self._refresh_icon_display(self.all_icon_items)

    def _clear_icon_layout(self):
        """清空图标布局"""
        # 清理按钮映射
        self.icon_buttons.clear()

        # 清理现有widgets
        for widget in self.icon_widgets:
            widget.setParent(None)  # 先断开父子关系
            widget.deleteLater()

        self.icon_widgets.clear()

        # 清空布局中的所有项
        while self.flow_layout.count():
            child = self.flow_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _create_icon_widget(self, icon, name, path):
        """创建单个图标widget"""
        item_widget = QWidget()
        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(6)
        item_layout.setAlignment(Qt.AlignCenter)

        btn = ToggleToolButton(icon)
        btn.setFixedSize(110, 110)
        btn.setIconSize(QSize(96, 96))
        btn.setToolTip(name)
        btn.setProperty('icon_path', path)  # 使用属性存储路径，避免闭包
        btn.clicked.connect(self._on_icon_clicked)
        item_layout.addWidget(btn, alignment=Qt.AlignCenter)

        label = QLabel(name)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setMaximumWidth(110)
        label.setStyleSheet("font-size: 10pt; color: #666;")
        item_layout.addWidget(label)

        # 存储按钮引用
        self.icon_buttons[btn] = path

        return item_widget

    def _on_icon_clicked(self):
        """图标按钮点击事件"""
        sender = self.sender()
        if sender in self.icon_buttons:
            path = self.icon_buttons[sender]
            self.selected_icon_path = path
            # 更新按钮状态 - 只有选中的按钮为checked
            for btn in self.icon_buttons.keys():
                btn.setChecked(btn == sender)

    def _refresh_icon_display(self, items_to_show):
        """根据过滤结果重新构建界面"""
        # 清空当前布局
        self._clear_icon_layout()

        # 临时禁用布局动画以提高性能
        self.flow_layout.setContentsMargins(0, 0, 0, 0)

        # 创建并添加显示的图标
        for item in items_to_show:
            widget = self._create_icon_widget(item["icon"], item["name"], item["path"])
            self.flow_layout.addWidget(widget)
            self.icon_widgets.append(widget)

        # 更新可见图标列表
        self.visible_icon_items = items_to_show

        # 恢复边距
        self.flow_layout.setContentsMargins(30, 30, 30, 30)

    def filter_components(self, text):
        for i in range(self.comp_list.count()):
            item = self.comp_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _on_icon_search_text_changed(self, text):
        """图标搜索框文本改变时触发（防抖）"""
        # 重置计时器，延迟执行搜索
        self.icon_search_timer.stop()
        self.icon_search_timer.start(300)  # 300ms防抖

    def _perform_icon_search(self):
        """执行图标搜索"""
        search_text = self.icon_search.text().lower()

        if not search_text:
            # 没有搜索词，显示所有图标
            self._refresh_icon_display(self.all_icon_items)
            return

        # 过滤匹配的图标 - 优化搜索逻辑
        filtered_items = [
            item for item in self.all_icon_items
            if search_text in item["name"].lower()
        ]

        # 重新显示过滤后的图标
        self._refresh_icon_display(filtered_items)

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
            # 重新加载图标列表
            QtCore.QTimer.singleShot(0, self.load_and_display_icons)
            # 恢复之前的搜索状态
            if self.icon_search.text():
                self._perform_icon_search()
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