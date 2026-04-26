# -*- coding: utf-8 -*-
"""
文件撤销预览对话框
"""

from pathlib import Path
from typing import Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QWidget,
)
from qfluentwidgets import (
    PrimaryPushButton,
    PushButton,
    TransparentToolButton,
    FluentIcon,
    isDarkTheme,
)

from app.utils.utils import get_icon


class FileUndoPreviewDialog(QDialog):
    """文件撤销预览对话框"""

    # 结果类型
    CANCEL = 0      # 取消撤销
    KEEP_CARD = 1   # 不还原文件（卡片也撤销）
    RESTORE = 2     # 还原所选文件

    def __init__(self, operations: List[Dict], parent=None):
        super().__init__(parent)
        self.operations = operations
        self._selected_set = set(range(len(operations)))  # 默认全选
        self._result = self.CANCEL
        self._init_ui()

    def _init_ui(self):
        dark = isDarkTheme()
        bg_color = "#1e1e1e" if dark else "#ffffff"
        text_color = "#e0e0e0" if dark else "#333333"
        border_color = "#3a3a3a" if dark else "#d0d0d0"

        self.setWindowTitle("还原文件")
        self.setMinimumSize(800, 600)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
                color: {text_color};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel("确认撤销以下文件操作？", self)
        title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {text_color};")
        layout.addWidget(title_label)

        # 说明
        desc_label = QLabel(
            "点击「确认撤销」将恢复这些文件到操作前的状态。\n"
            "此操作不可撤销。",
            self
        )
        desc_label.setStyleSheet(f"color: #8c99ad; font-size: 13px;")
        layout.addWidget(desc_label)

        # 文件列表
        list_label = QLabel(f"共 {len(self.operations)} 个文件将被回滚：", self)
        list_label.setStyleSheet(f"font-weight: bold; color: {text_color};")
        layout.addWidget(list_label)

        # 全选
        select_layout = QHBoxLayout()
        self.select_all_cb = QCheckBox("全选", self)
        self.select_all_cb.setChecked(True)
        self.select_all_cb.stateChanged.connect(self._on_select_all_changed)
        select_layout.addWidget(self.select_all_cb)
        select_layout.addStretch()
        layout.addLayout(select_layout)

        # 文件列表
        list_widget = QListWidget(self)
        list_widget.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {border_color};
                border-radius: 8px;
                background-color: {bg_color};
            }}
            QListWidget::item {{
                padding: 4px;
                border-bottom: 1px solid {border_color};
            }}
        """)

        self.file_cbs = []
        for i, op in enumerate(self.operations):
            file_path = op.get("file_path", "")
            file_name = Path(file_path).name if file_path else "未知"
            tool_name = op.get("tool_name", "")

            item = QListWidgetItem(list_widget)
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(10, 8, 10, 8)

            cb = QCheckBox()
            cb.setChecked(True)
            cb.index = i
            cb.stateChanged.connect(self._on_item_check_changed)
            self.file_cbs.append(cb)

            name_label = QLabel(file_name)
            name_label.setStyleSheet(f"color: {text_color}; font-weight: bold;")

            path_label = QLabel(file_path)
            path_label.setStyleSheet(f"color: #8c99ad; font-size: 12px;")
            path_label.setWordWrap(True)

            item_layout.addWidget(cb, 0)
            item_layout.addWidget(name_label, 0)
            item_layout.addWidget(path_label, 1)

            # 添加差异查看按钮
            diff_btn = TransparentToolButton(get_icon("差异对比"), self)
            diff_btn.setFixedSize(24, 24)
            diff_btn.setToolTip("查看差异")
            diff_btn.op_index = i
            diff_btn.clicked.connect(lambda _, idx=i: self._show_diff(idx))
            item_layout.addWidget(diff_btn, 0)

            item.setSizeHint(item_widget.sizeHint())
            list_widget.addItem(item)
            list_widget.setItemWidget(item, item_widget)

        layout.addWidget(list_widget, 1)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = PushButton("取消撤销", self)
        self.cancel_btn.setDefault(False)
        self.cancel_btn.clicked.connect(self._on_cancel)

        self.keep_btn = PushButton("不还原更改", self)
        self.keep_btn.clicked.connect(self._on_keep)

        self.restore_btn = PrimaryPushButton("还原所选文件", self)
        self.restore_btn.setDefault(True)
        self.restore_btn.clicked.connect(self._on_restore)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.keep_btn)
        btn_layout.addWidget(self.restore_btn)
        layout.addLayout(btn_layout)

    def _on_select_all_changed(self, state):
        checked = state == Qt.Checked
        self._selected_set = set(range(len(self.operations))) if checked else set()
        for cb in self.file_cbs:
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)

    def _on_item_check_changed(self, state):
        cb = self.sender()
        if state == Qt.Checked:
            self._selected_set.add(cb.index)
        else:
            self._selected_set.discard(cb.index)

        all_checked = len(self._selected_set) == len(self.operations)
        none_checked = len(self._selected_set) == 0
        self.select_all_cb.blockSignals(True)
        self.select_all_cb.setCheckState(Qt.Checked if all_checked else (Qt.Unchecked if none_checked else Qt.PartiallyChecked))
        self.select_all_cb.blockSignals(False)

    def _on_cancel(self):
        """取消撤销"""
        self._result = self.CANCEL
        self.reject()

    def _on_keep(self):
        """不还原文件（但卡片撤销）"""
        self._result = self.KEEP_CARD
        self.selected_ops = []
        self.accept()

    def _on_restore(self):
        """还原所选文件"""
        self._result = self.RESTORE
        self.selected_ops = [self.operations[i] for i in sorted(self._selected_set)]
        if not self.selected_ops:
            return
        self.accept()

    def _show_diff(self, index: int):
        """显示指定操作的差异"""
        from app.widgets.side_dock_area.plugins.llm_chatter.utils.diff_viewer import (
            DiffHtmlGenerator,
            DiffViewerWindow,
        )

        op = self.operations[index]
        file_path = op.get("file_path", "")
        backup_path = op.get("backup_path", "")

        if not file_path or not backup_path:
            return

        try:
            # 读取备份文件和当前文件
            with open(backup_path, 'r', encoding='utf-8', errors='replace') as f:
                old_content = f.read()
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                new_content = f.read()

            # 生成 unified diff
            import difflib
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=Path(file_path).name,
                tofile=Path(file_path).name,
                lineterm='\n'
            )

            diff_output = ''.join(diff)
            html = DiffHtmlGenerator.generate_html_report(diff_output, "")

            viewer = DiffViewerWindow(parent=self)
            viewer.load_html(html)
            viewer.show()

        except Exception as e:
            from loguru import logger
            logger.error(f"[FileUndo] 显示差异失败: {e}")

    def get_result(self) -> int:
        """获取用户的选择"""
        return self._result

    def get_selected_operations(self) -> List[Dict]:
        """获取选中的操作列表"""
        return getattr(self, 'selected_ops', [])