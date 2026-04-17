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


COLORS = {
    "bg": "#1a1a1a",
    "bg_hover": "#21262d",
    "border": "#30363d",
    "primary": "#3b82f6",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "text_primary": "#f0f6fc",
    "text_secondary": "#8b949e",
    "text_muted": "#6b7280",
    "tag_bg": "#21262d",
}


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
        self.status_code = status_code
        self.setMinimumWidth(320)
        self.setFixedHeight(180)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            #ComponentCard {
                background: #1a1a1a;
                border: 1px solid #30363d;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self._build_header(layout)
        self._build_description(layout)
        self._build_footer(layout)

    def _build_header(self, layout):
        header = QHBoxLayout()
        header.setSpacing(10)

        name_val = (
            self.data.get("组件名称")
            or self.data.get("name")
            or self.data.get("canvas_name")
            or "P"
        )
        display_name = str(name_val)[:20]

        self._icon_lbl = QLabel(display_name[0].upper())
        self._icon_lbl.setFixedSize(36, 36)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._update_icon_style()
        header.addWidget(self._icon_lbl)

        title_v = QVBoxLayout()
        title_v.setSpacing(1)

        self._name_lbl = QLabel(display_name)
        self._name_lbl.setObjectName("CardTitle")
        self._name_lbl.setFont(get_unified_font(13, True))
        self._name_lbl.setStyleSheet(f"color: {COLORS['text_primary']};")
        self._name_lbl.setToolTip(display_name)
        title_v.addWidget(self._name_lbl)

        uuid_val = self.data.get("组件id") or self.data.get("uuid") or ""
        self._uuid_lbl = QLabel(str(uuid_val)[:8])
        self._uuid_lbl.setFont(get_unified_font(9))
        self._uuid_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")
        title_v.addWidget(self._uuid_lbl)

        header.addLayout(title_v)
        header.addStretch()

        self._status_badge = self._create_status_badge()
        if self._status_badge:
            header.addWidget(self._status_badge)

        self.check_box = CheckBox(self)
        self.check_box.stateChanged.connect(lambda: self.check_changed.emit())
        header.addWidget(self.check_box)
        layout.addLayout(header)

    def _update_icon_style(self):
        colors = {
            "new": ("#1f6feb", "#8144ff"),
            "match": ("#22c55e", "#16a34a"),
            "diff": ("#f2994a", "#f2c94c"),
            "old": ("#6c757d", "#5a6268"),
        }
        start, end = colors.get(self.status_code, colors["new"])
        self._icon_lbl.setStyleSheet(
            f"color: white; border-radius: 6px; font-weight: bold; font-size: 14px; "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {start}, stop:1 {end});"
        )

    def _create_status_badge(self):
        if self.mode == "market":
            status_map = {
                "match": ("已就绪", COLORS["success"]),
                "diff": ("有更新", COLORS["warning"]),
                "old": ("云端较旧", COLORS["text_muted"]),
            }
            if self.status_code in status_map:
                text, color = status_map[self.status_code]
                badge = QLabel(text)
                badge.setStyleSheet(
                    f"background: transparent; color: {color}; border: 1px solid {color}; "
                    f"border-radius: 4px; padding: 1px 6px; font-size: 10px;"
                )
                return badge
        elif self.is_linked:
            badge = QLabel("已同步")
            badge.setStyleSheet(
                f"background: transparent; color: {COLORS['primary']}; "
                f"border: 1px solid {COLORS['primary']}; border-radius: 4px; "
                f"padding: 1px 6px; font-size: 10px;"
            )
            return badge
        return None

    def _build_description(self, layout):
        desc_val = self.data.get("组件描述") or self.data.get("desc") or ""
        self._desc_lbl = QLabel(
            str(desc_val)[:60] + ("..." if len(str(desc_val)) > 60 else "")
        )
        self._desc_lbl.setFont(get_unified_font(11))
        self._desc_lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setFixedHeight(32)
        self._desc_lbl.setAlignment(Qt.AlignTop)
        self._desc_lbl.setToolTip(str(desc_val))
        layout.addWidget(self._desc_lbl)

    def _build_footer(self, layout):
        footer = QHBoxLayout()
        footer.setSpacing(6)

        cat_val = self.data.get("组件类别") or self.data.get("category") or "常规"
        self._cat_tag = QLabel(str(cat_val)[:6])
        self._cat_tag.setFont(get_unified_font(10))
        self._cat_tag.setStyleSheet(
            f"background: {COLORS['tag_bg']}; color: {COLORS['text_secondary']}; "
            f"border-radius: 3px; padding: 2px 6px;"
        )
        footer.addWidget(self._cat_tag)

        ver_val = self.data.get("版本号") or "1.0.0"
        self._ver_tag = QLabel(f"v{ver_val}")
        self._ver_tag.setFont(get_unified_font(10))
        self._ver_tag.setStyleSheet(
            f"background: {COLORS['tag_bg']}; color: {COLORS['text_secondary']}; "
            f"border-radius: 3px; padding: 2px 6px;"
        )
        footer.addWidget(self._ver_tag)

        creator = (
            self.data.get("创建人")
            or self.data.get("creator")
            or self.data.get("author")
            or ""
        )[:8]
        self._creator_lbl = QLabel(creator)
        self._creator_lbl.setFont(get_unified_font(10))
        self._creator_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")
        footer.addWidget(self._creator_lbl)

        footer.addStretch()

        if self.mode == "market" and self.is_admin:
            self._delete_btn = ToolButton(FluentIcon.DELETE, self)
            self._delete_btn.setStyleSheet(f"color: {COLORS['error']};")
            self._delete_btn.clicked.connect(lambda: self.delete_signal.emit(self.data))
            footer.addWidget(self._delete_btn)

        btn_text, btn_enabled, btn_icon = self._get_action_config()
        self._action_btn = PrimaryPushButton(btn_icon, btn_text)
        self._action_btn.setEnabled(btn_enabled)
        self._action_btn.setFont(get_unified_font(11))
        self._action_btn.clicked.connect(
            lambda: self.action_signal.emit(self.data, self.mode)
        )
        footer.addWidget(self._action_btn)
        layout.addLayout(footer)

    def _get_action_config(self):
        if self.mode == "market":
            if self.status_code == "match":
                return ("最新版", False, FluentIcon.ACCEPT)
            elif self.status_code == "old":
                return ("回滚", True, FluentIcon.DOWNLOAD)
            elif self.status_code == "diff":
                return ("更新", True, FluentIcon.UPDATE)
            return ("安装", True, FluentIcon.DOWNLOAD)
        return ("上传", True, get_icon("upload"))

    def set_checked(self, checked):
        self.check_box.setChecked(checked)

    def set_visible(self, visible):
        self.setVisible(visible)

    def set_status(self, status_code):
        if status_code != self.status_code:
            self.status_code = status_code
            self._update_icon_style()
