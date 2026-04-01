# -*- coding: utf-8 -*-
import os
import shutil
import uuid
from enum import Enum

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal, QPoint
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QSizePolicy,
    QWidget,
    QLabel,
    QApplication,
)
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    PushButton,
    BodyLabel,
    SearchLineEdit,
    ToggleToolButton,
    ScrollArea,
    FlowLayout,
    SimpleCardWidget,
    FluentIcon,
)

from app.utils.icon_name_map import ICON_NAME_TO_FILE


class LazyIconLoader:
    def __init__(self):
        self.builtin_icons_cache = None
        self.builtin_icons_loaded = False

    def get_builtin_icons(self):
        if not self.builtin_icons_loaded:
            self.builtin_icons_cache = []
            for icon_enum in FluentIcon:
                if isinstance(icon_enum, Enum):
                    self.builtin_icons_cache.append(
                        {
                            "icon": icon_enum.icon(),
                            "name": icon_enum.value,
                            "path": f"builtin:{icon_enum.name}",
                            "is_builtin": True,
                        }
                    )
            self.builtin_icons_loaded = True
        return self.builtin_icons_cache


class IconSelectorPopup(QWidget):
    """
    图标选择器 Popup 窗口
    发射信号: icon_selected(icon_path)
    """

    icon_selected = pyqtSignal(str)

    def __init__(self, parent, icons_dir=None):
        super().__init__(parent)
        self.icons_dir = icons_dir
        self.selected_icon_path = ""

        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(550, 450)

        self.icon_loader = LazyIconLoader()
        self.all_icon_items = []
        self.icon_widgets = []
        self.icon_buttons = {}

        self._init_ui()
        QTimer.singleShot(100, self.load_and_display_icons)
        QTimer.singleShot(200, self._select_first_icon)

    def _select_first_icon(self):
        if self.icon_widgets:
            first_btn = self.icon_widgets[0].findChild(ToggleToolButton)
            if first_btn:
                first_btn.click()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = SimpleCardWidget(self)
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
        self.container_layout.setContentsMargins(16, 16, 16, 16)
        self.container_layout.setSpacing(12)

        top_layout = QHBoxLayout()
        top_layout.addWidget(BodyLabel("选择图标"))
        top_layout.addStretch()

        self.icon_search = SearchLineEdit(self)
        self.icon_search.setFixedWidth(180)
        self.icon_search.setPlaceholderText("搜索图标...")

        self.icon_search_timer = QTimer()
        self.icon_search_timer.setSingleShot(True)
        self.icon_search_timer.timeout.connect(self._perform_icon_search)
        self.icon_search.textChanged.connect(self._on_icon_search_text_changed)
        top_layout.addWidget(self.icon_search)

        self.upload_btn = PushButton("上传图标", self)
        self.upload_btn.setIcon(FluentIcon.UP)
        self.upload_btn.clicked.connect(self._upload_icon)
        top_layout.addWidget(self.upload_btn)
        self.container_layout.addLayout(top_layout)

        scroll_area = ScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            "background: transparent; border: 1px solid #404040; border-radius: 8px;"
        )

        self.icon_container = QWidget()
        self.icon_container.setStyleSheet("background: transparent;")
        self.flow_layout = FlowLayout(self.icon_container)
        self.flow_layout.setContentsMargins(12, 12, 12, 12)
        self.flow_layout.setVerticalSpacing(12)
        self.flow_layout.setHorizontalSpacing(12)

        scroll_area.setWidget(self.icon_container)
        self.container_layout.addWidget(scroll_area)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.cancel_btn = PushButton("取消", self)
        self.cancel_btn.clicked.connect(self.close)

        self.confirm_btn = PushButton("确定", self)
        self.confirm_btn.clicked.connect(self._on_confirm)

        bottom_layout.addWidget(self.cancel_btn)
        bottom_layout.addWidget(self.confirm_btn)
        self.container_layout.addLayout(bottom_layout)

        self.main_layout.addWidget(self.container)

    def load_and_display_icons(self):
        self._clear_icon_layout()
        self.all_icon_items.clear()

        self.all_icon_items.append(
            {
                "icon": FluentIcon.APPLICATION.icon(),
                "name": "无图标",
                "path": "",
                "is_builtin": False,
            }
        )

        icon_files = [
            (name, f":/icons/{icon}") for name, icon in ICON_NAME_TO_FILE.items()
        ]
        for name, p in icon_files:
            pixmap = QPixmap(str(p)).scaled(
                64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon = QIcon(pixmap)
            self.all_icon_items.append(
                {"icon": icon, "name": name, "path": p, "is_builtin": False}
            )

        builtin_icons = self.icon_loader.get_builtin_icons()
        self.all_icon_items.extend(builtin_icons)

        self._refresh_icon_display(self.all_icon_items)

    def _clear_icon_layout(self):
        self.icon_buttons.clear()
        for widget in self.icon_widgets:
            widget.setParent(None)
            widget.deleteLater()
        self.icon_widgets.clear()
        while self.flow_layout.count():
            child = self.flow_layout.takeAt(0)
            if child:
                widget = child.widget()
                if widget:
                    widget.deleteLater()

    def _create_icon_widget(self, icon, name, path):
        item_widget = QWidget()
        item_widget.setFixedWidth(80)

        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(4)
        item_layout.setAlignment(Qt.AlignCenter)

        btn = ToggleToolButton(icon)
        btn.setFixedSize(64, 64)
        btn.setIconSize(QSize(48, 48))
        btn.setToolTip(name)
        btn.setProperty("icon_path", path)
        btn.clicked.connect(self._on_icon_clicked)
        item_layout.addWidget(btn, alignment=Qt.AlignCenter)

        label = QLabel(name)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        font_metrics = label.fontMetrics()
        elided_text = font_metrics.elidedText(name, Qt.ElideRight, 75)
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
            from loguru import logger

            logger.info(f"Icon clicked, selected_path: {path}")
            for btn in self.icon_buttons.keys():
                btn.setChecked(btn == sender)

    def _refresh_icon_display(self, items_to_show):
        self._clear_icon_layout()

        max_items = 200
        display_items = items_to_show[:max_items]

        for item in display_items:
            widget = self._create_icon_widget(item["icon"], item["name"], item["path"])
            self.flow_layout.addWidget(widget)
            self.icon_widgets.append(widget)

    def _on_icon_search_text_changed(self, text):
        self.icon_search_timer.stop()
        self.icon_search_timer.start(300)

    def _perform_icon_search(self):
        search_text = self.icon_search.text().lower()
        if not search_text:
            self._refresh_icon_display(self.all_icon_items)
            return

        filtered_items = [
            item for item in self.all_icon_items if search_text in item["name"].lower()
        ]
        self._refresh_icon_display(filtered_items)

    def _upload_icon(self):
        from PyQt5.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标", "", "Images (*.png *.jpg *.jpeg *.svg)"
        )

        if not file_path:
            return

        if not self.icons_dir:
            from app.scan_components import resource_path

            self.icons_dir = resource_path("app/component_extensions/custom_icons")

        if not os.path.exists(self.icons_dir):
            os.makedirs(self.icons_dir)

        try:
            ext = os.path.splitext(file_path)[1].lower()
            new_name = f"custom_{uuid.uuid4().hex}{ext}"
            dst = os.path.join(self.icons_dir, new_name)
            shutil.copy2(file_path, dst)

            self.selected_icon_path = dst
            QTimer.singleShot(0, self.load_and_display_icons)
            if self.icon_search.text():
                self._perform_icon_search()

            InfoBar.success(
                "成功", "图标上传成功", parent=self, position=InfoBarPosition.TOP_RIGHT
            )
        except Exception as e:
            InfoBar.error(
                "错误",
                f"上传失败: {e}",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
            )

    def _on_confirm(self):
        self.icon_selected.emit(self.selected_icon_path)
        self.close()

    def show_at_widget(self, widget):
        pos = widget.mapToGlobal(QPoint(0, widget.height()))
        screen = QApplication.primaryScreen().availableGeometry()

        btn_right = widget.mapToGlobal(QPoint(widget.width(), widget.height())).x()
        x = btn_right - self.width()
        y = pos.y()

        if x < screen.left():
            x = screen.left() + 5
        if x + self.width() > screen.right():
            x = screen.right() - self.width() - 5

        if y + self.height() > screen.bottom():
            y = widget.mapToGlobal(QPoint(0, 0)).y() - self.height()

        if y < screen.top():
            y = screen.top() + 5

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
