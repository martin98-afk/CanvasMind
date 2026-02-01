import os
import shutil
import uuid
from enum import Enum

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal, QPoint
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy, QWidget, QLabel,
    QListWidgetItem, QApplication
)
from qfluentwidgets import (
    InfoBar, InfoBarPosition, PushButton, SubtitleLabel, ListWidget,
    FluentIcon, BodyLabel, SearchLineEdit, ToggleToolButton, ScrollArea,
    FlowLayout, SimpleCardWidget, PrimaryPushButton
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


class AddQuickComponentPopup(QWidget):
    """
    添加快捷组件的 Popup 窗口
    发射信号: component_added(full_path, icon_path)
    """
    component_added = pyqtSignal(str, str)

    def __init__(self, parent, component_map):
        super().__init__(parent)
        self.home = parent  # 假设 parent 有 config 属性
        self.component_map = component_map
        self.selected_full_path = None
        self.selected_icon_path = ""

        # 窗口属性设置
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 固定大小
        self.setFixedSize(960, 600)

        # 图标加载器
        self.icon_loader = LazyIconLoader()
        self.all_icon_items = []
        self.visible_icon_items = []
        self.icon_widgets = []
        self.icon_buttons = {}

        self._init_ui()

        # 延迟加载图标
        QTimer.singleShot(100, self.load_and_display_icons)

    def _init_ui(self):
        # === 主容器 ===
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = SimpleCardWidget(self)
        # 样式参考 CanvasSettingPopup，适配深色/浅色模式请根据实际需求调整背景色
        self.container.setStyleSheet("""
            SimpleCardWidget {
                background-color: #2D2D2D; 
                border: 1px solid #454545;
                border-radius: 12px;
            }
            QLabel {
                color: #FFFFFF;
            }
        """)

        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(20, 20, 20, 20)
        self.container_layout.setSpacing(16)

        # 1. 标题栏
        self.titleLabel = SubtitleLabel('添加快捷组件', self)
        self.container_layout.addWidget(self.titleLabel)

        # 2. 内容区（左右分栏）
        content_layout = QHBoxLayout()
        content_layout.setSpacing(24)

        # --- 左侧：组件列表 ---
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        left_layout.addWidget(BodyLabel("选择组件"))

        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText("搜索组件...")
        self.search_box.textChanged.connect(self.filter_components)
        left_layout.addWidget(self.search_box)

        self.comp_list = ListWidget(self)
        self.comp_list.setSelectionMode(self.comp_list.SingleSelection)
        self.comp_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 给 ListWidget 设置样式以确保在 popup 中可见
        self.comp_list.setStyleSheet("background-color: transparent; border: 1px solid #404040; border-radius: 8px;")
        self.populate_component_list()
        left_layout.addWidget(self.comp_list)

        # --- 右侧：图标网格区 ---
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # 右侧顶部工具栏
        top_layout = QHBoxLayout()
        top_layout.addWidget(BodyLabel("选择图标"))
        top_layout.addStretch()

        self.icon_search = SearchLineEdit(self)
        self.icon_search.setFixedWidth(200)
        self.icon_search.setPlaceholderText("搜索图标...")

        # 搜索防抖
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

        # 图标滚动区
        scroll_area = ScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("background: transparent; border: 1px solid #404040; border-radius: 8px;")

        self.icon_container = QWidget()
        self.icon_container.setStyleSheet("background: transparent;")
        self.flow_layout = FlowLayout(self.icon_container)
        self.flow_layout.setContentsMargins(15, 15, 15, 15)
        self.flow_layout.setVerticalSpacing(15)
        self.flow_layout.setHorizontalSpacing(15)

        scroll_area.setWidget(self.icon_container)
        right_layout.addWidget(scroll_area)

        content_layout.addWidget(left_frame, 1)
        content_layout.addWidget(right_frame, 2)
        self.container_layout.addLayout(content_layout)

        # 3. 底部按钮栏
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.cancelButton = PushButton('取消', self)
        self.cancelButton.clicked.connect(self.close)

        self.yesButton = PrimaryPushButton('确定', self)
        self.yesButton.clicked.connect(self._on_confirm)

        bottom_layout.addWidget(self.cancelButton)
        bottom_layout.addWidget(self.yesButton)
        self.container_layout.addLayout(bottom_layout)

        self.main_layout.addWidget(self.container)

    # === 逻辑处理部分 (大部分复用原代码) ===

    def populate_component_list(self):
        self.comp_list.clear()
        for full_path in sorted(self.component_map.keys()):
            comp_name = os.path.basename(full_path).replace('.py', '')
            item = QListWidgetItem(comp_name)
            item.setToolTip(full_path)
            item.setData(Qt.UserRole, full_path)
            self.comp_list.addItem(item)

    def load_and_display_icons(self):
        self._clear_icon_layout()
        self.all_icon_items.clear()

        # 1. "无图标"
        self.all_icon_items.append({
            "icon": FluentIcon.APPLICATION.icon(),
            "name": "无图标",
            "path": "",
            "is_builtin": False
        })

        # 2. 自定义图标
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

        # 3. 内置图标
        builtin_icons = self.icon_loader.get_builtin_icons()
        self.all_icon_items.extend(builtin_icons)

        self._refresh_icon_display(self.all_icon_items)

    def _clear_icon_layout(self):
        self.icon_buttons.clear()
        for widget in self.icon_widgets:
            widget.setParent(None)
            widget.deleteLater()
        self.icon_widgets.clear()
        # 清空布局
        while self.flow_layout.count():
            child = self.flow_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _create_icon_widget(self, icon, name, path):
        item_widget = QWidget()
        # 稍微调小尺寸以适应popup
        item_widget.setFixedWidth(100)

        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(4)
        item_layout.setAlignment(Qt.AlignCenter)

        btn = ToggleToolButton(icon)
        btn.setFixedSize(90, 90)
        btn.setIconSize(QSize(72, 72))
        btn.setToolTip(name)
        btn.setProperty('icon_path', path)
        btn.clicked.connect(self._on_icon_clicked)
        item_layout.addWidget(btn, alignment=Qt.AlignCenter)

        label = QLabel(name)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        # 截断过长文字
        font_metrics = label.fontMetrics()
        elided_text = font_metrics.elidedText(name, Qt.ElideRight, 90)
        label.setText(elided_text)
        label.setStyleSheet("font-size: 9pt; color: #aaa;")
        item_layout.addWidget(label)

        self.icon_buttons[btn] = path
        return item_widget

    def _on_icon_clicked(self):
        sender = self.sender()
        if sender in self.icon_buttons:
            path = self.icon_buttons[sender]
            self.selected_icon_path = path
            for btn in self.icon_buttons.keys():
                btn.setChecked(btn == sender)

    def _refresh_icon_display(self, items_to_show):
        self._clear_icon_layout()
        self.flow_layout.setContentsMargins(0, 0, 0, 0)

        # 性能优化：限制最大显示数量，如果太多就只显示前200个，或者分页
        # 这里暂时全显，但要注意 items_to_show 的大小
        max_items = 300
        display_items = items_to_show[:max_items]

        for item in display_items:
            widget = self._create_icon_widget(item["icon"], item["name"], item["path"])
            self.flow_layout.addWidget(widget)
            self.icon_widgets.append(widget)

        self.flow_layout.setContentsMargins(15, 15, 15, 15)

    def filter_components(self, text):
        for i in range(self.comp_list.count()):
            item = self.comp_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _on_icon_search_text_changed(self, text):
        self.icon_search_timer.stop()
        self.icon_search_timer.start(300)

    def _perform_icon_search(self):
        search_text = self.icon_search.text().lower()
        if not search_text:
            self._refresh_icon_display(self.all_icon_items)
            return

        filtered_items = [
            item for item in self.all_icon_items
            if search_text in item["name"].lower()
        ]
        self._refresh_icon_display(filtered_items)

    def _upload_icon(self):
        from PyQt5.QtWidgets import QFileDialog
        # 临时隐藏 Popup 避免文件选择框被覆盖或造成焦点问题（可选，视具体行为而定）
        # self.hide()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标", "", "Images (*.png *.jpg *.jpeg *.svg)"
        )
        # self.show()

        if not file_path:
            return
        try:
            # 假设 icons_dir 存在于 self.home 或者需要传递进来
            # 这里需要你根据实际项目结构调整获取 icons_dir 的方式
            icons_dir = getattr(self.home, 'icons_dir', os.path.join(os.getcwd(), 'icons'))
            if not os.path.exists(icons_dir):
                os.makedirs(icons_dir)

            ext = os.path.splitext(file_path)[1].lower()
            new_name = f"custom_{uuid.uuid4().hex}{ext}"
            dst = os.path.join(icons_dir, new_name)
            shutil.copy2(file_path, dst)

            # 更新列表
            QtCore.QTimer.singleShot(0, self.load_and_display_icons)
            if self.icon_search.text():
                self._perform_icon_search()

        except Exception as e:
            InfoBar.error("错误", f"上传失败: {e}", parent=self, position=InfoBarPosition.TOP_RIGHT)

    def _on_confirm(self):
        """点击确定按钮"""
        if self._validate():
            self.component_added.emit(self.selected_full_path, self.selected_icon_path)
            self.close()

    def _validate(self):
        comp_item = self.comp_list.currentItem()
        if not comp_item:
            InfoBar.warning("提示", "请选择一个组件", parent=self, position=InfoBarPosition.TOP_RIGHT)
            return False

        selected_path = comp_item.data(Qt.UserRole)

        # 检查是否已存在
        try:
            current_config = self.home.config.get(self.home.config.quick_components)
            if selected_path in [item["full_path"] for item in current_config]:
                InfoBar.warning("提示", "已存在同名组件", parent=self, position=InfoBarPosition.TOP_RIGHT)
                return False
        except Exception:
            pass  # 容错，防止 config 读取失败

        self.selected_full_path = selected_path
        return True

    def show_at_button(self, button):
        """
        在指定按钮附近显示弹窗。
        逻辑参考了 CanvasSettingPopup，确保不超出屏幕边界。
        """
        # 计算位置
        btn_pos = button.mapToGlobal(QPoint(0, 0))

        # 默认尝试对齐到按钮的右下角
        # x: 按钮右边 - 弹窗宽度
        # y: 按钮底边
        x = btn_pos.x() + button.width() - self.width()
        y = btn_pos.y() + button.height() + 5  # 留一点间隙

        # 获取屏幕尺寸进行边界修正
        screen = QApplication.primaryScreen().availableGeometry()

        # 如果右侧超出屏幕，往左移
        if x + self.width() > screen.right():
            x = screen.right() - self.width() - 10
        # 如果左侧超出屏幕，贴左边
        if x < screen.left():
            x = screen.left() + 10

        # 如果底部超出屏幕，往上移（显示在按钮上方）
        if y + self.height() > screen.bottom():
            y = btn_pos.y() - self.height() - 5

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()