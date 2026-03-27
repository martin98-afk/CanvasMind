# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel
from qfluentwidgets import (
    CardWidget,
    PrimaryPushButton,
    FluentIcon,
    ToolButton,
    CheckBox,
)
from app.utils.utils import get_icon, get_unified_font


class ComponentCard(CardWidget):
    action_signal = pyqtSignal(dict, str)
    delete_signal = pyqtSignal(dict)
    check_changed = pyqtSignal()

    def __init__(
        self,
        data,
        mode="market",
        is_linked=False,
        is_admin=False,
        status_code="new",
        parent=None,
    ):
        super().__init__(parent=parent)
        self.setObjectName("ComponentCard")
        self.data = data or {}
        self.mode = mode
        self.is_linked = is_linked
        self.is_admin = is_admin
        self.status_code = status_code  # "new", "match", "diff" (新), "old" (旧)
        self.setMinimumWidth(350)
        self.setFixedHeight(210)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 第一行：标题 + 复选框
        header = QHBoxLayout()
        name_val = (
            self.data.get("组件名称")
            or self.data.get("name")
            or self.data.get("canvas_name")
            or "P"
        )
        display_name = str(name_val)

        icon_lbl = QLabel(display_name[0].upper())
        icon_lbl.setFixedSize(32, 32)
        icon_lbl.setAlignment(Qt.AlignCenter)

        icon_style = (
            "color: white; border-radius: 6px; font-weight: bold; font-size: 14px;"
        )
        if self.status_code == "diff":
            icon_style += "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f2994a, stop:1 #f2c94c);"
        elif self.status_code == "old":
            icon_style += "background: #6c757d;"  # 灰色表示旧版
        else:
            icon_style += "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1f6feb, stop:1 #8144ff);"

        icon_lbl.setStyleSheet(icon_style)
        header.addWidget(icon_lbl)

        title_v = QVBoxLayout()
        title_v.setSpacing(0)
        name_lbl = QLabel(display_name)
        name_lbl.setObjectName("CardTitle")
        name_lbl.setFont(get_unified_font(13, True))
        title_v.addWidget(name_lbl)

        uuid_val = self.data.get("组件id") or self.data.get("uuid") or "---"
        uuid_lbl = QLabel(str(uuid_val))
        uuid_lbl.setObjectName("CardUUID")
        uuid_lbl.setFont(get_unified_font(9))
        title_v.addWidget(uuid_lbl)

        header.addLayout(title_v)
        header.addStretch()

        # 状态徽章
        if self.mode == "market":
            if self.status_code == "match":
                badge = QLabel("已就绪")
                badge.setStyleSheet(
                    "background: rgba(40, 167, 69, 0.1); color: #28a745; border: 1px solid #28a745; border-radius: 4px; padding: 2px 6px; font-size: 10px;"
                )
                header.addWidget(badge)
            elif self.status_code == "diff":
                badge = QLabel("有更新")
                badge.setStyleSheet(
                    "background: rgba(255, 193, 7, 0.1); color: #ffc107; border: 1px solid #ffc107; border-radius: 4px; padding: 2px 6px; font-size: 10px;"
                )
                header.addWidget(badge)
            elif self.status_code == "old":
                badge = QLabel("云端较旧")
                badge.setStyleSheet(
                    "background: rgba(108, 117, 125, 0.1); color: #6c757d; border: 1px solid #6c757d; border-radius: 4px; padding: 2px 6px; font-size: 10px;"
                )
                header.addWidget(badge)
        elif self.is_linked:
            badge = QLabel("已同步")
            badge.setStyleSheet(
                "background: rgba(31, 111, 235, 0.1); color: #1f6feb; border: 1px solid #1f6feb; border-radius: 4px; padding: 2px 6px; font-size: 10px;"
            )
            header.addWidget(badge)

        self.check_box = CheckBox(self)
        self.check_box.stateChanged.connect(lambda: self.check_changed.emit())
        header.addWidget(self.check_box)
        layout.addLayout(header)

        # 第二行：描述
        desc_val = self.data.get("组件描述") or self.data.get("desc") or "暂无描述."
        desc = QLabel(str(desc_val))
        desc.setObjectName("CardDesc")
        desc.setFont(get_unified_font(10))
        desc.setWordWrap(True)
        desc.setFixedHeight(40)
        desc.setAlignment(Qt.AlignTop)
        layout.addWidget(desc)

        # 第三行：作者与时间
        meta = QHBoxLayout()
        creator = (
            self.data.get("创建人")
            or self.data.get("creator")
            or self.data.get("author")
            or "未知"
        )
        cloud_time = (
            self.data.get("cloud_updated_at") or self.data.get("updated_at") or ""
        )
        local_time = (
            self.data.get("local_updated_at") or self.data.get("最后修改时间") or ""
        )

        if cloud_time and local_time and cloud_time != local_time:
            meta_lbl = QLabel(
                f"by {creator} • 云端:{cloud_time[:10]} 本地:{local_time[:10]}"
            )
        elif cloud_time:
            meta_lbl = QLabel(f"by {creator} • 云端:{cloud_time[:10]}")
        elif local_time:
            meta_lbl = QLabel(f"by {creator} • 本地:{local_time[:10]}")
        else:
            meta_lbl = QLabel(f"by {creator} • ---")

        meta_lbl.setFont(get_unified_font(11))
        meta_lbl.setStyleSheet("color: #8b949e;")
        meta.addWidget(meta_lbl)
        meta.addStretch()
        layout.addLayout(meta)

        # 第四行：标签与动作
        footer = QHBoxLayout()
        footer.setSpacing(6)

        cat_val = self.data.get("组件类别") or self.data.get("category") or "常规"
        cat_tag = QLabel(str(cat_val))
        cat_tag.setFont(get_unified_font(11))
        cat_tag.setStyleSheet(
            "background: #21262d; color: #8b949e; border-radius: 4px; padding: 2px 8px;"
        )
        footer.addWidget(cat_tag)

        ver_val = self.data.get("版本号") or "1.0.0"
        ver_tag = QLabel(f"v{ver_val}")
        ver_tag.setFont(get_unified_font(11))
        ver_tag.setStyleSheet(
            "background: #21262d; color: #8b949e; border-radius: 4px; padding: 2px 8px;"
        )
        footer.addWidget(ver_tag)

        footer.addStretch()

        if self.mode == "market" and self.is_admin:
            self.delete_btn = ToolButton(FluentIcon.DELETE, self)
            self.delete_btn.setStyleSheet("color: #ff4d4f;")
            self.delete_btn.clicked.connect(lambda: self.delete_signal.emit(self.data))
            footer.addWidget(self.delete_btn)

        # 按钮逻辑
        btn_text = self.tr("安装") if self.mode == "market" else self.tr("上传")
        if self.mode == "market":
            if self.status_code == "diff":
                btn_text = self.tr("更新")
            elif self.status_code == "old":
                btn_text = self.tr("旧版本")

        icon = FluentIcon.DOWNLOAD if self.mode == "market" else get_icon("upload")
        self.action_btn = PrimaryPushButton(icon, btn_text)

        if self.mode == "market":
            if self.status_code == "match":
                self.action_btn.setEnabled(False)
                self.action_btn.setText(self.tr("最新版"))
            elif self.status_code == "old":
                self.action_btn.setEnabled(True)  # 允许回滚
                self.action_btn.setText(self.tr("回滚"))

        self.action_btn.clicked.connect(
            lambda: self.action_signal.emit(self.data, self.mode)
        )
        footer.addWidget(self.action_btn)
        layout.addLayout(footer)
