# -*- coding: utf-8 -*-
"""
RoleEditorDialog - 角色编辑弹窗

用于编辑和创建自定义角色
"""

from typing import Optional
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFormLayout, QPushButton, QMessageBox
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, LineEdit, TextEdit, FluentIcon
)
from qfluentwidgets import setCustomStyleSheet

from app.llm_chatter.core.role_config import RoleConfig, get_role_config_manager


class RoleEditorDialog(QDialog):
    """角色编辑弹窗（深色主题）"""

    roleSaved = pyqtSignal(str)  # 保存后的角色 ID

    def __init__(self, role_id: str = "", parent=None):
        super().__init__(parent)
        self._role_id = role_id
        self._role_config_manager = get_role_config_manager()
        self._original_role: Optional[RoleConfig] = None

        self._setup_ui()
        self._load_role()

    def _setup_ui(self):
        self.setWindowTitle("编辑角色")
        self.setMinimumWidth(500)
        self.setMinimumHeight(450)

        # 深色主题样式
        self.setStyleSheet("""
            QDialog {
                background-color: #1a2230;
                color: #AABBCC;
            }
            QGroupBox {
                font-weight: bold;
                color: #8899AA;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
            }
        """)

        layout = QVBoxLayout(self)

        # 基本信息
        basic_group = QGroupBox("基本信息", self)
        basic_layout = QFormLayout(basic_group)

        self._id_edit = LineEdit(self)
        self._id_edit.setPlaceholderText("角色ID（英文，唯一）")
        self._id_edit.setStyleSheet("""
            LineEdit {
                background-color: #0d1520;
                color: #AABBCC;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                padding: 6px 10px;
            }
            LineEdit:focus {
                border: 1px solid #569CD6;
            }
        """)
        basic_layout.addRow("ID:", self._id_edit)

        self._name_edit = LineEdit(self)
        self._name_edit.setPlaceholderText("显示名称")
        self._name_edit.setStyleSheet(self._id_edit.styleSheet())
        basic_layout.addRow("名称:", self._name_edit)

        # 颜色选择
        color_layout = QHBoxLayout()
        self._color_btn = QPushButton("#888888", self)
        self._color_btn.setFixedWidth(80)
        self._color_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d1520;
                color: #AABBCC;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #152030;
                border-color: rgba(255,255,255,0.2);
            }
        """)
        self._color_btn.clicked.connect(self._on_color_clicked)
        color_layout.addWidget(self._color_btn)
        color_layout.addStretch()
        basic_layout.addRow("颜色:", color_layout)

        layout.addWidget(basic_group)

        # 提示词
        prompt_group = QGroupBox("角色提示词", self)
        prompt_layout = QVBoxLayout(prompt_group)

        self._prompt_edit = TextEdit(self)
        self._prompt_edit.setPlaceholderText("输入角色的系统提示词...")
        self._prompt_edit.setMinimumHeight(200)
        self._prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #0d1520;
                color: #AABBCC;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                padding: 10px;
            }
            QTextEdit:focus {
                border: 1px solid #569CD6;
            }
        """)
        prompt_layout.addWidget(self._prompt_edit)

        layout.addWidget(prompt_group)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._cancel_btn = PushButton("取消", self)
        self._cancel_btn.setStyleSheet("""
            PushButton {
                background-color: rgba(255,255,255,0.05);
                color: #8899AA;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                padding: 6px 16px;
            }
            PushButton:hover {
                background-color: rgba(255,255,255,0.1);
            }
        """)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        self._save_btn = PrimaryPushButton("保存", self)
        self._save_btn.setStyleSheet("""
            PrimaryPushButton {
                background-color: #4E93FF;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
            }
            PrimaryPushButton:hover {
                background-color: #6AA8FF;
            }
        """)
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)

        layout.addLayout(btn_layout)

    def _load_role(self):
        """加载角色配置"""
        if self._role_id:
            self._original_role = self._role_config_manager.get_role(self._role_id)
            if self._original_role:
                self._id_edit.setText(self._original_role.id)
                self._id_edit.setEnabled(False)  # ID 不可修改
                self._name_edit.setText(self._original_role.name)
                self._color_btn.setText(self._original_role.color)
                self._prompt_edit.setText(self._original_role.prompt)
                self.setWindowTitle(f"编辑角色 - {self._original_role.name}")

    def _on_color_clicked(self):
        """颜色选择"""
        from PyQt5.QtGui import QColor
        from PyQt5.QtWidgets import QColorDialog

        color = QColorDialog.getColor(
            QColor(self._color_btn.text()),
            self,
            "选择角色颜色"
        )
        if color.isValid():
            self._color_btn.setText(color.name())

    def _on_save(self):
        """保存角色"""
        role_id = self._id_edit.text().strip()
        name = self._name_edit.text().strip()
        color = self._color_btn.text()
        prompt = self._prompt_edit.toPlainText()

        if not role_id:
            self._id_edit.setFocus()
            return

        if not name:
            self._name_edit.setFocus()
            return

        # 确定角色类型
        role_type = "custom"
        preset_types = ["coordinator", "developer", "designer", "tester"]
        if role_id in preset_types:
            role_type = role_id

        # 创建/更新角色配置
        config = RoleConfig(
            id=role_id,
            name=name,
            role_type=role_type,
            prompt=prompt,
            color=color,
            is_preset=False,
        )

        if self._original_role:
            config.created_at = self._original_role.created_at

        if self._role_config_manager.save_custom_role(config):
            self.roleSaved.emit(role_id)
            self.accept()
        else:
            QMessageBox.warning(self, "保存失败", "无法保存角色配置")