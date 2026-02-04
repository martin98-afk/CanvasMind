# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel)
from qfluentwidgets import (CardWidget, PrimaryPushButton, FluentIcon, ToolButton,
                            CheckBox)

from app.utils.utils import get_icon


# --- 组件卡片 ---
class ComponentCard(CardWidget):
    action_signal = pyqtSignal(dict, str)
    delete_signal = pyqtSignal(dict)
    check_changed = pyqtSignal()  # 告知父容器勾选状态改变

    def __init__(self, data, mode="market", is_linked=False, is_admin=False, status_code="new", parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ComponentCard")
        self.data = data or {}
        self.mode = mode
        self.is_linked = is_linked
        self.is_admin = is_admin
        self.status_code = status_code  # "new", "match", "diff"
        self.setMinimumWidth(350)
        self.setFixedHeight(210)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 第一行：标题 + 复选框
        header = QHBoxLayout()

        # 修复 TypeError: 'NoneType' object is not subscriptable
        name_val = self.data.get('组件名称') or self.data.get('name') or 'P'
        display_name = str(name_val)

        icon_lbl = QLabel(display_name[0].upper())
        icon_lbl.setFixedSize(32, 32)
        icon_lbl.setAlignment(Qt.AlignCenter)

        # 根据源码一致性显示不同颜色样式
        icon_style = "color: white; border-radius: 6px; font-weight: bold; font-size: 14px;"
        if self.status_code == "diff":
            icon_style += "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f2994a, stop:1 #f2c94c);"
        else:
            icon_style += "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1f6feb, stop:1 #8144ff);"

        icon_lbl.setStyleSheet(icon_style)
        header.addWidget(icon_lbl)

        title_v = QVBoxLayout()
        title_v.setSpacing(0)
        name_lbl = QLabel(display_name)
        name_lbl.setObjectName("CardTitle")
        title_v.addWidget(name_lbl)

        uuid_val = self.data.get('组件id') or self.data.get('uuid') or '---'
        uuid_lbl = QLabel(str(uuid_val))
        uuid_lbl.setObjectName("CardUUID")
        title_v.addWidget(uuid_lbl)

        header.addLayout(title_v)
        header.addStretch()

        # 状态徽章 (增强版状态判断)
        if self.mode == "market":
            if self.status_code == "match":
                badge = QLabel("已就绪")
                badge.setObjectName("StatusTag")
                badge.setStyleSheet("background: rgba(40, 167, 69, 0.1); color: #28a745; border: 1px solid #28a745;")
                header.addWidget(badge)
            elif self.status_code == "diff":
                badge = QLabel("有更新")
                badge.setObjectName("StatusTag")
                badge.setStyleSheet("background: rgba(255, 193, 7, 0.1); color: #ffc107; border: 1px solid #ffc107;")
                header.addWidget(badge)
        elif self.is_linked:
            badge = QLabel("已同步")
            badge.setObjectName("StatusTag")
            header.addWidget(badge)

        self.check_box = CheckBox(self)
        self.check_box.stateChanged.connect(lambda: self.check_changed.emit())
        header.addWidget(self.check_box)
        layout.addLayout(header)

        # 第二行：描述
        desc_val = self.data.get('组件描述') or self.data.get('desc') or '暂无描述.'
        desc = QLabel(str(desc_val))
        desc.setObjectName("CardDesc")
        desc.setWordWrap(True)
        desc.setFixedHeight(40)
        desc.setAlignment(Qt.AlignTop)
        layout.addWidget(desc)

        # 第三行：作者与时间
        meta = QHBoxLayout()
        creator = self.data.get('创建人') or self.data.get('creator') or 'unknown'
        m_time = str(self.data.get('最后修改时间') or '---')
        meta_lbl = QLabel(f"by {creator} • {m_time}")
        meta_lbl.setStyleSheet("color: white; font-size: 11px;")
        meta.addWidget(meta_lbl)
        meta.addStretch()
        layout.addLayout(meta)

        # 第四行：标签与动作
        footer = QHBoxLayout()
        footer.setSpacing(6)

        cat_val = self.data.get('组件类别') or 'General'
        cat_tag = QLabel(str(cat_val))
        cat_tag.setObjectName("TagLabel")
        footer.addWidget(cat_tag)

        ver_val = self.data.get('版本号') or '1.0.0'
        ver_tag = QLabel(f"v{ver_val}")
        ver_tag.setObjectName("TagLabel")
        footer.addWidget(ver_tag)

        footer.addStretch()

        if self.mode == "market" and self.is_admin:
            self.delete_btn = ToolButton(FluentIcon.DELETE, self)
            self.delete_btn.setCursor(Qt.PointingHandCursor)
            self.delete_btn.setStyleSheet("""
                        ToolButton { color: #ff4d4f; }
                        ToolButton:hover { background: rgba(255, 77, 79, 0.1); color: #ff7875; }
                    """)
            self.delete_btn.setToolTip("从云端彻底删除")
            self.delete_btn.clicked.connect(lambda: self.delete_signal.emit(self.data))
            footer.addWidget(self.delete_btn)

        # 按钮文本处理
        btn_text = "安装" if self.mode == "market" else "上传"
        if self.mode == "market" and self.status_code == "diff":
            btn_text = "更新"

        icon = FluentIcon.DOWNLOAD if self.mode == "market" else get_icon("upload")
        self.action_btn = PrimaryPushButton(icon, btn_text)

        if self.mode == "market" and self.status_code == "match":
            self.action_btn.setEnabled(False)
            self.action_btn.setText("最新版")

        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.clicked.connect(lambda: self.action_signal.emit(self.data, self.mode))
        footer.addWidget(self.action_btn)

        layout.addLayout(footer)
