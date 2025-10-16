from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QListWidgetItem
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, ListWidget, PushButton,
    FluentIcon, BodyLabel, PrimaryPushButton
)
from pathlib import Path
import shutil
import uuid
import os


class AddQuickComponentDialog(MessageBoxBase):
    def __init__(self, parent, component_map, icons_dir: Path):
        super().__init__(parent)
        self.component_map = component_map
        self.icons_dir = icons_dir
        self.icons_dir.mkdir(exist_ok=True)
        self.selected_full_path = None
        self.selected_icon_path = ""

        self.titleLabel = SubtitleLabel('添加快捷组件', self)
        self.viewLayout.addWidget(self.titleLabel)

        # 组件列表
        self.comp_list = ListWidget(self)
        for full_path in sorted(self.component_map.keys()):
            comp_name = os.path.basename(full_path).replace('.py', '')
            item = QListWidgetItem(f"{comp_name} ({full_path})")
            item.setData(Qt.UserRole, full_path)
            self.comp_list.addItem(item)
        self.viewLayout.addWidget(BodyLabel("1. 选择组件："))
        self.viewLayout.addWidget(self.comp_list)

        # 图标选择
        self.icon_list = ListWidget(self)
        self.icon_list.setFixedHeight(120)
        self.icon_list.setViewMode(ListWidget.IconMode)
        self.icon_list.setIconSize(QSize(48, 48))
        self.icon_list.setSpacing(8)
        self.icon_list.setFlow(ListWidget.LeftToRight)
        self.icon_list.setWrapping(False)
        self.icon_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.icon_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # “无图标”
        none_item = QListWidgetItem("无图标")
        none_item.setIcon(FluentIcon.APPLICATION.icon())
        none_item.setData(Qt.UserRole, "")
        self.icon_list.addItem(none_item)

        # 加载已有图标
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.svg']:
            for p in self.icons_dir.glob(ext):
                pixmap = QPixmap(str(p)).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                item = QListWidgetItem(p.name)
                item.setIcon(QIcon(pixmap))
                item.setData(Qt.UserRole, str(p.resolve()))
                self.icon_list.addItem(item)

        self.viewLayout.addWidget(BodyLabel("2. 选择或上传图标："))
        icon_layout = QHBoxLayout()
        icon_layout.addWidget(self.icon_list)

        self.upload_btn = PushButton("上传图标", self)
        self.upload_btn.setIcon(FluentIcon.UP)
        self.upload_btn.clicked.connect(self._upload_icon)
        icon_layout.addWidget(self.upload_btn)
        icon_layout.addStretch()
        self.viewLayout.addLayout(icon_layout)

        self.yesButton.setText('确定')
        self.cancelButton.setText('取消')

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
            pixmap = QPixmap(str(dst)).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QListWidgetItem(new_name)
            item.setIcon(QIcon(pixmap))
            item.setData(Qt.UserRole, str(dst.resolve()))
            self.icon_list.addItem(item)
            self.icon_list.setCurrentItem(item)
        except Exception as e:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error("错误", f"上传失败: {e}", parent=self.parent(), position=InfoBarPosition.TOP_RIGHT)

    def validate(self):
        comp_item = self.comp_list.currentItem()
        if not comp_item:
            return False
        self.selected_full_path = comp_item.data(Qt.UserRole)
        icon_item = self.icon_list.currentItem()
        self.selected_icon_path = icon_item.data(Qt.UserRole) if icon_item else ""
        return True