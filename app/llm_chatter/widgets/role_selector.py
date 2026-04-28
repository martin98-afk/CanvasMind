# -*- coding: utf-8 -*-
"""
RoleSelector - 标题栏角色选择器

在标题栏添加下拉框选择当前会话的角色身份
"""

from typing import Optional
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QComboBox
from qfluentwidgets import ToolButton, FluentIcon

from app.llm_chatter.core.role_config import get_role_config_manager


class RoleSelector(QWidget):
    """角色选择器组件"""

    roleChanged = pyqtSignal(str)  # 角色 ID 变化信号
    roleCleared = pyqtSignal()  # 清除角色信号（选择"无身份"时）
    editRequested = pyqtSignal(str)  # 编辑请求信号

    # 角色颜色和简称
    ROLE_DATA = {
        "coordinator": {"color": "#4EC9B0", "short": "统筹"},
        "developer": {"color": "#569CD6", "short": "开发"},
        "designer": {"color": "#DCDCAA", "short": "设计"},
        "tester": {"color": "#CE9178", "short": "测试"},
        "custom": {"color": "#888888", "short": "自定义"},
    }

    # 无身份的颜色
    NO_ROLE_COLOR = "#666666"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_role_id = ""
        self._current_session_id = ""
        self._role_config_manager = get_role_config_manager()

        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)

        # 角色下拉框
        self._combo = QComboBox(self)
        self._combo.setFixedWidth(70)
        self._set_combo_style(self.NO_ROLE_COLOR)
        self._combo.currentTextChanged.connect(self._on_role_changed)
        layout.addWidget(self._combo)

        # 编辑按钮
        self._edit_btn = ToolButton(FluentIcon.EDIT, self)
        self._edit_btn.setFixedSize(20, 20)
        self._edit_btn.setToolTip("编辑角色")
        self._edit_btn.clicked.connect(self._on_edit_clicked)
        self._edit_btn.setStyleSheet("""
            ToolButton {
                background: transparent;
                border: none;
            }
            ToolButton:hover {
                background: rgba(255,255,255,0.1);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self._edit_btn)

        # 加载角色列表
        self._refresh_role_list()

    def _set_combo_style(self, color: str):
        """设置下拉框样式"""
        self._combo.setStyleSheet(f"""
            QComboBox {{
                background-color: rgba(255, 255, 255, 0.05);
                color: {color};
                border: 1px solid {color}40;
                border-radius: 4px;
                padding: 2px 4px 2px 6px;
                font-size: 11px;
            }}
            QComboBox:hover {{
                background-color: rgba(255, 255, 255, 0.08);
                border-color: {color}80;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 14px;
            }}
            QComboBox::down-arrow {{
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid {color};
                margin-right: 2px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #1a2230;
                color: #AABBCC;
                selection-background-color: #2a3a50;
                border: 1px solid rgba(255,255,255,0.1);
                padding: 4px;
            }}
        """)

    def _refresh_role_list(self):
        """刷新角色列表"""
        self._combo.blockSignals(True)
        self._combo.clear()

        # 第一项：无身份（空字符串表示无身份）
        self._combo.addItem("无", "")
        self._combo.insertSeparator(1)

        # 预制角色
        preset_roles = self._role_config_manager.list_roles(
            include_preset=True, include_custom=False
        )
        for role in preset_roles:
            short_name = self.ROLE_DATA.get(role.id, {}).get("short", role.name[:2])
            self._combo.addItem(short_name, role.id)

        # 自定义角色
        custom_roles = self._role_config_manager.list_roles(
            include_preset=False, include_custom=True
        )
        if custom_roles:
            self._combo.insertSeparator(self._combo.count())
            for role in custom_roles:
                short_name = role.name[:2] if len(role.name) > 2 else role.name
                self._combo.addItem(short_name, role.id)

        # 默认选择"无身份"
        self._combo.setCurrentIndex(0)
        self._current_role_id = ""

        self._combo.blockSignals(False)

    def _on_role_changed(self, text: str):
        """角色选择变化"""
        role_id = self._combo.currentData() or ""

        if role_id == self._current_role_id:
            return

        old_role_id = self._current_role_id
        self._current_role_id = role_id

        if not role_id:
            # 选择"无身份"
            self._set_combo_style(self.NO_ROLE_COLOR)
            self.roleCleared.emit()
        else:
            # 选择有身份的角色
            color = self.ROLE_DATA.get(role_id, {}).get("color", "#888888")
            self._set_combo_style(color)
            self.roleChanged.emit(role_id)

    def _on_edit_clicked(self):
        """编辑按钮点击"""
        self.editRequested.emit(self._current_role_id)

    def set_current_role(self, role_id: str):
        """设置当前角色"""
        self._current_role_id = role_id
        index = self._combo.findData(role_id)
        if index >= 0:
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(index)
            self._combo.blockSignals(False)
            color = self.ROLE_DATA.get(role_id, {}).get("color", "#888888")
            self._set_combo_style(color)
        else:
            # 未找到，设置为"无身份"
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(0)
            self._combo.blockSignals(False)
            self._current_role_id = ""
            self._set_combo_style(self.NO_ROLE_COLOR)

    def set_session_id(self, session_id: str):
        """设置会话 ID"""
        self._current_session_id = session_id

    def get_current_role(self) -> str:
        """获取当前角色 ID（空字符串表示无身份）"""
        return self._combo.currentData() or ""

    def has_role(self) -> bool:
        """是否有选择角色"""
        return bool(self._combo.currentData())

    def refresh(self):
        """刷新角色列表"""
        self._refresh_role_list()
