# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve, QRect
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PyQt5.QtGui import QColor, QBrush, QPainter, QPen
from qfluentwidgets import (
    CardWidget,
    PrimaryPushButton,
    FluentIcon,
    ToolButton,
    CheckBox,
    TransparentToolButton,
)
from app.utils.utils import get_icon, get_unified_font


COLORS = {
    "bg": "#1a1a1a",
    "bg_hover": "#222222",
    "border": "#2d2d2d",
    "border_hover": "#3d3d3d",
    "primary": "#3b82f6",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "text_primary": "#ffffff",
    "text_secondary": "#a1a1a1",
    "text_muted": "#6b6b6b",
    "tag_bg": "#21262d",
}


class ComponentCard(CardWidget):
    action_signal = pyqtSignal(dict, str)
    delete_signal = pyqtSignal(dict)
    check_changed = pyqtSignal()

    _status_codes = ("new", "match", "diff", "old")

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
        self._is_checked = False
        self._hovered = False
        self.setMinimumWidth(320)
        self.setFixedHeight(200)
        self.setGraphicsEffect(self._create_shadow())
        self._setup_animations()
        self.init_ui()

    def _create_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        return shadow

    def _setup_animations(self):
        self._hover_anim = QPropertyAnimation(self, b"geometry")
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._shadow_anim = QPropertyAnimation(self.graphicsEffect(), b"blurRadius")
        self._shadow_anim.setDuration(150)

    def init_ui(self):
        self.setStyleSheet(f"""
            #ComponentCard {{
                background: {COLORS["bg"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 12px;
            }}
            #ComponentCard:hover {{
                background: {COLORS["bg_hover"]};
                border-color: {COLORS["border_hover"]};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._build_header(layout)
        self._build_description(layout)
        self._build_meta(layout)
        self._build_footer(layout)

    def _build_header(self, layout):
        header = QHBoxLayout()
        header.setSpacing(12)

        name_val = (
            self.data.get("组件名称")
            or self.data.get("name")
            or self.data.get("canvas_name")
            or "P"
        )
        display_name = str(name_val)

        self._icon_lbl = QLabel(display_name[0].upper())
        self._icon_lbl.setFixedSize(40, 40)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._update_icon_style()
        header.addWidget(self._icon_lbl)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)

        self._name_lbl = QLabel(display_name)
        self._name_lbl.setObjectName("CardTitle")
        self._name_lbl.setFont(get_unified_font(14, True))
        self._name_lbl.setStyleSheet(f"color: {COLORS['text_primary']};")
        title_v.addWidget(self._name_lbl)

        uuid_val = self.data.get("组件id") or self.data.get("uuid") or "---"
        self._uuid_lbl = QLabel(str(uuid_val)[:12])
        self._uuid_lbl.setObjectName("CardUUID")
        self._uuid_lbl.setFont(get_unified_font(10))
        self._uuid_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")
        title_v.addWidget(self._uuid_lbl)

        header.addLayout(title_v)
        header.addStretch()

        self._status_badge = self._create_status_badge()
        if self._status_badge:
            header.addWidget(self._status_badge)

        self.check_box = CheckBox(self)
        self.check_box.stateChanged.connect(self._on_check_changed)
        header.addWidget(self.check_box)
        layout.addLayout(header)

    def _update_icon_style(self):
        gradient_colors = {
            "new": ("#1f6feb", "#8144ff"),
            "match": ("#22c55e", "#16a34a"),
            "diff": ("#f2994a", "#f2c94c"),
            "old": ("#6c757d", "#5a6268"),
        }
        start, end = gradient_colors.get(self.status_code, gradient_colors["new"])
        self._icon_lbl.setStyleSheet(
            f"color: white; border-radius: 8px; font-weight: bold; font-size: 16px; "
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
                    f"background: rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1); "
                    f"color: {color}; border: 1px solid {color}; border-radius: 4px; "
                    f"padding: 2px 8px; font-size: 11px; font-weight: 500;"
                )
                return badge
        elif self.is_linked:
            badge = QLabel("已同步")
            badge.setStyleSheet(
                f"background: rgba(59, 130, 246, 0.1); color: {COLORS['primary']}; "
                f"border: 1px solid {COLORS['primary']}; border-radius: 4px; "
                f"padding: 2px 8px; font-size: 11px; font-weight: 500;"
            )
            return badge
        return None

    def _build_description(self, layout):
        desc_val = self.data.get("组件描述") or self.data.get("desc") or "暂无描述."
        self._desc_lbl = QLabel(str(desc_val))
        self._desc_lbl.setObjectName("CardDesc")
        self._desc_lbl.setFont(get_unified_font(12))
        self._desc_lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setFixedHeight(36)
        self._desc_lbl.setAlignment(Qt.AlignTop)
        layout.addWidget(self._desc_lbl)

    def _build_meta(self, layout):
        meta = QHBoxLayout()
        meta.setSpacing(8)

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
            meta_text = f"{creator} · 云端:{cloud_time[:10]} 本地:{local_time[:10]}"
        elif cloud_time:
            meta_text = f"{creator} · 云端:{cloud_time[:10]}"
        elif local_time:
            meta_text = f"{creator} · 本地:{local_time[:10]}"
        else:
            meta_text = f"{creator} · ---"

        self._meta_lbl = QLabel(meta_text)
        self._meta_lbl.setFont(get_unified_font(11))
        self._meta_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")
        meta.addWidget(self._meta_lbl)
        meta.addStretch()
        layout.addLayout(meta)

    def _build_footer(self, layout):
        footer = QHBoxLayout()
        footer.setSpacing(8)

        cat_val = self.data.get("组件类别") or self.data.get("category") or "常规"
        self._cat_tag = QLabel(str(cat_val))
        self._cat_tag.setFont(get_unified_font(11))
        self._cat_tag.setStyleSheet(
            f"background: {COLORS['tag_bg']}; color: {COLORS['text_secondary']}; "
            f"border-radius: 4px; padding: 3px 10px;"
        )
        footer.addWidget(self._cat_tag)

        ver_val = self.data.get("版本号") or "1.0.0"
        self._ver_tag = QLabel(f"v{ver_val}")
        self._ver_tag.setFont(get_unified_font(11))
        self._ver_tag.setStyleSheet(
            f"background: {COLORS['tag_bg']}; color: {COLORS['text_secondary']}; "
            f"border-radius: 4px; padding: 3px 10px;"
        )
        footer.addWidget(self._ver_tag)

        footer.addStretch()

        if self.mode == "market" and self.is_admin:
            self._delete_btn = ToolButton(FluentIcon.DELETE, self)
            self._delete_btn.setStyleSheet(f"color: {COLORS['error']};")
            self._delete_btn.clicked.connect(lambda: self.delete_signal.emit(self.data))
            footer.addWidget(self._delete_btn)

        btn_text, btn_enabled, btn_icon = self._get_action_config()
        self._action_btn = PrimaryPushButton(btn_icon, btn_text)
        self._action_btn.setEnabled(btn_enabled)
        self._action_btn.setFont(get_unified_font(12))
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

    def _on_check_changed(self):
        self._is_checked = self.check_box.isChecked()
        self.check_changed.emit()

    def enterEvent(self, event):
        self._hovered = True
        self._animate_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._animate_hover(False)
        super().leaveEvent(event)

    def _animate_hover(self, hovering):
        if hovering:
            self._shadow_anim.setStartValue(12)
            self._shadow_anim.setEndValue(24)
            self._shadow_anim.start()
        else:
            self._shadow_anim.setStartValue(24)
            self._shadow_anim.setEndValue(12)
            self._shadow_anim.start()

    def set_checked(self, checked):
        self.check_box.setChecked(checked)

    def set_visible(self, visible):
        self.setVisible(visible)

    def set_status(self, status_code):
        if status_code != self.status_code:
            self.status_code = status_code
            self._update_icon_style()
