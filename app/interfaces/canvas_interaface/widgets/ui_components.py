# -*- coding: utf-8 -*-
import os

from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFrame
from qfluentwidgets import TransparentToolButton, FluentIcon, LineEdit, RoundMenu, Action
from qtpy import QtGui

from app.utils.utils import get_icon
from ..constants import BUTTONS_CONTAINER_X_OFFSET


class CanvasUIComponents:
    def __init__(self, parent):
        self.parent = parent

    def create_floating_buttons(self):
        container = QWidget(self.parent.canvas_widget)
        container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        container.move(self.parent.canvas_widget.width() - BUTTONS_CONTAINER_X_OFFSET, 5)
        layout = QHBoxLayout(container)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        buttons = {
            'run': (FluentIcon.PLAY, "运行工作流", self.parent.run_workflow),
            'stop': (FluentIcon.PAUSE, "停止运行", self.parent.stop_workflow),
            'console': (get_icon("console"), "显示/隐藏调试控制台", self.parent.toggle_console_panel),
            'export': (FluentIcon.SAVE, "导出工作流", self.parent._save_via_dialog),
            'export_model': (FluentIcon.SHARE, "导出选中节点为独立模型", self.parent.export_selected_nodes_as_project),
            'close': (FluentIcon.CLOSE, "关闭当前画布", self.parent._close_current_canvas),
        }

        btn_widgets = {}
        for name, (icon, tooltip, slot) in buttons.items():
            btn = TransparentToolButton(icon, self.parent)
            btn.setToolTip(tooltip)
            btn.clicked.connect(slot)
            if name == 'stop':
                btn.hide()
            btn_widgets[name] = btn
            layout.addWidget(btn)

        layout.addStretch()
        container.setLayout(layout)
        container.show()

        self.parent.run_btn = btn_widgets['run']
        self.parent.stop_btn = btn_widgets['stop']
        self.parent.buttons_container = container

    def create_name_label(self):
        container = QWidget(self.parent.canvas_widget)
        container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        line_edit = LineEdit(container)
        line_edit.setStyleSheet("""
            LineEdit {
                background: transparent;
                border: none;
                padding: 2px 4px;
                color: white;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        line_edit.setText(self.parent.workflow_name)
        line_edit.textChanged.connect(self.parent.update_workflow_name)
        self._update_name_width(line_edit)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addStretch()
        container.setLayout(layout)
        container.show()
        self.parent.name_container = container
        QTimer.singleShot(0, self._position_name)

    def _update_name_width(self, line_edit):
        text = line_edit.text() or " "
        width = line_edit.fontMetrics().horizontalAdvance(text) + 24
        line_edit.setFixedWidth(max(width, 80))
        self.parent.name_container.setFixedWidth(line_edit.width())

    def _position_name(self):
        if not self.parent.name_container.isVisible():
            return
        name_edit = self.parent.name_container.findChild(LineEdit)
        if not name_edit:
            return
        self._update_name_width(name_edit)
        x = max(0, (self.parent.canvas_widget.width() - self.parent.name_container.width()) // 2)
        self.parent.name_container.move(x, 0)

    # ✅ 完整还原 floating_nodes（快捷节点面板）
    def create_floating_nodes(self):
        self.parent.nodes_container = QWidget(self.parent.canvas_widget)
        self.parent.nodes_container.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._update_nodes_container_position()

        self.parent.node_layout = QVBoxLayout(self.parent.nodes_container)
        self.parent.node_layout.setSpacing(3)
        self.parent.node_layout.setContentsMargins(0, 0, 0, 0)

        # === 固定控制流按钮 ===
        buttons = [
            ("更新", "创建迭代", lambda: self.parent.create_backdrop_node("ControlFlowIterateNode")),
            ("无限", "创建循环", lambda: self.parent.create_backdrop_node("ControlFlowLoopNode")),
            ("条件分支", "创建分支", lambda: self.parent.create_next_node("control_flow.ControlFlowBranchNode")),
            ("代码执行", "创建代码编辑", lambda: self.parent.create_next_node("dynamic.DYNAMIC_CODE")),
            ("工具", "创建工具调用", lambda: self.parent.create_next_node("dynamic.StatusDynamicNode_大模型组件_工具调用")),
        ]

        for icon_name, tooltip, slot in buttons:
            btn = TransparentToolButton(get_icon(icon_name), self.parent)
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(tooltip)
            btn.clicked.connect(slot)
            self.parent.node_layout.addWidget(btn)

        # === 分隔线 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #555;")
        self.parent.node_layout.addWidget(separator)

        # === 可显示的快捷按钮容器 ===
        self.parent.visible_quick_container = QWidget(self.parent.nodes_container)
        self.parent.visible_quick_layout = QVBoxLayout(self.parent.visible_quick_container)
        self.parent.visible_quick_layout.setSpacing(3)
        self.parent.visible_quick_layout.setContentsMargins(0, 0, 0, 0)
        self.parent.node_layout.addWidget(self.parent.visible_quick_container)

        # === "更多"按钮及其菜单 ===
        self.parent.more_quick_button = TransparentToolButton(FluentIcon.MORE, self.parent)
        self.parent.more_quick_button.setIconSize(QSize(20, 20))
        self.parent.more_quick_button.setToolTip("更多快捷组件")
        self.parent.more_quick_menu = RoundMenu(parent=self.parent)
        self.parent.more_quick_button.clicked.connect(self.parent._show_more_quick_menu)
        self.parent.node_layout.addWidget(self.parent.more_quick_button)

        # === "+" 按钮（始终在最后）===
        self.parent.add_quick_btn = TransparentToolButton(FluentIcon.ADD, self.parent)
        self.parent.add_quick_btn.setIconSize(QSize(20, 20))
        self.parent.add_quick_btn.setToolTip("添加快捷组件")
        self.parent.add_quick_btn.clicked.connect(self.parent.quick_manager.open_add_dialog)
        self.parent.node_layout.addWidget(self.parent.add_quick_btn)

        self.parent.nodes_container.setLayout(self.parent.node_layout)
        self.parent.nodes_container.show()
        self.parent._refresh_quick_buttons()

    def _update_nodes_container_position(self):
        if not hasattr(self.parent, 'nodes_container') or not self.parent.canvas_widget:
            return
        self.parent.nodes_container.adjustSize()
        y = max(50, (self.parent.canvas_widget.height() - self.parent.nodes_container.height()) // 2)
        self.parent.nodes_container.move(0, y)

    def _show_more_quick_menu(self):
        """显示“更多”按钮的菜单"""
        # Clear the menu first
        self.parent.more_quick_menu.clear()
        # Add actions for hidden quick components
        for full_path, icon_path in self._hidden_quick_components:
            comp_name = os.path.basename(full_path).replace('.py', '')
            if icon_path and os.path.exists(icon_path):
                icon = QtGui.QIcon(icon_path)
            elif icon_path.startswith("builtin:\\"):
                icon_name = icon_path.split("\\")[-1]
                icon = FluentIcon[icon_name]
            else:
                icon = FluentIcon.APPLICATION
            action = Action(
                icon, f"创建 {comp_name}",
                triggered=lambda _, fp=full_path, ip=icon_path: self.create_next_node(fp, ip)
            )
            action.setProperty("full_path", full_path)
            self.more_quick_menu.addAction(action)
        # Show the menu
        self.more_quick_menu.exec_(self.more_quick_button.mapToGlobal(QPoint(0, self.more_quick_button.height())))

    def _refresh_quick_buttons(self):
        MAX_VISIBLE_QUICK_BUTTONS = 7

        all_quick_components = self.parent.quick_manager.get_quick_components()
        num_quick = len(all_quick_components)

        # --- 清理现有按钮 ---
        # 清除可见容器中的按钮
        while self.visible_quick_layout.count():
            item = self.visible_quick_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 清空菜单
        self.more_quick_menu.clear()
        # 重置隐藏列表
        self._hidden_quick_components = []

        # --- 重新分配按钮 ---
        for i, qc in enumerate(all_quick_components):
            full_path = qc["full_path"]
            comp_name = os.path.basename(full_path).replace('.py', '')
            icon_path = qc.get("icon_path")

            if i > MAX_VISIBLE_QUICK_BUTTONS:
                self._hidden_quick_components.append((qc["full_path"], qc.get("icon_path")))
                self.more_quick_button.show()
            else:

                if icon_path and os.path.exists(icon_path):
                    icon = QtGui.QIcon(icon_path)
                elif icon_path.startswith("builtin:\\"):
                    icon_name = icon_path.split("\\")[-1]
                    icon = FluentIcon[icon_name]
                    icon_path = f":/qfluentwidgets/images/icons/{FluentIcon[icon_name].value}_white.svg"
                else:
                    icon = FluentIcon.APPLICATION
                    icon_path = f":/qfluentwidgets/images/icons/{FluentIcon.APPLICATION.value}_white.svg"

                btn = TransparentToolButton(icon, self)
                btn.setIconSize(QSize(20, 20))
                btn.setToolTip(f"创建 {comp_name}")
                btn.setProperty("full_path", full_path)
                btn.clicked.connect(lambda _, ip=icon_path, fp=full_path: self.create_next_node(fp, ip))

                # 右键菜单：删除
                btn.setContextMenuPolicy(Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, b=btn, fp=full_path: self._show_quick_button_menu(b, fp, pos)
                )
                self.visible_quick_layout.addWidget(btn)

        # 如果没有隐藏的组件，隐藏“更多”按钮
        if not self._hidden_quick_components:
            self.more_quick_button.hide()

        QtCore.QTimer.singleShot(0, self._update_nodes_container_position)